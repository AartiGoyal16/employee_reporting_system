"""
Standalone database seeding script for Employee Reporting System.
Allows safe provisioning of synthetic assessment demo accounts in hosted environments
without relying on public HTTP endpoints.
"""
import asyncio
import logging
from app.database import db_manager, get_database
from app.services.seed_data import seed_database

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed")

async def run_seed():
    logger.info("Connecting to database to provision seeded accounts...")
    await db_manager.connect_to_database()
    db = get_database()
    try:
        await seed_database(db)
        logger.info("Database seeding completed successfully.")
    except Exception as exc:
        logger.error(f"Seeding failed: {exc}")
    finally:
        await db_manager.close_database_connection()

if __name__ == "__main__":
    asyncio.run(run_seed())
