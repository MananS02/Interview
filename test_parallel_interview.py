#!/usr/bin/env python3
"""
Test script for Parallel Interview API endpoints
Demonstrates how to create, manage, and monitor parallel interview sessions
"""

import requests
import json
import time
from typing import Dict, List

# Configuration - Using localhost explicitly
BASE_URL = "http://localhost:8005"
API_BASE = f"{BASE_URL}/api/parallel_interview"



def create_interview_session(name: str, email: str, questions: List[str], question_types: List[str] = None) -> Dict:
    """Create a new parallel interview session"""
    print(f"\n📝 Creating interview session for {name}...")
    
    payload = {
        "name": name,
        "email": email,
        "phone": "+1234567890",
        "questions": questions,
        "question_types": question_types or ["text"] * len(questions),
        "max_questions": len(questions),
        "text_question_timer": 120,
        "coding_question_timer": 300
    }
    
    response = requests.post(f"{API_BASE}/create", json=payload)
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Session created successfully!")
        print(f"   Session ID: {data['session_id']}")
        print(f"   LiveKit Room: {data.get('livekit_room_name', 'N/A')}")
        print(f"   Total Questions: {data['interview_config']['total_questions']}")
        return data
    else:
        print(f"❌ Failed to create session: {response.text}")
        return None


def start_session(session_id: str) -> bool:
    """Start an interview session"""
    print(f"\n▶️  Starting session {session_id[:8]}...")
    
    response = requests.post(f"{API_BASE}/session/{session_id}/start")
    
    if response.status_code == 200:
        print(f"✅ Session started successfully!")
        return True
    else:
        print(f"❌ Failed to start session: {response.text}")
        return False


def get_session_details(session_id: str) -> Dict:
    """Get detailed information about a session"""
    print(f"\n🔍 Fetching details for session {session_id[:8]}...")
    
    response = requests.get(f"{API_BASE}/session/{session_id}")
    
    if response.status_code == 200:
        data = response.json()
        session = data['session']
        print(f"✅ Session details:")
        print(f"   Candidate: {session['user_details']['name']}")
        print(f"   Status: {'Active' if session['is_active'] else 'Inactive'}")
        print(f"   Progress: {session['current_question_count']}/{session['max_questions']}")
        print(f"   Average Score: {session['average_score']:.1f}")
        print(f"   Violations: {session['proctoring_violations_count']}")
        return data
    else:
        print(f"❌ Failed to get session details: {response.text}")
        return None


def list_sessions(status: str = None, limit: int = 10) -> List[Dict]:
    """List all interview sessions"""
    print(f"\n📋 Listing sessions (status={status or 'all'}, limit={limit})...")
    
    params = {"limit": limit}
    if status:
        params["status"] = status
    
    response = requests.get(f"{API_BASE}/sessions", params=params)
    
    if response.status_code == 200:
        data = response.json()
        sessions = data['sessions']
        print(f"✅ Found {data['total']} total sessions, showing {len(sessions)}:")
        
        for i, session in enumerate(sessions, 1):
            user = session.get('user_details', {})
            print(f"   {i}. {user.get('name', 'Unknown')} - {session.get('status', 'unknown')} - {session.get('proctoring_session_id', '')[:8]}")
        
        return sessions
    else:
        print(f"❌ Failed to list sessions: {response.text}")
        return []


def get_stats() -> Dict:
    """Get overall statistics"""
    print(f"\n📊 Fetching statistics...")
    
    response = requests.get(f"{API_BASE}/stats")
    
    if response.status_code == 200:
        data = response.json()
        stats = data['stats']
        print(f"✅ Statistics:")
        print(f"   Total Sessions: {stats['total_sessions']}")
        print(f"   Active: {stats['active_sessions']}")
        print(f"   Completed: {stats['completed_sessions']}")
        print(f"   Initialized: {stats['initialized_sessions']}")
        print(f"   In Memory: {stats['in_memory_sessions']}")
        print(f"   LiveKit Rooms: {stats['active_livekit_rooms']}")
        return stats
    else:
        print(f"❌ Failed to get statistics: {response.text}")
        return None


def end_session(session_id: str) -> bool:
    """End an interview session"""
    print(f"\n⏹️  Ending session {session_id[:8]}...")
    
    response = requests.post(f"{API_BASE}/session/{session_id}/end")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Session ended successfully!")
        print(f"   Questions Answered: {data['questions_answered']}")
        print(f"   Average Score: {data['average_score']:.1f}")
        print(f"   Report Available: {data['report_available']}")
        return True
    else:
        print(f"❌ Failed to end session: {response.text}")
        return False


def delete_session(session_id: str) -> bool:
    """Delete an interview session"""
    print(f"\n🗑️  Deleting session {session_id[:8]}...")
    
    response = requests.delete(f"{API_BASE}/session/{session_id}")
    
    if response.status_code == 200:
        print(f"✅ Session deleted successfully!")
        return True
    else:
        print(f"❌ Failed to delete session: {response.text}")
        return False


def test_parallel_interviews():
    """Test creating multiple parallel interview sessions"""
    print("\n" + "="*60)
    print("🚀 Testing Parallel Interview API")
    print("="*60)
    
    # Test 1: Get initial statistics
    print("\n--- Test 1: Initial Statistics ---")
    get_stats()
    
    # Test 2: Create multiple sessions
    print("\n--- Test 2: Creating Multiple Sessions ---")
    
    candidates = [
        {
            "name": "Alice Johnson",
            "email": "alice@example.com",
            "questions": [
                "Tell me about your experience with Python",
                "What is your understanding of REST APIs?",
                "Write a function to find duplicates in a list"
            ],
            "question_types": ["text", "text", "coding"]
        },
        {
            "name": "Bob Smith",
            "email": "bob@example.com",
            "questions": [
                "Describe your experience with databases",
                "What is normalization?",
                "Write a SQL query to join two tables"
            ],
            "question_types": ["text", "text", "coding"]
        },
        {
            "name": "Carol Williams",
            "email": "carol@example.com",
            "questions": [
                "What is your experience with JavaScript?",
                "Explain async/await",
                "Write a promise-based function"
            ],
            "question_types": ["text", "text", "coding"]
        }
    ]
    
    session_ids = []
    for candidate in candidates:
        result = create_interview_session(
            name=candidate["name"],
            email=candidate["email"],
            questions=candidate["questions"],
            question_types=candidate["question_types"]
        )
        if result:
            session_ids.append(result['session_id'])
        time.sleep(0.5)  # Small delay between requests
    
    # Test 3: Start sessions
    print("\n--- Test 3: Starting Sessions ---")
    for session_id in session_ids:
        start_session(session_id)
        time.sleep(0.3)
    
    # Test 4: Get session details
    print("\n--- Test 4: Session Details ---")
    for session_id in session_ids:
        get_session_details(session_id)
        time.sleep(0.3)
    
    # Test 5: List all active sessions
    print("\n--- Test 5: List Active Sessions ---")
    list_sessions(status="in_progress")
    
    # Test 6: Get updated statistics
    print("\n--- Test 6: Updated Statistics ---")
    get_stats()
    
    # Test 7: End first session
    if session_ids:
        print("\n--- Test 7: Ending First Session ---")
        end_session(session_ids[0])
    
    # Test 8: List all sessions
    print("\n--- Test 8: List All Sessions ---")
    list_sessions(limit=20)
    
    # Test 9: Delete a session (optional - uncomment to test)
    # if session_ids:
    #     print("\n--- Test 9: Deleting Session ---")
    #     delete_session(session_ids[0])
    
    print("\n" + "="*60)
    print("✅ All tests completed!")
    print("="*60)
    
    return session_ids


def interactive_menu():
    """Interactive menu for testing the API"""
    while True:
        print("\n" + "="*60)
        print("Parallel Interview API - Interactive Menu")
        print("="*60)
        print("1. Create new session")
        print("2. List all sessions")
        print("3. Get session details")
        print("4. Start session")
        print("5. End session")
        print("6. Delete session")
        print("7. Get statistics")
        print("8. Run automated tests")
        print("0. Exit")
        print("="*60)
        
        choice = input("\nEnter your choice: ").strip()
        
        if choice == "1":
            name = input("Enter candidate name: ")
            email = input("Enter candidate email: ")
            questions_str = input("Enter questions (comma-separated): ")
            questions = [q.strip() for q in questions_str.split(",")]
            create_interview_session(name, email, questions)
        
        elif choice == "2":
            status = input("Filter by status (initialized/in_progress/completed, or press Enter for all): ").strip()
            list_sessions(status=status if status else None)
        
        elif choice == "3":
            session_id = input("Enter session ID: ").strip()
            get_session_details(session_id)
        
        elif choice == "4":
            session_id = input("Enter session ID: ").strip()
            start_session(session_id)
        
        elif choice == "5":
            session_id = input("Enter session ID: ").strip()
            end_session(session_id)
        
        elif choice == "6":
            session_id = input("Enter session ID: ").strip()
            confirm = input("Are you sure you want to delete this session? (yes/no): ").strip().lower()
            if confirm == "yes":
                delete_session(session_id)
        
        elif choice == "7":
            get_stats()
        
        elif choice == "8":
            test_parallel_interviews()
        
        elif choice == "0":
            print("\n👋 Goodbye!")
            break
        
        else:
            print("❌ Invalid choice. Please try again.")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # Run automated tests
        test_parallel_interviews()
    else:
        # Run interactive menu
        interactive_menu()
