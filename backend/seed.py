import asyncio
import logging
from app.database import db_manager, get_database
from app.services.seed_data import seed_database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed")

async def main():
    logger.info("Initializing database connection for standalone seed...")
    await db_manager.connect_to_database()
    db = get_database()
    # Force clean reseed if requested
    logger.info("Clearing existing collections...")
    await db.users.delete_many({})
    await db.work_updates.delete_many({})
    await db.weekly_reports.delete_many({})
    await db.questions.delete_many({})
    
    logger.info("Running seed script...")
    await seed_database(db)
    logger.info("Standalone seed completed successfully!")
    await db_manager.close_database_connection()

if __name__ == "__main__":
    asyncio.run(main())
