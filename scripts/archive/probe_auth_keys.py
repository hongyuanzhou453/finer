import requests
import os
from dotenv import load_dotenv

load_dotenv()

def probe_auth_variants():
    refresh_token = os.getenv("IFIND_REFRESH_TOKEN")
    auth_url = "https://quantapi.51ifind.com/api/v1/get_access_token"
    res = requests.post(auth_url, headers={"refresh_token": refresh_token})
    token = res.json()["data"]["access_token"]
    
    url = "https://quantapi.10jqka.com.cn/ds_service/api/v1/thsapi"
    # Testing multiple variants of token key in JSON body
    keys = ["access_token", "accessToken", "token", "token_key"]
    
    for key in keys:
        payload = {
            key: token,
            "func": "THS_BD",
            "codes": "000001.SZ",
            "indicators": "ths_close_price_stock",
            "params": "2023-01-01,1"
        }
        try:
            res = requests.post(url, json=payload, timeout=5)
            print(f"Key: {key} -> Status: {res.status_code}")
            if res.status_code == 200:
                print(f"Success! Body: {res.text[:100]}...")
        except Exception as e:
            print(f"Key: {key} -> Error: {e}")

if __name__ == "__main__":
    probe_auth_variants()
