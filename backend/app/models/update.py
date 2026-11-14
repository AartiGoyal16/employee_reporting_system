from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class WorkUpdateBase(BaseModel):
    date: str = Field(..., description="Date of the update (YYYY-MM-DD)")
    title: str = Field(..., min_length=2, max_length=150, description="Brief summary of work done")
    description: str = Field(..., min_length=5, description="Detailed description of tasks completed")
    category: Optional[str] = Field("Feature", description="Category: Feature, Bug Fix, Code Review, Meeting, DevOps, etc.")
    hours_spent: Optional[float] = Field(None, ge=0, le=24, description="Hours spent on this task")

class WorkUpdateCreate(WorkUpdateBase):
    pass

class WorkUpdateEdit(BaseModel):
    date: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    hours_spent: Optional[float] = None

class WorkUpdateResponse(WorkUpdateBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
