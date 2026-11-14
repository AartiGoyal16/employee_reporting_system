from fastapi import APIRouter, HTTPException, status, Depends
from datetime import datetime
from bson import ObjectId
from app.database import get_database
from app.models.user import UserLogin, TokenResponse, UserResponse
from app.auth.security import verify_password
from app.auth.jwt import create_access_token
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin):
    db = get_database()
    email_clean = credentials.email.strip().lower()
    user = await db.users.find_one({"email": email_clean})

    if not user or not verify_password(credentials.password, user.get("hashed_password", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_str = str(user["_id"])
    token = create_access_token(data={
        "sub": user_id_str,
        "email": user["email"],
        "role": user["role"],
        "name": user["name"]
    })

    user_resp = UserResponse(
        id=user_id_str,
        email=user["email"],
        name=user["name"],
        role=user["role"],
        department=user.get("department"),
        manager_id=user.get("manager_id"),
        created_at=user.get("created_at")
    )

    return TokenResponse(access_token=token, token_type="bearer", user=user_resp)

@router.get("/me", response_model=UserResponse)
async def get_my_profile(current_user: dict = Depends(get_current_user)):
    return UserResponse(
        id=current_user["id"],
        email=current_user["email"],
        name=current_user["name"],
        role=current_user["role"],
        department=current_user.get("department"),
        manager_id=current_user.get("manager_id"),
        created_at=current_user.get("created_at")
    )

@router.get("/demo-users")
async def get_demo_users():
    """Returns sample pre-seeded users for demo testing."""
    return [
        {
            "role": "manager",
            "name": "Sarah Chen",
            "email": "manager@company.com",
            "password": "Manager@123",
            "description": "Engineering Manager (Manages Alex & Priya)"
        },
        {
            "role": "employee",
            "name": "Alex Rivera",
            "email": "alex@company.com",
            "password": "Employee@123",
            "description": "Senior Software Engineer (Reports to Sarah)"
        },
        {
            "role": "employee",
            "name": "Priya Patel",
            "email": "priya@company.com",
            "password": "Employee@123",
            "description": "Frontend Engineer (Reports to Sarah)"
        },
        {
            "role": "manager",
            "name": "David Miller",
            "email": "david.manager@company.com",
            "password": "Manager@123",
            "description": "Product Manager (Manages Marcus)"
        },
        {
            "role": "employee",
            "name": "Marcus Johnson",
            "email": "marcus@company.com",
            "password": "Employee@123",
            "description": "UI/UX Designer (Reports to David)"
        }
    ]
