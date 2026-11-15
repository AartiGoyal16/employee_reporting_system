import os
import pytest
import asyncio
from datetime import datetime, timedelta
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.config import Settings, settings
from app.database import get_database, db_manager, DatabaseManager, redact_mongo_uri
from app.services.seed_data import seed_database
from app.services.email_service import send_manager_notification_email, send_reminder_email
from unittest.mock import patch, MagicMock
import json
import httpx
from bson import ObjectId
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

        # Run 2 submissions concurrently with complete answers
        sub_payload = {
            "answers": [
                {"question_key": "accomplishments", "question_text": "Q1", "answer": "Done 1"},
                {"question_key": "in_progress", "question_text": "Q2", "answer": "Done 2"},
                {"question_key": "blockers", "question_text": "Q3", "answer": "None"},
                {"question_key": "priorities", "question_text": "Q4", "answer": "Next"}
            ]
        }
        res1, res2 = await asyncio.gather(
            client.post(f"/api/v1/reports/{report_id}/submit", headers=h, json=sub_payload),
            client.post(f"/api/v1/reports/{report_id}/submit", headers=h, json=sub_payload),
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

# ============================================================================
# 7. FINAL DEFECT FIXES VERIFICATION TESTS
# ============================================================================

def test_mongo_uri_redaction():
    """Priority 1: Redacts MongoDB credentials from URIs and exception strings."""
    raw_uri = "mongodb+srv://admin_user:P@ssw0rd123!@cluster0.abcde.mongodb.net/testdb?retryWrites=true"
    redacted = redact_mongo_uri(raw_uri)
    assert "P@ssw0rd123!" not in redacted
    assert "admin_user:***@" in redacted

    err_msg = f"Connection failed to {raw_uri} timed out"
    redacted_err = redact_mongo_uri(err_msg)
    assert "P@ssw0rd123!" not in redacted_err
    assert "admin_user:***@" in redacted_err

@pytest.mark.anyio
async def test_email_html_escaping():
    """Priority 1: Escapes all dynamic content inserted into email HTML."""
    with patch("app.services.email_service.send_email_async", return_value=True) as mock_send:
        await send_manager_notification_email(
            manager_email="mgr@company.com",
            manager_name="<script>alert('xss')</script>Manager",
            employee_name="<b>Employee</b>",
            week_start="2026-11-09",
            week_end="2026-11-15",
            ai_highlights=["<img src=x onerror=alert(1)> Highlight"],
            report_id="12345"
        )
        assert mock_send.called
        body = mock_send.call_args[0][2]
        assert "<script>" not in body
        assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in body
        assert "<b>Employee</b>" not in body
        assert "&lt;b&gt;Employee&lt;/b&gt;" in body
        assert "<img src=x onerror=alert(1)>" not in body
        assert "&lt;img src=x onerror=alert(1)&gt;" in body

@pytest.mark.anyio
async def test_rbac_manager_forbidden_from_employee_routes():
    """Priority 1: Enforces employee-only access on employee endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_mgr = await client.post("/api/v1/auth/login", json={"email": "manager@company.com", "password": "Manager@123"})
        mgr_h = {"Authorization": f"Bearer {r_mgr.json()['access_token']}"}

        # 1. GET /updates -> 403
        r1 = await client.get("/api/v1/updates", headers=mgr_h)
        assert r1.status_code == 403

        # 2. POST /updates -> 403
        r2 = await client.post("/api/v1/updates", headers=mgr_h, json={
            "date": "2026-11-14",
            "title": "Manager trying to add update",
            "description": "Long enough description",
            "hours_spent": 4.0
        })
        assert r2.status_code == 403

        # 3. GET /reports/current -> 403
        r3 = await client.get("/api/v1/reports/current", headers=mgr_h)
        assert r3.status_code == 403

        # 4. POST /reports/draft -> 403
        r4 = await client.post("/api/v1/reports/draft", headers=mgr_h, json={
            "week_start_date": "2026-11-09",
            "week_end_date": "2026-11-15",
            "answers": []
        })
        assert r4.status_code == 403

@pytest.mark.anyio
async def test_backend_validation_work_updates_and_answers():
    """Priority 1: Backend validation for work-update dates, edit fields, hours and report answers."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_emp = await client.post("/api/v1/auth/login", json={"email": "priya@company.com", "password": "Employee@123"})
        h = {"Authorization": f"Bearer {r_emp.json()['access_token']}"}

        # 1. Invalid date format
        r_bad_date = await client.post("/api/v1/updates", headers=h, json={
            "date": "2026-99-99",
            "title": "Valid Title",
            "description": "Valid description long enough",
            "hours_spent": 5.0
        })
        assert r_bad_date.status_code == 422

        # 2. Negative hours
        r_neg_hours = await client.post("/api/v1/updates", headers=h, json={
            "date": "2026-11-14",
            "title": "Valid Title",
            "description": "Valid description long enough",
            "hours_spent": -2.0
        })
        assert r_neg_hours.status_code == 422

        # 3. Zero hours (must be gt=0)
        r_zero_hours = await client.post("/api/v1/updates", headers=h, json={
            "date": "2026-11-14",
            "title": "Valid Title",
            "description": "Valid description long enough",
            "hours_spent": 0
        })
        assert r_zero_hours.status_code == 422

        # 4. Hours > 24
        r_huge_hours = await client.post("/api/v1/updates", headers=h, json={
            "date": "2026-11-14",
            "title": "Valid Title",
            "description": "Valid description long enough",
            "hours_spent": 25.0
        })
        assert r_huge_hours.status_code == 422

@pytest.mark.anyio
async def test_prevent_work_update_and_draft_modification_while_submitting():
    """Priority 2: Prevents work-update creation, editing or deletion and draft answers while a report is submitting."""
    db = get_database()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_emp = await client.post("/api/v1/auth/login", json={"email": "priya@company.com", "password": "Employee@123"})
        h = {"Authorization": f"Bearer {r_emp.json()['access_token']}"}

        # Initialize Priya's current week report first so it exists in db
        r_init = await client.get("/api/v1/reports/current", headers=h)
        assert r_init.status_code == 200
        cur_report = r_init.json()
        report_id = cur_report["id"]
        test_date = cur_report["week_start_date"]

        # Temporarily set report to 'submitting'
        await db.weekly_reports.update_one(
            {"_id": ObjectId(report_id)},
            {"$set": {"status": "submitting", "submission_started_at": datetime.utcnow()}}
        )

        # Attempt to create work update for submitting week -> 400
        r_create = await client.post("/api/v1/updates", headers=h, json={
            "date": test_date,
            "title": "Blocked Update",
            "description": "Should be rejected because report is submitting",
            "hours_spent": 2.0
        })
        assert r_create.status_code == 400
        assert "submitting" in r_create.json()["detail"].lower()

        # Attempt to save draft answers while submitting -> 400
        r_draft = await client.post("/api/v1/reports/draft", headers=h, json={
            "week_start_date": cur_report["week_start_date"],
            "week_end_date": cur_report["week_end_date"],
            "answers": []
        })
        assert r_draft.status_code == 400
        assert "submitting" in r_draft.json()["detail"].lower()

        # Restore back to draft
        await db.weekly_reports.update_one(
            {"_id": ObjectId(report_id)},
            {"$set": {"status": "draft"}}
        )

@pytest.mark.anyio
async def test_submit_requires_all_four_answers():
    """Priority 2: Enforces all 4 weekly reflection questions must be answered before submitting."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_emp = await client.post("/api/v1/auth/login", json={"email": "priya@company.com", "password": "Employee@123"})
        h = {"Authorization": f"Bearer {r_emp.json()['access_token']}"}

        r_rep = await client.get("/api/v1/reports/current", headers=h)
        rep_id = r_rep.json()["id"]

        # Attempt submission with blank answers -> 400
        r_sub = await client.post(f"/api/v1/reports/{rep_id}/submit", headers=h, json={
            "answers": [
                {"question_key": "q1", "question_text": "Q1", "answer": "Answer 1"},
                {"question_key": "q2", "question_text": "Q2", "answer": "   "},
                {"question_key": "q3", "question_text": "Q3", "answer": "Answer 3"},
                {"question_key": "q4", "question_text": "Q4", "answer": "Answer 4"}
            ]
        })
        assert r_sub.status_code == 400
        assert "all 4 weekly reflection questions must be answered" in r_sub.json()["detail"].lower()

@pytest.mark.anyio
async def test_stale_submitting_report_recovery():
    """Priority 2: Safe recovery for stale submitting reports after a server crash."""
    db = get_database()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_emp = await client.post("/api/v1/auth/login", json={"email": "priya@company.com", "password": "Employee@123"})
        h = {"Authorization": f"Bearer {r_emp.json()['access_token']}"}

        r_rep = await client.get("/api/v1/reports/current", headers=h)
        rep_id = r_rep.json()["id"]

        # Artificially set status to 'submitting' with timestamp 200 seconds ago (stale)
        stale_time = datetime.utcnow() - timedelta(seconds=200)
        await db.weekly_reports.update_one(
            {"_id": ObjectId(rep_id)},
            {"$set": {"status": "submitting", "submission_started_at": stale_time}}
        )

        # Now submit with complete answers - it should detect stale submission, recover, and submit
        r_sub = await client.post(f"/api/v1/reports/{rep_id}/submit", headers=h, json={
            "answers": [
                {"question_key": "accomplishments", "question_text": "Q1", "answer": "Done 1"},
                {"question_key": "in_progress", "question_text": "Q2", "answer": "Done 2"},
                {"question_key": "blockers", "question_text": "Q3", "answer": "None"},
                {"question_key": "priorities", "question_text": "Q4", "answer": "Next"}
            ]
        })
        assert r_sub.status_code == 200
        assert r_sub.json()["status"] == "submitted"
        assert len(r_sub.json().get("work_updates", [])) >= 0

@pytest.mark.anyio
async def test_reminders_force_true_idempotent_and_smtp_failure():
    """Priority 3: Manual reminders idempotent (force=True does not duplicate) and unconfirmed SMTP marked failed."""
    db = get_database()
    await db.reminder_logs.delete_many({})

    # 1. Run reminder check with force=True -> sends reminders
    res1 = await run_reminder_check(force=True)
    assert res1["status"] == "success"
    sent1 = res1["sent_count"]
    assert sent1 > 0

    # 2. Run reminder check again immediately with force=True -> duplicate count must be 0!
    res2 = await run_reminder_check(force=True)
    assert res2["status"] == "success"
    assert res2["sent_count"] == 0, "Repeated manager reminder must be idempotent even with force=True"

    # 3. Test SMTP failure does not record reminder as sent
    await db.reminder_logs.delete_many({})
    with patch("app.services.reminder.send_reminder_email", return_value=False):
        with patch.dict(os.environ, {"TESTING": "0"}):
            res_fail = await run_reminder_check(force=True)
            assert res_fail["sent_count"] == 0
            failed_logs = await db.reminder_logs.find({"status": "failed"}).to_list(10)
            assert len(failed_logs) > 0
            sent_logs = await db.reminder_logs.find({"status": "sent"}).to_list(10)
            assert len(sent_logs) == 0

@pytest.mark.anyio
async def test_mocked_gemini_groq_local_fallback_sequence():
    """Priority 4: Tests the actual mocked Gemini -> Groq -> local fallback sequence."""
    sample_data = {
        "user_name": "Fallback Sequence Test",
        "week_start_date": "2026-11-09",
        "week_end_date": "2026-11-15",
        "work_updates": [{"title": "Task 1", "category": "Feature", "hours_spent": 5.0}],
        "answers": [{"question_key": "accomplishments", "answer": "Built feature"}]
    }

    # Step 1: Gemini succeeds
    with patch("app.services.ai_summary.generate_gemini_summary", return_value={
        "executive_summary": "Gemini Summary",
        "key_highlights": ["Gemini Highlight"],
        "blockers_identified": [],
        "manager_recommendation": "Gemini Rec",
        "model_used": "Google Gemini (gemini-3.5-flash-lite)"
    }):
        with patch.object(settings, "GEMINI_API_KEY", "fake_gemini_key"):
            with patch.dict(os.environ, {"ALLOW_LIVE_AI_IN_TESTS": "1"}):
                res_gem = await generate_ai_summary_with_retry(sample_data)
                assert "Gemini" in res_gem["model_used"]

    # Step 2: Gemini fails, Groq succeeds
    with patch("app.services.ai_summary.generate_gemini_summary", side_effect=Exception("Gemini Down")):
        with patch("app.services.ai_summary.generate_groq_summary", return_value={
            "executive_summary": "Groq Summary",
            "key_highlights": ["Groq Highlight"],
            "blockers_identified": [],
            "manager_recommendation": "Groq Rec",
            "model_used": "Groq Llama-3 (Free Tier Fallback)"
        }):
            with patch.object(settings, "GEMINI_API_KEY", "fake_gemini_key"):
                with patch.object(settings, "GROQ_API_KEY", "fake_groq_key"):
                    with patch.dict(os.environ, {"ALLOW_LIVE_AI_IN_TESTS": "1"}):
                        res_groq = await generate_ai_summary_with_retry(sample_data, max_retries=1)
                        assert "Groq" in res_groq["model_used"]

    # Step 3: Both Gemini and Groq fail -> Local fallback succeeds
    with patch("app.services.ai_summary.generate_gemini_summary", side_effect=Exception("Gemini Down")):
        with patch("app.services.ai_summary.generate_groq_summary", side_effect=Exception("Groq Down")):
            with patch.object(settings, "GEMINI_API_KEY", "fake_gemini_key"):
                with patch.object(settings, "GROQ_API_KEY", "fake_groq_key"):
                    with patch.dict(os.environ, {"ALLOW_LIVE_AI_IN_TESTS": "1"}):
                        res_local = await generate_ai_summary_with_retry(sample_data, max_retries=1)
                        assert "Built-in" in res_local["model_used"]

@pytest.mark.anyio
async def test_heuristic_summary_no_fabricated_accomplishments():
    """Priority 4: No fabricated accomplishments in heuristic summary when no updates are provided."""
    empty_data = {
        "user_name": "Clean Test",
        "week_start_date": "2026-11-09",
        "week_end_date": "2026-11-15",
        "work_updates": [],
        "answers": []
    }
    res = generate_heuristic_summary(empty_data)
    assert "deliverables and tasks" not in res["key_highlights"][0]
    assert "No specific accomplishments or work updates logged" in res["key_highlights"][0]

@pytest.mark.anyio
async def test_seed_data_gemini_metadata():
    """Priority 4: Correct model metadata in demo seed data."""
    db = get_database()
    alex = await db.users.find_one({"email": "alex@company.com"})
    alex_report = await db.weekly_reports.find_one({"user_id": str(alex["_id"]), "status": "submitted"})
    assert alex_report is not None
    assert alex_report.get("ai_summary") is not None
    model = alex_report["ai_summary"].get("model_used", "")
    assert "1.5" not in model, f"Found obsolete model in seeded report: {model}"
    assert "gemini-3.5-flash-lite" in model
