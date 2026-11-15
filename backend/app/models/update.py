import re
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime

def validate_iso_date(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
        raise ValueError("Date must be in YYYY-MM-DD format")
    try:
        datetime.strptime(v, "%Y-%m-%d")
    except ValueError:
        raise ValueError("Invalid calendar date")
    return v

class WorkUpdateBase(BaseModel):
    date: str = Field(..., description="Date of the update (YYYY-MM-DD)")
    title: str = Field(..., min_length=2, max_length=150, description="Brief summary of work done")
    description: str = Field(..., min_length=5, description="Detailed description of tasks completed")
    category: Optional[str] = Field("Feature", description="Category: Feature, Bug Fix, Code Review, Meeting, DevOps, etc.")
    hours_spent: Optional[float] = Field(None, gt=0, le=24, description="Hours spent on this task (must be positive and <= 24)")

    @field_validator("date")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        return validate_iso_date(v)

class WorkUpdateCreate(WorkUpdateBase):
    pass

class WorkUpdateEdit(BaseModel):
    date: Optional[str] = None
    title: Optional[str] = Field(None, min_length=2, max_length=150)
    description: Optional[str] = Field(None, min_length=5)
    category: Optional[str] = None
    hours_spent: Optional[float] = Field(None, gt=0, le=24)

    @field_validator("date")
    @classmethod
    def validate_edit_date_format(cls, v: Optional[str]) -> Optional[str]:
        return validate_iso_date(v)

class WorkUpdateResponse(WorkUpdateBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
