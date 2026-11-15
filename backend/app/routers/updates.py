from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional
from datetime import datetime, timedelta
from bson import ObjectId
from app.database import get_database
from app.models.update import WorkUpdateCreate, WorkUpdateEdit, WorkUpdateResponse
from app.auth.dependencies import require_employee

import uuid

router = APIRouter(prefix="/updates", tags=["Work Updates"])

def get_week_boundaries_for_date(date_str: str) -> tuple[str, str]:
    """Computes Monday and Sunday calendar dates for any given YYYY-MM-DD date."""
    dt = datetime.strptime(date_str, "%Y-%m-%d").date()
    monday = dt - timedelta(days=dt.weekday())
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")

async def acquire_draft_report_lease(
    db,
    user_id: str,
    user_dict: dict,
    week_start: str,
    week_end: str,
    add_update_id: Optional[str] = None,
    remove_update_id: Optional[str] = None
) -> tuple[bool, str, Optional[str]]:
    """
    Ownership-aware atomic coordination strategy:
    Acquires an atomic mutation lease on the weekly report document guaranteeing it is in 'draft' status.
    Generates a unique lease_token recorded in active_leases.
    Returns (allowed, status, lease_token).
    """
    lease_token = str(uuid.uuid4())
    now = datetime.utcnow()
    update_ops = {
        "$inc": {"mutation_sequence": 1},
        "$addToSet": {"active_leases": lease_token},
        "$set": {"updated_at": now}
    }
    if add_update_id:
        update_ops["$addToSet"]["work_update_ids"] = add_update_id
    if remove_update_id:
        update_ops["$pull"] = {"work_update_ids": remove_update_id}

    # 1. Atomic lease on existing draft report
    lease = await db.weekly_reports.find_one_and_update(
        {
            "user_id": user_id,
            "week_start_date": week_start,
            "week_end_date": week_end,
            "status": "draft"
        },
        update_ops,
        return_document=True
    )
    if lease:
        return True, "draft", lease_token

    # 2. Check if report already exists in non-draft status
    existing = await db.weekly_reports.find_one({
        "user_id": user_id,
        "week_start_date": week_start,
        "week_end_date": week_end
    })
    if existing:
        return False, existing.get("status", "locked"), None

    # 3. Report doc does not exist yet -> create draft with lease
    manager_name = None
    if user_dict.get("manager_id"):
        try:
            m_oid = ObjectId(user_dict["manager_id"])
        except Exception:
            m_oid = user_dict["manager_id"]
        mgr = await db.users.find_one({"_id": m_oid})
        if mgr:
            manager_name = mgr.get("name")

    initial_ids = [add_update_id] if add_update_id else []
    try:
        await db.weekly_reports.insert_one({
            "_id": ObjectId(),
            "user_id": user_id,
            "user_name": user_dict.get("name"),
            "user_email": user_dict.get("email"),
            "manager_id": user_dict.get("manager_id"),
            "manager_name": manager_name,
            "week_start_date": week_start,
            "week_end_date": week_end,
            "work_update_ids": initial_ids,
            "answers": [],
            "status": "draft",
            "submitted_at": None,
            "ai_summary": None,
            "mutation_sequence": 1,
            "active_leases": [lease_token],
            "created_at": now,
            "updated_at": now
        })
        return True, "draft", lease_token
    except Exception:
        # Concurrent insert race: re-check
        existing = await db.weekly_reports.find_one({
            "user_id": user_id,
            "week_start_date": week_start,
            "week_end_date": week_end
        })
        if existing and existing.get("status") in ["submitting", "submitted"]:
            return False, existing.get("status"), None
        lease = await db.weekly_reports.find_one_and_update(
            {
                "user_id": user_id,
                "week_start_date": week_start,
                "week_end_date": week_end,
                "status": "draft"
            },
            update_ops,
            return_document=True
        )
        return (True, "draft", lease_token) if lease else (False, "locked", None)

async def release_draft_report_lease(
    db,
    user_id: str,
    week_start: str,
    week_end: str,
    lease_token: Optional[str] = None,
    rollback_add_id: Optional[str] = None,
    rollback_remove_id: Optional[str] = None
):
    """
    Releases this specific operation's lease token and safely rolls back changes if requested.
    Only releases if the lease_token is present in active_leases on the draft report.
    Never modifies a submitted report or another operation's state.
    """
    if not lease_token:
        return

    pull_ops = {"active_leases": lease_token}
    if rollback_add_id:
        pull_ops["work_update_ids"] = rollback_add_id

    ops = {
        "$pull": pull_ops,
        "$set": {"updated_at": datetime.utcnow()}
    }
    if rollback_remove_id:
        ops["$addToSet"] = {"work_update_ids": rollback_remove_id}

    await db.weekly_reports.update_one(
        {
            "user_id": user_id,
            "week_start_date": week_start,
            "week_end_date": week_end,
            "status": {"$in": ["draft", "submitting"]},
            "active_leases": lease_token
        },
        ops
    )

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
    """Create a new daily work update with atomic weekly report lease coordination."""
    db = get_database()
    week_start, week_end = get_week_boundaries_for_date(update_data.date)
    new_oid = ObjectId()
    now = datetime.utcnow()

    # Atomically acquire lease on the weekly report guaranteeing draft status
    allowed, report_status, lease_token = await acquire_draft_report_lease(
        db, current_user["id"], current_user, week_start, week_end, add_update_id=str(new_oid)
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot add work update for {update_data.date}: weekly report for {week_start} to {week_end} is {report_status} and cannot be modified."
        )

    doc = {
        "_id": new_oid,
        "user_id": current_user["id"],
        "date": update_data.date,
        "title": update_data.title,
        "description": update_data.description,
        "category": update_data.category or "Feature",
        "hours_spent": update_data.hours_spent,
        "created_at": now,
        "updated_at": now
    }
    mutation_succeeded = False
    try:
        await db.work_updates.insert_one(doc)
        mutation_succeeded = True
    except Exception as exc:
        await release_draft_report_lease(
            db, current_user["id"], week_start, week_end, lease_token=lease_token, rollback_add_id=str(new_oid)
        )
        raise exc
    finally:
        if mutation_succeeded:
            await release_draft_report_lease(db, current_user["id"], week_start, week_end, lease_token=lease_token)

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
    """Edit an existing daily work update with atomic weekly report coordination."""
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

    lease_new = None
    lease_old = None
    mutation_succeeded = False

    if update_data.date and update_data.date != doc["date"]:
        old_start, old_end = get_week_boundaries_for_date(doc["date"])
        new_start, new_end = get_week_boundaries_for_date(update_data.date)

        # 1. Lease target week first
        allowed_new, st_new, lease_new = await acquire_draft_report_lease(
            db, current_user["id"], current_user, new_start, new_end, add_update_id=str(oid)
        )
        if not allowed_new:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot move work update to {update_data.date}: that week's report is {st_new} and cannot be modified."
            )

        # 2. Lease source week
        allowed_old, st_old, lease_old = await acquire_draft_report_lease(
            db, current_user["id"], current_user, old_start, old_end, remove_update_id=str(oid)
        )
        if not allowed_old:
            # Revert target week lease and addition cleanly
            await release_draft_report_lease(
                db, current_user["id"], new_start, new_end, lease_token=lease_new, rollback_add_id=str(oid)
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot move work update from {doc['date']}: source weekly report is {st_old} and cannot be modified."
            )
    else:
        week_start, week_end = get_week_boundaries_for_date(doc["date"])
        allowed, report_status, lease_new = await acquire_draft_report_lease(
            db, current_user["id"], current_user, week_start, week_end
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot edit work update: the weekly report for {week_start} to {week_end} is {report_status} and cannot be modified."
            )

    set_fields = {k: v for k, v in update_data.dict().items() if v is not None}
    set_fields["updated_at"] = datetime.utcnow()

    try:
        if update_data.date and update_data.date != doc["date"]:
            res = await db.work_updates.update_one(
                {"_id": oid, "date": doc["date"]},
                {"$set": set_fields}
            )
            if getattr(res, "matched_count", 0) == 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Work update was concurrently modified or moved."
                )
        else:
            await db.work_updates.update_one({"_id": oid}, {"$set": set_fields})
        mutation_succeeded = True
    except Exception as exc:
        if update_data.date and update_data.date != doc["date"]:
            await release_draft_report_lease(
                db, current_user["id"], new_start, new_end, lease_token=lease_new, rollback_add_id=str(oid)
            )
            await release_draft_report_lease(
                db, current_user["id"], old_start, old_end, lease_token=lease_old, rollback_remove_id=str(oid)
            )
        else:
            await release_draft_report_lease(
                db, current_user["id"], week_start, week_end, lease_token=lease_new
            )
        raise exc
    finally:
        if mutation_succeeded:
            if update_data.date and update_data.date != doc["date"]:
                await release_draft_report_lease(db, current_user["id"], new_start, new_end, lease_token=lease_new)
                await release_draft_report_lease(db, current_user["id"], old_start, old_end, lease_token=lease_old)
            else:
                await release_draft_report_lease(db, current_user["id"], week_start, week_end, lease_token=lease_new)

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
    """Delete a daily work update with atomic weekly report coordination."""
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

    week_start, week_end = get_week_boundaries_for_date(doc["date"])
    allowed, report_status, lease_token = await acquire_draft_report_lease(
        db, current_user["id"], current_user, week_start, week_end, remove_update_id=str(oid)
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete work update: the weekly report for {week_start} to {week_end} is {report_status} and cannot be modified."
        )

    mutation_succeeded = False
    try:
        await db.work_updates.delete_one({"_id": oid})
        mutation_succeeded = True
    except Exception as exc:
        await release_draft_report_lease(
            db, current_user["id"], week_start, week_end, lease_token=lease_token, rollback_remove_id=str(oid)
        )
        raise exc
    finally:
        if mutation_succeeded:
            await release_draft_report_lease(db, current_user["id"], week_start, week_end, lease_token=lease_token)

    return None
