import requests
import os
from dotenv import load_dotenv

load_dotenv()

def try_fund_holdings():
    refresh_token = os.getenv("IFIND_REFRESH_TOKEN")
    auth_url = "https://quantapi.10jqka.com.cn/api/v1/get_access_token"
    res = requests.post(auth_url, headers={"refresh_token": refresh_token})
    token = res.json()["data"]["access_token"]
    
    url = "https://quantapi.10jqka.com.cn/api/v1/basic_data_service"
    
    # Correct structure for basic_data_service
    payload = {
        "codes": "008892.OF",
        "indipara": [
            {
                "indicator": "ths_fund_stock_portfolio_stock_name_fund",
                "indiparams": ["20231231", "0"]
            },
            {
                "indicator": "ths_fund_stock_portfolio_stock_code_fund",
                "indiparams": ["20231231", "0"]
            },
            {
                "indicator": "ths_fund_stock_portfolio_ratio_fund",
                "indiparams": ["20231231", "0"]
            }
        ]
    }
    
    headers = {
        "Content-Type": "application/json",
        "access_token": token
    }
    
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        print(f"Status: {res.status_code}")
        if res.status_code == 200:
            print(f"Success! Response: {res.text[:1000]}...")
        else:
            print(f"Error Body: {res.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    try_fund_holdings()
