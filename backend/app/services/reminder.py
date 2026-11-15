"""
Reminder Scheduler — lightweight asyncio background task with atomic database locking.
Runs periodically, finds employees without a submitted report for the current week,
and sends a reminder email on REMINDER_DAY (default: Saturday).
Uses an atomic record in `reminder_logs` to guarantee idempotency across multiple workers/instances.
"""
import os
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
    Find employees who haven't submitted this week's report and send a reminder.
    - Idempotent: Uses atomic claim in `reminder_logs` to prevent duplicate emails across workers.
    - Respects TESTING mode to suppress external network calls.
    - force=True bypasses the day-of-week check for on-demand manager triggers.
    """
    today_name = datetime.utcnow().strftime("%A").lower()
    reminder_day = settings.REMINDER_DAY.lower()

    if not force and today_name != reminder_day:
        return {
            "status": "skipped",
            "reason": f"Today is {today_name}, reminder configured for {reminder_day}",
            "sent_count": 0
        }

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
    is_test = os.getenv("TESTING") == "1" or settings.ENVIRONMENT.lower() == "test"

    for emp in employees:
        emp_id = str(emp["_id"])
        emp_email = emp.get("email")
        emp_name = emp.get("name", "Employee")

        if not emp_email:
            continue

        # 1. Check if report is already submitted this week
        report = await db.weekly_reports.find_one({
            "user_id": emp_id,
            "week_start_date": week_start,
            "week_end_date": week_end,
        })

        if report and report.get("status") == "submitted":
            continue

        # 2. Idempotency Check: Atomic claim via reminder_logs collection
        claim_key = {
            "user_id": emp_id,
            "week_start_date": week_start,
            "type": "deadline_reminder"
        }

        if not force:
            existing = await db.reminder_logs.find_one(claim_key)
            if existing and existing.get("status") in ["claimed", "sent"]:
                continue

            # Atomically attempt to insert the claim to prevent other instances from double-sending
            try:
                await db.reminder_logs.insert_one({
                    **claim_key,
                    "week_end_date": week_end,
                    "status": "claimed",
                    "claimed_at": datetime.utcnow()
                })
            except Exception:
                # Duplicate record exists; another instance claimed it
                continue

        # 3. Dispatch reminder email
        try:
            if is_test:
                logger.info(f"[TESTING] Suppressed actual email send to {emp_email}")
                sent = True
            else:
                sent = await send_reminder_email(emp_email, emp_name, week_end)

            now = datetime.utcnow()
            # Update reminder log to sent
            await db.reminder_logs.update_one(
                claim_key,
                {"$set": {"status": "sent", "sent_at": now}},
                upsert=True
            )

            # Update report doc if present
            if report:
                await db.weekly_reports.update_one(
                    {"_id": report["_id"]},
                    {"$set": {"reminder_sent": True, "reminder_sent_at": now}}
                )

            sent_count += 1
            reminded_employees.append({"name": emp_name, "email": emp_email})
            logger.info(f"[Reminder] Sent reminder to {emp_name} ({emp_email})")
        except Exception as exc:
            logger.warning(f"[Reminder] Failed to send reminder to {emp_email}: {exc}")
            # Release failed claim so subsequent run can retry
            try:
                await db.reminder_logs.delete_one(claim_key)
            except Exception:
                pass

    return {
        "status": "success",
        "week_start": week_start,
        "week_end": week_end,
        "sent_count": sent_count,
        "reminded_employees": reminded_employees
    }


async def start_reminder_scheduler():
    """
    Background task loop — checks once per hour whether it's the
    reminder day, then runs the reminder check.
    Gracefully terminates on asyncio.CancelledError.
    """
    logger.info("[Reminder] Scheduler started. Monitoring weekly submission deadlines.")
    while True:
        try:
            await run_reminder_check()
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            logger.info("[Reminder] Scheduler received cancellation. Stopping loop cleanly.")
            break
        except Exception as exc:
            logger.error(f"[Reminder] Scheduler error (will retry next cycle): {exc}")
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                logger.info("[Reminder] Scheduler received cancellation during error sleep. Stopping.")
                break
