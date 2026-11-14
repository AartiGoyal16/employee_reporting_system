from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from bson import ObjectId
from app.database import get_database
from app.models.question import QuestionResponse, QuestionCreate, QuestionUpdate
from app.auth.dependencies import get_current_user, require_manager

router = APIRouter(prefix="/questions", tags=["Questions"])

@router.get("", response_model=List[QuestionResponse])
async def get_questions(current_user: dict = Depends(get_current_user)):
    """Retrieve all active weekly reporting questions, sorted by order."""
    db = get_database()
    cursor = db.questions.find({"is_active": True}).sort("order", 1)
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
    existing = await db.questions.find_one({"key": question.key})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Question with key '{question.key}' already exists."
        )
    
    doc = question.dict()
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
