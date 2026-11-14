import logging
import json
import httpx
from datetime import datetime
from typing import Dict, Any, List
from app.config import settings

logger = logging.getLogger(__name__)

async def generate_gemini_summary(report_data: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    prompt = f"""You are an executive assistant and engineering management advisor.
Analyze the following employee weekly report and daily work updates, and generate a structured executive summary.

EMPLOYEE INFORMATION:
Name: {report_data.get('user_name', 'Employee')}
Week: {report_data.get('week_start_date')} to {report_data.get('week_end_date')}

DAILY WORK UPDATES:
{json.dumps(report_data.get('work_updates', []), indent=2)}

ANSWERS TO WEEKLY QUESTIONS:
{json.dumps(report_data.get('answers', []), indent=2)}

OUTPUT FORMAT:
Respond with valid, strict JSON ONLY (no markdown formatting, no backticks, no extra text):
{{
  "executive_summary": "2-3 sentences providing an executive-level overview of accomplishments and velocity.",
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

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        # Clean any backticks if returned
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        parsed = json.loads(text.strip())
        parsed["model_used"] = "Google Gemini 1.5 Flash (Free Tier)"
        parsed["generated_at"] = datetime.utcnow()
        return parsed

async def generate_groq_summary(report_data: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""You are an engineering management advisor. Analyze this weekly employee report and output strict JSON.
Report:
{json.dumps(report_data, indent=2)}

Return JSON with keys: executive_summary (string), key_highlights (list of strings), blockers_identified (list of strings), manager_recommendation (string)."""

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": "You are a professional management analyst. Always return valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        parsed["model_used"] = "Groq Llama-3.1-8b (Free Tier)"
        parsed["generated_at"] = datetime.utcnow()
        return parsed

def generate_heuristic_summary(report_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Intelligent NLP and heuristic rule-based summary generator.
    Guarantees 100% reliable summary generation even without external API keys or when offline.
    """
    updates = report_data.get("work_updates", [])
    answers = report_data.get("answers", [])
    user_name = report_data.get("user_name", "The employee")

    # Group updates
    total_hours = sum(u.get("hours_spent", 0) or 0 for u in updates)
    categories = list(set(u.get("category", "General") for u in updates if u.get("category")))
    
    # Extract answers
    answer_map = {a.get("question_key"): a.get("answer", "") for a in answers}
    accomplishments = answer_map.get("accomplishments", "")
    in_progress = answer_map.get("in_progress", "")
    blockers = answer_map.get("blockers", "")
    priorities = answer_map.get("priorities", "")

    # Highlights
    highlights = []
    if accomplishments and accomplishments.strip():
        # Split sentences or bullets
        items = [line.strip("- •* \t") for line in accomplishments.split("\n") if len(line.strip()) > 3]
        highlights.extend(items[:3])
    
    for u in updates[:3]:
        title = u.get("title")
        if title and title not in highlights:
            highlights.append(f"{title} ({u.get('category', 'Task')})")

    if not highlights:
        highlights = ["Completed scheduled sprint activities and daily tasks."]

    # Blockers
    blocker_list = []
    if blockers and len(blockers.strip()) > 3 and "none" not in blockers.lower() and "no blocker" not in blockers.lower():
        b_items = [line.strip("- •* \t") for line in blockers.split("\n") if len(line.strip()) > 3]
        blocker_list.extend(b_items[:2])
    else:
        blocker_list = ["No critical blockers reported this week."]

    # Executive summary
    cat_str = f" across {', '.join(categories)}" if categories else ""
    hours_str = f" across {total_hours} logged hours" if total_hours > 0 else ""
    exec_summary = (
        f"{user_name} demonstrated steady weekly progress{hours_str}{cat_str}. "
        f"Key accomplishments focused on {highlights[0].lower() if highlights else 'ongoing tasks'}. "
        f"Priorities for next week are centered on: {priorities.split('.')[0] if priorities else 'sprint execution'}."
    )

    # Manager recommendation
    if "No critical blockers" not in blocker_list[0]:
        rec = f"Review reported blocker ('{blocker_list[0]}') in your 1-on-1 to help unblock progress early."
    elif in_progress:
        rec = f"Align on milestones for currently in-progress deliverables during upcoming sprint check-in."
    else:
        rec = "Maintain current momentum and review upcoming priorities during the Monday planning meeting."

    return {
        "executive_summary": exec_summary,
        "key_highlights": highlights[:4],
        "blockers_identified": blocker_list,
        "manager_recommendation": rec,
        "model_used": "Built-in Intelligent Summary Engine (Free / Local)",
        "generated_at": datetime.utcnow()
    }

async def generate_ai_summary_with_retry(report_data: Dict[str, Any], max_retries: int = 2) -> Dict[str, Any]:
    """
    Attempts generation with free AI provider (Gemini or Groq), retrying if transient failures occur,
    and falls back safely to the intelligent heuristic engine so the submission never fails.
    """
    gemini_key = settings.GEMINI_API_KEY
    groq_key = settings.GROQ_API_KEY

    # 1. Try Gemini if configured
    if gemini_key:
        for attempt in range(max_retries):
            try:
                logger.info(f"Generating AI summary via Gemini (attempt {attempt + 1})...")
                return await generate_gemini_summary(report_data, gemini_key)
            except Exception as e:
                logger.warning(f"Gemini API attempt {attempt + 1} failed: {e}")

    # 2. Try Groq if configured
    if groq_key:
        for attempt in range(max_retries):
            try:
                logger.info(f"Generating AI summary via Groq (attempt {attempt + 1})...")
                return await generate_groq_summary(report_data, groq_key)
            except Exception as e:
                logger.warning(f"Groq API attempt {attempt + 1} failed: {e}")

    # 3. Fallback to resilient heuristic NLP summary
    logger.info("Using built-in intelligent summary engine for report summary.")
    return generate_heuristic_summary(report_data)
