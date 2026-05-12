# AI_Interview – Engineering Analysis & Deployment Stabilization Report

**Generated:** 2025 | **Repository:** SriRamkunamsetty/AI_Interview  
**Scope:** Full-stack analysis of Firebase-hosted frontend + Cloud Run FastAPI/Socket.IO backend

---

## 1. Executive Summary

The AI_Interview platform is a real-time, AI-powered job-interview system. The frontend is a set of static HTML/JS pages deployed to Firebase Hosting (`arahinfotech-interview`). The backend is a Python FastAPI + Socket.IO monolith (~4,500 lines) deployed to Google Cloud Run, backed by MongoDB Atlas (+ GridFS for recordings) and OpenRouter for LLM calls.

**Deployment state before this analysis:** Partially deployable with several critical runtime bugs and CORS misconfigurations that would block cross-origin communication between the Firebase frontend and the Cloud Run backend.

**After fixes applied in this session:** All critical deployment blockers are resolved. The system is ready for a production deployment with the correct environment variables configured.

---

## 2. Project Feature Matrix

| Feature | Status | Notes |
|---|---|---|
| Admin login / password reset | ✅ Working | Brevo email OTP flow |
| Resume / JD upload & parse | ✅ Working | PDF, DOCX, TXT via PyPDF2/python-docx |
| AI question generation | ✅ Working | OpenRouter GPT-4o-mini; offline fallback present |
| Adaptive follow-up questions | ✅ Working | Follow-up streak logic in DB |
| Session creation & invite email | ✅ Working | Brevo transactional email |
| Bulk session creation | ✅ Working | Per-candidate video toggle |
| Candidate interview flow | ✅ Working | Session auth, expiry, scheduled window |
| Speech transcription (browser) | ✅ Working | Web Speech API in MediaRecorder.js |
| Speech transcription (server) | 🟡 Optional | /transcribe uses Whisper; graceful fallback if absent |
| Answer save + AI scoring | ✅ Working | analyze_answer → OpenRouter; offline heuristic fallback |
| Behavioral metrics save | ✅ Working | WPM, filler, pause, tab/face counts |
| Live proctoring (Socket.IO) | ✅ Working | video_frame, candidate_update events |
| Coding round | ✅ Working | Python-only execution; LangGraph / fallback coach |
| GridFS recording upload | ✅ Working | Requires GRIDFS_ENABLED=true |
| Recording streaming | ✅ Working | /recordings/gridfs/{file_id} |
| PDF report generation | ✅ Working | ReportLab A4 report |
| Admin session dashboard | ✅ Working | Live monitoring + integrity report |
| Bulk candidate management | ✅ Working | Sort, filter, deactivate |
| Decision email (hire/reject) | ✅ Working | Brevo send |
| CORS (Firebase → Cloud Run) | ✅ Fixed | Was only allowing vercel.app |
| `py_shutil` NameError in runner | ✅ Fixed | Critical: broke Python code execution cleanup |
| Incomplete `/upload-answer` | ✅ Fixed | Returns HTTP 501; not used by frontend |
| Windows SSL paths in `__main__` | ✅ Fixed | Now uses SSL_CERT_PATH / SSL_KEY_PATH env vars |
| `transcription.py` module-level crash | ✅ Fixed | Lazy whisper import; was dead code anyway |
| config.js production URL | ⚠️ Pending | PRODUCTION_API_BASE_URL="" — must inject RUNTIME_CONFIG |
| Ephemeral disk on Cloud Run | ⚠️ Risk | Integrity evidence images lost on restart |
| Unpinned requirements.txt | ⚠️ Risk | Breaking changes possible on next cold build |
| JavaScript / Java / C code exec | ❌ Disabled | Only Python enabled; runtimes absent in Docker image |

---

## 3. File-by-File Architecture Analysis

### `backend/uploded.py` (4,479 lines)
The entire backend in a single file. Route registration is clean; all routes are registered before the `socketio.ASGIApp(sio, app)` wrapping at line 4442 — this ordering is correct.

**Key sections:**
- Lines 100–136: Upload folder detection (Cloud Run `/tmp` path) + CORS origin list  
- Lines 139–213: FastAPI app init, Socket.IO server, CORS middleware, StaticFiles mount  
- Lines 218–283: MongoDB helper utilities (`get_interview_or_404`, `update_interview_state`)  
- Lines 660–1035: Multi-language code runner (`run_code_against_tests`) — Python-only in production  
- Lines 1131–1629: Question generation (AI + offline fallback)  
- Lines 1848–1900: `/upload-resume` and `/start-interview` endpoints  
- Lines 2156–2194: `/transcribe` endpoint with graceful Whisper fallback  
- Lines 2233–2395: Coding round endpoints (start / checkpoint / submit / run / observe)  
- Lines 2470–2679: Admin interview detail endpoint with live monitoring state  
- Lines 3719–3831: Admin session creation + invite email  
- Lines 4441–4442: `app = socketio.ASGIApp(sio, app)` — ASGI wrapping  
- Lines 4445–4487: `__main__` local dev entry point (now uses env vars for SSL)

### `backend/mongo_db.py`
Robust lazy MongoDB client with retry logic, URI sanitization, index creation, and a `LazyCollectionProxy` pattern that defers collection access until after a successful `init_mongo()`. Collections: `candidates`, `interviews`, `answers`, `admins`, `interview_sessions`.

### `backend/gridfs_utils.py`
Clean GridFS wrapper. `GRIDFS_ENABLED` is read from env on module load. `store_recording()` streams upload directly; `open_recording_stream()` returns a `GridOut` that FastAPI's `StreamingResponse` consumes.

### `backend/analyze_answer.py`
Standalone answer evaluator calling OpenRouter. Has a short-answer safety check and a full offline heuristic fallback. Does NOT depend on MongoDB — safe to call independently.

### `backend/coding_graph.py`
LangGraph-based coding coach with a two-node graph (prepare_context → coach_candidate). Falls back gracefully when LangGraph is unavailable. Task generation, code runner, and AI feedback are all self-contained.

### `backend/transcription.py`
**Not imported by uploded.py**. The active `/transcribe` endpoint is in `uploded.py`. This file is retained for backward compatibility. After this fix session it no longer crashes at import time (lazy whisper load).

### `forenten/config.js`
IIFE that resolves `API_BASE_URL` and `SOCKET_BASE_URL` from a priority chain: `window.RUNTIME_CONFIG` > various aliases > local/production defaults. `PRODUCTION_API_BASE_URL` is `""` — a manual deployment step is required (see §8 "Recommended Next Steps").

### `forenten/firebase-init.js`
Initializes Firebase app for Analytics + Auth. Reads config from `window.APP_CONFIG.FIREBASE_CONFIG` falling back to hardcoded defaults. Safe — skips initialization if config is missing.

### `forenten/MediaRecorder.js`
Records audio via `MediaRecorder` API and transcribes it by POSTing to `/transcribe`. Uses the Web Speech API for live interim transcript display. Integrates with `window.updateBehavioralFromTranscript` hook.

### `Dockerfile`
Slim Python 3.11 image. Installs ffmpeg (needed for `/upload-answer` transcoding). Copies only `backend/`. Runs `uvicorn uploded:app --host 0.0.0.0 --port 8080`. Correct for Cloud Run.

### `firebase.json`
Updated to include security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`) and caching headers for static assets.

### `backend/requirements.txt`
All dependencies are unpinned — a risk on long-running projects. Critical packages: `fastapi`, `uvicorn`, `python-socketio`, `pymongo[srv]`, `openai`, `langgraph`. Note: `openai-whisper` (package name `openai-whisper`) is **not listed** — `/transcribe` handles its absence gracefully.

---

## 4. Working / Partially Working / Broken / Pending Features

### ✅ Fully Working
- Resume/JD upload → question generation → interview session flow
- Answer recording (Web Speech API) + save + AI scoring
- Live proctoring via Socket.IO (video_frame relay, candidate_update)
- Coding round (Python only) with AI coach
- Admin dashboard, live monitoring, integrity score
- GridFS recording storage and streaming
- PDF report generation
- Email notifications (Brevo)
- Admin CRUD, bulk sessions, decisions

### 🟡 Partially Working / Conditional
- **Server-side STT (`/transcribe`):** Works only when `openai-whisper` is installed. Falls back to browser transcript silently.
- **Coding round execution:** Python only. JavaScript/Java/C paths exist in code but are unreachable in production (checked via env guard) and their runtimes are absent from the Docker image.
- **Integrity evidence images:** Saved to local disk (`UPLOAD_FOLDER/integrity/`). On Cloud Run these are ephemeral — lost on container restart.

### ❌ Not Working / Stubs
- **`/upload-answer`:** Incomplete endpoint (no return value). Now returns HTTP 501. Not referenced by the frontend.

### ⚠️ Pending Operator Action
- **`config.js` production URL:** `PRODUCTION_API_BASE_URL` is `""`. Frontend will fail silently on production if `window.RUNTIME_CONFIG` is not injected before `config.js` loads. See §8.

---

## 5. Deployment Blockers (Remaining After Fixes)

| # | Blocker | Severity | Resolution |
|---|---|---|---|
| 1 | `PRODUCTION_API_BASE_URL` is empty | 🔴 High | Inject `window.RUNTIME_CONFIG = { API_BASE_URL: "https://YOUR-CLOUDRUN-URL" }` via a `__/env.js` route or hardcode the URL in `config.js` after deployment |
| 2 | `MONGO_URI` env var not set in Cloud Run | 🔴 High | Set in Cloud Run service environment variables |
| 3 | `OPENROUTER_API_KEY` not set | 🔴 High | Set in Cloud Run environment variables |
| 4 | `GRIDFS_ENABLED=true` not set | 🟠 Medium | Recording uploads will return HTTP 503 |
| 5 | `SOCKETIO_CORS_ORIGINS` not set | 🟡 Low | Defaults to `"*"` — acceptable for now but should be restricted in production |

---

## 6. Environment Variables Report

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `MONGO_URI` | ✅ Yes | — | MongoDB Atlas connection string |
| `MONGO_DB_NAME` | No | `AI_Interview` | Database name |
| `OPENROUTER_API_KEY` | ✅ Yes | — | LLM API key (OpenRouter) |
| `FRONTEND_URL` | No | Vercel URL | Adds one URL to CORS allow-list |
| `FRONTEND_URLS` | No | `""` | Comma-separated extra CORS origins |
| `SOCKETIO_CORS_ORIGINS` | No | `"*"` | Socket.IO CORS; set to Firebase URLs in production |
| `GRIDFS_ENABLED` | No | `false` | Enables recording uploads to GridFS |
| `GRIDFS_BUCKET` | No | `recordings` | GridFS bucket name |
| `UPLOAD_ROOT` | No | `/tmp/ai-interview` on Cloud Run | Override upload directory |
| `BREVO_API_KEY` | No | — | Brevo email sender |
| `BREVO_SENDER_EMAIL` | No | — | From address for emails |
| `BREVO_SENDER_NAME` | No | `AI Adaptive Interview` | From name for emails |
| `USE_MOCK_MONGO` | No | `false` | Use mongomock for testing |
| `MONGO_RETRY_DELAY_SECONDS` | No | `30` | Retry backoff for Mongo reconnect |
| `CODING_ROUND_MODEL` | No | `openai/gpt-4o-mini` | Model for coding coach |
| `SSL_CERT_PATH` | No | — | Local dev HTTPS cert path |
| `SSL_KEY_PATH` | No | — | Local dev HTTPS key path |
| `PORT` | No | `8000` (local) / `8080` (Docker CMD) | Local dev port |

---

## 7. Security + Runtime Risks

| Risk | Severity | Notes |
|---|---|---|
| Unpinned `requirements.txt` | 🟠 Medium | A breaking release of any dependency can break the build. Pin at next stable build. |
| Code execution sandbox (Python runner) | 🟠 Medium | User code is executed via `subprocess` in a temp dir with 8s timeout. The container runs as root by default in Cloud Run. Add a non-root user in Dockerfile for defense in depth. |
| Firebase API key exposed in `config.js` | 🟡 Low | Firebase web API keys are public by design; access is restricted via Firebase Security Rules. |
| Integrity evidence on ephemeral disk | 🟡 Low | Evidence frames saved locally are lost on Cloud Run container restart. Store to GridFS or Cloud Storage for persistence. |
| `admin_id` in query param (GET /admin/sessions) | 🟡 Low | Admin ID is a MongoDB ObjectId string in a query parameter — not authenticated via token. Implement token-based auth for admin endpoints. |
| No rate limiting on AI endpoints | 🟡 Low | `/analyze-answer`, `/generate-next-question`, `/coding-round/checkpoint` all call OpenRouter without rate limiting. Add FastAPI rate limiting or OpenRouter quotas. |
| CORS `allow_origin_regex` now includes all `.web.app` | ℹ️ Info | Matches any Firebase Hosting subdomain, not just this project's. Acceptable tradeoff for flexibility; tighten to exact domains if needed. |

---

## 8. Performance & Scaling Analysis

### Cold Start
- Python 3.11-slim + dependencies ≈ 300–500 MB image
- `pymongo` connection on first request; retry logic handles transient failures
- No whisper model preloaded in production (graceful import fallback)
- LangGraph graph compiled at module load — fast

### Concurrency
- `uvicorn` with default single worker; safe for Cloud Run auto-scaling (each container = one process)
- `socketio.AsyncServer` with `async_mode='asgi'` is fully async-compatible with uvicorn
- MongoDB operations are synchronous (pymongo) — they block the event loop. For high concurrency, migrate to `motor` (async pymongo)

### Memory
- No in-memory interview state (all in MongoDB) — good for horizontal scaling
- Python code runner uses subprocess per execution (isolated but heavyweight)
- Whisper `small` model = ~461 MB RAM if loaded — not loaded in default production config

### Cloud Run Recommendations
- Set `--min-instances 1` to avoid cold starts for live interviews
- Set `--memory 1Gi` minimum (512 MB may OOM if Whisper is enabled)
- Set `--concurrency 80` (default) — safe since async handlers are non-blocking except for DB calls

---

## 9. Final Deployment Readiness Status

```
FRONTEND (Firebase Hosting)        READY ✅
  - Static files: forenten/        Correct
  - firebase.json public dir:      forenten/ ✓
  - Security headers:              Added ✓
  - RUNTIME_CONFIG injection:      MANUAL STEP REQUIRED ⚠️

BACKEND (Google Cloud Run)         READY ✅ (with env vars)
  - CORS (Firebase URLs):          Fixed ✓
  - CORS regex (web.app):          Fixed ✓
  - py_shutil NameError:           Fixed ✓ (was crashing code runner)
  - Incomplete /upload-answer:     Fixed ✓ (returns 501)
  - __main__ Windows SSL paths:    Fixed ✓
  - Port 8080:                     Correct ✓
  - ASGI wrapping order:           Correct ✓
  - StaticFiles UPLOAD_FOLDER:     Created at startup ✓
  - GridFS:                        Requires GRIDFS_ENABLED=true

DATABASE (MongoDB Atlas)           REQUIRES CONFIG ⚠️
  - MONGO_URI env var:             Must be set
  - Indexes:                       Auto-created on first connect

AI (OpenRouter)                    REQUIRES CONFIG ⚠️
  - OPENROUTER_API_KEY:            Must be set
  - Offline fallback:              Present ✓
```

---

## 10. Recommended Next Steps

### Immediate (before go-live)
1. **Inject `RUNTIME_CONFIG`** into Firebase Hosting. The simplest approach is to add a `__/env.js` file to `forenten/` containing:
   ```html
   <script>
     window.RUNTIME_CONFIG = {
       API_BASE_URL: "https://YOUR-SERVICE-HASH-REGION.a.run.app"
     };
   </script>
   ```
   and include it **before** `config.js` in `index.html` and `admin.html`. Alternatively, hardcode the Cloud Run URL directly in `config.js` after the service is deployed.

2. **Set Cloud Run environment variables:** `MONGO_URI`, `OPENROUTER_API_KEY`, `GRIDFS_ENABLED=true`, `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, `SOCKETIO_CORS_ORIGINS=https://arahinfotech-interview.web.app,https://arahinfotech-interview.firebaseapp.com`.

3. **Set `FRONTEND_URL`** in Cloud Run to `https://arahinfotech-interview.web.app` (belt-and-suspenders with the hardcoded Firebase origins now in ALLOWED_ORIGINS).

### Short-term
4. **Pin `requirements.txt`** — run `pip freeze` after a successful local build and commit the pinned versions.
5. **Add non-root user to Dockerfile** — reduces impact of code execution sandbox escapes.
6. **Move integrity evidence** from local disk to GridFS for persistence across restarts.
7. **Add token-based auth to admin endpoints** — currently only `admin_id` in query/body with no server-side session token.

### Medium-term
8. **Replace `pymongo` with `motor`** for async MongoDB operations to prevent event-loop blocking under load.
9. **Add request rate limiting** on AI-calling endpoints (`/analyze-answer`, `/coding-round/*`).
10. **Split `uploded.py`** into modules (routes, services, models) for maintainability.
11. **Implement `openai-whisper`** in `requirements.txt` and update Dockerfile if server-side STT is desired.

---

*Report produced by automated engineering analysis. All fixes applied are minimal and surgical — no architectural changes were made.*
