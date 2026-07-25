import requests
import os
from dotenv import load_dotenv

load_dotenv()

def probe_complex():
    refresh_token = os.getenv("IFIND_REFRESH_TOKEN")
    auth_url = "https://quantapi.51ifind.com/api/v1/get_access_token"
    res = requests.post(auth_url, headers={"refresh_token": refresh_token})
    token = res.json()["data"]["access_token"]
    
    # Common endpoint from some blog posts
    url = "https://quantapi.10jqka.com.cn/ds_service/api/v1/ths_data"
    
    print(f"Token: {token[:10]}...")
    
    # Variant 1: JSON with token in header
    print("Testing JSON + Header token...")
    try:
        res1 = requests.post(url, headers={"access_token": token, "Content-Type": "application/json"}, 
                             json={"func": "THS_BD", "codes": "000001.SZ", "indicators": "ths_close_price_stock", "params": "2023-01-01,1"})
        print(f"Res 1: {res1.status_code}")
    except: pass

    # Variant 2: Form data (URL-encoded)
    print("Testing Form-data + Header token...")
    try:
        res2 = requests.post(url, headers={"access_token": token}, 
                             data={"func": "THS_BD", "codes": "000001.SZ", "indicators": "ths_close_price_stock", "params": "2023-01-01,1"})
        print(f"Res 2: {res2.status_code}")
    except: pass

    # Variant 3: Token in Body
    print("Testing JSON + Body token...")
    try:
        res3 = requests.post(url, json={"access_token": token, "func": "THS_BD", "codes": "000001.SZ", "indicators": "ths_close_price_stock", "params": "2023-01-01,1"})
        print(f"Res 3: {res3.status_code}")
    except: pass

if __name__ == "__main__":
    probe_complex()
