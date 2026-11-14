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
