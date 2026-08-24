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

        # 1. Cases indexes
        cases_col = db.db.get_collection("cases")
        await cases_col.create_index("caseId", unique=True)
        logger.info("Unique index on 'caseId' ensured in 'cases' collection")

        # 2. Entities indexes
        entities_col = db.db.get_collection("entities")
        await entities_col.create_index("entityId", unique=True)
        await entities_col.create_index("caseId")
        await entities_col.create_index([("caseId", 1), ("entityId", 1)])
        logger.info("Indexes ensured in 'entities' collection")

        # 3. Accounts indexes
        accounts_col = db.db.get_collection("accounts")
        await accounts_col.create_index("accountId", unique=True)
        await accounts_col.create_index("caseId")
        await accounts_col.create_index("ownerEntityId")
        await accounts_col.create_index("bankEntityId")
        logger.info("Indexes ensured in 'accounts' collection")

        # 4. Relationships indexes
        relationships_col = db.db.get_collection("relationships")
        await relationships_col.create_index("relationshipId", unique=True)
        await relationships_col.create_index("caseId")
        await relationships_col.create_index("sourceEntityId")
        await relationships_col.create_index("targetEntityId")
        logger.info("Indexes ensured in 'relationships' collection")

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


async def get_entities_collection():
    database = await get_database()
    return database.get_collection("entities")


async def get_accounts_collection():
    database = await get_database()
    return database.get_collection("accounts")


async def get_relationships_collection():
    database = await get_database()
    return database.get_collection("relationships")


async def is_db_connected() -> bool:
    try:
        if db.client is None:
            return False
        await db.client.admin.command("ping")
        return True
    except Exception:
        return False
