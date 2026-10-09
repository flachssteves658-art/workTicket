import requests
import os
from dotenv import load_dotenv

def test_violation():
    load_dotenv()
    url = os.getenv('VIOLATION_RECORD_API_URL', 'http://127.0.0.1:8002')
    print(f"Testing VIOLATION_RECORD_API_URL: {url}")
    try:
        # Just check root or health endpoint if known, or just connect
        resp = requests.get(f"{url}/docs", timeout=5)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            print("SUCCESS: Violation API is reachable.")
        else:
            print("WARNING: Violation API returned non-200.")
    except Exception as e:
        print(f"FAILURE: Could not connect to Violation API: {e}")

if __name__ == "__main__":
    test_violation()
