import asyncio
import os
from dotenv import load_dotenv
from sqlalchemy.engine.url import make_url
from asyncmy import create_pool

load_dotenv()

async def update_expire_date():
    database_url = os.getenv('DATABASE_URL')
    print(f"Connecting to: {database_url}")
    url = make_url(database_url)
    
    pool = await create_pool(
        host=url.host,
        port=url.port or 3306,
        user=url.username,
        password=url.password,
        db=url.database,
        autocommit=True,
    )
    
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Update to next year
                sql = "UPDATE stream_configs SET expire_date = '2027-01-01 00:00:00' WHERE stream_name = 'wit_test111'"
                await cur.execute(sql)
                print(f"Updated expire_date. Affected rows: {cur.rowcount}")
                
                # Verify
                sql_check = "SELECT stream_name, expire_date FROM stream_configs WHERE stream_name = 'wit_test111'"
                await cur.execute(sql_check)
                row = await cur.fetchone()
                print(f"New expire_date: {row}")
                
    except Exception as e:
        print(f"Error: {e}")
    finally:
        pool.close()
        await pool.wait_closed()

if __name__ == "__main__":
    asyncio.run(update_expire_date())