from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional
from bson import ObjectId
from app.database import get_database
from app.models.question import QuestionResponse, QuestionCreate, QuestionUpdate
from app.auth.dependencies import get_current_user, require_manager

router = APIRouter(prefix="/questions", tags=["Questions"])

@router.get("", response_model=List[QuestionResponse])
async def get_questions(
    include_inactive: bool = Query(False, description="Include inactive questions (for manager configuration)"),
    current_user: dict = Depends(get_current_user)
):
    """Retrieve weekly reporting questions, sorted by order."""
    db = get_database()
    query = {} if include_inactive else {"is_active": True}
    cursor = db.questions.find(query).sort("order", 1)
    questions = await cursor.to_list(length=100)
    
    results = []
    for q in questions:
        results.append(QuestionResponse(
            id=str(q["_id"]),
            key=q["key"],
            question_text=q["question_text"],
            order=q.get("order", 0),
            is_active=q.get("is_active", True)
        ))
    return results

@router.post("", response_model=QuestionResponse)
async def create_question(question: QuestionCreate, current_user: dict = Depends(require_manager)):
    """Allow managers/admins to add custom weekly questions (Bonus requirement)."""
    db = get_database()
    # Check if key exists
    clean_key = question.key.strip().lower().replace(" ", "_")
    existing = await db.questions.find_one({"key": clean_key})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Question with key '{clean_key}' already exists."
        )
    
    doc = question.dict()
    doc["key"] = clean_key
    res = await db.questions.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    return QuestionResponse(**doc)

@router.put("/{question_id}", response_model=QuestionResponse)
async def update_question(
    question_id: str,
    update_data: QuestionUpdate,
    current_user: dict = Depends(require_manager)
):
    """Allow managers to edit questions (Bonus requirement)."""
    db = get_database()
    try:
        q_oid = ObjectId(question_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid question ID format")

    update_dict = {k: v for k, v in update_data.dict().items() if v is not None}
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    result = await db.questions.update_one({"_id": q_oid}, {"$set": update_dict})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Question not found")

    updated = await db.questions.find_one({"_id": q_oid})
    return QuestionResponse(
        id=str(updated["_id"]),
        key=updated["key"],
        question_text=updated["question_text"],
        order=updated.get("order", 0),
        is_active=updated.get("is_active", True)
    )

@router.patch("/{question_id}/toggle", response_model=QuestionResponse)
async def toggle_question_active(
    question_id: str,
    current_user: dict = Depends(require_manager)
):
    """Toggle a question's active/inactive status."""
    db = get_database()
    try:
        q_oid = ObjectId(question_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid question ID format")

    question = await db.questions.find_one({"_id": q_oid})
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    new_status = not question.get("is_active", True)
    await db.questions.update_one({"_id": q_oid}, {"$set": {"is_active": new_status}})
    updated = await db.questions.find_one({"_id": q_oid})
    return QuestionResponse(
        id=str(updated["_id"]),
        key=updated["key"],
        question_text=updated["question_text"],
        order=updated.get("order", 0),
        is_active=updated.get("is_active", True)
    )

@router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(
    question_id: str,
    current_user: dict = Depends(require_manager)
):
    """Delete a question from the weekly template."""
    db = get_database()
    try:
        q_oid = ObjectId(question_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid question ID format")

    res = await db.questions.delete_one({"_id": q_oid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Question not found")
    return None
