import re
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.models.update import WorkUpdateResponse

def validate_iso_date(v: str) -> str:
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
        raise ValueError("Date must be in YYYY-MM-DD format")
    try:
        datetime.strptime(v, "%Y-%m-%d")
    except ValueError:
        raise ValueError("Invalid calendar date")
    return v

class QuestionAnswer(BaseModel):
    question_key: str = Field(..., min_length=1, description="Key of question e.g. accomplishments")
    question_text: str = Field(..., min_length=1, description="The prompt question text")
    answer: str = Field("", description="Employee's answer to the question")

class AISummary(BaseModel):
    executive_summary: str = Field(..., description="High-level overview of employee weekly performance")
    key_highlights: List[str] = Field(default_factory=list, description="Top achievements and completed milestones")
    blockers_identified: List[str] = Field(default_factory=list, description="Challenges or bottlenecks requiring attention")
    manager_recommendation: str = Field(..., description="Actionable advice for the manager")
    model_used: str = Field("Google Gemini / Heuristic Engine", description="AI Model provider used")
    generated_at: datetime = Field(default_factory=datetime.utcnow)

class WeeklyReportCreateOrSave(BaseModel):
    week_start_date: str = Field(..., description="Start date of week YYYY-MM-DD")
    week_end_date: str = Field(..., description="End date of week YYYY-MM-DD")
    answers: List[QuestionAnswer] = Field(default_factory=list)
    work_update_ids: Optional[List[str]] = Field(default_factory=list)

    @field_validator("week_start_date", "week_end_date")
    @classmethod
    def validate_dates(cls, v: str) -> str:
        return validate_iso_date(v)

    @model_validator(mode="after")
    def validate_range(self):
        try:
            start = datetime.strptime(self.week_start_date, "%Y-%m-%d")
            end = datetime.strptime(self.week_end_date, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Dates must be valid YYYY-MM-DD calendar dates")

        if start > end:
            raise ValueError("week_start_date cannot be after week_end_date")

        # Validate legitimate Monday-to-Sunday week
        if start.weekday() != 0:
            raise ValueError(f"week_start_date ({self.week_start_date}) must be a Monday")
        if end.weekday() != 6:
            raise ValueError(f"week_end_date ({self.week_end_date}) must be a Sunday")
        if (end - start).days != 6:
            raise ValueError("Weekly report period must span exactly 7 days from Monday to Sunday")

        return self

class WeeklyReportSubmit(BaseModel):
    # Optional last updates before submission
    answers: Optional[List[QuestionAnswer]] = None

class WeeklyReportResponse(BaseModel):
    id: str
    user_id: str
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    manager_id: Optional[str] = None
    manager_name: Optional[str] = None
    week_start_date: str
    week_end_date: str
    answers: List[QuestionAnswer]
    work_updates: Optional[List[WorkUpdateResponse]] = []
    status: str = Field(..., description="'draft' or 'submitted'")
    submitted_at: Optional[datetime] = None
    ai_summary: Optional[AISummary] = None
    created_at: datetime
    updated_at: datetime
