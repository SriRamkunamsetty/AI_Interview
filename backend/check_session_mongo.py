from mongo_db import interview_sessions_collection
import json

link_id = "fd422e78-9568-48ea-be80-ba31e73f99c8"
row = interview_sessions_collection.find_one({"link_id": link_id})

if row:
    print(f"✅ Found session: {repr(row)}")
else:
    print(f"❌ Session NOT found for link_id: {link_id}")
    
# Also print all sessions to see what's there
print("\n--- All Sessions ---")
for s in interview_sessions_collection.find():
    print(f"Link ID: {s.get('link_id', 'N/A')}, Status: {s.get('status', 'N/A')}")
