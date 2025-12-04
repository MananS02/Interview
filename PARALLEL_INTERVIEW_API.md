# Parallel Interview API Documentation

This document describes the new parallel interview endpoints that enable managing multiple concurrent interview sessions.

## Overview

The parallel interview API provides comprehensive endpoints for:
- Creating and managing multiple concurrent interview sessions
- Tracking session status and progress
- Managing LiveKit rooms for real-time communication
- Generating statistics and reports
- Full CRUD operations on interview sessions

## Base URL

All endpoints are prefixed with `/api/parallel_interview`

## Endpoints

### 1. Create Parallel Interview Session

**Endpoint:** `POST /api/parallel_interview/create`

Creates a new interview session with full initialization including LiveKit room and proctoring setup.

**Request Body:**
```json
{
  "name": "John Doe",
  "email": "john@example.com",
  "phone": "+1234567890",
  "job_id": "job_123",
  "questions": ["What is your experience with Python?", "Explain OOP concepts"],
  "question_types": ["text", "text"],
  "max_questions": 5,
  "text_question_timer": 120,
  "coding_question_timer": 300
}
```

**Parameters:**
- `name` (required): Candidate's full name
- `email` (required): Candidate's email address
- `phone` (optional): Candidate's phone number
- `job_id` (optional): ID of the job opening (if using predefined questions)
- `questions` (optional): Array of custom questions (required if job_id not provided)
- `question_types` (optional): Array of question types ("text" or "coding"), defaults to "text"
- `max_questions` (optional): Maximum number of questions to ask
- `text_question_timer` (optional): Timer for text questions in seconds (default: 120)
- `coding_question_timer` (optional): Timer for coding questions in seconds (default: 300)

**Response:**
```json
{
  "status": "success",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "livekit_room_name": "interview-550e8400-e29b-41d4-a716-446655440000",
  "livekit_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "livekit_url": "wss://your-livekit-server.com",
  "user_details": {
    "name": "John Doe",
    "email": "john@example.com",
    "phone": "+1234567890"
  },
  "interview_config": {
    "total_questions": 10,
    "max_questions": 5,
    "text_question_timer": 120,
    "coding_question_timer": 300,
    "question_types": ["text", "text", "coding", "text", "coding"]
  }
}
```

---

### 2. List All Sessions

**Endpoint:** `GET /api/parallel_interview/sessions`

Retrieves a paginated list of all interview sessions with optional filtering.

**Query Parameters:**
- `status` (optional): Filter by status ("initialized", "in_progress", "completed")
- `limit` (optional): Number of results per page (default: 50, max: 200)
- `offset` (optional): Pagination offset (default: 0)

**Example:**
```
GET /api/parallel_interview/sessions?status=in_progress&limit=20&offset=0
```

**Response:**
```json
{
  "status": "success",
  "sessions": [
    {
      "_id": "507f1f77bcf86cd799439011",
      "proctoring_session_id": "550e8400-e29b-41d4-a716-446655440000",
      "user_details": {
        "name": "John Doe",
        "email": "john@example.com",
        "phone": "+1234567890"
      },
      "status": "in_progress",
      "created_at": "2025-12-04T19:30:00Z",
      "job_id": "job_123",
      "job_title": "Senior Python Developer",
      "question_index": 3,
      "consent_received": true
    }
  ],
  "total": 45,
  "limit": 20,
  "offset": 0
}
```

---

### 3. Get Session Details

**Endpoint:** `GET /api/parallel_interview/session/{session_id}`

Retrieves detailed information about a specific interview session.

**Example:**
```
GET /api/parallel_interview/session/550e8400-e29b-41d4-a716-446655440000
```

**Response:**
```json
{
  "status": "success",
  "session": {
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "user_details": {
      "name": "John Doe",
      "email": "john@example.com",
      "phone": "+1234567890"
    },
    "is_active": true,
    "current_question_count": 3,
    "max_questions": 5,
    "consent_received": true,
    "reference_face_captured": true,
    "total_questions": 10,
    "current_question_index": 3,
    "average_score": 7.5,
    "proctoring_violations_count": 0
  },
  "interview_state": {
    "dialogue_length": 7,
    "evaluations_count": 3,
    "text_question_timer": 120,
    "coding_question_timer": 300
  },
  "livekit_room": {
    "name": "interview-550e8400-e29b-41d4-a716-446655440000",
    "num_participants": 2,
    "creation_time": 1701715800
  }
}
```

---

### 4. Start Interview Session

**Endpoint:** `POST /api/parallel_interview/session/{session_id}/start`

Activates an interview session, marking it as "in_progress".

**Example:**
```
POST /api/parallel_interview/session/550e8400-e29b-41d4-a716-446655440000/start
```

**Response:**
```json
{
  "status": "success",
  "message": "Interview session started",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "livekit_room_name": "interview-550e8400-e29b-41d4-a716-446655440000"
}
```

---

### 5. End Interview Session

**Endpoint:** `POST /api/parallel_interview/session/{session_id}/end`

Ends an interview session, generates the report, and cleans up resources.

**Example:**
```
POST /api/parallel_interview/session/550e8400-e29b-41d4-a716-446655440000/end
```

**Response:**
```json
{
  "status": "success",
  "message": "Interview session ended",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "report_available": true,
  "questions_answered": 5,
  "average_score": 8.2
}
```

---

### 6. Delete Interview Session

**Endpoint:** `DELETE /api/parallel_interview/session/{session_id}`

Permanently deletes an interview session and all associated data.

**Example:**
```
DELETE /api/parallel_interview/session/550e8400-e29b-41d4-a716-446655440000
```

**Response:**
```json
{
  "status": "success",
  "message": "Session deleted",
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

### 7. Get Statistics

**Endpoint:** `GET /api/parallel_interview/stats`

Retrieves overall statistics about all interview sessions.

**Example:**
```
GET /api/parallel_interview/stats
```

**Response:**
```json
{
  "status": "success",
  "stats": {
    "total_sessions": 150,
    "active_sessions": 8,
    "completed_sessions": 135,
    "initialized_sessions": 7,
    "in_memory_sessions": 15,
    "active_livekit_rooms": 8
  }
}
```

---

## Usage Examples

### Example 1: Create and Start an Interview

```python
import requests

# Step 1: Create session
response = requests.post('http://localhost:8005/api/parallel_interview/create', json={
    "name": "Jane Smith",
    "email": "jane@example.com",
    "phone": "+1234567890",
    "questions": [
        "Tell me about yourself",
        "What is your experience with Python?",
        "Write a function to reverse a string"
    ],
    "question_types": ["text", "text", "coding"],
    "max_questions": 3,
    "text_question_timer": 120,
    "coding_question_timer": 300
})

data = response.json()
session_id = data['session_id']
livekit_token = data['livekit_token']

# Step 2: Start the session
requests.post(f'http://localhost:8005/api/parallel_interview/session/{session_id}/start')

# Step 3: Connect to LiveKit room with the token
# (Client-side code would use the livekit_token to join the room)

# Step 4: End the session when complete
requests.post(f'http://localhost:8005/api/parallel_interview/session/{session_id}/end')
```

### Example 2: Monitor Active Sessions

```python
import requests

# Get all active sessions
response = requests.get('http://localhost:8005/api/parallel_interview/sessions?status=in_progress')
sessions = response.json()['sessions']

for session in sessions:
    session_id = session['proctoring_session_id']
    
    # Get detailed info for each session
    detail_response = requests.get(f'http://localhost:8005/api/parallel_interview/session/{session_id}')
    details = detail_response.json()
    
    print(f"Candidate: {details['session']['user_details']['name']}")
    print(f"Progress: {details['session']['current_question_count']}/{details['session']['max_questions']}")
    print(f"Average Score: {details['session']['average_score']}")
    print("---")
```

### Example 3: Bulk Session Management

```python
import requests

# Get statistics
stats_response = requests.get('http://localhost:8005/api/parallel_interview/stats')
stats = stats_response.json()['stats']

print(f"Total Sessions: {stats['total_sessions']}")
print(f"Active: {stats['active_sessions']}")
print(f"Completed: {stats['completed_sessions']}")

# Clean up old completed sessions
completed_sessions = requests.get(
    'http://localhost:8005/api/parallel_interview/sessions?status=completed&limit=100'
).json()['sessions']

for session in completed_sessions:
    session_id = session['proctoring_session_id']
    # Delete sessions older than 30 days
    # (Add your date logic here)
    requests.delete(f'http://localhost:8005/api/parallel_interview/session/{session_id}')
```

---

## Session States

Interview sessions can be in one of three states:

1. **initialized**: Session created but not yet started
2. **in_progress**: Interview is actively running
3. **completed**: Interview has ended

---

## Integration with Existing Endpoints

The parallel interview API works seamlessly with existing endpoints:

- **Face Capture**: Use `/capture_reference_face` with the session_id
- **WebSocket**: Connect to `/ws/interview?session_id={session_id}` for real-time communication
- **Reports**: Access reports via `/api/reports/{session_id}`
- **Proctoring**: Proctoring is automatically initialized for each session

---

## Error Handling

All endpoints return standard HTTP status codes:

- `200 OK`: Successful operation
- `400 Bad Request`: Invalid input parameters
- `404 Not Found`: Session not found
- `500 Internal Server Error`: Server error

Error responses include a detail message:

```json
{
  "detail": "Session 550e8400-e29b-41d4-a716-446655440000 not found"
}
```

---

## Best Practices

1. **Session Cleanup**: Always call the `/end` endpoint when an interview is complete to free up resources
2. **Error Handling**: Implement retry logic for network failures
3. **Monitoring**: Regularly check `/stats` endpoint to monitor system health
4. **Pagination**: Use appropriate `limit` and `offset` values when listing sessions
5. **LiveKit Integration**: Store the `livekit_token` securely on the client side

---

## Notes

- Each session gets a unique UUID as `session_id`
- LiveKit rooms are automatically created and cleaned up
- Proctoring sessions are automatically initialized
- All session data is persisted in MongoDB for multi-worker support
- Sessions are stored both in-memory and in MongoDB for performance and reliability
