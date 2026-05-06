# AI Interview Platform: Codebase Analysis and Bug Diagnosis

This document provides a comprehensive analysis of the AI Interview platform codebase, focusing on system architecture, workflow, and the root causes of two critical bugs: live preview inconsistency and the failure of videos to save in MongoDB Atlas.

## 1. System Architecture Overview

The platform is a full-stack application with a Python-based backend and an HTML/JavaScript frontend.

| Component | Technology | Description |
| :--- | :--- | :--- |
| **Frontend** | HTML, CSS, JavaScript | Consists of two main interfaces: `index.html` for the candidate interview and `admin.html` for the admin dashboard. It uses `MediaRecorder` for video/audio capture and `fetch` for API communication. |
| **Backend** | FastAPI (Python) | A REST API server (`uploded.py`) that handles business logic, data processing, and communication with the database. |
| **Database** | MongoDB Atlas | Used to store all persistent data, including interview sessions, candidate information, answers, and analysis results. |
| **Deployment**| Vercel (Frontend), Render (Backend) | The frontend is deployed on Vercel, and the backend is deployed on Render. |

## 2. End-to-End Workflow

1.  **Initiation**: A candidate starts an interview via a unique session link.
2.  **Capture**: The frontend (`index.html`) captures video and audio using the browser's `MediaRecorder` API.
3.  **Real-time Data Submission**: During the interview, the frontend sends a continuous stream of data to the backend:
    *   Transcriptions are generated via the Web Speech API and sent to the `/transcribe` endpoint.
    *   Behavioral data (e.g., tab switches, face detection alerts) is sent to the `/save-behavioral-data` endpoint.
    *   Each answer is submitted to the `/save-answer` endpoint for analysis.
4.  **Admin Monitoring**: The admin dashboard (`admin.html`) periodically polls the `/admin/interview/{link_id}` endpoint to fetch and display the latest interview data.
5.  **Completion & Upload**: When the interview ends, the frontend stops the recording, packages the full video into a `.webm` blob, and uploads it to the `/upload-full-recording` endpoint.
6.  **Storage**: The backend receives the video file, saves it to a local directory on the server, and stores the file path in the corresponding MongoDB document.

## 3. Root Cause Analysis

### Bug 1: Live Preview Inconsistency

**Root Cause**: The live monitoring feature is implemented using **HTTP polling**, not a real-time communication protocol like WebSockets. The `admin.html` page uses a `setInterval` function to repeatedly call the `/admin/interview/{link_id}` endpoint. This architectural choice is the primary source of the observed inconsistency and delays.

*   **Polling Latency**: There is an inherent delay between the time an event occurs on the candidate's side and when it is reflected on the admin's dashboard. This delay is a sum of the polling interval, network latency, and backend processing time.
*   **Data Staleness**: The data displayed on the admin dashboard is only as fresh as the last poll. Any actions that happen between polls will not be visible until the next refresh, creating a perception of instability.
*   **Lack of Real-time Push**: The server does not proactively push updates to the admin client. The client must constantly pull data, which is inefficient and not truly "live."

### Bug 2: Video Not Saving in MongoDB Atlas

**Root Cause**: The video file itself is **not being stored in MongoDB Atlas**. The backend's `/upload-full-recording` endpoint saves the video to the **local filesystem** of the server running on Render. It then stores only the **file path** string in the `recording_path` field of the interview document in MongoDB.

*   **Ephemeral Filesystems**: Cloud platforms like Render use ephemeral filesystems. This means that any files written to the local disk are temporary and are **deleted** when the server instance restarts, redeploys, or goes to sleep. This is the core reason the videos appear to be missing.
*   **Invalid File Path**: The path stored in MongoDB (e.g., `uploads/recordings/interview-id.webm`) becomes a dead link as soon as the file is wiped from the ephemeral storage, making it impossible to retrieve the video.

## 4. Debugging Checklist

To verify the findings and systematically debug the issues, follow this checklist:

### General

- [ ] **Check Browser Console**: Look for any failed network requests (4xx or 5xx errors) or JavaScript errors in both the candidate and admin browser windows.
- [ ] **Check Backend Logs**: Inspect the logs from your Render service for any application errors, stack traces, or failed database operations.

### Bug 1: Live Preview Inconsistency

- [ ] **Verify Polling Requests**: In the admin dashboard's browser developer tools (Network tab), confirm that `fetch` requests to `/admin/interview/{link_id}` are being sent regularly.
- [ ] **Measure Request Duration**: Check the time taken for these polling requests to complete. Long durations indicate backend or database performance issues.
- [ ] **Inspect API Responses**: Examine the JSON response from the polling endpoint. Check if the `live_monitoring` and `last_activity_at` fields are being updated as expected.

### Bug 2: Video Not Saving

- [ ] **Confirm Frontend Upload**: In the candidate's browser, after ending the interview, check the Network tab for the `POST` request to `/upload-full-recording`. Ensure it receives a 200 OK response.
- [ ] **Inspect Upload Payload**: Verify that the request payload contains the video file (`full_interview.webm`).
- [ ] **Check Backend Logs for Save Operation**: Look for log messages in your Render service confirming that the file was received and "saved" to a local path.
- [ ] **Verify MongoDB Document**: Use a MongoDB client to inspect the `interviews_collection`. Find the relevant interview document and check the value of the `recording_path` field. Confirm that it contains a file path.
- [ ] **Attempt to Access the File (if possible)**: If you can get shell access to your Render instance immediately after an upload (before it restarts), check if the file exists at the specified `recording_path`. This will confirm the ephemeral nature of the storage.
