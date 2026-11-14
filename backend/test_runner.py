import os
os.environ["TESTING"] = "1"

import asyncio
import httpx
from app.main import app
from app.database import get_database
from app.services.seed_data import seed_database

async def run_all_tests():
    print("--- Starting End-to-End API Integration Verification ---")
    
    # Pre-seed in-memory database for testing
    db = get_database()
    await seed_database(db)
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health check
        print("Testing root & health...")
        r = await client.get("/")
        assert r.status_code == 200, f"Root failed: {r.status_code}"
        assert r.json()["status"] == "online"
        
        r_health = await client.get("/health")
        assert r_health.status_code == 200
        print("✅ Health check passed!")

        # 2. Login verification
        print("Testing authentication (Employee & Manager)...")
        # Invalid password
        r_bad = await client.post("/api/v1/auth/login", json={"email": "alex@company.com", "password": "Wrong"})
        assert r_bad.status_code == 401
        
        # Valid Employee Login
        r_emp = await client.post("/api/v1/auth/login", json={"email": "alex@company.com", "password": "Employee@123"})
        assert r_emp.status_code == 200
        emp_token = r_emp.json()["access_token"]
        emp_headers = {"Authorization": f"Bearer {emp_token}"}
        print("✅ Employee auth verified!")

        # Valid Manager Login
        r_mgr = await client.post("/api/v1/auth/login", json={"email": "manager@company.com", "password": "Manager@123"})
        assert r_mgr.status_code == 200
        mgr_token = r_mgr.json()["access_token"]
        mgr_headers = {"Authorization": f"Bearer {mgr_token}"}
        print("✅ Manager auth verified!")

        # 3. Weekly Questions
        print("Testing weekly questions...")
        r_q = await client.get("/api/v1/questions", headers=emp_headers)
        assert r_q.status_code == 200
        questions = r_q.json()
        assert len(questions) >= 4
        print(f"✅ Loaded {len(questions)} weekly reporting questions!")

        # 4. Work Updates CRUD
        print("Testing daily work updates...")
        r_up_create = await client.post("/api/v1/updates", headers=emp_headers, json={
            "date": "2026-11-14",
            "title": "E2E Verification and API hardening",
            "description": "Implemented test runner, validated security checks, and configured Render & Vercel builds.",
            "category": "Feature",
            "hours_spent": 6.0
        })
        assert r_up_create.status_code == 201
        update_id = r_up_create.json()["id"]

        r_up_list = await client.get("/api/v1/updates", headers=emp_headers)
        assert r_up_list.status_code == 200
        assert any(u["id"] == update_id for u in r_up_list.json())

        r_up_edit = await client.put(f"/api/v1/updates/{update_id}", headers=emp_headers, json={
            "title": "Updated: E2E Verification and API hardening",
            "hours_spent": 7.0
        })
        assert r_up_edit.status_code == 200
        assert r_up_edit.json()["hours_spent"] == 7.0
        print("✅ Work updates CRUD verified!")

        # 5. Weekly Reports Flow & AI Summary
        print("Testing weekly report draft saving & submission with AI Summary...")
        r_cur = await client.get("/api/v1/reports/current", headers=emp_headers)
        assert r_cur.status_code == 200
        report = r_cur.json()
        report_id = report["id"]

        if report["status"] == "draft":
            r_draft = await client.post("/api/v1/reports/draft", headers=emp_headers, json={
                "week_start_date": report["week_start_date"],
                "week_end_date": report["week_end_date"],
                "answers": [
                    {"question_key": "accomplishments", "question_text": "What were your main accomplishments this week?", "answer": "Shipped backend APIs, database models, and auth system."},
                    {"question_key": "in_progress", "question_text": "What work is currently in progress?", "answer": "Building frontend dashboard views."},
                    {"question_key": "blockers", "question_text": "What blockers or challenges did you face?", "answer": "None."},
                    {"question_key": "priorities", "question_text": "What are your priorities for next week?", "answer": "Deploy to Vercel and Render."}
                ]
            })
            assert r_draft.status_code == 200

            r_sub = await client.post(f"/api/v1/reports/{report_id}/submit", headers=emp_headers)
            assert r_sub.status_code == 200
            sub_data = r_sub.json()
            assert sub_data["status"] == "submitted"
            assert sub_data["ai_summary"] is not None
            assert len(sub_data["ai_summary"]["executive_summary"]) > 0
            print(f"✅ Report submitted and AI summary generated: '{sub_data['ai_summary']['executive_summary'][:60]}...'")

            # Immutable test
            r_retry = await client.post("/api/v1/reports/draft", headers=emp_headers, json={
                "week_start_date": report["week_start_date"],
                "week_end_date": report["week_end_date"],
                "answers": []
            })
            assert r_retry.status_code == 400
            print("✅ Report immutability verified (strictly read-only after submission)!")

        # 6. Manager RBAC and Isolation
        print("Testing Manager role-based isolation...")
        r_mgr_emps = await client.get("/api/v1/manager/employees", headers=mgr_headers)
        assert r_mgr_emps.status_code == 200
        emp_names = [e["name"] for e in r_mgr_emps.json()]
        assert "Alex Rivera" in emp_names
        assert "Marcus Johnson" not in emp_names

        r_mgr_reports = await client.get("/api/v1/manager/reports", headers=mgr_headers)
        assert r_mgr_reports.status_code == 200
        assert len(r_mgr_reports.json()) >= 1
        alex_report_id = r_mgr_reports.json()[0]["id"]

        # Manager 2 (David) login
        r_david = await client.post("/api/v1/auth/login", json={"email": "david.manager@company.com", "password": "Manager@123"})
        david_token = r_david.json()["access_token"]
        david_headers = {"Authorization": f"Bearer {david_token}"}

        r_david_forbidden = await client.get(f"/api/v1/manager/reports/{alex_report_id}", headers=david_headers)
        assert r_david_forbidden.status_code == 403
        print("✅ Cross-manager report access blocked (403 Forbidden) verified!")

        # Employee accessing manager routes
        r_emp_forbidden = await client.get("/api/v1/manager/reports", headers=emp_headers)
        assert r_emp_forbidden.status_code == 403
        print("✅ Employee forbidden from manager routes (403 Forbidden) verified!")

        # 7. PDF Export
        print("Testing PDF report generation...")
        r_pdf = await client.get(f"/api/v1/reports/{alex_report_id}/pdf", headers=mgr_headers)
        assert r_pdf.status_code == 200
        assert r_pdf.headers["content-type"] == "application/pdf"
        assert r_pdf.content.startswith(b"%PDF")
        print(f"✅ PDF successfully generated ({len(r_pdf.content)} bytes)!")

    print("\n🎉 ALL BACKEND APIS & RBAC VERIFIED SUCCESSFULLY! 🎉\n")

if __name__ == "__main__":
    asyncio.run(run_all_tests())
