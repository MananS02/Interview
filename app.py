import os
import json
import random
import pdfplumber
from fastapi import FastAPI, Request, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import requests
import httpx
from gtts import gTTS
from datetime import datetime
from typing import List, Dict, Optional
from pydantic import BaseModel, PrivateAttr
import uuid
import tempfile
import uvicorn
import logging
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from xhtml2pdf import pisa
import re
import os
import smtplib
import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import certifi
from motor.motor_asyncio import AsyncIOMotorClient

os.environ["GLOG_minloglevel"] = "2"  # Hide MediaPipe startup dump

# Import the proctoring service
from proctoring_service import ProctoringService

# Import LiveKit configuration
from livekit_config import livekit_manager

# FIXED: Track which sessions have been emailed to prevent duplicates
email_sent_for_session = set()

# --- Configure Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
load_dotenv()

# Check email configuration on startup
def check_email_configuration():
    """Check and log email configuration status on startup"""
    if EMAIL_USERNAME and EMAIL_PASSWORD:
        logger.info(f"✅ EMAIL CONFIGURED: {EMAIL_USERNAME} via {EMAIL_SMTP_SERVER}:{EMAIL_SMTP_PORT}")
        logger.info("✅ Automatic interview report emails will be sent to candidates")
    else:
        logger.warning("⚠️ EMAIL NOT CONFIGURED: Automatic report sending is DISABLED")
        logger.warning("💡 To enable email functionality:")
        logger.warning("   1. Edit the .env file")
        logger.warning("   2. Configure EMAIL_USERNAME and EMAIL_PASSWORD")
        logger.warning("   3. See EMAIL_README.md for detailed instructions")
        logger.warning("   4. Visit /email_setup_guide for step-by-step guidance")

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set default JSON response charset
@app.middleware("http")
async def add_charset_middleware(request: Request, call_next):
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith(("application/json", "text/html")):
        response.headers["content-type"] += "; charset=utf-8"
    return response

# Custom WebSocket class to ensure proper encoding
class EncodedWebSocket(WebSocket):
    async def send_text(self, data: str):
        # Ensure proper UTF-8 encoding and handle special characters
        if isinstance(data, str):
            data = data.encode('utf-8').decode('utf-8')
        await super().send_text(data)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

AUDIO_FOLDER = "audio_files"
os.makedirs(AUDIO_FOLDER, exist_ok=True)

# OpenRouter API Key (for all AI operations: questions, evaluation, analysis)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Sarvam AI API Key (for STT and TTS)
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")

# Email Configuration
EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "AI Interview System")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"
AUTO_EMAIL_ON_END = os.getenv("AUTO_EMAIL_ON_END", "false").lower() == "true"

# MongoDB configuration
MONGODB_URI = os.getenv("MONGODB_URI", "")
MONGODB_DB = os.getenv("MONGODB_DB", "Interview_bot")

# MongoDB client and collections (initialized on startup)
mongo_client: Optional[AsyncIOMotorClient] = None
mongo_db = None
jobs_collection = None
reports_collection = None
sessions_collection = None


# Database startup and shutdown handlers
@app.on_event("startup")
async def startup_db():
    """Initialize MongoDB connection and collections"""
    global mongo_client, mongo_db, jobs_collection, reports_collection, sessions_collection
    try:
        if not MONGODB_URI:
            logger.error("❌ MONGODB_URI not configured in .env")
            logger.warning("⚠️  Application will run without database persistence")
            return
        
        logger.info(f"🔄 Connecting to MongoDB: {MONGODB_DB}")
        mongo_client = AsyncIOMotorClient(
            MONGODB_URI,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            tls=True,
            tlsCAFile=certifi.where(),
            tlsDisableOCSPEndpointCheck=True
        )
        mongo_db = mongo_client[MONGODB_DB]
        jobs_collection = mongo_db["Jobs"]
        reports_collection = mongo_db["Interview_report"]
        sessions_collection = mongo_db["InterviewSessions"]
        
        # Test connection
        await mongo_client.admin.command('ping')
        logger.info(f"✅ MongoDB connected to database: {MONGODB_DB}")
        logger.info(f"✅ Collections: Jobs, Interview_report, InterviewSessions")
        
        # Create indexes for better performance
        await jobs_collection.create_index("id", unique=True)
        await reports_collection.create_index("session_id", unique=True)
        await reports_collection.create_index("candidate_email")
        await reports_collection.create_index("job_id")
        await sessions_collection.create_index("session_id", unique=True)
        await sessions_collection.create_index("job_id")
        await sessions_collection.create_index("status")
        logger.info("✅ MongoDB indexes created")
        
        # Load jobs from MongoDB into memory cache
        await load_jobs_from_db()
    except Exception as e:
        logger.error(f"❌ MongoDB startup failed: {e}")
        logger.warning("⚠️  Check your MongoDB credentials and network access settings")
        logger.warning("⚠️  Application will run without database persistence")

@app.on_event("shutdown")
async def shutdown_db():
    """Close MongoDB connection"""
    global mongo_client
    try:
        if mongo_client:
            mongo_client.close()
            logger.info("MongoDB disconnected")
    except Exception as e:
        logger.error(f"MongoDB shutdown error: {e}")

# Helper functions for MongoDB operations
async def save_interview_report_to_db(session_id: str, report: "InterviewReport", job_id: Optional[str] = None):
    """Save or update interview report in MongoDB"""
    try:
        now = datetime.now()
        report_doc = {
            "session_id": session_id,
            "candidate_name": report.candidate_name,
            "candidate_email": report.candidate_email,
            "candidate_phone": report.candidate_phone,
            "job_id": job_id,
            "report_json": report.dict(),
            "updated_at": now
        }

        # Upsert: update if exists, insert if not
        result = await reports_collection.update_one(
            {"session_id": session_id},
            {"$set": report_doc, "$setOnInsert": {"created_at": now}},
            upsert=True
        )
        
        if result.upserted_id:
            logger.info(f"✅ Report saved to MongoDB for session {session_id}")
        else:
            logger.info(f"✅ Report updated in MongoDB for session {session_id}")
    except Exception as e:
        logger.error(f"❌ Failed to save report to MongoDB: {e}")

async def get_interview_report_from_db(session_id: str) -> Optional[Dict]:
    """Retrieve interview report from MongoDB by session ID"""
    try:
        result = await reports_collection.find_one({"session_id": session_id})
        if result:
            # Remove MongoDB's _id field for cleaner output
            result.pop("_id", None)
            return result
        return None
    except Exception as e:
        logger.error(f"❌ Failed to retrieve report from MongoDB: {e}")
        return None

async def get_all_interview_reports_from_db(limit: int = 100, offset: int = 0) -> List[Dict]:
    """Retrieve all interview reports from MongoDB with pagination"""
    try:
        cursor = reports_collection.find().sort("created_at", -1).skip(offset).limit(limit)
        results = await cursor.to_list(length=limit)
        # Remove MongoDB's _id field from all results
        for result in results:
            result.pop("_id", None)
        return results
    except Exception as e:
        logger.error(f"❌ Failed to retrieve reports from MongoDB: {e}")
        return []

# Check email configuration on startup
check_email_configuration()

# Create a thread pool for blocking operations
executor = ThreadPoolExecutor(max_workers=4)

# Initialize proctoring service
proctoring_service = ProctoringService()

# --- PDF Parsing (pdfplumber) ---
def extract_text_from_pdf(pdf_path: str) -> str:
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        logger.info(f"pdfplumber extraction complete. Total text length: {len(text)}")
        return text.strip()
    except Exception as e:
        logger.error(f"Error during pdfplumber text extraction: {e}")
        return ""

async def query_gemini_with_retry(prompt: str, max_retries: int = 3) -> str:
    """Query OpenRouter with retry logic for rate limiting"""
    for attempt in range(max_retries):
        try:
            return await query_openrouter_general(prompt)
        except Exception as e:
            if "429" in str(e) or "Too Many Requests" in str(e):
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"Rate limited. Retrying in {wait_time:.2f} seconds... (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error("Max retries exceeded for API call")
                    # Return fallback instead of crashing
                    return "Unable to generate response due to API rate limits. Please try again later."
            else:
                raise
    return ""

# --- Resume Summarization Function ---
async def summarize_resume(resume_text: str) -> str:
    """Generate a comprehensive summary of the resume once to reuse in all prompts."""
    prompt = f"""
You are a smart AI assistant. The following is a candidate's resume.

Your job is to extract and summarize all key elements: education, projects, internships, certifications, skills, achievements, tools, and any other relevant details.

Present them in a clean and complete paragraph format. This will be reused throughout the interview.

Resume:
--------
{resume_text}
"""
    try:
        summary = (await query_gemini_with_retry(prompt)).strip()
        logger.info("Resume summarized successfully.")
        return summary
    except Exception as e:
        logger.error(f"Failed to summarize resume: {e}")
        return resume_text  # fallback to raw

# --- State management ---
# ADDED: User details model for face capture
class UserDetails(BaseModel):
    name: str = ""
    phone: str = ""
    email: str = ""

class InterviewState(BaseModel):
    user_details: UserDetails = UserDetails()  # ADDED
    resume_text: str = ""
    resume_summary: str = ""  # NEW: Store resume summary instead of full text
    current_dialogue: List[Dict] = []
    is_interview_active: bool = False
    current_question_count: int = 0
    max_questions: int = 7
    min_questions: int = 5
    last_question: str = ""
    consent_received: bool = False
    answer_evaluations: List[Dict] = []  # Store AI evaluations silently
    total_score: float = 0.0
    average_score: float = 0.0
    proctoring_session_id: str = ""  # Track proctoring session
    proctoring_violations: List[Dict] = []  # Track violations
    reference_face_captured: bool = False  # ADDED
    preloaded_questions: List[str] = []
    preloaded_question_types: List[str] = []  # Track question types: "text" or "coding"
    current_question_index: int = 0
    text_question_timer: int = 120  # Timer for text questions in seconds
    coding_question_timer: int = 300  # Timer for coding questions in seconds
    livekit_room_name: str = ""  # LiveKit room name for this session
    # Private attribute to track async evaluation tasks (not part of schema)
    _pending_eval_tasks: List[asyncio.Task] = PrivateAttr(default_factory=list)

class InterviewKPIs(BaseModel):
    communication_score: float = 0.0
    technical_score: float = 0.0
    problem_solving_score: float = 0.0
    confidence_score: float = 0.0
    clarity_score: float = 0.0
    response_time_avg: float = 0.0
    questions_answered: int = 0
    completion_rate: float = 0.0
    engagement_level: str = "Medium"
    strengths_count: int = 0
    improvement_areas_count: int = 0

class InterviewReport(BaseModel):
    candidate_name: str = "Candidate"
    candidate_phone: str = ""  # ADDED
    candidate_email: str = ""  # ADDED
    interview_date: str = ""
    overall_score: float = 0.0
    technical_score: float = 0.0
    communication_score: float = 0.0
    experience_score: float = 0.0
    problem_solving_score: float = 0.0
    detailed_feedback: str = ""
    resume_quality: str = ""
    technical_skills: str = ""
    communication_skills: str = ""
    strengths: List[str] = []
    areas_for_improvement: List[str] = []
    recommendations: str = ""
    interview_transcript: List[Dict] = []
    kpis: InterviewKPIs = InterviewKPIs()
    proctoring_violations: List[Dict] = []  # Add proctoring violations

# Admin: Job openings
class QuestionItem(BaseModel):
    text: str
    type: str = "text"  # "text" or "coding"

class JobOpening(BaseModel):
    id: str
    title: str
    description: str = ""
    location: str = ""
    experience: str = ""
    status: str = "open"  # open/closed/draft
    questions: List[str] = []  # Keep for backward compatibility
    question_items: List[QuestionItem] = []  # New structured format
    text_question_timer: int = 120  # Timer for text questions in seconds (default 2 minutes)
    coding_question_timer: int = 300  # Timer for coding questions in seconds (default 5 minutes)
    created_at: str = ""
    updated_at: str = ""

# DEPRECATED: Global interview_state (kept for backward compatibility)
interview_state = InterviewState()
logger.info("InterviewState initialized.")

# NEW: Dictionary to store interview states per session (for parallel interviews)
interview_states = {}  # {session_id: InterviewState}

# Global variable to store generated reports
generated_reports = {}

# ADDED: Simple storage for user details (for production, use a proper database)
user_sessions = {}

# Admin: in-memory jobs cache (loaded from MongoDB)
jobs: Dict[str, JobOpening] = {}

# MongoDB job operations
async def save_job_to_db(job: JobOpening) -> None:
    """Save or update a job in MongoDB Jobs collection"""
    try:
        job_doc = job.dict()
        # Upsert: update if exists, insert if not
        await jobs_collection.update_one(
            {"id": job.id},
            {"$set": job_doc},
            upsert=True
        )
        logger.info(f"✅ Job '{job.title}' saved to MongoDB (id: {job.id})")
    except Exception as e:
        logger.error(f"❌ Failed to save job to MongoDB: {e}")

async def delete_job_from_db(job_id: str) -> bool:
    """Delete a job from MongoDB Jobs collection"""
    try:
        result = await jobs_collection.delete_one({"id": job_id})
        if result.deleted_count > 0:
            logger.info(f"✅ Job deleted from MongoDB (id: {job_id})")
            return True
        return False
    except Exception as e:
        logger.error(f"❌ Failed to delete job from MongoDB: {e}")
        return False

# Session management functions
async def save_session_to_db(session_id: str, session_data: dict) -> None:
    """Save or update interview session in MongoDB"""
    try:
        if sessions_collection is None:
            logger.warning("⚠️  Sessions collection not initialized")
            return
        
        now = datetime.now()
        session_doc = {
            "session_id": session_id,
            "job_id": session_data.get("job_id"),
            "candidate": session_data.get("user_details", {}),
            "status": session_data.get("status", "in_progress"),
            "created_at": session_data.get("created_at", now.isoformat()),
            "completed_at": session_data.get("completed_at"),
            "current_state": {
                "question_index": session_data.get("question_index", 0),
                "dialogue": session_data.get("dialogue", []),
                "answer_evaluations": session_data.get("answer_evaluations", []),
                "proctoring_violations": session_data.get("proctoring_violations", []),
                "consent_received": session_data.get("consent_received", False),
                "preloaded_questions": session_data.get("preloaded_questions", []),
                "preloaded_question_types": session_data.get("preloaded_question_types", []),
            },
            "updated_at": now.isoformat()
        }
        
        # Upsert: update if exists, insert if not
        await sessions_collection.update_one(
            {"session_id": session_id},
            {"$set": session_doc},
            upsert=True
        )
        logger.debug(f"✅ Session {session_id} saved to MongoDB")
    except Exception as e:
        logger.error(f"❌ Failed to save session to MongoDB: {e}")

async def get_session_from_db(session_id: str) -> Optional[dict]:
    """Retrieve interview session from MongoDB"""
    try:
        if sessions_collection is None:
            logger.warning("⚠️  Sessions collection not initialized")
            return None
        
        session_doc = await sessions_collection.find_one({"session_id": session_id})
        if session_doc:
            session_doc.pop("_id", None)  # Remove MongoDB _id
            logger.debug(f"✅ Session {session_id} loaded from MongoDB")
            return session_doc
        return None
    except Exception as e:
        logger.error(f"❌ Failed to load session from MongoDB: {e}")
        return None

async def update_session_status(session_id: str, status: str, completed_at: Optional[str] = None) -> None:
    """Update session status in MongoDB"""
    try:
        if sessions_collection is None:
            return
        
        update_data = {
            "status": status,
            "updated_at": datetime.now().isoformat()
        }
        if completed_at:
            update_data["completed_at"] = completed_at
        
        await sessions_collection.update_one(
            {"session_id": session_id},
            {"$set": update_data}
        )
        logger.debug(f"✅ Session {session_id} status updated to {status}")
    except Exception as e:
        logger.error(f"❌ Failed to update session status: {e}")

def session_to_interview_state(session_doc: dict) -> InterviewState:
    """Convert MongoDB session document to InterviewState object"""
    state = InterviewState()
    
    # Load candidate details
    if "candidate" in session_doc:
        state.user_details = UserDetails(**session_doc["candidate"])
    
    # Load current state
    current_state = session_doc.get("current_state", {})
    state.current_dialogue = current_state.get("dialogue", [])
    state.answer_evaluations = current_state.get("answer_evaluations", [])
    state.proctoring_violations = current_state.get("proctoring_violations", [])
    state.consent_received = current_state.get("consent_received", False)
    state.preloaded_questions = current_state.get("preloaded_questions", [])
    state.preloaded_question_types = current_state.get("preloaded_question_types", [])
    state.current_question_index = current_state.get("question_index", 0)
    
    # Set session ID and status
    state.proctoring_session_id = session_doc.get("session_id", "")
    state.is_interview_active = session_doc.get("status") == "in_progress"
    
    # Set timers from job if available
    job_id = session_doc.get("job_id")
    if job_id and job_id in jobs:
        job = jobs[job_id]
        state.text_question_timer = job.text_question_timer
        state.coding_question_timer = job.coding_question_timer
    
    return state

async def save_interview_state_to_db(session_id: str, state: InterviewState) -> None:
    """Save current interview state to MongoDB (for real-time persistence)"""
    try:
        if sessions_collection is None:
            return
        
        session_data = {
            "question_index": state.current_question_index,
            "dialogue": state.current_dialogue,
            "answer_evaluations": state.answer_evaluations,
            "proctoring_violations": state.proctoring_violations,
            "consent_received": state.consent_received,
        }
        
        await sessions_collection.update_one(
            {"session_id": session_id},
            {"$set": {
                "current_state": session_data,
                "updated_at": datetime.now().isoformat()
            }}
        )
        logger.debug(f"Interview state saved for session {session_id}")
    except Exception as e:
        logger.error(f"Failed to save interview state: {e}")

async def load_jobs_from_db() -> None:
    """Load all jobs from MongoDB into memory cache"""
    global jobs
    try:
        if jobs_collection is None:
            logger.warning("⚠️  Jobs collection not initialized, skipping load")
            return
            
        cursor = jobs_collection.find()
        job_docs = await cursor.to_list(length=None)
        jobs = {}
        for doc in job_docs:
            doc.pop("_id", None)  # Remove MongoDB _id
            try:
                job = JobOpening(**doc)
                jobs[job.id] = job
                logger.debug(f"   Loaded job: {job.title} (ID: {job.id}, Questions: {len(job.questions)})")
            except Exception as e:
                logger.warning(f"Skipping invalid job document: {e}")
        logger.info(f"✅ Loaded {len(jobs)} job(s) from MongoDB")
        if len(jobs) > 0:
            for job_id, job in jobs.items():
                logger.info(f"   📋 {job.title} - {len(job.questions)} questions")
    except Exception as e:
        logger.error(f"❌ Failed to load jobs from MongoDB: {e}")
        jobs = {}

# --- WebSocket manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.proctoring_connections: List[WebSocket] = []
        logger.info("ConnectionManager initialized.")

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected: {websocket.client}")

    async def connect_proctoring(self, websocket: WebSocket):
        await websocket.accept()
        self.proctoring_connections.append(websocket)
        logger.info(f"Proctoring WebSocket connected: {websocket.client}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected: {websocket.client}")

    def disconnect_proctoring(self, websocket: WebSocket):
        if websocket in self.proctoring_connections:
            self.proctoring_connections.remove(websocket)
        logger.info(f"Proctoring WebSocket disconnected: {websocket.client}")

manager = ConnectionManager()

# --- Async Audio Generation with Sarvam Bulbul TTS ---
async def generate_audio_async(text: str, lang: str = 'en') -> str:
    """Generate audio using Sarvam Bulbul TTS API"""
    if not SARVAM_API_KEY:
        logger.warning("Sarvam API key not configured, falling back to gTTS")
        return await generate_audio_gtts_fallback(text, lang)
    
    filename = f"audio_{uuid.uuid4().hex}.mp3"
    filepath = os.path.join(AUDIO_FOLDER, filename)

    try:
        logger.info(f"Generating audio with Sarvam Bulbul TTS...")
        url = "https://api.sarvam.ai/text-to-speech"
        headers = {
            "api-subscription-key": SARVAM_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        payload = {
            "inputs": [text],
            "target_language_code": "en-IN",  # English (India)
            "speaker": "anushka",  # Valid female voice (matches test file)
            "pitch": 0,
            "pace": 1,
            "loudness": 1,
            "speech_sample_rate": 22050,
            "enable_preprocessing": True,
            "model": "bulbul:v2"  # Bulbul v2 for TTS
        }

        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            
            logger.info(f"Sarvam TTS response status: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"Sarvam TTS error: {response.status_code} - {response.text}")
                raise Exception(f"Sarvam API returned {response.status_code}")
            
            response.raise_for_status()
            
            # Sarvam returns base64 encoded audio (WAV format)
            result = response.json()
            logger.info(f"Sarvam TTS response keys: {result.keys()}")
            
            audio_base64 = result["audios"][0]
            
            # Decode and save
            import base64
            audio_data = base64.b64decode(audio_base64)
            
            # Ensure directory exists
            os.makedirs(AUDIO_FOLDER, exist_ok=True)
            
            with open(filepath, 'wb') as f:
                f.write(audio_data)
            
            # Verify file was written
            if os.path.exists(filepath):
                file_size = os.path.getsize(filepath)
                logger.info(f"✅ Audio generated successfully with Sarvam Bulbul v2: {filename} ({file_size} bytes)")
            else:
                logger.error(f"❌ Audio file was NOT saved: {filepath}")
                raise Exception("Audio file not saved")
            
            return filename
            
    except httpx.HTTPStatusError as e:
        logger.error(f"Sarvam TTS HTTP error: {e.response.status_code} - {e.response.text}")
        return await generate_audio_gtts_fallback(text, lang)
    except Exception as e:
        logger.error(f"Sarvam TTS failed: {e}", exc_info=True)
        return await generate_audio_gtts_fallback(text, lang)

async def generate_audio_gtts_fallback(text: str, lang: str = 'en') -> str:
    """Fallback to gTTS if Sarvam fails"""
    filename = f"audio_{uuid.uuid4().hex}.mp3"
    filepath = os.path.join(AUDIO_FOLDER, filename)

    def _generate_audio():
        for attempt in range(3):
            try:
                tts = gTTS(text=text, lang=lang)
                tts.save(filepath)
                logger.info(f"Audio generated successfully with gTTS: {filename}")
                return filename
            except Exception as e:
                logger.warning(f"[gTTS] Attempt {attempt + 1} failed: {e}")
                time.sleep(2)
        logger.error("gTTS failed after 3 retries.")
        raise Exception("gTTS failed after 3 retries")

    # Run gTTS in thread pool to avoid blocking
    loop = asyncio.get_event_loop()
    filename = await loop.run_in_executor(executor, _generate_audio)
    return filename

# Legacy function for backward compatibility
def generate_audio(text: str, lang: str = 'en') -> str:
    """Synchronous audio generation (legacy)"""
    filename = f"audio_{uuid.uuid4().hex}.mp3"
    filepath = os.path.join(AUDIO_FOLDER, filename)
    for attempt in range(3):
        try:
            tts = gTTS(text=text, lang=lang)
            tts.save(filepath)
            logger.info(f"Audio generated successfully: {filename}")
            return filename
        except Exception as e:
            logger.warning(f"[gTTS] Attempt {attempt + 1} failed: {e}")
            time.sleep(2)
    logger.error("gTTS failed after 3 retries.")
    raise Exception("gTTS failed after 3 retries")

async def query_openrouter_general(prompt: str, system_message: str = "You are a professional AI interviewer. Generate clear, relevant interview questions.") -> str:
    """Query OpenRouter for general AI tasks (questions, summaries, analysis)"""
    if not OPENROUTER_API_KEY:
        raise Exception("OpenRouter API key is not configured. Please set OPENROUTER_API_KEY in .env file.")

    logger.info(f"Querying OpenRouter with prompt: {prompt[:200]}...")
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8500",
        "X-Title": "AI Interview System"
    }
    data = {
        "model": "meta-llama/llama-3.1-70b-instruct",
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 1500
    }

    timeout = httpx.Timeout(45.0, connect=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=data)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            logger.info("OpenRouter query successful.")
            return content
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error querying OpenRouter: {e.response.status_code} - {e.response.text}")
        raise
    except httpx.RequestError as e:
        logger.error(f"Request error querying OpenRouter: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in query_openrouter_general: {e}", exc_info=True)
        raise

async def query_openrouter(prompt: str) -> str:
    """Query OpenRouter for answer evaluation (wrapper for backward compatibility)"""
    return await query_openrouter_general(
        prompt,
        system_message="You are a professional AI interviewer and evaluator. Always follow the exact format requested. Provide detailed, fair evaluations."
    )

async def generate_introductory_question(resume_summary: str) -> str:
    """Always start with this fixed question after consent."""
    return "Tell me about yourself."

# Global state for tracking
current_topic = None
topic_question_count = 0
covered_topics = set()

async def generate_dynamic_question(resume_summary: str, last_response: str, dialogue: List[Dict]) -> str:
    global current_topic, topic_question_count, covered_topics

    # Get recent conversation context (last 4 exchanges)
    recent_context = "\n".join(
        f"{msg['role']}: {msg['content']}" for msg in dialogue[-4:]
    )

    prompt = f"""Candidate Summary (from resume):
--------
{resume_summary}

Recent conversation:
{recent_context}

Last answer: {last_response}

Topics already covered: {', '.join(covered_topics) if covered_topics else 'None'}

Generate ONE interview question following these rules:

1. Focus on: projects, internships, certifications, technical skills, tools used
2. If last answer was detailed and complete → move to NEW topic from resume
3. If last answer was brief/incomplete → ask ONE follow-up, then move on
4. Don't repeat covered topics: {covered_topics}
5. Prioritize: projects > internships > certifications > skills
6. Ask specific technical questions about implementation, challenges, results

Return ONLY the question. No explanations."""

    try:
        question = (await query_gemini_with_retry(prompt)).strip()

        # Simple topic management
        followup_keywords = ["how", "what", "can you elaborate", "tell me more", "explain"]
        is_followup = any(keyword in question.lower()[:20] for keyword in followup_keywords)

        if is_followup and current_topic:
            topic_question_count += 1
            if topic_question_count >= 2:  # Max 2 questions per topic
                covered_topics.add(current_topic)
                current_topic = None
                topic_question_count = 0
        else:
            # New topic detected
            if current_topic:
                covered_topics.add(current_topic)
            current_topic = extract_topic_from_question(question)
            topic_question_count = 1

        return question

    except Exception as e:
        logger.error(f"Error generating question: {e}")
        return get_fallback_question()

def extract_topic_from_question(question: str) -> str:
    """Extract main topic from question for tracking"""
    question_lower = question.lower()

    # Topic keywords mapping
    topics = {
        'project': ['project', 'application', 'system', 'built', 'developed'],
        'internship': ['internship', 'intern', 'company', 'workplace'],
        'certification': ['certification', 'certified', 'course', 'training'],
        'skills': ['technology', 'language', 'framework', 'tool', 'skill']
    }

    for topic, keywords in topics.items():
        if any(keyword in question_lower for keyword in keywords):
            return topic
    return 'general'

def get_fallback_question() -> str:
    """Simple fallback questions covering main resume areas"""
    fallbacks = [
        "What's the most challenging project you've worked on?",
        "Tell me about your internship experience and key learnings.",
        "Which certification or course has been most valuable to you?",
        "What technologies are you most comfortable working with?"
    ]

    return fallbacks[len(covered_topics) % len(fallbacks)]

# Reset function for new interviews
def reset_interview_state():
    global current_topic, topic_question_count, covered_topics
    current_topic = None
    topic_question_count = 0
    covered_topics = set()

async def evaluate_user_answer(question: str, user_answer: str, resume_summary: str) -> Dict:
    """Evaluate user's answer in real-time and provide detailed feedback."""
    
    # Check if this is a coding question (contains [CODE] markers)
    is_coding_question = '[CODE]' in user_answer and '[/CODE]' in user_answer
    
    if is_coding_question:
        # Extract code and explanation
        code_match = re.search(r'\[CODE\](.*?)\[/CODE\]', user_answer, re.DOTALL)
        code = code_match.group(1).strip() if code_match else ""
        explanation = re.sub(r'\[CODE\].*?\[/CODE\]', '', user_answer, flags=re.DOTALL).strip()
        
        prompt = f"""
You are a STRICT technical interview evaluator specializing in coding assessments. Focus PRIMARILY on the CODE QUALITY, not the explanation.

CODING QUESTION:
{question}

CANDIDATE'S CODE:
{code}

CANDIDATE'S EXPLANATION (SECONDARY - only for context):
{explanation if explanation else "No explanation provided"}

CANDIDATE'S RESUME CONTEXT:
{resume_summary}

Provide evaluation in this EXACT format:

SCORE: [0-10]
TECHNICAL_ACCURACY: [Rate code correctness and logic 0-10]
COMMUNICATION_CLARITY: [Rate code readability and structure 0-10]
RELEVANCE: [Rate how well solution addresses the problem 0-10]
DEPTH: [Rate code quality, edge cases, optimization 0-10]
CONFIDENCE: [Rate code completeness and robustness 0-10]
PROBLEM_SOLVING: [Rate algorithmic approach and reasoning 0-10]
STRENGTHS: [List 2-3 key strengths in the CODE ONLY]
WEAKNESSES: [List 2-3 areas for improvement in the CODE]
FEEDBACK: [Constructive feedback on CODE quality, logic, and implementation - IGNORE explanation quality]
FOLLOW_UP_SUGGESTION: [Suggest what interviewer should ask next]

STRICT Evaluation Criteria for Coding Questions:
- Technical Accuracy (50%): Does the code actually work? Is the logic correct? Test mentally with edge cases.
- Problem-Solving (25%): Is the algorithmic approach optimal? Are edge cases handled? Is complexity reasonable?
- Code Quality (15%): Is the code clean, readable, maintainable? Proper naming? Good structure?
- Depth (10%): Are optimizations present? Error handling? Input validation?

SCORING GUIDELINES (BE STRICT):
- 9-10: Perfect or near-perfect solution with optimal approach, edge cases, and clean code
- 7-8: Working solution with good approach but minor issues or missing optimizations
- 5-6: Working solution with significant issues, poor approach, or missing edge cases
- 3-4: Partially working code with major logical errors or incomplete implementation
- 0-2: Non-working code, completely wrong approach, or missing critical logic

IMPORTANT: 
- IGNORE the candidate's explanation quality - focus ONLY on the CODE itself
- Be strict with scoring - most candidates should score 4-7, not 7-10
- Deduct points for: missing edge cases, poor variable names, no error handling, inefficient algorithms
- Only give 8+ for truly excellent, production-ready code
"""
    else:
        # Regular text question evaluation
        prompt = f"""
You are a fair and balanced interview evaluator. Analyze the candidate's response for factual correctness and practical understanding. Give credit for correct concepts even if phrased informally, but be thorough in checking accuracy. Partial answers should receive partial credit. Deduct points for factual errors, missing key concepts, or vague responses that don't demonstrate understanding.

QUESTION ASKED:
{question}

CANDIDATE'S ANSWER:
{user_answer}

CANDIDATE'S RESUME CONTEXT:
{resume_summary}

Provide evaluation in this EXACT format:

SCORE: [0-10]
TECHNICAL_ACCURACY: [Rate technical correctness 0-10]
COMMUNICATION_CLARITY: [Rate clarity and articulation 0-10]
RELEVANCE: [Rate how well answer addresses question 0-10]
DEPTH: [Rate depth of explanation 0-10]
CONFIDENCE: [Rate confidence level 0-10]
PROBLEM_SOLVING: [Rate problem-solving approach 0-10]
STRENGTHS: [List 2-3 key strengths in the answer]
WEAKNESSES: [List 2-3 areas for improvement]
FEEDBACK: [Constructive feedback in 2-3 sentences]
FOLLOW_UP_SUGGESTION: [Suggest what interviewer should ask next based on this answer]

Evaluation Criteria:
- Technical Accuracy (40%): Is the answer factually correct? Are key concepts covered?
- Relevance (25%): How well does the answer address the specific question asked?
- Problem-Solving (15%): Does the answer show reasoning, understanding of tradeoffs?
- Depth (10%): Are important details, examples, or rationale provided?
- Communication Clarity (5%): Is the answer clear and well-structured?
- Confidence (5%): Does the answer demonstrate solid understanding?

SCORING GUIDELINES:
- 9-10: Comprehensive, accurate answer covering all key points with examples
- 7-8: Good answer with correct concepts but missing some details or depth
- 5-6: Partially correct answer with some gaps or minor inaccuracies
- 3-4: Incomplete answer with significant gaps or conceptual errors
- 0-2: Incorrect answer or completely off-topic

Provide specific, actionable feedback that helps the candidate improve.
"""

    try:
        # Use OpenRouter for evaluation instead of Azure OpenAI
        evaluation = await query_openrouter(prompt)
        logger.info(f"Raw evaluation response: {evaluation[:500]}...")

        # Extract evaluation components using regex
        score_match = re.search(r'SCORE:\s*(\d+(?:\.\d+)?)', evaluation, re.IGNORECASE)
        tech_match = re.search(r'TECHNICAL_ACCURACY:\s*(\d+(?:\.\d+)?)', evaluation, re.IGNORECASE)
        comm_match = re.search(r'COMMUNICATION_CLARITY:\s*(\d+(?:\.\d+)?)', evaluation, re.IGNORECASE)
        rel_match = re.search(r'RELEVANCE:\s*(\d+(?:\.\d+)?)', evaluation, re.IGNORECASE)
        depth_match = re.search(r'DEPTH:\s*(\d+(?:\.\d+)?)', evaluation, re.IGNORECASE)
        conf_match = re.search(r'CONFIDENCE:\s*(\d+(?:\.\d+)?)', evaluation, re.IGNORECASE)
        prob_match = re.search(r'PROBLEM_SOLVING:\s*(\d+(?:\.\d+)?)', evaluation, re.IGNORECASE)

        # Extract scores with validation - use 5.0 as default for balanced scoring
        overall_score = float(score_match.group(1)) if score_match else 5.0
        technical_score = float(tech_match.group(1)) if tech_match else 5.0
        communication_score = float(comm_match.group(1)) if comm_match else 5.0
        relevance_score = float(rel_match.group(1)) if rel_match else 5.0
        depth_score = float(depth_match.group(1)) if depth_match else 5.0
        confidence_score = float(conf_match.group(1)) if conf_match else 5.0
        problem_solving_score = float(prob_match.group(1)) if prob_match else 5.0

        # Log if any scores are missing
        if not score_match:
            logger.warning("SCORE not found in evaluation response")
        if not tech_match:
            logger.warning("TECHNICAL_ACCURACY not found in evaluation response")

        # Extract text sections
        strengths = extract_section(evaluation, 'STRENGTHS', 'WEAKNESSES')
        weaknesses = extract_section(evaluation, 'WEAKNESSES', 'FEEDBACK')
        feedback = extract_section(evaluation, 'FEEDBACK', 'FOLLOW_UP_SUGGESTION')
        follow_up_suggestion = extract_section(evaluation, 'FOLLOW_UP_SUGGESTION', None)

        result = {
            "overall_score": min(10.0, max(0.0, overall_score)),
            "technical_accuracy": min(10.0, max(0.0, technical_score)),
            "communication_clarity": min(10.0, max(0.0, communication_score)),
            "relevance": min(10.0, max(0.0, relevance_score)),
            "depth": min(10.0, max(0.0, depth_score)),
            "confidence": min(10.0, max(0.0, confidence_score)),
            "problem_solving": min(10.0, max(0.0, problem_solving_score)),
            "strengths": strengths,
            "weaknesses": weaknesses,
            "feedback": feedback,
            "follow_up_suggestion": follow_up_suggestion,
            "raw_evaluation": evaluation
        }
        
        logger.info(f"Evaluation successful - Overall Score: {result['overall_score']}/10")
        return result

    except Exception as e:
        logger.error(f"Error evaluating answer: {e}", exc_info=True)
        return {
            "overall_score": 5.0,
            "technical_accuracy": 5.0,
            "communication_clarity": 5.0,
            "relevance": 5.0,
            "depth": 5.0,
            "confidence": 5.0,
            "problem_solving": 5.0,
            "strengths": "Response provided",
            "weaknesses": "Evaluation temporarily unavailable",
            "feedback": "Please continue with the interview",
            "follow_up_suggestion": "Ask a follow-up question based on the response",
            "raw_evaluation": "Evaluation failed"
        }

def extract_section(text: str, start_marker: str, end_marker: Optional[str] = None) -> str:
    """Extract text section between markers."""
    start_pattern = rf'{re.escape(start_marker)}:\s*'
    start_match = re.search(start_pattern, text, re.IGNORECASE)
    
    if not start_match:
        return "Not available"
    
    start_pos = start_match.end()
    
    if end_marker:
        end_pattern = rf'{re.escape(end_marker)}:'
        end_match = re.search(end_pattern, text[start_pos:], re.IGNORECASE)
        if end_match:
            return text[start_pos:start_pos + end_match.start()].strip()
    
    return text[start_pos:].strip()

def calculate_kpis(evaluations: List[Dict]) -> InterviewKPIs:
    """Calculate KPIs from evaluation data."""
    if not evaluations:
        return InterviewKPIs()

    # Calculate average scores
    communication_scores = [eval_data["evaluation"]["communication_clarity"] for eval_data in evaluations]
    technical_scores = [eval_data["evaluation"]["technical_accuracy"] for eval_data in evaluations]
    problem_solving_scores = [eval_data["evaluation"].get("problem_solving", 5.0) for eval_data in evaluations]
    confidence_scores = [eval_data["evaluation"].get("confidence", 5.0) for eval_data in evaluations]

    # Calculate averages
    communication_avg = sum(communication_scores) / len(communication_scores)
    technical_avg = sum(technical_scores) / len(technical_scores)
    problem_solving_avg = sum(problem_solving_scores) / len(problem_solving_scores)
    confidence_avg = sum(confidence_scores) / len(confidence_scores)

    # Calculate completion rate
    expected_questions = interview_state.max_questions
    actual_questions = len(evaluations)
    completion_rate = (actual_questions / expected_questions) * 100

    # Determine engagement level
    overall_avg = (communication_avg + technical_avg + problem_solving_avg + confidence_avg) / 4
    if overall_avg >= 8:
        engagement_level = "High"
    elif overall_avg >= 6:
        engagement_level = "Medium"
    else:
        engagement_level = "Low"

    # Count strengths and improvement areas
    strengths_count = sum(1 for eval_data in evaluations if eval_data["evaluation"]["strengths"] != "Not available")
    improvement_areas_count = sum(1 for eval_data in evaluations if eval_data["evaluation"]["weaknesses"] != "Not available")

    return InterviewKPIs(
        communication_score=communication_avg,
        technical_score=technical_avg,
        problem_solving_score=problem_solving_avg,
        confidence_score=confidence_avg,
        clarity_score=communication_avg,  # Using communication as clarity proxy
        response_time_avg=0.0,  # Would need timing data
        questions_answered=actual_questions,
        completion_rate=completion_rate,
        engagement_level=engagement_level,
        strengths_count=strengths_count,
        improvement_areas_count=improvement_areas_count
    )

async def generate_interview_report(dialogue: List[Dict], resume_summary: str, evaluations: List[Dict]) -> InterviewReport:
    """Generate comprehensive report including AI evaluations and KPIs."""
    # Filter valid dialogue entries
    valid_dialogue = [
        msg for msg in dialogue
        if msg.get("content") and msg["content"] != "[No response]" and len(msg["content"].strip()) > 3
    ]

    # Calculate KPIs
    kpis = calculate_kpis(evaluations)

    # Calculate evaluation statistics
    if evaluations:
        overall_scores = [eval_data["evaluation"]["overall_score"] for eval_data in evaluations]
        technical_scores = [eval_data["evaluation"]["technical_accuracy"] for eval_data in evaluations]
        communication_scores = [eval_data["evaluation"]["communication_clarity"] for eval_data in evaluations]

        avg_overall = sum(overall_scores) / len(overall_scores)
        avg_technical = sum(technical_scores) / len(technical_scores)
        avg_communication = sum(communication_scores) / len(communication_scores)

        # Create detailed evaluation summary
        detailed_evaluations = "\n\n".join([
            f"Q{i+1}: {eval_data['question']}\n"
            f"Answer: {eval_data['answer'][:200]}{'...' if len(eval_data['answer']) > 200 else ''}\n"
            f"Score: {eval_data['evaluation']['overall_score']}/10\n"
            f"Communication: {eval_data['evaluation']['communication_clarity']}/10\n"
            f"Technical: {eval_data['evaluation']['technical_accuracy']}/10\n"
            f"Confidence: {eval_data['evaluation'].get('confidence', 5.0)}/10\n"
            f"Feedback: {eval_data['evaluation']['feedback']}\n"
            f"Strengths: {eval_data['evaluation']['strengths']}\n"
            f"Areas for Improvement: {eval_data['evaluation']['weaknesses']}"
            for i, eval_data in enumerate(evaluations)
        ])

        # Extract strengths and areas for improvement
        strengths = [eval_data["evaluation"]["strengths"] for eval_data in evaluations if eval_data["evaluation"]["strengths"] != "Not available"]
        areas_for_improvement = [eval_data["evaluation"]["weaknesses"] for eval_data in evaluations if eval_data["evaluation"]["weaknesses"] != "Not available"]

    else:
        avg_overall = 0.0
        avg_technical = 0.0
        avg_communication = 0.0
        detailed_evaluations = "No evaluations available"
        strengths = []
        areas_for_improvement = []

    # Generate overall analysis
    dialogue_text = "\n".join([
        f"{msg['role'].capitalize()}: {msg['content']}"
        for msg in valid_dialogue
    ])

    prompt = f"""
Generate a comprehensive interview analysis based on the following data:

RESUME SUMMARY: {resume_summary}

INTERVIEW TRANSCRIPT: {dialogue_text}

AI EVALUATION SUMMARY: {detailed_evaluations}

Provide detailed analysis covering overall performance, technical skills, communication abilities, and recommendations.
Focus on constructive feedback and specific areas for improvement.
"""

    try:
        analysis = await query_gemini_with_retry(prompt)

        report = InterviewReport(
            candidate_name=interview_state.user_details.name or "Candidate",
            candidate_phone=interview_state.user_details.phone,
            candidate_email=interview_state.user_details.email,
            interview_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            overall_score=avg_overall * 10,  # Convert to 0-100 scale
            technical_score=avg_technical * 10,
            communication_score=avg_communication * 10,
            detailed_feedback=f"Real-time AI Evaluations:\n\n{detailed_evaluations}\n\n"
                            f"Overall Analysis:\n{analysis}",
            strengths=strengths[:5],  # Limit to top 5
            areas_for_improvement=areas_for_improvement[:5],  # Limit to top 5
            interview_transcript=valid_dialogue,  # Use filtered dialogue
            kpis=kpis,
            proctoring_violations=interview_state.proctoring_violations
        )

        return report

    except Exception as e:
        logger.error(f"Error generating report: {e}")
        return InterviewReport(
            candidate_name=interview_state.user_details.name or "Candidate",
            candidate_phone=interview_state.user_details.phone,
            candidate_email=interview_state.user_details.email,
            interview_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            overall_score=avg_overall * 10,
            technical_score=avg_technical * 10,
            communication_score=avg_communication * 10,
            detailed_feedback=f"Real-time AI Evaluations:\n\n{detailed_evaluations}",
            strengths=strengths[:5],
            areas_for_improvement=areas_for_improvement[:5],
            interview_transcript=valid_dialogue,
            kpis=kpis,
            proctoring_violations=interview_state.proctoring_violations
        )

async def generate_report_background(dialogue: List[Dict], resume_summary: str, evaluations: List[Dict], session_id: str):
    """Generate report in background without blocking WebSocket"""
    try:
        report = await generate_interview_report(dialogue, resume_summary, evaluations)
        generated_reports[session_id] = report
        logger.info(f"Report generated for session {session_id}")
    except Exception as e:
        logger.error(f"Background report generation failed: {e}")

# --- Email Functions ---
async def send_interview_report_email(candidate_email: str, candidate_name: str, report: InterviewReport) -> dict:
    """Send interview report via email with PDF attachment.
    
    Returns dict with status and message for better feedback.
    """
    if not EMAIL_USERNAME or not EMAIL_PASSWORD:
        logger.warning("Email credentials not configured. Please set EMAIL_USERNAME and EMAIL_PASSWORD in .env file")
        return {
            "success": False,
            "message": "Email not configured. Please contact administrator to set up email credentials.",
            "error_type": "configuration"
        }

    try:
        # Generate PDF content
        html_content = templates.get_template("report_pdf.html").render(
            report=report
        )

        # Create PDF using xhtml2pdf
        pdf_buffer = BytesIO()
        pisa_status = pisa.CreatePDF(src=html_content, dest=pdf_buffer)
        pdf_buffer.seek(0)
        pdf_content = pdf_buffer.read()
        if getattr(pisa_status, 'err', 0):
            logger.error(f"PDF generation error for {candidate_email}: %s", getattr(pisa_status, 'err', None))

        # Create email message
        message = MIMEMultipart()
        message["From"] = f"{EMAIL_FROM_NAME} <{EMAIL_USERNAME}>"
        message["To"] = candidate_email
        message["Subject"] = f"Your Interview Report - {candidate_name}"

        # Email body
        body = f"""Dear {candidate_name},

Thank you for participating in our AI-powered interview process. We are pleased to provide you with your comprehensive interview evaluation report.

📊 Interview Summary:

• Overall Score: {report.overall_score:.1f}/100
• Communication Score: {report.communication_score:.1f}/100
• Technical Score: {report.technical_score:.1f}/100
• Interview Date: {report.interview_date}

Please find your detailed interview report attached as a PDF. The report includes:

✅ Performance analysis across multiple dimensions
✅ Strengths and areas for improvement
✅ Detailed feedback from our AI evaluation system
✅ Complete interview transcript
✅ Proctoring integrity report

We encourage you to review the feedback carefully as it provides valuable insights to help you succeed in future interviews.

If you have any questions about your report, please don't hesitate to contact us.

Best regards,
AI Interview System Team

---
This is an automated message. Please do not reply to this email."""

        message.attach(MIMEText(body, "plain"))

        # Attach PDF
        pdf_attachment = MIMEBase("application", "octet-stream")
        pdf_attachment.set_payload(pdf_content)
        encoders.encode_base64(pdf_attachment)
        pdf_attachment.add_header(
            "Content-Disposition",
            f"attachment; filename=Interview_Report_{candidate_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
        )
        message.attach(pdf_attachment)

        # Send email using aiosmtplib for async support
        await aiosmtplib.send(
            message,
            hostname=EMAIL_SMTP_SERVER,
            port=EMAIL_SMTP_PORT,
            start_tls=EMAIL_USE_TLS,
            username=EMAIL_USERNAME,
            password=EMAIL_PASSWORD,
        )

        logger.info(f"✅ Interview report successfully sent to {candidate_email}")
        return {
            "success": True,
            "message": f"Interview report successfully sent to {candidate_email}",
            "email": candidate_email
        }

    except Exception as e:
        error_msg = f"Failed to send email to {candidate_email}: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "message": error_msg,
            "error_type": "sending",
            "email": candidate_email
        }

async def send_email_notification(to_email: str, subject: str, body: str) -> dict:
    """Send a simple email notification without attachments.
    
    Returns dict with status and message for better feedback.
    """
    if not EMAIL_USERNAME or not EMAIL_PASSWORD:
        logger.warning("Email credentials not configured. Please set EMAIL_USERNAME and EMAIL_PASSWORD in .env file")
        return {
            "success": False,
            "message": "Email not configured. Please contact administrator to set up email credentials.",
            "error_type": "configuration"
        }

    try:
        message = MIMEMultipart()
        message["From"] = f"{EMAIL_FROM_NAME} <{EMAIL_USERNAME}>"
        message["To"] = to_email
        message["Subject"] = subject

        message.attach(MIMEText(body, "plain"))

        await aiosmtplib.send(
            message,
            hostname=EMAIL_SMTP_SERVER,
            port=EMAIL_SMTP_PORT,
            start_tls=EMAIL_USE_TLS,
            username=EMAIL_USERNAME,
            password=EMAIL_PASSWORD,
        )

        logger.info(f"Email notification sent to {to_email}")
        return {
            "success": True,
            "message": f"Email notification sent to {to_email}",
            "email": to_email
        }

    except Exception as e:
        error_msg = f"Failed to send email notification to {to_email}: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "message": error_msg,
            "error_type": "sending",
            "email": to_email
        }

# --- Routes ---
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    logger.info("Serving index page.")
    # No need to reset global state anymore
    return templates.TemplateResponse("index.html", {"request": request, "report": None})

@app.post("/start_interview")
async def start_interview(
    request: Request,
    resume: List[UploadFile] = File(None),
    name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...),
    questions: Optional[str] = Form(None),
    max_questions: Optional[int] = Form(None),
    job_id: Optional[str] = Form(None)
):
    logger.info("Starting new interview process.")
    global interview_state

    # Create NEW session-specific state
    session_id = str(uuid.uuid4())
    new_state = InterviewState()
    new_state.user_details = UserDetails(name=name, phone=phone, email=email)
    new_state.resume_text = ""
    new_state.resume_summary = ""
    new_state.current_dialogue = []
    new_state.is_interview_active = False
    new_state.current_question_count = 0
    new_state.last_question = ""
    new_state.consent_received = False
    new_state.answer_evaluations = []
    new_state.total_score = 0.0
    new_state.average_score = 0.0
    new_state.proctoring_session_id = session_id
    new_state.proctoring_violations = []
    new_state.reference_face_captured = False
    new_state.preloaded_questions = []
    new_state.preloaded_question_types = []
    new_state.current_question_index = 0

    # Store in dictionary for parallel access using proctoring_session_id as key
    # This ensures both interview and proctoring WebSockets use the same session_id
    interview_states[new_state.proctoring_session_id] = new_state
    
    # Also update global for backward compatibility
    interview_state = new_state

    # Reset email tracking for new session
    if session_id in email_sent_for_session:
        email_sent_for_session.remove(session_id)

    parsed_questions: List[str] = []
    parsed_question_types: List[str] = []
    
    if questions is not None:
        try:
            candidate = json.loads(questions)
            if isinstance(candidate, list):
                parsed_questions = [str(q).strip() for q in candidate if str(q).strip()]
                parsed_question_types = ["text"] * len(parsed_questions)  # Default to text
        except Exception:
            # Fallback to newline-separated parsing
            parsed_questions = [line.strip() for line in questions.splitlines() if line.strip()]
            parsed_question_types = ["text"] * len(parsed_questions)  # Default to text
    elif job_id:
        job = jobs.get(job_id)
        if job and job.questions:
            # Use question_items if available, otherwise fall back to questions
            if job.question_items:
                parsed_questions = [item.text for item in job.question_items]
                parsed_question_types = [item.type for item in job.question_items]
            else:
                parsed_questions = [q.strip() for q in job.questions if q.strip()]
                parsed_question_types = ["text"] * len(parsed_questions)
            
            # Load timer settings from job
            new_state.text_question_timer = job.text_question_timer
            new_state.coding_question_timer = job.coding_question_timer
        else:
            logger.warning("Job not found or has no questions.")
            raise HTTPException(status_code=400, detail="Job not found or has no questions.")
    else:
        logger.warning("No questions provided.")
        raise HTTPException(status_code=400, detail="No questions provided. Please pass questions or job_id.")

    if not parsed_questions:
        logger.warning("Parsed questions list is empty.")
        raise HTTPException(status_code=400, detail="Questions list is empty after parsing.")

    new_state.preloaded_questions = parsed_questions
    new_state.preloaded_question_types = parsed_question_types
    # Set max_questions to length of provided questions unless overridden
    if max_questions is not None:
        try:
            mq = int(max_questions)
            new_state.max_questions = max(1, min(mq, len(parsed_questions)))
        except Exception:
            new_state.max_questions = len(parsed_questions)
    else:
        new_state.max_questions = len(parsed_questions)

    # Ensure resume summary is empty since we're not using resume context
    new_state.resume_text = ""
    new_state.resume_summary = ""

    # Store user session data
    session_data = {
        "user_details": new_state.user_details.dict(),
        "proctoring_session_id": new_state.proctoring_session_id,
        "created_at": datetime.now().isoformat(),
        "status": "in_progress",
        "job_id": job_id,
        "job_title": jobs.get(job_id).title if job_id and jobs.get(job_id) else None,
        "question_index": new_state.current_question_index,
        "dialogue": new_state.current_dialogue,
        "answer_evaluations": new_state.answer_evaluations,
        "proctoring_violations": new_state.proctoring_violations,
        "consent_received": new_state.consent_received,
        "preloaded_questions": new_state.preloaded_questions,
        "preloaded_question_types": new_state.preloaded_question_types,
        "text_question_timer": new_state.text_question_timer,
        "coding_question_timer": new_state.coding_question_timer,
    }

    user_sessions[new_state.proctoring_session_id] = session_data
    
    # Save session to MongoDB for multi-worker support
    await save_session_to_db(new_state.proctoring_session_id, session_data)

    # Initialize proctoring session
    await proctoring_service.create_session(new_state.proctoring_session_id)

    logger.info(f"Interview initialized for {name}. Awaiting face verification.")
    return JSONResponse({
        "status": "ready_for_face_capture",
        "message": "Please proceed to face verification.",
        "proctoring_session_id": new_state.proctoring_session_id,
        "user_name": name
    })

@app.post("/capture_reference_face")
async def capture_reference_face(request: Request):
    """Store the captured reference face for identity verification."""
    try:
        data = await request.json()
        image_data = data.get('image_data')

        if not image_data:
            raise HTTPException(status_code=400, detail="No image data provided")

        # Set reference face in proctoring service
        result = await proctoring_service.set_reference_face(
            interview_state.proctoring_session_id,
            image_data
        )

        if result.get('status') == 'success':
            interview_state.reference_face_captured = True
            logger.info("Reference face captured successfully")
            return JSONResponse({
                "status": "success",
                "message": "Reference face captured successfully"
            })
        else:
            # Still allow interview to proceed even if face capture fails
            interview_state.reference_face_captured = True
            logger.warning("Face capture failed but allowing interview to proceed")
            return JSONResponse({
                "status": "success",
                "message": "Session activated successfully"
            })

    except Exception as e:
        logger.error(f"Error capturing reference face: {e}")
        # Fallback: Still allow interview to proceed
        interview_state.reference_face_captured = True
        return JSONResponse({
            "status": "success",
            "message": "Session activated successfully"
        })

@app.get("/user_session/{session_id}")
async def get_user_session(session_id: str):
    """Get user session data."""
    if session_id in user_sessions:
        return JSONResponse(user_sessions[session_id])
    else:
        raise HTTPException(status_code=404, detail="Session not found")

@app.post("/start_interview_session")
async def start_interview_session(request: Request):
    """Start the actual interview session after face verification."""
    try:
        # Get session_id from request body
        body = await request.json()
        session_id = body.get("session_id") or body.get("proctoring_session_id")
        
        if not session_id:
            # Fallback to global interview_state for backward compatibility
            session_id = interview_state.proctoring_session_id
        
        # Get the specific session state
        local_state = interview_states.get(session_id)
        if not local_state:
            # Try to load from MongoDB
            session_doc = await get_session_from_db(session_id)
            if session_doc:
                local_state = session_to_interview_state(session_doc)
                interview_states[session_id] = local_state
            else:
                raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        
        # Allow interview to proceed regardless of face capture status
        local_state.is_interview_active = True
        
        # Log complete interview details after face verification
        logger.info("=" * 80)
        logger.info("🎯 INTERVIEW SESSION STARTED - POST FACE VERIFICATION")
        logger.info("=" * 80)
        logger.info(f"📋 Candidate Name: {local_state.user_details.name}")
        logger.info(f"📧 Candidate Email: {local_state.user_details.email}")
        logger.info(f"📱 Candidate Phone: {local_state.user_details.phone}")
        logger.info(f"💼 Job ID: {getattr(local_state, 'job_id', 'N/A')}")
        logger.info(f"🔑 Proctoring Session ID: {local_state.proctoring_session_id}")
        logger.info(f"❓ Total Questions: {len(local_state.preloaded_questions)}")
        logger.info(f"⏱️  Text Question Timer: {local_state.text_question_timer}s")
        logger.info(f"⏱️  Coding Question Timer: {local_state.coding_question_timer}s")
        logger.info(f"🎤 Interview Active: {local_state.is_interview_active}")
        logger.info(f"📅 Timestamp: {datetime.now().isoformat()}")
        logger.info("=" * 80)

        # Create LiveKit room for this interview session
        try:
            room_name = f"interview-{local_state.proctoring_session_id}"
            room_info = await livekit_manager.create_room(
                room_name=room_name,
                empty_timeout=600,  # 10 minutes
                max_participants=2  # Interviewer bot + candidate
            )
            logger.info(f"✅ LiveKit room created: {room_name}")
            
            # Generate token for candidate
            candidate_token = livekit_manager.generate_token(
                room_name=room_name,
                participant_identity=f"candidate-{local_state.proctoring_session_id}",
                participant_name=local_state.user_details.name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
                ttl=3600  # 1 hour
            )
            
            # Store room info in session state
            local_state.livekit_room_name = room_name
            
            return JSONResponse({
                "status": "interview_ready",
                "message": "Interview session ready. Please connect to LiveKit room to begin.",
                "proctoring_session_id": local_state.proctoring_session_id,
                "livekit_room_name": room_name,
                "livekit_token": candidate_token,
                "livekit_url": livekit_manager.ws_url  # Use WebSocket URL for client
            })
        except Exception as lk_error:
            logger.error(f"Failed to create LiveKit room: {lk_error}")
            # Fallback: Return session info without LiveKit (for backward compatibility during migration)
            return JSONResponse({
                "status": "interview_ready",
                "message": "Interview session ready. Please connect to WebSocket to begin.",
                "proctoring_session_id": local_state.proctoring_session_id
            })

    except Exception as e:
        logger.error(f"Error starting interview session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# LiveKit Room Management Endpoints
@app.post("/api/livekit/create_room")
async def create_livekit_room(request: Request):
    """
    Create a LiveKit room for an interview session
    
    Request body:
    {
        "session_id": "unique_session_id",
        "max_participants": 2
    }
    """
    try:
        data = await request.json()
        session_id = data.get("session_id")
        max_participants = data.get("max_participants", 2)
        
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id is required")
        
        room_name = f"interview-{session_id}"
        room_info = await livekit_manager.create_room(
            room_name=room_name,
            empty_timeout=600,
            max_participants=max_participants
        )
        
        return JSONResponse({
            "status": "success",
            "room_name": room_name,
            "room_info": room_info
        })
    except Exception as e:
        logger.error(f"Error creating LiveKit room: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/livekit/get_token")
async def get_livekit_token(request: Request):
    """
    Generate a LiveKit access token for a participant
    
    Request body:
    {
        "room_name": "interview-session_id",
        "participant_identity": "candidate-session_id",
        "participant_name": "John Doe",
        "can_publish": true,
        "can_subscribe": true,
        "can_publish_data": true
    }
    """
    try:
        data = await request.json()
        room_name = data.get("room_name")
        participant_identity = data.get("participant_identity")
        participant_name = data.get("participant_name", "")
        can_publish = data.get("can_publish", True)
        can_subscribe = data.get("can_subscribe", True)
        can_publish_data = data.get("can_publish_data", True)
        
        if not room_name or not participant_identity:
            raise HTTPException(status_code=400, detail="room_name and participant_identity are required")
        
        token = livekit_manager.generate_token(
            room_name=room_name,
            participant_identity=participant_identity,
            participant_name=participant_name,
            can_publish=can_publish,
            can_subscribe=can_subscribe,
            can_publish_data=can_publish_data,
            ttl=3600
        )
        
        return JSONResponse({
            "status": "success",
            "token": token,
            "livekit_url": livekit_manager.ws_url
        })
    except Exception as e:
        logger.error(f"Error generating LiveKit token: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/livekit/delete_room/{room_name}")
async def delete_livekit_room(room_name: str):
    """Delete a LiveKit room"""
    try:
        success = await livekit_manager.delete_room(room_name)
        if success:
            return JSONResponse({"status": "success", "message": f"Room {room_name} deleted"})
        else:
            raise HTTPException(status_code=404, detail=f"Room {room_name} not found")
    except Exception as e:
        logger.error(f"Error deleting LiveKit room: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/livekit/rooms")
async def list_livekit_rooms():
    """List all active LiveKit rooms"""
    try:
        rooms = await livekit_manager.list_rooms()
        return JSONResponse({"status": "success", "rooms": rooms})
    except Exception as e:
        logger.error(f"Error listing LiveKit rooms: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Parallel Interview Management Endpoints
@app.post("/api/parallel_interview/create")
async def create_parallel_interview(request: Request):
    """
    Create a new parallel interview session with full initialization
    
    Request body:
    {
        "name": "John Doe",
        "email": "john@example.com",
        "phone": "+1234567890",
        "job_id": "job_123",  // Optional
        "questions": ["Q1", "Q2"],  // Optional if job_id provided
        "question_types": ["text", "coding"],  // Optional, defaults to "text"
        "max_questions": 5,  // Optional
        "text_question_timer": 120,  // Optional, seconds
        "coding_question_timer": 300  // Optional, seconds
    }
    
    Returns:
    {
        "status": "success",
        "session_id": "uuid",
        "livekit_room_name": "interview-uuid",
        "livekit_token": "token",
        "livekit_url": "wss://...",
        "user_details": {...},
        "interview_config": {...}
    }
    """
    try:
        data = await request.json()
        
        # Validate required fields
        name = data.get("name")
        email = data.get("email")
        phone = data.get("phone", "")
        
        if not name or not email:
            raise HTTPException(status_code=400, detail="name and email are required")
        
        # Create new session
        session_id = str(uuid.uuid4())
        new_state = InterviewState()
        new_state.user_details = UserDetails(name=name, phone=phone, email=email)
        new_state.proctoring_session_id = session_id
        
        # Parse questions
        job_id = data.get("job_id")
        questions = data.get("questions", [])
        question_types = data.get("question_types", [])
        
        parsed_questions = []
        parsed_question_types = []
        
        if job_id:
            job = jobs.get(job_id)
            if job and job.questions:
                if job.question_items:
                    parsed_questions = [item.text for item in job.question_items]
                    parsed_question_types = [item.type for item in job.question_items]
                else:
                    parsed_questions = [q.strip() for q in job.questions if q.strip()]
                    parsed_question_types = ["text"] * len(parsed_questions)
                
                new_state.text_question_timer = job.text_question_timer
                new_state.coding_question_timer = job.coding_question_timer
            else:
                raise HTTPException(status_code=404, detail="Job not found or has no questions")
        elif questions:
            parsed_questions = [str(q).strip() for q in questions if str(q).strip()]
            parsed_question_types = question_types if question_types else ["text"] * len(parsed_questions)
        else:
            raise HTTPException(status_code=400, detail="Either job_id or questions must be provided")
        
        if not parsed_questions:
            raise HTTPException(status_code=400, detail="No valid questions found")
        
        # Set interview configuration
        new_state.preloaded_questions = parsed_questions
        new_state.preloaded_question_types = parsed_question_types
        
        max_questions = data.get("max_questions")
        if max_questions is not None:
            new_state.max_questions = max(1, min(int(max_questions), len(parsed_questions)))
        else:
            new_state.max_questions = len(parsed_questions)
        
        # Override timers if provided
        if "text_question_timer" in data:
            new_state.text_question_timer = int(data["text_question_timer"])
        if "coding_question_timer" in data:
            new_state.coding_question_timer = int(data["coding_question_timer"])
        
        # Store in memory and MongoDB
        interview_states[session_id] = new_state
        
        session_data = {
            "user_details": new_state.user_details.dict(),
            "proctoring_session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "status": "initialized",
            "job_id": job_id,
            "job_title": jobs.get(job_id).title if job_id and jobs.get(job_id) else None,
            "question_index": 0,
            "dialogue": [],
            "answer_evaluations": [],
            "proctoring_violations": [],
            "consent_received": False,
            "preloaded_questions": parsed_questions,
            "preloaded_question_types": parsed_question_types,
            "text_question_timer": new_state.text_question_timer,
            "coding_question_timer": new_state.coding_question_timer,
        }
        
        user_sessions[session_id] = session_data
        await save_session_to_db(session_id, session_data)
        
        # Initialize proctoring session
        await proctoring_service.create_session(session_id)
        
        # Create LiveKit room
        room_name = f"interview-{session_id}"
        try:
            room_info = await livekit_manager.create_room(
                room_name=room_name,
                empty_timeout=600,
                max_participants=2
            )
            
            # Generate token
            candidate_token = livekit_manager.generate_token(
                room_name=room_name,
                participant_identity=f"candidate-{session_id}",
                participant_name=name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
                ttl=3600
            )
            
            new_state.livekit_room_name = room_name
            
            logger.info(f"✅ Parallel interview session created: {session_id} for {name}")
            
            return JSONResponse({
                "status": "success",
                "session_id": session_id,
                "livekit_room_name": room_name,
                "livekit_token": candidate_token,
                "livekit_url": livekit_manager.ws_url,
                "user_details": {
                    "name": name,
                    "email": email,
                    "phone": phone
                },
                "interview_config": {
                    "total_questions": len(parsed_questions),
                    "max_questions": new_state.max_questions,
                    "text_question_timer": new_state.text_question_timer,
                    "coding_question_timer": new_state.coding_question_timer,
                    "question_types": parsed_question_types
                }
            })
        except Exception as lk_error:
            logger.error(f"LiveKit room creation failed: {lk_error}")
            # Return session without LiveKit
            return JSONResponse({
                "status": "success",
                "session_id": session_id,
                "user_details": {
                    "name": name,
                    "email": email,
                    "phone": phone
                },
                "interview_config": {
                    "total_questions": len(parsed_questions),
                    "max_questions": new_state.max_questions,
                    "text_question_timer": new_state.text_question_timer,
                    "coding_question_timer": new_state.coding_question_timer
                },
                "warning": "LiveKit room creation failed, using fallback mode"
            })
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating parallel interview: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/parallel_interview/sessions")
async def list_parallel_interview_sessions(
    status: Optional[str] = Query(None, description="Filter by status: initialized, in_progress, completed"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
):
    """
    List all parallel interview sessions with filtering and pagination
    
    Returns:
    {
        "status": "success",
        "sessions": [...],
        "total": 100,
        "limit": 50,
        "offset": 0
    }
    """
    try:
        # Get sessions from MongoDB
        query = {}
        if status:
            query["status"] = status
        
        cursor = sessions_collection.find(query).skip(offset).limit(limit)
        sessions = await cursor.to_list(length=limit)
        
        total = await sessions_collection.count_documents(query)
        
        # Format sessions
        formatted_sessions = []
        for session in sessions:
            session["_id"] = str(session["_id"])
            formatted_sessions.append(session)
        
        return JSONResponse({
            "status": "success",
            "sessions": formatted_sessions,
            "total": total,
            "limit": limit,
            "offset": offset
        })
    except Exception as e:
        logger.error(f"Error listing parallel interview sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/parallel_interview/session/{session_id}")
async def get_parallel_interview_session(session_id: str):
    """
    Get detailed information about a specific parallel interview session
    
    Returns:
    {
        "status": "success",
        "session": {...},
        "interview_state": {...},
        "livekit_room": {...}
    }
    """
    try:
        # Get session from memory or MongoDB
        local_state = interview_states.get(session_id)
        
        if not local_state:
            session_doc = await get_session_from_db(session_id)
            if session_doc:
                local_state = session_to_interview_state(session_doc)
                interview_states[session_id] = local_state
            else:
                raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        
        # Get LiveKit room info if available
        livekit_room_info = None
        if local_state.livekit_room_name:
            try:
                rooms = await livekit_manager.list_rooms()
                for room in rooms:
                    if room.get("name") == local_state.livekit_room_name:
                        livekit_room_info = room
                        break
            except Exception as e:
                logger.warning(f"Could not fetch LiveKit room info: {e}")
        
        return JSONResponse({
            "status": "success",
            "session": {
                "session_id": session_id,
                "user_details": local_state.user_details.dict(),
                "is_active": local_state.is_interview_active,
                "current_question_count": local_state.current_question_count,
                "max_questions": local_state.max_questions,
                "consent_received": local_state.consent_received,
                "reference_face_captured": local_state.reference_face_captured,
                "total_questions": len(local_state.preloaded_questions),
                "current_question_index": local_state.current_question_index,
                "average_score": local_state.average_score,
                "proctoring_violations_count": len(local_state.proctoring_violations)
            },
            "interview_state": {
                "dialogue_length": len(local_state.current_dialogue),
                "evaluations_count": len(local_state.answer_evaluations),
                "text_question_timer": local_state.text_question_timer,
                "coding_question_timer": local_state.coding_question_timer
            },
            "livekit_room": livekit_room_info
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting parallel interview session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/parallel_interview/session/{session_id}/start")
async def start_parallel_interview_session(session_id: str):
    """
    Start/activate a parallel interview session
    
    Returns:
    {
        "status": "success",
        "message": "Interview session started",
        "session_id": "uuid"
    }
    """
    try:
        # Get session
        local_state = interview_states.get(session_id)
        
        if not local_state:
            session_doc = await get_session_from_db(session_id)
            if session_doc:
                local_state = session_to_interview_state(session_doc)
                interview_states[session_id] = local_state
            else:
                raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        
        # Activate interview
        local_state.is_interview_active = True
        
        # Update session in MongoDB
        if session_id in user_sessions:
            user_sessions[session_id]["status"] = "in_progress"
            await save_session_to_db(session_id, user_sessions[session_id])
        
        logger.info(f"✅ Parallel interview session started: {session_id}")
        
        return JSONResponse({
            "status": "success",
            "message": "Interview session started",
            "session_id": session_id,
            "livekit_room_name": local_state.livekit_room_name if local_state.livekit_room_name else None
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting parallel interview session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/parallel_interview/session/{session_id}/end")
async def end_parallel_interview_session(session_id: str):
    """
    End a parallel interview session and generate report
    
    Returns:
    {
        "status": "success",
        "message": "Interview session ended",
        "session_id": "uuid",
        "report_available": true
    }
    """
    try:
        # Get session
        local_state = interview_states.get(session_id)
        
        if not local_state:
            session_doc = await get_session_from_db(session_id)
            if session_doc:
                local_state = session_to_interview_state(session_doc)
                interview_states[session_id] = local_state
            else:
                raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        
        # Deactivate interview
        local_state.is_interview_active = False
        
        # Update session status
        if session_id in user_sessions:
            user_sessions[session_id]["status"] = "completed"
            await save_session_to_db(session_id, user_sessions[session_id])
        
        # Generate report in background
        if local_state.current_dialogue and local_state.answer_evaluations:
            asyncio.create_task(
                generate_report_background(
                    local_state.current_dialogue,
                    local_state.resume_summary,
                    local_state.answer_evaluations,
                    session_id
                )
            )
            report_available = True
        else:
            report_available = False
        
        # Clean up LiveKit room
        if local_state.livekit_room_name:
            try:
                await livekit_manager.delete_room(local_state.livekit_room_name)
                logger.info(f"LiveKit room deleted: {local_state.livekit_room_name}")
            except Exception as e:
                logger.warning(f"Could not delete LiveKit room: {e}")
        
        logger.info(f"✅ Parallel interview session ended: {session_id}")
        
        return JSONResponse({
            "status": "success",
            "message": "Interview session ended",
            "session_id": session_id,
            "report_available": report_available,
            "questions_answered": len(local_state.answer_evaluations),
            "average_score": local_state.average_score
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ending parallel interview session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/parallel_interview/session/{session_id}")
async def delete_parallel_interview_session(session_id: str):
    """
    Delete a parallel interview session and all associated data
    
    Returns:
    {
        "status": "success",
        "message": "Session deleted",
        "session_id": "uuid"
    }
    """
    try:
        # Remove from memory
        if session_id in interview_states:
            del interview_states[session_id]
        
        if session_id in user_sessions:
            del user_sessions[session_id]
        
        if session_id in generated_reports:
            del generated_reports[session_id]
        
        # Remove from MongoDB
        await sessions_collection.delete_one({"proctoring_session_id": session_id})
        await reports_collection.delete_one({"session_id": session_id})
        
        # Clean up LiveKit room
        room_name = f"interview-{session_id}"
        try:
            await livekit_manager.delete_room(room_name)
        except Exception as e:
            logger.warning(f"Could not delete LiveKit room: {e}")
        
        # Clean up proctoring session
        try:
            await proctoring_service.end_session(session_id)
        except Exception as e:
            logger.warning(f"Could not end proctoring session: {e}")
        
        logger.info(f"✅ Parallel interview session deleted: {session_id}")
        
        return JSONResponse({
            "status": "success",
            "message": "Session deleted",
            "session_id": session_id
        })
    except Exception as e:
        logger.error(f"Error deleting parallel interview session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/parallel_interview/stats")
async def get_parallel_interview_stats():
    """
    Get statistics about parallel interview sessions
    
    Returns:
    {
        "status": "success",
        "stats": {
            "total_sessions": 100,
            "active_sessions": 5,
            "completed_sessions": 90,
            "initialized_sessions": 5,
            "active_livekit_rooms": 5
        }
    }
    """
    try:
        # Count sessions by status
        total_sessions = await sessions_collection.count_documents({})
        active_sessions = await sessions_collection.count_documents({"status": "in_progress"})
        completed_sessions = await sessions_collection.count_documents({"status": "completed"})
        initialized_sessions = await sessions_collection.count_documents({"status": "initialized"})
        
        # Count active LiveKit rooms
        active_livekit_rooms = 0
        try:
            rooms = await livekit_manager.list_rooms()
            active_livekit_rooms = len([r for r in rooms if r.get("name", "").startswith("interview-")])
        except Exception as e:
            logger.warning(f"Could not fetch LiveKit rooms: {e}")
        
        # Count in-memory sessions
        in_memory_sessions = len(interview_states)
        
        return JSONResponse({
            "status": "success",
            "stats": {
                "total_sessions": total_sessions,
                "active_sessions": active_sessions,
                "completed_sessions": completed_sessions,
                "initialized_sessions": initialized_sessions,
                "in_memory_sessions": in_memory_sessions,
                "active_livekit_rooms": active_livekit_rooms
            }
        })
    except Exception as e:
        logger.error(f"Error getting parallel interview stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# DEPRECATED: WebSocket endpoints (kept for backward compatibility during migration)
# These will be removed once LiveKit migration is complete
        logger.error(f"Error starting interview session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/interview")
async def websocket_interview(websocket: EncodedWebSocket, session_id: str = Query(...)):
    """
    WebSocket handler for interview flow - now session-aware for parallel interviews.
    Each candidate gets their own isolated state loaded from MongoDB.
    """
    logger.info(f"WebSocket connection for session {session_id} from {websocket.client}")
    await manager.connect(websocket)
    
    # Load THIS candidate's session from MongoDB or dictionary
    local_state = None
    if session_id in interview_states:
        local_state = interview_states[session_id]
        logger.info(f"Loaded session {session_id} from memory")
    else:
        # Fallback: load from MongoDB
        session_doc = await get_session_from_db(session_id)
        if session_doc:
            local_state = session_to_interview_state(session_doc)
            interview_states[session_id] = local_state
            logger.info(f"Loaded session {session_id} from MongoDB")
    
    if not local_state:
        logger.error(f"Session {session_id} not found")
        await websocket.close(code=1008, reason="Session not found")
        return
    
    # Send initial greeting with dynamic timer information
    text_minutes = local_state.text_question_timer // 60
    coding_minutes = local_state.coding_question_timer // 60
    greeting = f"I'm an AI interviewer. I'm here to conduct a technical interview with you. You'll have {text_minutes} minute{'s' if text_minutes != 1 else ''} for text questions and {coding_minutes} minute{'s' if coding_minutes != 1 else ''} for coding questions. Are you ready to begin?"

    local_state.current_dialogue.append({
        "role": "interviewer",
        "content": greeting,
        "timestamp": datetime.now().isoformat()
    })

    local_state.last_question = greeting

    # Generate audio asynchronously
    audio_filename = await generate_audio_async(greeting)

    await websocket.send_text(json.dumps({
        "type": "question",
        "content": greeting,
        "audio_file": audio_filename,
        "start_recording": True,
        "proctoring_session_id": local_state.proctoring_session_id
    }, ensure_ascii=False))

    logger.info(f"Initial greeting sent for session {session_id}")

    while local_state.is_interview_active:
        try:
            data = await websocket.receive()
            if 'text' not in data:
                continue

            message = json.loads(data['text'])
            logger.debug(f"Session {session_id} received message type: {message.get('type')}")

            if message['type'] == 'text_response':
                user_text = message['content'].strip().replace('â—', '').replace('âœï¸', '')
                is_timeout_submission = message.get('timeout_submission', False)
                logger.info(f"Session {session_id} response: {user_text[:50]}... (timeout: {is_timeout_submission})")

                # Only process non-empty responses (unless it's a timeout submission)
                if (not user_text or user_text == "[No response]" or user_text.startswith("[No response")) and not is_timeout_submission:
                    logger.warning("Empty response received, requesting user to try again")
                    await websocket.send_text(json.dumps({
                        "type": "question",
                        "content": "I didn't catch that. Could you please repeat your answer?",
                        "audio_file": await generate_audio_async("I didn't catch that. Could you please repeat your answer?"),
                        "start_recording": True
                    }))
                    continue
                
                # For timeout submissions, use a default message if empty
                if is_timeout_submission and (not user_text or user_text == "[No response]" or user_text.startswith("[No response")):
                    user_text = "[No response - Time expired]"
                    logger.info("Timeout submission with no response - proceeding to next question")

                # Send simple acknowledgment without evaluation details
                await websocket.send_text(json.dumps({
                    "type": "processing_response",
                    "content": "Thank you for your response. Processing next question..."
                }))

                # Process user response
                local_state.current_dialogue.append({
                    "role": "candidate",
                    "content": user_text,
                    "timestamp": datetime.now().isoformat()
                })

                # Consent flow
                if not local_state.consent_received:
                    if (not local_state.consent_received and any(kw in user_text.lower() for kw in ["yes", "sure", "ready", "start", "okay", "go ahead", "begin"])):
                        local_state.consent_received = True
                        logger.info(f"Session {session_id}: Consent received. Asking first preloaded question")

                        if local_state.preloaded_questions and local_state.current_question_index < len(local_state.preloaded_questions):
                            first_question = local_state.preloaded_questions[local_state.current_question_index]
                            first_question_type = local_state.preloaded_question_types[local_state.current_question_index] if local_state.current_question_index < len(local_state.preloaded_question_types) else "text"
                            local_state.current_question_index += 1
                        else:
                            first_question = "Let's begin."
                            first_question_type = "text"
                        local_state.current_question_count += 1
                        local_state.last_question = first_question

                        local_state.current_dialogue.append({
                            "role": "interviewer",
                            "content": first_question,
                            "timestamp": datetime.now().isoformat()
                        })

                        audio_filename = await generate_audio_async(first_question)
                        
                        # Determine timer based on question type
                        question_timer = local_state.coding_question_timer if first_question_type == "coding" else local_state.text_question_timer

                        await websocket.send_text(json.dumps({
                            "type": "question",
                            "content": first_question,
                            "audio_file": audio_filename,
                            "start_recording": first_question_type != "coding",
                            "question_type": first_question_type,
                            "timer_seconds": question_timer
                        }))
                        
                        # Save state to MongoDB after consent
                        await save_interview_state_to_db(session_id, local_state)
                    elif not local_state.consent_received:
                        await websocket.send_text(json.dumps({
                            "type": "question",
                            "content": "Just let me know when you're ready to begin the interview.",
                            "audio_file": await generate_audio_async("Just let me know when you're ready to begin the interview."),
                            "start_recording": True
                        }))
                    continue

                # **HIDDEN AI EVALUATION - run fully in background to reduce latency**
                # Skip evaluation for timeout submissions with no meaningful content
                if user_text.strip() and local_state.last_question and not (is_timeout_submission and user_text.startswith("[No response")):
                    async def _evaluate_and_store(question_text: str, answer_text: str, resume_summary_text: str):
                        try:
                            evaluation = await evaluate_user_answer(
                                question_text,
                                answer_text,
                                resume_summary_text
                            )

                            local_state.answer_evaluations.append({
                                "question": question_text,
                                "answer": answer_text,
                                "evaluation": evaluation,
                                "timestamp": datetime.now().isoformat()
                            })

                            local_state.total_score += evaluation["overall_score"]
                            local_state.average_score = local_state.total_score / len(local_state.answer_evaluations)

                            logger.info(f"Session {session_id}: Answer evaluated silently: Score {evaluation['overall_score']}/10, Average: {local_state.average_score:.1f}")

                        except Exception as e:
                            logger.error(f"Error during silent answer evaluation: {e}")

                    # Track pending evaluation tasks to ensure they complete before report generation
                    try:
                        task = asyncio.create_task(_evaluate_and_store(local_state.last_question, user_text, local_state.resume_summary))
                        local_state._pending_eval_tasks.append(task)
                    except Exception as _:
                        pass

                # Proceed immediately to next question (no blocking sleep)
                await asyncio.sleep(0)

                # Continue while there are preloaded questions remaining and within max_questions
                should_continue = (
                    local_state.current_question_count < local_state.max_questions and
                    local_state.current_question_index < len(local_state.preloaded_questions)
                )

                if should_continue:
                    next_question = local_state.preloaded_questions[local_state.current_question_index]
                    next_question_type = local_state.preloaded_question_types[local_state.current_question_index] if local_state.current_question_index < len(local_state.preloaded_question_types) else "text"
                    local_state.current_question_index += 1
                else:
                    next_question = "Thank you for attending the interview. Your report will be generated shortly."
                    next_question_type = "text"
                    should_continue = False

                local_state.current_question_count += 1
                local_state.last_question = next_question

                local_state.current_dialogue.append({
                    "role": "interviewer",
                    "content": next_question,
                    "timestamp": datetime.now().isoformat()
                })

                audio_filename = await generate_audio_async(next_question)
                
                # Determine timer based on question type
                question_timer = local_state.coding_question_timer if next_question_type == "coding" else local_state.text_question_timer

                await websocket.send_text(json.dumps({
                    "type": "question" if should_continue else "interview_concluded",
                    "content": next_question,
                    "audio_file": audio_filename,
                    "start_recording": should_continue and next_question_type != "coding",
                    "stop_recording": not should_continue,
                    "total_questions": len(local_state.answer_evaluations),
                    "question_type": next_question_type,
                    "timer_seconds": question_timer if should_continue else 0
                }))

                # Save state to MongoDB after each question
                await save_interview_state_to_db(session_id, local_state)

                if not should_continue:
                    break

            elif message['type'] == 'end_interview':
                logger.info(f"Session {session_id}: Client requested to end interview.")
                conclusion = "Thank you for your time. Your interview report will be available shortly."

                local_state.current_dialogue.append({
                    "role": "interviewer",
                    "content": conclusion,
                    "timestamp": datetime.now().isoformat()
                })

                audio_filename = await generate_audio_async(conclusion)

                await websocket.send_text(json.dumps({
                    "type": "interview_concluded",
                    "content": conclusion,
                    "audio_file": audio_filename,
                    "stop_recording": True
                }))
                break

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for session {session_id}.")
            break
        except Exception as e:
            logger.error(f"Error processing WebSocket message for session {session_id}: {e}")
            # Don't try to send error message if WebSocket is already closed
            try:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "content": "Sorry, something went wrong. Let's continue shortly.",
                    "stop_recording": True
                }))
            except:
                logger.debug(f"Could not send error message, WebSocket already closed for session {session_id}")
            break

    manager.disconnect(websocket)
    local_state.is_interview_active = False

    # Ensure all pending evaluations complete before report generation (with timeout)
    try:
        pending = [t for t in local_state._pending_eval_tasks if not t.done()]
        if pending:
            logger.info(f"Session {session_id}: Waiting for {len(pending)} pending evaluation tasks...")
            await asyncio.wait_for(
                asyncio.gather(*pending, return_exceptions=True),
                timeout=10.0  # Max 10 seconds wait
            )
    except asyncio.TimeoutError:
        logger.warning(f"Session {session_id}: Evaluation tasks timed out after 10s, proceeding with report generation")
    except Exception as e:
        logger.warning(f"Session {session_id}: Pending evaluation tasks wait failed: {e}")
    finally:
        local_state._pending_eval_tasks = []

    # Always generate and store report on interview end (with timeout protection)
    report = None
    try:
        if local_state.current_dialogue:
            logger.info(f"Session {session_id}: Starting report generation...")
            # Add timeout to prevent indefinite hanging
            report = await asyncio.wait_for(
                generate_interview_report(
                    local_state.current_dialogue,
                    local_state.resume_summary,
                    local_state.answer_evaluations
                ),
                timeout=90.0  # Max 90 seconds for report generation (increased for OpenRouter)
            )
            generated_reports[local_state.proctoring_session_id] = report
            logger.info(f"Session {session_id}: Report generated successfully")
            
            # Save to MongoDB database (with timeout)
            job_id = user_sessions.get(local_state.proctoring_session_id, {}).get("job_id")
            try:
                await asyncio.wait_for(
                    save_interview_report_to_db(
                        local_state.proctoring_session_id,
                        report,
                        job_id
                    ),
                    timeout=10.0  # Max 10 seconds for DB save
                )
                logger.info(f"Session {session_id}: Report saved to database")
            except asyncio.TimeoutError:
                logger.error(f"Session {session_id}: MongoDB save timed out after 10s")
            except Exception as db_error:
                logger.error(f"Session {session_id}: Failed to save report to DB: {db_error}")
            
            if local_state.proctoring_session_id in user_sessions:
                user_sessions[local_state.proctoring_session_id]["status"] = "completed"
                user_sessions[local_state.proctoring_session_id]["completed_at"] = datetime.now().isoformat()
                user_sessions[local_state.proctoring_session_id]["overall_score"] = report.overall_score
            
            # Update session status in MongoDB
            await update_session_status(
                local_state.proctoring_session_id,
                "completed",
                datetime.now().isoformat()
            )
        else:
            logger.info(f"Session {session_id}: No dialogue found; skipping report generation")
    except asyncio.TimeoutError:
        logger.error(f"Session {session_id}: Report generation timed out after 90s - no report generated")
    except Exception as e:
        logger.error(f"Session {session_id}: Error generating/storing report on end: {e}", exc_info=True)

    # Automatic email sending to admin (always enabled)
    ADMIN_EMAIL = "manansharmas0464@gmail.com"
    if (report and local_state.proctoring_session_id not in email_sent_for_session):
        async def _send_email_background():
            try:
                # Send to admin email instead of candidate
                result = await send_interview_report_email(
                    ADMIN_EMAIL,
                    local_state.user_details.name,
                    report
                )
                if result["success"]:
                    email_sent_for_session.add(local_state.proctoring_session_id)
                    logger.info(f"Session {session_id}: Automatic email sent to admin {ADMIN_EMAIL}")
                else:
                    logger.error(f"Session {session_id}: Failed to send automatic email: {result['message']}")
            except Exception as e:
                logger.error(f"Session {session_id}: Email sending exception: {e}")
        
        # Send email in background
        asyncio.create_task(_send_email_background())
    
    # Clean up session from memory after completion
    if session_id in interview_states:
        del interview_states[session_id]
        logger.info(f"Session {session_id}: Cleaned up from memory")
@app.websocket("/ws/proctoring")
async def websocket_proctoring(websocket: EncodedWebSocket, session_id: str = Query(...)):
    """WebSocket endpoint for proctoring functionality - session-aware"""
    logger.info(f"Proctoring WebSocket connection established for session {session_id} from {websocket.client}")
    await manager.connect_proctoring(websocket)
    
    # Get session-specific state
    local_state = None
    if session_id in interview_states:
        local_state = interview_states[session_id]
        logger.info(f"Loaded proctoring state for session {session_id} from memory")
    else:
        # Fallback: load from MongoDB
        session_doc = await get_session_from_db(session_id)
        if session_doc:
            local_state = session_to_interview_state(session_doc)
            interview_states[session_id] = local_state
            logger.info(f"Loaded proctoring state for session {session_id} from MongoDB")
    
    if not local_state:
        logger.error(f"Proctoring session {session_id} not found")
        await websocket.close(code=1008, reason="Session not found")
        return

    while True:
        try:
            data = await websocket.receive()
            if 'text' not in data:
                continue

            message = json.loads(data['text'])
            logger.debug(f"Received proctoring message type: {message.get('type')}")

            if message['type'] == 'set_reference_face':
                result = await proctoring_service.set_reference_face(
                    message['session_id'],
                    message['image_data']
                )

                await websocket.send_text(json.dumps({
                    "type": "reference_face_response",
                    "result": result
                }))

            elif message['type'] == 'process_frame':
                result = await proctoring_service.process_frame(
                    message['session_id'],
                    message['image_data']
                )

                # Store violations in session-specific interview state
                if result.get('violations'):
                    for violation in result['violations']:
                        if violation.get('type') == 'violation':
                            local_state.proctoring_violations.append({
                                "timestamp": datetime.now().isoformat(),
                                "type": violation.get('message', 'Unknown violation'),
                                "severity": violation.get('severity', 'medium')
                            })

                # Check if session should be terminated
                if result.get('violations'):
                    for violation in result['violations']:
                        if violation.get('terminate', False):
                            # End interview due to proctoring violations
                            local_state.is_interview_active = False
                            logger.info(f"Session {session_id}: Interview terminated due to proctoring violations")
                            break

                # Only send if connection is still open
                try:
                    await websocket.send_text(json.dumps({
                        "type": "proctoring_result",
                        "result": result
                    }))
                except:
                    logger.debug("Proctoring WebSocket already closed, skipping result send")
                    break

        except WebSocketDisconnect:
            logger.info(f"Proctoring WebSocket disconnected for {websocket.client}.")
            break
        except Exception as e:
            logger.error(f"Error processing proctoring WebSocket message: {e}", exc_info=True)
            # Don't try to send if connection is already closed
            try:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Proctoring error occurred"
                }))
            except:
                pass  # Connection already closed, ignore
            break

    manager.disconnect_proctoring(websocket)

@app.websocket("/ws/sarvam-stt")
async def websocket_sarvam_stt_proxy(websocket: WebSocket):
    """WebSocket proxy for Sarvam STT to add API key header"""
    await websocket.accept()
    logger.info(f"Sarvam STT proxy WebSocket connected from {websocket.client}")
    
    if not SARVAM_API_KEY:
        await websocket.send_json({"type": "error", "data": {"error": "Sarvam API key not configured"}})
        await websocket.close()
        return
    
    # Connect to Sarvam STT WebSocket with API key header
    sarvam_ws_url = "wss://api.sarvam.ai/speech-to-text-translate/ws?model=saaras:v2.5&sample_rate=16000&vad_signals=true&flush_signal=true"
    headers = {
        "Api-Subscription-Key": SARVAM_API_KEY
    }
    
    try:
        import websockets
        async with websockets.connect(sarvam_ws_url, extra_headers=headers) as sarvam_ws:
            logger.info("✅ Connected to Sarvam STT WebSocket")
            
            # Create tasks for bidirectional communication
            async def forward_to_sarvam():
                try:
                    while True:
                        data = await websocket.receive_text()
                        await sarvam_ws.send(data)
                        logger.debug(f"Forwarded to Sarvam: {data[:100]}...")
                except Exception as e:
                    logger.error(f"Error forwarding to Sarvam: {e}")
            
            async def forward_from_sarvam():
                try:
                    async for message in sarvam_ws:
                        await websocket.send_text(message)
                        logger.debug(f"Forwarded from Sarvam: {message[:100]}...")
                except Exception as e:
                    logger.error(f"Error forwarding from Sarvam: {e}")
            
            # Run both tasks concurrently
            await asyncio.gather(
                forward_to_sarvam(),
                forward_from_sarvam()
            )
            
    except Exception as e:
        logger.error(f"Sarvam STT proxy error: {e}", exc_info=True)
        await websocket.send_json({"type": "error", "data": {"error": str(e)}})
    finally:
        await websocket.close()
        logger.info("Sarvam STT proxy WebSocket closed")

# FIXED: Single report route with automatic email sending and notification
@app.get("/report", response_class=HTMLResponse)
async def get_report(request: Request):
    """Generate and display the interview report with automatic email sending."""
    global interview_state

    if not interview_state.current_dialogue:
        logger.warning("No interview data available for report generation")
        return templates.TemplateResponse("index.html", {
            "request": request,
            "error": "No interview data available. Please complete an interview first."
        })

    # End proctoring session if active
    if interview_state.proctoring_session_id:
        await proctoring_service.end_session(interview_state.proctoring_session_id)

    # Generate the comprehensive report using resume summary
    report = await generate_interview_report(
        interview_state.current_dialogue,
        interview_state.resume_summary,
        interview_state.answer_evaluations
    )

    # AUTOMATIC EMAIL SENDING - Only send once per session
    email_status = None
    if (interview_state.proctoring_session_id not in email_sent_for_session and 
        interview_state.user_details.email and 
        EMAIL_USERNAME and EMAIL_PASSWORD):
        
        try:
            # Send email automatically
            email_result = await send_interview_report_email(
                interview_state.user_details.email,
                interview_state.user_details.name,
                report
            )
            
            if email_result["success"]:
                email_status = {
                    "success": True,
                    "message": f"✅ Report automatically sent to {interview_state.user_details.email}"
                }
                # Mark this session as emailed to prevent duplicates
                email_sent_for_session.add(interview_state.proctoring_session_id)
                logger.info(f"✅ Automatic email sent successfully to {interview_state.user_details.email}")
            else:
                email_status = {
                    "success": False,
                    "message": f"❌ Failed to send email: {email_result['message']}"
                }
                logger.error(f"❌ Automatic email failed: {email_result['message']}")
        except Exception as e:
            email_status = {
                "success": False,
                "message": f"❌ Email error: {str(e)}"
            }
            logger.error(f"❌ Automatic email exception: {e}")
    elif interview_state.proctoring_session_id in email_sent_for_session:
        email_status = {
            "success": True,
            "message": f"✅ Report was already sent to {interview_state.user_details.email}"
        }
    elif not EMAIL_USERNAME or not EMAIL_PASSWORD:
        email_status = {
            "success": False,
            "message": "⚠️ Email not configured. Please set up email credentials."
        }
    elif not interview_state.user_details.email:
        email_status = {
            "success": False,
            "message": "⚠️ No candidate email address available."
        }

    return templates.TemplateResponse("report.html", {
        "request": request,
        "report": report,
        "email_status": email_status  # Pass email status to template
    })

@app.get("/report/{session_id}", response_class=HTMLResponse)
async def get_report_by_session(session_id: str, request: Request):
    """Get interview report for a specific session ID."""
    # Try to get from memory cache first
    report = generated_reports.get(session_id)
    
    if not report:
        # Try to load from MongoDB
        db_record = await get_interview_report_from_db(session_id)
        if not db_record:
            logger.warning(f"Report not found for session {session_id}")
            raise HTTPException(status_code=404, detail="Report not found for this session")
        
        # Reconstruct report from DB
        report = InterviewReport(**db_record["report_json"])
        generated_reports[session_id] = report
        logger.info(f"Report loaded from DB for session {session_id}")
    
    # Get session info for email status
    session_info = user_sessions.get(session_id, {})
    email_status = None
    
    if session_id in email_sent_for_session:
        email_status = {
            "success": True,
            "message": f"✅ Report was sent to admin email"
        }
    
    return templates.TemplateResponse("report.html", {
        "request": request,
        "report": report,
        "email_status": email_status
    })

@app.get("/report/download")
async def download_report_pdf(request: Request, session_id: Optional[str] = None):
    """Generate and download PDF report."""
    global interview_state
    
    report = None
    
    # If session_id provided, use that specific report
    if session_id:
        report = generated_reports.get(session_id)
        if not report:
            db_record = await get_interview_report_from_db(session_id)
            if db_record:
                report = InterviewReport(**db_record["report_json"])
    
    # Fallback to current interview_state
    if not report:
        if not interview_state.current_dialogue:
            raise HTTPException(status_code=404, detail="No interview data available")
        
        # Generate the report using resume summary
        report = await generate_interview_report(
            interview_state.current_dialogue,
            interview_state.resume_summary,
            interview_state.answer_evaluations
        )

    # Render HTML template
    html_content = templates.get_template("report_pdf.html").render(
        request=request,
        report=report
    )

    # Generate PDF using xhtml2pdf
    pdf_buffer = BytesIO()
    pisa_status = pisa.CreatePDF(src=html_content, dest=pdf_buffer)
    pdf_buffer.seek(0)
    if getattr(pisa_status, 'err', 0):
        logger.error("PDF generation error on download: %s", getattr(pisa_status, 'err', None))

    # Use candidate name in filename if available
    filename = f"interview_report_{report.candidate_name.replace(' ', '_')}.pdf" if report.candidate_name else "interview_report.pdf"
    
    return Response(
        content=pdf_buffer.read(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    logger.info(f"Serving audio file: {filename}")
    file_path = os.path.join(AUDIO_FOLDER, filename)
    
    # Debug: List all files in audio folder
    if not os.path.exists(file_path):
        try:
            existing_files = os.listdir(AUDIO_FOLDER) if os.path.exists(AUDIO_FOLDER) else []
            logger.error(f"Audio file not found: {file_path}")
            logger.error(f"Files in {AUDIO_FOLDER}: {existing_files[:10]}")  # Show first 10 files
        except Exception as e:
            logger.error(f"Error listing audio folder: {e}")
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(file_path)

@app.get("/api/sarvam-config")
async def get_sarvam_config():
    """Provide Sarvam API configuration to frontend"""
    if not SARVAM_API_KEY:
        raise HTTPException(status_code=500, detail="Sarvam API key not configured")
    
    return JSONResponse({
        "api_key": "configured",  # Don't expose actual key to frontend
        "ws_url": "/ws/sarvam-stt",  # Use backend proxy
        "model": "saaras:v2.5",
        "sample_rate": 16000
    })

@app.post("/send_report_email")
async def send_report_email_manually(request: Request):
    """Manual email sending with duplicate prevention."""
    try:
        data = await request.json()
        candidate_email = data.get("email", "").strip()
        candidate_name = data.get("name", "").strip()

        if not candidate_email or not candidate_name:
            raise HTTPException(status_code=400, detail="Email and name are required")

        if not interview_state.current_dialogue:
            raise HTTPException(status_code=404, detail="No interview data available")

        # Generate fresh report
        report = await generate_interview_report(
            interview_state.current_dialogue,
            interview_state.resume_summary,
            interview_state.answer_evaluations
        )
        
        # Update report with provided details
        report.candidate_email = candidate_email
        report.candidate_name = candidate_name

        # Send email
        result = await send_interview_report_email(candidate_email, candidate_name, report)

        if result["success"]:
            # Mark as sent to prevent automatic sending again
            if interview_state.proctoring_session_id:
                email_sent_for_session.add(interview_state.proctoring_session_id)
            
            logger.info(f"✅ Manual email sent successfully to {candidate_email}")
            return JSONResponse({
                "success": True,
                "message": f"Report successfully sent to {candidate_email}"
            })
        else:
            # Return appropriate error status based on error type
            status_code = 400 if result.get("error_type") == "configuration" else 500
            raise HTTPException(status_code=status_code, detail=result["message"])

    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error in manual email sending: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/test_email")
async def test_email_configuration():
    """Test email configuration by sending a test email."""
    if not EMAIL_USERNAME or not EMAIL_PASSWORD:
        raise HTTPException(status_code=400, detail="Email credentials not configured. Please set EMAIL_USERNAME and EMAIL_PASSWORD in .env file")

    try:
        result = await send_email_notification(
            EMAIL_USERNAME,  # Send to self for testing
            "AI Interview System - Email Test",
            "This is a test email to verify that the email configuration is working correctly.\n\nIf you receive this message, the email system is properly configured.\n\nTime: " + str(datetime.now())
        )

        if result["success"]:
            return JSONResponse({
                "status": "success",
                "message": result["message"]
            })
        else:
            status_code = 400 if result.get("error_type") == "configuration" else 500
            raise HTTPException(status_code=status_code, detail=result["message"])

    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error testing email configuration: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/email_status")
async def get_email_status():
    """Get current email configuration status."""
    is_configured = bool(EMAIL_USERNAME and EMAIL_PASSWORD)
    return JSONResponse({
        "email_configured": is_configured,
        "smtp_server": EMAIL_SMTP_SERVER if is_configured else "Not configured",
        "smtp_port": EMAIL_SMTP_PORT if is_configured else "Not configured",
        "from_name": EMAIL_FROM_NAME if is_configured else "Not configured",
        "use_tls": EMAIL_USE_TLS if is_configured else "Not configured",
        "username": EMAIL_USERNAME if is_configured else "Not configured",
        "setup_instructions": {
            "message": "Email not configured. Automatic report sending is disabled." if not is_configured else "Email is properly configured.",
            "steps": [
                "1. Edit the .env file in the project root",
                "2. Uncomment and configure the EMAIL_* variables",
                "3. For Gmail: Use App Password (not regular password)",
                "4. Restart the application",
                "5. Test email configuration using /test_email endpoint"
            ] if not is_configured else []
        }
    })

@app.get("/email_setup_guide")
async def email_setup_guide():
    """Provide detailed email setup instructions."""
    return JSONResponse({
        "title": "Email Setup Guide for AI Interview System",
        "current_status": "Configured" if (EMAIL_USERNAME and EMAIL_PASSWORD) else "Not Configured",
        "gmail_setup": {
            "title": "Gmail Setup (Recommended)",
            "steps": [
                "1. Enable 2-Factor Authentication on your Gmail account",
                "2. Go to Google Account Settings → Security",
                "3. Under '2-Step Verification', select 'App passwords'",
                "4. Generate a password for 'Mail'",
                "5. Copy the generated 16-character password",
                "6. In .env file, set EMAIL_USERNAME=your_email@gmail.com",
                "7. In .env file, set EMAIL_PASSWORD=the_generated_app_password",
                "8. Restart the application"
            ],
            "env_example": {
                "EMAIL_SMTP_SERVER": "smtp.gmail.com",
                "EMAIL_SMTP_PORT": "587",
                "EMAIL_USERNAME": "your_email@gmail.com",
                "EMAIL_PASSWORD": "your_16_char_app_password",
                "EMAIL_FROM_NAME": "AI Interview System",
                "EMAIL_USE_TLS": "true"
            }
        },
        "other_providers": {
            "outlook": {
                "EMAIL_SMTP_SERVER": "smtp-mail.outlook.com",
                "EMAIL_SMTP_PORT": "587"
            },
            "yahoo": {
                "EMAIL_SMTP_SERVER": "smtp.mail.yahoo.com",
                "EMAIL_SMTP_PORT": "587"
            }
        },
        "testing": {
            "message": "After configuration, test your email setup",
            "endpoint": "POST /test_email",
            "description": "Sends a test email to your configured email address"
        },
        "troubleshooting": [
            "Ensure 2FA is enabled for Gmail",
            "Use App Password, not your regular Gmail password",
            "Check firewall settings for SMTP ports",
            "Verify email address and password are correct",
            "Check spam folder for test emails"
        ]
    })

# Record fullscreen exit events as proctoring violations
@app.post("/proctoring/fullscreen_event")
async def record_fullscreen_event(request: Request):
    try:
        data = await request.json()
        event = data.get("event", "exit_fullscreen")
        session_id = data.get("session_id", interview_state.proctoring_session_id)
        severity = data.get("severity", "medium")

        interview_state.proctoring_violations.append({
            "timestamp": datetime.now().isoformat(),
            "type": "Fullscreen Exit" if event == "exit_fullscreen" else f"Screen Event: {event}",
            "severity": severity
        })

        logger.info(f"Recorded fullscreen event for session {session_id}: {event}")
        return JSONResponse({"status": "ok"})
    except Exception as e:
        logger.error(f"Error recording fullscreen event: {e}")
        raise HTTPException(status_code=500, detail="Failed to record event")

# --- Admin: Jobs & Dashboard ---
@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse(job.dict())

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    try:
        # Prepare jobs list and interviews list
        jobs_list = list(jobs.values())
        interviews = []
        for session_id, data in user_sessions.items():
            details = data.get("user_details", {})
            interviews.append({
                "session_id": session_id,
                "name": details.get("name", "Candidate"),
                "email": details.get("email", ""),
                "phone": details.get("phone", ""),
                "job_id": data.get("job_id"),
                "job_title": data.get("job_title"),
                "created_at": data.get("created_at"),
                "completed_at": data.get("completed_at"),
                "status": data.get("status", "unknown"),
                "has_report": session_id in generated_reports,
                "overall_score": data.get("overall_score")
            })
        interviews.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return templates.TemplateResponse("admin.html", {
            "request": request,
            "jobs": jobs_list,
            "interviews": interviews
        })
    except Exception as e:
        logger.error(f"Error rendering admin dashboard: {e}")
        raise HTTPException(status_code=500, detail="Failed to render admin dashboard")

@app.post("/admin/jobs/create")
async def admin_create_job(
    title: str = Form(...),
    description: str = Form(""),
    location: str = Form(""),
    experience: str = Form(""),
    status: str = Form("open"),
    questions: str = Form(""),
    question_types: str = Form(""),  # JSON string of question types
    text_question_timer: int = Form(120),  # Timer for text questions (default 120 seconds)
    coding_question_timer: int = Form(300)  # Timer for coding questions (default 300 seconds)
):
    try:
        job_id = str(uuid.uuid4())
        q_list = [q.strip() for q in questions.splitlines() if q.strip()]
        
        # Parse question types (JSON format: {"0": "text", "1": "coding", ...})
        question_items = []
        try:
            types_dict = json.loads(question_types) if question_types else {}
            for idx, q_text in enumerate(q_list):
                q_type = types_dict.get(str(idx), "text")
                question_items.append(QuestionItem(text=q_text, type=q_type))
        except:
            # Fallback: all questions are text type
            question_items = [QuestionItem(text=q, type="text") for q in q_list]
        
        now = datetime.now().isoformat()
        job = JobOpening(
            id=job_id,
            title=title,
            description=description,
            location=location,
            experience=experience,
            status=status,
            questions=q_list,  # Keep for backward compatibility
            question_items=question_items,
            text_question_timer=text_question_timer,
            coding_question_timer=coding_question_timer,
            created_at=now,
            updated_at=now
        )
        jobs[job_id] = job
        await save_job_to_db(job)
        return JSONResponse({"success": True, "job": job.dict(), "share_url": f"/?job_id={job_id}"})
    except Exception as e:
        logger.error(f"Error creating job: {e}")
        raise HTTPException(status_code=500, detail="Failed to create job")

@app.post("/admin/jobs/{job_id}/delete")
async def admin_delete_job(job_id: str):
    try:
        if job_id in jobs:
            del jobs[job_id]
            await delete_job_from_db(job_id)
            return JSONResponse({"success": True})
        else:
            raise HTTPException(status_code=404, detail="Job not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting job: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete job")

@app.post("/admin/jobs/reload")
async def admin_reload_jobs():
    """Reload all jobs from MongoDB into memory"""
    try:
        await load_jobs_from_db()
        return JSONResponse({
            "success": True, 
            "message": f"Reloaded {len(jobs)} job(s) from MongoDB",
            "jobs": {job_id: {"title": job.title, "questions": len(job.questions)} for job_id, job in jobs.items()}
        })
    except Exception as e:
        logger.error(f"Error reloading jobs: {e}")
        raise HTTPException(status_code=500, detail="Failed to reload jobs")

# --- Candidates Dashboard Routes ---
@app.get("/candidates", response_class=HTMLResponse)
async def list_candidates(request: Request):
    try:
        # Build lightweight view models
        candidates = []
        for session_id, data in user_sessions.items():
            details = data.get("user_details", {})
            candidates.append({
                "session_id": session_id,
                "name": details.get("name", "Candidate"),
                "email": details.get("email", ""),
                "phone": details.get("phone", ""),
                "created_at": data.get("created_at", ""),
                "completed_at": data.get("completed_at", ""),
                "status": data.get("status", "unknown"),
                "has_report": session_id in generated_reports,
                "overall_score": data.get("overall_score")
            })

        # Sort newest first
        candidates.sort(key=lambda c: c.get("created_at", ""), reverse=True)

        return templates.TemplateResponse("candidates.html", {
            "request": request,
            "candidates": candidates
        })
    except Exception as e:
        logger.error(f"Error listing candidates: {e}")
        raise HTTPException(status_code=500, detail="Failed to load candidates")


@app.get("/candidates/{session_id}", response_class=HTMLResponse)
async def view_candidate_report(session_id: str, request: Request):
    try:
        if session_id not in user_sessions:
            raise HTTPException(status_code=404, detail="Candidate session not found")

        # Try to get report from memory first, then from database
        report = generated_reports.get(session_id)
        if not report:
            # Try to fetch from database
            db_record = await get_interview_report_from_db(session_id)
            if db_record and db_record.get("report_json"):
                report = InterviewReport(**db_record["report_json"])
        else:
            # Report exists in memory only; ensure it is persisted for future access
            db_record = await get_interview_report_from_db(session_id)
            if not db_record:
                job_id = user_sessions.get(session_id, {}).get("job_id")
                await save_interview_report_to_db(session_id, report, job_id)
        if not report:
            # Report not available yet
            return templates.TemplateResponse("candidates.html", {
                "request": request,
                "candidates": [
                    {
                        "session_id": session_id,
                        "name": user_sessions[session_id]["user_details"].get("name", "Candidate"),
                        "email": user_sessions[session_id]["user_details"].get("email", ""),
                        "phone": user_sessions[session_id]["user_details"].get("phone", ""),
                        "created_at": user_sessions[session_id].get("created_at", ""),
                        "completed_at": user_sessions[session_id].get("completed_at", ""),
                        "status": user_sessions[session_id].get("status", "unknown"),
                        "has_report": False,
                        "overall_score": user_sessions[session_id].get("overall_score")
                    }
                ],
                "message": "Report is not available for this session yet."
            })

        # Render the same report template with the stored report
        return templates.TemplateResponse("report.html", {"request": request, "report": report})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error viewing candidate report: {e}")
        raise HTTPException(status_code=500, detail="Failed to load candidate report")

# --- Sarvam Saarika STT Endpoint ---
@app.post("/transcribe_audio")
async def transcribe_audio(audio: UploadFile = File(...)):
    """Transcribe audio using Sarvam Saarika v2.5 STT"""
    if not SARVAM_API_KEY:
        raise HTTPException(status_code=500, detail="Sarvam API key not configured")
    
    try:
        logger.info("Transcribing audio with Sarvam Saarika v2.5...")
        
        # Read audio file
        audio_content = await audio.read()
        
        # Prepare multipart form data
        url = "https://api.sarvam.ai/speech-to-text"
        headers = {
            "api-subscription-key": SARVAM_API_KEY
        }
        
        files = {
            "file": (audio.filename, audio_content, audio.content_type)
        }
        params = {
            "language": "en-IN",  # Match test file format
            "model": "saarika:v2.5"  # Correct model name (not saaras)
        }
        
        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, files=files, data=params)
            
            logger.info(f"Sarvam STT response status: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"Sarvam STT error: {response.status_code} - {response.text}")
                raise Exception(f"Sarvam STT API returned {response.status_code}")
            
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Sarvam STT response keys: {result.keys()}")
            
            # Try both 'text' and 'transcript' fields
            transcript = result.get("text", result.get("transcript", ""))
            
            logger.info(f"Transcription successful: {transcript[:100]}...")
            return JSONResponse({
                "success": True,
                "transcript": transcript
            })
            
    except Exception as e:
        logger.error(f"Sarvam STT failed: {e}", exc_info=True)
        return JSONResponse({
            "success": False,
            "error": str(e),
            "transcript": ""
        }, status_code=500)

# API endpoints for interview reports from database
@app.get("/api/reports")
async def get_all_reports(limit: int = 100, offset: int = 0):
    """Get all interview reports from database with pagination"""
    try:
        reports = await get_all_interview_reports_from_db(limit, offset)
        return JSONResponse({
            "success": True,
            "count": len(reports),
            "reports": reports
        })
    except Exception as e:
        logger.error(f"Error fetching reports: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch reports")

@app.get("/api/reports/{session_id}")
async def get_report_by_session(session_id: str):
    """Get interview report by session ID from database"""
    try:
        report = await get_interview_report_from_db(session_id)
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        return JSONResponse({
            "success": True,
            "report": report
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching report: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch report")

if __name__ == "__main__":
    logger.info("Starting FastAPI application with Uvicorn.")
    uvicorn.run(app, host="0.0.0.0", port=8021, reload=True)
