from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, Literal
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr
    name: str
    role: str = Field(..., description="Role: 'employee' or 'manager'")
    department: Optional[str] = "Engineering"
    manager_id: Optional[str] = Field(None, description="Manager ID if user is an employee")

class UserCreate(UserBase):
    password: str

class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Full name")
    email: EmailStr
    password: str = Field(..., min_length=6, description="Password (min 6 characters)")
    role: Optional[str] = Field("employee", description="Role (public registration is restricted to 'employee')")
    department: Optional[str] = Field("Engineering", description="Department / team name")
    manager_id: Optional[str] = Field(None, description="Manager's user ID (optional: select assigned manager)")

    @field_validator('role')
    @classmethod
    def validate_role_is_employee(cls, v):
        if v and v.strip().lower() != "employee":
            raise ValueError("Public registration is restricted to 'employee' role only. Manager accounts must be provisioned administratively.")
        return "employee"

    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v):
        if len(v) < 6:
            raise ValueError('Password must be at least 6 characters long')
        return v

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('Name cannot be empty')
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    email: EmailStr
    name: str
    role: str
    department: Optional[str] = None
    manager_id: Optional[str] = None
    created_at: Optional[datetime] = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
