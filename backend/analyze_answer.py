import os
import requests
import json

from dotenv import load_dotenv

load_dotenv()


def post_openrouter_chat(payload: dict, api_key: str):
    session = requests.Session()
    session.trust_env = False
    return session.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=30
    )

def analyze_answer(question: str, answer: str, context: str = ""):
    # Short-circuit for empty/placeholder answers
    if not answer or not answer.strip() or answer.strip() in ["Transcribing...", "Your speech will appear here automatically..."]:
        return {
            "corrected_answer": "No answer provided.",
            "grammar_score": 0,
            "relevance_score": 0,
            "clarity_score": 0,
            "overall_score": 0,
            "feedback": "Please record your answer before analyzing."
        }

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return {
            "corrected_answer": "Error: Missing API Key",
            "overall_score": 0,
            "feedback": "Server configuration error: OpenRouter API Key is missing."
        }
    prompt = f"""
You are an expert interview coach and evaluator. Your task is to provide high-quality, personalized feedback to a candidate.

Context (Resume/Job Description):
{context}

Question: "{question}"
Candidate's Answer: "{answer}"

Instructions:
1. **Analyze strictly based on the 'Candidate's Answer'**: Do NOT score based on the candidate's potential or resume. Score ONLY what they actually said.
   - If the answer is "hello", "I don't know", or very short/irrelevant, the score MUST be low (0-30).
   - Only give high scores for complete, relevant answers that address the question.

2. **Corrected Answer**:
   - If the candidate's answer is good, polish it.
   - If the candidate's answer is poor or missing (e.g. just "hello"), generate a **FULL MODEL ANSWER** based on their Resume/Context.
   - Start the corrected answer with "Suggested Answer:" if you are providing a model answer because theirs was poor.

3. **Feedback**:
   - Be honest. If they just said "hello", tell them they need to actually answer the question.
   - Critique the content, delivery (implied by text), and structure.

4. **Scoring**: Rate the **Candidate's Answer** on a scale of 0-100. 
   - CRITICAL: If the candidate's answer is short (e.g. "hello") or irrelevant, the score MUST be < 30. 
   - Do NOT score your own "Suggested Answer".

5. **Keywords**: Extract key concepts from the *Suggested Answer* if the user's answer was poor.

Return VALID JSON ONLY.

Format:
{{
  "corrected_answer": "Suggested Answer: ...",
  "grammar_score": 0,
  "relevance_score": 0,
  "clarity_score": 0,
  "overall_score": 0,
  "feedback": "Feedback...",
  "keywords": ["key1", "key2"]
}}
"""

    try:
        response = post_openrouter_chat(
            {
                "model": "openai/gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0
            },
            api_key
        )

        if response.status_code == 402:
            raise Exception("API Quota Exceeded (402)")
        
        if response.status_code != 200:
             raise Exception(f"API Error {response.status_code}")

        data = response.json()
        
        if "choices" not in data:
            raise Exception("Invalid API structure")

        content = data["choices"][0]["message"]["content"]
        
        start = content.find("{")
        end = content.rfind("}") + 1
        if start == -1 or end == 0:
             raise Exception("No JSON found")

        result = json.loads(content[start:end])

        # Safety Check: If answer is too short (< 15 words) and score is high, force it down.
        # This prevents the AI from scoring its own "Suggested Answer" or giving credit for empty greetings.
        if len(answer.split()) < 15 and result.get("overall_score", 0) > 40:
            result["overall_score"] = 10
            if "too short" not in result.get("feedback", "").lower():
                 result["feedback"] = "Your answer was too short to be evaluated properly. Please provide a more detailed response. " + result.get("feedback", "")
        
        return result

    except Exception as e:
        print(f"⚠️ Analysis API Failed: {e}")
        # FALLBACK: Heuristic Scoring (Offline Mode)
        word_count = len(answer.split())
        
        if word_count < 10:
            score = 15
            feedback = f"⚠️ API Quota/Error (Offline Mode). Answer too short ({word_count} words). Score penalized. Please provide more detail."
        else:
            # Score based on length, capped at 85
            score = min(max(word_count * 2, 40), 85)
            feedback = f"⚠️ API Quota/Error (Offline Mode). Your answer was recorded ({word_count} words). To get real AI analysis, check API credits."
            
        return {
            "corrected_answer": "Analysis unavailable (Offline Mode)",
            "overall_score": score,
            "feedback": feedback,
            "keywords": ["Offline"]
        }

print("evaluate_answer.py loaded")
