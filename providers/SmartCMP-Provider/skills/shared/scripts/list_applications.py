"""List applications/projects for a business group.

Usage:
  python list_applications.py <BG_ID> [KEYWORD]

Arguments:
  BG_ID      Business group ID from list_business_groups.py
  KEYWORD    Optional filter keyword for application name search

Output:
  - Numbered list of applications with IDs and descriptions (user-visible)

Environment:
  CMP_URL    - Base URL (IP, hostname, or full path; auto-normalized)
  CMP_COOKIE - Session cookie string

Examples:
  python list_applications.py 47673d8d-6b3f-...
  python list_applications.py 47673d8d-6b3f-... "web"
"""
import sys
import requests

# Import shared utilities (handles URL normalization, SSL warnings)
try:
    from _common import require_config
except ImportError:
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _common import require_config

BASE_URL, COOKIE, HEADERS = require_config()

if len(sys.argv) < 2:
    print("Usage: python list_applications.py <BG_ID> [KEYWORD]")
    sys.exit(1)

BG_ID = sys.argv[1]
keyword = sys.argv[2] if len(sys.argv) > 2 else ""
url = f"{BASE_URL}/groups"
params = {"query": "", "topGroup": "true", "businessGroupIds": BG_ID, "page": 1, "size": 50, "sort": "name,asc"}
if keyword:
    params["queryValue"] = keyword
headers = {"Content-Type": "application/json; charset=utf-8", "Cookie": COOKIE}

resp = requests.get(url, headers=headers, params=params, verify=False, timeout=30)
if resp.status_code != 200:
    print(f"HTTP {resp.status_code}: {resp.text}")
    sys.exit(1)

result = resp.json()
items = result.get("content", [])
total = result.get("totalElements", len(items))
print(f"Found {total} application(s):\n")
for i, g in enumerate(items):
    name = g.get("name", "N/A")
    gid = g.get("id", "N/A")
    desc = g.get("description", "")
    print(f"  [{i+1}] {name} (id: {gid})")
    if desc:
        print(f"      Description: {desc[:80]}")
