# Parallel Interview API - Quick Reference

## Quick Start

### 1. Create a Session
```bash
curl -X POST http://localhost:8005/api/parallel_interview/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "email": "john@example.com",
    "questions": ["Question 1", "Question 2"],
    "question_types": ["text", "coding"]
  }'
```

### 2. Start the Session
```bash
curl -X POST http://localhost:8005/api/parallel_interview/session/{SESSION_ID}/start
```

### 3. Get Session Details
```bash
curl http://localhost:8005/api/parallel_interview/session/{SESSION_ID}
```

### 4. End the Session
```bash
curl -X POST http://localhost:8005/api/parallel_interview/session/{SESSION_ID}/end
```

---

## All Endpoints Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/parallel_interview/create` | Create new session |
| GET | `/api/parallel_interview/sessions` | List all sessions |
| GET | `/api/parallel_interview/session/{id}` | Get session details |
| POST | `/api/parallel_interview/session/{id}/start` | Start session |
| POST | `/api/parallel_interview/session/{id}/end` | End session |
| DELETE | `/api/parallel_interview/session/{id}` | Delete session |
| GET | `/api/parallel_interview/stats` | Get statistics |

---

## Using the Test Script

### Run Automated Tests
```bash
python test_parallel_interview.py --test
```

### Run Interactive Menu
```bash
python test_parallel_interview.py
```

---

## Key Features

✅ **Parallel Sessions**: Run multiple interviews simultaneously
✅ **LiveKit Integration**: Automatic room creation and token generation
✅ **Proctoring**: Automatic proctoring session initialization
✅ **MongoDB Persistence**: All sessions stored for multi-worker support
✅ **Statistics**: Real-time monitoring of all sessions
✅ **Full CRUD**: Complete lifecycle management

---

## Session Lifecycle

```
1. CREATE    → Session initialized, LiveKit room created
2. START     → Interview becomes active
3. CONDUCT   → Questions asked, answers evaluated
4. END       → Report generated, resources cleaned up
5. DELETE    → (Optional) Permanent removal
```

---

## Integration Points

### With Existing Endpoints
- **Face Capture**: `/capture_reference_face`
- **WebSocket**: `/ws/interview?session_id={id}`
- **Reports**: `/api/reports/{id}`
- **Proctoring**: Automatic via `proctoring_service`

### With LiveKit
- Room name: `interview-{session_id}`
- Participant: `candidate-{session_id}`
- Token TTL: 1 hour (3600 seconds)

---

## Common Use Cases

### 1. Batch Interview Creation
```python
import requests

candidates = [
    {"name": "Alice", "email": "alice@example.com"},
    {"name": "Bob", "email": "bob@example.com"},
]

questions = ["Q1", "Q2", "Q3"]

for candidate in candidates:
    requests.post('http://localhost:8005/api/parallel_interview/create', json={
        "name": candidate["name"],
        "email": candidate["email"],
        "questions": questions
    })
```

### 2. Monitor Active Interviews
```python
import requests

response = requests.get(
    'http://localhost:8005/api/parallel_interview/sessions?status=in_progress'
)

for session in response.json()['sessions']:
    print(f"{session['user_details']['name']} - Question {session['question_index']}")
```

### 3. Auto-cleanup Completed Sessions
```python
import requests
from datetime import datetime, timedelta

# Get completed sessions
response = requests.get(
    'http://localhost:8005/api/parallel_interview/sessions?status=completed'
)

# Delete sessions older than 7 days
cutoff = datetime.now() - timedelta(days=7)

for session in response.json()['sessions']:
    created = datetime.fromisoformat(session['created_at'])
    if created < cutoff:
        requests.delete(
            f'http://localhost:8005/api/parallel_interview/session/{session["proctoring_session_id"]}'
        )
```

---

## Error Codes

| Code | Meaning | Common Causes |
|------|---------|---------------|
| 400 | Bad Request | Missing required fields, invalid data |
| 404 | Not Found | Session doesn't exist |
| 500 | Server Error | Database error, LiveKit error |

---

## Tips & Best Practices

1. **Always end sessions** to free up LiveKit rooms and resources
2. **Use pagination** when listing many sessions
3. **Monitor stats** regularly to track system health
4. **Store session_id** on client side for reconnection
5. **Handle LiveKit failures** gracefully (API provides fallback)

---

## Monitoring Dashboard Example

```python
import requests
import time

while True:
    stats = requests.get('http://localhost:8005/api/parallel_interview/stats').json()['stats']
    
    print(f"\r Active: {stats['active_sessions']} | "
          f"Completed: {stats['completed_sessions']} | "
          f"Total: {stats['total_sessions']}", end='')
    
    time.sleep(5)
```

---

## Questions?

For detailed documentation, see: `PARALLEL_INTERVIEW_API.md`
For testing, run: `python test_parallel_interview.py`
