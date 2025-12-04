# Parallel Interview Architecture

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLIENT APPLICATION                          │
│  (Frontend - React/Vue/etc or API Consumer)                        │
└────────────┬────────────────────────────────────────────────────────┘
             │
             │ HTTP/REST API Calls
             │
             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    PARALLEL INTERVIEW API                           │
│                    (FastAPI Endpoints)                              │
│                                                                     │
│  POST   /api/parallel_interview/create                             │
│  GET    /api/parallel_interview/sessions                           │
│  GET    /api/parallel_interview/session/{id}                       │
│  POST   /api/parallel_interview/session/{id}/start                 │
│  POST   /api/parallel_interview/session/{id}/end                   │
│  DELETE /api/parallel_interview/session/{id}                       │
│  GET    /api/parallel_interview/stats                              │
└────┬────────────┬─────────────┬──────────────┬──────────────────────┘
     │            │             │              │
     │            │             │              │
     ▼            ▼             ▼              ▼
┌─────────┐  ┌──────────┐  ┌─────────┐  ┌──────────────┐
│ MongoDB │  │ LiveKit  │  │Proctoring│  │ In-Memory   │
│         │  │ Manager  │  │ Service  │  │ State Store │
│Sessions │  │          │  │          │  │             │
│Reports  │  │Rooms     │  │Face      │  │interview_   │
│         │  │Tokens    │  │Detection │  │states{}     │
└─────────┘  └──────────┘  └─────────┘  └──────────────┘
```

## Data Flow: Creating a Parallel Interview

```
1. CLIENT REQUEST
   ↓
   POST /api/parallel_interview/create
   {
     "name": "John Doe",
     "email": "john@example.com",
     "questions": ["Q1", "Q2", "Q3"]
   }

2. API PROCESSING
   ↓
   ├─→ Generate UUID session_id
   ├─→ Create InterviewState object
   ├─→ Parse questions and configuration
   └─→ Store in interview_states[session_id]

3. EXTERNAL SERVICES
   ↓
   ├─→ MongoDB: Save session_data
   ├─→ LiveKit: Create room "interview-{session_id}"
   ├─→ LiveKit: Generate access token
   └─→ Proctoring: Initialize session

4. RESPONSE
   ↓
   {
     "status": "success",
     "session_id": "uuid",
     "livekit_room_name": "interview-uuid",
     "livekit_token": "token...",
     "livekit_url": "wss://...",
     "user_details": {...},
     "interview_config": {...}
   }
```

## Session Lifecycle

```
┌──────────────┐
│ INITIALIZED  │  ← POST /create
└──────┬───────┘
       │
       │ POST /session/{id}/start
       ▼
┌──────────────┐
│ IN_PROGRESS  │  ← Interview active
└──────┬───────┘    Questions asked
       │            Answers evaluated
       │            Proctoring active
       │
       │ POST /session/{id}/end
       ▼
┌──────────────┐
│  COMPLETED   │  ← Report generated
└──────┬───────┘    LiveKit room deleted
       │
       │ DELETE /session/{id} (optional)
       ▼
┌──────────────┐
│   DELETED    │  ← All data removed
└──────────────┘
```

## Parallel Session Management

```
┌─────────────────────────────────────────────────────────────┐
│                    INTERVIEW PLATFORM                        │
│                                                              │
│  Session 1: Alice    [IN_PROGRESS] ████████░░ 80%          │
│  Session 2: Bob      [IN_PROGRESS] ████░░░░░░ 40%          │
│  Session 3: Carol    [INITIALIZED] ░░░░░░░░░░  0%          │
│  Session 4: Dave     [COMPLETED]   ██████████ 100%         │
│  Session 5: Eve      [IN_PROGRESS] ██████░░░░ 60%          │
│                                                              │
│  Active Sessions: 3                                          │
│  Total Sessions: 5                                           │
│  LiveKit Rooms: 3                                            │
└─────────────────────────────────────────────────────────────┘
```

## Component Interactions

```
┌──────────────────────────────────────────────────────────────┐
│                    PARALLEL INTERVIEW API                     │
└──────────────┬──────────────┬──────────────┬─────────────────┘
               │              │              │
               ▼              ▼              ▼
        ┌─────────────┐ ┌──────────┐ ┌─────────────┐
        │  Interview  │ │ LiveKit  │ │ Proctoring  │
        │   State     │ │ Manager  │ │  Service    │
        │  Manager    │ │          │ │             │
        └──────┬──────┘ └────┬─────┘ └──────┬──────┘
               │             │               │
               ▼             ▼               ▼
        ┌─────────────────────────────────────────┐
        │              MongoDB                     │
        │  ┌──────────┐ ┌──────────┐ ┌──────────┐│
        │  │ Sessions │ │ Reports  │ │ Violations││
        │  └──────────┘ └──────────┘ └──────────┘│
        └─────────────────────────────────────────┘
```

## Request/Response Flow

```
CLIENT                  API                 SERVICES
  │                      │                      │
  ├─── POST /create ────→│                      │
  │                      ├─── save_session ────→│ MongoDB
  │                      ├─── create_room ─────→│ LiveKit
  │                      ├─── init_session ────→│ Proctoring
  │                      │                      │
  │←──── session_id ─────┤                      │
  │      + token         │                      │
  │                      │                      │
  ├─── POST /start ─────→│                      │
  │                      ├─── update_status ───→│ MongoDB
  │←──── success ────────┤                      │
  │                      │                      │
  │  (Interview happens via WebSocket/LiveKit)  │
  │                      │                      │
  ├─── POST /end ───────→│                      │
  │                      ├─── generate_report ─→│ Background
  │                      ├─── delete_room ─────→│ LiveKit
  │                      ├─── update_status ───→│ MongoDB
  │←──── report_info ────┤                      │
  │                      │                      │
```

## Monitoring Dashboard Flow

```
┌─────────────────────────────────────────────────────────┐
│              ADMIN MONITORING DASHBOARD                  │
└────────────────────┬────────────────────────────────────┘
                     │
                     │ GET /api/parallel_interview/stats
                     ▼
              ┌─────────────┐
              │   API       │
              │   Stats     │
              │  Endpoint   │
              └──────┬──────┘
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
   ┌─────────┐ ┌─────────┐ ┌──────────┐
   │ MongoDB │ │ Memory  │ │ LiveKit  │
   │ Counts  │ │ States  │ │  Rooms   │
   └─────────┘ └─────────┘ └──────────┘
        │            │            │
        └────────────┴────────────┘
                     │
                     ▼
              ┌─────────────┐
              │ Aggregated  │
              │ Statistics  │
              └─────────────┘
                     │
                     ▼
              ┌─────────────┐
              │   JSON      │
              │  Response   │
              └─────────────┘
```

## Scalability Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    LOAD BALANCER                          │
└────────┬──────────────┬──────────────┬───────────────────┘
         │              │              │
         ▼              ▼              ▼
    ┌────────┐     ┌────────┐     ┌────────┐
    │Worker 1│     │Worker 2│     │Worker 3│
    │        │     │        │     │        │
    │FastAPI │     │FastAPI │     │FastAPI │
    └────┬───┘     └────┬───┘     └────┬───┘
         │              │              │
         └──────────────┴──────────────┘
                        │
                        ▼
         ┌──────────────────────────────┐
         │      Shared MongoDB          │
         │  (Session Persistence)       │
         └──────────────────────────────┘
                        │
         ┌──────────────┴──────────────┐
         │                             │
         ▼                             ▼
    ┌─────────┐                  ┌──────────┐
    │LiveKit  │                  │Proctoring│
    │ Server  │                  │ Service  │
    └─────────┘                  └──────────┘
```

## Key Design Principles

1. **Stateless API**: All state stored in MongoDB for multi-worker support
2. **Session Isolation**: Each interview has unique session_id
3. **Resource Management**: Automatic cleanup of LiveKit rooms
4. **Error Resilience**: Fallback modes when services fail
5. **Monitoring**: Real-time statistics for system health
6. **Scalability**: Horizontal scaling via shared MongoDB

## Performance Considerations

- **In-Memory Cache**: Active sessions cached for fast access
- **Async Operations**: Non-blocking I/O for all database operations
- **Background Tasks**: Report generation doesn't block responses
- **Connection Pooling**: MongoDB connection pool for efficiency
- **Pagination**: Limit result sets to prevent memory issues
