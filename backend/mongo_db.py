import os
import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote, unquote

import certifi
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi

load_dotenv()

USE_MOCK_MONGO = os.getenv("USE_MOCK_MONGO", "").lower() in {"1", "true", "yes"}
MONGO_URI = (os.getenv("MONGO_URI") or "").strip()
DB_NAME = os.getenv("MONGO_DB_NAME", "AI_Interview")

client = None
db = None
_mongo_ready = False
_mongo_error = ""
_indexes_ensured = False
_last_mongo_attempt_at = None
_next_retry_at = None
_retry_delay_seconds = int(os.getenv("MONGO_RETRY_DELAY_SECONDS", "30"))


class MongoConfigurationError(RuntimeError):
    pass


def _log(message: str) -> None:
    print(f"[mongo] {message}")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_iso(dt: Optional[datetime]) -> str:
    return dt.isoformat() if dt else ""


def _python_version_string() -> str:
    return ".".join(str(part) for part in os.sys.version_info[:3])


def _infer_mongo_hint() -> str:
    lowered_error = (_mongo_error or "").lower()
    python_version = os.sys.version_info

    if "multiple '@' symbols" in lowered_error or "url encoding" in lowered_error:
        return "Check that the MongoDB username and password are URL-encoded exactly once."
    if "tlsv1_alert_internal_error" in lowered_error:
        if python_version >= (3, 14):
            return "Render is using Python 3.14 by default. Pin Render to Python 3.12.x and verify Atlas network access."
        return "Verify Atlas network access, URI correctness, and TLS compatibility for the current runtime."
    if "not configured" in lowered_error:
        return "Set the MONGO_URI environment variable in Render."
    return "Inspect the sanitized URI, Atlas IP access list, database user credentials, and Render Python version."


def _looks_percent_encoded(value: str) -> bool:
    return "%" in value


def _analyze_mongo_uri(uri: str) -> dict:
    info = {
        "scheme": "unknown",
        "host_count": 0,
        "hosts": [],
        "has_credentials": False,
        "username_present": False,
        "password_present": False,
        "username_encoded": False,
        "password_encoded": False,
        "has_app_name": False,
        "retry_writes": None,
        "w": None,
        "tls": None,
        "direct_connection": None,
        "issues": [],
    }

    cleaned = (uri or "").strip()
    if not cleaned:
        info["issues"].append("MONGO_URI is empty.")
        return info

    if not cleaned.startswith(("mongodb://", "mongodb+srv://")):
        info["issues"].append("MONGO_URI must start with mongodb:// or mongodb+srv://")
        return info

    info["scheme"] = "mongodb+srv" if cleaned.startswith("mongodb+srv://") else "mongodb"
    remainder = cleaned.split("://", 1)[1]
    authority, _, tail = remainder.partition("/")
    userinfo = ""
    host_part = authority

    if "@" in authority:
        userinfo, host_part = authority.rsplit("@", 1)
        info["has_credentials"] = True
        if authority.count("@") > 1:
            info["issues"].append("Credentials contain multiple '@' symbols. Password may need URL encoding.")
        if ":" in userinfo:
            username, password = userinfo.split(":", 1)
        else:
            username, password = userinfo, ""
        info["username_present"] = bool(username)
        info["password_present"] = bool(password)
        info["username_encoded"] = _looks_percent_encoded(username)
        info["password_encoded"] = _looks_percent_encoded(password)
        if username and quote(unquote(username), safe="") != username and "%" not in username:
            info["issues"].append("Username contains reserved characters and may need URL encoding.")
        if password and quote(unquote(password), safe="") != password and "%" not in password:
            info["issues"].append("Password contains reserved characters and may need URL encoding.")

    host_section, _, query = tail.partition("?")
    hosts = [segment for segment in host_part.split(",") if segment]
    info["hosts"] = hosts[:3]
    info["host_count"] = len(hosts)

    params = {}
    if query:
        for raw_pair in query.split("&"):
            if not raw_pair:
                continue
            key, _, value = raw_pair.partition("=")
            params[key] = value

    info["has_app_name"] = "appName" in params
    info["retry_writes"] = params.get("retryWrites")
    info["w"] = params.get("w")
    info["tls"] = params.get("tls")
    info["direct_connection"] = params.get("directConnection")

    if info["scheme"] == "mongodb+srv" and params.get("tls", "").lower() == "false":
        info["issues"].append("mongodb+srv should not disable TLS.")
    if params.get("retryWrites") and params["retryWrites"].lower() not in {"true", "false"}:
        info["issues"].append("retryWrites must be true or false.")
    if params.get("w") and params["w"] not in {"majority", "1", "2", "3"} and not params["w"].isdigit():
        info["issues"].append("w parameter looks unusual.")
    if host_section and "@" in host_section:
        info["issues"].append("Host portion contains '@', which suggests malformed credentials.")

    return info


def _sanitized_mongo_uri(uri: str) -> str:
    cleaned = (uri or "").strip()
    if not cleaned or "://" not in cleaned:
        return "<empty>"
    scheme, remainder = cleaned.split("://", 1)
    if "@" not in remainder:
        return f"{scheme}://{remainder}"
    userinfo, host_part = remainder.rsplit("@", 1)
    username = userinfo.split(":", 1)[0] if ":" in userinfo else userinfo
    username = quote(unquote(username), safe="%") if username else "<missing-user>"
    return f"{scheme}://{username}:***@{host_part}"


def _validate_mongo_configuration() -> dict:
    analysis = _analyze_mongo_uri(MONGO_URI)
    _log(f"Mongo URI summary: {analysis}")
    _log(f"Mongo URI sanitized: {_sanitized_mongo_uri(MONGO_URI)}")
    if analysis["issues"]:
        raise MongoConfigurationError(" ; ".join(analysis["issues"]))
    return analysis


def _build_client():
    if USE_MOCK_MONGO:
        import mongomock

        _log("Using mongomock client.")
        return mongomock.MongoClient()

    if not MONGO_URI:
        raise RuntimeError("MONGO_URI is not configured.")

    _log(f"Inferred Database Name: {DB_NAME}")
    return MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=5000,
        tlsCAFile=certifi.where(),
        directConnection=False,
        server_api=ServerApi("1"),
    )


def _ensure_indexes() -> None:
    global _indexes_ensured

    if _indexes_ensured or db is None:
        return

    candidates_collection.get_collection().create_index("name", unique=True)
    admins_collection.get_collection().create_index("username", unique=True)
    interview_sessions_collection.get_collection().create_index("link_id", unique=True)
    answers_collection.get_collection().create_index([("interview_id", 1), ("question_id", 1)], unique=True)
    interviews_collection.get_collection().create_index("id", unique=True)
    _indexes_ensured = True
    _log("Indexes ensured.")


def init_mongo(force: bool = False) -> bool:
    global client, db, _mongo_ready, _mongo_error, _last_mongo_attempt_at, _next_retry_at

    if _mongo_ready and not force:
        return True
    if not force and _next_retry_at and _utc_now() < _next_retry_at:
        return False

    close_mongo()
    _mongo_error = ""
    _last_mongo_attempt_at = _utc_now()
    _next_retry_at = _last_mongo_attempt_at + timedelta(seconds=_retry_delay_seconds)
    _log("Connecting to MongoDB...")

    try:
        client = _build_client()
        if not USE_MOCK_MONGO:
            client.admin.command("ping")
        db = client[DB_NAME]
        _mongo_ready = True
        _next_retry_at = None
        _log(f"MongoDB connected to database '{DB_NAME}'.")
        _ensure_indexes()
        return True
    except Exception as exc:
        _mongo_ready = False
        _mongo_error = f"{type(exc).__name__}: {exc}"
        client = None
        db = None
        _log(f"MongoDB connection failed: {_mongo_error}")
        traceback.print_exc()
        return False


def close_mongo() -> None:
    global client, db, _mongo_ready

    if client is not None:
        try:
            client.close()
        except Exception:
            pass

    client = None
    db = None
    _mongo_ready = False


def get_db():
    if db is None:
        init_mongo()
    return db


def get_mongo_status() -> dict:
    return {
        "ready": _mongo_ready,
        "use_mock": USE_MOCK_MONGO,
        "has_uri": bool(MONGO_URI),
        "db_name": DB_NAME,
        "error": _mongo_error,
        "sanitized_uri": _sanitized_mongo_uri(MONGO_URI),
        "last_attempt_at": _safe_iso(_last_mongo_attempt_at),
        "next_retry_at": _safe_iso(_next_retry_at),
        "retry_delay_seconds": _retry_delay_seconds,
        "python_version": _python_version_string(),
        "hint": _infer_mongo_hint(),
    }


class LazyCollectionProxy:
    def __init__(self, collection_name: str):
        self.collection_name = collection_name

    def get_collection(self):
        current_db = get_db()
        if current_db is None:
            raise RuntimeError(
                f"MongoDB is unavailable while accessing collection '{self.collection_name}'."
            )
        return current_db[self.collection_name]

    def __getattr__(self, item):
        return getattr(self.get_collection(), item)

    def __getitem__(self, item):
        return self.get_collection()[item]

    def __repr__(self) -> str:
        return f"<LazyCollectionProxy {self.collection_name}>"


candidates_collection = LazyCollectionProxy("candidates")
interviews_collection = LazyCollectionProxy("interviews")
answers_collection = LazyCollectionProxy("answers")
admins_collection = LazyCollectionProxy("admins")
interview_sessions_collection = LazyCollectionProxy("interview_sessions")
