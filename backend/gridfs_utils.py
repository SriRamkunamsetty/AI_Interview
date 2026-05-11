import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from bson import ObjectId
from gridfs import GridFSBucket
from gridfs.grid_file import GridOut

from mongo_db import get_db

GRIDFS_ENABLED = os.getenv("GRIDFS_ENABLED", "").lower() in {"1", "true", "yes"}
GRIDFS_BUCKET = os.getenv("GRIDFS_BUCKET", "recordings").strip() or "recordings"


def is_gridfs_enabled() -> bool:
    return GRIDFS_ENABLED


def get_gridfs_bucket() -> GridFSBucket:
    db = get_db()
    if db is None:
        raise RuntimeError("MongoDB is not available for GridFS. Ensure MONGO_URI is configured and mongo_db.init_mongo() succeeds.")
    return GridFSBucket(db, bucket_name=GRIDFS_BUCKET)


def store_recording(upload_file, interview_id: str) -> Dict[str, str]:
    bucket = get_gridfs_bucket()
    metadata = {
        "interview_id": interview_id,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "content_type": upload_file.content_type or "video/webm",
        "original_filename": upload_file.filename or "full_interview.webm",
        "storage_type": "gridfs",
    }
    file_id = bucket.upload_from_stream(
        upload_file.filename or "full_interview.webm",
        upload_file.file,
        metadata=metadata,
        content_type=upload_file.content_type or "video/webm",
    )
    return {"file_id": str(file_id), "bucket": GRIDFS_BUCKET}


def build_recording_url(file_id: str) -> str:
    return f"/recordings/gridfs/{file_id}"


def open_recording_stream(file_id: str) -> GridOut:
    bucket = get_gridfs_bucket()
    return bucket.open_download_stream(ObjectId(file_id))
