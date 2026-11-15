# 🚀 Employee Work & Weekly Reporting System

An enterprise-grade, backend-focused full-stack MVP built for the Technical Assessment. Employees log daily work updates and complete four weekly reflection questions; on submission, the backend automatically generates a structured **AI Executive Summary** using Google Gemini (with multi-tier fallback and retry logic) and immediately routes the read-only report to the employee's assigned manager.

---

## 🌟 Key Highlights & Assessment Deliverables

- **Backend-Focused Architecture**: Clean, modular FastAPI with async motor/pymongo MongoDB driver, Pydantic v2 schemas, and strict separation of concerns.
- **Strict Role-Based Access Control (RBAC)**:
  - **Employee**: Can only view, create, and modify their own work updates and reports.
  - **Manager**: Can only inspect reports belonging to their assigned direct reports (cross-team access is blocked with HTTP 403 Forbidden).
- **Core Weekly Workflow**:
  - Daily Work Updates CRUD with category tags & hours tracked.
  - Four Weekly Reflection Questions with draft saving and auto-recovery.
  - One-click report submission locking the report into immutable **Read-Only** mode.
- **Free-Tier AI Integration with Multi-Tier Fallback & Retry**:
  - Primary: **Google Gemini 3.5 Flash-Lite** (`gemini-3.5-flash-lite`, Free Tier via Google AI Studio).
  - Secondary: **Groq Llama-3.1-8b** (Free Tier).
  - Resilient Fallback: Built-in deterministic NLP heuristic engine ensuring 100% submission reliability even if external APIs or network connectivity are offline.
  - Zero Hallucination Guardrails: Prompts strictly constrain output to actual logged work updates and weekly answers without inventing unperformed tasks.
- **Enterprise-Grade Security & Data Integrity**:
  - 🔒 **Credential Redaction**: MongoDB URIs and passwords are automatically stripped from all logs and runtime exceptions.
  - 🔐 **Employee Route Isolation**: Work update CRUD and weekly report draft/submission routes strictly require Employee role.
  - ⚡ **Atomic Concurrency & Crash Recovery**: `submitting` transition locks drafts against double submission; orphaned submissions auto-recover on restart.
- **Bonus Capabilities Included**:
  - 📄 **PDF Generation & Export**: Download official executive report PDFs with branded headers, meta table, AI summary card, question reflections, and daily logs.
  - 🔁 **AI Retry Logic**: Exponential backoff with 2 retries for transient API network hiccups.
  - 📜 **Weekly Report History**: Full timeline drawer to browse past submitted reports.
  - ⚙️ **Configurable Questions**: Manager interface to configure custom weekly question prompts.

---

## 🔑 Seeded Demo Credentials

No external SSO or HR integration is required. The system auto-seeds realistic demo accounts with hierarchical reporting relationships upon first launch:

| Role | Name | Email | Password | Assigned Relationship |
| :--- | :--- | :--- | :--- | :--- |
| **Manager** | **Sarah Chen** | `manager@company.com` | `Manager@123` | Engineering Manager (Manages Alex & Priya) |
| **Employee** | **Alex Rivera** | `alex@company.com` | `Employee@123` | Senior Engineer (Reports to Sarah Chen) |
| **Employee** | **Priya Patel** | `priya@company.com` | `Employee@123` | Frontend Engineer (Reports to Sarah Chen) |
| **Manager** | **David Miller** | `david.manager@company.com` | `Manager@123` | Product Manager (Manages Marcus) |
| **Employee** | **Marcus Johnson** | `marcus@company.com` | `Employee@123` | UI/UX Designer (Reports to David Miller) |

> 💡 *The UI includes **1-Click Demo Login Buttons** on the sign-in screen to instantly switch between roles without manually typing credentials!*

---

## 🛠️ Tech Stack

- **Backend**: Python 3.11+ / FastAPI / Uvicorn / Pydantic v2 / PyJWT / Bcrypt / ReportLab
- **Database**: MongoDB / MongoDB Atlas (with in-memory async mock auto-detection for local testing)
- **Frontend**: React 18 / Vite / Tailwind CSS / Lucide React / Axios / React Router v6
- **AI Provider**: Google Gemini 2.5 Flash API (free tier) + Groq Llama-3.1 + Deterministic Heuristic Fallback
- **Deployment**: Vercel (Frontend SPA) + Render (FastAPI Web Service)

---

## 📁 Repository Structure

```
BharatRohan_Assess/
├── backend/
│   ├── app/
│   │   ├── auth/              # JWT tokens, Bcrypt security, RBAC dependencies
│   │   ├── models/            # Pydantic data validation schemas
│   │   ├── routers/           # REST endpoints: auth, updates, questions, reports, manager
│   │   ├── services/          # AI summary engine, ReportLab PDF exporter, seed data
│   │   ├── config.py          # Environment settings with pydantic-settings
│   │   ├── database.py        # MongoDB connection manager (Atlas + Motor + Mock)
│   │   └── main.py            # FastAPI entry point, CORS, lifespan hooks
│   ├── tests/
│   │   └── test_api.py        # Pytest integration test suite
│   ├── test_runner.py         # Standalone E2E verification test suite
│   ├── seed.py                # Standalone database re-seeder
│   ├── requirements.txt       # Python dependencies
│   ├── Dockerfile             # Multi-stage production container build
│   ├── render.yaml            # Render infrastructure blueprint
│   ├── Procfile               # Render web start command
│   └── .env.example           # Backend environment template
├── frontend/
│   ├── src/
│   │   ├── components/        # Navbar, WorkUpdateModal, AISummaryCard, QuestionModal
│   │   ├── context/           # AuthContext (JWT session state & RBAC)
│   │   ├── pages/             # Login, EmployeeDashboard, WeeklyReportPage, ManagerDashboard, ReportDetailView
│   │   ├── services/          # Axios API service client
│   │   ├── App.jsx            # React Router v6 tree with role guards
│   │   └── main.jsx           # Root DOM renderer
│   ├── package.json           # Node scripts & dependencies
│   ├── vite.config.js         # Vite configuration with /api proxy
│   ├── tailwind.config.js     # Tailwind CSS theme extension
│   ├── vercel.json            # Vercel SPA routing rewrites
│   └── .env.example           # Frontend environment template
├── PLATFORM_OPERATIONS.md     # Detailed Platform Operations Document
└── README.md                  # System overview and quickstart guide
```

---

## 🚀 Local Quickstart Guide

### 1. Prerequisites
- Python 3.10+ installed
- Node.js v18+ and npm installed
- *(Optional)* Local MongoDB or MongoDB Atlas URI (if not running, the system automatically uses the zero-config in-memory mock database)

---

### 2. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create and activate virtual environment
python -m venv venv

# Windows PowerShell:
.\venv\Scripts\Activate.ps1
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env to add your GEMINI_API_KEY (optional: system has full NLP fallback if left blank)

# Run backend comprehensive test suite
pytest -c backend/pytest.ini backend/tests/test_comprehensive.py -v

# Run legacy API test suite
pytest -c backend/pytest.ini backend/tests/test_api.py -v

# Start FastAPI development server
uvicorn app.main:app --reload --port 8000
```

FastAPI will start at `http://127.0.0.1:8000`.  
Explore interactive OpenAPI docs at `http://127.0.0.1:8000/docs`.

---

### 3. Frontend Setup

```bash
# In a new terminal, navigate to frontend directory
cd frontend

# Install npm dependencies
npm install

# Run frontend test suite
npm test

# Start Vite development server
npm run dev
```

Open your browser at `http://localhost:5173`.

---

## 📡 API Overview

| Method | Endpoint | Access | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/login` | Public | Authenticates credentials and returns JWT Bearer token |
| `GET` | `/api/v1/auth/me` | Authenticated | Retrieves current logged-in profile & role |
| `GET` | `/api/v1/auth/demo-users`| Public | Returns pre-seeded demo user accounts |
| `GET` | `/api/v1/questions` | Authenticated | Returns the 4 active weekly questions |
| `POST` | `/api/v1/questions` | Manager | Creates a new configurable weekly question (Bonus) |
| `GET` | `/api/v1/updates` | Employee | Lists employee's daily work updates (strict ownership) |
| `POST` | `/api/v1/updates` | Employee | Logs a new daily work update |
| `PUT` | `/api/v1/updates/{id}` | Employee | Edits an existing work update |
| `DELETE`| `/api/v1/updates/{id}`| Employee | Deletes a work update |
| `GET` | `/api/v1/reports/current` | Employee | Gets or creates current week's report draft |
| `POST` | `/api/v1/reports/draft` | Employee | Saves report draft answers (only if not submitted) |
| `POST` | `/api/v1/reports/{id}/submit` | Employee | Submits report, generates AI summary, locks report |
| `GET` | `/api/v1/reports/{id}/pdf` | Employee / Mgr | Downloads official PDF version of the report |
| `GET` | `/api/v1/manager/employees` | Manager | Lists employees assigned to the current manager |
| `GET` | `/api/v1/manager/reports` | Manager | Lists submitted reports for assigned employees |
| `GET` | `/api/v1/manager/reports/{id}`| Manager | Inspects full report (updates + answers + AI summary) |

---

## 🤖 AI Model Selection & Resilience Note

- **Primary Model**: **Google Gemini 3.5 Flash-Lite** (`gemini-3.5-flash-lite`, configurable via `GEMINI_MODEL`).
  - *Why selected*: Google Gemini 3.5 Flash-Lite is officially supported on the free tier according to Google's official Gemini API documentation, providing high speed, structured JSON generation, and a generous context window. Predecessor models (`gemini-1.5-flash` and `gemini-2.5-flash`) have been deprecated or phased out for new projects.
  - *Fallback*: Secondary fallback to Groq (`openai/gpt-oss-120b`) free tier.
- **Fail-Safe Heuristic Engine**: If no API key is supplied or external provider rate limits/timeouts occur, the built-in deterministic NLP heuristic engine parses work categories, logged hours, completed milestones, and blockers to synthesize the executive summary and manager recommendation. Output is strictly marked with `model_used: "Deterministic Heuristic Fallback (Local)"`. Never hallucinates or invents deliverables if updates are absent.
- **Retry Mechanism**: The system automatically executes exponential retries on transient connection timeouts.
- **Security & Guardrails**: The API key is sent via standard HTTP header `x-goog-api-key` (never exposed in query parameters or logged); the prompt explicitly instructs the LLM not to invent tasks or embellish outside the provided updates. Error logs automatically redact sensitive credentials.

---

## 🌐 Production Cloud Deployment Guide

> **Note on Email & Notifications**: In accordance with the assessment requirements, email delivery and SMTP reminder scheduler functionality are intentionally **not included**. The application focuses strictly on core work tracking, weekly reporting, reflection answers, AI summarization, submitted report immutability, PDF export, and manager accountability oversight.

### 1. MongoDB Atlas Setup
1. Create a free shared cluster (M0) on [MongoDB Atlas](https://www.mongodb.com/atlas).
2. **Database Access**: Create a database user (e.g. `reporting_user`) with `Read and write to any database` privileges. Ensure password characters that are URI-reserved (like `@`, `:`, `/`) are URL-encoded.
3. **Network Access**: Add IP address `0.0.0.0/0` (Allow Access from Anywhere) to allow inbound connections from Render's cloud servers.
4. Copy the connection string (format: `mongodb+srv://reporting_user:<PASSWORD>@cluster0.mongodb.net/employee_reporting_db?retryWrites=true&w=majority`).

### 2. Backend Deployment on Render
1. Log in to [Render](https://render.com/) and create a new **Web Service** connected to this repository (or use the included `render.yaml` Blueprint).
2. Configure settings:
   - **Root Directory**: `backend`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path**: `/health`
3. Set Environment Variables in Render:
   - `ENVIRONMENT`: `production` *(Enforces strict security, disables demo-users endpoint, and mandates MongoDB connectivity)*
   - `MONGODB_URI`: *Your MongoDB Atlas connection URI*
   - `DATABASE_NAME`: `employee_reporting_db`
   - `JWT_SECRET_KEY`: *A strong, secure secret of at least 32 characters*
   - `ALGORITHM`: `HS256`
   - `ACCESS_TOKEN_EXPIRE_MINUTES`: `10080`
   - `BACKEND_CORS_ORIGINS`: `["https://your-app.vercel.app"]` *(Exact Vercel frontend URL; single URL, comma-separated, or JSON array)*
   - `GEMINI_API_KEY`: *(Optional) Your Google AI Studio API key*
   - `GEMINI_MODEL`: `gemini-3.5-flash-lite`
   - `GROQ_API_KEY`: *(Optional) Your Groq API key for secondary fallback*
   - `SEED_DEMO_ACCOUNTS`: `"true"` for initial deployment to seed evaluation accounts, then set to `"false"`
   - `ENABLE_DEMO_USERS`: `"false"` *(Disables public demo credentials endpoint in production)*
4. Click **Deploy**. Note your backend URL (e.g., `https://employee-reporting-api.onrender.com`).

### 3. Frontend Deployment on Vercel
1. Log in to [Vercel](https://vercel.com/) and create a new project importing this repository.
2. Configure settings:
   - **Framework Preset**: `Vite`
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
3. Environment Variables:
   - `VITE_API_BASE_URL`: `https://employee-reporting-api.onrender.com/api/v1` *(Your Render backend URL with /api/v1)*
4. Click **Deploy**. Vercel will deploy your application with full SPA client-side routing powered by `frontend/vercel.json`.

### 4. Health Check & Connectivity Verification
Verify your deployment by querying the health endpoint:
```bash
curl https://employee-reporting-api.onrender.com/health
```
Expected output:
```json
{
  "status": "healthy",
  "service": "Employee Work & Weekly Reporting System",
  "environment": "production",
  "database": "mongodb_connected"
}
```
If MongoDB is unreachable, the endpoint returns HTTP `503 Service Unavailable` with details, preventing traffic from reaching an unbacked API.

### 5. Troubleshooting MongoDB Connection Failures
- **ServerSelectionTimeoutError / Connection Timeout**: Ensure Atlas Network Access includes `0.0.0.0/0`.
- **Authentication Failed**: Verify database username and password in Atlas Database Access. If the password has special characters (`@`, `:`, `#`), URL-encode them.
- **Production Startup Error**: In production, falling back to an in-memory mock database is prohibited for safety. Ensure `MONGODB_URI` is correctly provided.

### 6. Testing Core Workflow with Evaluation Accounts
Log in at your deployed Vercel URL using the pre-seeded evaluation accounts:
1. **Manager Flow**:
   - Log in as Sarah Chen (`manager@company.com` / `Manager@123`).
   - View assigned team members (Alex Rivera and Priya Patel) on the Manager Dashboard.
   - Inspect team weekly report submissions and AI-synthesized executive summaries.
   - Export official branded executive PDFs.
2. **Employee Flow**:
   - Log in as Alex Rivera (`alex@company.com` / `Employee@123`).
   - Create, edit, and delete daily work updates with hours spent and category tags.
   - Review current weekly report draft with updates automatically linked.
   - Fill in reflection questions and submit the report.
   - Verify report locks into immutable submitted mode with generated AI summary and PDF download.

For additional architectural details and edge cases, refer to [`PLATFORM_OPERATIONS.md`](./PLATFORM_OPERATIONS.md).
