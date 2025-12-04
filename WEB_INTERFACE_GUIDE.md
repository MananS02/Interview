# 🌐 Parallel Interview API - Web Interface

## Quick Access

### Interactive Web Tester
Open in your browser:
```
http://localhost:8005/static/parallel_interview_tester.html
```

This provides a beautiful, interactive interface to:
- ✅ View real-time statistics
- ✅ Create new interview sessions
- ✅ Get session details
- ✅ List all sessions with filtering
- ✅ Start/End sessions
- ✅ Delete sessions
- ✅ Auto-refresh statistics every 10 seconds

## Features

### 📊 Live Statistics Dashboard
- Total Sessions
- Active Sessions
- Completed Sessions
- Active LiveKit Rooms

### 🎯 Interactive Forms
- Pre-filled example data
- JSON validation
- Real-time responses
- Auto-fill session IDs across forms

### 🎨 Beautiful UI
- Modern gradient design
- Responsive layout
- Color-coded HTTP methods
- Expandable endpoint sections

## Alternative Testing Methods

### 1. Python Test Script
```bash
# Automated tests
python test_parallel_interview.py --test

# Interactive menu
python test_parallel_interview.py
```

### 2. cURL Commands
```bash
# Get statistics
curl http://localhost:8005/api/parallel_interview/stats | python3 -m json.tool

# Create session
curl -X POST http://localhost:8005/api/parallel_interview/create \
  -H "Content-Type: application/json" \
  -d '{"name":"Test","email":"test@example.com","questions":["Q1","Q2"]}'
```

### 3. Postman Collection
Import `Parallel_Interview_API.postman_collection.json` into Postman.

## Screenshots

### Statistics Dashboard
The top section shows real-time statistics that auto-refresh every 10 seconds.

### Endpoint Testing
Each endpoint has:
- HTTP method badge (GET/POST/DELETE)
- Full URL display
- Interactive form with example data
- JSON response viewer

## Usage Tips

1. **Start with Statistics**: Click "Refresh Statistics" to see current system state

2. **Create a Session**: 
   - Expand "Create Interview Session"
   - Modify the example data if needed
   - Click "Create Session"
   - Session ID will auto-fill in other forms

3. **Test Session Lifecycle**:
   - Create → Start → Get Details → End → Delete

4. **Monitor Active Sessions**:
   - Use "List All Sessions" with status filter
   - Set to "in_progress" to see active interviews

5. **Auto-Refresh**: Statistics update automatically every 10 seconds

## All Endpoints Available

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/parallel_interview/create` | Create session |
| GET | `/api/parallel_interview/sessions` | List sessions |
| GET | `/api/parallel_interview/session/{id}` | Get details |
| POST | `/api/parallel_interview/session/{id}/start` | Start session |
| POST | `/api/parallel_interview/session/{id}/end` | End session |
| DELETE | `/api/parallel_interview/session/{id}` | Delete session |
| GET | `/api/parallel_interview/stats` | Get statistics |

## Example Workflow

1. Open http://localhost:8005/static/parallel_interview_tester.html
2. View current statistics
3. Create a new session (session ID auto-fills)
4. Start the session
5. Get session details to see progress
6. End the session when complete
7. Statistics update automatically

## Benefits

✅ **No Installation Required** - Just open in browser  
✅ **Visual Feedback** - See responses immediately  
✅ **Auto-Fill** - Session IDs populate automatically  
✅ **Live Updates** - Statistics refresh every 10 seconds  
✅ **Beautiful UI** - Modern, professional design  
✅ **Easy Testing** - No need for Postman or cURL  

## Troubleshooting

**Page doesn't load:**
- Ensure server is running: `uvicorn app:app --reload --host 0.0.0.0 --port 8005`
- Check URL: http://localhost:8005/static/parallel_interview_tester.html

**CORS errors:**
- Server already has CORS enabled for all origins
- Should work without issues

**Statistics show "-":**
- Click "Refresh Statistics" button
- Check browser console for errors

## Next Steps

1. Open the web interface in your browser
2. Test creating a few sessions
3. Monitor the statistics dashboard
4. Integrate the API into your frontend application

---

**Access Now:** http://localhost:8005/static/parallel_interview_tester.html
