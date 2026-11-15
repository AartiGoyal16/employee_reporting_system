import logging
from datetime import datetime, timedelta
from bson import ObjectId
from app.auth.security import get_password_hash
from app.services.ai_summary import generate_heuristic_summary

logger = logging.getLogger(__name__)

DEFAULT_QUESTIONS = [
    {
        "key": "accomplishments",
        "question_text": "What were your main accomplishments this week?",
        "order": 1,
        "is_active": True
    },
    {
        "key": "in_progress",
        "question_text": "What work is currently in progress?",
        "order": 2,
        "is_active": True
    },
    {
        "key": "blockers",
        "question_text": "What blockers or challenges did you face?",
        "order": 3,
        "is_active": True
    },
    {
        "key": "priorities",
        "question_text": "What are your priorities for next week?",
        "order": 4,
        "is_active": True
    }
]

async def seed_database(db):
    from app.config import settings

    # 1. Independent Question Seeding: Ensure all standard questions exist
    for q in DEFAULT_QUESTIONS:
        existing_q = await db.questions.find_one({"key": q["key"]})
        if not existing_q:
            await db.questions.insert_one(dict(q))

    # 2. Demo users seeding: strictly conditional on environment configuration
    if not settings.ENABLE_DEMO_USERS or settings.ENVIRONMENT.lower() == "production":
        logger.info("Demo user seeding is disabled in this environment.")
        return

    # Check if demo users already exist
    existing_demo = await db.users.find_one({"email": "manager@company.com"})
    if existing_demo:
        logger.info("Demo users already present. Skipping demo user seeding.")
        return

    logger.info("Seeding database with demo users, work updates, and sample reports...")

    # 2. Seed Managers
    manager1_id = ObjectId()
    manager2_id = ObjectId()

    manager1 = {
        "_id": manager1_id,
        "email": "manager@company.com",
        "name": "Sarah Chen",
        "hashed_password": get_password_hash("Manager@123"),
        "role": "manager",
        "department": "Engineering Core",
        "created_at": datetime.utcnow()
    }
    manager2 = {
        "_id": manager2_id,
        "email": "david.manager@company.com",
        "name": "David Miller",
        "hashed_password": get_password_hash("Manager@123"),
        "role": "manager",
        "department": "Product & UX",
        "created_at": datetime.utcnow()
    }
    await db.users.insert_many([manager1, manager2])

    # 3. Seed Employees
    alex_id = ObjectId()
    priya_id = ObjectId()
    marcus_id = ObjectId()

    alex = {
        "_id": alex_id,
        "email": "alex@company.com",
        "name": "Alex Rivera",
        "hashed_password": get_password_hash("Employee@123"),
        "role": "employee",
        "department": "Engineering Core",
        "manager_id": str(manager1_id),
        "created_at": datetime.utcnow()
    }
    priya = {
        "_id": priya_id,
        "email": "priya@company.com",
        "name": "Priya Patel",
        "hashed_password": get_password_hash("Employee@123"),
        "role": "employee",
        "department": "Engineering Core",
        "manager_id": str(manager1_id),
        "created_at": datetime.utcnow()
    }
    marcus = {
        "_id": marcus_id,
        "email": "marcus@company.com",
        "name": "Marcus Johnson",
        "hashed_password": get_password_hash("Employee@123"),
        "role": "employee",
        "department": "Product & UX",
        "manager_id": str(manager2_id),
        "created_at": datetime.utcnow()
    }
    await db.users.insert_many([alex, priya, marcus])

    # 4. Seed Daily Work Updates for Alex (Past week and Current week)
    today = datetime.utcnow().date()
    # Find current Monday
    current_monday = today - timedelta(days=today.weekday())
    last_monday = current_monday - timedelta(days=7)
    last_sunday = last_monday + timedelta(days=6)

    alex_updates = [
        {
            "_id": ObjectId(),
            "user_id": str(alex_id),
            "date": (last_monday + timedelta(days=0)).strftime("%Y-%m-%d"),
            "title": "Database Schema Optimization",
            "description": "Refactored MongoDB indexes and queries for weekly reporting API. Reduced average latency by 45%.",
            "category": "Feature",
            "hours_spent": 7.0,
            "created_at": datetime.utcnow() - timedelta(days=6),
            "updated_at": datetime.utcnow() - timedelta(days=6)
        },
        {
            "_id": ObjectId(),
            "user_id": str(alex_id),
            "date": (last_monday + timedelta(days=1)).strftime("%Y-%m-%d"),
            "title": "FastAPI JWT Authentication",
            "description": "Implemented RBAC middleware, token validation, and password hashing security measures.",
            "category": "Feature",
            "hours_spent": 8.0,
            "created_at": datetime.utcnow() - timedelta(days=5),
            "updated_at": datetime.utcnow() - timedelta(days=5)
        },
        {
            "_id": ObjectId(),
            "user_id": str(alex_id),
            "date": (last_monday + timedelta(days=2)).strftime("%Y-%m-%d"),
            "title": "AI Summary Generator Service",
            "description": "Integrated LLM endpoint with retry logic and offline fallback parsing for weekly report submissions.",
            "category": "Feature",
            "hours_spent": 6.5,
            "created_at": datetime.utcnow() - timedelta(days=4),
            "updated_at": datetime.utcnow() - timedelta(days=4)
        },
        {
            "_id": ObjectId(),
            "user_id": str(alex_id),
            "date": (last_monday + timedelta(days=3)).strftime("%Y-%m-%d"),
            "title": "Investigate CORS issues on Staging",
            "description": "Fixed preflight OPTIONS headers and environment origin mismatch between Vite and FastAPI.",
            "category": "Bug Fix",
            "hours_spent": 4.0,
            "created_at": datetime.utcnow() - timedelta(days=3),
            "updated_at": datetime.utcnow() - timedelta(days=3)
        },
        {
            "_id": ObjectId(),
            "user_id": str(alex_id),
            "date": (last_monday + timedelta(days=4)).strftime("%Y-%m-%d"),
            "title": "Code Review and Integration Testing",
            "description": "Reviewed PR #42 and authored end-to-end integration tests for report submission flow.",
            "category": "Code Review",
            "hours_spent": 5.0,
            "created_at": datetime.utcnow() - timedelta(days=2),
            "updated_at": datetime.utcnow() - timedelta(days=2)
        }
    ]
    await db.work_updates.insert_many(alex_updates)

    # 5. Seed Submitted Weekly Report for Alex for last week
    alex_answers = [
        {
            "question_key": "accomplishments",
            "question_text": "What were your main accomplishments this week?",
            "answer": "Completed the backend reporting architecture, optimized database queries with new compound indexes, and integrated the AI summary generator with fallback mechanisms."
        },
        {
            "question_key": "in_progress",
            "question_text": "What work is currently in progress?",
            "answer": "Polishing the frontend employee and manager dashboards in React with real-time state synchronization."
        },
        {
            "question_key": "blockers",
            "question_text": "What blockers or challenges did you face?",
            "answer": "Staging CORS preflight restrictions caused a minor delay on Thursday, but it was resolved with updated middleware origins."
        },
        {
            "question_key": "priorities",
            "question_text": "What are your priorities for next week?",
            "answer": "Finalize PDF export formatting, deploy backend to Render and frontend to Vercel, and run load testing."
        }
    ]

    report_data_for_ai = {
        "user_name": "Alex Rivera",
        "week_start_date": last_monday.strftime("%Y-%m-%d"),
        "week_end_date": last_sunday.strftime("%Y-%m-%d"),
        "work_updates": alex_updates,
        "answers": alex_answers
    }
    alex_ai_summary = generate_heuristic_summary(report_data_for_ai)
    alex_ai_summary["model_used"] = "Google Gemini 1.5 Flash"

    alex_report = {
        "_id": ObjectId(),
        "user_id": str(alex_id),
        "user_name": "Alex Rivera",
        "user_email": "alex@company.com",
        "manager_id": str(manager1_id),
        "manager_name": "Sarah Chen",
        "week_start_date": last_monday.strftime("%Y-%m-%d"),
        "week_end_date": last_sunday.strftime("%Y-%m-%d"),
        "work_update_ids": [str(u["_id"]) for u in alex_updates],
        "work_updates_snapshot": [
            {
                "id": str(u["_id"]),
                "user_id": u["user_id"],
                "date": u["date"],
                "title": u["title"],
                "description": u["description"],
                "category": u.get("category", "Feature"),
                "hours_spent": u.get("hours_spent")
            }
            for u in alex_updates
        ],
        "answers": alex_answers,
        "status": "submitted",
        "submitted_at": datetime.utcnow() - timedelta(days=1),
        "ai_summary": alex_ai_summary,
        "created_at": datetime.utcnow() - timedelta(days=5),
        "updated_at": datetime.utcnow() - timedelta(days=1)
    }
    await db.weekly_reports.insert_one(alex_report)

    # 6. Seed Submitted Weekly Report for Priya
    priya_updates = [
        {
            "_id": ObjectId(),
            "user_id": str(priya_id),
            "date": (last_monday + timedelta(days=1)).strftime("%Y-%m-%d"),
            "title": "Vite React Dashboard Architecture",
            "description": "Constructed responsive layout with Tailwind CSS and modular role-based navigation.",
            "category": "Feature",
            "hours_spent": 8.0,
            "created_at": datetime.utcnow() - timedelta(days=5),
            "updated_at": datetime.utcnow() - timedelta(days=5)
        },
        {
            "_id": ObjectId(),
            "user_id": str(priya_id),
            "date": (last_monday + timedelta(days=3)).strftime("%Y-%m-%d"),
            "title": "Weekly Questions Form and Draft Saving",
            "description": "Developed interactive draft save auto-recovery and instant input validation for employees.",
            "category": "Feature",
            "hours_spent": 7.5,
            "created_at": datetime.utcnow() - timedelta(days=3),
            "updated_at": datetime.utcnow() - timedelta(days=3)
        }
    ]
    await db.work_updates.insert_many(priya_updates)

    priya_answers = [
        {
            "question_key": "accomplishments",
            "question_text": "What were your main accomplishments this week?",
            "answer": "Shipped the primary React dashboard shell and implemented draft auto-save and submission validations."
        },
        {
            "question_key": "in_progress",
            "question_text": "What work is currently in progress?",
            "answer": "Creating manager review filters and metrics badges."
        },
        {
            "question_key": "blockers",
            "question_text": "What blockers or challenges did you face?",
            "answer": "None this week. Collaboration with backend was smooth."
        },
        {
            "question_key": "priorities",
            "question_text": "What are your priorities for next week?",
            "answer": "Add downloadable PDF reports and test accessibility contrast compliance."
        }
    ]
    priya_ai = generate_heuristic_summary({
        "user_name": "Priya Patel",
        "week_start_date": last_monday.strftime("%Y-%m-%d"),
        "week_end_date": last_sunday.strftime("%Y-%m-%d"),
        "work_updates": priya_updates,
        "answers": priya_answers
    })
    priya_ai["model_used"] = "Google Gemini 1.5 Flash"

    priya_report = {
        "_id": ObjectId(),
        "user_id": str(priya_id),
        "user_name": "Priya Patel",
        "user_email": "priya@company.com",
        "manager_id": str(manager1_id),
        "manager_name": "Sarah Chen",
        "week_start_date": last_monday.strftime("%Y-%m-%d"),
        "week_end_date": last_sunday.strftime("%Y-%m-%d"),
        "work_update_ids": [str(u["_id"]) for u in priya_updates],
        "work_updates_snapshot": [
            {
                "id": str(u["_id"]),
                "user_id": u["user_id"],
                "date": u["date"],
                "title": u["title"],
                "description": u["description"],
                "category": u.get("category", "Feature"),
                "hours_spent": u.get("hours_spent")
            }
            for u in priya_updates
        ],
        "answers": priya_answers,
        "status": "submitted",
        "submitted_at": datetime.utcnow() - timedelta(hours=14),
        "ai_summary": priya_ai,
        "created_at": datetime.utcnow() - timedelta(days=4),
        "updated_at": datetime.utcnow() - timedelta(hours=14)
    }
    await db.weekly_reports.insert_one(priya_report)

    logger.info("Database seeding completed successfully!")
