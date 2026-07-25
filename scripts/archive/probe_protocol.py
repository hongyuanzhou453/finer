import requests
import os
from dotenv import load_dotenv

load_dotenv()

def try_protocol():
    refresh_token = os.getenv("IFIND_REFRESH_TOKEN")
    auth_url = "https://quantapi.51ifind.com/api/v1/get_access_token"
    res = requests.post(auth_url, headers={"refresh_token": refresh_token})
    token = res.json()["data"]["access_token"]
    
    # User's sample protocol string
    protocol = "THS_BD('688001.SH,688002.SH','ths_pe_lyr_stock;ths_ps_lyr_stock','2026-04-03;2026-04-03','format:json')"
    
    url = "https://quantapi.51ifind.com/api/v1/thsapi"
    # Testing protocol string in 'q' or 'func' or as raw body
    variants = [
        {"json": {"q": protocol}, "label": "q in JSON"},
        {"json": {"func": "THS_BD", "codes": "688001.SH", "indicators": "ths_pe_lyr_stock", "params": "2026-04-03,2"}, "label": "Structured JSON (retry)"},
        {"data": {"q": protocol}, "label": "q in form-data"}
    ]
    
    for v in variants:
        headers = {"access_token": token}
        try:
            if "json" in v:
                res = requests.post(url, headers=headers, json=v["json"], timeout=5)
            else:
                res = requests.post(url, headers=headers, data=v["data"], timeout=5)
            print(f"{v['label']} -> Status: {res.status_code}")
            if res.status_code == 200:
                print(f"Success! Body: {res.text[:200]}...")
        except Exception as e:
            print(f"{v['label']} -> Error: {e}")

if __name__ == "__main__":
    try_protocol()
