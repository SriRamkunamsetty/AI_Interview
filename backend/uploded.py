from fastapi import FastAPI, UploadFile, File, Form, HTTPException
import os
import sys
import json
import tempfile
import shutil
import uuid
import random
import threading
import time
import base64
import html
import textwrap
import traceback
import re
import io
import subprocess
import requests
import httpx
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from difflib import SequenceMatcher

# 1. Logging Setup
print("🚀 Starting Backend Initialization...")

# 2. Environment Loading
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ Environment variables loaded.")
except Exception as e:
    print(f"⚠️ Warning: Failed to load .env file: {e}")

# 3. Critical Imports with Error Handling
try:
    from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, StreamingResponse
    from fastapi.staticfiles import StaticFiles
    from fastapi.middleware.gzip import GZipMiddleware
    from pydantic import BaseModel
    print("✅ FastAPI components imported.")
except ImportError as e:
    print(f"❌ CRITICAL: FastAPI import failed: {e}")
    sys.exit(1)

try:
    import socketio
    import cloudinary
    import cloudinary.uploader
    print("✅ WebSocket and Cloudinary libraries imported.")
except ImportError as e:
    print(f"❌ CRITICAL: External integration libraries missing: {e}")
    sys.exit(1)

try:
    from openai import OpenAI
    import PyPDF2
    from docx import Document
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import simpleSplit
    print("✅ AI and Document processing libraries imported.")
except ImportError as e:
    print(f"⚠️ Warning: Some processing libraries missing: {e}")

# 4. Local Module Imports
try:
    from analyze_answer import analyze_answer
    from coding_graph import generate_coding_task, observe_coding_intent, run_coding_round
    from gridfs_utils import (
        build_recording_url,
        is_gridfs_enabled,
        open_recording_stream,
        store_recording,
    )
    from mongo_db import (
        admins_collection,
        answers_collection,
        candidates_collection,
        close_mongo,
        get_mongo_status,
        init_mongo,
        interview_sessions_collection,
        interviews_collection,
    )
    print("✅ Local modules imported.")
except ImportError as e:
    print(f"❌ CRITICAL: Local module import failed: {e}")
    traceback.print_exc()
    sys.exit(1)


# 5. System Configuration
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

UPLOAD_ROOT = os.getenv("UPLOAD_ROOT", "").strip()
# Cloud Run exposes K_SERVICE and supports writable ephemeral disk under /tmp only.
if not UPLOAD_ROOT and os.getenv("K_SERVICE"):
    UPLOAD_ROOT = os.path.join(tempfile.gettempdir(), "ai-interview")
if UPLOAD_ROOT:
    UPLOAD_FOLDER = os.path.join(UPLOAD_ROOT, "uploads")
else:
    UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 6. Cloudinary Configuration
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

if not all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
    print("⚠️ WARNING: Cloudinary environment variables are missing. Video uploads will fail.")
else:
    try:
        cloudinary.config(
            cloud_name=CLOUDINARY_CLOUD_NAME,
            api_key=CLOUDINARY_API_KEY,
            api_secret=CLOUDINARY_API_SECRET,
            secure=True
        )
        print("✅ Cloudinary configured successfully.")
    except Exception as e:
        print(f"❌ ERROR: Failed to configure Cloudinary: {e}")


CANONICAL_FRONTEND_URL = "https://ai-adaptive-interview-liart.vercel.app"
FRONTEND_URL = os.getenv("FRONTEND_URL", CANONICAL_FRONTEND_URL).rstrip("/")
if "ai-adaptive-interview.vercel.app" in FRONTEND_URL and "liart" not in FRONTEND_URL:
    FRONTEND_URL = CANONICAL_FRONTEND_URL
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "https://localhost:3000",
    "http://127.0.0.1:3000",
    "https://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
if FRONTEND_URL and FRONTEND_URL not in ALLOWED_ORIGINS:
    ALLOWED_ORIGINS.append(FRONTEND_URL)
EXTRA_FRONTEND_URLS = [
    url.strip().rstrip("/")
    for url in os.getenv("FRONTEND_URLS", "").split(",")
    if url.strip()
]
for url in EXTRA_FRONTEND_URLS:
    if url not in ALLOWED_ORIGINS:
        ALLOWED_ORIGINS.append(url)

# 8. App Initialization
app = FastAPI()
print("✅ FastAPI app instance created.")

# 9. Socket.IO Setup
try:
    socketio_cors_raw = os.getenv("SOCKETIO_CORS_ORIGINS", "*").strip()
    if socketio_cors_raw == "*":
        socketio_cors = "*"
    else:
        socketio_cors = [origin.strip() for origin in socketio_cors_raw.split(",") if origin.strip()]
    sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins=socketio_cors)
    print("✅ Socket.IO server initialized.")
except Exception as e:
    print(f"❌ CRITICAL: Socket.IO initialization failed: {e}")
    traceback.print_exc()
    sys.exit(1)

@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")

@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")

@sio.on("join_interview")
async def join_interview(sid, data):
    interview_id = data.get("interview_id")
    if interview_id:
        await sio.enter_room(sid, interview_id)
        print(f"Client {sid} joined room: {interview_id}")

@sio.on("candidate_update")
async def candidate_update(sid, data):
    interview_id = data.get("interview_id")
    if interview_id:
        # Broadcast metadata to everyone in the room (admin)
        await sio.emit("live_update", data, room=interview_id, skip_sid=sid)

@sio.on("video_frame")
async def video_frame(sid, data):
    # data is expected to be a dict with 'interview_id' and 'frame' (binary)
    interview_id = data.get("interview_id")
    frame = data.get("frame")
    if interview_id and frame:
        # Directly relay binary frame to admins in the room
        await sio.emit("live_frame", {"frame": frame, "timestamp": data.get("timestamp")}, room=interview_id, skip_sid=sid)

app.add_middleware(GZipMiddleware, minimum_size=1000)

# Health check for keeping Render awake
@app.get("/")
@app.get("/health")
@app.head("/")
@app.head("/health")
def health_check():
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mongo": get_mongo_status(),
    }

# Mount uploads folder to serve files
app.mount("/uploads", StaticFiles(directory=UPLOAD_FOLDER), name="uploads")


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage removed in favor of MongoDB persistence
# interviews = {}

def get_client():
    load_dotenv()
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("⚠️ Warning: OPENROUTER_API_KEY not found in environment")
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        http_client=httpx.Client(trust_env=False)
    )


def post_openrouter_chat(payload: Dict[str, Any], headers: Dict[str, str], timeout: int = 30):
    session = requests.Session()
    session.trust_env = False
    return session.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=timeout
    )

def get_or_create_candidate(name: str) -> str:
    row = candidates_collection.find_one({"name": name})

    if row:
        return str(row["_id"])

    result = candidates_collection.insert_one({
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    return str(result.inserted_id)


def get_interview_or_404(interview_id: str) -> Dict[str, Any]:
    """Fetch interview from MongoDB. Replaces in-memory lookup."""
    row = interviews_collection.find_one({"id": interview_id})
    if not row:
        raise HTTPException(status_code=404, detail="Interview not found")

    try:
        questions_raw = row.get("questions", "[]")
        loaded_questions = json.loads(questions_raw) if isinstance(questions_raw, str) else questions_raw
    except Exception:
        loaded_questions = []

    return {
        "id": interview_id,
        "source": row.get("source"),
        "profile_text": row.get("profile_text", ""),
        "questions": loaded_questions,
        "answers": {},  # Answers are stored in answers_collection
        "created_at": row.get("created_at"),
        "coding_round": row.get("coding_round"),
    }

def update_interview_state(interview_id: str, update_data: Dict[str, Any]):
    """Update interview state in MongoDB."""
    interviews_collection.update_one({"id": interview_id}, {"$set": update_data})

def validate_interview_session(interview_id: str):
    """Ensure interview exists and is valid."""
    return get_interview_or_404(interview_id)


def get_answer_history(interview_id: str) -> List[Dict[str, Any]]:
    return list(answers_collection.find({"interview_id": interview_id}).sort("question_id", 1))


def normalize_candidate_name(name: str) -> List[str]:
    cleaned = re.sub(r"[^a-zA-Z\s]", " ", (name or "").lower())
    tokens = [token for token in cleaned.split() if token]
    suffixes = {"mr", "mrs", "ms", "dr", "jr", "sr"}
    return [token for token in tokens if token not in suffixes]


def compare_candidate_names(manual_name: str, detected_name: str) -> Dict[str, Any]:
    manual_tokens = normalize_candidate_name(manual_name)
    detected_tokens = normalize_candidate_name(detected_name)
    if not manual_tokens or not detected_tokens:
        return {
            "manual_name": manual_name,
            "detected_name": detected_name,
            "similarity": 0.0,
            "matches": True,
            "reason": "insufficient_data",
        }

    manual_joined = " ".join(manual_tokens)
    detected_joined = " ".join(detected_tokens)
    sequence_score = SequenceMatcher(None, manual_joined, detected_joined).ratio()
    overlap_score = len(set(manual_tokens) & set(detected_tokens)) / max(len(set(manual_tokens)), len(set(detected_tokens)))
    subset_score = 0.92 if set(manual_tokens).issubset(set(detected_tokens)) or set(detected_tokens).issubset(set(manual_tokens)) else 0.0
    similarity = round(max(sequence_score, overlap_score, subset_score), 3)
    matches = similarity >= 0.7
    reason = "matched" if matches else "mismatch"
    return {
        "manual_name": manual_name,
        "detected_name": detected_name,
        "similarity": similarity,
        "matches": matches,
        "reason": reason,
    }


def build_candidate_session_link(link_id: str) -> str:
    return f"{FRONTEND_URL.rstrip('/')}/index.html?session_id={link_id}"


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def compute_integrity_report(session_data: Dict[str, Any], answers_data: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    answers_data = answers_data or []
    live_monitoring = session_data.get("live_monitoring") or {}
    violations = session_data.get("violations") or []

    totals = {
        "tab_switches": _safe_int(live_monitoring.get("tab_switch_count")) + sum(_safe_int(a.get("tab_switches")) for a in answers_data),
        "face_alerts": _safe_int(live_monitoring.get("face_alert_count")) + sum(_safe_int(a.get("face_alerts")) for a in answers_data),
        "multiple_faces": _safe_int(live_monitoring.get("multiple_face_count")),
        "invisible_face_count": _safe_int(live_monitoring.get("invisible_face_count")),
        "movement_violations": _safe_int(live_monitoring.get("movement_count")),
        "fullscreen_exits": _safe_int(live_monitoring.get("fullscreen_exit_count")),
        "background_noise_alerts": _safe_int(live_monitoring.get("background_noise_alerts")),
        "object_alerts": _safe_int(live_monitoring.get("object_alert_count")),
        "suspicious_behavior_count": _safe_int(live_monitoring.get("suspicious_behavior_count")),
        "violation_events": len(violations),
    }

    score = 100
    score -= totals["tab_switches"] * 6
    score -= totals["face_alerts"] * 2
    score -= totals["multiple_faces"] * 18
    score -= totals["invisible_face_count"] * 10
    score -= totals["movement_violations"] * 7
    score -= totals["fullscreen_exits"] * 10
    score -= totals["background_noise_alerts"] * 3
    score -= totals["object_alerts"] * 8
    score -= totals["suspicious_behavior_count"] * 4
    score = max(0, min(100, score))

    if session_data.get("auto_terminated"):
        risk_classification = "Critical"
    elif score >= 85:
        risk_classification = "Low"
    elif score >= 65:
        risk_classification = "Moderate"
    elif score >= 40:
        risk_classification = "High"
    else:
        risk_classification = "Critical"

    summary_bits = []
    if totals["multiple_faces"]:
        summary_bits.append(f"multiple faces detected {totals['multiple_faces']} time(s)")
    if totals["invisible_face_count"]:
        summary_bits.append(f"face missing {totals['invisible_face_count']} time(s)")
    if totals["movement_violations"]:
        summary_bits.append(f"camera/head instability recorded {totals['movement_violations']} time(s)")
    if totals["fullscreen_exits"]:
        summary_bits.append(f"fullscreen exited {totals['fullscreen_exits']} time(s)")
    if totals["tab_switches"]:
        summary_bits.append(f"tab switching detected {totals['tab_switches']} time(s)")
    if totals["background_noise_alerts"]:
        summary_bits.append(f"background noise threshold triggered {totals['background_noise_alerts']} time(s)")
    if not summary_bits:
        summary_bits.append("No major integrity anomalies were recorded.")

    return {
        **totals,
        "integrity_score": score,
        "risk_classification": risk_classification,
        "termination_reason": session_data.get("termination_reason", ""),
        "auto_terminated": bool(session_data.get("auto_terminated")),
        "camera_stability": "Unstable" if totals["movement_violations"] >= 3 else "Stable",
        "ai_summary": "Integrity review: " + "; ".join(summary_bits),
    }


def persist_integrity_evidence(interview_id: str, evidence_frame: str, label: str) -> str:
    if not evidence_frame or not evidence_frame.startswith("data:image/"):
        return ""
    try:
        header, encoded = evidence_frame.split(",", 1)
        extension = "jpg" if "jpeg" in header or "jpg" in header else "png"
        evidence_dir = os.path.join(UPLOAD_FOLDER, "integrity")
        os.makedirs(evidence_dir, exist_ok=True)
        filename = f"{interview_id}_{label}_{int(time.time())}.{extension}"
        file_path = os.path.join(evidence_dir, filename)
        with open(file_path, "wb") as handle:
            handle.write(base64.b64decode(encoded))
        return file_path.replace("\\", "/")
    except Exception as exc:
        print(f"Integrity evidence save failed: {exc}")
        return ""


def build_answer_summary(answers_data: List[Dict[str, Any]]) -> str:
    if not answers_data:
        return "No completed verbal answers were found."

    blocks = []
    for item in answers_data[-5:]:
        answer_text = (item.get("answer_text") or "").strip()
        if len(answer_text) > 280:
            answer_text = answer_text[:280].rstrip() + "..."
        blocks.append(
            f"Question: {item.get('question_text', '')}\n"
            f"Answer: {answer_text}\n"
            f"AI Score: {item.get('ai_score', 0)}"
        )
    return "\n\n".join(blocks)


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _question_pool_from_interview_doc(interview_doc: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not interview_doc:
        return []
    raw_questions = interview_doc.get("questions", [])
    if isinstance(raw_questions, list):
        return raw_questions
    try:
        return json.loads(raw_questions or "[]")
    except Exception:
        return []


def _derive_live_confidence_score(live_monitoring: Dict[str, Any], latest_answer_score: Optional[float] = None) -> float:
    explicit = live_monitoring.get("confidence_score")
    if explicit is not None:
        return round(_safe_float(explicit), 1)
    if latest_answer_score is not None:
        return round(_safe_float(latest_answer_score), 1)
    risk = _safe_float(live_monitoring.get("integrity_risk_score"))
    return round(max(0.0, min(100.0, 100.0 - risk)), 1)


def _derive_communication_score(
    live_monitoring: Dict[str, Any],
    latest_answer: Optional[Dict[str, Any]] = None,
) -> float:
    explicit = live_monitoring.get("communication_score")
    if explicit is not None:
        return round(_safe_float(explicit), 1)

    if latest_answer:
        wpm = _safe_float(latest_answer.get("wpm"))
        filler = _safe_int(latest_answer.get("filler_count"))
        pauses = _safe_int(latest_answer.get("pause_count"))
        keyword_pct = _safe_float(latest_answer.get("keyword_match_pct"))
        score = 68.0
        if wpm:
            if 95 <= wpm <= 165:
                score += 12
            elif wpm < 75:
                score -= 10
            elif wpm > 185:
                score -= 8
        score += min(keyword_pct * 0.12, 12)
        score -= min(filler * 2.5, 16)
        score -= min(pauses * 1.5, 10)
        return round(max(0.0, min(100.0, score)), 1)

    return round(max(0.0, min(100.0, 100.0 - (_safe_float(live_monitoring.get("integrity_risk_score")) * 0.45))), 1)


def _build_live_answers_snapshot(answer_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    snapshot = []
    for row in answer_rows[-5:]:
        answer_text = (row.get("answer_text") or "").strip()
        snapshot.append({
            "question_id": row.get("question_id"),
            "question_text": row.get("question_text") or "",
            "answer_text": answer_text,
            "answer_excerpt": (answer_text[:220].rstrip() + "...") if len(answer_text) > 220 else answer_text,
            "ai_score": row.get("ai_score"),
            "ai_feedback": row.get("ai_feedback") or "",
            "wpm": round(_safe_float(row.get("wpm")), 1),
            "pause_count": _safe_int(row.get("pause_count")),
            "filler_count": _safe_int(row.get("filler_count")),
            "keyword_match_pct": round(_safe_float(row.get("keyword_match_pct")), 1),
            "time_spent_seconds": _safe_int(row.get("time_spent_seconds")),
            "tab_switches": _safe_int(row.get("tab_switches")),
            "face_alerts": _safe_int(row.get("face_alerts")),
            "created_at": row.get("created_at"),
        })
    return snapshot


def _build_coding_round_snapshot(coding_round: Dict[str, Any]) -> Dict[str, Any]:
    if not coding_round:
        return {}

    latest_feedback = coding_round.get("latest_feedback") or {}
    latest_run = coding_round.get("latest_run") or {}
    latest_observation = coding_round.get("last_observation") or {}
    task = coding_round.get("task") or {}
    scorecard = latest_feedback.get("scorecard") or {}

    return {
        "status": coding_round.get("status") or "not_started",
        "language": coding_round.get("language") or task.get("recommended_language") or "python",
        "title": task.get("title") or "Live coding round",
        "difficulty": task.get("difficulty") or "Medium",
        "updated_at": coding_round.get("updated_at") or coding_round.get("started_at"),
        "latest_explanation": coding_round.get("latest_explanation") or "",
        "latest_code_excerpt": ((coding_round.get("latest_code") or "")[:320].rstrip() + "...") if len((coding_round.get("latest_code") or "")) > 320 else (coding_round.get("latest_code") or ""),
        "runtime_error": latest_run.get("runtime_error") or "",
        "hidden_passed": _safe_int((latest_run.get("hidden_summary") or {}).get("passed")),
        "hidden_total": _safe_int((latest_run.get("hidden_summary") or {}).get("total")),
        "coach_message": latest_feedback.get("coach_message") or "",
        "interviewer_prompt": latest_observation.get("interviewer_prompt") or "",
        "inferred_intent": latest_observation.get("inferred_intent") or "",
        "scorecard": {
            "problem_understanding": scorecard.get("problem_understanding"),
            "implementation": scorecard.get("implementation"),
            "communication": scorecard.get("communication"),
            "overall": scorecard.get("overall"),
        },
    }


def _build_live_dashboard_metrics(sessions: List[Dict[str, Any]]) -> Dict[str, Any]:
    ongoing_sessions = [s for s in sessions if (s.get("status") or "pending") == "started" and not s.get("is_deactivated", False)]
    speaking_count = 0
    live_coding_count = 0
    integrity_alert_count = 0
    monitoring_ready_count = 0
    confidence_values: List[float] = []
    active_sessions: List[Dict[str, Any]] = []

    for session in ongoing_sessions:
        live_monitoring = session.get("live_monitoring") or {}
        violations = session.get("violations") or []
        latest_answer_score = None
        interview_id = session.get("interview_id")
        if interview_id:
            latest_answer = answers_collection.find_one(
                {"interview_id": interview_id},
                sort=[("question_id", -1)],
            )
            latest_answer_score = latest_answer.get("ai_score") if latest_answer else None

        confidence_score = _derive_live_confidence_score(live_monitoring, latest_answer_score)
        confidence_values.append(confidence_score)

        if live_monitoring.get("speaking"):
            speaking_count += 1
        if (live_monitoring.get("phase") or "").lower() == "coding":
            live_coding_count += 1
        if live_monitoring.get("updated_at"):
            monitoring_ready_count += 1

        integrity_alert_count += (
            _safe_int(live_monitoring.get("multiple_face_count"))
            + _safe_int(live_monitoring.get("invisible_face_count"))
            + _safe_int(live_monitoring.get("movement_count"))
            + _safe_int(live_monitoring.get("fullscreen_exit_count"))
            + _safe_int(live_monitoring.get("tab_switch_count"))
            + _safe_int(live_monitoring.get("object_alert_count"))
            + len(violations)
        )

        active_sessions.append({
            "link_id": session.get("link_id"),
            "candidate_name": session.get("candidate_name") or "Candidate",
            "phase": live_monitoring.get("phase") or "verbal",
            "speaking": bool(live_monitoring.get("speaking")),
            "confidence_score": confidence_score,
            "integrity_risk_score": _safe_int(live_monitoring.get("integrity_risk_score")),
            "question_text": live_monitoring.get("current_question_text") or "",
            "updated_at": live_monitoring.get("updated_at") or session.get("last_activity_at") or session.get("created_at"),
        })

    return {
        "ongoing_count": len(ongoing_sessions),
        "live_session_count": len(ongoing_sessions),
        "monitoring_ready_count": monitoring_ready_count,
        "integrity_alert_count": integrity_alert_count,
        "avg_live_confidence_score": round(sum(confidence_values) / len(confidence_values), 1) if confidence_values else 0.0,
        "currently_speaking_count": speaking_count,
        "live_coding_sessions_count": live_coding_count,
        "active_sessions": active_sessions[:6],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def persist_coding_round(interview_id: str, coding_round: Dict[str, Any]) -> None:
    """Persist coding round state to MongoDB."""
    interviews_collection.update_one(
        {"id": interview_id},
        {"$set": {"coding_round": coding_round}},
        upsert=False,
    )


def build_coding_test_payload(coding_round: Dict[str, Any]) -> Dict[str, Any]:
    task = coding_round.get("task", {})
    test_cases = task.get("test_cases", [])
    visible = [case for case in test_cases if case.get("visible")]
    hidden = [case for case in test_cases if not case.get("visible")]
    return {
        "visible_cases": [
            {
                "id": case.get("id"),
                "input": case.get("input"),
                "output": case.get("expected"),
            }
            for case in visible[:3]
        ],
        "hidden_case_count": len(hidden[:4]),
        "total_case_count": len(test_cases[:7]),
    }


def _runner_error(message: str) -> Dict[str, Any]:
    return {
        "status": "error",
        "runtime_error": message,
        "visible_results": [],
        "hidden_summary": {"passed": 0, "total": 4},
    }


def _runner_tempdir():
    runner_tmp_root = os.path.abspath(os.path.join(UPLOAD_FOLDER, "runner_tmp"))
    os.makedirs(runner_tmp_root, exist_ok=True)
    runner_tmp_path = os.path.join(runner_tmp_root, f"run_{uuid.uuid4().hex}")

    class RunnerTempDir:
        def __enter__(self):
            os.makedirs(runner_tmp_path, exist_ok=False)
            return runner_tmp_path

        def __exit__(self, exc_type, exc, tb):
            py_shutil.rmtree(runner_tmp_path, ignore_errors=True)
            return False

    return RunnerTempDir()


def _collect_runner_output(result: subprocess.CompletedProcess) -> Dict[str, Any]:
    if result.returncode != 0:
        return _runner_error((result.stderr or result.stdout or "Unknown execution error").strip())

    try:
        all_results = json.loads(result.stdout.strip() or "[]")
    except Exception:
        return _runner_error("The runner returned an invalid response.")

    visible_results = [row for row in all_results if row.get("visible")]
    hidden_results = [row for row in all_results if not row.get("visible")]
    return {
        "status": "ok",
        "runtime_error": None,
        "visible_results": visible_results,
        "hidden_summary": {
            "passed": sum(1 for row in hidden_results if row.get("passed")),
            "total": len(hidden_results),
        },
        "all_passed": all(row.get("passed") for row in all_results) if all_results else False,
    }


def _supports_simple_multilang(value: Any) -> bool:
    if isinstance(value, (int, float, str, bool)) or value is None:
        return True
    if isinstance(value, list):
        return all(_supports_simple_multilang(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _supports_simple_multilang(item) for key, item in value.items())
    return False


def _js_literal(value: Any) -> str:
    return json.dumps(value)


def _java_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        if not value:
            return "new int[]{}"
        if all(isinstance(item, int) for item in value):
            return "new int[]{" + ", ".join(str(item) for item in value) + "}"
        if all(isinstance(item, str) for item in value):
            return "new String[]{" + ", ".join(json.dumps(item) for item in value) + "}"
    raise ValueError("This test input is not supported for Java execution.")


def _java_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "double"
    if isinstance(value, str):
        return "String"
    if isinstance(value, list):
        if not value:
            return "int[]"
        if all(isinstance(item, int) for item in value):
            return "int[]"
        if all(isinstance(item, str) for item in value):
            return "String[]"
    raise ValueError("Unsupported Java argument type.")


def _c_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value)
    raise ValueError("This test input is not supported for C execution.")


def _c_type(value: Any) -> str:
    if isinstance(value, bool):
        return "int"
    if isinstance(value, int):
        return "int"
    if isinstance(value, str):
        return "const char*"
    raise ValueError("Unsupported C argument type.")


def _normalize_runner_tests(task: Dict[str, Any], tests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    signature = task.get("starter_function_signature") or ""
    params = ""
    if "(" in signature and ")" in signature:
        params = signature.split("(", 1)[1].split(")", 1)[0]
    param_parts = [part.strip() for part in params.split(",") if part.strip()]
    single_list_arg = len(param_parts) == 1 and "list" in param_parts[0].lower()
    if not single_list_arg:
        return tests

    normalized = []
    for case in tests:
        item = dict(case)
        raw_input = item.get("input", [])
        if isinstance(raw_input, list):
            if len(raw_input) == 1 and isinstance(raw_input[0], list):
                normalized_input = raw_input
            else:
                normalized_input = [raw_input]
        else:
            normalized_input = [[raw_input]]
        item["input"] = normalized_input
        normalized.append(item)
    return normalized


def run_code_against_tests(code: str, task: Dict[str, Any], language: str) -> Dict[str, Any]:
    function_name = task.get("function_name") or "solve"
    tests = _normalize_runner_tests(task, task.get("test_cases", []))
    language = (language or "python").lower()

    if not code.strip():
        return _runner_error("No code was provided.")

    if language == "python":
        payload = {"function_name": function_name, "tests": tests}
        harness = f"""
import json
candidate_ns = {{}}
payload = json.loads({json.dumps(json.dumps(payload))})
code = {json.dumps(code)}
exec(code, candidate_ns)
func = candidate_ns.get(payload["function_name"])
if not callable(func):
    raise NameError(f"Function '{{payload['function_name']}}' was not found in the submitted code.")
results = []
for case in payload["tests"]:
    try:
        actual = func(*case["input"])
        passed = actual == case["expected"]
        results.append({{"id": case["id"], "visible": case["visible"], "passed": passed, "error": None}})
    except Exception as exc:
        results.append({{"id": case["id"], "visible": case["visible"], "passed": False, "error": f"{{type(exc).__name__}}: {{exc}}"}})
print(json.dumps(results))
"""
        with _runner_tempdir() as tmpdir:
            script_path = os.path.join(tmpdir, "runner.py")
            with open(script_path, "w", encoding="utf-8") as handle:
                handle.write(harness)
            try:
                result = subprocess.run([sys.executable, script_path], capture_output=True, text=True, timeout=8)
            except subprocess.TimeoutExpired:
                return _runner_error("Execution timed out after 8 seconds.")
        return _collect_runner_output(result)

    if language == "javascript":
        if not py_shutil.which("node"):
            return _runner_error("JavaScript runtime is not installed on the server.")
        if not all(_supports_simple_multilang(case.get("expected")) and all(_supports_simple_multilang(arg) for arg in case.get("input", [])) for case in tests):
            return _runner_error("This task uses inputs that are not supported for JavaScript execution in the current runner.")
        payload = {"function_name": function_name, "tests": tests}
        harness = f"""
const payload = JSON.parse({json.dumps(json.dumps(payload))});
{code}
function stableStringify(value) {{
  if (Array.isArray(value)) {{
    return `[${{value.map(stableStringify).join(',')}}]`;
  }}
  if (value && typeof value === 'object') {{
    return `{{${{Object.keys(value).sort().map((key) => `${{JSON.stringify(key)}}:${{stableStringify(value[key])}}`).join(',')}}}}`;
  }}
  return JSON.stringify(value);
}}
let fn = globalThis[payload.function_name];
if (typeof fn !== 'function') {{
  try {{
    fn = eval(payload.function_name);
  }} catch (err) {{
    fn = undefined;
  }}
}}
if (typeof fn !== 'function') {{
  throw new Error(`Function ${{payload.function_name}} was not found in the submitted code.`);
}}
const results = [];
for (const testCase of payload.tests) {{
  try {{
    const actual = fn(...testCase.input);
    const passed = stableStringify(actual) === stableStringify(testCase.expected);
    results.push({{ id: testCase.id, visible: testCase.visible, passed, error: null }});
  }} catch (err) {{
    results.push({{ id: testCase.id, visible: testCase.visible, passed: false, error: String(err) }});
  }}
}}
console.log(JSON.stringify(results));
"""
        with _runner_tempdir() as tmpdir:
            script_path = os.path.join(tmpdir, "runner.js")
            with open(script_path, "w", encoding="utf-8") as handle:
                handle.write(harness)
            try:
                result = subprocess.run(["node", script_path], capture_output=True, text=True, timeout=8)
            except subprocess.TimeoutExpired:
                return _runner_error("Execution timed out after 8 seconds.")
        return _collect_runner_output(result)

    if language == "java":
        if not py_shutil.which("javac") or not py_shutil.which("java"):
            return _runner_error("Java compiler/runtime is not installed on the server.")
        try:
            runner_cases = []
            for case in tests:
                args = ", ".join(_java_literal(arg) for arg in case.get("input", []))
                expected = _java_literal(case.get("expected"))
                runner_cases.append((case["id"], case["visible"], args, expected))
        except ValueError as exc:
            return _runner_error(str(exc))
        method_name = function_name
        runner_body = "\n".join(
            f"""
        try {{
            boolean passed = java.util.Objects.deepEquals(Solution.{method_name}({args}), {expected});
            results.add(new Result({case_id}, {str(visible).lower()}, passed, null));
        }} catch (Throwable err) {{
            results.add(new Result({case_id}, {str(visible).lower()}, false, err.toString()));
        }}
"""
            for case_id, visible, args, expected in runner_cases
        )
        runner = f"""
import java.util.*;

class Runner {{
    static class Result {{
        int id;
        boolean visible;
        boolean passed;
        String error;
        Result(int id, boolean visible, boolean passed, String error) {{
            this.id = id;
            this.visible = visible;
            this.passed = passed;
            this.error = error;
        }}
    }}

    public static void main(String[] args) {{
        List<Result> results = new ArrayList<>();
{runner_body}
        StringBuilder out = new StringBuilder("[");
        for (int i = 0; i < results.size(); i++) {{
            Result r = results.get(i);
            if (i > 0) out.append(",");
            out.append("{{\\"id\\":").append(r.id)
               .append(",\\"visible\\":").append(r.visible)
               .append(",\\"passed\\":").append(r.passed)
               .append(",\\"error\\":");
            if (r.error == null) out.append("null");
            else out.append("\\"").append(r.error.replace("\\\\", "\\\\\\\\").replace("\\"", "\\\\\\"")).append("\\"");
            out.append("}}");
        }}
        out.append("]");
        System.out.println(out.toString());
    }}
}}
"""
        with _runner_tempdir() as tmpdir:
            solution_path = os.path.join(tmpdir, "Solution.java")
            runner_path = os.path.join(tmpdir, "Runner.java")
            with open(solution_path, "w", encoding="utf-8") as handle:
                handle.write(code)
            with open(runner_path, "w", encoding="utf-8") as handle:
                handle.write(runner)
            compile_result = subprocess.run(["javac", solution_path, runner_path], capture_output=True, text=True, cwd=tmpdir, timeout=12)
            if compile_result.returncode != 0:
                return _runner_error((compile_result.stderr or compile_result.stdout).strip())
            try:
                result = subprocess.run(["java", "Runner"], capture_output=True, text=True, cwd=tmpdir, timeout=8)
            except subprocess.TimeoutExpired:
                return _runner_error("Execution timed out after 8 seconds.")
        return _collect_runner_output(result)

    if language == "c":
        if not py_shutil.which("gcc"):
            return _runner_error("C compiler is not installed on the server.")
        if not all(
            isinstance(case.get("expected"), (int, bool, str))
            and all(isinstance(arg, (int, bool, str)) for arg in case.get("input", []))
            for case in tests
        ):
            return _runner_error("This task uses inputs that are not supported for C execution in the current runner.")
        try:
            call_blocks = []
            for case in tests:
                args = ", ".join(_c_literal(arg) for arg in case.get("input", []))
                expected = _c_literal(case.get("expected"))
                if isinstance(case.get("expected"), str):
                    compare = f'strcmp({function_name}({args}), {expected}) == 0'
                else:
                    compare = f'{function_name}({args}) == {expected}'
                call_blocks.append(
                    f"""
    results[index++] = (struct Result){{{case["id"]}, {1 if case["visible"] else 0}, ({compare}), NULL}};
"""
                )
        except ValueError as exc:
            return _runner_error(str(exc))
        harness = f"""
#include <stdio.h>
#include <string.h>
{code}
struct Result {{ int id; int visible; int passed; const char* error; }};
int main() {{
    struct Result results[{len(tests)}];
    int index = 0;
{''.join(call_blocks)}
    printf("[");
    for (int i = 0; i < index; i++) {{
        if (i > 0) printf(",");
        printf("{{\\"id\\":%d,\\"visible\\":%s,\\"passed\\":%s,\\"error\\":null}}",
            results[i].id,
            results[i].visible ? "true" : "false",
            results[i].passed ? "true" : "false");
    }}
    printf("]");
    return 0;
}}
"""
        with _runner_tempdir() as tmpdir:
            c_path = os.path.join(tmpdir, "runner.c")
            exe_path = os.path.join(tmpdir, "runner.exe")
            with open(c_path, "w", encoding="utf-8") as handle:
                handle.write(harness)
            compile_result = subprocess.run(["gcc", c_path, "-o", exe_path], capture_output=True, text=True, timeout=12)
            if compile_result.returncode != 0:
                return _runner_error((compile_result.stderr or compile_result.stdout).strip())
            try:
                result = subprocess.run([exe_path], capture_output=True, text=True, timeout=8)
            except subprocess.TimeoutExpired:
                return _runner_error("Execution timed out after 8 seconds.")
        return _collect_runner_output(result)

    return _runner_error(f"Language '{language}' is not supported.")


def extract_skills(text: str) -> List[str]:
    """Extract skills from resume text."""
    skills = []
    common_skills = [
        # Programming Languages
        "Python", "JavaScript", "Java", "C++", "C#", "PHP", "Ruby", "Swift", "Kotlin", "Go", "Rust", "TypeScript",
        # Web Technologies
        "HTML", "CSS", "React", "Angular", "Vue.js", "Node.js", "Django", "Flask", "Spring", "ASP.NET", "Express.js",
        # Databases
        "SQL", "MySQL", "PostgreSQL", "MongoDB", "Oracle", "SQLite", "Redis", "Cassandra",
        # Cloud & DevOps
        "AWS", "Azure", "Google Cloud", "Docker", "Kubernetes", "Terraform", "Ansible", "Jenkins", "Git", "CI/CD",
        # Data Science
        "Data Science", "Machine Learning", "Deep Learning", "Data Analysis", "Pandas", "NumPy", "TensorFlow", "PyTorch", "scikit-learn",
        # Other
        "REST API", "GraphQL", "Microservices", "Agile", "Scrum", "TDD", "OOP", "Functional Programming"
    ]
    
    for skill in common_skills:
        if skill.lower() in text.lower():
            skills.append(skill)
    
    return list(dict.fromkeys(skills))[:8]  # Remove duplicates and limit to 8 skills

def analyze_resume_or_jd(text: str):
    prompt = f"""
    Analyze the following resume or job description and return STRICT JSON only:
    {{
      "skills": [],
      "projects": [],
      "tools_and_technologies": [],
      "experience_level": "",
      "domains": [],
      "important_keywords": []
    }}
    Content: {text}
    """

    try:
        response = get_client().chat.completions.create(
            model="google/gemini-2.0-flash-001", # OpenRouter model ID
            messages=[{"role": "user", "content": prompt}]
        )
        
        raw_text = response.choices[0].message.content
        # Extract JSON
        json_start = raw_text.find("{")
        json_end = raw_text.rfind("}") + 1
        return json.loads(raw_text[json_start:json_end])
    except Exception as e:
        print(f"OpenRouter Analysis Error: {e}")
        return {"skills": [], "projects": [], "tools_and_technologies": [], "experience_level": "Unknown", "domains": [], "important_keywords": []}
    
def extract_experiences(text: str) -> List[Dict]:
    """Extract work experiences from resume text."""
    experiences = []
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    for i, line in enumerate(lines):
        line_lower = line.lower()
        if len(line) > 90 or len(line.split()) > 14:
            continue
        if any(role in line_lower for role in ['developer', 'engineer', 'analyst', 'specialist', 'manager', 'designer', 'researcher', 'scientist']):
            exp = {
                "title": line,
                "company": lines[i+1] if i+1 < len(lines) and len(lines[i+1]) < 50 else "a company"
            }
            # Avoid adding duplicate experiences
            if not any(e['title'] == exp['title'] and e['company'] == exp['company'] for e in experiences):
                experiences.append(exp)
                if len(experiences) >= 3:  # Limit to 3 experiences
                    break
    
    return experiences

def extract_projects(text: str) -> List[Dict]:
    """Extract projects from resume text."""
    projects = []
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    for i, line in enumerate(lines):
        line_lower = line.lower()
        if ("project" in line_lower or "portfolio" in line_lower) and len(line.split()) < 5:
            project = {
                "name": line.replace("Project:", "").replace("project:", "").strip(),
                "description": lines[i+1] if i+1 < len(lines) and 10 < len(lines[i+1]) < 200 else ""
            }
            # Avoid adding duplicate projects
            if not any(p['name'] == project['name'] for p in projects):
                projects.append(project)
    
    return projects

def generate_resume_questions(resume_text: str) -> List[Dict[str, str]]:
    """Generate personalized interview questions based on resume content."""
    print("Generating personalized resume-specific questions...")
    
    # Extract structured information
    skills = extract_skills(resume_text)
    experiences = extract_experiences(resume_text)
    projects = extract_projects(resume_text)
    
    questions = []
    
    # 1. Self Introduction (First 2 questions)
    intro_questions = [
        {
            "id": 1,
            "question": "Can you please introduce yourself and tell us about your professional background?",
            "difficulty": "Easy",
            "type": "Self-Introduction",
            "category": "Basic"
        },
        {
            "id": 2,
            "question": "What motivated you to pursue a career in this field, and what are your key strengths?",
            "difficulty": "Easy",
            "type": "Self-Introduction",
            "category": "Background"
        }
    ]
    questions.extend(intro_questions)
    
    # 2. Basic Skills Questions (Questions 3-4)
    if skills:
        # Take top 2 skills for basic questions
        for skill in skills[:2]:
            questions.append({
                "id": len(questions) + 1,
                "question": f"How would you rate your proficiency in {skill} and what projects have you used it in?",
                "difficulty": "Easy",
                "type": "Technical",
                "category": f"{skill} Basics"
            })
    
    # 3. Experience Questions (Middle Questions)
    for i, exp in enumerate(experiences[:2]):  # Limit to 2 experiences
        company = exp.get('company', 'your previous role')
        title = exp.get('title', '')
        
        questions.append({
            "id": len(questions) + 1,
            "question": f"At {company} as a {title}, what were your key responsibilities and achievements?",
            "difficulty": "Medium",
            "type": "Experience",
            "category": "Work History"
        })
        
        # Add a follow-up question about challenges
        if i == 0:  # Only add one challenge question
            questions.append({
                "id": len(questions) + 1,
                "question": f"What was the most challenging project you worked on at {company} and how did you handle it?",
                "difficulty": "Medium",
                "type": "Problem-Solving",
                "category": "Work Challenges"
            })
    
    # 4. Advanced Skills Questions (After Experience)
    if len(skills) > 2:  # If we have more than 2 skills
        for skill in skills[2:4]:  # Take next 2 skills for advanced questions
            questions.append({
                "id": len(questions) + 1,
                "question": f"Can you explain a complex problem you solved using {skill}? What was your approach and what did you learn?",
                "difficulty": "Hard",
                "type": "Technical",
                "category": f"Advanced {skill}"
            })
    
    # 5. Project Questions (If we need more questions)
    if len(questions) < 8 and projects:  # If we don't have enough questions yet
        for proj in projects[:1]:  # Limit to 1 project
            title = proj.get('title', 'a project')
            
            questions.append({
                "id": len(questions) + 1,
                "question": f"Tell me about your project '{title}'. What was your role, and what technologies did you use?",
                "difficulty": "Medium",
                "type": "Project",
                "category": "Projects"
            })
    
    # 6. Future and Closing Questions (Last 2 questions)
    future_questions = [
        {
            "question": "What technical skills are you currently working to improve, and how are you going about it?",
            "difficulty": "Easy",
            "type": "Career Development",
            "category": "Future Goals"
        },
        {
            "question": "Where do you see your career in the next 3-5 years, and how does this position align with your goals?",
            "difficulty": "Medium",
            "type": "Career Goals",
            "category": "Future Planning"
        }
    ]
    
    # Add future questions with proper IDs
    for q in future_questions:
        questions.append({
            "id": len(questions) + 1,
            **q
        })
    
    # Ensure we have at least 10 questions
    generic_questions = [
        "Can you describe a time when you had to work under pressure to meet a tight deadline?",
        "How do you approach learning new technologies or programming languages?",
        "Can you explain a technical concept to someone who doesn't have a technical background?",
        "What development tools and IDEs are you most comfortable using, and why?",
        "How do you handle code reviews and feedback on your work?",
        "What version control systems have you worked with, and what's your experience with them?",
        "Can you describe your experience with testing and quality assurance processes?",
        "How do you stay updated with the latest industry trends and technologies?",
        "What's your approach to debugging complex issues in your code?",
        "Can you describe a time when you had to collaborate with a difficult team member and how you handled it?"
    ]
    
    # Add generic questions if we don't have enough
    while len(questions) < 10 and generic_questions:
        questions.append({
            "id": len(questions) + 1,
            "question": generic_questions.pop(0),
            "difficulty": "Medium",
            "type": "General",
            "category": "Professional Development"
        })
    
    # Ensure we don't have too many questions
    if len(questions) > 25:
        questions = questions[:25]
    
    print(f"Generated {len(questions)} questions for the interview")
    return questions

def extract_text_from_file(file_content: bytes, filename: str) -> str:
    """Extract text content from different file types."""
    file_extension = filename.lower().split('.')[-1]

    try:
        if file_extension == 'pdf':
            # Extract text from PDF
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text.strip()

        elif file_extension in ['docx', 'doc']:
            # Extract text from DOCX
            doc = Document(io.BytesIO(file_content))
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text.strip()

        elif file_extension == 'txt':
            # Handle plain text files
            return file_content.decode('utf-8')

        else:
            # Try to decode as UTF-8 text for other formats
            return file_content.decode('utf-8')

    except Exception as e:
        print(f"Error extracting text from {filename}: {e}")
        # Fallback: try to decode as UTF-8
        try:
            return file_content.decode('utf-8', errors='ignore')
        except:
            raise HTTPException(status_code=400, detail=f"Unable to process file {filename}. Supported formats: PDF, DOCX, TXT")

def generate_jd_questions(jd_text: str) -> List[Dict[str, str]]:
    """Generate interview questions based on Job Description using AI."""
    print("Generating questions from Job Description...")
    
    questions = [
        {
            "id": 1,
            "question": "Can you please introduce yourself and tell us why you are interested in this specific role?",
            "difficulty": "Easy",
            "type": "Self-Introduction",
            "category": "Basic"
        }
    ]

    prompt = f"""
    You are an expert technical recruiter constructing a rigorous interview.
    
    Job Description:
    {jd_text[:4000]}
    
    Task:
    1. EXTRACT top 5 critical technical keywords/skills from the Job Description (e.g., 'React', 'AWS', 'System Design').
    2. GENERATE 6 specific interview questions testing these exact skills.
       - The extracted keywords MUST be the focus of the questions.
       - Do NOT ask generic "soft skill" questions unless the JD emphasizes them.
       - Vary difficulty: Start with basic checks, move to scenario-based/hard problems.
       - Act as a real human interviewer. NEVER say "According to the job description" or "You mentioned in your resume". Just ask the question directly.
    
    Return STRICT JSON format:
    {{
        "extracted_keywords": ["Skill1", "Skill2", ...],
        "questions": [
            {{
                "question": "Specific question testing a skill...",
                "difficulty": "Medium",
                "type": "Technical",
                "category": "Skill Name"
            }}
        ]
    }}
    """

    try:
        response = get_client().chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.choices[0].message.content
        start = raw.find("{")
        end = raw.rfind("}") + 1
        data = json.loads(raw[start:end])
        
        # Log extracted keywords for debugging/logging
        print(f"✅ Extracted JD Keywords: {data.get('extracted_keywords', [])}")
        
        # Add generated questions to the list
        for q in data.get("questions", []):
            questions.append({
                "id": len(questions) + 1,
                "question": q["question"],
                "difficulty": q.get("difficulty", "Medium"),
                "type": q.get("type", "General"),
                "category": q.get("category", "JD Requirement")
            })

            
    except Exception as e:
        print(f"Error generating JD questions: {e}")
        
        # --- OFFLINE/FALLBACK MODE ---
        # If API fails, try to extract keywords manually using Regex/List
        common_keywords = [
            "Python", "Java", "React", "Angular", "Vue", "AWS", "Azure", "Docker", "Kubernetes", "SQL", 
            "NoSQL", "Git", "CI/CD", "Machine Learning", "AI", "Data Science", "Spring", "Node.js", 
            "JavaScript", "TypeScript", "C++", "C#", ".NET", "Go", "Rust", "Swift", "Kotlin", "Flutter"
        ]
        
        found_keywords = []
        for kw in common_keywords:
            if kw.lower() in jd_text.lower():
                found_keywords.append(kw)
        
        print(f"⚠️ Offline Mode: Found keywords {found_keywords}")
        
        if found_keywords:
            for i, kw in enumerate(found_keywords[:5]): # Top 5 matched
                questions.append({
                    "id": len(questions) + 1,
                    "question": f"Can you describe your experience with {kw} and a challenging problem you solved using it?",
                    "difficulty": "Medium",
                    "type": "Technical",
                    "category": f"{kw} Skill"
                })
        else:
             # Genuine Fallback if absolutely no keywords matched
             questions.extend([
                {
                    "id": 2,
                    "question": "What specifically attracted you to the technical requirements of this position?",
                    "difficulty": "Medium",
                    "type": "General",
                    "category": "Fit"
                },
                {
                    "id": 3,
                    "question": "Can you walk us through your most significant technical achievement relevant to this role?",
                    "difficulty": "Hard",
                    "type": "Project",
                    "category": "Experience"
                }
            ])

    return questions

def generate_mock_questions(text: str, source: str, num_questions: int = 6, resume_text: str = None, jd_text: str = None) -> List[Dict[str, str]]:
    """
    Generate structured interview questions.
    Structure: Self-Intro → Technical Middle → Closing
    
    When API is available: calls AI to generate dynamic middle questions.
    When API is down: uses smart keyword-extraction from resume/JD to build questions offline.
    """
    num_questions = max(4, num_questions)
    
    opening = [
        {
            "id": 1,
            "question": "Can you please introduce yourself and tell us why you are interested in this specific role?",
            "difficulty": "Easy",
            "type": "Self-Introduction",
            "category": "Basic"
        }
    ]
    
    closing = [
        {
            "question": "What do you consider your biggest strengths and weaknesses?",
            "difficulty": "Easy",
            "type": "Self-Assessment",
            "category": "Strengths & Weaknesses"
        },
        {
            "question": "Where do you see yourself in the next 5 years, and how does this role fit into that vision?",
            "difficulty": "Easy",
            "type": "Career Goals",
            "category": "Future Plans"
        }
    ]
    if num_questions >= 10:
        closing.append({
            "question": "Do you have any questions for us about the team, the role, or the company?",
            "difficulty": "Easy",
            "type": "Closing",
            "category": "Candidate Questions"
        })
    
    middle_count = num_questions - len(opening) - len(closing)
    middle_count = max(1, middle_count)
    
    middle_questions = []
    
    try:
        if "resume" in source.lower():
            ai_questions = generate_resume_questions(text)
        else:
            ai_questions = generate_jd_questions(text)
        
        for q in ai_questions:
            qtype = q.get("type", "").lower()
            qcat = q.get("category", "").lower()
            if any(x in qtype for x in ["self-intro", "introduction", "career", "future"]):
                continue
            if any(x in qcat for x in ["basic", "background", "future goals", "closing"]):
                continue
            middle_questions.append(q)
            
        print(f"✅ AI generated {len(middle_questions)} technical questions")
    except Exception as e:
        print(f"⚠️ AI question generation failed: {e}")
        print("📋 Falling back to smart offline question generator...")
    
    # ── OFFLINE FALLBACK: Extract skills/projects and build timeline-based questions ──
    if len(middle_questions) < middle_count:
        offline_questions = _generate_offline_questions(resume_text or "", jd_text or text, num_questions)
        middle_questions.extend(offline_questions)
        print(f"📋 Offline generator added {len(offline_questions)} questions")
    
    middle_questions = middle_questions[:middle_count]
    
    all_questions = []
    idx = 1
    
    for q in opening:
        q["id"] = idx
        all_questions.append(q)
        idx += 1
    for q in middle_questions:
        q["id"] = idx
        all_questions.append(q)
        idx += 1
    for q in closing:
        q["id"] = idx
        all_questions.append(q)
        idx += 1
    
    return all_questions


def _generate_offline_questions(resume_text: str, jd_text: str, total_count: int) -> List[Dict[str, str]]:
    """
    Intelligent Interview Coach Offline Generator
    Adapts based on Total Time (total_count) and Presence of Resume (Single vs Bulk).
    Ensures a continuous flow of questions spanning Self-Intro, Skills, Projects, JD, and HR.
    """
    import re
    questions = []
    
    has_resume = bool(resume_text and len(resume_text.strip()) > 50)
    text_to_parse = (resume_text + " " + jd_text).lower()
    jd_lower = jd_text.lower()
    
    # ── 1. Extract Technical Skills ──
    tech_keywords = [
        "Python", "Java", "JavaScript", "TypeScript", "React", "Angular", "Vue", "Node.js",
        "Express", "Django", "Flask", "FastAPI", "Spring Boot", "Spring", ".NET", "C#", "C++",
        "Go", "Rust", "Swift", "Kotlin", "Flutter", "React Native", "PHP", "Ruby", "Rails",
        "AWS", "Azure", "GCP", "Docker", "Kubernetes", "Jenkins", "CI/CD", "Terraform",
        "SQL", "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "DynamoDB",
        "Machine Learning", "Deep Learning", "TensorFlow", "PyTorch", "NLP", "Computer Vision",
        "REST API", "GraphQL", "Microservices", "System Design", "Data Structures",
        "Algorithms", "HTML", "CSS", "Tailwind", "Bootstrap", "Git", "Linux",
        "Agile", "Scrum", "JIRA", "Figma"
    ]
    
    resume_skills = [kw for kw in tech_keywords if kw.lower() in resume_text.lower()] if has_resume else []
    jd_skills = [kw for kw in tech_keywords if kw.lower() in jd_lower]
    
    generic_skills = ["programming fundamentals", "system architecture", "version control", "database design", "debugging"]
    hr_questions = [
        "Tell me about a time you faced a difficult challenge at work and how you overcame it.",
        "How do you handle tight deadlines or stressful situations?",
        "Describe a situation where you had a conflict with a team member. How was it resolved?",
        "What motivates you the most in your professional career?",
        "How do you prioritize your tasks when you have multiple urgent requests?",
        "Tell me about a time you had to learn a new concept quickly.",
        "What is your proudest professional achievement?",
        "Describe a time you failed or made a mistake. What did you learn from it?",
        "How do you ensure you stay updated with industry trends?",
        "Can you share an example of how you successfully worked in a remote or distributed team?"
    ]
    
    # We apportion the questions to ensure an endless stream depending on total_count
    target = max(10, total_count + 15) # Generate significantly more to ensure an endless flow
    
    # --- PHASE 1: SELF-INTRO / BACKGROUND ---
    if has_resume:
        questions.append({"question": "Can you briefly walk me through your professional journey and what led you to apply for this role?", "difficulty": "Easy", "type": "Background", "category": "Experience"})
        questions.append({"question": "What specifically caught your eye about this firm and the job description we posted?", "difficulty": "Easy", "type": "Motivation", "category": "Motivation"})
    else:
        questions.append({"question": "Could you provide a high-level overview of your background and your core expertise?", "difficulty": "Easy", "type": "Background", "category": "Experience"})
        questions.append({"question": "What is the single most important skill you bring to the table that aligns with this role?", "difficulty": "Easy", "type": "Motivation", "category": "Skills"})
        
    # --- PHASE 2: SKILLS ---
    skills_to_ask = resume_skills if resume_skills else jd_skills
    if not skills_to_ask: skills_to_ask = generic_skills
    skills_count = max(3, int(target * 0.25))
    
    for i in range(skills_count):
        skill = skills_to_ask[i % len(skills_to_ask)]
        if i % 3 == 0:
            q = f"How would you rate your proficiency with {skill}? Can you describe a significant project where you utilized it to solve a complex problem?"
        elif i % 3 == 1:
            q = f"What are some common pitfalls or challenges you encounter when working with {skill}, and how do you mitigate them?"
        else:
            q = f"If you were to mentor a junior developer on {skill}, what core principles would you emphasize?"
        questions.append({"question": q, "difficulty": "Medium", "type": "Technical", "category": f"{skill} Deep-Dive"})

    # --- PHASE 3: PROJECTS & EXPERIENCE ---
    projects_count = max(3, int(target * 0.25))
    if has_resume:
        project_patterns = [r'(?:project|built|developed|created|designed)\s*[:\-]?\s*([A-Z][A-Za-z0-9\s\-]{3,30})']
        found_projects = []
        for pattern in project_patterns:
            found_projects.extend([m.strip() for m in re.findall(pattern, resume_text, re.IGNORECASE) if len(m.strip()) > 3])
        found_projects = list(set(found_projects))
        
        for i in range(projects_count):
            proj = found_projects[i % len(found_projects)] if found_projects else "your most complex technical project"
            if i % 2 == 0:
                q = f"Let's discuss {proj}. Walk me through the architecture and the major technical decisions you made."
            else:
                q = f"Regarding {proj}, what was the most difficult bug or bottleneck you encountered and how did you resolve it?"
            questions.append({"question": q, "difficulty": "Hard", "type": "Project", "category": "Architecture"})
    else:
        for i in range(projects_count):
            if i % 2 == 0:
                q = "Tell me about the most impactful project you have delivered in your career. What was your specific contribution?"
            else:
                q = "Walk me through a project where the requirements were vague or constantly changing. How did you manage it?"
            questions.append({"question": q, "difficulty": "Medium", "type": "Project", "category": "Execution"})

    # --- PHASE 4: JOB DESCRIPTION COMPLIANCE ---
    jd_count = max(3, int(target * 0.25))
    jd_focus = jd_skills if jd_skills else ["the core tools required for this position", "our tech stack"]
    for i in range(jd_count):
        focus = jd_focus[i % len(jd_focus)]
        if i % 2 == 0:
            q = f"This role heavily involves {focus}. Could you share an experience that demonstrates your readiness for this?"
        else:
            q = f"In the context of the job description requiring strong {focus} expertise, how do you handle scalable architectures?"
        questions.append({"question": q, "difficulty": "Hard", "type": "Role Fit", "category": "JD Requirement"})

    # --- PHASE 5: HR / BEHAVIORAL ---
    hr_count = max(5, int(target * 0.25))
    for i in range(hr_count):
        q = hr_questions[i % len(hr_questions)]
        questions.append({"question": q, "difficulty": "Medium", "type": "Behavioral", "category": "HR/Culture"})

    return questions

def score_answer(question: str, answer: str):
    prompt = f"""
You are an interview evaluator.

Question:
{question}

Candidate Answer:
{answer}

Evaluate on:
1. Relevance
2. Clarity
3. Technical depth (if applicable)
4. Confidence

Return STRICT JSON only:
{{
  "score": 0-10,
  "feedback": "short constructive feedback",
  "keywords": ["keyword1", "keyword2"]
}}
"""

    response = get_client().chat.completions.create(
        model="openai/gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.choices[0].message.content
    start = raw.find("{")
    end = raw.rfind("}") + 1
    return json.loads(raw[start:end])

# --- ADAPTIVE INTERVIEW LOGIC ---

class NextQuestionRequest(BaseModel):
    interview_id: str
    current_question_id: int
    answer_text: str

class ViolationRequest(BaseModel):
    type: str
    count: int
    timestamp: str
    detail: str = ""
    phase: str = ""
    question_id: Optional[int] = None
    evidence_frame: str = ""


class LiveMonitoringUpdate(BaseModel):
    current_question_id: Optional[int] = None
    current_question_text: str = ""
    question_index: int = 0
    total_questions: int = 0
    progress_pct: float = 0
    phase: str = "verbal"
    elapsed_seconds: int = 0
    time_remaining_seconds: int = 0
    audio_level: float = 0
    speaking: bool = False
    silence_seconds: int = 0
    face_status: str = "Unknown"
    multiple_face_count: int = 0
    invisible_face_count: int = 0
    movement_count: int = 0
    fullscreen_exit_count: int = 0
    tab_switch_count: int = 0
    face_alert_count: int = 0
    background_noise_alerts: int = 0
    object_alert_count: int = 0
    suspicious_behavior_count: int = 0
    integrity_risk_score: int = 0
    integrity_health_status: str = "Monitoring"
    warnings: List[str] = []
    camera_frame: str = ""
    mic_active: bool = False
    interviewer_prompt: str = ""
    current_transcript: str = ""
    transcript_word_count: int = 0
    latest_answer_excerpt: str = ""
    currently_answering: bool = False
    communication_score: float = 0
    confidence_score: float = 0
    auto_terminated: bool = False
    termination_reason: str = ""


class IntegrityTerminationRequest(BaseModel):
    type: str
    reason: str
    count: int = 0
    timestamp: str
    phase: str = ""
    question_id: Optional[int] = None
    evidence_frame: str = ""
    interview_duration_seconds: int = 0

def generate_followup_question(answer_text: str, resume_context: str, jd_text: str, current_q_id: int, followup_streak: int) -> Dict:
    if followup_streak < 3:
        prompt = f"""
        You are an intelligent technical interviewer.
        
        Context:
        - Candidate Resume Summary: {resume_context[:1000]}...
        - Candidate's Last Answer: "{answer_text}"
        
        Task:
        Generate ONE follow-up interview question (JSON) to dig deeper into what the candidate just said.
        - Act as a human interviewer making a natural conversation. 
        - NEVER say "You mentioned in your answer" or "Based on your answer". Ask directly!
        - If they mentioned a Project, ask about architectural decisions or challenges in THAT project.
        - If they mentioned a specific Tech Stack (e.g., React, Python), ask a conceptual question about it.
        - If their answer was vague, ask them to clarify specific examples.
        
        Return STRICT JSON:
        {{
            "question": "The actual question string...",
            "difficulty": "Medium",
            "type": "Follow-up",
            "category": "Deep Dive"
        }}
        """
    else:
        prompt = f"""
        You are an intelligent technical interviewer.
        
        Context:
        - Job Description: {jd_text[:1000]}...
        
        Task:
        Change the topic and ask ONE new interview question (JSON) based strictly on the Job Description.
        - Act as a human interviewer making a natural conversation.
        - Frame the question based on the skills, requirements, or responsibilities mentioned in the JD.
        
        Return STRICT JSON:
        {{
            "question": "The actual question string...",
            "difficulty": "Medium",
            "type": "JD-Based",
            "category": "Role Requirement"
        }}
        """
    
    try:
        response = get_client().chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.choices[0].message.content
        start = raw.find("{")
        end = raw.rfind("}") + 1
        q_data = json.loads(raw[start:end])
        
        # Add ID
        q_data["id"] = current_q_id + 1
        return q_data
    except Exception as e:
        print(f"Error generating follow-up: {e}")
        # Raise error so the endpoint fails and frontend skips adaptive questions
        raise Exception("API Quota/Error (Offline Mode) - Follow-up generation skipped.")

@app.post("/generate-next-question")
def api_gen_next_question(req: NextQuestionRequest):
    interview = get_interview_or_404(req.interview_id)
    followup_streak = interview.get("followup_streak", 0)
    
    try:
        # Generate the question
        new_question = generate_followup_question(
            req.answer_text, 
            interview.get("profile_text", ""),
            interview.get("job_description", ""),
            req.current_question_id,
            followup_streak
        )
        
        if followup_streak >= 3:
            interview["followup_streak"] = 0
        else:
            interview["followup_streak"] = followup_streak + 1

    except Exception as e:
        # If API fails, return a 503 so frontend catches it and moves to next pre-generated question
        raise HTTPException(status_code=503, detail="AI generation failed")
    
    # Insert this new question into the list right after current
    # Find current index
    current_idx = -1
    for i, q in enumerate(interview["questions"]):
        if int(q["id"]) == req.current_question_id:
            current_idx = i
            break
            
    if current_idx != -1:
        # Check if we already have a follow-up (avoid infinite expansion if re-running)
        if current_idx + 1 < len(interview["questions"]):
             # If next question is already a "Follow-up", maybe replace it? 
             # For now, let's just INSERT it to be dynamic.
             # Shift IDs of subsequent questions
             for q in interview["questions"][current_idx+1:]:
                 q["id"] = int(q["id"]) + 1
                 
        interview["questions"].insert(current_idx + 1, new_question)
        
        # Update DB with new question list
        interviews_collection.update_one(
            {"id": req.interview_id}, 
            {"$set": {"questions": json.dumps(interview["questions"])}}
        )
        
        return new_question
    
    raise HTTPException(status_code=400, detail="Current question ID not found")


@app.post("/upload-resume")
@app.post("/upload-resume/")
async def upload_resume(
    file: UploadFile = File(...),
    source: str = Form("resume")
):
    try:
        print(f"Uploading resume with source: {source}")

        # Read file content
        content = await file.read()

        # Extract text based on file type
        content_str = extract_text_from_file(content, file.filename)

        if not content_str.strip():
            raise HTTPException(status_code=400, detail="No readable text found in the file")

        # Generate interview ID
        interview_id = f"int_{int(datetime.now(timezone.utc).timestamp())}_{uuid.uuid4().hex[:8]}"

        # Analyze the resume
        profile_analysis = analyze_resume_or_jd(content_str)

        # Generate questions
        questions = generate_mock_questions(content_str, source)

        if not questions:
            raise HTTPException(status_code=400, detail="Failed to generate questions")        # Store interview data (DB)
        try:
            interviews_collection.insert_one({
                "id": interview_id,
                "source": source,
                "profile_text": content_str[:5000],
                "profile_analysis": profile_analysis,
                "questions": json.dumps(questions),
                "created_at": datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            print(f"Failed to save generated interview profile to database: {e}")


        return {
            "interview_id": interview_id,
            "total_questions": len(questions),
            "first_question": questions[0]
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Upload error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process resume: {str(e)}")

@app.post("/start-interview")
@app.post("/start-interview/")
async def start_interview(
    content: str = Form(...),
    source: str = Form("resume")
):
    try:
        print(f"Starting interview with source: {source}")

        interview_id = f"int_{int(datetime.now(timezone.utc).timestamp())}_{uuid.uuid4().hex[:8]}"

        # ✅ STEP-3.2 → AI ANALYSIS (CORRECT PLACE)
        profile_analysis = analyze_resume_or_jd(content)

        # Generate questions based on Source (Resume vs JD)
        questions = generate_mock_questions(content, source)

        if not questions:
            raise HTTPException(status_code=400, detail="Failed to generate questions")

        # ✅ STE        # Store interview data (DB)
        try:
            interviews_collection.insert_one({
                "id": interview_id,
                "source": source,
                "profile_text": content[:5000],
                "profile_analysis": profile_analysis,
                "questions": json.dumps(questions),
                "created_at": datetime.now(timezone.utc).isoformat()
            })
        except Exception as db_e:
            print(f"⚠️ DB Save Error: {db_e}")
        return {
            "interview_id": interview_id,
            "total_questions": len(questions),
            "first_question": questions[0]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/interview/{interview_id}/question/{question_id}")
async def get_question(interview_id: str, question_id: int):
    """Fetch specific question from MongoDB."""
    interview = get_interview_or_404(interview_id)
    
    # Ensure ID comparison works (cast both to int)
    question = next((q for q in interview["questions"] if int(q["id"]) == int(question_id)), None)
    
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
        
    return {
        "current_question": question,
        "total_questions": len(interview["questions"]),
        "interview_id": interview_id
    }
# Add this import at the top

import base64

@app.post("/upload-answer")
async def upload_answer(
    interview_id: str = Form(...),
    question_id: int = Form(...),
    video: UploadFile = File(...)
):
    interview = get_interview_or_404(interview_id)

    with tempfile.TemporaryDirectory() as tmp:
        video_path = os.path.join(tmp, "input.webm")
        audio_path = os.path.join(tmp, "audio.wav")

        with open(video_path, "wb") as f:
            f.write(await video.read())

        # Extract audio using ffmpeg
        subprocess.run([
            "ffmpeg", "-i", video_path,
            "-ar", "16000",
            "-ac", "1",
            audio_path
        ], check=True)

        # Whisper STT

@app.get("/interview/{interview_id}/summary")
async def get_interview_summary(interview_id: str):
    """Get a summary of the interview including all questions and answers."""
    interview = get_interview_or_404(interview_id)
    
    # Fetch answers from DB
    answers = get_answer_history(interview_id)
    
    return {
        "interview_id": interview_id,
        "source": interview["source"],
        "created_at": interview["created_at"],
        "total_questions": len(interview["questions"]),
        "questions_answered": len(answers),
        "questions": interview["questions"],
        "answers": {str(a["question_id"]): a for a in answers}
    }
@app.get("/")
def root():
    return {"status": "Backend is running"}

class ChatRequest(BaseModel):
    message: str
@app.post("/chat")
def chat(req: ChatRequest):
    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "Voice Chatbot"
    }

    data = {
        "model": "openai/gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful interview assistant. Keep responses short."
            },
            {
                "role": "user",
                "content": req.message
            }
        ]
    }

    response = post_openrouter_chat(data, headers)

    return {
        "reply": response.json()["choices"][0]["message"]["content"]
    }

class AnswerRequest(BaseModel):
    interview_id: str
    candidate_name: str
    question_id: int
    question_text: str
    answer_text: str
    


@app.post("/save-answer")
async def save_answer(
    interview_id: str = Form(...),
    question_id: int = Form(...),
    question_text: str = Form(...),
    answer_text: str = Form(...),
    candidate_name: str = Form("Candidate")
):
    print(f"[answer-save] interview_id={interview_id} question_id={question_id} answer_chars={len(answer_text or '')}")
    print(f"💾 Saving answer for {question_id}...")
    
    # Get context from MongoDB
    context = ""
    try:
        interview = get_interview_or_404(interview_id)
        context = f"Candidate's {interview.get('source')}: {interview.get('profile_text')}"
    except Exception as e:
        print(f"⚠️ Context fetch error: {e}")

    # Use the robust analyze_answer function
    ai_result = analyze_answer(question_text, answer_text, context)

    # Prepare keywords (handle list or string)
    keywords = ai_result.get("keywords", [])
    if isinstance(keywords, list):
        keywords_str = ",".join(keywords)
    else:
        keywords_str = str(keywords)

    # Delete any existing answer for this question in this interview to avoid duplicates
    answers_collection.delete_many({"interview_id": interview_id, "question_id": question_id})
    
    answers_collection.insert_one({
        "interview_id": interview_id,
        "question_id": question_id,
        "question_text": question_text,
        "answer_text": answer_text,
        "ai_score": ai_result.get("overall_score", 0),
        "ai_feedback": ai_result.get("feedback", "No feedback"),
        "ai_keywords": keywords_str,
        "corrected_answer": ai_result.get("corrected_answer", "N/A"),
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    interview_sessions_collection.update_one(
        {"interview_id": interview_id},
        {"$set": {"last_activity_at": datetime.now(timezone.utc).isoformat()}},
    )

    print(
        f"[answer-save] persisted interview_id={interview_id} "
        f"question_id={question_id} ai_score={ai_result.get('overall_score', 0)}"
    )

    print("✅ Answer saved to DB.")

    return {
        "status": "saved",
        "ai_score": ai_result.get("overall_score", 0),
        "ai_feedback": ai_result.get("feedback", "")
    }


# ─── NEW: Save Behavioral / Proctoring Metrics per Question ───────────────────
class BehavioralData(BaseModel):
    interview_id: str
    question_id: int
    wpm: float = 0
    pause_count: int = 0
    filler_count: int = 0
    time_spent_seconds: int = 0
    keyword_match_pct: float = 0
    tab_switches: int = 0
    face_alerts: int = 0

@app.post("/save-behavioral-data")
def save_behavioral_data(data: BehavioralData):
    """Saves per-question behavioral and proctoring metrics"""
    try:
        print(
            f"[behavioral-save] interview_id={data.interview_id} question_id={data.question_id} "
            f"wpm={data.wpm} tab_switches={data.tab_switches} face_alerts={data.face_alerts}"
        )
        answers_collection.update_many(
            {"interview_id": data.interview_id, "question_id": data.question_id},
            {"$set": {
                "wpm": data.wpm,
                "pause_count": data.pause_count,
                "filler_count": data.filler_count,
                "time_spent_seconds": data.time_spent_seconds,
                "keyword_match_pct": data.keyword_match_pct,
                "tab_switches": data.tab_switches,
                "face_alerts": data.face_alerts
            }}
        )
        interview_sessions_collection.update_one(
            {"interview_id": data.interview_id},
            {"$set": {"last_activity_at": datetime.now(timezone.utc).isoformat()}},
        )
        return {"status": "ok"}
    except Exception as e:
        print(f"Behavioral save error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...),
    candidate_name: str = Form("Candidate")
):
    try:
        import whisper
    except ImportError:
        print("Whisper is not installed; keeping browser transcript fallback.")
        return {"text": "No speech detected", "transcription_available": False}

    data = await audio.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as f:
        f.write(data)
        path = f.name

    try:
        model = whisper.load_model("small")
        result = model.transcribe(
            path,
            language="en",
            task="transcribe",
            fp16=False,
            initial_prompt=(
                "This is a job interview. "
                f"The candidate's name is {candidate_name}. "
                "Proper nouns and technical terms may appear."
            ),
        )
        text = (result.get("text") or "").strip()
        return {"text": text or "No speech detected", "transcription_available": True}
    except Exception as e:
        print(f"Transcription failed: {e}")
        return {"text": "No speech detected", "transcription_available": False}
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


class CodingRoundStartRequest(BaseModel):
    interview_id: str


class CodingRoundCheckpointRequest(BaseModel):
    interview_id: str
    code: str = ""
    explanation: str = ""
    language: str = "python"


class CodingRoundSubmitRequest(CodingRoundCheckpointRequest):
    pass


class CodingRoundRunRequest(CodingRoundCheckpointRequest):
    pass


class CodingRoundObserveRequest(CodingRoundCheckpointRequest):
    pass


@app.post("/coding-round/start")
def start_coding_round(req: CodingRoundStartRequest):
    interview = get_interview_or_404(req.interview_id)
    answers_data = get_answer_history(req.interview_id)

    existing_round = interview.get("coding_round") or {}
    if existing_round.get("task"):
        return {
            "interview_id": req.interview_id,
            "coding_round": existing_round,
            "tests": build_coding_test_payload(existing_round),
            "resumed": True,
        }

    profile_text = interview.get("profile_text", "")
    task = generate_coding_task(profile_text, answers_data)
    coding_round = {
        "status": "active",
        "task": task,
        "answer_summary": build_answer_summary(answers_data),
        "language": task.get("recommended_language", "python"),
        "latest_code": "",
        "latest_explanation": "",
        "latest_feedback": "",
        "checkpoints": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    persist_coding_round(req.interview_id, coding_round)
    return {
        "interview_id": req.interview_id,
        "coding_round": coding_round,
        "tests": build_coding_test_payload(coding_round),
        "resumed": False,
    }


@app.get("/coding-round/{interview_id}")
def get_coding_round(interview_id: str):
    interview = get_interview_or_404(interview_id)
    coding_round = interview.get("coding_round")
    if not coding_round:
        raise HTTPException(status_code=404, detail="Coding round not started")
    return {"interview_id": interview_id, "coding_round": coding_round, "tests": build_coding_test_payload(coding_round)}


def _run_coding_feedback(req: CodingRoundCheckpointRequest, feedback_mode: str) -> Dict[str, Any]:
    interview = get_interview_or_404(req.interview_id)
    coding_round = interview.get("coding_round")
    if not coding_round or not coding_round.get("task"):
        raise HTTPException(status_code=400, detail="Coding round not started")

    latest_code = req.code or ""
    latest_explanation = req.explanation or ""
    unchanged = (
        latest_code.strip() == (coding_round.get("latest_code", "") or "").strip()
        and latest_explanation.strip() == (coding_round.get("latest_explanation", "") or "").strip()
        and coding_round.get("latest_feedback")
        and feedback_mode == "checkpoint"
    )
    if unchanged:
        return {
            "interview_id": req.interview_id,
            "coding_round": coding_round,
            "feedback": coding_round.get("latest_feedback"),
            "cached": True,
        }

    feedback = run_coding_round(
        task=coding_round["task"],
        answer_summary=coding_round.get("answer_summary", ""),
        code=latest_code,
        explanation=latest_explanation,
        language=req.language,
        prior_feedback=coding_round.get("latest_feedback", ""),
        feedback_mode=feedback_mode,
    )

    checkpoint = {
        "at": datetime.now(timezone.utc).isoformat(),
        "language": req.language,
        "code_length": len(latest_code),
        "explanation_length": len(latest_explanation),
        "feedback": feedback,
        "mode": feedback_mode,
    }

    coding_round["latest_code"] = latest_code
    coding_round["latest_explanation"] = latest_explanation
    coding_round["language"] = req.language
    coding_round["latest_feedback"] = feedback
    coding_round["updated_at"] = checkpoint["at"]
    coding_round.setdefault("checkpoints", []).append(checkpoint)
    if feedback_mode == "final":
        coding_round["status"] = "completed"
        coding_round["final_evaluation"] = feedback
        coding_round["completed_at"] = checkpoint["at"]

    persist_coding_round(req.interview_id, coding_round)
    return {
        "interview_id": req.interview_id,
        "coding_round": coding_round,
        "feedback": feedback,
        "cached": False,
    }


@app.post("/coding-round/checkpoint")
def coding_round_checkpoint(req: CodingRoundCheckpointRequest):
    return _run_coding_feedback(req, "checkpoint")


@app.post("/coding-round/submit")
def coding_round_submit(req: CodingRoundSubmitRequest):
    return _run_coding_feedback(req, "final")


@app.post("/coding-round/run")
def coding_round_run(req: CodingRoundRunRequest):
    interview = get_interview_or_404(req.interview_id)
    coding_round = interview.get("coding_round")
    if not coding_round or not coding_round.get("task"):
        raise HTTPException(status_code=400, detail="Coding round not started")
    result = run_code_against_tests(req.code or "", coding_round["task"], req.language or "python")
    coding_round["latest_code"] = req.code or ""
    coding_round["latest_explanation"] = req.explanation or coding_round.get("latest_explanation", "")
    coding_round["language"] = req.language or "python"
    coding_round["latest_run"] = {
        "at": datetime.now(timezone.utc).isoformat(),
        **result,
    }
    persist_coding_round(req.interview_id, coding_round)
    return {
        "interview_id": req.interview_id,
        "run_result": result,
        "tests": build_coding_test_payload(coding_round),
    }


@app.post("/coding-round/observe")
def coding_round_observe(req: CodingRoundObserveRequest):
    interview = get_interview_or_404(req.interview_id)
    coding_round = interview.get("coding_round")
    if not coding_round or not coding_round.get("task"):
        raise HTTPException(status_code=400, detail="Coding round not started")

    observation = observe_coding_intent(
        task=coding_round["task"],
        code=req.code or "",
        explanation=req.explanation or "",
        language=req.language or "python",
    )
    coding_round["last_observation"] = {
        "at": datetime.now(timezone.utc).isoformat(),
        **observation,
    }
    persist_coding_round(req.interview_id, coding_round)
    return {"interview_id": req.interview_id, "observation": observation}

@app.get("/interview/{interview_id}/ai-summary")
def interview_ai_summary(interview_id: str):
    answers = answers_collection.find({"interview_id": interview_id, "ai_score": {"$ne": None}})
    scores = [a.get("ai_score", 0) for a in answers]
    avg_score = round(sum(scores) / len(scores), 2) if scores else 0

    return {
        "interview_id": interview_id,
        "average_score": avg_score,
        "total_questions": len(scores)
    }

# ─── Helper: Generate AI Summary (Recommendation + S&W) ─────────────────────
def generate_interview_summary(candidate_name: str, answers_data: list) -> dict:
    """
    Given list of {question, answer, ai_score, ai_feedback},
    produce an overall recommendation and strengths/weaknesses summary.
    """
    if not answers_data:
        return {
            "recommendation": "No Data",
            "strengths": "No answers provided.",
            "weaknesses": "No answers provided."
        }

    avg = sum(a.get("ai_score", 0) or 0 for a in answers_data) / len(answers_data)

    qa_block = "\n".join(
        f"Q{i+1}: {a['question_text']}\nA: {a['answer_text']}\nScore: {a.get('ai_score',0)}/100"
        for i, a in enumerate(answers_data)
    )

    prompt = f"""
You are a senior hiring manager reviewing an interview for {candidate_name}.
Here is the full transcript:

{qa_block}

Average score: {avg:.1f}/100

Please respond in JSON with exactly three keys:
- "recommendation": one of "Strong Hire", "Hire", "Borderline", "No Hire"
- "strengths": 2-3 sentence paragraph on what the candidate did well
- "weaknesses": 2-3 sentence paragraph on where the candidate needs improvement
"""

    try:
        response = get_client().chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.choices[0].message.content
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception as e:
        print(f"Summary generation error: {e}")
        # Fallback from score
        if avg >= 75:
            rec = "Strong Hire"
        elif avg >= 55:
            rec = "Hire"
        elif avg >= 35:
            rec = "Borderline"
        else:
            rec = "No Hire"
        return {
            "recommendation": rec,
            "strengths": "Summary generation failed — please review individual scores.",
            "weaknesses": "Summary generation failed — please review individual scores."
        }


@app.get("/admin/interview/{link_id}")
def get_interview_details(link_id: str):
    # 1. Fetch session metadata
    session_data = interview_sessions_collection.find_one({"link_id": link_id})
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")

    candidate_name = session_data.get("candidate_name")
    created_at = session_data.get("created_at")
    jd = session_data.get("job_description")
    actual_interview_id = session_data.get("interview_id")
    saved_rec = session_data.get("overall_recommendation")
    saved_str = session_data.get("strengths_summary")
    saved_wk = session_data.get("weaknesses_summary")
    saved_avg = session_data.get("avg_score")
    current_status = session_data.get("status")
    candidate_email = session_data.get("candidate_email")
    live_monitoring = session_data.get("live_monitoring") or {}
    violations = session_data.get("violations") or []
    question_pool: List[Dict[str, Any]] = []
    coding_snapshot: Dict[str, Any] = {}
    monitoring_state = "idle"

    # Disabled: admin result reads must not mutate candidate session status.
    if False and current_status == 'started' and actual_interview_id:
        if answers_collection.find_one({"interview_id": actual_interview_id}):
            print(f"🔄 Fallback: Marking session {link_id} as completed because results exist.")
            interview_sessions_collection.update_one({"link_id": link_id}, {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc).isoformat()}})

    # Fetch recording path from interviews table
    recording_url = None
    interview_doc = None
    if actual_interview_id:
        rec_row = interviews_collection.find_one({"id": actual_interview_id})
        interview_doc = rec_row
        question_pool = _question_pool_from_interview_doc(interview_doc)
        coding_snapshot = _build_coding_round_snapshot((interview_doc or {}).get("coding_round") or {})
        if rec_row and rec_row.get("recording_path"):
            # Convert absolute path to a relative URL path
            raw_path = rec_row["recording_path"].replace("\\", "/")
            # Extract the part starting with "uploads/"
            idx = raw_path.find("uploads/")
            if idx != -1:
                recording_url = raw_path[idx:]

    results = []
    total_tab_switches = 0
    total_face_alerts = 0
    total_time = 0
    answer_rows: List[Dict[str, Any]] = []

    if actual_interview_id:
        answer_rows = list(answers_collection.find({"interview_id": actual_interview_id}).sort("question_id", 1))
        rows = answer_rows

        for row in rows:
            tab_sw = row.get("tab_switches") or 0
            face_al = row.get("face_alerts") or 0
            total_tab_switches += tab_sw
            total_face_alerts += face_al
            total_time += (row.get("time_spent_seconds") or 0)

            results.append({
                "question_id": row.get("question_id"),
                "question_text": row.get("question_text"),
                "answer_text": row.get("answer_text") or "(No answer yet)",
                "ai_score": row.get("ai_score"),
                "ai_feedback": row.get("ai_feedback") or "No feedback provided",
                "corrected_answer": row.get("corrected_answer") or "N/A",
                "wpm": round(row.get("wpm") or 0, 1),
                "pause_count": row.get("pause_count") or 0,
                "filler_count": row.get("filler_count") or 0,
                "time_spent_seconds": row.get("time_spent_seconds") or 0,
                "keyword_match_pct": round(row.get("keyword_match_pct") or 0, 1),
                "tab_switches": tab_sw,
                "face_alerts": face_al,
                "created_at": row.get("created_at")
            })

    # 2. Calculate or restore AI summary
    avg_score = 0
    if results:
        scores = [r["ai_score"] for r in results if r["ai_score"] is not None]
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    recommendation = saved_rec or "In Progress"
    strengths = saved_str or "Interview is still in progress."
    weaknesses = saved_wk or "Final evaluation will be generated after completion."
    summary_ready = current_status == "completed"

    if summary_ready:
        if saved_rec:
            recommendation = saved_rec
            strengths = saved_str
            weaknesses = saved_wk
        else:
            summary = generate_interview_summary(candidate_name or "Candidate", results)
            recommendation = summary.get("recommendation", "No Data")
            strengths = summary.get("strengths", "")
            weaknesses = summary.get("weaknesses", "")
            try:
                interview_sessions_collection.update_one(
                    {"link_id": link_id},
                    {"$set": {
                        "overall_recommendation": recommendation,
                        "strengths_summary": strengths,
                        "weaknesses_summary": weaknesses,
                        "avg_score": avg_score
                    }}
                )
            except Exception as e:
                print(f"Summary cache error: {e}")

    integrity_report = compute_integrity_report(session_data, answer_rows if actual_interview_id else [])
    latest_answer = answer_rows[-1] if answer_rows else None
    latest_answer_score = latest_answer.get("ai_score") if latest_answer else None
    live_confidence_score = _derive_live_confidence_score(live_monitoring, latest_answer_score)
    communication_score = _derive_communication_score(live_monitoring, latest_answer)
    total_questions = len(question_pool)
    live_question_index = _safe_int(live_monitoring.get("question_index")) or _safe_int(live_monitoring.get("current_question_id")) or len(answer_rows)
    if total_questions and live_question_index > total_questions:
        live_question_index = total_questions
    progress_pct = _safe_float(live_monitoring.get("progress_pct"))
    if progress_pct <= 0 and total_questions:
        progress_pct = round(min(100.0, (max(live_question_index, len(answer_rows)) / total_questions) * 100.0), 1)
    elif progress_pct <= 0 and answer_rows:
        progress_pct = round(min(100.0, len(answer_rows) * 5.0), 1)
    updated_at = live_monitoring.get("updated_at") or session_data.get("last_activity_at") or created_at
    updated_dt = _parse_iso_datetime(updated_at)
    if current_status == "completed":
        monitoring_state = "completed"
    elif updated_dt:
        age_seconds = max(0, int((datetime.now(timezone.utc) - updated_dt).total_seconds()))
        monitoring_state = "live" if age_seconds <= 12 else ("stale" if age_seconds <= 45 else "disconnected")
    current_transcript = (live_monitoring.get("current_transcript") or "").strip()
    submitted_answers_snapshot = _build_live_answers_snapshot(answer_rows)
    current_answer_state = "listening"
    if live_monitoring.get("currently_answering"):
        current_answer_state = "answering"
    elif (live_monitoring.get("phase") or "").lower() == "coding":
        current_answer_state = "coding"
    elif latest_answer:
        current_answer_state = "submitted"
    print(
        f"[admin-live] link_id={link_id} status={current_status} answers={len(answer_rows)} "
        f"violations={len(violations)} monitoring_state={monitoring_state}"
    )

    return {
        "interview_id": link_id,
        "actual_interview_id": actual_interview_id,
        "candidate_name": candidate_name or "Candidate",
        "date": created_at,
        "source": "Job Description / Resume",
        "avg_score": avg_score,
        "overall_recommendation": recommendation,
        "strengths_summary": strengths,
        "weaknesses_summary": weaknesses,
        "recording_url": recording_url,
        "decision": session_data.get("decision"),
        "session_status": current_status,
        "summary_ready": summary_ready,
        "monitoring_state": monitoring_state,
        "last_activity_at": session_data.get("last_activity_at"),
        "live_monitoring": live_monitoring,
        "violations": violations,
        "termination_reason": session_data.get("termination_reason", ""),
        "auto_terminated": bool(session_data.get("auto_terminated")),
        "progress": {
            "current_question_id": live_monitoring.get("current_question_id"),
            "question_index": live_question_index,
            "total_questions": total_questions,
            "progress_pct": progress_pct,
            "phase": live_monitoring.get("phase") or "verbal",
            "currently_answering": bool(live_monitoring.get("currently_answering")),
            "elapsed_seconds": _safe_int(live_monitoring.get("elapsed_seconds")),
            "time_remaining_seconds": _safe_int(live_monitoring.get("time_remaining_seconds")),
        },
        "live_answer_stream": {
            "current_transcript": current_transcript,
            "transcript_word_count": _safe_int(live_monitoring.get("transcript_word_count")),
            "latest_answer_excerpt": live_monitoring.get("latest_answer_excerpt") or (submitted_answers_snapshot[-1]["answer_excerpt"] if submitted_answers_snapshot else ""),
            "current_answer_state": current_answer_state,
            "submitted_answers": submitted_answers_snapshot,
        },
        "live_analytics": {
            "confidence_score": live_confidence_score,
            "communication_score": communication_score,
            "speaking": bool(live_monitoring.get("speaking")),
            "audio_level": round(_safe_float(live_monitoring.get("audio_level")), 3),
            "silence_seconds": _safe_int(live_monitoring.get("silence_seconds")),
            "integrity_risk_score": _safe_int(live_monitoring.get("integrity_risk_score")),
        },
        "candidate_monitoring": {
            "camera_frame": live_monitoring.get("camera_frame") or "",
            "face_status": live_monitoring.get("face_status") or "Unknown",
            "mic_active": bool(live_monitoring.get("mic_active")),
            "warnings": live_monitoring.get("warnings") or [],
            "interviewer_prompt": live_monitoring.get("interviewer_prompt") or "",
            "updated_at": updated_at,
        },
        "coding_snapshot": coding_snapshot,
        "integrity": {
            "total_tab_switches": total_tab_switches,
            "total_face_alerts": total_face_alerts,
            "total_time_minutes": round(total_time / 60, 1)
        },
        "integrity_report": integrity_report,
        "answers": results
    }

class AnalyzeRequest(BaseModel):
    interview_id: Optional[str] = None
    question_id: Optional[int] = None
    question: str
    answer: str

class DecisionRequest(BaseModel):
    link_id: str
    decision: str # 'selected' or 'rejected'
    admin_id: Optional[str] = None

@app.post("/analyze-answer")
def analyze(req: AnalyzeRequest):
    """Analyze answer using context from MongoDB."""
    context = ""
    if req.interview_id:
        try:
            interview = get_interview_or_404(req.interview_id)
            context = f"Candidate's {interview.get('source')}: {interview.get('profile_text')}"
        except Exception as e:
            print(f"⚠️ Context fetch error: {e}")
    
    result = analyze_answer(req.question, req.answer, context)

    # Delete existing to avoid duplicates
    answers_collection.delete_many({"interview_id": req.interview_id, "question_id": req.question_id})

    # Store in DB
    try:
        answers_collection.insert_one({
            "interview_id": req.interview_id,
            "question_id": req.question_id,
            "question_text": req.question,
            "answer_text": req.answer,
            "ai_score": result.get("overall_score", 0),
            "ai_feedback": result.get("feedback", ""),
            "ai_keywords": json.dumps(result.get("keywords", [])),
            "corrected_answer": result.get("corrected_answer", ""),
            "created_at": datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
        print(f"⚠️ Failed to save answer to DB: {e}")

    return result

@app.post("/upload-full-recording")
async def upload_full_recording(
    interview_id: str = Form(...),
    file: UploadFile = File(...)
):
    try:
        if is_gridfs_enabled():
            try:
                gridfs_info = store_recording(file, interview_id)
                recording_url = build_recording_url(gridfs_info["file_id"])
                interviews_collection.update_one(
                    {"id": interview_id},
                    {"$set": {
                        "recording_path": recording_url,
                        "recording_url": recording_url,
                        "recording_gridfs_id": gridfs_info["file_id"],
                        "recording_bucket": gridfs_info["bucket"],
                        "storage_type": "gridfs"
                    }}
                )
                return {
                    "status": "success",
                    "file_path": recording_url,
                    "storage_type": "gridfs",
                    "file_id": gridfs_info["file_id"]
                }
            except Exception as gridfs_error:
                print(f"⚠️ GridFS upload failed: {gridfs_error}")
                raise HTTPException(status_code=500, detail="GridFS upload failed")
        else:
            print(f"Uploading recording for interview {interview_id} to Cloudinary (GRIDFS_ENABLED is false)...")

            # Upload to Cloudinary
            # We use resource_type="video" for webm files
            upload_result = cloudinary.uploader.upload(
                file.file,
                resource_type="video",
                public_id=f"interviews/{interview_id}_full",
                overwrite=True
            )

            video_url = upload_result.get("secure_url")
            print(f"Cloudinary upload successful: {video_url}")

            # Update database with the persistent URL
            interviews_collection.update_one(
                {"id": interview_id},
                {"$set": {
                    "recording_path": video_url,
                    "recording_url": video_url,
                    "storage_type": "cloudinary"
                }}
            )

            return {"status": "success", "file_path": video_url, "storage_type": "cloudinary"}
    except Exception as e:
        print(f"Error uploading to Cloudinary: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/recordings/gridfs/{file_id}")
def stream_gridfs_recording(file_id: str):
    try:
        grid_out = open_recording_stream(file_id)
        return StreamingResponse(
            grid_out,
            media_type=(grid_out.metadata or {}).get("content_type", "video/webm")
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))


from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from fastapi.responses import FileResponse

@app.get("/generate-report/{interview_id}")
def generate_report(interview_id: str):
    # Fetch interview data
    interview_data = interviews_collection.find_one({"id": interview_id})
    if not interview_data:
        raise HTTPException(status_code=404, detail="Interview not found")
    
    source = interview_data.get("source")
    date = interview_data.get("created_at")
    profile_text = interview_data.get("profile_text")
    
    # Fetch Q&A data
    answers_cursor = answers_collection.find({"interview_id": interview_id}).sort("question_id", 1)
    answer_docs = list(answers_cursor)
    answers = [(a.get("question_text"), a.get("answer_text"), a.get("ai_score"), a.get("ai_feedback"), a.get("corrected_answer")) for a in answer_docs]
    session_data = interview_sessions_collection.find_one({"interview_id": interview_id}) or {}
    integrity_report = compute_integrity_report(session_data, answer_docs)
    
    # Generate PDF
    pdf_filename = f"Interview_Report_{interview_id}.pdf"
    file_path = os.path.join(UPLOAD_FOLDER, pdf_filename)
    
    doc = SimpleDocTemplate(file_path, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title_style = styles['Title']
    story.append(Paragraph(f"Interview Report", title_style))
    story.append(Spacer(1, 12))
    
    # Meta Info
    normal_style = styles['Normal']
    story.append(Paragraph(f"<b>Interview ID:</b> {interview_id}", normal_style))
    story.append(Paragraph(f"<b>Date:</b> {format_datetime_for_display(date)}", normal_style))
    story.append(Paragraph(f"<b>Source:</b> {source}", normal_style))
    story.append(Spacer(1, 12))
    
    # Calculate Average Score
    if answers:
        scores = [row[2] for row in answers if row[2] is not None]
        avg_score = sum(scores) / len(scores) if scores else 0
        
        # Color code overall score
        color = "green" if avg_score >= 60 else "orange" if avg_score >= 40 else "red"
        story.append(Paragraph(f"<b>Overall Score:</b> <font color='{color}' size='14'>{avg_score:.1f}/100</font>", normal_style))
    else:
        story.append(Paragraph("<b>Overall Score:</b> N/A", normal_style))
    
    story.append(Spacer(1, 20))

    story.append(Paragraph("<b>Integrity Summary</b>", styles['Heading3']))
    story.append(Paragraph(f"<b>Integrity Score:</b> {integrity_report.get('integrity_score', 0)}/100", normal_style))
    story.append(Paragraph(f"<b>Risk Classification:</b> {integrity_report.get('risk_classification', 'Low')}", normal_style))
    story.append(Paragraph(f"<b>Multiple Faces:</b> {integrity_report.get('multiple_faces', 0)} | <b>Invisible Face:</b> {integrity_report.get('invisible_face_count', 0)} | <b>Movement:</b> {integrity_report.get('movement_violations', 0)}", normal_style))
    story.append(Paragraph(f"<b>Tab Switches:</b> {integrity_report.get('tab_switches', 0)} | <b>Fullscreen Exits:</b> {integrity_report.get('fullscreen_exits', 0)} | <b>Noise Alerts:</b> {integrity_report.get('background_noise_alerts', 0)}", normal_style))
    if integrity_report.get('termination_reason'):
        story.append(Paragraph(f"<b>Termination Reason:</b> {integrity_report.get('termination_reason')}", normal_style))
    story.append(Paragraph(integrity_report.get('ai_summary', 'Integrity review unavailable.'), normal_style))
    story.append(Spacer(1, 18))
    
    # Q&A Details
    for i, row in enumerate(answers):
        q_text, a_text, score, feedback, verified_answer = row
        
        # Question Header
        story.append(Paragraph(f"<b>Q{i+1}: {q_text}</b>", styles['Heading3']))
        story.append(Spacer(1, 5))
        
        # Your Answer
        a_text_disp = a_text if a_text else "(No answer recorded)"
        story.append(Paragraph(f"<b>Your Answer:</b> {a_text_disp}", normal_style))
        story.append(Spacer(1, 5))
        
        # AI Feedback & Score
        score_str = f"{score}/100" if score is not None else "N/A"
        feedback_str = feedback if feedback else "No feedback provided."
        
        # Color score (Green > 60, Red < 60)
        score_color = "green" if (score and score >= 60) else "red"
        
        story.append(Paragraph(f"<b>Score:</b> <font color='{score_color}'><b>{score_str}</b></font>", normal_style))
        story.append(Paragraph(f"<b>Feedback:</b> {feedback_str}", normal_style))
        
        # Suggested Answer (if verified answer exists and is different/better)
        if verified_answer:
             story.append(Spacer(1, 5))
             story.append(Paragraph(f"<b>Suggested/Corrected Answer:</b>", normal_style))
             story.append(Paragraph(f"<i>{verified_answer}</i>", normal_style))
             
        story.append(Spacer(1, 15))
        story.append(Paragraph("<hr width='100%'/>", normal_style)) # Separator using simplified HR if supported or just lines
        # Reportlab doesn't support <hr> well in Paragraph, use drawing or character separator
        # story.append(Paragraph("_" * 80, normal_style)) 
        
        story.append(Spacer(1, 15))

    doc.build(story)
    
    # Return the PDF file directly for download
    return FileResponse(
        path=file_path,
        filename=pdf_filename,
        media_type="application/pdf"
    )

# --------------------------------------------------------------------------------
# ADMIN & SESSION MANAGEMENT APIs
# --------------------------------------------------------------------------------

import hashlib

class AdminLogin(BaseModel):
    username: str
    password: str

class CreateSession(BaseModel):
    candidate_name: str
    candidate_email: str
    resume_text: str
    job_description: str
    admin_id: str
    interview_duration: int = 30  # minutes
    record_video: bool = True
    custom_email_html: str = ""  # Task 1: Admin-editable email content
    scheduled_start: str = ""  # Task 4: ISO datetime for scheduled start
    scheduled_end: str = ""    # Task 4: ISO datetime for scheduled end
    resume_detected_name: str = ""
    resume_name_similarity: float = 0
    resume_name_confirmed: bool = False

class ForgotPasswordRequest(BaseModel):
    username: str
    email: str

class VerifyOTPRequest(BaseModel):
    username: str
    otp: str

class ResetPasswordRequest(BaseModel):
    username: str
    otp: str
    new_password: str

class UpdateProfileRequest(BaseModel):
    admin_id: str
    email: str

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

EMAIL_SCHEDULER_STARTED = False
JOB_DESCRIPTION_PDF_THRESHOLD = 900

def parse_iso_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
        return parsed
    except Exception:
        return None

def format_datetime_for_display(value: str) -> str:
    """Parse ISO datetime and return a formatted IST string."""
    dt = parse_iso_datetime(value)
    if not dt:
        return value
    # Convert to IST (UTC+5:30)
    ist_offset = timezone(timedelta(hours=5, minutes=30))
    ist_dt = dt.astimezone(ist_offset)
    return ist_dt.strftime("%d %b %Y, %I:%M %p")

def should_attach_job_description_pdf(job_description: str) -> bool:
    text = (job_description or "").strip()
    return len(text) > JOB_DESCRIPTION_PDF_THRESHOLD or text.count("\n") > 12

def generate_job_description_pdf_base64(job_description: str) -> str:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left_margin = 50
    top = height - 60
    line_height = 16

    pdf.setTitle("Job Description")
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(left_margin, top, "Job Description")
    y = top - 28

    pdf.setFont("Helvetica", 10)
    for paragraph in (job_description or "").splitlines() or [""]:
        wrapped_lines = simpleSplit(paragraph or " ", "Helvetica", 10, width - (left_margin * 2))
        for line in wrapped_lines:
            if y < 60:
                pdf.showPage()
                pdf.setFont("Helvetica", 10)
                y = height - 60
            pdf.drawString(left_margin, y, line)
            y -= line_height
        y -= 6

    pdf.save()
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")

def build_job_description_block(job_description: str) -> str:
    text = (job_description or "").strip()
    if not text:
        return '<p style="margin: 0; color: #64748b; font-size: 14px; line-height: 1.5;">Not provided</p>'

    if should_attach_job_description_pdf(text):
        summary = html.escape(textwrap.shorten(" ".join(text.split()), width=260, placeholder="..."))
        return (
            '<p style="margin: 0 0 8px; color: #64748b; font-size: 14px; line-height: 1.6;">'
            f'{summary}</p>'
            '<p style="margin: 0; color: #475569; font-size: 13px; line-height: 1.5;">'
            'The full job description is attached as a PDF so the email stays clean and easy to read.'
            '</p>'
        )

    formatted_jd = "<br/>".join(html.escape(line) for line in text.splitlines()) or html.escape(text)
    return f'<p style="margin: 0; color: #64748b; font-size: 14px; line-height: 1.5;">{formatted_jd}</p>'

def build_schedule_block(scheduled_start: str = "", scheduled_end: str = "") -> str:
    if not scheduled_start:
        return ""

    schedule_block = f'<p><b>Scheduled Time:</b> {format_datetime_for_display(scheduled_start)}'
    end_dt = parse_iso_datetime(scheduled_end) if scheduled_end else None
    if end_dt:
        # For the end time, we just need the time part in IST
        ist_offset = timezone(timedelta(hours=5, minutes=30))
        ist_end_dt = end_dt.astimezone(ist_offset)
        schedule_block += f' - {ist_end_dt.strftime("%I:%M %p")} (IST)'
    else:
        schedule_block += ' (IST)'
    schedule_block += '</p>'
    schedule_block += (
        '<p style="color: #e74c3c;"><b>Important:</b> '
        'This interview can only be accessed during the scheduled timeline, and the invitation email is sent 15 minutes before the start time.'
        '</p>'
    )
    return schedule_block

def build_default_interview_email_html(candidate_name: str, duration: int, job_description: str, full_link: str, scheduled_start: str = "", scheduled_end: str = "") -> str:
    schedule_block = build_schedule_block(scheduled_start, scheduled_end)
    job_description_block = build_job_description_block(job_description)
    safe_candidate_name = html.escape((candidate_name or "").strip() or "Not provided")
    duration_label = f"{duration} minutes" if isinstance(duration, int) and duration > 0 else "Not provided"

    return f"""
    <html>
    <body style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f8fafc;">
        <div style="background: linear-gradient(135deg, #6366f1, #8b5cf6); border-radius: 12px 12px 0 0; padding: 30px; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 24px;">Interview Invitation</h1>
        </div>
        <div style="background: white; border-radius: 0 0 12px 12px; padding: 30px; border: 1px solid #e2e8f0; border-top: none;">
            <p style="font-size: 16px; color: #334155;">Dear <b>{safe_candidate_name}</b>,</p>
            <p style="color: #475569; line-height: 1.6;">You have been invited to an AI-powered interview by <b style="color: #6366f1;">Arah Info Tech</b>.</p>
            <div style="background: #f1f5f9; border-radius: 8px; padding: 15px; margin: 15px 0; border-left: 4px solid #6366f1;">
                <p style="margin: 0 0 5px; font-weight: 600; color: #334155;">Role Details:</p>
                {job_description_block}
            </div>
            <p style="color: #475569;"><b>Duration:</b> {duration_label}</p>
            {schedule_block}
            <div style="text-align: center; margin: 25px 0;">
                <a href="{full_link}" style="background: linear-gradient(135deg, #6366f1, #8b5cf6); color: white; padding: 14px 32px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px; display: inline-block; box-shadow: 0 4px 12px rgba(99,102,241,0.3);">
                    Start Interview
                </a>
            </div>
            <div style="background: #fef3c7; border-radius: 8px; padding: 12px; margin-top: 15px;">
                <p style="margin: 0; color: #92400e; font-size: 13px;"><b>Important:</b> Please join only during the scheduled time window. If no schedule is set, the link remains valid for 24 hours.</p>
            </div>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
            <p style="color: #94a3b8; font-size: 13px; margin: 0;">Best regards,<br/><b style="color: #6366f1;">Arah Info Tech Pvt Ltd</b></p>
        </div>
    </body>
    </html>
    """

def compute_invite_send_at(scheduled_start: str = "") -> Optional[datetime]:
    start_dt = parse_iso_datetime(scheduled_start)
    if not start_dt:
        return None
    return start_dt - timedelta(minutes=15)

def queue_or_send_interview_email(session_doc: Dict[str, Any], link_url: str) -> Dict[str, Any]:
    scheduled_start = session_doc.get("scheduled_start", "")
    send_at = compute_invite_send_at(scheduled_start)
    now = datetime.now(timezone.utc)

    if send_at and send_at > now:
        interview_sessions_collection.update_one(
            {"_id": session_doc["_id"]},
            {"$set": {
                "invite_email_status": "pending",
                "invite_email_send_at": send_at.isoformat(),
                "invite_email_sent_at": None
            }}
        )
        return {
            "email_sent": False,
            "email_scheduled": True,
            "email_send_at": send_at.isoformat()
        }

    email_sent = send_interview_email(
        candidate_email=session_doc.get("candidate_email", ""),
        candidate_name=session_doc.get("candidate_name", ""),
        link_url=link_url,
        duration=session_doc.get("interview_duration", 30),
        job_description=session_doc.get("job_description", ""),
        custom_html=session_doc.get("custom_email_html", ""),
        scheduled_start=session_doc.get("scheduled_start", ""),
        scheduled_end=session_doc.get("scheduled_end", "")
    )

    interview_sessions_collection.update_one(
        {"_id": session_doc["_id"]},
        {"$set": {
            "invite_email_status": "sent" if email_sent else "failed",
            "invite_email_send_at": (send_at.isoformat() if send_at else now.isoformat()),
            "invite_email_sent_at": (now.isoformat() if email_sent else None)
        }}
    )
    return {
        "email_sent": email_sent,
        "email_scheduled": False,
        "email_send_at": (send_at.isoformat() if send_at else now.isoformat())
    }

def send_interview_email(candidate_email: str, candidate_name: str, link_url: str, duration: int, job_description: str, custom_html: str = "", scheduled_start: str = "", scheduled_end: str = ""):
    import os
    import requests
    from dotenv import load_dotenv
    load_dotenv(override=True)
    brevo_api_key = os.getenv("BREVO_API_KEY")
    sender_name = os.getenv("BREVO_SENDER_NAME", "Arah Info Tech Pvt ltd")
    sender_email = os.getenv("BREVO_SENDER_EMAIL", "oragantisagar041@gmail.com")

    if not brevo_api_key:
        print("⚠️ Warning: BREVO_API_KEY not found in environment")
        return False
    
    print(f"DEBUG: Using Brevo API key: {brevo_api_key[:10]}...{brevo_api_key[-5:] if len(brevo_api_key) > 5 else ''}")
    print(f"DEBUG: Sender Email: {sender_email}")
        
    # Prepare the job description by replacing newlines with HTML line breaks
    formatted_jd = job_description.replace("\n", "<br/>")

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": brevo_api_key,
        "content-type": "application/json"
    }

    # Construct the base URL for the interview link
    # On Render, FRONTEND_URL should be set to your Vercel URL
    full_link = link_url if link_url.startswith("http") else f"{os.getenv('FRONTEND_URL', 'https://ai-adaptive-interview-liart.vercel.app')}{link_url}"

    # Task 4: Build schedule info block
    schedule_block = ""
    if scheduled_start:
        try:
            from datetime import datetime as dt_parse
            start_dt = dt_parse.fromisoformat(scheduled_start)
            schedule_block = f'<p><b>Scheduled Time:</b> {start_dt.strftime("%d %b %Y, %I:%M %p")}'
            if scheduled_end:
                end_dt = dt_parse.fromisoformat(scheduled_end)
                schedule_block += f' — {end_dt.strftime("%I:%M %p")}'
            schedule_block += '</p>'
            schedule_block += '<p style="color: #e74c3c;"><b>⚠️ Important:</b> This link will only be accessible during the scheduled time window. It will be sent 15 minutes before the start time.</p>'
        except Exception:
            pass

    # Task 1: Use custom HTML if provided by admin, else use default template
    if custom_html and custom_html.strip():
        html_content = custom_html
    else:
        html_content = f"""
    <html>
    <body style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f8fafc;">
        <div style="background: linear-gradient(135deg, #6366f1, #8b5cf6); border-radius: 12px 12px 0 0; padding: 30px; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 24px;">Interview Invitation</h1>
        </div>
        <div style="background: white; border-radius: 0 0 12px 12px; padding: 30px; border: 1px solid #e2e8f0; border-top: none;">
            <p style="font-size: 16px; color: #334155;">Dear <b>{candidate_name}</b>,</p>
            <p style="color: #475569; line-height: 1.6;">You have been invited to an AI-powered interview by <b style="color: #6366f1;">Arah Info Tech</b>.</p>
            <div style="background: #f1f5f9; border-radius: 8px; padding: 15px; margin: 15px 0; border-left: 4px solid #6366f1;">
                <p style="margin: 0 0 5px; font-weight: 600; color: #334155;">📋 Role Details:</p>
                <p style="margin: 0; color: #64748b; font-size: 14px; line-height: 1.5;">{formatted_jd}</p>
            </div>
            <p style="color: #475569;"><b>⏱️ Duration:</b> {duration} minutes</p>
            {schedule_block}
            <div style="text-align: center; margin: 25px 0;">
                <a href="{full_link}" style="background: linear-gradient(135deg, #6366f1, #8b5cf6); color: white; padding: 14px 32px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px; display: inline-block; box-shadow: 0 4px 12px rgba(99,102,241,0.3);">
                    🚀 Start Interview Now
                </a>
            </div>
            <div style="background: #fef3c7; border-radius: 8px; padding: 12px; margin-top: 15px;">
                <p style="margin: 0; color: #92400e; font-size: 13px;">⚠️ <b>Important:</b> This interview link will expire in exactly <b>24 hours</b>. Ensure a stable internet connection and a quiet environment.</p>
            </div>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
            <p style="color: #94a3b8; font-size: 13px; margin: 0;">Best regards,<br/><b style="color: #6366f1;">Arah Info Tech Pvt Ltd</b></p>
        </div>
    </body>
    </html>
    """

    payload = {
        "sender": {
            "name": sender_name,
            "email": sender_email
        },
        "to": [{"email": candidate_email, "name": candidate_name}],
        "subject": "Interview Invitation by Arah Info Tech",
        "htmlContent": html_content
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        print(f"Email successfully sent to {candidate_email}")
        return True
    except Exception as e:
        print(f"Failed to send email to {candidate_email}: {e}")
        return False


# ── Task 1: Email Preview Endpoint ──────────────────────────────────────────
def send_interview_email(candidate_email: str, candidate_name: str, link_url: str, duration: int, job_description: str, custom_html: str = "", scheduled_start: str = "", scheduled_end: str = ""):
    import os
    import requests
    from dotenv import load_dotenv

    load_dotenv(override=True)
    brevo_api_key = os.getenv("BREVO_API_KEY")
    sender_name = os.getenv("BREVO_SENDER_NAME", "Arah Info Tech Pvt ltd")
    sender_email = os.getenv("BREVO_SENDER_EMAIL", "oragantisagar041@gmail.com")

    if not brevo_api_key:
        print("Warning: BREVO_API_KEY not found in environment")
        return False

    full_link = link_url if link_url.startswith("http") else f"{os.getenv('FRONTEND_URL', 'https://ai-adaptive-interview-liart.vercel.app')}{link_url}"

    html_content = custom_html.strip() if custom_html and custom_html.strip() else build_default_interview_email_html(
        candidate_name=candidate_name,
        duration=duration,
        job_description=job_description,
        full_link=full_link,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end
    )
    html_content = html_content.replace("{{INTERVIEW_LINK}}", full_link)

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": candidate_email, "name": candidate_name}],
        "subject": "Interview Invitation by Arah Info Tech",
        "htmlContent": html_content
    }

    if should_attach_job_description_pdf(job_description):
        payload["attachment"] = [{
            "name": "job_description.pdf",
            "content": generate_job_description_pdf_base64(job_description)
        }]

    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers={
                "accept": "application/json",
                "api-key": brevo_api_key,
                "content-type": "application/json"
            }
        )
        response.raise_for_status()
        print(f"Email successfully sent to {candidate_email}")
        return True
    except Exception as e:
        print(f"Failed to send email to {candidate_email}: {e}")
        return False


class EmailPreviewRequest(BaseModel):
    candidate_name: str
    candidate_email: str
    job_description: str
    duration: int = 30
    scheduled_start: str = ""
    scheduled_end: str = ""

@app.post("/admin/preview-email")
def preview_email(data: EmailPreviewRequest):
    """Return the default email HTML for admin to edit before sending."""
    return {
        "html": build_default_interview_email_html(
            candidate_name=data.candidate_name,
            duration=data.duration,
            job_description=data.job_description,
            full_link="{{INTERVIEW_LINK}}",
            scheduled_start=data.scheduled_start,
            scheduled_end=data.scheduled_end
        )
    }


# ── Task 3: Submission Notification Email ────────────────────────────────────
def preview_email_v2(data: EmailPreviewRequest):
    return {
        "html": build_default_interview_email_html(
            candidate_name=data.candidate_name,
            duration=data.duration,
            job_description=data.job_description,
            full_link="{{INTERVIEW_LINK}}",
            scheduled_start=data.scheduled_start,
            scheduled_end=data.scheduled_end
        )
    }

for _route in app.routes:
    if getattr(_route, "path", "") == "/admin/preview-email" and "POST" in getattr(_route, "methods", set()):
        _route.endpoint = preview_email_v2
        break

def send_submission_notification(candidate_email: str, candidate_name: str, admin_email: str, avg_score: float, total_questions: int):
    """Send test submission notification to both admin and candidate."""
    load_dotenv(override=True)
    api_key = os.getenv("BREVO_API_KEY")
    sender_name = os.getenv("BREVO_SENDER_NAME", "Arah Info Tech Pvt ltd")
    sender_email_addr = os.getenv("BREVO_SENDER_EMAIL")
    if not api_key:
        return False

    # Email to candidate
    candidate_html = f"""
    <html><body style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #10b981, #059669); border-radius: 12px 12px 0 0; padding: 25px; text-align: center;">
            <h2 style="color: white; margin: 0;">✅ Interview Submitted Successfully</h2>
        </div>
        <div style="background: white; border-radius: 0 0 12px 12px; padding: 25px; border: 1px solid #e2e8f0;">
            <p>Dear <b>{candidate_name}</b>,</p>
            <p>Thank you for completing your AI-powered interview. Your responses have been successfully submitted and are now being reviewed.</p>
            <div style="background: #f0fdf4; border-radius: 8px; padding: 15px; margin: 15px 0; text-align: center;">
                <p style="margin: 0; color: #166534; font-size: 14px;">📊 <b>Questions Answered:</b> {total_questions}</p>
            </div>
            <p style="color: #64748b;">Our recruitment team will review your performance and get back to you shortly. Please keep an eye on your email for further updates.</p>
            <p style="color: #94a3b8; font-size: 13px;">Best regards,<br/><b style="color: #6366f1;">Arah Info Tech Pvt Ltd</b></p>
        </div>
    </body></html>
    """

    # Email to admin
    score_color = "#10b981" if avg_score >= 60 else "#ef4444"
    admin_html = f"""
    <html><body style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #6366f1, #8b5cf6); border-radius: 12px 12px 0 0; padding: 25px; text-align: center;">
            <h2 style="color: white; margin: 0;">📋 New Interview Submission</h2>
        </div>
        <div style="background: white; border-radius: 0 0 12px 12px; padding: 25px; border: 1px solid #e2e8f0;">
            <p>A candidate has completed their interview:</p>
            <div style="background: #f1f5f9; border-radius: 8px; padding: 15px; margin: 15px 0;">
                <p style="margin: 5px 0;"><b>👤 Candidate:</b> {candidate_name}</p>
                <p style="margin: 5px 0;"><b>📧 Email:</b> {candidate_email}</p>
                <p style="margin: 5px 0;"><b>📊 Questions Answered:</b> {total_questions}</p>
                <p style="margin: 5px 0;"><b>🏆 Average Score:</b> <span style="color: {score_color}; font-weight: 700; font-size: 18px;">{avg_score:.1f}/100</span></p>
            </div>
            <p style="color: #64748b;">Login to the admin panel to review the full results, video recording, and AI analysis.</p>
            <p style="color: #94a3b8; font-size: 13px;">— AI Interview System</p>
        </div>
    </body></html>
    """

    results = []
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {"api-key": api_key, "content-type": "application/json"}

    # Send to candidate
    try:
        res = requests.post(url, json={
            "sender": {"name": sender_name, "email": sender_email_addr},
            "to": [{"email": candidate_email, "name": candidate_name}],
            "subject": "Your Interview Has Been Submitted — Arah Info Tech",
            "htmlContent": candidate_html
        }, headers=headers)
        results.append(res.status_code < 300)
    except Exception:
        results.append(False)

    # Send to admin
    if admin_email:
        try:
            res = requests.post(url, json={
                "sender": {"name": sender_name, "email": sender_email_addr},
                "to": [{"email": admin_email, "name": "Admin"}],
                "subject": f"Interview Submitted: {candidate_name}",
                "htmlContent": admin_html
            }, headers=headers)
            results.append(res.status_code < 300)
        except Exception:
            results.append(False)

    return all(results)


# ── Task 8: Dashboard Stats Endpoint ────────────────────────────────────────
@app.get("/admin/dashboard-stats")
def get_dashboard_stats(admin_id: str):
    """Return aggregated stats for the admin dashboard."""
    try:
        all_sessions = list(interview_sessions_collection.find({"created_by": admin_id}))
        now = datetime.now(timezone.utc)
        
        active_sessions = [s for s in all_sessions if not s.get("is_deactivated", False)]
        total = len(active_sessions)
        pending = 0
        completed = 0
        started = 0
        expired = 0
        selected = 0
        rejected = 0
        total_score = 0
        scored_count = 0
        today_count = 0
        week_count = 0
        
        for s in all_sessions:
            if s.get("is_deactivated", False):
                continue
                
            status = s.get("status", "pending")
            if status == "pending" and s.get("expires_at"):
                try:
                    if now > datetime.fromisoformat(s["expires_at"]):
                        status = "expired"
                except Exception:
                    pass
            
            if status == "completed":
                completed += 1
            elif status == "started":
                started += 1
            elif status == "expired":
                expired += 1
            else:
                pending += 1
            
            if s.get("decision") == "selected":
                selected += 1
            elif s.get("decision") == "rejected":
                rejected += 1
            
            if s.get("avg_score") is not None:
                total_score += s["avg_score"]
                scored_count += 1
            
            try:
                created = datetime.fromisoformat(s.get("created_at", ""))
                if created.date() == now.date():
                    today_count += 1
                if (now - created).days <= 7:
                    week_count += 1
            except Exception:
                pass
        
        avg_score = round(total_score / scored_count, 1) if scored_count > 0 else 0
        
        return {
            "total": total,
            "pending": pending,
            "completed": completed,
            "started": started,
            "expired": expired,
            "selected": selected,
            "rejected": rejected,
            "avg_score": avg_score,
            "today": today_count,
            "this_week": week_count
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/admin/live-dashboard-metrics")
def get_live_dashboard_metrics(admin_id: str):
    try:
        sessions = list(interview_sessions_collection.find({"created_by": admin_id}))
        metrics = _build_live_dashboard_metrics(sessions)
        print(
            f"[dashboard-live] admin_id={admin_id} ongoing={metrics['ongoing_count']} "
            f"alerts={metrics['integrity_alert_count']} speaking={metrics['currently_speaking_count']}"
        )
        return metrics
    except Exception as exc:
        print(f"[dashboard-live] error admin_id={admin_id}: {exc}")
        return {"error": str(exc)}


# ── Task 2: Export Sessions Data Endpoint ───────────────────────────────────
@app.get("/admin/export-sessions")
async def export_sessions(admin_id: str, status_filter: str = ""):
    """Return session data for Excel export, filtered by status."""
    query = {"created_by": admin_id}
    rows = list(interview_sessions_collection.find(query).sort("created_at", -1))
    now = datetime.now(timezone.utc)
    
    export_data = []
    for row in rows:
        current_status = row.get("status", "pending")
        if current_status == "pending" and row.get("expires_at"):
            try:
                if now > datetime.fromisoformat(row["expires_at"]):
                    current_status = "expired"
            except Exception:
                pass
        
        decision = row.get("decision", "")
        
        # Apply status filter
        if status_filter:
            if status_filter == "selected" and decision != "selected":
                continue
            elif status_filter == "rejected" and decision != "rejected":
                continue
            elif status_filter in ["pending", "completed", "started", "expired"] and current_status != status_filter:
                continue
        
        export_data.append({
            "candidate_name": row.get("candidate_name", ""),
            "candidate_email": row.get("candidate_email", ""),
            "status": current_status,
            "decision": decision or "Pending Review",
            "score": row.get("avg_score", ""),
            "recommendation": row.get("overall_recommendation", ""),
            "interview_duration": row.get("interview_duration", 30),
            "created_at": row.get("created_at", ""),
            "expires_at": row.get("expires_at", "")
        })
    
    return {"data": export_data}

# Redundant v2 removed as v1 unified above.

def process_pending_invitation_emails():
    if not init_mongo():
        print("Skipping pending invitation email processing because MongoDB is unavailable.")
        return

    now = datetime.now(timezone.utc).isoformat()
    due_sessions = list(interview_sessions_collection.find({
        "invite_email_status": {"$in": ["pending", "failed"]},
        "invite_email_send_at": {"$lte": now}
    }).limit(25))

    for session in due_sessions:
        claimed = interview_sessions_collection.update_one(
            {"_id": session["_id"], "invite_email_status": {"$in": ["pending", "failed"]}},
            {"$set": {"invite_email_status": "sending"}}
        )
        if claimed.modified_count == 0:
            continue

        link_url = build_candidate_session_link(session['link_id'])
        sent = send_interview_email(
            candidate_email=session.get("candidate_email", ""),
            candidate_name=session.get("candidate_name", ""),
            link_url=link_url,
            duration=session.get("interview_duration", 30),
            job_description=session.get("job_description", ""),
            custom_html=session.get("custom_email_html", ""),
            scheduled_start=session.get("scheduled_start", ""),
            scheduled_end=session.get("scheduled_end", "")
        )

        interview_sessions_collection.update_one(
            {"_id": session["_id"]},
            {"$set": {
                "invite_email_status": "sent" if sent else "failed",
                "invite_email_sent_at": datetime.now(timezone.utc).isoformat() if sent else None
            }}
        )

def invitation_email_scheduler_loop():
    while True:
        try:
            process_pending_invitation_emails()
        except Exception as e:
            print(f"Email scheduler error: {e}")
        time.sleep(30)

@app.on_event("startup")
def startup_event():
    global EMAIL_SCHEDULER_STARTED
    print("Startup event triggered.")
    print(f"Python runtime={sys.version}")
    print(f"FRONTEND_URL={FRONTEND_URL}")
    print(f"OPENROUTER_API_KEY configured={bool(os.getenv('OPENROUTER_API_KEY'))}")
    print("Connecting Mongo...")
    mongo_connected = init_mongo()
    print(f"Mongo connected={mongo_connected}")
    if not mongo_connected:
        print(f"Mongo status: {get_mongo_status()}")

    # Create default admin if not exists
    try:
        if mongo_connected:
            row = admins_collection.find_one({"username": "admin"})
            if not row:
                hashed_pw = hash_password("admin123")
                default_email = os.getenv("BREVO_SENDER_EMAIL", "oragantisagar041@gmail.com")
                admins_collection.insert_one({
                    "username": "admin",
                    "password": hashed_pw,
                    "email": default_email,
                    "created_at": datetime.now(timezone.utc).isoformat()
                })
                print(f"Default admin created: admin / admin123 (Email: {default_email})")
            else:
                if not row.get("email"):
                    default_email = os.getenv("BREVO_SENDER_EMAIL", "oragantisagar041@gmail.com")
                    admins_collection.update_one({"username": "admin"}, {"$set": {"email": default_email}})
        else:
            print("Skipping default admin bootstrap because Mongo is unavailable.")
    except Exception as e:
        print(f"Error checking/creating admin: {e}")
        traceback.print_exc()

    if not EMAIL_SCHEDULER_STARTED:
        threading.Thread(target=invitation_email_scheduler_loop, daemon=True).start()
        EMAIL_SCHEDULER_STARTED = True
        print("Invitation email scheduler started.")


@app.on_event("shutdown")
def shutdown_event():
    print("Shutdown event triggered.")
    close_mongo()

@app.post("/admin/forgot-password")
async def forgot_password(data: ForgotPasswordRequest):
    user = admins_collection.find_one({"username": data.username, "email": data.email})
    if not user:
        raise HTTPException(status_code=404, detail="Username and email do not match our records.")
    
    otp = "".join([str(random.randint(0, 9)) for _ in range(6)])
    expiry = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    
    admins_collection.update_one({"_id": user["_id"]}, {"$set": {"otp": otp, "otp_expiry": expiry}})
    
    # Send OTP email
    email_sent = send_otp_email(data.email, data.username, otp)
    if email_sent:
        return {"status": "success", "message": "OTP sent to your registered email."}
    else:
        raise HTTPException(status_code=500, detail="Failed to send OTP. Please try again later.")

@app.post("/admin/verify-otp")
async def verify_otp(data: VerifyOTPRequest):
    row = admins_collection.find_one({"username": data.username})
    if not row or not row.get("otp"):
        raise HTTPException(status_code=400, detail="No OTP found for this user.")
    
    db_otp = row.get("otp")
    expiry_str = row.get("otp_expiry")
    if db_otp != data.otp:
        raise HTTPException(status_code=401, detail="Invalid OTP code.")
    
    expiry = datetime.fromisoformat(expiry_str)
    if datetime.now(timezone.utc) > expiry:
        raise HTTPException(status_code=401, detail="OTP has expired.")
    
    return {"status": "success", "message": "OTP verified successfully."}

@app.post("/admin/reset-password")
async def reset_password(data: ResetPasswordRequest):
    # Verify OTP one last time for safety
    row = admins_collection.find_one({"username": data.username})
    if not row or row.get("otp") != data.otp:
        raise HTTPException(status_code=401, detail="Invalid session. Please restart the process.")
    
    expiry = datetime.fromisoformat(row.get("otp_expiry"))
    if datetime.now(timezone.utc) > expiry:
        raise HTTPException(status_code=401, detail="Session expired.")
    
    hashed_pw = hash_password(data.new_password)
    admins_collection.update_one({"_id": row["_id"]}, {"$set": {"password": hashed_pw, "otp": None, "otp_expiry": None}})
    
    return {"status": "success", "message": "Password updated successfully. You can now login."}

def send_otp_email(email: str, name: str, otp: str):
    load_dotenv(override=True)
    api_key = os.getenv("BREVO_API_KEY")
    sender_name = os.getenv("BREVO_SENDER_NAME", "Arah Info Tech Pvt ltd")
    sender_email = os.getenv("BREVO_SENDER_EMAIL")
    
    if not api_key: return False

    html = f"""
    <html><body>
        <h3>Password Reset Request</h3>
        <p>Dear {name},</p>
        <p>You requested to reset your admin password. Please use the following One-Time Password (OTP) to proceed:</p>
        <h2 style='color: #6366f1; letter-spacing: 5px; font-size: 2rem;'>{otp}</h2>
        <p>This code is valid for 10 minutes. If you did not request this, please ignore this email.</p>
        <p>Best Regards,<br/>Arah Info Tech Pvt ltd</p>
    </body></html>
    """

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": email, "name": name}],
        "subject": "Admin Password Reset OTP",
        "htmlContent": html
    }
    
    try:
        url = "https://api.brevo.com/v3/smtp/email"
        headers = {"accept": "application/json", "api-key": api_key, "content-type": "application/json"}
        response = requests.post(url, json=payload, headers=headers)
        return response.status_code < 300
    except:
        return False

@app.post("/admin/login")
async def admin_login(data: AdminLogin):
    hashed_pw = hash_password(data.password)
    user = admins_collection.find_one({"username": data.username, "password": hashed_pw})
    if user:
        email = user.get("email", "")
        return {"status": "success", "admin_id": str(user["_id"]), "username": user["username"], "email": email}
    else:
        raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/admin/profile")
async def update_profile(data: UpdateProfileRequest):
    try:
        from bson import ObjectId
        admins_collection.update_one({"_id": ObjectId(str(data.admin_id))}, {"$set": {"email": data.email}})
        return {"status": "success", "message": "Profile updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

def extract_info_from_resume(text: str) -> Dict:
    client = get_client()
    try:
        response = client.chat.completions.create(
            model="google/gemini-2.0-flash-001",
            messages=[{
                "role": "system",
                "content": "You are a professional recruiting assistant. Extract the candidate's full name and email address from the provided resume text. Return ONLY a valid JSON object with keys 'name' and 'email'. If either cannot be found, use null."
            }, {
                "role": "user",
                "content": text[:5000] # Use first block of text
            }],
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        print(f"Error extracting candidate info: {e}")
        return {"name": None, "email": None}

@app.post("/admin/parse-resume")
async def parse_resume(file: UploadFile = File(...)):
    content = await file.read()
    text = extract_text_from_file(content, file.filename)
    info = extract_info_from_resume(text)
    return {
        "status": "success", 
        "text": text,
        "name": info.get("name"),
        "email": info.get("email"),
        "normalized_name": " ".join(normalize_candidate_name(info.get("name") or ""))
    }

from datetime import timedelta

@app.post("/admin/create-session")
async def create_session(data: CreateSession):
    link_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    
    # Task 4: If scheduled, use scheduled_end as expiry; otherwise 24h
    if data.scheduled_end:
        try:
            expires_at = datetime.fromisoformat(data.scheduled_end).isoformat()
        except Exception:
            expires_at = (now + timedelta(hours=24)).isoformat()
    else:
        expires_at = (now + timedelta(hours=24)).isoformat()
    
    name_validation = compare_candidate_names(data.candidate_name, data.resume_detected_name) if data.resume_detected_name else {"matches": True, "similarity": 1.0, "manual_name": data.candidate_name, "detected_name": "", "reason": "not_available"}
    if data.resume_detected_name and not name_validation.get("matches") and not data.resume_name_confirmed:
        raise HTTPException(status_code=400, detail="Candidate name does not match the uploaded resume. Please review and confirm.")

    session_doc = {
        "link_id": link_id,
        "candidate_name": data.candidate_name,
        "candidate_email": data.candidate_email,
        "resume_text": data.resume_text,
        "job_description": data.job_description,
        "custom_email_html": data.custom_email_html,
        "created_by": data.admin_id,
        "created_at": now.isoformat(),
        "expires_at": expires_at,
        "interview_duration": data.interview_duration,
        "record_video": data.record_video,
        "status": "pending",
        "resume_detected_name": data.resume_detected_name,
        "resume_name_similarity": name_validation.get("similarity", data.resume_name_similarity or 0),
        "resume_name_confirmed": bool(data.resume_name_confirmed or name_validation.get("matches")),
        "name_validation": name_validation,
    }
    
    # Task 4: Store scheduled time window
    if data.scheduled_start:
        session_doc["scheduled_start"] = data.scheduled_start
    if data.scheduled_end:
        session_doc["scheduled_end"] = data.scheduled_end
    
    interview_sessions_collection.insert_one(session_doc)
    session_doc["_id"] = interview_sessions_collection.find_one({"link_id": link_id}, {"_id": 1})["_id"]
    
    link_url = build_candidate_session_link(link_id)
    
    email_result = queue_or_send_interview_email(session_doc, link_url)
    
    return {
        "status": "success", 
        "link_id": link_id, 
        "link_url": link_url,
        "email_sent": email_result["email_sent"],
        "email_scheduled": email_result["email_scheduled"],
        "email_send_at": email_result["email_send_at"],
        "name_validation": name_validation
    }


# ── Bulk Session Models ────────────────────────────────────────────────────────
class BulkCandidate(BaseModel):
    candidate_name: str
    candidate_email: str
    resume_text: str = ""
    record_video: bool = True  # Task 5: Per-candidate video toggle

class BulkCreateSession(BaseModel):
    candidates: List[BulkCandidate]
    job_description: str
    admin_id: str
    interview_duration: int = 30
    record_video: bool = True  # Global default
    custom_email_html: str = ""  # Task 1: Optional admin-edited email
    scheduled_start: str = ""  # Task 4
    scheduled_end: str = ""    # Task 4

@app.post("/admin/bulk-create-sessions")
async def bulk_create_sessions(data: BulkCreateSession):
    """
    Create interview sessions for multiple candidates at once.
    Each candidate gets their own unique link and receives an email invitation.
    Returns a per-candidate result list with link_id, link_url, and email_sent status.
    """
    if not data.candidates:
        raise HTTPException(status_code=400, detail="No candidates provided")

    results = []
    now = datetime.now(timezone.utc)

    for candidate in data.candidates:
        link_id = str(uuid.uuid4())
        link_url = build_candidate_session_link(link_id)
        candidate_error = None

        try:
            scheduled_expiry = parse_iso_datetime(data.scheduled_end)
            session_doc = {
                "link_id": link_id,
                "candidate_name": candidate.candidate_name,
                "candidate_email": candidate.candidate_email,
                "resume_text": candidate.resume_text,
                "job_description": data.job_description,
                "custom_email_html": data.custom_email_html,
                "created_by": data.admin_id,
                "created_at": now.isoformat(),
                "expires_at": (scheduled_expiry.isoformat() if scheduled_expiry else (now + timedelta(hours=24)).isoformat()),
                "interview_duration": data.interview_duration,
                "record_video": candidate.record_video,  # Task 5: Per-candidate video
                "status": "pending"
            }
            if data.scheduled_start:
                session_doc["scheduled_start"] = data.scheduled_start
            if data.scheduled_end:
                session_doc["scheduled_end"] = data.scheduled_end
            insert_result = interview_sessions_collection.insert_one(session_doc)
            session_doc["_id"] = insert_result.inserted_id
        except Exception as db_err:
            print(f"⚠️ DB Error for {candidate.candidate_email}: {db_err}")
            candidate_error = f"DB error: {db_err}"

        # Send email invitation
        email_sent = False
        email_scheduled = False
        email_send_at = ""
        if not candidate_error:
            try:
                email_result = queue_or_send_interview_email(session_doc, link_url)
                email_sent = email_result["email_sent"]
                email_scheduled = email_result["email_scheduled"]
                email_send_at = email_result["email_send_at"]
            except Exception as email_err:
                print(f"⚠️ Email Error for {candidate.candidate_email}: {email_err}")

        results.append({
            "candidate_name": candidate.candidate_name,
            "candidate_email": candidate.candidate_email,
            "link_id": link_id if not candidate_error else None,
            "link_url": link_url if not candidate_error else None,
            "email_sent": email_sent,
            "email_scheduled": email_scheduled,
            "email_send_at": email_send_at,
            "status": "error" if candidate_error else "success",
            "error": candidate_error
        })

    successful = sum(1 for r in results if r["status"] == "success")
    print(f"✅ Bulk sessions created: {successful}/{len(results)}")

    return {
        "status": "success",
        "total": len(results),
        "successful": successful,
        "failed": len(results) - successful,
        "results": results
    }


@app.get("/session/{link_id}")
async def get_session(link_id: str):
    row = interview_sessions_collection.find_one({"link_id": link_id})
    if row:
        expires_at = row.get("expires_at")
        now = datetime.now(timezone.utc)
        
        # Check if the link has expired
        is_expired = False
        if expires_at:
            try:
                expiration_time = parse_iso_datetime(expires_at)
                if now > expiration_time:
                    is_expired = True
            except Exception as e:
                print(f"Error parsing expiration time: {e}")
        
        # Task 4: Check if interview is within scheduled time window
        is_before_schedule = False
        scheduled_start = row.get("scheduled_start", "")
        scheduled_end = row.get("scheduled_end", "")
        if scheduled_start:
            try:
                start_time = parse_iso_datetime(scheduled_start)
                if now < start_time:
                    is_before_schedule = True
            except Exception:
                pass
        if scheduled_end:
            try:
                end_time = parse_iso_datetime(scheduled_end)
                if now > end_time:
                    is_expired = True
            except Exception:
                pass
                
        return {
            "status": "success",
            "candidate_name": row.get("candidate_name"),
            "resume_text": row.get("resume_text"),
            "job_description": row.get("job_description"),
            "session_status": row.get("status"),
            "interview_duration": int(row.get("interview_duration") or 30) if row.get("interview_duration") else 30,
            "is_expired": is_expired,
            "is_before_schedule": is_before_schedule,
            "scheduled_start": scheduled_start,
            "scheduled_end": scheduled_end,
            "record_video": row.get("record_video", True),
            "is_deactivated": row.get("is_deactivated", False)
        }
    else:
        raise HTTPException(status_code=404, detail="Session not found")
from typing import Optional

@app.get("/admin/sessions")
async def get_all_sessions(admin_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None, sort_by: str = "score", deactivated: str = "false"):
    if deactivated == "all":
        query_filter = {"created_by": admin_id}
    elif deactivated == "true":
        query_filter = {"created_by": admin_id, "is_deactivated": True}
    else:
        # Default: only active
        query_filter = {"created_by": admin_id, "$or": [{"is_deactivated": False}, {"is_deactivated": {"$exists": False}}]}
    
    if (start_date and start_date.strip()) or (end_date and end_date.strip()):
        date_filter = {}
        if start_date and start_date.strip():
            date_filter["$gte"] = start_date
        if end_date and end_date.strip():
            date_filter["$lte"] = end_date + "T23:59:59"
        query_filter["created_at"] = date_filter
    
    sort_field = [("created_at", -1)] if sort_by == "date" else [("avg_score", -1), ("created_at", -1)]
    
    rows = interview_sessions_collection.find(query_filter).sort(sort_field)
    
    sessions = []
    for row in rows:
        has_video = False
        interview_id = row.get("interview_id")
        if interview_id:
            interview_doc = interviews_collection.find_one({"id": interview_id}, {"recording_path": 1})
            if interview_doc and interview_doc.get("recording_path"):
                has_video = True

        sessions.append({
            "link_id": row.get("link_id"),
            "candidate_name": row.get("candidate_name"),
            "candidate_email": row.get("candidate_email"),
            "status": row.get("status"),
            "created_at": row.get("created_at"),
            "expires_at": row.get("expires_at"),
            "interview_duration": row.get("interview_duration"),
            "interview_id": interview_id,
            "avg_score": row.get("avg_score"),
            "recommendation": row.get("overall_recommendation"),
            "decision": row.get("decision"),
            "has_video": has_video,
            "record_video": row.get("record_video", True),
            "is_deactivated": row.get("is_deactivated", False)
        })
        
    return {"status": "success", "sessions": sessions}

@app.delete("/admin/sessions/{link_id}")
async def delete_session(link_id: str):
    row = interview_sessions_collection.find_one({"link_id": link_id})
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
        
    # Delete from interview tracking
    interview_id = row.get("interview_id")
    if interview_id:
        interviews_collection.delete_one({"id": interview_id})
        answers_collection.delete_many({"interview_id": interview_id})
            
    # Delete the session link
    interview_sessions_collection.delete_one({"link_id": link_id})
    
    return {"status": "success", "message": "Session deleted"}

@app.post("/admin/sessions/{link_id}/deactivate")
async def deactivate_session(link_id: str):
    result = interview_sessions_collection.update_one({"link_id": link_id}, {"$set": {"is_deactivated": True}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "success"}

@app.post("/admin/sessions/{link_id}/activate")
async def activate_session(link_id: str):
    result = interview_sessions_collection.update_one({"link_id": link_id}, {"$set": {"is_deactivated": False}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "success"}

@app.post("/start-session-interview")
async def start_session_interview(link_id: str = Form(...)):
    row = interview_sessions_collection.find_one({"link_id": link_id})
    
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
        
    candidate_name = row.get("candidate_name")
    candidate_email = row.get("candidate_email")
    resume_text = row.get("resume_text")
    job_description = row.get("job_description")
    status = row.get("status")
    num_questions = row.get("num_questions")
    raw_duration = row.get("interview_duration")
    try:
        interview_duration = int(raw_duration) if raw_duration and int(raw_duration) > 0 else 30
    except (ValueError, TypeError):
        interview_duration = 30
    print(f"[TIMER DEBUG] link_id={link_id}, raw interview_duration from DB={row.get('interview_duration')}, used={interview_duration}")
    existing_interview_id = row.get("interview_id")
    expires_at = row.get("expires_at")
    
    # Check if the link has expired
    if expires_at:
        try:
            expiration_time = parse_iso_datetime(expires_at)
            if datetime.now(timezone.utc) > expiration_time:
                return {
                    "is_expired": True,
                    "message": "This interview link has expired. Please contact your administrator."
                }
        except Exception as e:
            print(f"Error parsing expiration time in start_session_interview: {e}")
            
    # Check scheduled restrictions (Task 4)
    scheduled_start = row.get("scheduled_start")
    scheduled_end = row.get("scheduled_end")
    if scheduled_start:
        try:
            start_time = parse_iso_datetime(scheduled_start)
            if datetime.now(timezone.utc) < start_time:
                return {
                    "is_before_schedule": True,
                    "scheduled_start": scheduled_start,
                    "scheduled_end": scheduled_end
                }
        except Exception as e:
            print(f"Error parsing scheduled_start time in start_session_interview: {e}")

    if scheduled_end:
        try:
            end_time = parse_iso_datetime(scheduled_end)
            if datetime.now(timezone.utc) > end_time:
                return {
                    "is_expired": True,
                    "message": "This interview window has ended. Please contact your administrator."
                }   
        except Exception as e:
            print(f"Error parsing scheduled_end time in start_session_interview: {e}")
    
    # If session was already started or completed, don't restart — return status
    if status in ('started', 'completed') and existing_interview_id:
        if status == 'completed':
            return {
                "already_started": True,
                "session_status": status,
                "candidate_name": candidate_name,
                "interview_id": existing_interview_id,
                "interview_duration": interview_duration
            }
        
        # Status is 'started' — reload the existing interview and return first question
        try:
            existing = get_interview_or_404(existing_interview_id)
        except Exception:
            existing = None
        
        if existing and existing.get("questions"):
            questions = existing["questions"]
            return {
                "status": "started",
                "interview_id": existing_interview_id,
                "questions": questions,
                "first_question": questions[0],
                "total_questions": len(questions),
                "candidate_name": candidate_name,
                "interview_duration": interview_duration,
                "record_video": row.get("record_video", True)
            }
        
        # Fallback: regenerate if questions lost
        return {
            "already_started": True,
            "session_status": status,
            "candidate_name": candidate_name,
            "interview_id": existing_interview_id,
            "interview_duration": interview_duration
        }
    
    # Always generate a full pool of questions — interview is time-based,
    # candidates answer as many as they can within the interview_duration timer
    num_questions_to_generate = 20
    
    # Generate Questions
    source = "job_description" if job_description and len(job_description) > 50 else "resume"
    content_str = job_description if source == "job_description" else resume_text
    
    profile_analysis = analyze_resume_or_jd(content_str)
    
    questions = generate_mock_questions(content_str, source, num_questions=num_questions_to_generate, resume_text=resume_text, jd_text=job_description)
    
    if not questions:
        raise HTTPException(status_code=400, detail="Failed to generate questions")

    interview_id = f"int_{int(datetime.now(timezone.utc).timestamp())}_{uuid.uuid4().hex[:8]}"

    # Store interview data (DB)
    try:
        interviews_collection.insert_one({
            "id": interview_id,
            "source": source,
            "profile_text": content_str[:5000],
            "profile_analysis": profile_analysis,
            "questions": json.dumps(questions),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "candidate_name": candidate_name,
            "candidate_email": candidate_email
        })
        
        # Update session status
        interview_sessions_collection.update_one(
            {"link_id": link_id},
            {"$set": {"status": "started", "interview_id": interview_id}}
        )
    except Exception as db_e:
        print(f"⚠️ DB Save Error: {db_e}")
    return {
        "status": "started",
        "interview_id": interview_id,
        "questions": questions,
        "first_question": questions[0] if questions else None,
        "total_questions": len(questions),
        "candidate_name": candidate_name,
        "interview_duration": interview_duration,
        "record_video": row.get("record_video", True)
    }

@app.post("/session/{interview_id}/live-update")
async def update_live_monitoring(interview_id: str, payload: LiveMonitoringUpdate):
    session = interview_sessions_collection.find_one({"interview_id": interview_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    live_monitoring = payload.dict()
    live_monitoring["updated_at"] = datetime.now(timezone.utc).isoformat()
    current_status = session.get("status", "started")
    next_status = "completed" if current_status == "completed" else "started"
    print(
        f"[live-update] interview_id={interview_id} status={current_status} phase={live_monitoring.get('phase')} "
        f"question={live_monitoring.get('current_question_id')} transcript_words={live_monitoring.get('transcript_word_count')} "
        f"warnings={len(live_monitoring.get('warnings') or [])} frame={'yes' if live_monitoring.get('camera_frame') else 'no'}"
    )
    interview_sessions_collection.update_one(
        {"interview_id": interview_id},
        {"$set": {
            "live_monitoring": live_monitoring,
            "last_activity_at": live_monitoring["updated_at"],
            "status": next_status
        }}
    )
    refreshed = interview_sessions_collection.find_one({"interview_id": interview_id}) or session
    return {
        "status": "success",
        "auto_terminated": bool(refreshed.get("auto_terminated")),
        "termination_reason": refreshed.get("termination_reason", "")
    }


@app.post("/session/{interview_id}/terminate")
async def terminate_interview_for_integrity(interview_id: str, payload: IntegrityTerminationRequest):
    session = interview_sessions_collection.find_one({"interview_id": interview_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    evidence_path = persist_integrity_evidence(interview_id, payload.evidence_frame, payload.type or "termination")
    event = {
        "type": payload.type,
        "count": payload.count,
        "timestamp": payload.timestamp,
        "detail": payload.reason,
        "phase": payload.phase,
        "question_id": payload.question_id,
        "evidence_path": evidence_path,
        "termination_triggered": True,
    }
    interview_sessions_collection.update_one(
        {"interview_id": interview_id},
        {
            "$set": {
                "auto_terminated": True,
                "termination_reason": payload.reason,
                "completed_by": "integrity",
                "termination_type": payload.type,
                "live_monitoring.auto_terminated": True,
                "live_monitoring.termination_reason": payload.reason,
                "live_monitoring.updated_at": datetime.now(timezone.utc).isoformat(),
                "last_activity_at": datetime.now(timezone.utc).isoformat(),
            },
            "$push": {"violations": event}
        }
    )
    print(f"[integrity-terminate] interview_id={interview_id} type={payload.type} count={payload.count}")
    return {"status": "success", "termination_reason": payload.reason}


@app.post("/session/{interview_id}/violation")
async def log_violation(interview_id: str, violation: ViolationRequest):
    print(f"⚠️ VIOLATION detected for session {interview_id}: {violation.type} (#{violation.count}) at {violation.timestamp}")
    try:
        interview_sessions_collection.update_one(
            {"interview_id": interview_id},
            {
                "$push": {"violations": violation.dict()},
                "$set": {"last_activity_at": datetime.now(timezone.utc).isoformat()}
            }
        )
        return {"status": "success"}
    except Exception as e:
        print(f"❌ Error logging violation: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/admin/update-decision")
@app.post("/admin/update_decision")
async def update_decision(data: DecisionRequest):
    print(f"🚀 Decision Update Request: link_id={data.link_id}, decision={data.decision}")
    try:
        # 1. Fetch candidate details for email
        row = interview_sessions_collection.find_one({"link_id": data.link_id})
        if not row:
            print(f"❌ Session NOT found for link_id: {data.link_id}")
            raise HTTPException(status_code=404, detail="Session not found")
        
        name = row.get("candidate_name")
        email = row.get("candidate_email")
        jd = row.get("job_description")
        print(f"👤 Candidate: {name}, Email: {email}")
        
        # 2. Update DB
        interview_sessions_collection.update_one({"link_id": data.link_id}, {"$set": {"decision": data.decision}})
        print(f"✅ DB Updated for {data.link_id}")
        
        # 3. Send Email
        email_sent = False
        email_reason = "No candidate email found"
        if email:
            email_sent = send_decision_email(email, name, data.decision, jd)
            print(f"📧 Email sent: {email_sent}")
            email_reason = "Success" if email_sent else "Email service error (Brevo API failed)"
        else:
            print("⚠️ No email found for candidate, skipping notification.")
        
        return {"status": "success", "decision": data.decision, "email_sent": email_sent, "email_reason": email_reason}
    except Exception as e:
        print(f"💥 Decision update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def send_decision_email(email: str, name: str, decision: str, jd: str):
    import requests
    load_dotenv(override=True)
    api_key = os.getenv("BREVO_API_KEY")
    sender_name = os.getenv("BREVO_SENDER_NAME", "Arah Info Tech Pvt ltd")
    sender_email = os.getenv("BREVO_SENDER_EMAIL")
    
    if not api_key: return False

    subject = "Interview Result - Invitation for next steps" if decision == 'selected' else "Application Status Update"
    
    if decision == 'selected':
        html = f"""
        <html><body>
            <h3>Congratulations {name}!</h3>
            <p>We are pleased to inform you that you have successfully cleared the AI interview for the role.</p>
            <p><b>Next Steps:</b> Our recruitment team will reach out to you shortly for the final technical/HR round. Please stay reachable on this email.</p>
            <p>Best Regards,<br/>Arah Team</p>
        </body></html>
        """
    else:
        html = f"""
        <html><body>
            <h3>Application Update</h3>
            <p>Dear {name},</p>
            <p>Thank you for taking the time to interview with us. Unfortunately, we have decided not to move forward with your application at this time.</p>
            <p>We were impressed with your background, but we had many qualified candidates for this role. We wish you the very best in your job search.</p>
            <p>Best Regards,<br/>Arah Team</p>
        </body></html>
        """

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": email, "name": name}],
        "subject": subject,
        "htmlContent": html
    }
    
    try:
        res = requests.post("https://api.brevo.com/v3/smtp/email", json=payload, headers={
            "api-key": api_key, "content-type": "application/json"
        })
        if res.status_code >= 300:
            print(f"❌ Brevo Error: {res.status_code} - {res.text}")
        return res.status_code < 300
    except Exception as email_err:
        print(f"💥 Email sending error: {email_err}")
        return False

@app.post("/complete-session/{link_id}")
async def complete_session(link_id: str):
    """Mark a session as completed and send notification emails (Task 3)."""
    try:
        interview_sessions_collection.update_one({"link_id": link_id}, {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc).isoformat()}})
        
        # Task 3: Send submission notification to admin and candidate
        try:
            session = interview_sessions_collection.find_one({"link_id": link_id})
            if session:
                candidate_name = session.get("candidate_name", "Candidate")
                candidate_email = session.get("candidate_email", "")
                interview_id = session.get("interview_id", "")
                admin_id = session.get("created_by", "")
                
                # Get admin email
                admin_email = ""
                if admin_id:
                    try:
                        from bson import ObjectId
                        admin = admins_collection.find_one({"_id": ObjectId(admin_id)})
                        if admin:
                            admin_email = admin.get("email", "")
                    except Exception:
                        pass
                
                # Calculate score
                avg_score = 0
                total_q = 0
                if interview_id:
                    answers = list(answers_collection.find({"interview_id": interview_id}))
                    total_q = len(answers)
                    scores = [a.get("ai_score", 0) for a in answers if a.get("ai_score") is not None]
                    avg_score = sum(scores) / len(scores) if scores else 0
                    
                    # Cache avg_score for dashboard
                    interview_sessions_collection.update_one(
                        {"link_id": link_id},
                        {"$set": {"avg_score": round(avg_score, 1)}}
                    )
                
                # Send notifications
                if candidate_email:
                    send_submission_notification(
                        candidate_email=candidate_email,
                        candidate_name=candidate_name,
                        admin_email=admin_email,
                        avg_score=avg_score,
                        total_questions=total_q
                    )
                    print(f"✅ Submission notification sent for {candidate_name}")
        except Exception as notify_err:
            print(f"⚠️ Submission notification error: {notify_err}")
        
        return {"status": "success"}
    except Exception as e:
        print(f"Error completing session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Wrap FastAPI app with Socket.IO after all routes/middleware/events are registered.
app = socketio.ASGIApp(sio, app)
print("✅ Socket.IO ASGI integration completed.")

if __name__ == "__main__":
    import uvicorn
    import socket

    HOST = "0.0.0.0"
    DEFAULT_PORT = int(os.getenv("PORT", 8000))

    def find_available_port(start_port: int, max_tries: int = 100) -> int:
        """Try to bind to ports starting at start_port and return the first available one."""
        for port in range(start_port, start_port + max_tries):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                # Try binding to the candidate port to check availability
                s.bind((HOST, port))
                s.close()
                return port
            except OSError:
                s.close()
                continue
        raise RuntimeError(f"No available ports found in range {start_port}-{start_port + max_tries - 1}")

    port_to_use = find_available_port(DEFAULT_PORT)
    if port_to_use != DEFAULT_PORT:
        print(f"Port {DEFAULT_PORT} is in use; starting server on available port {port_to_use} instead.")

    # Check for SSL certificates in the forenten folder
    cert_path = r"c:\Users\sagar\Downloads\mock-interview\forenten\cert.pem"
    key_path = r"c:\Users\sagar\Downloads\mock-interview\forenten\key.pem"
    
    if os.path.exists(cert_path) and os.path.exists(key_path):
        print(f"🚀 Starting HTTPS server on port {port_to_use}")
        uvicorn.run(app, host=HOST, port=port_to_use, ssl_certfile=cert_path, ssl_keyfile=key_path)
    else:
        print(f"🚀 Starting HTTP server on port {port_to_use} (SSL certs not found)")
        uvicorn.run(app, host=HOST, port=port_to_use)
