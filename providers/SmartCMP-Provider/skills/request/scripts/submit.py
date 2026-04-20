# -*- coding: utf-8 -*-
"""Submit a service request to SmartCMP.

Usage:
  python submit.py --file <json_file>
  python submit.py --json '<json_string>'

Arguments:
  --file, -f    Path to JSON file containing request body (recommended)
  --json, -j    JSON string (not recommended in PowerShell due to encoding)

Output:
  - Request ID and State for each submitted request

Environment:
  CMP_URL    - Base URL (IP, hostname, or full path; auto-normalized)
  CMP_COOKIE - Session cookie string

Examples:
  python submit.py --file request_body.json
  python submit.py -f ./my_request.json

API Reference:
  POST /generic-request/submit
"""
import sys
import json
import os
import argparse
import requests

# Import shared utilities (handles URL normalization, SSL warnings)
try:
    from _common import require_config, create_headers
except ImportError:
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared', 'scripts'))
    from _common import require_config, create_headers

BASE_URL, AUTH_TOKEN, HEADERS, _ = require_config()


def _load_runtime_cookies() -> dict:
    raw = os.environ.get("ATLASCLAW_COOKIES", "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _enrich_request_body(body: object) -> object:
    if not isinstance(body, dict):
        return body

    enriched = dict(body)
    if enriched.get("userId") and enriched.get("userLoginId"):
        return enriched

    cookies = _load_runtime_cookies()
    cookie_user_id = str(cookies.get("userId", "") or "").strip()
    if cookie_user_id and not enriched.get("userId"):
        enriched["userId"] = cookie_user_id

    cookie_login_id = str(cookies.get("userLoginId", "") or "").strip()
    if cookie_login_id and not enriched.get("userLoginId"):
        enriched["userLoginId"] = cookie_login_id

    runtime_user_id = str(os.environ.get("ATLASCLAW_USER_ID", "") or "").strip()
    if runtime_user_id and not enriched.get("userLoginId"):
        enriched["userLoginId"] = runtime_user_id

    return enriched

# -- Parse arguments -----------------------------------------------------------
parser = argparse.ArgumentParser(description='Submit request to SmartCMP')
group = parser.add_mutually_exclusive_group(required=False)
group.add_argument('--file', '-f', help='Path to JSON file containing request body')
group.add_argument('--json', '-j', '--json-body', help='JSON string (avoid in PowerShell)')
args = parser.parse_args()

if not args.file and not args.json:
    print("ERROR: No request body provided.")
    print("You must pass the json_body parameter with the complete request JSON.")
    print('For cloud resources: {"catalogId":"...","catalogName":"Linux VM","userLoginId":"admin","businessGroupName":"ABI","name":"vm-01","resourceSpecs":[{"node":"Compute","type":"cloudchef.nodes.Compute","cpu":2,"memory":4}]}')
    print('For tickets: {"catalogId":"...","catalogName":"ticket","userLoginId":"admin","businessGroupName":"my-group","name":"ticket-title","genericRequest":{"description":"problem description"}}')
    print("FORBIDDEN fields: Do NOT add priority, category, requestor, parameters, impactScope, urgency, contactName, or any field not shown above.")
    print("First show the user a JSON preview, get their confirmation, then call this tool with the json_body parameter set to the confirmed JSON string.")
    sys.exit(0)

# -- Load request body ---------------------------------------------------------
def _sanitize_json_string(s: str) -> str:
    """Replace smart/curly quotes with standard ASCII quotes."""
    return (s
        .replace('\u201c', '"')   # left double curly quote
        .replace('\u201d', '"')   # right double curly quote
        .replace('\u2018', "'")   # left single curly quote
        .replace('\u2019', "'")   # right single curly quote
        .replace('\uff02', '"')   # fullwidth quotation mark
    )

try:
    if args.file:
        with open(args.file, 'r', encoding='utf-8') as f:
            body = json.load(f)
    else:
        raw_json = _sanitize_json_string(args.json)
        body = json.loads(raw_json)
except json.JSONDecodeError as e:
    print(f"[ERROR] Invalid JSON: {e}")
    sys.exit(1)
except FileNotFoundError:
    print(f"[ERROR] File not found: {args.file}")
    sys.exit(1)

body = _enrich_request_body(body)

# -- Normalize resourceSpecs to array -----------------------------------------
# SmartCMP backend expects resourceSpecs as an array (ArrayList<ResourceSpec>).
# LLMs sometimes send it as a single object; wrap it defensively.
if isinstance(body, dict) and "resourceSpecs" in body:
    specs = body["resourceSpecs"]
    if isinstance(specs, dict):
        body["resourceSpecs"] = [specs]

# -- Submit request ------------------------------------------------------------
url = f"{BASE_URL}/generic-request/submit"
headers = create_headers(AUTH_TOKEN)

try:
    resp = requests.post(url, headers=headers, json=body, verify=False, timeout=30)
    result = resp.json()
except requests.exceptions.RequestException as e:
    print(f"[ERROR] Request failed: {e}")
    sys.exit(1)
except json.JSONDecodeError:
    print(f"[ERROR] Invalid response: {resp.text}")
    sys.exit(1)

# -- Output result -------------------------------------------------------------
catalog_name = body.get("catalogName", "")
request_name = body.get("name", "")

if resp.status_code == 200:
    if isinstance(result, list) and result:
        r = result[0]
        req_id = r.get('id', 'N/A')
        state = r.get('state', 'N/A')
        error = r.get('errorMessage', '')
        if error:
            print(f"[FAILED] 提交失败")
            print(f"  Error: {error}")
        else:
            print(f"[SUCCESS] 申请已提交")
            print(f"  Request ID: {req_id}")
            print(f"  State: {state}")
            if catalog_name:
                print(f"  Catalog: {catalog_name}")
            if request_name:
                print(f"  Name: {request_name}")
        # Print remaining items if any
        for r in result[1:]:
            print(f"  ---")
            print(f"  Request ID: {r.get('id', 'N/A')}")
            print(f"  State: {r.get('state', 'N/A')}")
            if r.get('errorMessage'):
                print(f"  Error: {r['errorMessage']}")
    elif isinstance(result, dict):
        if 'id' in result:
            print(f"[SUCCESS] 申请已提交")
            print(f"  Request ID: {result.get('id', 'N/A')}")
            print(f"  State: {result.get('state', 'N/A')}")
            if catalog_name:
                print(f"  Catalog: {catalog_name}")
            if request_name:
                print(f"  Name: {request_name}")
        elif 'message' in result or 'error' in result:
            print(f"[FAILED] 提交失败")
            print(f"  Message: {result.get('message', result.get('error', ''))}")
        else:
            print(f"Status: 200")
            print(f"  Response: {result}")
    else:
        print(f"[SUCCESS] 申请已提交")
else:
    print(f"[FAILED] HTTP {resp.status_code}")
    if isinstance(result, dict):
        print(f"  Message: {result.get('message', result.get('error', json.dumps(result, ensure_ascii=False)))}")
    else:
        print(f"  Response: {result}")
