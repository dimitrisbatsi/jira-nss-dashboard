import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

base_url = os.getenv("GEMINI_BASE_URL", "").rstrip("/")
username = os.getenv("GEMINI_USERNAME")
api_key = os.getenv("GEMINI_API_KEY")

auth = HTTPBasicAuth(username, api_key)
headers = {
    "Accept": "application/json",
    "Content-Type": "application/json"
}

endpoints = [
    "/api/meta/statuses",
    "/api/statuses",
    "/api/meta/types",
    "/api/types",
    "/api/meta/resolutions",
    "/api/resolutions"
]

for ep in endpoints:
    url = f"{base_url}{ep}"
    try:
        response = requests.get(url, auth=auth, headers=headers, timeout=10)
        print(f"{ep} -> Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"  Count: {len(data)}")
            if data:
                print(f"  Sample: {data[0]}")
    except Exception as e:
        print(f"Error on {ep}: {e}")
