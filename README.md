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
  - Primary: **Google Gemini 1.5 Flash** (Free Tier).
  - Secondary: **Groq Llama-3.1-8b** (Free Tier).
  - Resilient Fallback: Built-in intelligent NLP heuristic engine ensuring 100% submission reliability even if external APIs or network connectivity are offline.
- **Bonus Capabilities Included**:
  - 📄 **PDF Generation & Export**: Download official executive report PDFs with branded headers, meta table, AI summary card, question reflections, and daily logs.
  - 🔁 **AI Retry Logic**: Exponential backoff with 2 retries for transient API network hiccups.
  - 📜 **Weekly Report History**: Full timeline drawer to browse past submitted reports.
  - ⚙️ **Configurable Questions**: Manager interface to configure custom weekly question prompts.
  - 📧 **Simulated Manager Notifications**: Automatic logging and notification trigger upon employee report submission.

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
- **Database**: MongoDB / MongoDB Atlas (with in-memory async mock auto-detection for instant local testability)
- **Frontend**: React 18 / Vite / Tailwind CSS / Lucide React / Axios / React Router v6
- **AI Provider**: Google Gemini 1.5 Flash API (free tier) + Groq Llama-3.1 + NLP Heuristic Fallback
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

# Run backend test suite
python test_runner.py

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

- **Primary Model**: **Google Gemini 1.5 Flash** via Google AI Studio API (`gemini-1.5-flash`).
  - *Why selected*: Google Gemini 1.5 Flash provides a generous free tier (15 requests/min), state-of-the-art context window, low latency, and structured JSON generation mode.
- **Secondary Provider**: **Groq Llama-3.1-8b-instant** free tier.
- **Fail-Safe Heuristic Engine**: If no API key is supplied or external provider rate limits occur, the built-in intelligent NLP heuristic engine parses work categories, logged hours, completed milestones, and blockers to synthesize the executive summary and manager recommendation.
- **Retry Mechanism**: The system automatically executes exponential retries on transient connection timeouts.

---

## 🌐 Deployment Instructions

Refer to [`PLATFORM_OPERATIONS.md`](./PLATFORM_OPERATIONS.md) for step-by-step instructions on deploying the React frontend to **Vercel** and the FastAPI backend to **Render**, along with MongoDB Atlas configuration.
