
import asyncio
import redis.asyncio as redis

async def check():
    r = redis.from_url('redis://:12345678@127.0.0.1:6379/0', encoding='utf-8', decode_responses=True)
    print("Checking all keys in Redis...")
    keys = await r.keys('*')
    print(f"Found {len(keys)} keys:")
    for k in keys:
        print(f" - {k}")
        if 'wit_test111' in k:
             t = await r.type(k)
             print(f"   Type: {t}")
    await r.aclose()

if __name__ == "__main__":
    asyncio.run(check())
