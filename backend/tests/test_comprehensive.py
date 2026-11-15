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
    fake_secret = "test_mock_gemini_key_xyz987654321"
    err = ValueError(f"Connection failed while calling endpoint with key {fake_secret}")
    sanitized = _sanitize_error(err, fake_secret)
    assert fake_secret not in sanitized
    assert "[REDACTED_API_KEY]" in sanitized

# ============================================================================
# 6. RELIABILITY, PRODUCTION HARDENING
# ============================================================================

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
async def test_production_cors_format_parsing():
    """Verifies that CORS origins can be passed as JSON list, comma-separated string, or single string."""
    s_single = Settings(
        ENVIRONMENT="development",
        BACKEND_CORS_ORIGINS="https://app.vercel.app"
    )
    assert s_single.BACKEND_CORS_ORIGINS == ["https://app.vercel.app"]

    s_comma = Settings(
        ENVIRONMENT="development",
        BACKEND_CORS_ORIGINS="https://app.vercel.app, https://other.app"
    )
    assert s_comma.BACKEND_CORS_ORIGINS == ["https://app.vercel.app", "https://other.app"]

    s_json = Settings(
        ENVIRONMENT="development",
        BACKEND_CORS_ORIGINS='["https://app.vercel.app"]'
    )
    assert s_json.BACKEND_CORS_ORIGINS == ["https://app.vercel.app"]

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

@pytest.mark.anyio
async def test_production_database_fails_fast_on_unreachable_atlas():
    """Verifies that production startup fails immediately with RuntimeError if Atlas is unreachable, never falling back to mock."""
    from app.database import DatabaseManager
    mgr = DatabaseManager()
    orig_env = settings.ENVIRONMENT
    orig_uri = settings.MONGODB_URI
    try:
        settings.ENVIRONMENT = "production"
        settings.MONGODB_URI = "mongodb://nonexistent.atlas.invalid:27017"
        with pytest.raises(RuntimeError) as exc_info:
            await mgr.connect_to_database()
        assert "Production startup failed" in str(exc_info.value)
        assert mgr.is_mock is True  # Didn't switch to active mock connection
        # Verify ping_database returns False in production if mock
        is_ping = await mgr.ping_database()
        assert is_ping is False
    finally:
        settings.ENVIRONMENT = orig_env
        settings.MONGODB_URI = orig_uri

@pytest.mark.anyio
async def test_production_mock_uri_strictly_prohibited():
    """Verifies that MONGODB_URI='mock' is strictly prohibited in production."""
    from app.database import DatabaseManager
    mgr = DatabaseManager()
    orig_env = settings.ENVIRONMENT
    orig_uri = settings.MONGODB_URI
    try:
        settings.ENVIRONMENT = "production"
        settings.MONGODB_URI = "mock"
        with pytest.raises(RuntimeError) as exc_info:
            await mgr.connect_to_database()
        assert "Mock database is strictly forbidden in production" in str(exc_info.value) or "falling back to mock database is prohibited" in str(exc_info.value)
    finally:
        settings.ENVIRONMENT = orig_env
        settings.MONGODB_URI = orig_uri

@pytest.mark.anyio
async def test_demo_seeding_idempotent_and_respects_toggle():
    """Verifies that SEED_DEMO_ACCOUNTS=False disables seeding, and repeated runs never duplicate accounts."""
    db = get_database()
    orig_seed = settings.SEED_DEMO_ACCOUNTS
    try:
        # 1. When SEED_DEMO_ACCOUNTS is False, no demo seeding occurs
        settings.SEED_DEMO_ACCOUNTS = False
        await seed_database(db)

        # 2. When True, run twice - must be strictly idempotent
        settings.SEED_DEMO_ACCOUNTS = True
        await seed_database(db)
        count_sarah = await db.users.count_documents({"email": "manager@company.com"})
        assert count_sarah == 1

        # Second run on same database:
        await seed_database(db)
        count_sarah_2 = await db.users.count_documents({"email": "manager@company.com"})
        assert count_sarah_2 == 1
    finally:
        settings.SEED_DEMO_ACCOUNTS = orig_seed

# ============================================================================
# 7. FINAL DEFECT FIXES VERIFICATION TESTS
# ============================================================================

@pytest.mark.anyio
async def test_mongo_uri_redaction():
    """
    Priority 1: Redacts MongoDB credentials from URIs and exception strings,
    including passwords containing special characters ('@', ':', URL-encoded '%40'),
    while preserving hostnames and diagnostic context.
    """
    # 1. Password with special characters including '@' and ':'
    complex_secret = "m0ck!p@ss:w0rd@123"
    raw_uri_at = f"mongodb+srv://admin_user:{complex_secret}@cluster0.abcde.mongodb.net/testdb?retryWrites=true"
    redacted_at = redact_mongo_uri(raw_uri_at)
    assert complex_secret not in redacted_at
    assert "p@ss" not in redacted_at
    assert "admin_user:***@cluster0.abcde.mongodb.net" in redacted_at
    assert "retryWrites=true" in redacted_at

    # 2. URL-encoded password
    encoded_secret = "p%40ss%3Aword%21"
    raw_uri_enc = f"mongodb://db_admin:{encoded_secret}@db.internal.net:27017/prod_db"
    redacted_enc = redact_mongo_uri(raw_uri_enc)
    assert encoded_secret not in redacted_enc
    assert "db_admin:***@db.internal.net:27017/prod_db" in redacted_enc

    # 3. Exception string preservation of context
    err_msg = f"ServerSelectionTimeoutError: connection to {raw_uri_at} timed out after 5000ms"
    redacted_err = redact_mongo_uri(err_msg)
    assert complex_secret not in redacted_err
    assert "ServerSelectionTimeoutError" in redacted_err
    assert "admin_user:***@cluster0.abcde.mongodb.net" in redacted_err
    assert "timed out after 5000ms" in redacted_err

    # 4. URI with no credentials left untouched
    no_cred_uri = "mongodb://localhost:27017/devdb"
    assert redact_mongo_uri(no_cred_uri) == no_cred_uri

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
                {"question_key": "accomplishments", "question_text": "Q1", "answer": "Answer 1"},
                {"question_key": "in_progress", "question_text": "Q2", "answer": "   "},
                {"question_key": "blockers", "question_text": "Q3", "answer": "Answer 3"},
                {"question_key": "priorities", "question_text": "Q4", "answer": "Answer 4"}
            ]
        })
        assert r_sub.status_code == 400
        assert "blank" in r_sub.json()["detail"].lower()

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
            "model_used": "Groq Cloud (openai/gpt-oss-120b)"
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

# ============================================================================
# 8. LATEST COMMIT AUDIT REGRESSION SUITE
# ============================================================================

from app.main import recover_stale_submitting_reports

@pytest.mark.anyio
async def test_startup_recovery_active_vs_stale_reports():
    """Requirement 2: Active reports (<120s) must NOT be reset; only genuinely stale reports (>120s) are reset."""
    db = get_database()
    now = datetime.utcnow()
    
    # 1. Active report (submitted 10s ago)
    active_id = ObjectId()
    await db.weekly_reports.insert_one({
        "_id": active_id,
        "user_id": "test_user_active",
        "week_start_date": "2026-11-09",
        "week_end_date": "2026-11-15",
        "status": "submitting",
        "submission_started_at": now - timedelta(seconds=10),
        "updated_at": now - timedelta(seconds=10)
    })

    # 2. Stale report (submitted 300s ago)
    stale_id = ObjectId()
    await db.weekly_reports.insert_one({
        "_id": stale_id,
        "user_id": "test_user_stale",
        "week_start_date": "2026-11-09",
        "week_end_date": "2026-11-15",
        "status": "submitting",
        "submission_started_at": now - timedelta(seconds=300),
        "updated_at": now - timedelta(seconds=300)
    })

    # Run recovery with 120s threshold
    recovered_count = await recover_stale_submitting_reports(db, stale_seconds=120)
    assert recovered_count >= 1

    active_doc = await db.weekly_reports.find_one({"_id": active_id})
    assert active_doc["status"] == "submitting", "Active report was erroneously reset!"

    stale_doc = await db.weekly_reports.find_one({"_id": stale_id})
    assert stale_doc["status"] == "draft", "Stale report was not recovered to draft!"

@pytest.mark.anyio
async def test_groq_fallback_generation_mocked():
    """Requirement 3: Verifies Groq fallback with openai/gpt-oss-120b and Gemini error."""
    sample_data = {
        "user_name": "Groq Tester",
        "week_start_date": "2026-11-09",
        "week_end_date": "2026-11-15",
        "work_updates": [{"title": "Groq Feature", "category": "Feature", "hours_spent": 4.0}],
        "answers": [{"question_key": "accomplishments", "answer": "Done"}]
    }

    # Gemini fails, Groq succeeds
    with patch("app.services.ai_summary.generate_gemini_summary", side_effect=Exception("Gemini Service Unavailable")):
        with patch("app.services.ai_summary.generate_groq_summary", return_value={
            "executive_summary": "Groq fallback generated report.",
            "key_highlights": ["Groq Feature"],
            "blockers_identified": [],
            "manager_recommendation": "Maintain momentum.",
            "model_used": "Groq Cloud (openai/gpt-oss-120b)"
        }):
            with patch.object(settings, "GEMINI_API_KEY", "mock_gemini_key"):
                with patch.object(settings, "GROQ_API_KEY", "mock_groq_key"):
                    res = await generate_ai_summary_with_retry(sample_data, max_retries=1, force_provider_chain=True)
                    assert "Groq Cloud" in res["model_used"]
                    assert "openai/gpt-oss-120b" in res["model_used"]

@pytest.mark.anyio
async def test_report_validation_monday_to_sunday_week():
    """Requirement 5: Enforces legitimate Monday-to-Sunday week boundary."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_emp = await client.post("/api/v1/auth/login", json={"email": "alex@company.com", "password": "Employee@123"})
        headers = {"Authorization": f"Bearer {r_emp.json()['access_token']}"}

        # Case 1: Start date is Tuesday (not Monday) -> Reject
        r_tuesday = await client.post("/api/v1/reports/draft", headers=headers, json={
            "week_start_date": "2026-11-10", # Tuesday
            "week_end_date": "2026-11-15",   # Sunday
            "answers": []
        })
        assert r_tuesday.status_code in [400, 422]

        # Case 2: End date is Saturday (not Sunday) -> Reject
        r_saturday = await client.post("/api/v1/reports/draft", headers=headers, json={
            "week_start_date": "2026-11-09", # Monday
            "week_end_date": "2026-11-14",   # Saturday
            "answers": []
        })
        assert r_saturday.status_code in [400, 422]

        # Case 3: Legitimate Monday to Sunday -> Accepted
        r_valid = await client.post("/api/v1/reports/draft", headers=headers, json={
            "week_start_date": "2026-11-09", # Monday
            "week_end_date": "2026-11-15",   # Sunday
            "answers": []
        })
        assert r_valid.status_code == 200

@pytest.mark.anyio
async def test_report_submission_answer_validation():
    """Requirement 5: Rejects missing, duplicate, unknown, and blank answers before submission."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create dedicated test user
        email = f"validator.{int(datetime.utcnow().timestamp())}@company.com"
        await client.post("/api/v1/auth/register", json={
            "name": "Validator Employee",
            "email": email,
            "password": "Password@123",
            "role": "employee"
        })
        r_log = await client.post("/api/v1/auth/login", json={"email": email, "password": "Password@123"})
        headers = {"Authorization": f"Bearer {r_log.json()['access_token']}"}

        # Create draft report
        r_draft = await client.post("/api/v1/reports/draft", headers=headers, json={
            "week_start_date": "2026-11-09",
            "week_end_date": "2026-11-15",
            "answers": []
        })
        report_id = r_draft.json()["id"]

        # 1. Missing answers (< 4)
        r_sub_missing = await client.post(f"/api/v1/reports/{report_id}/submit", headers=headers, json={
            "answers": [
                {"question_key": "accomplishments", "question_text": "q1", "answer": "Done"}
            ]
        })
        assert r_sub_missing.status_code == 400
        assert "4" in r_sub_missing.json()["detail"]

        # 2. Duplicate question key
        r_sub_dup = await client.post(f"/api/v1/reports/{report_id}/submit", headers=headers, json={
            "answers": [
                {"question_key": "accomplishments", "question_text": "q1", "answer": "Done"},
                {"question_key": "accomplishments", "question_text": "q1 dup", "answer": "Done again"},
                {"question_key": "in_progress", "question_text": "q2", "answer": "Ongoing"},
                {"question_key": "blockers", "question_text": "q3", "answer": "None"}
            ]
        })
        assert r_sub_dup.status_code == 400
        assert "Duplicate" in r_sub_dup.json()["detail"]

        # 3. Unknown question key
        r_sub_unknown = await client.post(f"/api/v1/reports/{report_id}/submit", headers=headers, json={
            "answers": [
                {"question_key": "accomplishments", "question_text": "q1", "answer": "Done"},
                {"question_key": "in_progress", "question_text": "q2", "answer": "Ongoing"},
                {"question_key": "blockers", "question_text": "q3", "answer": "None"},
                {"question_key": "favorite_food", "question_text": "q4", "answer": "Pizza"}
            ]
        })
        assert r_sub_unknown.status_code == 400
        assert "Unknown" in r_sub_unknown.json()["detail"]

        # 4. Blank answer
        r_sub_blank = await client.post(f"/api/v1/reports/{report_id}/submit", headers=headers, json={
            "answers": [
                {"question_key": "accomplishments", "question_text": "q1", "answer": "Done"},
                {"question_key": "in_progress", "question_text": "q2", "answer": "   "},
                {"question_key": "blockers", "question_text": "q3", "answer": "None"},
                {"question_key": "priorities", "question_text": "q4", "answer": "Sprint plan"}
            ]
        })
        assert r_sub_blank.status_code == 400
        assert "blank" in r_sub_blank.json()["detail"]

        # 5. All 4 valid answers -> Success
        r_sub_valid = await client.post(f"/api/v1/reports/{report_id}/submit", headers=headers, json={
            "answers": [
                {"question_key": "accomplishments", "question_text": "q1", "answer": "Built core features"},
                {"question_key": "in_progress", "question_text": "q2", "answer": "Writing automated tests"},
                {"question_key": "blockers", "question_text": "q3", "answer": "No blockers currently"},
                {"question_key": "priorities", "question_text": "q4", "answer": "Release MVP to production"}
            ]
        })
        assert r_sub_valid.status_code == 200
        assert r_sub_valid.json()["status"] == "submitted"

@pytest.mark.anyio
async def test_work_update_mutation_concurrency_guard():
    """Requirement 6: Work updates cannot be mutated while report is submitting or submitted."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create employee
        email = f"concur.{int(datetime.utcnow().timestamp())}@company.com"
        await client.post("/api/v1/auth/register", json={
            "name": "Concurrency User",
            "email": email,
            "password": "Password@123",
            "role": "employee"
        })
        r_log = await client.post("/api/v1/auth/login", json={"email": email, "password": "Password@123"})
        headers = {"Authorization": f"Bearer {r_log.json()['access_token']}"}

        # 1. Create a work update
        r_up = await client.post("/api/v1/updates", headers=headers, json={
            "date": "2026-11-10",
            "title": "Task 1",
            "description": "Initial update",
            "category": "Feature",
            "hours_spent": 3.0
        })
        assert r_up.status_code == 201
        update_id = r_up.json()["id"]

        # 2. Lock report to submitting in db (simulating submission starting)
        db = get_database()
        cur_user = await db.users.find_one({"email": email})
        await db.weekly_reports.update_one(
            {"user_id": str(cur_user["_id"]), "week_start_date": "2026-11-09"},
            {"$set": {"status": "submitting", "submission_started_at": datetime.utcnow()}},
            upsert=True
        )

        # 3. Attempting to add a new update for that week must be rejected
        r_add = await client.post("/api/v1/updates", headers=headers, json={
            "date": "2026-11-11",
            "title": "Raced Update",
            "description": "Should fail",
            "category": "Feature",
            "hours_spent": 2.0
        })
        assert r_add.status_code == 400
        assert "submitting" in r_add.json()["detail"]

        # 4. Attempting to edit existing update must be rejected
        r_edit = await client.put(f"/api/v1/updates/{update_id}", headers=headers, json={
            "title": "Modified Title"
        })
        assert r_edit.status_code == 400
        assert "submitting" in r_edit.json()["detail"]

        # 5. Attempting to delete existing update must be rejected
        r_del = await client.delete(f"/api/v1/updates/{update_id}", headers=headers)
        assert r_del.status_code == 400
        assert "submitting" in r_del.json()["detail"]

@pytest.mark.anyio
async def test_manager_team_assignment_and_unassign():
    """Requirement 7: Manager can view unassigned employees, unassign, and reassign team members."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Login as manager
        r_mgr = await client.post("/api/v1/auth/login", json={"email": "manager@company.com", "password": "Manager@123"})
        mgr_headers = {"Authorization": f"Bearer {r_mgr.json()['access_token']}"}
        mgr_id = r_mgr.json()["user"]["id"]

        # Create a new employee (registered unassigned per onboarding policy)
        emp_email = f"teammate.{int(datetime.utcnow().timestamp())}@company.com"
        r_reg = await client.post("/api/v1/auth/register", json={
            "name": "Team Mate",
            "email": emp_email,
            "password": "Password@123",
            "role": "employee"
        })
        assert r_reg.status_code == 201
        db = get_database()
        emp_doc = await db.users.find_one({"email": emp_email})
        emp_id = str(emp_doc["_id"])

        # Manager assigns employee
        r_assign = await client.post(f"/api/v1/manager/employees/{emp_id}/assign", headers=mgr_headers)
        assert r_assign.status_code == 200

        # Manager unassigns employee
        r_unassign = await client.post(f"/api/v1/manager/employees/{emp_id}/unassign", headers=mgr_headers)
        assert r_unassign.status_code == 200
        emp_unassigned = await db.users.find_one({"_id": emp_doc["_id"]})
        assert emp_unassigned["manager_id"] is None

        # Employee appears in unassigned employees
        r_unassigned_list = await client.get("/api/v1/manager/unassigned-employees", headers=mgr_headers)
        assert r_unassigned_list.status_code == 200
        unassigned_ids = [e["id"] for e in r_unassigned_list.json()]
        assert emp_id in unassigned_ids

        # Manager reassigns employee
        r_reassign = await client.post(f"/api/v1/manager/employees/{emp_id}/assign", headers=mgr_headers)
        assert r_reassign.status_code == 200
        emp_reassigned = await db.users.find_one({"_id": emp_doc["_id"]})
        assert emp_reassigned["manager_id"] == mgr_id

@pytest.mark.anyio
async def test_manager_assignment_conflict_between_two_managers():
    """Requirement 5: Manager B cannot silently take an employee already assigned to Manager A."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Manager A (Sarah)
        r_mgr_a = await client.post("/api/v1/auth/login", json={"email": "manager@company.com", "password": "Manager@123"})
        h_mgr_a = {"Authorization": f"Bearer {r_mgr_a.json()['access_token']}"}
        mgr_a_id = r_mgr_a.json()["user"]["id"]

        # Manager B (David)
        r_mgr_b = await client.post("/api/v1/auth/login", json={"email": "david.manager@company.com", "password": "Manager@123"})
        h_mgr_b = {"Authorization": f"Bearer {r_mgr_b.json()['access_token']}"}
        mgr_b_id = r_mgr_b.json()["user"]["id"]

        # Employee registers unassigned, then Manager A assigns employee
        emp_email = f"shared.emp.{int(datetime.utcnow().timestamp())}@company.com"
        r_reg = await client.post("/api/v1/auth/register", json={
            "name": "Target Employee",
            "email": emp_email,
            "password": "Password@123",
            "role": "employee"
        })
        assert r_reg.status_code == 201
        db = get_database()
        emp_doc = await db.users.find_one({"email": emp_email})
        emp_id = str(emp_doc["_id"])

        r_assign_a = await client.post(f"/api/v1/manager/employees/{emp_id}/assign", headers=h_mgr_a)
        assert r_assign_a.status_code == 200

        # Manager B attempts to assign this employee -> 409 Conflict
        r_steal = await client.post(f"/api/v1/manager/employees/{emp_id}/assign", headers=h_mgr_b)
        assert r_steal.status_code == 409
        assert "already assigned to another manager" in r_steal.json()["detail"].lower()

        # Verify employee still belongs to Manager A
        emp_check = await db.users.find_one({"_id": emp_doc["_id"]})
        assert emp_check["manager_id"] == mgr_a_id

@pytest.mark.anyio
async def test_submission_claim_token_ownership_and_stale_takeover():
    """Requirement 2: Submission claim token prevents late rollbacks from resetting newer active claims."""
    db = get_database()
    r_oid = ObjectId()
    now = datetime.utcnow()

    # Create submitting report with token 1
    await db.weekly_reports.insert_one({
        "_id": r_oid,
        "user_id": "test_owner_user",
        "week_start_date": "2026-11-09",
        "week_end_date": "2026-11-15",
        "status": "submitting",
        "submission_claim_token": "token_1_stale",
        "submission_started_at": now - timedelta(seconds=200)
    })

    # Simulating stale recovery takeover with token 2
    takeover_res = await db.weekly_reports.find_one_and_update(
        {
            "_id": r_oid,
            "status": "submitting",
            "submission_claim_token": "token_1_stale"
        },
        {
            "$set": {
                "submission_claim_token": "token_2_active",
                "submission_started_at": datetime.utcnow()
            }
        },
        return_document=True
    )
    assert takeover_res is not None

    # Now, if an old orphaned process with token 1 tries to roll back:
    late_rollback = await db.weekly_reports.update_one(
        {"_id": r_oid, "status": "submitting", "submission_claim_token": "token_1_stale"},
        {"$set": {"status": "draft"}}
    )
    # Late rollback MUST match 0 documents and fail to overwrite
    assert late_rollback.matched_count == 0

    # Report is still submitting under active token 2
    cur_doc = await db.weekly_reports.find_one({"_id": r_oid})
    assert cur_doc["status"] == "submitting"
    assert cur_doc["submission_claim_token"] == "token_2_active"

@pytest.mark.anyio
async def test_submission_error_returns_generic_client_safe_message():
    """Requirement 4: Unexpected exceptions return generic error, redacting internal trace/details."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        email = f"safeerr.{int(datetime.utcnow().timestamp())}@company.com"
        await client.post("/api/v1/auth/register", json={
            "name": "Safe Err User",
            "email": email,
            "password": "Password@123",
            "role": "employee"
        })
        r_emp = await client.post("/api/v1/auth/login", json={"email": email, "password": "Password@123"})
        h = {"Authorization": f"Bearer {r_emp.json()['access_token']}"}

        # Create draft
        r_d = await client.post("/api/v1/reports/draft", headers=h, json={
            "week_start_date": "2026-11-09",
            "week_end_date": "2026-11-15",
            "answers": []
        })
        rep_id = r_d.json()["id"]

        valid_answers = [
            {"question_key": "accomplishments", "question_text": "q1", "answer": "A1"},
            {"question_key": "in_progress", "question_text": "q2", "answer": "A2"},
            {"question_key": "blockers", "question_text": "q3", "answer": "A3"},
            {"question_key": "priorities", "question_text": "q4", "answer": "A4"}
        ]

        # Patch AI generation to raise a sensitive internal database/network exception
        internal_secret = "InternalDatabaseException: password=super_secret_db_pass"
        with patch("app.routers.reports.generate_ai_summary_with_retry", side_effect=RuntimeError(internal_secret)):
            r_sub = await client.post(f"/api/v1/reports/{rep_id}/submit", headers=h, json={"answers": valid_answers})
            assert r_sub.status_code == 500
            # Ensure client does NOT see internal exception or passwords
            assert "super_secret_db_pass" not in r_sub.text
            assert "InternalDatabaseException" not in r_sub.text
            assert "An internal error occurred" in r_sub.json()["detail"]

@pytest.mark.anyio
async def test_concurrency_report_submission_blocks_while_work_update_mutation_in_progress():
    """Ensure report submission rejects (HTTP 409) if a work-update mutation holds an active lease."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        email = f"mutblock.{int(datetime.utcnow().timestamp())}@company.com"
        await client.post("/api/v1/auth/register", json={
            "name": "Mutation Block User",
            "email": email,
            "password": "Password@123",
            "role": "employee"
        })
        r_emp = await client.post("/api/v1/auth/login", json={"email": email, "password": "Password@123"})
        h = {"Authorization": f"Bearer {r_emp.json()['access_token']}"}

        # Create draft report
        r_d = await client.post("/api/v1/reports/draft", headers=h, json={
            "week_start_date": "2026-11-09",
            "week_end_date": "2026-11-15",
            "answers": []
        })
        rep_id = r_d.json()["id"]

        # Simulate an in-flight work-update mutation holding a lease token
        db = get_database()
        lease_token = "lease-token-in-flight-1234"
        await db.weekly_reports.update_one(
            {"_id": ObjectId(rep_id)},
            {"$addToSet": {"active_leases": lease_token}}
        )

        valid_answers = [
            {"question_key": "accomplishments", "question_text": "q1", "answer": "Done"},
            {"question_key": "in_progress", "question_text": "q2", "answer": "Doing"},
            {"question_key": "blockers", "question_text": "q3", "answer": "None"},
            {"question_key": "priorities", "question_text": "q4", "answer": "Next"}
        ]
        # Attempt submission -> must be rejected with 409 Conflict
        r_sub = await client.post(f"/api/v1/reports/{rep_id}/submit", headers=h, json={"answers": valid_answers})
        assert r_sub.status_code == 409
        assert "mutation is currently in progress" in r_sub.json()["detail"]

        # Report status is still draft
        cur_rep = await db.weekly_reports.find_one({"_id": ObjectId(rep_id)})
        assert cur_rep["status"] == "draft"

@pytest.mark.anyio
async def test_concurrency_work_update_move_between_two_weeks_atomic():
    """Ensure moving an update between two weeks atomically coordinates both reports."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        email = f"moveweek.{int(datetime.utcnow().timestamp())}@company.com"
        await client.post("/api/v1/auth/register", json={
            "name": "Move Week User",
            "email": email,
            "password": "Password@123",
            "role": "employee"
        })
        r_emp = await client.post("/api/v1/auth/login", json={"email": email, "password": "Password@123"})
        h = {"Authorization": f"Bearer {r_emp.json()['access_token']}"}

        # Create update in Week 1 (2026-11-10)
        r_up = await client.post("/api/v1/updates", headers=h, json={
            "date": "2026-11-10",
            "title": "Task in Week 1",
            "description": "Week 1 details",
            "category": "Feature",
            "hours_spent": 4.0
        })
        assert r_up.status_code == 201
        up_id = r_up.json()["id"]

        # Week 2 (2026-11-16 to 2026-11-22) is submitted
        db = get_database()
        cur_user = await db.users.find_one({"email": email})
        user_id = str(cur_user["_id"])

        await db.weekly_reports.insert_one({
            "_id": ObjectId(),
            "user_id": user_id,
            "week_start_date": "2026-11-16",
            "week_end_date": "2026-11-22",
            "work_update_ids": [],
            "answers": [],
            "status": "submitted",
            "submitted_at": datetime.utcnow()
        })

        # Attempt to move update to submitted week 2 (2026-11-17) -> must be rejected
        r_move_to_submitted = await client.put(f"/api/v1/updates/{up_id}", headers=h, json={
            "date": "2026-11-17"
        })
        assert r_move_to_submitted.status_code == 400
        assert "submitted" in r_move_to_submitted.json()["detail"]

        # Ensure update date unchanged in database
        up_check = await db.work_updates.find_one({"_id": ObjectId(up_id)})
        assert up_check["date"] == "2026-11-10"

        # Now test moving from submitted week 1 to draft week 2
        # Mark week 1 as submitted and week 2 as draft
        await db.weekly_reports.update_one(
            {"user_id": user_id, "week_start_date": "2026-11-09"},
            {"$set": {"status": "submitted"}}
        )
        await db.weekly_reports.update_one(
            {"user_id": user_id, "week_start_date": "2026-11-16"},
            {"$set": {"status": "draft"}}
        )

        r_move_from_submitted = await client.put(f"/api/v1/updates/{up_id}", headers=h, json={
            "date": "2026-11-17"
        })
        assert r_move_from_submitted.status_code == 400
        assert "submitted" in r_move_from_submitted.json()["detail"]

        # Verify target week report did not keep the update id
        rep_w2 = await db.weekly_reports.find_one({"user_id": user_id, "week_start_date": "2026-11-16"})
        assert up_id not in rep_w2.get("work_update_ids", [])

@pytest.mark.anyio
async def test_concurrency_controlled_interleavings():
    """Requirement 6: Controlled async interleavings testing create, edit, delete, move vs submit, and recovery."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create user
        email = f"interleaving.{int(datetime.utcnow().timestamp())}@company.com"
        await client.post("/api/v1/auth/register", json={
            "name": "Interleaving Tester",
            "email": email,
            "password": "Password@123",
            "role": "employee"
        })
        r_emp = await client.post("/api/v1/auth/login", json={"email": email, "password": "Password@123"})
        h = {"Authorization": f"Bearer {r_emp.json()['access_token']}"}
        user_id = r_emp.json()["user"]["id"]
        db = get_database()

        valid_answers = [
            {"question_key": "accomplishments", "question_text": "q1", "answer": "Done"},
            {"question_key": "in_progress", "question_text": "q2", "answer": "Doing"},
            {"question_key": "blockers", "question_text": "q3", "answer": "None"},
            {"question_key": "priorities", "question_text": "q4", "answer": "Next"}
        ]

        # 1. Create vs Submit: slow insert holds lease while submit is attempted
        r_d = await client.post("/api/v1/reports/draft", headers=h, json={
            "week_start_date": "2026-11-09",
            "week_end_date": "2026-11-15",
            "answers": []
        })
        rep_id = r_d.json()["id"]

        orig_insert = db.work_updates.insert_one
        async def slow_insert(*args, **kwargs):
            # Interleave submit attempt while lease is actively held
            r_sub = await client.post(f"/api/v1/reports/{rep_id}/submit", headers=h, json={"answers": valid_answers})
            assert r_sub.status_code == 409
            assert "mutation is currently in progress" in r_sub.json()["detail"]
            return await orig_insert(*args, **kwargs)

        with patch.object(db.work_updates, "insert_one", side_effect=slow_insert):
            r_create = await client.post("/api/v1/updates", headers=h, json={
                "date": "2026-11-10",
                "title": "Interleaved Create",
                "description": "Details",
                "category": "Feature",
                "hours_spent": 3.0
            })
            assert r_create.status_code == 201
            up_id = r_create.json()["id"]

        # Ensure lease was released once mutation finished
        rep_after_create = await db.weekly_reports.find_one({"_id": ObjectId(rep_id)})
        assert rep_after_create.get("active_leases", []) == []

        # 2. Edit vs Submit: slow update_one holds lease while submit is attempted
        orig_update = db.work_updates.update_one
        async def slow_update(*args, **kwargs):
            r_sub = await client.post(f"/api/v1/reports/{rep_id}/submit", headers=h, json={"answers": valid_answers})
            assert r_sub.status_code == 409
            assert "mutation is currently in progress" in r_sub.json()["detail"]
            return await orig_update(*args, **kwargs)

        with patch.object(db.work_updates, "update_one", side_effect=slow_update):
            r_edit = await client.put(f"/api/v1/updates/{up_id}", headers=h, json={
                "title": "Interleaved Edit Title"
            })
            assert r_edit.status_code == 200

        rep_after_edit = await db.weekly_reports.find_one({"_id": ObjectId(rep_id)})
        assert rep_after_edit.get("active_leases", []) == []

        # 3. Move vs Submit: moving across weeks holds leases while submit is attempted
        # Initialize week 2 draft report
        await client.post("/api/v1/reports/draft", headers=h, json={
            "week_start_date": "2026-11-16",
            "week_end_date": "2026-11-22",
            "answers": []
        })

        async def slow_move_update(*args, **kwargs):
            r_sub = await client.post(f"/api/v1/reports/{rep_id}/submit", headers=h, json={"answers": valid_answers})
            assert r_sub.status_code == 409
            assert "mutation is currently in progress" in r_sub.json()["detail"]
            return await orig_update(*args, **kwargs)

        with patch.object(db.work_updates, "update_one", side_effect=slow_move_update):
            r_move = await client.put(f"/api/v1/updates/{up_id}", headers=h, json={
                "date": "2026-11-17"
            })
            assert r_move.status_code == 200

        # Move it back to week 1 for delete testing
        await client.put(f"/api/v1/updates/{up_id}", headers=h, json={"date": "2026-11-10"})

        # 4. Delete vs Submit: slow delete_one holds lease while submit is attempted
        orig_delete = db.work_updates.delete_one
        async def slow_delete(*args, **kwargs):
            r_sub = await client.post(f"/api/v1/reports/{rep_id}/submit", headers=h, json={"answers": valid_answers})
            assert r_sub.status_code == 409
            assert "mutation is currently in progress" in r_sub.json()["detail"]
            return await orig_delete(*args, **kwargs)

        with patch.object(db.work_updates, "delete_one", side_effect=slow_delete):
            r_del = await client.delete(f"/api/v1/updates/{up_id}", headers=h)
            assert r_del.status_code == 204

        rep_after_del = await db.weekly_reports.find_one({"_id": ObjectId(rep_id)})
        assert rep_after_del.get("active_leases", []) == []

        # 5. Mutation failure after acquiring both week leases: rollback restores state
        r_new_up = await client.post("/api/v1/updates", headers=h, json={
            "date": "2026-11-10",
            "title": "Fail Task",
            "description": "Details",
            "category": "Feature",
            "hours_spent": 2.0
        })
        fail_up_id = r_new_up.json()["id"]

        # Add another operation's lease on both reports to verify it is NOT removed during rollback
        other_lease_token = "other-concurrent-op-lease-555"
        await db.weekly_reports.update_one(
            {"_id": ObjectId(rep_id)},
            {"$addToSet": {"active_leases": other_lease_token}}
        )
        rep_target_doc = await db.weekly_reports.find_one({"user_id": user_id, "week_start_date": "2026-11-16"})
        if rep_target_doc:
            await db.weekly_reports.update_one(
                {"_id": rep_target_doc["_id"]},
                {"$addToSet": {"active_leases": other_lease_token}}
            )

        from app.database import MockCollectionWrapper
        orig_wrapper_update_one = MockCollectionWrapper.update_one

        async def failing_update(self, filter_dict, *args, **kwargs):
            if getattr(self._collection, "name", None) == "work_updates" and isinstance(filter_dict, dict) and filter_dict.get("_id") == ObjectId(fail_up_id):
                raise RuntimeError("Simulated DB disk failure during work_updates update_one")
            return await orig_wrapper_update_one(self, filter_dict, *args, **kwargs)

        with patch.object(MockCollectionWrapper, "update_one", side_effect=failing_update, autospec=True):
            with pytest.raises(RuntimeError):
                await client.put(f"/api/v1/updates/{fail_up_id}", headers=h, json={"date": "2026-11-17"})

        # Verify rollback restored both week reports:
        # Target week does NOT have fail_up_id
        rep_target = await db.weekly_reports.find_one({"_id": ObjectId(rep_id)})
        rep_w2_check = await db.weekly_reports.find_one({"user_id": rep_target["user_id"], "week_start_date": "2026-11-16"})
        assert fail_up_id not in rep_w2_check.get("work_update_ids", [])
        # Target week move lease was released, but the other operation's lease was preserved
        assert other_lease_token in rep_w2_check.get("active_leases", [])
        assert len(rep_w2_check.get("active_leases", [])) == 1

        # Source week still has fail_up_id, its move lease was released, and the other operation's lease remains
        rep_w1_check = await db.weekly_reports.find_one({"_id": ObjectId(rep_id)})
        assert fail_up_id in rep_w1_check.get("work_update_ids", [])
        assert other_lease_token in rep_w1_check.get("active_leases", [])
        assert len(rep_w1_check.get("active_leases", [])) == 1

        # Verify the work update date is completely unchanged in the database
        up_doc_check = await db.work_updates.find_one({"_id": ObjectId(fail_up_id)})
        assert up_doc_check["date"] == "2026-11-10"

        # Clean up other_lease_token
        await db.weekly_reports.update_many(
            {"user_id": user_id},
            {"$pull": {"active_leases": other_lease_token}}
        )

        # 6. Two simultaneous moves on the same update
        r_move_1, r_move_2 = await asyncio.gather(
            client.put(f"/api/v1/updates/{fail_up_id}", headers=h, json={"date": "2026-11-17"}),
            client.put(f"/api/v1/updates/{fail_up_id}", headers=h, json={"date": "2026-11-18"}),
            return_exceptions=True
        )
        # Both requests must either succeed serially or be safely processed without lease corruption
        rep_w2_final = await db.weekly_reports.find_one({"user_id": rep_target["user_id"], "week_start_date": "2026-11-16"})
        assert rep_w2_final.get("active_leases", []) == []

        # 7. Mutation lasting longer than 30 seconds does NOT get bypassed by submit
        dummy_lease = "long-running-lease-999"
        await db.weekly_reports.update_one(
            {"_id": ObjectId(rep_id)},
            {"$addToSet": {"active_leases": dummy_lease}}
        )
        # Even if 60 seconds have elapsed, submit MUST still be rejected because lease token is active
        r_sub_long = await client.post(f"/api/v1/reports/{rep_id}/submit", headers=h, json={"answers": valid_answers})
        assert r_sub_long.status_code == 409
        assert "mutation is currently in progress" in r_sub_long.json()["detail"]

        # Clean up dummy lease
        await db.weekly_reports.update_one(
            {"_id": ObjectId(rep_id)},
            {"$pull": {"active_leases": dummy_lease}}
        )

@pytest.mark.anyio
async def test_stale_recovery_does_not_reset_newer_active_mutation():
    """Requirement 4: Stale recovery calls the actual recovery implementation and protects live leases."""
    from app.main import recover_stale_submitting_reports
    db = get_database()
    r_oid = ObjectId()
    now = datetime.utcnow()

    # Create submitting report with stale token (from 200s ago)
    await db.weekly_reports.insert_one({
        "_id": r_oid,
        "user_id": "test_owner_user_stale",
        "week_start_date": "2026-11-09",
        "week_end_date": "2026-11-15",
        "status": "submitting",
        "submission_claim_token": "stale-claim-token-111",
        "submission_started_at": now - timedelta(seconds=200),
        "active_leases": ["active-mutation-token-999"]
    })

    # Call the actual recovery implementation!
    recovered_count = await recover_stale_submitting_reports(db, stale_seconds=120)
    assert recovered_count >= 1

    # Verify report is recovered to draft, but active mutation lease is PRESERVED
    check_doc = await db.weekly_reports.find_one({"_id": r_oid})
    assert check_doc["status"] == "draft"
    assert "active-mutation-token-999" in check_doc["active_leases"]
    assert check_doc.get("submission_claim_token") is None

    # Clean up test doc
    await db.weekly_reports.delete_one({"_id": r_oid})

@pytest.mark.anyio
async def test_registration_employee_cannot_assign_arbitrary_manager_at_signup():
    """Requirement 3: Verify registration authorization policy prevents manager self-assignment."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        db = get_database()
        real_mgr = await db.users.find_one({"role": "manager"})
        real_mgr_id = str(real_mgr["_id"])

        # 1. Registration with a REAL existing manager ID -> 403 Forbidden
        r_real_mgr = await client.post("/api/v1/auth/register", json={
            "name": "Self Assign Real Mgr",
            "email": f"attacker.realmgr.{int(datetime.utcnow().timestamp())}@company.com",
            "password": "Password@123",
            "role": "employee",
            "manager_id": real_mgr_id
        })
        assert r_real_mgr.status_code == 403
        assert "Direct manager assignment during public registration is not permitted" in r_real_mgr.json()["detail"]

        # 2. Registration with a non-existent manager ID -> 403 Forbidden
        r_invalid_mgr = await client.post("/api/v1/auth/register", json={
            "name": "Self Assign Attacker",
            "email": f"attacker.selfassign.{int(datetime.utcnow().timestamp())}@company.com",
            "password": "Password@123",
            "role": "employee",
            "manager_id": str(ObjectId())
        })
        assert r_invalid_mgr.status_code == 403
        assert "Direct manager assignment during public registration is not permitted" in r_invalid_mgr.json()["detail"]

        # 3. Legitimate registration without manager_id succeeds with manager_id: None
        legit_email = f"legit.newemp.{int(datetime.utcnow().timestamp())}@company.com"
        r_legit = await client.post("/api/v1/auth/register", json={
            "name": "Legit Employee",
            "email": legit_email,
            "password": "Password@123",
            "role": "employee"
        })
        assert r_legit.status_code == 201
        assert r_legit.json()["user"]["manager_id"] is None

        # Verify in database that employee was created with manager_id: None
        legit_doc = await db.users.find_one({"email": legit_email})
        assert legit_doc["manager_id"] is None

