"""
Reminder Scheduler — lightweight asyncio background task.
Runs once per day, finds employees without a submitted report
for the current week, and sends a reminder email on REMINDER_DAY
(default: Saturday). Uses a per-report flag to avoid duplicate sends.
Also supports on-demand manager trigger.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from app.database import get_database
from app.services.email_service import send_reminder_email
from app.config import settings

logger = logging.getLogger(__name__)


def _get_current_week_boundaries():
    today = datetime.utcnow().date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


async def run_reminder_check(manager_id: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
    """
    Find employees who haven't submitted this week's report
    and haven't already been reminded, then send them a reminder.
    If force=True, ignores the day-of-week check (useful for manual trigger).
    If manager_id is given, only targets employees belonging to that manager.
    """
    today_name = datetime.utcnow().strftime("%A").lower()
    reminder_day = settings.REMINDER_DAY.lower()

    if not force and today_name != reminder_day:
        return {"status": "skipped", "reason": f"Today is {today_name}, reminder configured for {reminder_day}", "sent_count": 0}

    week_start, week_end = _get_current_week_boundaries()
    logger.info(f"[Reminder] Running check for week {week_start} → {week_end} (force={force}, manager_id={manager_id})")

    db = get_database()

    query = {"role": "employee"}
    if manager_id:
        query["manager_id"] = manager_id

    cursor = db.users.find(query)
    employees = await cursor.to_list(length=500)

    sent_count = 0
    reminded_employees = []

    for emp in employees:
        emp_id = str(emp["_id"])
        emp_email = emp.get("email")
        emp_name = emp.get("name", "Employee")

        if not emp_email:
            continue

        # Check if report exists for this week
        report = await db.weekly_reports.find_one({
            "user_id": emp_id,
            "week_start_date": week_start,
            "week_end_date": week_end,
        })

        if report and report.get("status") == "submitted":
            continue  # Already submitted

        if report and report.get("reminder_sent") and not force:
            continue  # Already reminded this cycle

        # Send reminder
        try:
            sent = await send_reminder_email(emp_email, emp_name, week_end)
            if report:
                await db.weekly_reports.update_one(
                    {"_id": report["_id"]},
                    {"$set": {"reminder_sent": True}}
                )
            sent_count += 1
            reminded_employees.append({"name": emp_name, "email": emp_email})
            logger.info(f"[Reminder] Sent reminder to {emp_name} ({emp_email})")
        except Exception as exc:
            logger.warning(f"[Reminder] Failed to send reminder to {emp_email}: {exc}")

    return {
        "status": "success",
        "week_start": week_start,
        "week_end": week_end,
        "sent_count": sent_count,
        "reminded_employees": reminded_employees
    }


async def start_reminder_scheduler():
    """
    Background task loop — checks once every hour whether it's the
    reminder day, then runs the reminder check.
    """
    logger.info("[Reminder] Scheduler started. Monitoring weekly submission deadlines.")
    while True:
        try:
            await run_reminder_check()
        except Exception as exc:
            logger.error(f"[Reminder] Scheduler error (will retry next cycle): {exc}")
        # Sleep for 1 hour before next check
        await asyncio.sleep(3600)
