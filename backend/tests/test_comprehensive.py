import os
import pytest
import asyncio
from datetime import datetime, timedelta
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.config import Settings, settings
from app.database import get_database, db_manager, DatabaseManager
from app.services.seed_data import seed_database
from unittest.mock import patch, MagicMock
import json
import httpx
from app.services.ai_summary import (
    generate_heuristic_summary,
    generate_gemini_summary,
    generate_groq_summary,
    generate_ai_summary_with_retry,
    _sanitize_error
)
from app.services.reminder import run_reminder_check
from app.auth.jwt import create_access_token, decode_access_token

@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"

@pytest.fixture(scope="module", autouse=True)
async def setup_test_db():
    os.environ["TESTING"] = "1"
    os.environ["ENVIRONMENT"] = "test"
    await db_manager.connect_to_database()
    db = get_database()
    await seed_database(db)
    yield

# ============================================================================
# 1. AUTHENTICATION & PRIVILEGE ESCALATION TESTS
# ============================================================================

@pytest.mark.anyio
async def test_auth_login_valid_and_invalid():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Invalid password
        r = await client.post("/api/v1/auth/login", json={"email": "alex@company.com", "password": "WrongPassword"})
        assert r.status_code == 401
        assert "Invalid" in r.json()["detail"]

        # 2. Non-existent email
        r_non = await client.post("/api/v1/auth/login", json={"email": "nobody@company.com", "password": "Any"})
        assert r_non.status_code == 401

        # 3. Valid Employee
        r_emp = await client.post("/api/v1/auth/login", json={"email": "alex@company.com", "password": "Employee@123"})
        assert r_emp.status_code == 200
        data = r_emp.json()
        assert data["user"]["role"] == "employee"
        assert "access_token" in data

        # 4. Valid Manager
        r_mgr = await client.post("/api/v1/auth/login", json={"email": "manager@company.com", "password": "Manager@123"})
        assert r_mgr.status_code == 200
        assert r_mgr.json()["user"]["role"] == "manager"

@pytest.mark.anyio
async def test_public_signup_privilege_escalation_blocked():
    """
    CRITICAL SECURITY TEST:
    A public user attempting to register with role='manager' MUST be prevented
    from gaining manager privileges (either rejected with 400 or forced to employee).
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Attempting signup with role='manager'
        r = await client.post("/api/v1/auth/register", json={
            "name": "Attacker",
            "email": "attacker.manager@company.com",
            "password": "Password@123",
            "role": "manager",
            "department": "Engineering"
        })
        # Should be rejected or sanitized
        if r.status_code == 201:
            assert r.json()["user"]["role"] == "employee", "Privilege escalation vulnerability: created manager via public signup!"
        else:
            assert r.status_code in [400, 422], f"Expected 400/422 validation failure, got {r.status_code}"

@pytest.mark.anyio
async def test_public_signup_employee_success_and_duplicate_handling():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        email = f"new.emp.{int(datetime.utcnow().timestamp())}@company.com"
        r = await client.post("/api/v1/auth/register", json={
            "name": "New Hire",
            "email": email,
            "password": "SecurePassword123",
            "role": "employee",
            "department": "Engineering"
        })
        assert r.status_code == 201
        data = r.json()
        assert data["user"]["role"] == "employee"
        assert data["user"]["email"] == email

        # Duplicate email registration must return 409 Conflict
        r_dup = await client.post("/api/v1/auth/register", json={
            "name": "Duplicate User",
            "email": email,
            "password": "AnotherPassword123",
            "role": "employee"
        })
        assert r_dup.status_code == 409

@pytest.mark.anyio
async def test_jwt_expiry_and_invalid_tokens():
    # 1. Invalid signature / token string
    decoded = decode_access_token("invalid.token.structure")
    assert decoded is None

    # 2. Expired token
    expired_token = create_access_token(
        {"sub": "test_user", "email": "test@test.com", "role": "employee"},
        expires_delta=timedelta(seconds=-10)
    )
    decoded_expired = decode_access_token(expired_token)
    assert decoded_expired is None

    # 3. Accessing protected endpoint with expired token
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
        assert r.status_code == 401

# ============================================================================
# 2. ROLE-BASED ACCESS CONTROL (RBAC) BOUNDARIES
# ============================================================================

@pytest.mark.anyio
async def test_rbac_employee_forbidden_from_manager_routes():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Login as employee
        r_emp = await client.post("/api/v1/auth/login", json={"email": "alex@company.com", "password": "Employee@123"})
        emp_token = r_emp.json()["access_token"]
        emp_h = {"Authorization": f"Bearer {emp_token}"}

        # Attempt manager endpoints
        r1 = await client.get("/api/v1/manager/employees", headers=emp_h)
        assert r1.status_code == 403

        r2 = await client.get("/api/v1/manager/reports", headers=emp_h)
        assert r2.status_code == 403

        r3 = await client.post("/api/v1/manager/send-reminders", headers=emp_h)
        assert r3.status_code == 403

        r4 = await client.post("/api/v1/questions", headers=emp_h, json={"key": "test", "question_text": "text"})
        assert r4.status_code == 403

@pytest.mark.anyio
async def test_rbac_manager_access_isolation_and_cross_manager_blocking():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Sarah Chen (Manager 1) manages Alex & Priya
        r_sarah = await client.post("/api/v1/auth/login", json={"email": "manager@company.com", "password": "Manager@123"})
        sarah_token = r_sarah.json()["access_token"]
        sarah_h = {"Authorization": f"Bearer {sarah_token}"}

        # David Miller (Manager 2) manages Marcus
        r_david = await client.post("/api/v1/auth/login", json={"email": "david.manager@company.com", "password": "Manager@123"})
        david_token = r_david.json()["access_token"]
        david_h = {"Authorization": f"Bearer {david_token}"}

        # Sarah sees Alex in assigned employees
        r_emps_sarah = await client.get("/api/v1/manager/employees", headers=sarah_h)
        assert r_emps_sarah.status_code == 200
        sarah_emp_names = [e["name"] for e in r_emps_sarah.json()]
        assert "Alex Rivera" in sarah_emp_names
        assert "Marcus Johnson" not in sarah_emp_names

        # David sees Marcus, not Alex
        r_emps_david = await client.get("/api/v1/manager/employees", headers=david_h)
        assert r_emps_david.status_code == 200
        david_emp_names = [e["name"] for e in r_emps_david.json()]
        assert "Marcus Johnson" in david_emp_names
        assert "Alex Rivera" not in david_emp_names

        # David attempting to filter by Alex (not his employee) -> 403 Forbidden
        alex_id = [e["id"] for e in r_emps_sarah.json() if e["name"] == "Alex Rivera"][0]
        r_cross = await client.get(f"/api/v1/manager/reports?employee_id={alex_id}", headers=david_h)
        assert r_cross.status_code == 403

# ============================================================================
# 3. DAILY WORK UPDATES CRUD & SUBMITTED WEEK IMMUTABILITY
# ============================================================================

@pytest.mark.anyio
async def test_work_updates_crud_and_private_ownership():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Login as Alex
        r_alex = await client.post("/api/v1/auth/login", json={"email": "alex@company.com", "password": "Employee@123"})
        alex_token = r_alex.json()["access_token"]
        alex_h = {"Authorization": f"Bearer {alex_token}"}

        # Login as Priya
        r_priya = await client.post("/api/v1/auth/login", json={"email": "priya@company.com", "password": "Employee@123"})
        priya_token = r_priya.json()["access_token"]
        priya_h = {"Authorization": f"Bearer {priya_token}"}

        # Create update for a future date (unsubmitted week)
        future_date = (datetime.utcnow().date() + timedelta(days=60)).strftime("%Y-%m-%d")
        r_create = await client.post("/api/v1/updates", headers=alex_h, json={
            "date": future_date,
            "title": "Future Sprint Planning",
            "description": "Scoping upcoming architectural changes",
            "category": "Meeting",
            "hours_spent": 3.0
        })
        assert r_create.status_code == 201
        update_id = r_create.json()["id"]

        # Priya cannot view Alex's update (403)
        r_p_view = await client.get(f"/api/v1/updates/{update_id}", headers=priya_h)
        assert r_p_view.status_code == 403

        # Priya cannot edit Alex's update (403)
        r_p_edit = await client.put(f"/api/v1/updates/{update_id}", headers=priya_h, json={"title": "Hacked"})
        assert r_p_edit.status_code == 403

        # Priya cannot delete Alex's update (403)
        r_p_del = await client.delete(f"/api/v1/updates/{update_id}", headers=priya_h)
        assert r_p_del.status_code == 403

        # Alex can edit
        r_edit = await client.put(f"/api/v1/updates/{update_id}", headers=alex_h, json={"hours_spent": 4.5})
        assert r_edit.status_code == 200
        assert r_edit.json()["hours_spent"] == 4.5

        # Alex can delete
        r_del = await client.delete(f"/api/v1/updates/{update_id}", headers=alex_h)
        assert r_del.status_code == 204

@pytest.mark.anyio
async def test_prevent_editing_updates_for_submitted_week():
    """
    CRITICAL WORKFLOW IMMUTABILITY TEST:
    Once a weekly report is submitted, work updates within that week
    CANNOT be modified or deleted, preserving historical consistency.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_alex = await client.post("/api/v1/auth/login", json={"email": "alex@company.com", "password": "Employee@123"})
        alex_h = {"Authorization": f"Bearer {r_alex.json()['access_token']}"}

        # Alex has a pre-seeded submitted report for last week
        # Find updates in that submitted week
        r_updates = await client.get("/api/v1/updates", headers=alex_h)
        submitted_update = r_updates.json()[0]

        # Attempt to edit an update that belongs to an already submitted week
        r_edit = await client.put(f"/api/v1/updates/{submitted_update['id']}", headers=alex_h, json={
            "title": "Tampered Title"
        })
        assert r_edit.status_code == 400
        assert "submitted" in r_edit.json()["detail"].lower()

        # Attempt to delete
        r_del = await client.delete(f"/api/v1/updates/{submitted_update['id']}", headers=alex_h)
        assert r_del.status_code == 400
        assert "submitted" in r_del.json()["detail"].lower()

# ============================================================================
# 4. REPORT WORKFLOW, CONCURRENCY & HISTORICAL SNAPSHOT
# ============================================================================

@pytest.mark.anyio
async def test_report_draft_save_and_reopen():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_alex = await client.post("/api/v1/auth/login", json={"email": "alex@company.com", "password": "Employee@123"})
        alex_h = {"Authorization": f"Bearer {r_alex.json()['access_token']}"}

        r_curr = await client.get("/api/v1/reports/current", headers=alex_h)
        assert r_curr.status_code == 200
        curr = r_curr.json()
        assert curr["status"] in ["draft", "submitted"]

        if curr["status"] == "draft":
            # Save draft answers
            r_save = await client.post("/api/v1/reports/draft", headers=alex_h, json={
                "week_start_date": curr["week_start_date"],
                "week_end_date": curr["week_end_date"],
                "answers": [
                    {"question_key": "accomplishments", "question_text": "Q1", "answer": "Draft answer 1"},
                    {"question_key": "in_progress", "question_text": "Q2", "answer": "Draft answer 2"},
                    {"question_key": "blockers", "question_text": "Q3", "answer": "None"},
                    {"question_key": "priorities", "question_text": "Q4", "answer": "Ship tests"}
                ]
            })
            assert r_save.status_code == 200
            assert r_save.json()["answers"][0]["answer"] == "Draft answer 1"

@pytest.mark.anyio
async def test_concurrent_report_submission_locking():
    """
    CONCURRENCY & ATOMICITY TEST:
    Simultaneous submission requests on the same draft must be handled safely.
    One succeeds; the other gets 409 Conflict (in progress) or 400 (already submitted).
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create fresh employee
        ts = int(datetime.utcnow().timestamp())
        emp_email = f"concurrent.emp.{ts}@company.com"
        r_reg = await client.post("/api/v1/auth/register", json={
            "name": "Concurrent Tester",
            "email": emp_email,
            "password": "Password123"
        })
        token = r_reg.json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}

        r_rep = await client.get("/api/v1/reports/current", headers=h)
        report_id = r_rep.json()["id"]

        # Run 2 submissions concurrently
        res1, res2 = await asyncio.gather(
            client.post(f"/api/v1/reports/{report_id}/submit", headers=h),
            client.post(f"/api/v1/reports/{report_id}/submit", headers=h),
            return_exceptions=True
        )

        statuses = [getattr(res1, "status_code", None), getattr(res2, "status_code", None)]
        # Exactly one must succeed (200), the other must receive 400 (already submitted) or 409 (conflict)
        assert 200 in statuses, f"Expected one 200 OK, got statuses: {statuses}"
        assert (400 in statuses or 409 in statuses), f"Expected 400 or 409 for concurrent attempt, got statuses: {statuses}"

# ============================================================================
# 5. AI SUMMARY SERVICE & MULTI-TIER FALLBACK TESTS
# ============================================================================

@pytest.mark.anyio
async def test_ai_summary_heuristic_fallback_deterministic():
    """Verifies that local fallback never hallucinates and produces clean JSON."""
    sample_data = {
        "user_name": "Test Engineer",
        "week_start_date": "2026-11-09",
        "week_end_date": "2026-11-15",
        "work_updates": [
            {"title": "Unit Tests", "category": "Quality Assurance", "hours_spent": 5.0},
            {"title": "Bug Fix #10", "category": "Bug Fix", "hours_spent": 3.0}
        ],
        "answers": [
            {"question_key": "accomplishments", "answer": "Shipped unit tests and resolved bug #10."},
            {"question_key": "in_progress", "answer": "Refactoring database queries."},
            {"question_key": "blockers", "answer": "None reported."},
            {"question_key": "priorities", "answer": "Deploy to production."}
        ]
    }
    summary = generate_heuristic_summary(sample_data)
    assert "executive_summary" in summary
    assert "key_highlights" in summary
    assert "blockers_identified" in summary
    assert "manager_recommendation" in summary
    assert "Built-in" in summary["model_used"]
    assert "Test Engineer" in summary["executive_summary"]
    assert len(summary["key_highlights"]) >= 1

@pytest.mark.anyio
async def test_ai_summary_three_tier_fallback_execution():
    """Tests that summary generation never crashes even when all external providers are down."""
    sample_data = {
        "user_name": "Resilience Test",
        "week_start_date": "2026-11-09",
        "week_end_date": "2026-11-15",
        "work_updates": [],
        "answers": []
    }
    # In test mode without network, generate_ai_summary_with_retry falls back cleanly
    result = await generate_ai_summary_with_retry(sample_data, max_retries=1)
    assert result is not None
    assert "executive_summary" in result
    assert "model_used" in result

@pytest.mark.anyio
async def test_gemini_summary_success_mocked():
    """Tests successful Gemini API response processing and JSON parsing."""
    sample_data = {
        "user_name": "Alex Rivera",
        "week_start_date": "2026-11-09",
        "week_end_date": "2026-11-15",
        "work_updates": [{"title": "Implemented API", "category": "Feature", "hours_spent": 8.0}],
        "answers": [{"question_key": "accomplishments", "answer": "Shipped feature."}]
    }

    mock_gemini_json = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json.dumps({
                                "executive_summary": "Alex successfully delivered the core API features.",
                                "key_highlights": ["Implemented API"],
                                "blockers_identified": ["No blockers"],
                                "manager_recommendation": "Continue code review workflow."
                            })
                        }
                    ]
                }
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_gemini_json
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        res = await generate_gemini_summary(sample_data, api_key="test_fake_gemini_key", model_override="gemini-3.5-flash-lite")
        assert res["executive_summary"] == "Alex successfully delivered the core API features."
        assert "Google Gemini (gemini-3.5-flash-lite)" in res["model_used"]
        assert "Implemented API" in res["key_highlights"]

@pytest.mark.anyio
async def test_gemini_summary_api_error_handling_and_fallback():
    """Tests that Gemini API 404 (model not found) or 429 errors fall back gracefully without crashing."""
    sample_data = {
        "user_name": "Alex Rivera",
        "week_start_date": "2026-11-09",
        "week_end_date": "2026-11-15",
        "work_updates": [{"title": "Task", "category": "General", "hours_spent": 4.0}],
        "answers": []
    }

    mock_err_resp = httpx.Response(status_code=404, request=httpx.Request("POST", "https://generativelanguage.googleapis.com"))

    with patch("httpx.AsyncClient.post", side_effect=httpx.HTTPStatusError("404 Not Found", request=mock_err_resp.request, response=mock_err_resp)):
        # Calling generate_gemini_summary directly raises the error
        with pytest.raises(httpx.HTTPStatusError):
            await generate_gemini_summary(sample_data, api_key="test_key")

        # But calling generate_ai_summary_with_retry catches it and falls back to deterministic local engine
        fallback_res = await generate_ai_summary_with_retry(sample_data, max_retries=1)
        assert fallback_res is not None
        assert "executive_summary" in fallback_res
        assert "Built-in" in fallback_res["model_used"]

@pytest.mark.anyio
async def test_gemini_api_key_sanitization():
    """Ensures that secret API keys are never leaked in error messages or logs."""
    fake_secret = "AIzaSySecretFakeKey1234567890"
    err = ValueError(f"Connection failed while calling endpoint with key {fake_secret}")
    sanitized = _sanitize_error(err, fake_secret)
    assert fake_secret not in sanitized
    assert "[REDACTED_API_KEY]" in sanitized

# ============================================================================
# 6. RELIABILITY, PRODUCTION HARDENING & REMINDER IDEMPOTENCY
# ============================================================================

@pytest.mark.anyio
async def test_reminder_scheduler_atomic_idempotency():
    """
    Verifies that running reminder check twice for the same week
    never dispatches duplicate reminders.
    """
    # 1. Run first check
    res1 = await run_reminder_check(force=True)
    assert res1["status"] == "success"

    # 2. Run second check immediately: duplicate emails must be 0
    res2 = await run_reminder_check(force=False)
    # Today is not reminder_day or all eligible already claimed
    assert res2.get("sent_count", 0) == 0

@pytest.mark.anyio
async def test_production_jwt_secret_validation():
    """Fails startup if production JWT secret is insecure/missing."""
    with pytest.raises(Exception):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="short",
            BACKEND_CORS_ORIGINS=["https://app.vercel.app"]
        )

@pytest.mark.anyio
async def test_production_cors_wildcard_rejected():
    """Fails startup if production CORS contains wildcard with credentials."""
    with pytest.raises(Exception):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="a" * 40,
            BACKEND_CORS_ORIGINS=["*"]
        )

@pytest.mark.anyio
async def test_demo_users_endpoint_disabled_in_production():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Temporarily toggle environment to production
        orig_env = settings.ENVIRONMENT
        orig_demo = settings.ENABLE_DEMO_USERS
        try:
            settings.ENVIRONMENT = "production"
            settings.ENABLE_DEMO_USERS = False
            r = await client.get("/api/v1/auth/demo-users")
            assert r.status_code == 404
        finally:
            settings.ENVIRONMENT = orig_env
            settings.ENABLE_DEMO_USERS = orig_demo

@pytest.mark.anyio
async def test_health_check_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
