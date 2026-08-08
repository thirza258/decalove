from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

class Database:
    client: AsyncIOMotorClient = None
    db = None

db = Database()

async def connect_to_mongo():
    db.client = AsyncIOMotorClient(settings.MONGODB_URL)
    db.db = db.client[settings.MONGODB_DB_NAME]
    print("Connected to MongoDB.")

async def close_mongo_connection():
    if db.client:
        db.client.close()
        print("Closed MongoDB connection.")

def get_db():
    return db.db
