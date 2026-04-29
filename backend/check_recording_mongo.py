from mongo_db import interviews_collection
import json

print("\n--- Recent Interviews ---")
for i in interviews_collection.find().sort("_id", -1).limit(5):
    print(f"ID: {i.get('id', 'N/A')}, Path: {i.get('recording_path', 'N/A')}")
