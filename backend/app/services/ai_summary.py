import os
import logging
import json
import httpx
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.config import settings

logger = logging.getLogger(__name__)

def _sanitize_error(e: Exception, *secrets: str) -> str:
    """Sanitizes exception messages to guarantee API keys are never leaked to logs."""
    msg = f"{type(e).__name__}: {str(e)}"
    for s in secrets:
        if s and len(s) > 4:
            msg = msg.replace(s, "[REDACTED_API_KEY]")
    return msg[:200]

async def generate_gemini_summary(report_data: Dict[str, Any], api_key: str, model_override: Optional[str] = None) -> Dict[str, Any]:
    """
    Generates structured AI summary using Google Gemini Developer API.
    Uses header-based authentication (x-goog-api-key) for security.
    """
    model = model_override or getattr(settings, "GEMINI_MODEL", "gemini-3.5-flash-lite")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json"
    }

    prompt = f"""You are an executive assistant and engineering management advisor.
Analyze the following employee weekly report and daily work updates, and generate a concise executive summary.
Strict constraint: Ground your summary strictly in the provided updates and answers. Do NOT fabricate or invent facts, achievements, or deliverables not present in the input.

EMPLOYEE INFORMATION:
Name: {report_data.get('user_name', 'Employee')}
Week: {report_data.get('week_start_date')} to {report_data.get('week_end_date')}

DAILY WORK UPDATES:
{json.dumps(report_data.get('work_updates', []), indent=2)}

ANSWERS TO WEEKLY QUESTIONS:
{json.dumps(report_data.get('answers', []), indent=2)}

OUTPUT FORMAT:
Respond with strict, valid JSON ONLY (no markdown formatting, no backticks, no conversational text):
{{
  "executive_summary": "2-3 sentences providing an executive-level overview grounded strictly in the activities above.",
  "key_highlights": [
    "Highlight 1",
    "Highlight 2",
    "Highlight 3"
  ],
  "blockers_identified": [
    "Blocker or challenge 1 (or 'No major blockers reported' if none)"
  ],
  "manager_recommendation": "1-2 actionable suggestions for the manager on how to support this employee next week."
}}
"""

    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json"
        }
    }

    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini returned empty candidates")
        text = candidates[0]["content"]["parts"][0]["text"].strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        parsed = json.loads(text.strip())
        parsed["model_used"] = f"Google Gemini ({model})"
        parsed["generated_at"] = datetime.utcnow()
        return parsed

async def generate_groq_summary(report_data: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    """Generates structured AI summary using Groq fallback provider."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    prompt = f"""You are an engineering management advisor. Analyze this weekly employee report and output strict JSON.
Ground your response exclusively on the provided data without hallucinating new facts.
Report:
{json.dumps(report_data, indent=2)}

Return JSON with exact keys: executive_summary (string), key_highlights (list of strings), blockers_identified (list of strings), manager_recommendation (string)."""

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "You are a professional management analyst. Always return valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2
    }

    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        parsed["model_used"] = "Groq Llama-3 (Free Tier Fallback)"
        parsed["generated_at"] = datetime.utcnow()
        return parsed

def generate_heuristic_summary(report_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic rule-based NLP summary generator.
    100% reliable fallback that never hallucinates and executes offline without network.
    Clearly identifies itself as the local fallback engine.
    """
    updates = report_data.get("work_updates", [])
    answers = report_data.get("answers", [])
    user_name = report_data.get("user_name", "The employee")

    total_hours = sum(u.get("hours_spent", 0) or 0 for u in updates)
    categories = list(set(u.get("category", "General") for u in updates if u.get("category")))

    # Extract answers
    answer_map = {a.get("question_key"): a.get("answer", "") for a in answers}
    accomplishments = answer_map.get("accomplishments", "")
    in_progress = answer_map.get("in_progress", "")
    blockers = answer_map.get("blockers", "")
    priorities = answer_map.get("priorities", "")

    # Highlights strictly grounded in provided data
    highlights = []
    if accomplishments and accomplishments.strip():
        items = [line.strip("- •* \t") for line in accomplishments.split("\n") if len(line.strip()) > 3]
        highlights.extend(items[:3])

    for u in updates[:3]:
        title = u.get("title")
        if title and title not in highlights:
            highlights.append(f"{title} ({u.get('category', 'Task')})")

    if not highlights:
        highlights = ["No specific accomplishments or work updates logged for this period."]

    # Blockers strictly grounded in provided data
    blocker_list = []
    if blockers and len(blockers.strip()) > 3 and "none" not in blockers.lower() and "no blocker" not in blockers.lower():
        b_items = [line.strip("- •* \t") for line in blockers.split("\n") if len(line.strip()) > 3]
        blocker_list.extend(b_items[:2])
    else:
        blocker_list = ["No critical blockers reported this week."]

    if total_hours > 0 or updates:
        cat_str = f" across {', '.join(categories)}" if categories else ""
        hours_str = f" across {total_hours} logged hours" if total_hours > 0 else ""
        exec_summary = (
            f"{user_name} demonstrated steady weekly progress{hours_str}{cat_str}. "
            f"Key focus: {highlights[0].lower() if highlights else 'ongoing tasks'}. "
            f"Next priorities: {priorities.split('.')[0] if priorities else 'sprint execution'}."
        )
    else:
        exec_summary = (
            f"{user_name} submitted a weekly report with no logged work updates. "
            f"Next priorities: {priorities.split('.')[0] if priorities else 'sprint alignment'}."
        )

    if "No critical blockers" not in blocker_list[0]:
        rec = f"Review reported blocker ('{blocker_list[0]}') in upcoming 1-on-1 to support progress."
    elif in_progress:
        rec = f"Review milestones for in-progress work: {in_progress.split('.')[0]}."
    else:
        rec = "Maintain current momentum and align on priorities during team planning."

    return {
        "executive_summary": exec_summary,
        "key_highlights": highlights[:4],
        "blockers_identified": blocker_list,
        "manager_recommendation": rec,
        "model_used": "Built-in Intelligent Summary Engine (Free / Local Fallback)",
        "generated_at": datetime.utcnow()
    }

async def generate_ai_summary_with_retry(report_data: Dict[str, Any], max_retries: int = 2) -> Dict[str, Any]:
    """
    Attempts generation with free AI provider (Gemini or Groq), retrying on transient failures,
    and falls back deterministically to the local heuristic engine so report submission never fails.
    Suppresses live network calls during automated test runs.
    """
    is_test = os.getenv("TESTING") == "1" or settings.ENVIRONMENT.lower() == "test"
    if is_test and not os.getenv("ALLOW_LIVE_AI_IN_TESTS"):
        logger.info("[TESTING] Using deterministic local summary engine for test run.")
        return generate_heuristic_summary(report_data)

    gemini_key = settings.GEMINI_API_KEY
    groq_key = settings.GROQ_API_KEY

    # 1. Primary: Google Gemini with retries
    if gemini_key:
        for attempt in range(max_retries):
            try:
                logger.info(f"Generating AI summary via Gemini (attempt {attempt + 1})...")
                return await generate_gemini_summary(report_data, gemini_key)
            except Exception as e:
                # Sanitize log output to prevent leaking credentials
                safe_err = _sanitize_error(e, gemini_key)
                logger.warning(f"Gemini API attempt {attempt + 1} failed: {safe_err}")

    # 2. Secondary: Groq Llama with retries
    if groq_key:
        for attempt in range(max_retries):
            try:
                logger.info(f"Generating AI summary via Groq (attempt {attempt + 1})...")
                return await generate_groq_summary(report_data, groq_key)
            except Exception as e:
                safe_err = _sanitize_error(e, groq_key)
                logger.warning(f"Groq API attempt {attempt + 1} failed: {safe_err}")

    # 3. Deterministic Local Fallback
    logger.info("Using built-in intelligent summary engine for report summary.")
    return generate_heuristic_summary(report_data)
