import sqlite3

conn = sqlite3.connect("interviews.db")
cursor = conn.cursor()

cursor.execute("""
SELECT 
    interview_id,
    question_id,
    ai_score,
    ai_feedback,
    ai_keywords,
    corrected_answer
FROM answers
""")

rows = cursor.fetchall()

if not rows:
    print("⚠️ No answers found in the database.")
else:
    print(f"✅ Found {len(rows)} answers:")
    for row in rows:
        print("\nInterview:", row[0])
        print("Question ID:", row[1])
        print("AI Score:", row[2])
        print("Feedback:", row[3])
        print("Keywords:", row[4])
        print("Corrected Answer:", row[5])
        print("-" * 30)
