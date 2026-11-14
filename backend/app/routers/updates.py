from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional
from datetime import datetime
from bson import ObjectId
from app.database import get_database
from app.models.update import WorkUpdateCreate, WorkUpdateEdit, WorkUpdateResponse
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/updates", tags=["Work Updates"])

@router.get("", response_model=List[WorkUpdateResponse])
async def get_my_work_updates(
    start_date: Optional[str] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    current_user: dict = Depends(get_current_user)
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
    current_user: dict = Depends(get_current_user)
):
    """Create a new daily work update."""
    db = get_database()
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
    current_user: dict = Depends(get_current_user)
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
    current_user: dict = Depends(get_current_user)
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

    set_fields = {k: v for k, v in update_data.dict().items() if v is not None}
    set_fields["updated_at"] = datetime.utcnow()

    await db.work_updates.update_one({"_id": oid}, {"$set": set_fields})
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
    current_user: dict = Depends(get_current_user)
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

    await db.work_updates.delete_one({"_id": oid})
    return None
