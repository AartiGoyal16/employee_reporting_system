from pydantic import BaseModel, Field
from typing import Optional

class QuestionBase(BaseModel):
    key: str = Field(..., description="Unique key for question e.g. accomplishments, in_progress, blockers, priorities")
    question_text: str = Field(..., description="Prompt text for the question")
    order: int = Field(0, description="Display order")
    is_active: bool = True

class QuestionCreate(QuestionBase):
    pass

class QuestionUpdate(BaseModel):
    question_text: Optional[str] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None

class QuestionResponse(QuestionBase):
    id: str
