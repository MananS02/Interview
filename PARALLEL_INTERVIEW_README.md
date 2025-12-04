# 🎯 Parallel Interview API - Complete Guide

## Overview

A comprehensive REST API for managing multiple concurrent interview sessions with LiveKit integration, proctoring, and MongoDB persistence.

## 🚀 Quick Start

### 1. Test the API
```bash
# Get current statistics
curl http://localhost:8005/api/parallel_interview/stats | python3 -m json.tool

# Create a new session
curl -X POST http://localhost:8005/api/parallel_interview/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "email": "john@example.com",
    "questions": ["Q1", "Q2", "Q3"]
  }' | python3 -m json.tool
```

### 2. Run Automated Tests
```bash
python test_parallel_interview.py --test
```

### 3. Interactive Testing
```bash
python test_parallel_interview.py
```

## 📚 Documentation Files

| File | Description |
|------|-------------|
| `PARALLEL_INTERVIEW_API.md` | Complete API documentation with examples |
| `PARALLEL_INTERVIEW_QUICK_REF.md` | Quick reference guide |
| `PARALLEL_INTERVIEW_ARCHITECTURE.md` | System architecture and diagrams |
| `PARALLEL_INTERVIEW_SUMMARY.md` | Implementation summary |
| `test_parallel_interview.py` | Test script with automated tests |
| `Parallel_Interview_API.postman_collection.json` | Postman collection |

## 🔗 API Endpoints

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/parallel_interview/create` | Create new session |
| GET | `/api/parallel_interview/sessions` | List all sessions |
| GET | `/api/parallel_interview/session/{id}` | Get session details |
| POST | `/api/parallel_interview/session/{id}/start` | Start session |
| POST | `/api/parallel_interview/session/{id}/end` | End session |
| DELETE | `/api/parallel_interview/session/{id}` | Delete session |
| GET | `/api/parallel_interview/stats` | Get statistics |

## 💡 Usage Examples

### Python
```python
import requests

# Create session
response = requests.post('http://localhost:8005/api/parallel_interview/create', json={
    "name": "Jane Doe",
    "email": "jane@example.com",
    "questions": ["Q1", "Q2", "Q3"],
    "question_types": ["text", "text", "coding"]
})

session_id = response.json()['session_id']

# Start session
requests.post(f'http://localhost:8005/api/parallel_interview/session/{session_id}/start')

# Get details
details = requests.get(f'http://localhost:8005/api/parallel_interview/session/{session_id}').json()
print(f"Progress: {details['session']['current_question_count']}/{details['session']['max_questions']}")

# End session
requests.post(f'http://localhost:8005/api/parallel_interview/session/{session_id}/end')
```

### cURL
```bash
# Create session
SESSION_ID=$(curl -s -X POST http://localhost:8005/api/parallel_interview/create \
  -H "Content-Type: application/json" \
  -d '{"name":"Test","email":"test@example.com","questions":["Q1","Q2"]}' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['session_id'])")

# Start session
curl -X POST http://localhost:8005/api/parallel_interview/session/$SESSION_ID/start

# Get details
curl http://localhost:8005/api/parallel_interview/session/$SESSION_ID

# End session
curl -X POST http://localhost:8005/api/parallel_interview/session/$SESSION_ID/end
```

### JavaScript/Node.js
```javascript
const axios = require('axios');

async function createAndStartInterview() {
  // Create session
  const createResponse = await axios.post('http://localhost:8005/api/parallel_interview/create', {
    name: 'John Doe',
    email: 'john@example.com',
    questions: ['Q1', 'Q2', 'Q3'],
    question_types: ['text', 'text', 'coding']
  });
  
  const sessionId = createResponse.data.session_id;
  
  // Start session
  await axios.post(`http://localhost:8005/api/parallel_interview/session/${sessionId}/start`);
  
  // Get details
  const details = await axios.get(`http://localhost:8005/api/parallel_interview/session/${sessionId}`);
  console.log('Session details:', details.data);
  
  return sessionId;
}
```

## 🧪 Testing

### Using the Test Script

**Automated Tests:**
```bash
python test_parallel_interview.py --test
```

**Interactive Menu:**
```bash
python test_parallel_interview.py
```

### Using Postman

1. Import `Parallel_Interview_API.postman_collection.json`
2. Set the `base_url` variable to `http://localhost:8005`
3. Run the requests in order

### Manual Testing

```bash
# 1. Get statistics
curl http://localhost:8005/api/parallel_interview/stats

# 2. Create session
curl -X POST http://localhost:8005/api/parallel_interview/create \
  -H "Content-Type: application/json" \
  -d '{"name":"Test","email":"test@example.com","questions":["Q1","Q2"]}'

# 3. List sessions
curl "http://localhost:8005/api/parallel_interview/sessions?limit=5"

# 4. Get session details (replace SESSION_ID)
curl http://localhost:8005/api/parallel_interview/session/SESSION_ID

# 5. Start session
curl -X POST http://localhost:8005/api/parallel_interview/session/SESSION_ID/start

# 6. End session
curl -X POST http://localhost:8005/api/parallel_interview/session/SESSION_ID/end
```

## 📊 Monitoring

### Get Real-time Statistics
```python
import requests
import time

while True:
    stats = requests.get('http://localhost:8005/api/parallel_interview/stats').json()['stats']
    print(f"\rActive: {stats['active_sessions']} | "
          f"Completed: {stats['completed_sessions']} | "
          f"Total: {stats['total_sessions']}", end='')
    time.sleep(5)
```

### List Active Sessions
```bash
curl "http://localhost:8005/api/parallel_interview/sessions?status=in_progress&limit=20"
```

## 🎯 Key Features

✅ **Parallel Sessions** - Handle multiple interviews simultaneously  
✅ **LiveKit Integration** - Automatic room creation and token generation  
✅ **MongoDB Persistence** - All sessions stored for reliability  
✅ **Proctoring** - Automatic proctoring session initialization  
✅ **Statistics** - Real-time monitoring and analytics  
✅ **Full CRUD** - Complete lifecycle management  
✅ **Error Handling** - Comprehensive error responses  
✅ **Scalability** - Designed for horizontal scaling  

## 🔧 Configuration

### Request Parameters

**Create Session:**
- `name` (required): Candidate's name
- `email` (required): Candidate's email
- `phone` (optional): Phone number
- `job_id` (optional): Use predefined job questions
- `questions` (optional): Custom questions array
- `question_types` (optional): Array of "text" or "coding"
- `max_questions` (optional): Limit number of questions
- `text_question_timer` (optional): Timer in seconds (default: 120)
- `coding_question_timer` (optional): Timer in seconds (default: 300)

### Response Format

All endpoints return JSON with a `status` field:
```json
{
  "status": "success",
  "data": {...}
}
```

Errors include a `detail` field:
```json
{
  "detail": "Error message"
}
```

## 🏗️ Architecture

```
Client → API Endpoints → Services (LiveKit, Proctoring) → MongoDB
                      ↓
              In-Memory State Cache
```

See `PARALLEL_INTERVIEW_ARCHITECTURE.md` for detailed diagrams.

## 📝 Session States

1. **initialized** - Session created but not started
2. **in_progress** - Interview is active
3. **completed** - Interview ended, report generated

## 🔗 Integration

### With Existing Endpoints
- Face Capture: `/capture_reference_face`
- WebSocket: `/ws/interview?session_id={id}`
- Reports: `/api/reports/{id}`

### With LiveKit
- Room: `interview-{session_id}`
- Participant: `candidate-{session_id}`
- Token TTL: 1 hour

## 🚨 Error Handling

All endpoints return appropriate HTTP status codes:
- `200 OK` - Success
- `400 Bad Request` - Invalid input
- `404 Not Found` - Session not found
- `500 Internal Server Error` - Server error

## 📈 Performance

- **In-Memory Cache**: Fast access to active sessions
- **Async Operations**: Non-blocking database operations
- **Background Tasks**: Report generation doesn't block
- **Connection Pooling**: Efficient database connections
- **Pagination**: Prevents memory issues with large datasets

## 🎓 Best Practices

1. Always call `/end` endpoint when interview completes
2. Use pagination when listing many sessions
3. Monitor `/stats` endpoint for system health
4. Store `session_id` securely on client side
5. Handle LiveKit failures gracefully
6. Clean up old completed sessions periodically

## 🆘 Troubleshooting

**LiveKit room creation fails:**
- Check LiveKit server is running
- Verify credentials in `.env`
- API provides fallback mode

**Session not found:**
- Verify session_id is correct
- Check if session was deleted
- Session may have expired

**MongoDB errors:**
- Verify MongoDB is running
- Check connection string in `.env`
- Ensure collections exist

## 📞 Support

For issues or questions:
1. Check the documentation files
2. Review the test script examples
3. Examine the Postman collection
4. Check server logs for errors

## 🎉 Success!

Your parallel interview API is ready to use! Start by running the test script:

```bash
python test_parallel_interview.py --test
```

Then explore the documentation and integrate with your frontend application.

---

**Created:** December 2025  
**Status:** ✅ Production Ready  
**Version:** 1.0.0
