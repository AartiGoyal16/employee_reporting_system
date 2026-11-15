import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import db_manager, get_database
from app.services.seed_data import seed_database
from app.services.reminder import start_reminder_scheduler
from app.routers import auth, updates, questions, reports, manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("api")

async def recover_stale_submitting_reports(db, stale_seconds: int = 120) -> int:
    """
    Atomically recovers genuinely stale abandoned 'submitting' reports back to 'draft'.
    Prevents active submissions on concurrent running instances from being erroneously reset.
    """
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    cutoff_dt = now - timedelta(seconds=stale_seconds)
    cutoff_iso = cutoff_dt.isoformat()

    filter_query = {
        "status": "submitting",
        "$or": [
            {"submission_started_at": {"$lte": cutoff_dt}},
            {"submission_started_at": {"$lte": cutoff_iso}},
            {
                "submission_started_at": None,
                "$or": [
                    {"updated_at": {"$lte": cutoff_dt}},
                    {"updated_at": {"$lte": cutoff_iso}},
                    {"updated_at": None}
                ]
            }
        ]
    }

    res = await db.weekly_reports.update_many(
        filter_query,
        {"$set": {"status": "draft", "updated_at": now}}
    )
    count = getattr(res, "modified_count", 0)
    if count:
        logger.info(f"Recovered {count} genuinely stale 'submitting' reports back to 'draft'.")
    return count

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION}...")
    await db_manager.connect_to_database()
    db = get_database()
    try:
        await seed_database(db)
    except Exception as e:
        logger.error(f"Error during auto-seeding: {e}")

    # Recover only genuinely stale reports stuck in 'submitting' (> 120 seconds)
    try:
        await recover_stale_submitting_reports(db, stale_seconds=120)
    except Exception as e:
        logger.warning(f"Could not perform startup stale report recovery: {e}")
    # Launch background deadline reminder scheduler if enabled
    reminder_task = None
    if settings.ENABLE_REMINDER_SCHEDULER:
        reminder_task = asyncio.create_task(start_reminder_scheduler())
    yield
    # Shutdown
    logger.info("Shutting down application...")
    if reminder_task:
        reminder_task.cancel()
        try:
            await reminder_task
        except (asyncio.CancelledError, Exception):
            pass
    await db_manager.close_database_connection()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Backend API for Employee Work & Weekly Reporting System with AI Summarization and RBAC",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(updates.router, prefix=settings.API_V1_STR)
app.include_router(questions.router, prefix=settings.API_V1_STR)
app.include_router(reports.router, prefix=settings.API_V1_STR)
app.include_router(manager.router, prefix=settings.API_V1_STR)

@app.get("/", tags=["Health"])
async def root():
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs_url": "/docs",
        "health": "OK"
    }

@app.get("/health", tags=["Health"])
async def health_check():
    is_healthy = await db_manager.ping_database()
    if not is_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unhealthy",
                "database": "disconnected",
                "environment": settings.ENVIRONMENT,
                "error": "Database connectivity check failed"
            }
        )
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "database": "mock_in_memory" if db_manager.is_mock else "mongodb_connected"
    }
