# 📘 Platform Operations & Architecture Document
### Employee Work & Weekly Reporting System

---

## 1. Executive Architecture Overview

The system is designed as a modular, decoupled full-stack architecture adhering to modern cloud-native standards:

```
[ Client Browser / SPA ]
       │ (HTTPS / JSON + JWT)
       ▼
[ React + Vite SPA on Vercel ]
       │ (REST API calls)
       ▼
[ FastAPI Application on Render ]
  ├── JWT Auth Middleware & RBAC Layer
  ├── Pydantic v2 Serialization & Request Validation
  ├── AI Summarization Service (Gemini / Groq / NLP Fallback)
  └── ReportLab PDF Rendering Engine
       │
       ▼
[ MongoDB Atlas Hosted Cluster ]
  ├── users (Employees & Managers)
  ├── work_updates (Daily tasks & hours)
  ├── weekly_reports (Drafts, Submitted Reports, AI Summaries)
  └── questions (Configurable weekly prompts)
```

---

## 2. Database Schema & Data Design

MongoDB is used as the document store. Documents are structured to support fast, single-query dashboard loading and historical reporting:

### 2.1 Collection: `users`
```json
{
  "_id": "ObjectId",
  "email": "alex@company.com",
  "name": "Alex Rivera",
  "hashed_password": "bcrypt_hashed_string",
  "role": "employee", // "employee" or "manager"
  "department": "Engineering Core",
  "manager_id": "ObjectId('manager_user_id')", // null for top managers
  "created_at": "ISODate"
}
```
**Indexes**:
- `email`: Unique index (`{"email": 1}`, unique: true)
- `manager_id`: Compound query index (`{"manager_id": 1, "role": 1}`)

### 2.2 Collection: `work_updates`
```json
{
  "_id": "ObjectId",
  "user_id": "string(user_id)",
  "date": "2026-11-14", // YYYY-MM-DD
  "title": "Database Schema Optimization",
  "description": "Refactored MongoDB indexes and queries for weekly reporting API.",
  "category": "Feature", // Feature, Bug Fix, Code Review, Meeting, DevOps, etc.
  "hours_spent": 7.0,
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```
**Indexes**:
- `user_id_date`: Compound index (`{"user_id": 1, "date": -1}`) for instant user dashboard retrieval and week-range queries.

### 2.3 Collection: `weekly_reports`
```json
{
  "_id": "ObjectId",
  "user_id": "string(user_id)",
  "user_name": "Alex Rivera",
  "user_email": "alex@company.com",
  "manager_id": "string(manager_id)",
  "manager_name": "Sarah Chen",
  "week_start_date": "2026-11-09",
  "week_end_date": "2026-11-15",
  "work_update_ids": ["update_id_1", "update_id_2"],
  "answers": [
    {
      "question_key": "accomplishments",
      "question_text": "What were your main accomplishments this week?",
      "answer": "Completed the backend reporting architecture..."
    },
    {
      "question_key": "in_progress",
      "question_text": "What work is currently in progress?",
      "answer": "Polishing the frontend employee and manager dashboards..."
    },
    {
      "question_key": "blockers",
      "question_text": "What blockers or challenges did you face?",
      "answer": "None."
    },
    {
      "question_key": "priorities",
      "question_text": "What are your priorities for next week?",
      "answer": "Finalize PDF export formatting and deploy to cloud."
    }
  ],
  "status": "submitted", // "draft" or "submitted"
  "submitted_at": "ISODate",
  "ai_summary": {
    "executive_summary": "Alex Rivera demonstrated steady weekly progress...",
    "key_highlights": [
      "Completed backend reporting architecture",
      "Optimized database queries with new compound indexes"
    ],
    "blockers_identified": [
      "No critical blockers reported this week."
    ],
    "manager_recommendation": "Maintain current momentum and review upcoming priorities.",
    "model_used": "Google Gemini 1.5 Flash",
    "generated_at": "ISODate"
  },
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```
**Indexes**:
- `user_week`: Unique compound index (`{"user_id": 1, "week_start_date": 1}`, unique: true)
- `manager_reports`: Compound index (`{"manager_id": 1, "status": 1, "submitted_at": -1}`)

### 2.4 Collection: `questions`
```json
{
  "_id": "ObjectId",
  "key": "accomplishments",
  "question_text": "What were your main accomplishments this week?",
  "order": 1,
  "is_active": true
}
```

---

## 3. Role-Based Access Control (RBAC) & Security Architecture

1. **Authentication Flow**:
   - `POST /api/v1/auth/login` checks credentials using Bcrypt (`checkpw`).
   - Generates an `HS256` signed JWT token containing `sub` (user ID), `email`, `role`, and `name`.
   - Client persists token in `localStorage` and injects `Authorization: Bearer <token>` on all requests.
2. **Backend Authorization Enforcement**:
   - `require_employee`: Rejects access to manager-only endpoints with `403 Forbidden`.
   - `require_manager`: Rejects non-manager requests with `403 Forbidden`.
   - **Data Ownership Isolation**:
     - Work updates query strictly enforces `query = {"user_id": current_user["id"]}`.
     - Manager dashboard queries strictly enforce `query = {"manager_id": current_user["id"]}`.
     - Cross-manager access (e.g., Manager B requesting a report submitted to Manager A) is explicitly verified and denied with `403 Forbidden`.
3. **Immutability Guarantee**:
   - Once a weekly report status becomes `submitted`, all draft modification and re-submission requests are blocked with `400 Bad Request`.

---

## 4. Cloud Deployment Runbook

### 4.1 Hosted MongoDB Atlas Setup
1. Create a free shared cluster (M0) on [MongoDB Atlas](https://www.mongodb.com/atlas).
2. Under **Database Access**, create a user `reporting_user` with read/write privileges.
3. Under **Network Access**, add IP `0.0.0.0/0` (Allow Access from Anywhere) to permit connections from Render's cloud servers.
4. Copy the connection string:
   `mongodb+srv://reporting_user:<PASSWORD>@cluster0.mongodb.net/employee_reporting_db?retryWrites=true&w=majority`

---

### 4.2 Backend Deployment on Render

1. Log in to [Render](https://render.com/) and click **New → Web Service**.
2. Connect your GitHub repository.
3. Configure the service settings:
   - **Root Directory**: `backend`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path**: `/health`
4. Set **Environment Variables** in the Render Dashboard:
   - `MONGODB_URI`: *Your MongoDB Atlas connection URI*
   - `DATABASE_NAME`: `employee_reporting_db`
   - `JWT_SECRET_KEY`: *A strong random 64-character secret*
   - `ALGORITHM`: `HS256`
   - `ACCESS_TOKEN_EXPIRE_MINUTES`: `10080`
   - `GEMINI_API_KEY`: *Your Google AI Studio API key*
   - `BACKEND_CORS_ORIGINS`: `["*"]`
5. Click **Create Web Service**.
6. Note the deployed Render URL: `https://your-backend-app.onrender.com`.

---

### 4.3 Frontend Deployment on Vercel

1. Log in to [Vercel](https://vercel.com/) and click **Add New → Project**.
2. Import the GitHub repository.
3. Configure the project settings:
   - **Framework Preset**: `Vite`
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
4. Set **Environment Variables**:
   - `VITE_API_BASE_URL`: `https://your-backend-app.onrender.com/api/v1`
5. Click **Deploy**.
6. The frontend will be available at `https://your-project.vercel.app`.

---

## 5. Operations, Health Monitoring & Troubleshooting

### 5.1 Health Check Probe
- Endpoint: `GET /health`
- Response:
  ```json
  {
    "status": "healthy",
    "database": "mongodb_connected"
  }
  ```

### 5.2 Standalone Database Reseed
To reset demo data back to clean state at any time:
```bash
cd backend
python seed.py
```

### 5.3 Troubleshooting Matrix

| Issue | Cause | Resolution |
| :--- | :--- | :--- |
| `CORS Error in Browser` | Origin mismatch between frontend and backend | Update `BACKEND_CORS_ORIGINS` in backend environment to include the Vercel domain or `["*"]`. |
| `MongoDB Connection Timeout` | Atlas IP whitelist does not allow Render's dynamic IP | In Atlas Network Access, ensure `0.0.0.0/0` is active. |
| `AI Summary Using Heuristic Mode` | `GEMINI_API_KEY` missing or exhausted | System gracefully falls back to built-in NLP engine without failing the submission; verify API key in environment variables. |
| `401 Unauthorized` | Expired or missing Bearer token | Relogin using demo credentials; check JWT expiration setting. |
