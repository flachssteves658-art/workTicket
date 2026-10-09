
import asyncio
import redis.asyncio as redis
from examples.streaming_web.backend.redis_service import get_keys_for_label

async def test():
    # Connect to Redis using the same credentials as check_redis_keys.py
    # redis://:12345678@127.0.0.1:6379/0
    rds = redis.from_url("redis://:12345678@127.0.0.1:6379/0", encoding="utf-8", decode_responses=False)
    
    label = "武汉工程大学"
    print(f"Testing get_keys_for_label with label: '{label}'")
    
    try:
        keys = await get_keys_for_label(rds, label)
        print(f"Found {len(keys)} keys:")
        for k in keys:
            print(f" - {k}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await rds.aclose()

if __name__ == "__main__":
    asyncio.run(test())
