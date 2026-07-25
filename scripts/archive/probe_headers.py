import requests
import os
from dotenv import load_dotenv

load_dotenv()

def probe_headers():
    refresh_token = os.getenv("IFIND_REFRESH_TOKEN")
    auth_url = "https://quantapi.51ifind.com/api/v1/get_access_token"
    res = requests.post(auth_url, headers={"refresh_token": refresh_token})
    token = res.json()["data"]["access_token"]
    
    url = "https://quantapi.51ifind.com/api/v1/thsapi"
    payload = {"func": "THS_BD", "codes": "000001.SZ", "indicators": "ths_close_price_stock", "params": "2023-01-01,1"}
    
    header_variants = [
        {"access_token": token},
        {"Authorization": f"Bearer {token}"},
        {"X-THS-Token": token},
        {"token": token}
    ]
    
    for headers in header_variants:
        headers["Content-Type"] = "application/json"
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=5)
            print(f"Header: {list(headers.keys())} -> Status: {res.status_code}")
        except Exception as e:
            print(f"Header: {list(headers.keys())} -> Error: {e}")

if __name__ == "__main__":
    probe_headers()
