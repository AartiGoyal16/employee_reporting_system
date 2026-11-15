from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional
from bson import ObjectId
from app.database import get_database
from app.models.report import WeeklyReportResponse
from app.models.user import UserResponse
from app.auth.dependencies import require_manager
from app.routers.reports import populate_report_details

router = APIRouter(prefix="/manager", tags=["Manager Operations"])

@router.get("/employees", response_model=List[UserResponse])
async def get_my_assigned_employees(current_user: dict = Depends(require_manager)):
    """
    Manager can see ONLY their assigned employees.
    Strict role-based isolation.
    """
    db = get_database()
    cursor = db.users.find({
        "role": "employee",
        "manager_id": current_user["id"]
    }).sort("name", 1)
    
    employees = await cursor.to_list(length=100)
    results = []
    for emp in employees:
        results.append(UserResponse(
            id=str(emp["_id"]),
            email=emp["email"],
            name=emp["name"],
            role=emp["role"],
            department=emp.get("department"),
            manager_id=emp.get("manager_id"),
            created_at=emp.get("created_at")
        ))
    return results

@router.get("/reports", response_model=List[WeeklyReportResponse])
async def get_team_reports(
    employee_id: Optional[str] = Query(None, description="Filter by assigned employee ID"),
    status_filter: Optional[str] = Query(None, description="Filter by status ('submitted', 'draft')"),
    current_user: dict = Depends(require_manager)
):
    """
    Manager dashboard showing reports ONLY for their assigned employees.
    Strictly queries by `manager_id: current_user.id`.
    """
    db = get_database()
    query = {"manager_id": current_user["id"]}

    if employee_id:
        # Validate that the requested employee is actually assigned to this manager
        try:
            emp_oid = ObjectId(employee_id)
        except Exception:
            emp_oid = employee_id
        emp = await db.users.find_one({"_id": emp_oid, "manager_id": current_user["id"]})
        if not emp:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Employee is not assigned to you."
            )
        query["user_id"] = employee_id

    if status_filter:
        query["status"] = status_filter

    cursor = db.weekly_reports.find(query).sort("submitted_at", -1)
    reports = await cursor.to_list(length=150)

    results = []
    for r in reports:
        populated = await populate_report_details(r, db)
        results.append(WeeklyReportResponse(**populated))
    return results

@router.get("/reports/{report_id}", response_model=WeeklyReportResponse)
async def get_team_report_detail(
    report_id: str,
    current_user: dict = Depends(require_manager)
):
    """
    Manager views full report (work updates, 4 answers, and AI summary).
    Strict authorization: ensures the report belongs to an assigned employee.
    """
    db = get_database()
    try:
        r_oid = ObjectId(report_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid report ID format")

    report = await db.weekly_reports.find_one({"_id": r_oid})
    if not report:
        raise HTTPException(status_code=404, detail="Weekly report not found")

    if str(report.get("manager_id")) != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: This report does not belong to your assigned employees."
        )

    populated = await populate_report_details(report, db)
    return WeeklyReportResponse(**populated)

@router.post("/send-reminders")
async def trigger_team_reminders(current_user: dict = Depends(require_manager)):
    """
    Manager can manually trigger deadline reminder emails
    to all their assigned employees who haven't submitted yet this week.
    """
    from app.services.reminder import run_reminder_check
    result = await run_reminder_check(manager_id=current_user["id"], force=True)
    return result

@router.get("/unassigned-employees", response_model=List[UserResponse])
async def get_unassigned_employees(current_user: dict = Depends(require_manager)):
    """Retrieve employees who do not currently have an assigned manager."""
    db = get_database()
    cursor = db.users.find({
        "role": "employee",
        "$or": [{"manager_id": None}, {"manager_id": ""}]
    }).sort("name", 1)
    employees = await cursor.to_list(length=100)
    return [
        UserResponse(
            id=str(e["_id"]),
            email=e["email"],
            name=e["name"],
            role=e["role"],
            department=e.get("department"),
            manager_id=e.get("manager_id"),
            created_at=e.get("created_at")
        )
        for e in employees
    ]

@router.post("/employees/{employee_id}/unassign")
async def unassign_employee(
    employee_id: str,
    current_user: dict = Depends(require_manager)
):
    """
    Manager unassigns an employee from their team roster (e.g. if mistakenly selected during signup).
    """
    db = get_database()
    try:
        emp_oid = ObjectId(employee_id)
    except Exception:
        emp_oid = employee_id

    emp = await db.users.find_one({"_id": emp_oid, "role": "employee", "manager_id": current_user["id"]})
    if not emp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found or is not assigned to you."
        )

    await db.users.update_one(
        {"_id": emp_oid},
        {"$set": {"manager_id": None}}
    )

    # Also update any draft reports to clear manager
    await db.weekly_reports.update_many(
        {"user_id": str(emp_oid), "status": "draft"},
        {"$set": {"manager_id": None, "manager_name": None}}
    )

    return {"status": "success", "message": f"Employee {emp['name']} unassigned successfully."}

@router.post("/employees/{employee_id}/assign")
async def assign_employee(
    employee_id: str,
    current_user: dict = Depends(require_manager)
):
    """
    Manager claims / assigns an employee to their team.
    Enforces authorization in the database update itself:
    - An employee can only be assigned if unassigned (manager_id is None, "", or missing),
      or already assigned to this manager.
    - If already assigned to another manager, returns 409 Conflict.
    """
    db = get_database()
    try:
        emp_oid = ObjectId(employee_id)
    except Exception:
        emp_oid = employee_id

    # Atomic conditional update enforcing assignment eligibility
    updated_emp = await db.users.find_one_and_update(
        {
            "_id": emp_oid,
            "role": "employee",
            "$or": [
                {"manager_id": None},
                {"manager_id": ""},
                {"manager_id": current_user["id"]},
                {"manager_id": {"$exists": False}}
            ]
        },
        {"$set": {"manager_id": current_user["id"]}},
        return_document=True
    )

    if not updated_emp:
        # Check if employee exists vs already assigned to another manager
        existing_emp = await db.users.find_one({"_id": emp_oid, "role": "employee"})
        if not existing_emp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Employee not found."
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Employee is already assigned to another manager. They must be unassigned before reassignment."
        )

    # Update draft reports with assigned manager
    await db.weekly_reports.update_many(
        {"user_id": str(emp_oid), "status": "draft"},
        {"$set": {"manager_id": current_user["id"], "manager_name": current_user["name"]}}
    )

    return {"status": "success", "message": f"Employee {updated_emp['name']} assigned to {current_user['name']}."}
