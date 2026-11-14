import os
os.environ["TESTING"] = "1"

import pytest
from fastapi.testclient import TestClient
from app.main import app

def test_root_and_health():
    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["status"] == "online"

        resp_health = client.get("/health")
        assert resp_health.status_code == 200
        assert resp_health.json()["status"] == "healthy"

def test_auth_login_success_and_failure():
    with TestClient(app) as client:
        # Invalid password
        bad_resp = client.post("/api/v1/auth/login", json={
            "email": "alex@company.com",
            "password": "WrongPassword"
        })
        assert bad_resp.status_code == 401

        # Successful employee login
        emp_resp = client.post("/api/v1/auth/login", json={
            "email": "alex@company.com",
            "password": "Employee@123"
        })
        assert emp_resp.status_code == 200
        emp_data = emp_resp.json()
        assert "access_token" in emp_data
        assert emp_data["user"]["role"] == "employee"
        assert emp_data["user"]["email"] == "alex@company.com"

        # Successful manager login
        mgr_resp = client.post("/api/v1/auth/login", json={
            "email": "manager@company.com",
            "password": "Manager@123"
        })
        assert mgr_resp.status_code == 200
        mgr_data = mgr_resp.json()
        assert mgr_data["user"]["role"] == "manager"

def test_get_questions():
    with TestClient(app) as client:
        login_res = client.post("/api/v1/auth/login", json={
            "email": "alex@company.com",
            "password": "Employee@123"
        })
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.get("/api/v1/questions", headers=headers)
        assert resp.status_code == 200
        questions = resp.json()
        assert len(questions) >= 4
        keys = [q["key"] for q in questions]
        assert "accomplishments" in keys
        assert "in_progress" in keys
        assert "blockers" in keys
        assert "priorities" in keys

def test_work_updates_crud():
    with TestClient(app) as client:
        login_res = client.post("/api/v1/auth/login", json={
            "email": "alex@company.com",
            "password": "Employee@123"
        })
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create
        create_res = client.post("/api/v1/updates", headers=headers, json={
            "date": "2026-11-14",
            "title": "Built REST endpoints and tests",
            "description": "Implemented FastAPI routers and test suite for weekly reporting.",
            "category": "Feature",
            "hours_spent": 5.5
        })
        assert create_res.status_code == 201
        update_item = create_res.json()
        update_id = update_item["id"]
        assert update_item["title"] == "Built REST endpoints and tests"

        # Read
        get_res = client.get(f"/api/v1/updates/{update_id}", headers=headers)
        assert get_res.status_code == 200
        assert get_res.json()["id"] == update_id

        # Update / Edit
        edit_res = client.put(f"/api/v1/updates/{update_id}", headers=headers, json={
            "title": "Updated: Built REST endpoints and tests",
            "hours_spent": 6.0
        })
        assert edit_res.status_code == 200
        assert edit_res.json()["title"] == "Updated: Built REST endpoints and tests"
        assert edit_res.json()["hours_spent"] == 6.0

def test_weekly_reporting_flow_and_ai_summary():
    with TestClient(app) as client:
        # Login as employee
        login_res = client.post("/api/v1/auth/login", json={
            "email": "alex@company.com",
            "password": "Employee@123"
        })
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Get current report
        current_res = client.get("/api/v1/reports/current", headers=headers)
        assert current_res.status_code == 200
        report = current_res.json()
        report_id = report["id"]

        if report["status"] == "draft":
            # Save draft
            draft_res = client.post("/api/v1/reports/draft", headers=headers, json={
                "week_start_date": report["week_start_date"],
                "week_end_date": report["week_end_date"],
                "answers": [
                    {
                        "question_key": "accomplishments",
                        "question_text": "What were your main accomplishments this week?",
                        "answer": "Finished all automated tests and RBAC authorization."
                    },
                    {
                        "question_key": "in_progress",
                        "question_text": "What work is currently in progress?",
                        "answer": "Completing React dashboard UI."
                    },
                    {
                        "question_key": "blockers",
                        "question_text": "What blockers or challenges did you face?",
                        "answer": "None."
                    },
                    {
                        "question_key": "priorities",
                        "question_text": "What are your priorities for next week?",
                        "answer": "Deploy to Vercel and Render."
                    }
                ]
            })
            assert draft_res.status_code == 200

            # Submit report
            submit_res = client.post(f"/api/v1/reports/{report_id}/submit", headers=headers)
            assert submit_res.status_code == 200
            submitted_data = submit_res.json()
            assert submitted_data["status"] == "submitted"
            assert submitted_data["ai_summary"] is not None
            assert len(submitted_data["ai_summary"]["executive_summary"]) > 10

            # Verify report is now read-only (resubmitting/draft saving should fail)
            retry_draft = client.post("/api/v1/reports/draft", headers=headers, json={
                "week_start_date": report["week_start_date"],
                "week_end_date": report["week_end_date"],
                "answers": []
            })
            assert retry_draft.status_code == 400

def test_manager_rbac_and_isolation():
    with TestClient(app) as client:
        # 1. Login as Sarah Chen (Manager of Alex and Priya)
        sarah_login = client.post("/api/v1/auth/login", json={
            "email": "manager@company.com",
            "password": "Manager@123"
        })
        sarah_token = sarah_login.json()["access_token"]
        sarah_headers = {"Authorization": f"Bearer {sarah_token}"}

        # Check Sarah's assigned employees
        emp_res = client.get("/api/v1/manager/employees", headers=sarah_headers)
        assert emp_res.status_code == 200
        employees = emp_res.json()
        emp_names = [e["name"] for e in employees]
        assert "Alex Rivera" in emp_names
        assert "Priya Patel" in emp_names
        assert "Marcus Johnson" not in emp_names  # Marcus belongs to David!

        # Check Sarah's reports
        reports_res = client.get("/api/v1/manager/reports", headers=sarah_headers)
        assert reports_res.status_code == 200
        reports = reports_res.json()
        assert len(reports) >= 1
        alex_report_id = reports[0]["id"]

        # 2. Login as David Miller (Manager of Marcus)
        david_login = client.post("/api/v1/auth/login", json={
            "email": "david.manager@company.com",
            "password": "Manager@123"
        })
        david_token = david_login.json()["access_token"]
        david_headers = {"Authorization": f"Bearer {david_token}"}

        # David tries to access Alex's report -> Must be 403 Forbidden!
        david_forbidden = client.get(f"/api/v1/manager/reports/{alex_report_id}", headers=david_headers)
        assert david_forbidden.status_code == 403

        # 3. Employee tries to access manager endpoint -> Must be 403 Forbidden!
        alex_login = client.post("/api/v1/auth/login", json={
            "email": "alex@company.com",
            "password": "Employee@123"
        })
        alex_token = alex_login.json()["access_token"]
        alex_headers = {"Authorization": f"Bearer {alex_token}"}
        alex_forbidden = client.get("/api/v1/manager/reports", headers=alex_headers)
        assert alex_forbidden.status_code == 403

def test_pdf_export():
    with TestClient(app) as client:
        # Login as manager Sarah
        mgr_login = client.post("/api/v1/auth/login", json={
            "email": "manager@company.com",
            "password": "Manager@123"
        })
        token = mgr_login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        reports_res = client.get("/api/v1/manager/reports", headers=headers)
        report_id = reports_res.json()[0]["id"]

        pdf_res = client.get(f"/api/v1/reports/{report_id}/pdf", headers=headers)
        assert pdf_res.status_code == 200
        assert pdf_res.headers["content-type"] == "application/pdf"
        assert pdf_res.content.startswith(b"%PDF")
