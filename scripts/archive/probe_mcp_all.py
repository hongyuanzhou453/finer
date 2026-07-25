import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

def probe_all_servers():
    token = os.getenv("IFIND_MCP_AUTH_TOKEN")
    servers = {
        "fund": os.getenv("IFIND_MCP_FUND_URL"),
        "stock": os.getenv("IFIND_MCP_STOCK_URL")
    }
    
    headers = {
        "Authorization": token,
        "Content-Type": "application/json"
    }

    for name, url in servers.items():
        print(f"--- Probing {name} server: {url} ---")
        
        # Test 1: List tools (we know this part might work at /tools/list)
        try:
            res = requests.post(f"{url}/tools/list", headers=headers, json={"jsonrpc":"2.0", "id":1, "method":"tools/list"}, timeout=5)
            print(f"List tools: {res.status_code}")
        except Exception as e:
            print(f"List tools error: {e}")

        # Test 2: Call tool (the problematic one)
        try:
            # Simple tool name for each server
            tool_name = "get_fund_info" if name == "fund" else "get_stock_info"
            payload = {
                "jsonrpc": "2.0",
                "id": "2",
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": {"query": "易方达蓝筹精选(008892)"} if name == "fund" else {"query": "同花顺(300033)"}
                }
            }
            # Try both root and /tools/call
            res_root = requests.post(url, headers=headers, json=payload, timeout=5)
            print(f"Call tool (root): {res_root.status_code}")
            
            res_sub = requests.post(f"{url}/tools/call", headers=headers, json=payload, timeout=5)
            print(f"Call tool (/tools/call): {res_sub.status_code}")
            
        except Exception as e:
            print(f"Call tool error: {e}")

if __name__ == "__main__":
    probe_all_servers()
