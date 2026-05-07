# AI Interview Platform: Comprehensive Architecture & Analysis Report

## 1. System Overview

The AI Interview Platform is a full-stack, real-time application designed to conduct, monitor, and evaluate automated interviews. It features a decoupled architecture where a static frontend communicates with a Python-based backend via REST APIs and WebSockets. The system supports live video streaming, real-time proctoring (integrity monitoring), AI-driven question generation, automated answer evaluation, and coding rounds.

The platform has recently undergone significant architectural upgrades to improve performance and reliability, notably migrating from HTTP polling to WebSockets for live streaming and from local file storage to Cloudinary for persistent video storage.

## 2. Full System Architecture Analysis

### 2.1 Frontend Architecture
The frontend is built as a Single Page Application (SPA) using vanilla HTML5, CSS3, and JavaScript (ES6+), served statically via Vercel.
*   **Candidate Interface (`forenten/index.html`)**: Manages the interview lifecycle, captures media via `MediaRecorder.js`, handles browser-based speech recognition, and streams live video frames and metadata via Socket.IO.
*   **Admin Dashboard (`forenten/admin.html`)**: Provides authentication, session management, and a real-time monitoring dashboard that consumes WebSocket events to display live candidate feeds and integrity alerts.
*   **Configuration (`forenten/config.js`)**: Manages environment-specific API base URLs.

### 2.2 Backend Architecture
The backend is a monolithic FastAPI application deployed on Render.
*   **Core Application (`backend/uploded.py`)**: The primary entry point containing REST endpoints, WebSocket event handlers, and business logic for session management, AI evaluation, and report generation.
*   **WebSocket Server**: Integrated using `python-socketio` (ASGI mode) alongside FastAPI to handle low-latency bidirectional communication.
*   **AI Pipeline**: Utilizes OpenRouter (specifically `openai/gpt-4o-mini`) for generating questions, evaluating answers, and summarizing interviews.
*   **Coding Round Engine (`backend/coding_graph.py`)**: Manages technical coding tasks, code execution, and AI-driven feedback.

### 2.3 Database Structure
Persistence is handled by MongoDB Atlas, accessed via `pymongo`.
*   **Connection Management (`backend/mongo_db.py`)**: Implements connection pooling, retry logic, and lazy collection proxies.
*   **Collections**:
    *   `candidates`: Stores candidate profiles.
    *   `admins`: Stores admin credentials and profiles.
    *   `interview_sessions`: Tracks the lifecycle of an interview link (pending, started, completed).
    *   `interviews`: Stores the actual interview data, including generated questions and the final recording URL.
    *   `answers`: Stores individual question responses, AI scores, and feedback.

### 2.4 External Integrations
*   **MongoDB Atlas**: Primary database for metadata and analytics.
*   **Cloudinary**: Cloud storage for full interview video recordings (`.webm`).
*   **OpenRouter (OpenAI)**: LLM provider for question generation, answer scoring, and coding feedback.
*   **Brevo (Sendinblue)**: SMTP service for sending interview invitations and completion notifications.

## 3. File-by-File Understanding

| File Path | Responsibility |
| :--- | :--- |
| `backend/uploded.py` | Main FastAPI application, Socket.IO server, REST endpoints, and core business logic. |
| `backend/mongo_db.py` | MongoDB connection manager, URI validation, and lazy collection proxies. |
| `backend/coding_graph.py` | AI logic for generating coding tasks and evaluating code submissions. |
| `backend/analyze_answer.py` | Helper functions for evaluating verbal answers using OpenRouter. |
| `backend/transcription.py` | Alternative/legacy transcription endpoint using local Whisper models. |
| `backend/database.py` | Legacy SQLite schema bootstrap (indicates architectural drift). |
| `forenten/index.html` | Candidate-facing UI, media capture, WebSocket emission, and interview flow. |
| `forenten/admin.html` | Admin-facing UI, session management, and real-time WebSocket reception. |
| `forenten/MediaRecorder.js` | Frontend class managing audio capture and browser-based speech recognition. |
| `forenten/config.js` | Frontend configuration for API base URLs. |

## 4. Workflow Explanation

### 4.1 Candidate Interview Lifecycle
1.  **Initialization**: Candidate opens the unique session link. The frontend fetches session details and initializes the camera/microphone.
2.  **Connection**: A Socket.IO connection is established, joining a room specific to the `interview_id`.
3.  **Execution**: The candidate answers questions sequentially. `MediaRecorder.js` captures audio and provides live transcripts.
4.  **Streaming**: Video frames (binary JPEGs) and metadata (transcripts, proctoring alerts) are streamed via WebSockets to the admin.
5.  **Submission**: After each answer, audio is uploaded to `/transcribe` for final processing, and the answer is saved.
6.  **Completion**: The full session recording is finalized and uploaded to Cloudinary via `/upload-full-recording`.

### 4.2 Admin Monitoring Flow
1.  **Dashboard**: Admin logs in and views active sessions.
2.  **Live View**: Admin clicks "Live View" for an active session.
3.  **WebSocket Reception**: The admin frontend joins the `interview_id` room via Socket.IO.
4.  **Rendering**: Receives `live_frame` (binary video) and `live_update` (metadata) events, updating the DOM in real-time without HTTP polling overhead.

## 5. Existing Fixes Summary

Based on `README.md` and `implementation_guide.md`, the following major architectural upgrades have already been applied:
1.  **Live Preview Inconsistency**: Replaced HTTP polling (`setInterval` + `fetch`) with **Socket.IO**. Video frames are now sent as binary JPEG blobs, significantly reducing latency (<150ms) and server overhead.
2.  **Video Persistence**: Replaced ephemeral local filesystem storage with **Cloudinary**. The `/upload-full-recording` endpoint now uploads directly to Cloudinary and saves the secure URL to MongoDB.
3.  **Performance Optimization**: Replaced `setInterval` with `requestAnimationFrame` on the frontend for frame capture, implementing a 120ms throttle (~8 FPS) to reduce candidate CPU usage.

## 6. Current Issues & Root Cause Analysis

Despite the recent upgrades, several architectural risks and potential root causes for errors remain:

### 6.1 Architectural Drift & Dead Code
*   **Issue**: The presence of `backend/database.py` (SQLite) alongside `backend/mongo_db.py` (MongoDB) indicates incomplete migration or dead code.
*   **Root Cause**: Legacy code was not removed during the MongoDB migration, potentially causing confusion or conflicting state if imported accidentally.

### 6.2 Transcription Pipeline Duplication
*   **Issue**: `forenten/MediaRecorder.js` relies on browser-based `SpeechRecognition` for live transcripts, but also uploads audio to `/transcribe`. Furthermore, `backend/transcription.py` exists as a separate Whisper-based implementation alongside logic in `uploded.py`.
*   **Root Cause**: Conflicting implementations of transcription. If the backend Whisper service is not running or fails, the system might fall back inconsistently. The API contract for `/transcribe` in `transcription.py` expects `candidate_name`, which may not align with the main app's expectations.

### 6.3 State Management in Monolith
*   **Issue**: `backend/uploded.py` uses an in-memory dictionary (`interviews = {}`) alongside MongoDB (`interviews_collection`).
*   **Root Cause**: In a serverless or multi-instance deployment (like Render), in-memory state will be lost on restart or not shared across workers, leading to "Interview not found" errors.

### 6.4 WebSocket Room Isolation
*   **Issue**: While Socket.IO rooms are used (`interview_id`), the reliance on global state or missing error handling during reconnection could break the live feed.
*   **Root Cause**: If a candidate briefly disconnects, the frontend might not properly re-emit the `join_interview` event, leaving the admin in a stale room.

## 7. Safe Fix Strategy

Before modifying any code, the following strategy must be adhered to:

1.  **Do Not Revert Upgrades**: Ensure that Socket.IO and Cloudinary implementations remain intact. Do not revert to HTTP polling or local storage.
2.  **Consolidate State**: Remove reliance on the in-memory `interviews` dictionary in `uploded.py`. All state must be read from and written to MongoDB to support stateless deployment.
3.  **Clean Up Legacy Code**: Safely deprecate and remove `backend/database.py` (SQLite) to prevent accidental imports and clarify the architecture.
4.  **Unify Transcription**: Standardize the transcription flow. Ensure the frontend `MediaRecorder.js` correctly interfaces with a single, robust backend endpoint, handling failures gracefully.
5.  **Enhance Error Boundaries**: Add robust `try/except` blocks around external API calls (OpenRouter, Cloudinary, Brevo) to prevent cascading failures.

## 8. Recommended Debugging Order

1.  **State Persistence**: Audit `uploded.py` for any usage of the `interviews` dictionary. Replace with direct MongoDB queries using `get_interview_or_404`.
2.  **Transcription Flow**: Trace the exact payload sent by `MediaRecorder.js` to `/transcribe` and verify which backend function handles it. Resolve any mismatches.
3.  **WebSocket Reconnection**: Test the candidate frontend's behavior when the network drops. Ensure `socket.on("connect")` re-joins the correct room.
4.  **Dead Code Removal**: Delete `backend/database.py` and verify the test suite (`test_uploded.py`) still passes.
5.  **Deployment Configuration**: Verify that `render.yaml` and environment variables correctly point to MongoDB and Cloudinary, ensuring no local file paths are hardcoded for permanent storage.
