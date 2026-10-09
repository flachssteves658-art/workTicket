
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import os

# From .env
DATABASE_URL = 'mysql+asyncmy://construction_user:12345678@127.0.0.1:3307/construction_hazard_detection'

async def check_streams():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.connect() as conn:
        print("Connected to database.")
        
        # Check sites first
        print("\n--- SITES ---")
        result = await conn.execute(text("SELECT * FROM sites"))
        sites = result.mappings().all()
        for s in sites:
            print(dict(s))
            
        # Check stream_configs
        print("\n--- STREAM CONFIGS ---")
        result = await conn.execute(text("SELECT * FROM stream_configs"))
        configs = result.mappings().all()
        for c in configs:
            print(dict(c))
            
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_streams())
