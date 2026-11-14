import logging
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import mongomock
from app.config import settings

logger = logging.getLogger(__name__)

class MockCursorWrapper:
    def __init__(self, cursor):
        self._cursor = cursor

    def sort(self, *args, **kwargs):
        self._cursor = self._cursor.sort(*args, **kwargs)
        return self

    def limit(self, limit):
        self._cursor = self._cursor.limit(limit)
        return self

    def skip(self, skip):
        self._cursor = self._cursor.skip(skip)
        return self

    async def to_list(self, length=None):
        items = list(self._cursor)
        if length is not None:
            return items[:length]
        return items

    def __aiter__(self):
        self._iter = iter(list(self._cursor))
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class MockCollectionWrapper:
    def __init__(self, collection):
        self._collection = collection

    async def find_one(self, *args, **kwargs):
        return self._collection.find_one(*args, **kwargs)

    async def insert_one(self, *args, **kwargs):
        return self._collection.insert_one(*args, **kwargs)

    async def insert_many(self, *args, **kwargs):
        return self._collection.insert_many(*args, **kwargs)

    async def update_one(self, *args, **kwargs):
        return self._collection.update_one(*args, **kwargs)

    async def update_many(self, *args, **kwargs):
        return self._collection.update_many(*args, **kwargs)

    async def delete_one(self, *args, **kwargs):
        return self._collection.delete_one(*args, **kwargs)

    async def delete_many(self, *args, **kwargs):
        return self._collection.delete_many(*args, **kwargs)

    async def count_documents(self, *args, **kwargs):
        return self._collection.count_documents(*args, **kwargs)

    def find(self, *args, **kwargs):
        cursor = self._collection.find(*args, **kwargs)
        return MockCursorWrapper(cursor)

    async def create_index(self, *args, **kwargs):
        try:
            return self._collection.create_index(*args, **kwargs)
        except Exception:
            return None


class MockDatabaseWrapper:
    def __init__(self, db):
        self._db = db

    def __getitem__(self, name):
        return MockCollectionWrapper(self._db[name])

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        return MockCollectionWrapper(self._db[name])

    def get_collection(self, name):
        return MockCollectionWrapper(self._db[name])


class DatabaseManager:
    client = None
    db = None
    is_mock = False

    def __init__(self):
        # Initialize safe default mock db so calls before async connect never fail
        sync_client = mongomock.MongoClient()
        self.client = sync_client
        self.db = MockDatabaseWrapper(sync_client[settings.DATABASE_NAME])
        self.is_mock = True

    async def connect_to_database(self):
        import os
        if os.getenv("TESTING") == "1" or settings.MONGODB_URI.lower() == "mock":
            logger.info("TESTING mode active: using in-memory mock MongoDB immediately.")
            self.is_mock = True
            sync_client = mongomock.MongoClient()
            self.client = sync_client
            self.db = MockDatabaseWrapper(sync_client[settings.DATABASE_NAME])
            return

        try:
            logger.info(f"Connecting to MongoDB at {settings.MONGODB_URI}...")
            client = AsyncIOMotorClient(
                settings.MONGODB_URI,
                serverSelectionTimeoutMS=1500,
                connectTimeoutMS=1500
            )
            # Test connection
            await client.admin.command('ping')
            self.client = client
            self.db = self.client[settings.DATABASE_NAME]
            self.is_mock = False
            logger.info(f"Connected to live MongoDB database '{settings.DATABASE_NAME}'")
        except Exception as e:
            logger.warning(
                f"Could not connect to live MongoDB: {e}. "
                f"Falling back to mongomock async wrapper for local dev/testing."
            )
            self.is_mock = True
            sync_client = mongomock.MongoClient()
            self.client = sync_client
            self.db = MockDatabaseWrapper(sync_client[settings.DATABASE_NAME])
            logger.info("Using async mock in-memory MongoDB. (Provide valid MONGODB_URI for MongoDB Atlas)")

    async def close_database_connection(self):
        if self.client and not self.is_mock:
            self.client.close()
            logger.info("MongoDB connection closed.")

db_manager = DatabaseManager()

def get_database():
    return db_manager.db
