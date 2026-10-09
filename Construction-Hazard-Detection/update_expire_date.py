
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import os

# From .env
DATABASE_URL = 'mysql+asyncmy://construction_user:12345678@127.0.0.1:3307/construction_hazard_detection'

async def update_stream():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        print("Connected to database.")
        
        # Update expire_date to next year
        print("Updating expire_date for 'wit_test111'...")
        await conn.execute(
            text("UPDATE stream_configs SET expire_date = '2027-01-19 00:00:00' WHERE stream_name = 'wit_test111'")
        )
        print("Update executed.")
            
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(update_stream())
