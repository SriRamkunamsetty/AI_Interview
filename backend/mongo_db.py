import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

USE_MOCK_MONGO = os.getenv("USE_MOCK_MONGO", "").lower() in {"1", "true", "yes"}
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")

if USE_MOCK_MONGO:
    import mongomock

    client = mongomock.MongoClient()
    print("MongoDB mock connected and initialized.")
else:
    client = MongoClient(MONGO_URI)
db = client["AI_Interview"]

# Collections
candidates_collection = db["candidates"]
interviews_collection = db["interviews"]
answers_collection = db["answers"]
admins_collection = db["admins"]
interview_sessions_collection = db["interview_sessions"]

# Setup unique indexes
candidates_collection.create_index("name", unique=True)
admins_collection.create_index("username", unique=True)
interview_sessions_collection.create_index("link_id", unique=True)
answers_collection.create_index([("interview_id", 1), ("question_id", 1)], unique=True)
interviews_collection.create_index("id", unique=True)

if not USE_MOCK_MONGO:
    print("MongoDB connected and initialized.")
