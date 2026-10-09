
import asyncio
import os
import sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Add project root to sys.path
sys.path.append(os.getcwd())

async def list_streams():
    # Hardcoded for now based on previous observations or env
    # The default in config.py is 'mysql+asyncmy://user:password@localhost/dbname'
    # But start_services.bat mentions password '12345678'.
    # I should try to read .env or use a likely connection string.
    # Assuming standard setup: mysql+asyncmy://root:12345678@127.0.0.1:3306/construction_hazard_detection
    
    # Let's try to load .env first
    from dotenv import load_dotenv
    load_dotenv()
    
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("DATABASE_URL not found in env, trying default...")
        db_url = 'mysql+asyncmy://root:12345678@127.0.0.1:3306/construction_hazard_detection'
    
    print(f"Connecting to DB: {db_url}")
    
    try:
        engine = create_async_engine(db_url)
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT * FROM stream_configs"))
            rows = result.fetchall()
            print(f"Found {len(rows)} streams in DB:")
            for row in rows:
                print(row)
                
            print("\nSites:")
            result = await conn.execute(text("SELECT * FROM sites"))
            rows = result.fetchall()
            for row in rows:
                print(row)
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(list_streams())
