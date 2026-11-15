import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Add backend directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import settings
from app.services.ai_summary import generate_gemini_summary, generate_ai_summary_with_retry

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("gemini_live_test")

async def test_live_gemini():
    api_key = os.getenv("GEMINI_API_KEY") or settings.GEMINI_API_KEY
    if not api_key:
        print("\n[ERROR] GEMINI_API_KEY is not set in environment or backend/.env file.")
        print("Please add your API key to backend/.env: GEMINI_API_KEY=\"AIzaSy...\" and re-run.\n")
        return

    # Strictly mask the key for display
    masked_key = f"{api_key[:6]}...[REDACTED]...{api_key[-4:]}" if len(api_key) > 12 else "[REDACTED]"
    model = os.getenv("GEMINI_MODEL") or getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")

    print("=================================================================")
    print("           Google Gemini API Live Integration Check              ")
    print("=================================================================")
    print(f"API Key Detected: {masked_key}")
    print(f"Configured Model: {model}")
    print("Testing direct generation via Google AI Studio Developer API...\n")

    sample_report = {
        "user_name": "Alex Rivera",
        "week_start_date": "2026-11-09",
        "week_end_date": "2026-11-15",
        "work_updates": [
            {
                "title": "Database Indexing & Query Optimization",
                "category": "Feature",
                "hours_spent": 7.0,
                "description": "Refactored MongoDB indexes for weekly reporting API."
            },
            {
                "title": "Bug Fix: Concurrency in Report Submission",
                "category": "Bug Fix",
                "hours_spent": 5.0,
                "description": "Implemented atomic draft status lock preventing double submissions."
            }
        ],
        "answers": [
            {
                "question_key": "accomplishments",
                "answer": "Completed database indexing and resolved submission concurrency issues."
            },
            {
                "question_key": "in_progress",
                "answer": "Adding comprehensive test coverage and documentation."
            },
            {
                "question_key": "blockers",
                "answer": "No major blockers this week."
            },
            {
                "question_key": "priorities",
                "answer": "Deploying the MVP to cloud staging."
            }
        ]
    }

    try:
        result = await generate_gemini_summary(sample_report, api_key=api_key, model_override=model)
        print("[SUCCESS] Gemini API responded successfully!")
        print(f"Model Used: {result.get('model_used')}")
        print("\n--- Generated Summary ---")
        print(f"Executive Summary: {result.get('executive_summary')}")
        print("Key Highlights:")
        for h in result.get("key_highlights", []):
            print(f"  - {h}")
        print(f"Blockers: {result.get('blockers_identified')}")
        print(f"Manager Recommendation: {result.get('manager_recommendation')}")
        print("-------------------------\n")
    except Exception as e:
        err_type = type(e).__name__
        err_str = str(e)
        # Redact any accidental occurrence of the secret
        err_str = err_str.replace(api_key, "[REDACTED_API_KEY]")
        print(f"\n[FAILURE] Direct Gemini call failed with {err_type}:")
        print(f"Detail: {err_str}\n")

        print("Testing multi-tier fallback resilience...")
        fallback_result = await generate_ai_summary_with_retry(sample_report)
        print(f"Fallback Active: {fallback_result.get('model_used')}")
        print("Summary generation succeeded via resilient fallback engine.\n")

if __name__ == "__main__":
    asyncio.run(test_live_gemini())
