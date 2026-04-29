from uploded import get_interview_details
import json

link_id = "fd422e78-9568-48ea-be80-ba31e73f99c8"
try:
    data = get_interview_details(link_id)
    print("\n--- Endpoint Response ---")
    print(f"Recording URL: {data.get('recording_url')}")
except Exception as e:
    print(f"Error: {e}")
