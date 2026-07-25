import requests
import os
from dotenv import load_dotenv

load_dotenv()

def probe_endpoints():
    refresh_token = os.getenv("IFIND_REFRESH_TOKEN")
    auth_url = "https://quantapi.51ifind.com/api/v1/get_access_token"
    headers = {"Content-Type": "application/json", "refresh_token": refresh_token}
    res = requests.post(auth_url, headers=headers)
    token = res.json()["data"]["access_token"]
    
    bases = [
        "https://quantapi.51ifind.com",
        "https://quantapi.10jqka.com.cn",
        "https://ft.10jqka.com.cn"
    ]
    paths = [
        "/api/v1/basic_data_service",
        "/api/v1/data_sequence",
        "/api/v1/thsapi",
        "/thsapi/v1/thsapi",
        "/api/v1/ths_data"
    ]
    
    for base in bases:
        for path in paths:
            url = f"{base}{path}"
            headers = {"Content-Type": "application/json", "access_token": token}
            payload = {"func": "THS_BD", "codes": "000001.SZ", "indicators": "ths_close_price_stock", "params": "2023-01-01,1"}
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=5)
                print(f"URL: {url} -> Status: {res.status_code}")
                if res.status_code == 200:
                    print(f"Body: {res.text[:100]}...")
            except Exception as e:
                print(f"URL: {url} -> Error: {e}")

if __name__ == "__main__":
    probe_endpoints()
