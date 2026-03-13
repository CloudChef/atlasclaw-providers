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
import argparse
import requests

# Import shared utilities (handles URL normalization, SSL warnings)
try:
    from _common import require_config
except ImportError:
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared', 'scripts'))
    from _common import require_config

BASE_URL, COOKIE, HEADERS = require_config()

# ── Parse arguments ───────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description='Submit request to SmartCMP')
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument('--file', '-f', help='Path to JSON file containing request body')
group.add_argument('--json', '-j', help='JSON string (avoid in PowerShell)')
args = parser.parse_args()

# ── Load request body ─────────────────────────────────────────────────────────
try:
    if args.file:
        with open(args.file, 'r', encoding='utf-8') as f:
            body = json.load(f)
    else:
        body = json.loads(args.json)
except json.JSONDecodeError as e:
    print(f"[ERROR] Invalid JSON: {e}")
    sys.exit(1)
except FileNotFoundError:
    print(f"[ERROR] File not found: {args.file}")
    sys.exit(1)

# ── Submit request ────────────────────────────────────────────────────────────
url = f"{BASE_URL}/generic-request/submit"
headers = {
    "Content-Type": "application/json; charset=utf-8",
    "Cookie": COOKIE
}

try:
    resp = requests.post(url, headers=headers, json=body, verify=False, timeout=30)
    result = resp.json()
except requests.exceptions.RequestException as e:
    print(f"[ERROR] Request failed: {e}")
    sys.exit(1)
except json.JSONDecodeError:
    print(f"[ERROR] Invalid response: {resp.text}")
    sys.exit(1)

# ── Output result ─────────────────────────────────────────────────────────────
print(f"Status: {resp.status_code}")

if isinstance(result, list):
    for r in result:
        req_id = r.get('id', 'N/A')
        state = r.get('state', 'N/A')
        error = r.get('errorMessage', '')
        print(f"  Request ID: {req_id}")
        print(f"  State: {state}")
        if error:
            print(f"  Error: {error}")
        print()
elif isinstance(result, dict):
    if 'id' in result:
        print(f"  Request ID: {result.get('id', 'N/A')}")
        print(f"  State: {result.get('state', 'N/A')}")
    if 'message' in result or 'error' in result:
        print(f"  Message: {result.get('message', result.get('error', ''))}")
else:
    print(f"  Response: {result}")
