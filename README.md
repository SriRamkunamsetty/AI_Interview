# AI Adaptive Interview Platform

A high-performance, full-stack AI interview platform featuring real-time video monitoring, behavioral analysis, and automated reporting.

## 🚀 System Architecture

The platform is built with a modern, decoupled architecture designed for low latency and high scalability.

### 🏗️ Core Components

| Component | Technology | Role |
| :--- | :--- | :--- |
| **Frontend** | HTML5, CSS3, JavaScript (ES6+) | Candidate interface & Admin dashboard. |
| **Backend** | FastAPI (Python 3.11) | REST API & WebSocket server. |
| **Real-time Engine** | Socket.IO | Low-latency binary video streaming & metadata sync. |
| **Database** | MongoDB Atlas | Persistent storage for interview data & analytics. |
| **Cloud Storage** | Cloudinary | Permanent storage for full interview recordings. |
| **AI/ML** | OpenAI / OpenRouter | Automated answer analysis & behavioral insights. |

## 🔄 System Workflow

1.  **Session Initiation**: Candidate joins via a unique link; the system initializes camera/mic and establishes a WebSocket connection.
2.  **Live Streaming**: 
    *   **Video**: Captured via `<video>` + `<canvas>`, throttled via `requestAnimationFrame`, and sent as binary JPEG blobs via Socket.IO.
    *   **Metadata**: Transcripts, audio levels, and proctoring alerts are synced in real-time.
3.  **Admin Monitoring**: Admins receive binary frames and metadata instantly, rendering them efficiently using `URL.createObjectURL` to minimize DOM overhead.
4.  **Interview Completion**: Full session recording is stopped, packaged as a `.webm` blob, and uploaded to Cloudinary.
5.  **Persistence**: Cloudinary URLs and interview analytics are saved to MongoDB Atlas for long-term access.

## 🛠️ Issues Solved & Implementation Details

### 1. Live Preview Inconsistency & Latency
*   **Issue**: Originally used HTTP polling (`setInterval` + `fetch`), resulting in 3-5s delays and high server overhead.
*   **Solution**: Implemented **Socket.IO** with binary frame streaming.
*   **Why**: WebSockets provide a persistent, full-duplex connection. Binary JPEG blobs (320px width, 0.4 quality) significantly reduce payload size compared to Base64 strings, ensuring <150ms latency.

### 2. Video Persistence
*   **Issue**: Videos were saved to the local server filesystem, which is ephemeral on platforms like Render/Vercel, leading to data loss.
*   **Solution**: Integrated **Cloudinary** for cloud-native video storage.
*   **Why**: Cloudinary provides reliable, permanent storage with a global CDN, ensuring interview recordings are never lost and are easily accessible via secure URLs.

### 3. Performance Optimization
*   **Issue**: High CPU usage on the candidate side due to frequent frame capture.
*   **Solution**: Replaced `setInterval` with `requestAnimationFrame` and implemented a 120ms throttle (~8 FPS).
*   **Why**: `requestAnimationFrame` aligns with the browser's refresh rate and pauses when the tab is inactive, saving resources while maintaining a smooth visual experience for the admin.

## ⚙️ Setup & Deployment

### Environment Variables
```env
MONGO_URI=your_mongodb_uri
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret
OPENROUTER_API_KEY=your_api_key
```

### Installation
```bash
pip install -r requirements.txt
python backend/uploded.py
```
