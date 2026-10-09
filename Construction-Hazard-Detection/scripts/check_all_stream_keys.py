
import asyncio
import redis.asyncio as redis

async def list_all_keys():
    rds = redis.from_url("redis://:12345678@127.0.0.1:6379/0", encoding="utf-8", decode_responses=False)
    
    print("Listing all keys starting with 'stream_frame:':")
    cursor = 0
    while True:
        cursor, keys = await rds.scan(cursor=cursor, match="stream_frame:*")
        for key in keys:
            try:
                decoded_key = key.decode('utf-8')
                print(f" - {decoded_key}")
            except Exception:
                print(f" - {key} (decoding failed)")
        
        if cursor == 0:
            break
            
    await rds.aclose()

if __name__ == "__main__":
    asyncio.run(list_all_keys())
