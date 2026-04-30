import os
import traceback
from typing import Optional

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

USE_MOCK_MONGO = os.getenv("USE_MOCK_MONGO", "").lower() in {"1", "true", "yes"}
MONGO_URI = (os.getenv("MONGO_URI") or "").strip()
DB_NAME = os.getenv("MONGO_DB_NAME", "AI_Interview")

client = None
db = None
_mongo_ready = False
_mongo_error = ""
_indexes_ensured = False


def _log(message: str) -> None:
    print(f"[mongo] {message}")


def _build_client():
    if USE_MOCK_MONGO:
        import mongomock

        _log("Using mongomock client.")
        return mongomock.MongoClient()

    if not MONGO_URI:
        raise RuntimeError("MONGO_URI is not configured.")

    return MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=5000,
        retryWrites=True,
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
    global client, db, _mongo_ready, _mongo_error

    if _mongo_ready and not force:
        return True

    close_mongo()
    _mongo_error = ""
    _log("Connecting to MongoDB...")

    try:
        client = _build_client()
        if not USE_MOCK_MONGO:
            client.admin.command("ping")
        db = client[DB_NAME]
        _mongo_ready = True
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
