from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.models.update import WorkUpdateResponse

class QuestionAnswer(BaseModel):
    question_key: str = Field(..., description="Key of question e.g. accomplishments")
    question_text: str = Field(..., description="The prompt question text")
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
