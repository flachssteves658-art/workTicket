import asyncio
import base64
import os
from dotenv import load_dotenv
import redis.asyncio as redis

load_dotenv()

async def check_keys():
    redis_url = os.getenv('REDIS_URL', 'redis://:12345678@127.0.0.1:6379/0')
    print(f"Connecting to Redis: {redis_url}")
    r = redis.from_url(redis_url, encoding='utf-8', decode_responses=True)
    
    # Label is "武汉工程大学"
    label = "武汉工程大学"
    encoded_label = base64.urlsafe_b64encode(label.encode('utf-8')).decode('utf-8')
    pattern = f"stream_frame:{encoded_label}|*"
    
    print(f"Searching for keys matching: {pattern}")
    keys = await r.keys(pattern)
    print(f"Found {len(keys)} keys.")
    for k in keys:
        print(f"Key: {k}")
    if keys:
        print(f"Sample key: {keys[0]}")
        # Check type
        key_type = await r.type(keys[0])
        print(f"Type: {key_type}")

    await r.close()

if __name__ == "__main__":
    asyncio.run(check_keys())