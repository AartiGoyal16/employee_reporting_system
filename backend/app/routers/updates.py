from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional
from datetime import datetime
from bson import ObjectId
from app.database import get_database
from app.models.update import WorkUpdateCreate, WorkUpdateEdit, WorkUpdateResponse
from app.auth.dependencies import require_employee

router = APIRouter(prefix="/updates", tags=["Work Updates"])

@router.get("", response_model=List[WorkUpdateResponse])
async def get_my_work_updates(
    start_date: Optional[str] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    current_user: dict = Depends(require_employee)
):
    """
    Employees can access only their own daily work updates.
    Optionally filter by date range.
    """
    db = get_database()
    query = {"user_id": current_user["id"]}

    if start_date and end_date:
        query["date"] = {"$gte": start_date, "$lte": end_date}
    elif start_date:
        query["date"] = {"$gte": start_date}
    elif end_date:
        query["date"] = {"$lte": end_date}

    cursor = db.work_updates.find(query).sort("date", -1)
    updates = await cursor.to_list(length=200)

    results = []
    for u in updates:
        results.append(WorkUpdateResponse(
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
    return results

@router.post("", response_model=WorkUpdateResponse, status_code=status.HTTP_201_CREATED)
async def create_work_update(
    update_data: WorkUpdateCreate,
    current_user: dict = Depends(require_employee)
):
    """Create a new daily work update."""
    db = get_database()

    # Integrity check: prevent logging updates for weeks whose reports are submitting or already submitted
    submitted_report = await db.weekly_reports.find_one({
        "user_id": current_user["id"],
        "status": {"$in": ["submitting", "submitted"]},
        "week_start_date": {"$lte": update_data.date},
        "week_end_date": {"$gte": update_data.date}
    })
    if submitted_report:
        report_status = submitted_report.get("status", "submitted")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot add work update for {update_data.date}: weekly report for {submitted_report['week_start_date']} to {submitted_report['week_end_date']} is {report_status} and cannot be modified."
        )

    now = datetime.utcnow()
    doc = {
        "_id": ObjectId(),
        "user_id": current_user["id"],
        "date": update_data.date,
        "title": update_data.title,
        "description": update_data.description,
        "category": update_data.category or "Feature",
        "hours_spent": update_data.hours_spent,
        "created_at": now,
        "updated_at": now
    }
    await db.work_updates.insert_one(doc)

    # Double-check race condition: ensure report was not locked to submitting/submitted during insert
    race_check = await db.weekly_reports.find_one({
        "user_id": current_user["id"],
        "status": {"$in": ["submitting", "submitted"]},
        "week_start_date": {"$lte": update_data.date},
        "week_end_date": {"$gte": update_data.date}
    })
    if race_check:
        await db.work_updates.delete_one({"_id": doc["_id"]})
        report_status = race_check.get("status", "submitted")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot add work update for {update_data.date}: weekly report is {report_status} and cannot be modified."
        )

    return WorkUpdateResponse(
        id=str(doc["_id"]),
        user_id=doc["user_id"],
        date=doc["date"],
        title=doc["title"],
        description=doc["description"],
        category=doc["category"],
        hours_spent=doc["hours_spent"],
        created_at=doc["created_at"],
        updated_at=doc["updated_at"]
    )

@router.get("/{update_id}", response_model=WorkUpdateResponse)
async def get_work_update(
    update_id: str,
    current_user: dict = Depends(require_employee)
):
    """Retrieve a single work update, enforcing that employees access only their own data."""
    db = get_database()
    try:
        oid = ObjectId(update_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid update ID format")

    doc = await db.work_updates.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Work update not found")

    if doc["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden: You cannot access work updates of other employees")

    return WorkUpdateResponse(
        id=str(doc["_id"]),
        user_id=doc["user_id"],
        date=doc["date"],
        title=doc["title"],
        description=doc["description"],
        category=doc.get("category", "Feature"),
        hours_spent=doc.get("hours_spent"),
        created_at=doc.get("created_at", datetime.utcnow()),
        updated_at=doc.get("updated_at", datetime.utcnow())
    )

@router.put("/{update_id}", response_model=WorkUpdateResponse)
async def edit_work_update(
    update_id: str,
    update_data: WorkUpdateEdit,
    current_user: dict = Depends(require_employee)
):
    """Edit an existing daily work update."""
    db = get_database()
    try:
        oid = ObjectId(update_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid update ID format")

    doc = await db.work_updates.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Work update not found")

    if doc["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden: You can only edit your own work updates")

    # Integrity check: prevent editing updates that are part of a submitting or submitted weekly report
    submitted_report = await db.weekly_reports.find_one({
        "user_id": current_user["id"],
        "status": {"$in": ["submitting", "submitted"]},
        "week_start_date": {"$lte": doc["date"]},
        "week_end_date": {"$gte": doc["date"]}
    })
    if submitted_report:
        report_status = submitted_report.get("status", "submitted")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot edit work update: the weekly report for {submitted_report['week_start_date']} to {submitted_report['week_end_date']} is {report_status} and cannot be modified."
        )

    # Check target date if date is being modified
    if update_data.date and update_data.date != doc["date"]:
        submitted_target = await db.weekly_reports.find_one({
            "user_id": current_user["id"],
            "status": {"$in": ["submitting", "submitted"]},
            "week_start_date": {"$lte": update_data.date},
            "week_end_date": {"$gte": update_data.date}
        })
        if submitted_target:
            report_status = submitted_target.get("status", "submitted")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot move work update to {update_data.date}: that week's report is {report_status} and cannot be modified."
            )

    set_fields = {k: v for k, v in update_data.dict().items() if v is not None}
    set_fields["updated_at"] = datetime.utcnow()

    await db.work_updates.update_one({"_id": oid}, {"$set": set_fields})

    # Double-check race condition: ensure report was not locked to submitting/submitted during edit
    race_check = await db.weekly_reports.find_one({
        "user_id": current_user["id"],
        "status": {"$in": ["submitting", "submitted"]},
        "week_start_date": {"$lte": set_fields.get("date", doc["date"])},
        "week_end_date": {"$gte": set_fields.get("date", doc["date"])}
    })
    if race_check:
        # Roll back edit
        revert_fields = {k: doc.get(k) for k in set_fields.keys()}
        await db.work_updates.update_one({"_id": oid}, {"$set": revert_fields})
        report_status = race_check.get("status", "submitted")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot edit work update: the weekly report is {report_status} and cannot be modified."
        )
    updated_doc = await db.work_updates.find_one({"_id": oid})

    return WorkUpdateResponse(
        id=str(updated_doc["_id"]),
        user_id=updated_doc["user_id"],
        date=updated_doc["date"],
        title=updated_doc["title"],
        description=updated_doc["description"],
        category=updated_doc.get("category", "Feature"),
        hours_spent=updated_doc.get("hours_spent"),
        created_at=updated_doc.get("created_at"),
        updated_at=updated_doc.get("updated_at")
    )

@router.delete("/{update_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_work_update(
    update_id: str,
    current_user: dict = Depends(require_employee)
):
    """Delete a daily work update."""
    db = get_database()
    try:
        oid = ObjectId(update_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid update ID format")

    doc = await db.work_updates.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Work update not found")

    if doc["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden: You can only delete your own work updates")

    # Integrity check: prevent deleting updates that are part of a submitting or submitted weekly report
    submitted_report = await db.weekly_reports.find_one({
        "user_id": current_user["id"],
        "status": {"$in": ["submitting", "submitted"]},
        "week_start_date": {"$lte": doc["date"]},
        "week_end_date": {"$gte": doc["date"]}
    })
    if submitted_report:
        report_status = submitted_report.get("status", "submitted")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete work update: the weekly report for {submitted_report['week_start_date']} to {submitted_report['week_end_date']} is {report_status} and cannot be modified."
        )

    await db.work_updates.delete_one({"_id": oid})
    return None
