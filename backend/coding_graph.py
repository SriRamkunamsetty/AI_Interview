import json
import os
import re
from hashlib import sha1
from typing import Any, Dict, List, TypedDict

import httpx
from openai import OpenAI

try:
    from langgraph.graph import END, StateGraph

    LANGGRAPH_AVAILABLE = True
except ImportError:
    END = None
    StateGraph = None
    LANGGRAPH_AVAILABLE = False


DEFAULT_MODEL = os.getenv("CODING_ROUND_MODEL", "openai/gpt-4o-mini")


class CodingRoundState(TypedDict, total=False):
    task: Dict[str, Any]
    answer_summary: str
    prior_feedback: str
    code: str
    explanation: str
    language: str
    feedback_mode: str
    latest_change: str
    context_packet: str
    response: Dict[str, Any]


def _get_client() -> OpenAI:
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
        http_client=httpx.Client(trust_env=False),
    )


def _truncate(text: str, limit: int) -> str:
    if isinstance(text, (dict, list)):
        text = json.dumps(text, ensure_ascii=True)
    elif text is not None and not isinstance(text, str):
        text = str(text)
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...[truncated]"


def _safe_json(content: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    try:
        start = content.find("{")
        end = content.rfind("}") + 1
        if start == -1 or end <= start:
            return fallback
        return json.loads(content[start:end])
    except Exception:
        return fallback


def _extract_function_name(signature: str) -> str:
    signature = signature or ""
    match = re.search(r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", signature)
    if match:
        return match.group(1)
    return "solve"


def _extract_java_method_name(signature: str) -> str:
    signature = signature or ""
    match = re.search(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", signature)
    if match:
        return match.group(1)
    return "solve"


def _default_task() -> Dict[str, Any]:
    signature = "def longest_unique_substring(text):"
    return {
        "title": "Longest Unique Substring Length",
        "description": "Write a function that returns the length of the longest substring without repeating characters.",
        "input_format": "A single string named text.",
        "output_format": "An integer representing the maximum length of a substring with all unique characters.",
        "constraints": [
            "Aim for O(n) time complexity.",
            "Handle empty strings and repeated characters correctly.",
            "Explain why your window moves when a duplicate is found.",
        ],
        "examples": [
            {
                "input": '"abcabcbb"',
                "output": "3",
                "explanation": "The longest substring without repeating characters is 'abc'.",
            }
        ],
        "evaluation_focus": ["correctness", "time complexity", "communication", "edge cases"],
        "starter_function_signature": signature,
        "function_name": _extract_function_name(signature),
        "difficulty": "Medium",
        "recommended_language": "python",
        "timebox_minutes": 20,
        "test_cases": [
            {"id": 1, "input": ["abcabcbb"], "expected": 3, "visible": True},
            {"id": 2, "input": ["bbbbb"], "expected": 1, "visible": True},
            {"id": 3, "input": ["pwwkew"], "expected": 3, "visible": True},
            {"id": 4, "input": [""], "expected": 0, "visible": False},
            {"id": 5, "input": ["dvdf"], "expected": 3, "visible": False},
            {"id": 6, "input": ["abba"], "expected": 2, "visible": False},
            {"id": 7, "input": ["anviaj"], "expected": 5, "visible": False},
        ],
    }


def _normalize_test_case(case: Dict[str, Any], case_id: int) -> Dict[str, Any]:
    raw_input = case.get("input", [])
    if not isinstance(raw_input, list):
        raw_input = [raw_input]
    return {
        "id": case.get("id", case_id),
        "input": raw_input,
        "expected": case.get("expected"),
        "visible": bool(case.get("visible", case_id <= 3)),
    }


def _has_concrete_expected_values(test_cases: List[Dict[str, Any]]) -> bool:
    vague_expected_markers = [
        "array of",
        "list of",
        "object with",
        "at least",
        "marked as",
        "should",
        "random",
        "varies",
        "probability",
    ]
    for case in test_cases:
        expected = case.get("expected")
        if expected is None:
            return False
        if isinstance(expected, str):
            lowered = expected.lower()
            if any(marker in lowered for marker in vague_expected_markers):
                return False
    return True


def _is_deterministic_task(task: Dict[str, Any]) -> bool:
    text = " ".join(
        str(task.get(key, ""))
        for key in ["title", "description", "input_format", "output_format"]
    ).lower()
    text += " " + " ".join(str(item) for item in task.get("constraints", []))
    nondeterministic_markers = [
        "current time",
        "timestamp",
        "expiration",
        "expires",
        "date",
        "today",
        "now",
        "random",
        "probability",
        "chance",
    ]
    return not any(marker in text for marker in nondeterministic_markers)


def _normalize_task(task: Dict[str, Any]) -> Dict[str, Any]:
    fallback = _default_task()
    normalized = dict(fallback)
    normalized.update(task or {})
    signature = normalized.get("starter_function_signature") or fallback["starter_function_signature"]
    normalized["starter_function_signature"] = signature
    normalized["function_name"] = normalized.get("function_name") or _extract_function_name(signature)
    normalized["recommended_language"] = normalized.get("recommended_language") or "python"
    test_cases = normalized.get("test_cases") or fallback["test_cases"]
    normalized["test_cases"] = [_normalize_test_case(case, idx + 1) for idx, case in enumerate(test_cases[:7])]
    if len(normalized["test_cases"]) < 7:
        for extra in fallback["test_cases"][len(normalized["test_cases"]):]:
            normalized["test_cases"].append(extra)
    if not _is_deterministic_task(normalized) or not _has_concrete_expected_values(normalized["test_cases"]):
        return fallback
    visible_count = sum(1 for case in normalized["test_cases"] if case["visible"])
    if visible_count < 3:
        for case in normalized["test_cases"]:
            case["visible"] = case["id"] <= 3
    return normalized


def _build_latest_change(code: str, explanation: str) -> str:
    code_hash = sha1((code or "").encode("utf-8")).hexdigest()[:10]
    note_hash = sha1((explanation or "").encode("utf-8")).hexdigest()[:10]
    return f"code_hash={code_hash}; explanation_hash={note_hash}; code_len={len(code or '')}; explanation_len={len(explanation or '')}"


def _build_context_packet(state: CodingRoundState) -> str:
    task = state.get("task", {})
    packet = {
        "task": {
            "title": task.get("title"),
            "difficulty": task.get("difficulty"),
            "starter_function_signature": task.get("starter_function_signature"),
            "evaluation_focus": task.get("evaluation_focus", []),
        },
        "candidate_context": _truncate(state.get("answer_summary", ""), 1200),
        "rolling_feedback_summary": _truncate(state.get("prior_feedback", ""), 700),
        "latest_change": state.get("latest_change") or _build_latest_change(
            state.get("code", ""), state.get("explanation", "")
        ),
        "spoken_logic": _truncate(state.get("explanation", ""), 1000),
        "code_snapshot": _truncate(state.get("code", ""), 3500),
        "language": state.get("language", "python"),
        "mode": state.get("feedback_mode", "checkpoint"),
    }
    return json.dumps(packet, ensure_ascii=True)


def _llm_json(system_prompt: str, user_prompt: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    try:
        response = _get_client().chat.completions.create(
            model=DEFAULT_MODEL,
            temperature=0.1,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content or ""
        return _safe_json(content, fallback)
    except Exception as exc:
        fallback = dict(fallback)
        fallback.setdefault("coach_message", f"AI feedback unavailable right now: {exc}")
        return fallback


def generate_coding_task(profile_text: str, answers_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    answers_summary = "\n".join(
        f"- Q: {a.get('question_text', '')}\n  A: {_truncate(a.get('answer_text', ''), 220)}"
        for a in answers_data[-5:]
    )
    fallback = _default_task()
    system_prompt = (
        "You design realistic live-coding interview tasks. Return valid JSON only."
    )
    user_prompt = f"""
Create a single coding round tailored to this candidate.

Profile:
{_truncate(profile_text, 2500)}

Recent interview answers:
{answers_summary or "- No answers available"}

Return JSON with:
- title
- description
- input_format
- output_format
- constraints (array)
- examples (array of objects with input, output, explanation)
- evaluation_focus (array)
- starter_function_signature
- function_name
- difficulty
- recommended_language
- timebox_minutes
- test_cases (exactly 7 items, each with input as JSON array args, expected, visible where first 3 are true and last 4 are false)

Make the task a pure function problem using only cross-language friendly inputs and outputs such as strings, numbers, booleans, or flat arrays. It should be solvable in 20-30 minutes and suitable for Python, JavaScript, Java, or C.
Do not use randomness, probabilities, logging requirements, network calls, files, dates, time, or side effects.
Every test case expected value must be an exact JSON value that can be compared with ==, never a natural-language description.
If the function takes one list argument, each test case input must be a one-item array containing that list, for example [[1,2,3]].
"""
    result = _llm_json(system_prompt, user_prompt, fallback)
    return _normalize_task(result)


def _prepare_context(state: CodingRoundState) -> CodingRoundState:
    state["latest_change"] = state.get("latest_change") or _build_latest_change(
        state.get("code", ""), state.get("explanation", "")
    )
    state["context_packet"] = _build_context_packet(state)
    return state


def _coach_candidate(state: CodingRoundState) -> CodingRoundState:
    fallback = {
        "coach_message": "Keep your explanation tightly aligned with the code you just wrote.",
        "strengths": ["You are making progress."],
        "risks": ["The draft could not be analyzed fully."],
        "next_steps": ["Run through one example manually and explain the data flow."],
        "scorecard": {
            "problem_understanding": 50,
            "implementation": 50,
            "communication": 50,
            "overall": 50,
        },
    }
    system_prompt = """
You are an expert live-coding interviewer.
Give concise, practical coaching based only on the compact context packet.
Do not reveal a full solution unless the candidate is completely blocked.
Return strict JSON only.
""".strip()
    final_mode = state.get("feedback_mode") == "final"
    user_prompt = f"""
Compact context packet:
{state.get("context_packet", "")}

Return JSON with:
- coach_message: short paragraph
- strengths: array of 2-3 short bullets
- risks: array of 2-3 short bullets
- next_steps: array of 2-4 concrete actions
- scorecard: object with problem_understanding, implementation, communication, overall (0-100)
{"- hiring_signal: short assessment" if final_mode else ""}
{"- final_recommendation: one of Strong Hire, Hire, Borderline, No Hire" if final_mode else ""}

Keep checkpoint feedback under 120 words in coach_message.
"""
    state["response"] = _llm_json(system_prompt, user_prompt, fallback)
    return state


def _build_graph():
    if not LANGGRAPH_AVAILABLE:
        return None
    graph = StateGraph(CodingRoundState)
    graph.add_node("prepare_context", _prepare_context)
    graph.add_node("coach_candidate", _coach_candidate)
    graph.set_entry_point("prepare_context")
    graph.add_edge("prepare_context", "coach_candidate")
    graph.add_edge("coach_candidate", END)
    return graph.compile()


CODING_GRAPH = _build_graph()


def run_coding_round(
    task: Dict[str, Any],
    answer_summary: str,
    code: str,
    explanation: str,
    language: str,
    prior_feedback: str = "",
    feedback_mode: str = "checkpoint",
) -> Dict[str, Any]:
    state: CodingRoundState = {
        "task": task,
        "answer_summary": answer_summary,
        "prior_feedback": prior_feedback,
        "code": code or "",
        "explanation": explanation or "",
        "language": language or "python",
        "feedback_mode": feedback_mode,
    }
    if CODING_GRAPH is not None:
        result = CODING_GRAPH.invoke(state)
    else:
        result = _coach_candidate(_prepare_context(state))
    response = dict(result.get("response", {}))
    response["context_window_strategy"] = {
        "langgraph_enabled": LANGGRAPH_AVAILABLE,
        "uses_compact_summary": True,
        "code_chars_sent": len(_truncate(code or "", 3500)),
        "explanation_chars_sent": len(_truncate(explanation or "", 1000)),
    }
    return response


def observe_coding_intent(
    task: Dict[str, Any],
    code: str,
    explanation: str,
    language: str,
) -> Dict[str, Any]:
    fallback = {
        "inferred_intent": "The candidate appears to be building the requested solution, but the current draft could not be fully interpreted.",
        "interviewer_prompt": "Walk me through the exact data structure or control flow you are using right now.",
        "follow_up_focus": "logic clarity",
    }
    compact_task = {
        "title": task.get("title"),
        "description": task.get("description"),
        "function_name": task.get("function_name"),
    }
    system_prompt = (
        "You are a live coding interviewer. Infer what the candidate is trying to implement and ask one concise question. Return strict JSON only."
    )
    user_prompt = f"""
Task:
{json.dumps(compact_task, ensure_ascii=True)}

Language: {language}
Candidate explanation:
{_truncate(explanation, 700)}

Candidate code:
{_truncate(code, 2200)}

Return JSON with:
- inferred_intent
- interviewer_prompt
- follow_up_focus

Keep interviewer_prompt under 24 words and make it easy to speak aloud.
"""
    return _llm_json(system_prompt, user_prompt, fallback)
