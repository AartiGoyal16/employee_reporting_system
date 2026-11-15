"""
Reminder Scheduler — lightweight asyncio background task with atomic database locking.
Runs periodically, finds employees without a submitted report for the current week,
and sends a reminder email on REMINDER_DAY (default: Saturday).
Uses an atomic record in `reminder_logs` to guarantee at-least-once delivery with
concurrency-safe claim locking across multiple workers/instances.

Note on Distributed Delivery Semantics:
Standard SMTP lacks distributed two-phase commit with databases. If an email is accepted
by an SMTP relay but the worker process crashes or network disconnects before the database
record is updated to status 'sent', a subsequent retry cycle may deliver a duplicate email.
Exactly-once delivery cannot be guaranteed without provider-level idempotency keys.
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
    - Accurately tracks eligible, sent, skipped, and failed recipients.
    - Distinguishes between no eligible employees, submitted reports, already reminded, missing SMTP, and delivery failure.
    - Never reports success when 0 emails were sent.
    """
    today_name = datetime.utcnow().strftime("%A").lower()
    reminder_day = settings.REMINDER_DAY.lower()
    week_start, week_end = _get_current_week_boundaries()

    if not force and today_name != reminder_day:
        return {
            "status": "skipped",
            "reason": f"Today is {today_name}, reminder configured for {reminder_day}",
            "message": f"Reminders are scheduled for {reminder_day.capitalize()} (today is {today_name.capitalize()}).",
            "week_start": week_start,
            "week_end": week_end,
            "eligible_count": 0,
            "sent_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "reminded_employees": [],
            "failed_employees": [],
            "skipped_details": {
                "no_employees_assigned": False,
                "submitted_count": 0,
                "already_reminded_count": 0
            }
        }

    logger.info(f"[Reminder] Running check for week {week_start} → {week_end} (force={force}, manager_id={manager_id})")

    db = get_database()

    query = {"role": "employee"}
    if manager_id:
        query["manager_id"] = manager_id

    cursor = db.users.find(query)
    employees = await cursor.to_list(length=500)

    if not employees:
        return {
            "status": "no_eligible",
            "reason": "no_employees",
            "message": "No employees are assigned to this manager.",
            "week_start": week_start,
            "week_end": week_end,
            "eligible_count": 0,
            "sent_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "reminded_employees": [],
            "failed_employees": [],
            "skipped_details": {
                "no_employees_assigned": True,
                "submitted_count": 0,
                "already_reminded_count": 0
            }
        }

    submitted_count = 0
    already_reminded_count = 0
    eligible_candidates = []

    now = datetime.utcnow()
    stale_cutoff = now - timedelta(seconds=300)
    stale_cutoff_iso = stale_cutoff.isoformat()

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
            submitted_count += 1
            continue

        # 2. Check if already reminded successfully or actively claimed
        claim_key = {
            "user_id": emp_id,
            "week_start_date": week_start,
            "type": "deadline_reminder"
        }
        existing_log = await db.reminder_logs.find_one(claim_key)
        if existing_log and existing_log.get("status") == "sent":
            already_reminded_count += 1
            continue
        if existing_log and existing_log.get("status") == "claimed":
            c_at = existing_log.get("claimed_at")
            if c_at and (c_at > stale_cutoff if isinstance(c_at, datetime) else c_at > stale_cutoff_iso):
                already_reminded_count += 1
                continue

        eligible_candidates.append({
            "emp_id": emp_id,
            "emp_name": emp_name,
            "emp_email": emp_email,
            "report": report,
            "claim_key": claim_key
        })

    eligible_count = len(eligible_candidates)
    skipped_count = submitted_count + already_reminded_count

    if eligible_count == 0:
        if already_reminded_count > 0:
            status_val = "already_reminded"
            reason_val = "already_reminded"
            msg = "All unsubmitted employees have already been reminded for this week."
        elif submitted_count > 0:
            status_val = "all_submitted"
            reason_val = "all_submitted"
            msg = "All assigned employees have already submitted their reports for this week."
        else:
            status_val = "no_eligible"
            reason_val = "no_eligible"
            msg = "No eligible employees require reminders at this time."

        return {
            "status": status_val,
            "reason": reason_val,
            "message": msg,
            "week_start": week_start,
            "week_end": week_end,
            "eligible_count": 0,
            "sent_count": 0,
            "skipped_count": skipped_count,
            "failed_count": 0,
            "reminded_employees": [],
            "failed_employees": [],
            "skipped_details": {
                "no_employees_assigned": False,
                "submitted_count": submitted_count,
                "already_reminded_count": already_reminded_count
            }
        }

    # Check SMTP configuration
    from app.services.email_service import is_smtp_configured
    if not is_smtp_configured():
        logger.warning("[Reminder] SMTP is not configured. Cannot dispatch reminders.")
        return {
            "status": "smtp_not_configured",
            "reason": "smtp_not_configured",
            "message": "SMTP email configuration is missing or incomplete. Reminders could not be sent.",
            "week_start": week_start,
            "week_end": week_end,
            "eligible_count": eligible_count,
            "sent_count": 0,
            "skipped_count": skipped_count,
            "failed_count": eligible_count,
            "reminded_employees": [],
            "failed_employees": [{"name": c["emp_name"], "email": c["emp_email"]} for c in eligible_candidates],
            "skipped_details": {
                "no_employees_assigned": False,
                "submitted_count": submitted_count,
                "already_reminded_count": already_reminded_count
            }
        }

    sent_count = 0
    failed_count = 0
    reminded_employees = []
    failed_employees = []

    for cand in eligible_candidates:
        emp_name = cand["emp_name"]
        emp_email = cand["emp_email"]
        claim_key = cand["claim_key"]
        report = cand["report"]

        # Step 2A: Atomically reclaim any failed or abandoned claim (>300s)
        reclaimed = await db.reminder_logs.find_one_and_update(
            {
                **claim_key,
                "$or": [
                    {"status": "failed"},
                    {"status": "claimed", "claimed_at": {"$lte": stale_cutoff}},
                    {"status": "claimed", "claimed_at": {"$lte": stale_cutoff_iso}}
                ]
            },
            {"$set": {"status": "claimed", "claimed_at": now}}
        )

        claim_acquired = False
        if reclaimed:
            claim_acquired = True
        else:
            try:
                await db.reminder_logs.insert_one({
                    **claim_key,
                    "week_end_date": week_end,
                    "status": "claimed",
                    "claimed_at": now
                })
                claim_acquired = True
            except Exception:
                # Concurrent insert race
                claim_acquired = False

        if not claim_acquired:
            already_reminded_count += 1
            continue

        # 3. Dispatch reminder email
        sent = False
        try:
            sent = await send_reminder_email(emp_email, emp_name, week_end)
        except Exception as exc:
            logger.warning(f"[Reminder] Failed to send reminder to {emp_email}: {exc}")
            sent = False

        if sent:
            send_now = datetime.utcnow()
            await db.reminder_logs.update_one(
                claim_key,
                {"$set": {"status": "sent", "sent_at": send_now}},
                upsert=True
            )
            if report:
                await db.weekly_reports.update_one(
                    {"_id": report["_id"]},
                    {"$set": {"reminder_sent": True, "reminder_sent_at": send_now}}
                )
            sent_count += 1
            reminded_employees.append({"name": emp_name, "email": emp_email})
            logger.info(f"[Reminder] Successfully sent reminder to {emp_name} ({emp_email})")
        else:
            fail_now = datetime.utcnow()
            await db.reminder_logs.update_one(
                claim_key,
                {"$set": {"status": "failed", "failed_at": fail_now}},
                upsert=True
            )
            failed_count += 1
            failed_employees.append({"name": emp_name, "email": emp_email})
            logger.warning(f"[Reminder] Delivery failed or unconfirmed for {emp_email}")

    if sent_count == eligible_count and failed_count == 0:
        status_val = "success"
        reason_val = "all_sent"
        msg = f"Deadline reminders successfully sent to {sent_count} team member{'s' if sent_count > 1 else ''}."
    elif sent_count > 0 and failed_count > 0:
        status_val = "partial_success"
        reason_val = "partial_delivery"
        msg = f"Reminders sent to {sent_count} team member{'s' if sent_count > 1 else ''}, but delivery failed for {failed_count}."
    else:
        status_val = "failed"
        reason_val = "delivery_failed"
        msg = f"Failed to deliver reminders to all {failed_count} eligible team member{'s' if failed_count > 1 else ''}."

    return {
        "status": status_val,
        "reason": reason_val,
        "message": msg,
        "week_start": week_start,
        "week_end": week_end,
        "eligible_count": eligible_count,
        "sent_count": sent_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "reminded_employees": reminded_employees,
        "failed_employees": failed_employees,
        "skipped_details": {
            "no_employees_assigned": False,
            "submitted_count": submitted_count,
            "already_reminded_count": already_reminded_count
        }
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
