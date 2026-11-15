from fastapi import APIRouter, HTTPException, status, Depends
from datetime import datetime
from bson import ObjectId
from app.database import get_database
from app.config import settings
from app.models.user import UserLogin, TokenResponse, UserResponse, RegisterRequest
from app.auth.security import verify_password, get_password_hash
from app.auth.jwt import create_access_token
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest):
    """
    Register a new employee or manager account.
    - Validates unique email (409 Conflict if already registered).
    - Hashes password with bcrypt.
    - Employees may optionally associate with a manager via manager_id.
    - Returns JWT token + user profile immediately so the client can log in directly.
    """
    db = get_database()
    email_clean = payload.email.strip().lower()

    # 1. Duplicate email check
    existing = await db.users.find_one({"email": email_clean})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists. Please log in instead."
        )

    # 2. Registration Authorization:
    # Public registrants cannot assign themselves to an arbitrary manager.
    # New employees must register without a manager and be claimed/assigned by their manager.
    if payload.manager_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Direct manager assignment during public registration is not permitted. New employees are registered unassigned and must be assigned by their manager."
        )
    resolved_manager_id = None

    # 3. Security: Public registration ALWAYS creates employee role
    account_role = "employee"
    new_id = ObjectId()
    now = datetime.utcnow()
    user_doc = {
        "_id": new_id,
        "email": email_clean,
        "name": payload.name.strip(),
        "hashed_password": get_password_hash(payload.password),
        "role": account_role,
        "department": payload.department or "Engineering",
        "manager_id": resolved_manager_id,
        "created_at": now,
    }
    await db.users.insert_one(user_doc)

    # 4. Issue JWT and return TokenResponse (auto-login after signup)
    user_id_str = str(new_id)
    token = create_access_token(data={
        "sub": user_id_str,
        "email": email_clean,
        "role": account_role,
        "name": payload.name.strip()
    })

    user_resp = UserResponse(
        id=user_id_str,
        email=email_clean,
        name=payload.name.strip(),
        role=account_role,
        department=payload.department or "Engineering",
        manager_id=resolved_manager_id,
        created_at=now
    )
    return TokenResponse(access_token=token, token_type="bearer", user=user_resp)

@router.get("/managers", response_model=list)
async def get_managers_list():
    """
    Public endpoint: Returns all manager accounts so the signup form can
    populate the 'Report To' dropdown for new employee accounts.
    """
    db = get_database()
    cursor = db.users.find({"role": "manager"}).sort("name", 1)
    managers = await cursor.to_list(length=100)
    return [
        {"id": str(m["_id"]), "name": m["name"], "department": m.get("department", "")}
        for m in managers
    ]


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
    """Returns sample pre-seeded users for demo testing in development environments only."""
    if not settings.ENABLE_DEMO_USERS or settings.ENVIRONMENT.lower() == "production":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demo users endpoint is disabled in production."
        )
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
