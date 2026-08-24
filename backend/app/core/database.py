import logging
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

logger = logging.getLogger("fraudlens.database")


class Database:
    client: AsyncIOMotorClient = None
    db = None


db = Database()


async def connect_to_mongo():
    logger.info("Connecting to MongoDB...")
    try:
        db.client = AsyncIOMotorClient(settings.MONGODB_URI)
        db.db = db.client[settings.MONGODB_DB_NAME]

        # Verify connection with a ping command
        await db.client.admin.command("ping")
        logger.info(f"Successfully connected to MongoDB database: '{settings.MONGODB_DB_NAME}'")

        # Create unique index on caseId
        cases_collection = db.db.get_collection("cases")
        await cases_collection.create_index("caseId", unique=True)
        logger.info("Unique index on 'caseId' ensured in 'cases' collection")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {str(e)}")
        raise e


async def close_mongo_connection():
    logger.info("Closing MongoDB connection...")
    if db.client:
        db.client.close()
        logger.info("MongoDB connection closed.")


async def get_database():
    if db.db is None:
        raise RuntimeError("Database connection is not initialized")
    return db.db


async def get_cases_collection():
    database = await get_database()
    return database.get_collection("cases")


async def is_db_connected() -> bool:
    try:
        if db.client is None:
            return False
        await db.client.admin.command("ping")
        return True
    except Exception:
        return False
