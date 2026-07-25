import requests
import os
from dotenv import load_dotenv

load_dotenv()

def probe_formats():
    refresh_token = os.getenv("IFIND_REFRESH_TOKEN")
    auth_url = "https://quantapi.51ifind.com/api/v1/get_access_token"
    res = requests.post(auth_url, headers={"refresh_token": refresh_token})
    token = res.json()["data"]["access_token"]
    
    url = "https://quantapi.51ifind.com/api/v1/thsapi"
    
    # Format 1: JSON body with access_token inside
    print("Testing Format 1: JSON with access_token in body...")
    payload1 = {
        "access_token": token,
        "func": "THS_BD",
        "codes": "000001.SZ",
        "indicators": "ths_close_price_stock",
        "params": "2023-01-01,1"
    }
    res1 = requests.post(url, json=payload1)
    print(f"Format 1 Status: {res1.status_code}")
    
    # Format 2: Form-data with access_token in header
    print("Testing Format 2: Form-data with access_token in header...")
    headers2 = {"access_token": token}
    data2 = {
        "func": "THS_BD",
        "codes": "000001.SZ",
        "indicators": "ths_close_price_stock",
        "params": "2023-01-01,1"
    }
    res2 = requests.post(url, headers=headers2, data=data2)
    print(f"Format 2 Status: {res2.status_code}")

    # Format 3: Different base
    url3 = "https://quantapi.10jqka.com.cn/api/v1/thsapi"
    print(f"Testing Format 3: {url3} with JSON...")
    res3 = requests.post(url3, headers=headers2, json=payload1)
    print(f"Format 3 Status: {res3.status_code}")

if __name__ == "__main__":
    probe_formats()
