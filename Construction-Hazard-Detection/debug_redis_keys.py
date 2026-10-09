
import redis
import base64
import re

def decode_key(key):
    try:
        decoded_key = key.decode('utf-8', errors='ignore')
        match = re.match(r'stream_frame:([A-Za-z0-9\-_]+=*)\|([A-Za-z0-9\-_]+=*)', decoded_key)
        if match:
            encoded_site, encoded_stream = match.groups()
            site = base64.urlsafe_b64decode(encoded_site).decode('utf-8')
            stream = base64.urlsafe_b64decode(encoded_stream).decode('utf-8')
            return f"Site: {site}, Stream: {stream} (Original Key: {decoded_key})"
        else:
            return f"Unmatched Key Format: {decoded_key}"
    except Exception as e:
        return f"Error decoding key {key}: {e}"

def main():
    try:
        # Connect to Redis
        r = redis.Redis(host='localhost', port=6379, password='12345678')
        
        # Scan for keys
        cursor = 0
        keys = []
        while True:
            cursor, batch = r.scan(cursor=cursor, match='stream_frame:*')
            keys.extend(batch)
            if cursor == 0:
                break
        
        print(f"Found {len(keys)} keys matching 'stream_frame:*':")
        for key in keys:
            print(decode_key(key))
            
        if not keys:
            print("No keys found. Please check if the backend service is running and processing video streams.")
            
    except Exception as e:
        print(f"Failed to connect to Redis or scan keys: {e}")

if __name__ == "__main__":
    main()
