import logging
from fastapi import APIRouter, HTTPException, status, Depends, Response
from typing import List, Optional
from datetime import datetime, timedelta
from bson import ObjectId
from app.database import get_database
from app.models.report import (
    WeeklyReportCreateOrSave,
    WeeklyReportResponse,
    WeeklyReportSubmit,
    QuestionAnswer,
    AISummary
)
from app.models.update import WorkUpdateResponse
from app.auth.dependencies import get_current_user, require_employee
from app.services.ai_summary import generate_ai_summary_with_retry
from app.services.pdf_export import generate_weekly_report_pdf
from app.services.email_service import send_manager_notification_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["Weekly Reports"])

def get_current_week_boundaries():
    today = datetime.utcnow().date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")

async def populate_report_details(report: dict, db) -> dict:
    # 1. If report is submitted and has an immutable snapshot, use the snapshot for historical consistency
    if report.get("status") == "submitted" and report.get("work_updates_snapshot"):
        updates_res = []
        for u in report["work_updates_snapshot"]:
            updates_res.append(WorkUpdateResponse(
                id=str(u.get("id") or u.get("_id", "")),
                user_id=u["user_id"],
                date=u["date"],
                title=u["title"],
                description=u["description"],
                category=u.get("category", "Feature"),
                hours_spent=u.get("hours_spent"),
                created_at=u.get("created_at") or datetime.utcnow(),
                updated_at=u.get("updated_at") or datetime.utcnow()
            ))
        report["work_updates"] = updates_res
        report["id"] = str(report["_id"])
        return report

    # 2. Otherwise (draft or pre-snapshot), fetch work updates for this employee in the report's date range
    cursor = db.work_updates.find({
        "user_id": report["user_id"],
        "date": {"$gte": report["week_start_date"], "$lte": report["week_end_date"]}
    }).sort("date", 1)
    raw_updates = await cursor.to_list(length=100)
    
    updates_res = []
    for u in raw_updates:
        updates_res.append(WorkUpdateResponse(
            id=str(u["_id"]),
            user_id=u["user_id"],
            date=u["date"],
            title=u["title"],
            description=u["description"],
            category=u.get("category", "Feature"),
            hours_spent=u.get("hours_spent"),
            created_at=u.get("created_at", datetime.utcnow()),
            updated_at=u.get("updated_at", datetime.utcnow())
        ))
    report["work_updates"] = updates_res
    report["id"] = str(report["_id"])
    return report

@router.get("/current", response_model=WeeklyReportResponse)
async def get_or_init_current_week_report(current_user: dict = Depends(require_employee)):
    """
    Get current week's report for the logged in employee.
    If none exists, initializes a clean draft pre-populated with active questions.
    """
    db = get_database()
    start_date, end_date = get_current_week_boundaries()

    report = await db.weekly_reports.find_one({
        "user_id": current_user["id"],
        "week_start_date": start_date,
        "week_end_date": end_date
    })

    if not report:
        # Fetch active questions
        cursor = db.questions.find({"is_active": True}).sort("order", 1)
        questions = await cursor.to_list(length=20)
        
        answers = [
            {"question_key": q["key"], "question_text": q["question_text"], "answer": ""}
            for q in questions
        ]

        # Find manager name if assigned
        manager_name = None
        if current_user.get("manager_id"):
            try:
                m_oid = ObjectId(current_user["manager_id"])
            except Exception:
                m_oid = current_user["manager_id"]
            manager = await db.users.find_one({"_id": m_oid})
            if manager:
                manager_name = manager.get("name")

        now = datetime.utcnow()
        doc = {
            "_id": ObjectId(),
            "user_id": current_user["id"],
            "user_name": current_user["name"],
            "user_email": current_user["email"],
            "manager_id": current_user.get("manager_id"),
            "manager_name": manager_name,
            "week_start_date": start_date,
            "week_end_date": end_date,
            "work_update_ids": [],
            "answers": answers,
            "status": "draft",
            "submitted_at": None,
            "ai_summary": None,
            "created_at": now,
            "updated_at": now
        }
        await db.weekly_reports.insert_one(doc)
        report = doc

    populated = await populate_report_details(report, db)
    return WeeklyReportResponse(**populated)

@router.get("", response_model=List[WeeklyReportResponse])
async def get_my_report_history(current_user: dict = Depends(require_employee)):
    """Weekly report history for the logged in employee."""
    db = get_database()
    cursor = db.weekly_reports.find({"user_id": current_user["id"]}).sort("week_start_date", -1)
    reports = await cursor.to_list(length=100)

    results = []
    for r in reports:
        populated = await populate_report_details(r, db)
        results.append(WeeklyReportResponse(**populated))
    return results

@router.get("/{report_id}", response_model=WeeklyReportResponse)
async def get_report_by_id(report_id: str, current_user: dict = Depends(get_current_user)):
    """
    Get a single weekly report.
    Access Control:
    - Employees can view only their own reports.
    - Managers can view reports only of their assigned employees.
    """
    db = get_database()
    try:
        r_oid = ObjectId(report_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid report ID format")

    report = await db.weekly_reports.find_one({"_id": r_oid})
    if not report:
        raise HTTPException(status_code=404, detail="Weekly report not found")

    is_owner = report["user_id"] == current_user["id"]
    is_assigned_manager = (
        current_user.get("role") == "manager" and
        str(report.get("manager_id")) == current_user["id"]
    )

    if not is_owner and not is_assigned_manager:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to access this report."
        )

    populated = await populate_report_details(report, db)
    return WeeklyReportResponse(**populated)

@router.post("/draft", response_model=WeeklyReportResponse)
async def save_report_draft(
    report_data: WeeklyReportCreateOrSave,
    current_user: dict = Depends(require_employee)
):
    """Save or update draft weekly report. After submission or during submission, the report is strictly read-only."""
    db = get_database()
    
    # Check if a report for this week already exists
    report = await db.weekly_reports.find_one({
        "user_id": current_user["id"],
        "week_start_date": report_data.week_start_date,
        "week_end_date": report_data.week_end_date
    })

    if report and report.get("status") in ["submitting", "submitted"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Report is currently {report.get('status')} and cannot be modified."
        )

    answers_list = [a.dict() for a in report_data.answers]
    now = datetime.utcnow()

    if report:
        res = await db.weekly_reports.update_one(
            {"_id": report["_id"], "status": "draft"},
            {
                "$set": {
                    "answers": answers_list,
                    "updated_at": now
                }
            }
        )
        if getattr(res, "matched_count", 0) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Report is currently submitting or submitted and cannot be modified."
            )
        updated = await db.weekly_reports.find_one({"_id": report["_id"]})
    else:
        # Create draft
        manager_name = None
        if current_user.get("manager_id"):
            try:
                m_oid = ObjectId(current_user["manager_id"])
            except Exception:
                m_oid = current_user["manager_id"]
            manager = await db.users.find_one({"_id": m_oid})
            if manager:
                manager_name = manager.get("name")

        doc = {
            "_id": ObjectId(),
            "user_id": current_user["id"],
            "user_name": current_user["name"],
            "user_email": current_user["email"],
            "manager_id": current_user.get("manager_id"),
            "manager_name": manager_name,
            "week_start_date": report_data.week_start_date,
            "week_end_date": report_data.week_end_date,
            "work_update_ids": [],
            "answers": answers_list,
            "status": "draft",
            "submitted_at": None,
            "ai_summary": None,
            "created_at": now,
            "updated_at": now
        }
        await db.weekly_reports.insert_one(doc)
        updated = doc

    populated = await populate_report_details(updated, db)
    return WeeklyReportResponse(**populated)

@router.post("/{report_id}/submit", response_model=WeeklyReportResponse)
async def submit_weekly_report(
    report_id: str,
    submit_payload: Optional[WeeklyReportSubmit] = None,
    current_user: dict = Depends(require_employee)
):
    """
    Submits weekly report:
    1. Atomic conditional lock from 'draft' to 'submitting' to prevent concurrent submissions.
    2. Snapshots all weekly work updates for historical immutability.
    3. Generates structured AI summary (Gemini / Groq / NLP fallback with retries).
    4. Locks report to 'submitted'.
    5. Dispatches manager notification.
    """
    import os
    import uuid
    from app.services.ai_summary import _sanitize_error

    db = get_database()
    try:
        r_oid = ObjectId(report_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid report ID format")

    claim_token = str(uuid.uuid4())
    now = datetime.utcnow()

    # Atomic conditional lock: only a draft report owned by current_user can be claimed
    claimed = await db.weekly_reports.find_one_and_update(
        {"_id": r_oid, "user_id": current_user["id"], "status": "draft"},
        {"$set": {
            "status": "submitting",
            "submission_claim_token": claim_token,
            "submission_started_at": now,
            "updated_at": now
        }}
    )

    if not claimed:
        # Investigate rejection reason
        existing = await db.weekly_reports.find_one({"_id": r_oid})
        if not existing:
            raise HTTPException(status_code=404, detail="Weekly report not found")
        if existing["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Forbidden: You cannot submit reports for another employee")
        if existing.get("status") == "submitted":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This report has already been submitted and is read-only."
            )
        if existing.get("status") == "submitting":
            # Check for stale abandoned submission (> 120 seconds) after server crash
            started_at = existing.get("submission_started_at")
            started_at_dt = None
            if started_at:
                if isinstance(started_at, str):
                    try:
                        started_at_dt = datetime.fromisoformat(started_at)
                    except Exception:
                        started_at_dt = None
                elif isinstance(started_at, datetime):
                    started_at_dt = started_at

            age = (datetime.utcnow() - started_at_dt).total_seconds() if started_at_dt else 999
            if age > 120:
                logger.warning(f"Submission {report_id} was stale ({age:.1f}s). Attempting atomic takeover with claim {claim_token}.")
                stale_filter = {
                    "_id": r_oid,
                    "user_id": current_user["id"],
                    "status": "submitting"
                }
                if existing.get("submission_claim_token"):
                    stale_filter["submission_claim_token"] = existing["submission_claim_token"]
                elif started_at:
                    stale_filter["submission_started_at"] = started_at

                claimed = await db.weekly_reports.find_one_and_update(
                    stale_filter,
                    {"$set": {
                        "status": "submitting",
                        "submission_claim_token": claim_token,
                        "submission_started_at": now,
                        "updated_at": now
                    }}
                )

            if not claimed:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Report submission is already in progress. Please wait a moment."
                )
        else:
            raise HTTPException(status_code=400, detail="Report cannot be submitted in its current state")

    report = claimed

    async def _safe_rollback(detail_msg: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        await db.weekly_reports.update_one(
            {"_id": r_oid, "status": "submitting", "submission_claim_token": claim_token},
            {"$set": {"status": "draft", "updated_at": datetime.utcnow()}, "$unset": {"submission_claim_token": ""}}
        )
        raise HTTPException(status_code=status_code, detail=detail_msg)

    try:
        # 1. Validate legitimate Monday-to-Sunday week
        try:
            start_dt = datetime.strptime(report.get("week_start_date", ""), "%Y-%m-%d")
            end_dt = datetime.strptime(report.get("week_end_date", ""), "%Y-%m-%d")
            if start_dt.weekday() != 0 or end_dt.weekday() != 6 or (end_dt - start_dt).days != 6:
                await _safe_rollback("Report week must span a legitimate Monday-to-Sunday period (7 days).")
        except (ValueError, TypeError):
            await _safe_rollback("Invalid report week start or end date format.")

        # Check if an active mutation lease is held on this report (e.g. work update mutation in flight)
        cur_rep = await db.weekly_reports.find_one({"_id": r_oid})
        active_leases = cur_rep.get("active_leases", []) if cur_rep else []
        if active_leases:
            await _safe_rollback(
                "A work-update mutation is currently in progress for this report. Please wait a moment.",
                status_code=status.HTTP_409_CONFLICT
            )

        # 2. Extract and validate answers
        answers = [a.dict() for a in submit_payload.answers] if (submit_payload and submit_payload.answers is not None) else report.get("answers", [])
        REQUIRED_KEYS = {"accomplishments", "in_progress", "blockers", "priorities"}

        if not answers:
            await _safe_rollback("All 4 weekly reflection questions must be answered before submitting.")

        keys = [a.get("question_key") for a in answers]

        # Check duplicates
        if len(keys) != len(set(keys)):
            await _safe_rollback("Duplicate question keys found in report answers.")

        # Check count of distinct answers
        if len(keys) != 4:
            await _safe_rollback(f"Report submission requires exactly 4 distinct weekly questions (received {len(keys)}).")

        # Check unknown keys
        unknown_keys = set(keys) - REQUIRED_KEYS
        if unknown_keys:
            await _safe_rollback(f"Unknown question keys: {list(unknown_keys)}. Required keys are: {list(REQUIRED_KEYS)}.")

        # Check missing keys
        missing_keys = REQUIRED_KEYS - set(keys)
        if missing_keys:
            await _safe_rollback(f"Missing required question keys: {list(missing_keys)}.")

        # Check blank or whitespace-only answers
        for a in answers:
            ans_text = str(a.get("answer", "")).strip()
            if not ans_text:
                await _safe_rollback(f"Answer for question '{a.get('question_key')}' cannot be blank.")

        # Fetch daily work updates for the report's week and build immutable snapshot
        cursor = db.work_updates.find({
            "user_id": current_user["id"],
            "date": {"$gte": report["week_start_date"], "$lte": report["week_end_date"]}
        }).sort("date", 1)
        work_updates = await cursor.to_list(length=100)

        work_update_ids = [str(u["_id"]) for u in work_updates]
        snapshot = [
            {
                "id": str(u["_id"]),
                "user_id": u["user_id"],
                "date": u["date"],
                "title": u["title"],
                "category": u.get("category", "Feature"),
                "description": u["description"],
                "hours_spent": u.get("hours_spent"),
                "created_at": u.get("created_at"),
                "updated_at": u.get("updated_at")
            }
            for u in work_updates
        ]

        # Prepare data for AI summary generator
        report_ai_payload = {
            "user_name": current_user["name"],
            "week_start_date": report["week_start_date"],
            "week_end_date": report["week_end_date"],
            "work_updates": snapshot,
            "answers": answers
        }

        # Generate AI summary with retry and fallback
        ai_summary_dict = await generate_ai_summary_with_retry(report_ai_payload, max_retries=2)

        now = datetime.utcnow()
        update_fields = {
            "answers": answers,
            "work_update_ids": work_update_ids,
            "work_updates_snapshot": snapshot,
            "status": "submitted",
            "submitted_at": now,
            "ai_summary": ai_summary_dict,
            "updated_at": now
        }

        # Finalize report atomically ensuring claim token matches
        finalize_res = await db.weekly_reports.update_one(
            {"_id": r_oid, "status": "submitting", "submission_claim_token": claim_token},
            {"$set": update_fields, "$unset": {"submission_claim_token": ""}}
        )
        if getattr(finalize_res, "matched_count", 0) == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Submission ownership lost to a concurrent session. Report was not submitted."
            )
    except HTTPException:
        raise
    except Exception as exc:
        safe_err = _sanitize_error(exc)
        logger.error(f"Error during report submission for {report_id} (claim {claim_token}): {safe_err}", exc_info=True)
        # Attempt to roll back status to draft only if this request owns the claim token
        await db.weekly_reports.update_one(
            {"_id": r_oid, "status": "submitting", "submission_claim_token": claim_token},
            {"$set": {"status": "draft", "updated_at": datetime.utcnow()}, "$unset": {"submission_claim_token": ""}}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while processing your report submission. Please try again later."
        )

    updated_report = await db.weekly_reports.find_one({"_id": r_oid})

    # Automated manager notification (Bonus feature: Email manager upon submission)
    manager_id = report.get("manager_id")
    is_test = os.getenv("TESTING") == "1"
    if manager_id:
        try:
            try:
                m_oid = ObjectId(manager_id)
            except Exception:
                m_oid = manager_id
            manager = await db.users.find_one({"_id": m_oid})
            if manager and manager.get("email"):
                highlights = ai_summary_dict.get("key_highlights", []) if ai_summary_dict else []
                if is_test:
                    logger.info(f"[TESTING] Suppressed email to manager {manager['email']}")
                else:
                    await send_manager_notification_email(
                        manager_email=manager["email"],
                        manager_name=manager.get("name", "Manager"),
                        employee_name=current_user.get("name", "Employee"),
                        week_start=report["week_start_date"],
                        week_end=report["week_end_date"],
                        ai_highlights=highlights,
                        report_id=str(r_oid),
                    )
            else:
                logger.info(f"Manager {manager_id} has no registered email. Skipped notification.")
        except Exception as e:
            logger.warning(f"Could not send manager notification email: {e}")

    populated = await populate_report_details(updated_report, db)
    return WeeklyReportResponse(**populated)

@router.get("/{report_id}/pdf")
async def download_report_pdf(report_id: str, current_user: dict = Depends(get_current_user)):
    """
    Bonus: Generate and download clean PDF report.
    Allowed for the report's owner and assigned manager.
    """
    db = get_database()
    try:
        r_oid = ObjectId(report_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid report ID format")

    report = await db.weekly_reports.find_one({"_id": r_oid})
    if not report:
        raise HTTPException(status_code=404, detail="Weekly report not found")

    is_owner = report["user_id"] == current_user["id"]
    is_assigned_manager = (
        current_user.get("role") == "manager" and
        str(report.get("manager_id")) == current_user["id"]
    )

    if not is_owner and not is_assigned_manager:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You cannot export this report."
        )

    populated = await populate_report_details(report, db)
    # Serialize updates for PDF
    serialized_updates = [
        u.dict() if hasattr(u, "dict") else u
        for u in populated.get("work_updates", [])
    ]
    populated["work_updates"] = serialized_updates

    pdf_stream = generate_weekly_report_pdf(populated)
    filename = f"Weekly_Report_{populated.get('week_start_date')}_{populated.get('user_name', 'Employee').replace(' ', '_')}.pdf"

    return Response(
        content=pdf_stream.getvalue(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\""
        }
    )
