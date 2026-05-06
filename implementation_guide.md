# AI Interview Platform: Fix Implementation Guide

This document outlines the architectural changes and code implementations applied to resolve the live preview inconsistency and video storage issues in the AI Interview platform.

## 1. Real-Time Live Preview (WebSocket Implementation)

To resolve the inconsistency and latency caused by HTTP polling, we replaced the polling mechanism with real-time WebSockets using **Socket.IO**.

### Backend Changes (`backend/uploded.py`)

We integrated `python-socketio` with the existing FastAPI application.

1.  **Dependencies**: Added `python-socketio` and `python-socketio[asyncio_client]`.
2.  **Socket.IO Server Setup**:
    ```python
    import socketio

    # Socket.IO setup
    sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
    socket_app = socketio.ASGIApp(sio, app)
    ```
3.  **Event Handlers**: Created handlers for joining rooms (based on `interview_id`) and broadcasting updates.
    ```python
    @sio.on("join_interview")
    async def join_interview(sid, data):
        interview_id = data.get("interview_id")
        if interview_id:
            await sio.enter_room(sid, interview_id)

    @sio.on("candidate_update")
    async def candidate_update(sid, data):
        interview_id = data.get("interview_id")
        if interview_id:
            # Broadcast to everyone in the room (admin)
            await sio.emit("live_update", data, room=interview_id, skip_sid=sid)
    ```

### Frontend Changes

#### Candidate Interface (`forenten/index.html`)

1.  **Included Socket.IO Client**: `<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>`
2.  **Initialization & Emission**: Added logic to connect to the WebSocket server and emit updates every 3 seconds.
    ```javascript
    let socket = null;

    function initSocket() {
        if (!currentInterviewId) return;
        socket = io(API_BASE_URL);
        socket.on('connect', () => {
            socket.emit('join_interview', { interview_id: currentInterviewId });
        });
    }

    function emitCandidateUpdate(extraData = {}) {
        if (!socket || !interviewActive) return;
        const updateData = {
            interview_id: currentInterviewId,
            timestamp: new Date().toISOString(),
            phase: currentPhase || 'verbal',
            question_index: currentQuestionId || 0,
            total_questions: (questions && questions.length) || 0,
            current_transcript: document.getElementById('transcriptionBox')?.value || '',
            face_status: currentFaceStatus || 'Stable',
            audio_level: latestAudioLevel || 0,
            ...extraData
        };
        socket.emit('candidate_update', updateData);
    }

    setInterval(() => {
        if (interviewActive) emitCandidateUpdate();
    }, 3000);
    ```

#### Admin Interface (`forenten/admin.html`)

1.  **Included Socket.IO Client**: `<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>`
2.  **Initialization & Reception**: Added logic to join the specific interview room and update the UI instantly upon receiving a `live_update` event.
    ```javascript
    let adminSocket = null;

    function initAdminSocket(interviewId) {
        if (adminSocket) adminSocket.disconnect();
        adminSocket = io(API_BASE);
        adminSocket.on('connect', () => {
            adminSocket.emit('join_interview', { interview_id: interviewId });
        });
        adminSocket.on('live_update', (data) => {
            updateLiveUI(data); // Function to update DOM elements
        });
    }
    ```

## 2. Persistent Video Storage (Cloudinary Implementation)

To resolve the issue of videos being deleted from the ephemeral local server storage, we integrated **Cloudinary** for permanent cloud storage.

### Backend Changes (`backend/uploded.py`)

1.  **Dependencies**: Added `cloudinary`.
2.  **Configuration**: Configured Cloudinary using environment variables.
    ```python
    import cloudinary
    import cloudinary.uploader

    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True
    )
    ```
3.  **Upload Endpoint Update**: Modified the `/upload-full-recording` endpoint to upload the file directly to Cloudinary and save the resulting secure URL to MongoDB.
    ```python
    @app.post("/upload-full-recording")
    async def upload_full_recording(
        interview_id: str = Form(...),
        file: UploadFile = File(...)
    ):
        try:
            # Upload to Cloudinary
            upload_result = cloudinary.uploader.upload(
                file.file,
                resource_type="video",
                public_id=f"interviews/{interview_id}_full",
                overwrite=True
            )
            
            video_url = upload_result.get("secure_url")
            
            # Update database with the persistent URL
            interviews_collection.update_one(
                {"id": interview_id},
                {"$set": {
                    "recording_path": video_url,
                    "recording_url": video_url,
                    "storage_type": "cloudinary"
                }}
            )
            
            return {"status": "success", "file_path": video_url}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    ```

## 3. Next Steps for Deployment

To deploy these changes successfully, you must configure the following environment variables in your Render backend environment:

*   `CLOUDINARY_CLOUD_NAME`: Your Cloudinary cloud name.
*   `CLOUDINARY_API_KEY`: Your Cloudinary API key.
*   `CLOUDINARY_API_SECRET`: Your Cloudinary API secret.

Ensure that your `requirements.txt` is updated to include the new dependencies:
```text
python-socketio
python-socketio[asyncio_client]
cloudinary
```

The frontend changes are already integrated into the HTML files and will be active upon your next Vercel deployment.
