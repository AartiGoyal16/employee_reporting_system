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
from app.auth.dependencies import get_current_user
from app.services.ai_summary import generate_ai_summary_with_retry
from app.services.pdf_export import generate_weekly_report_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["Weekly Reports"])

def get_current_week_boundaries():
    today = datetime.utcnow().date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")

async def populate_report_details(report: dict, db) -> dict:
    # 1. Fetch work updates for this employee in the report's date range
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
async def get_or_init_current_week_report(current_user: dict = Depends(get_current_user)):
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
async def get_my_report_history(current_user: dict = Depends(get_current_user)):
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
    current_user: dict = Depends(get_current_user)
):
    """Save or update draft weekly report. After submission, the report is strictly read-only."""
    db = get_database()
    
    # Check if a report for this week already exists
    report = await db.weekly_reports.find_one({
        "user_id": current_user["id"],
        "week_start_date": report_data.week_start_date,
        "week_end_date": report_data.week_end_date
    })

    if report and report.get("status") == "submitted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Report has already been submitted and is strictly read-only."
        )

    answers_list = [a.dict() for a in report_data.answers]
    now = datetime.utcnow()

    if report:
        await db.weekly_reports.update_one(
            {"_id": report["_id"]},
            {
                "$set": {
                    "answers": answers_list,
                    "updated_at": now
                }
            }
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
    current_user: dict = Depends(get_current_user)
):
    """
    Submits weekly report:
    1. Validates report exists and belongs to current user.
    2. Validates it is not already submitted (immutable once submitted).
    3. Fetches all weekly work updates.
    4. Generates structured AI summary (Gemini / Groq / NLP fallback with retries).
    5. Locks report to 'submitted'.
    6. Logs automated manager notification (Bonus feature).
    """
    db = get_database()
    try:
        r_oid = ObjectId(report_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid report ID format")

    report = await db.weekly_reports.find_one({"_id": r_oid})
    if not report:
        raise HTTPException(status_code=404, detail="Weekly report not found")

    if report["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden: You cannot submit reports for another employee")

    if report.get("status") == "submitted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This report has already been submitted and is read-only."
        )

    # Update answers if supplied in payload
    if submit_payload and submit_payload.answers is not None:
        report["answers"] = [a.dict() for a in submit_payload.answers]

    # Fetch daily work updates for the report's week
    cursor = db.work_updates.find({
        "user_id": current_user["id"],
        "date": {"$gte": report["week_start_date"], "$lte": report["week_end_date"]}
    }).sort("date", 1)
    work_updates = await cursor.to_list(length=100)

    work_update_ids = [str(u["_id"]) for u in work_updates]
    serialized_updates = [
        {
            "date": u["date"],
            "title": u["title"],
            "category": u.get("category", "Feature"),
            "description": u["description"],
            "hours_spent": u.get("hours_spent")
        }
        for u in work_updates
    ]

    # Prepare data for AI summary generator
    report_ai_payload = {
        "user_name": current_user["name"],
        "week_start_date": report["week_start_date"],
        "week_end_date": report["week_end_date"],
        "work_updates": serialized_updates,
        "answers": report.get("answers", [])
    }

    # Generate AI summary with retry and fallback
    ai_summary_dict = await generate_ai_summary_with_retry(report_ai_payload, max_retries=2)

    now = datetime.utcnow()
    update_fields = {
        "answers": report.get("answers", []),
        "work_update_ids": work_update_ids,
        "status": "submitted",
        "submitted_at": now,
        "ai_summary": ai_summary_dict,
        "updated_at": now
    }

    await db.weekly_reports.update_one({"_id": r_oid}, {"$set": update_fields})
    updated_report = await db.weekly_reports.find_one({"_id": r_oid})

    # Bonus: Simulate automated manager notification
    manager_id = report.get("manager_id")
    if manager_id:
        logger.info(
            f"📧 [NOTIFICATION SIMULATION] Report submitted by {current_user['name']} "
            f"for week {report['week_start_date']} to {report['week_end_date']}. "
            f"Notification sent to Manager ID: {manager_id}."
        )

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
