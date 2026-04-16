# -*- coding: utf-8 -*-
"""List applications/projects for a business group.

Usage:
  python list_applications.py <BG_ID> [KEYWORD]

Arguments:
  BG_ID      Business group ID from list_business_groups.py
  KEYWORD    Optional filter keyword for application name search

Output:
  - Numbered list of applications (user-visible)
  - ##APPLICATION_META_START## ... ##APPLICATION_META_END##
      JSON array: [{index, id, name, description}, ...]
      Parse silently - do NOT display to user.

Environment:
  CMP_URL             - Base URL (IP, hostname, or full path; auto-normalized)
  CMP_COOKIE          - Session cookie string
  BUSINESS_GROUP_ID   - (Optional) Business group ID passed from framework

Examples:
  python list_applications.py 47673d8d-6b3f-...
  python list_applications.py 47673d8d-6b3f-... "web"
"""
import os
import sys
import json
import requests

# Import shared utilities (handles URL normalization, SSL warnings)
try:
    from _common import require_config
except ImportError:
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _common import require_config

BASE_URL, AUTH_TOKEN, HEADERS, _ = require_config()

BG_ID = os.environ.get("BUSINESS_GROUP_ID", "")
if not BG_ID and len(sys.argv) >= 2:
    BG_ID = sys.argv[1]
keyword = sys.argv[2] if len(sys.argv) > 2 else ""

if not BG_ID:
    print("Usage: python list_applications.py <BG_ID> [KEYWORD]")
    sys.exit(1)
url = f"{BASE_URL}/groups"
params = {"query": "", "topGroup": "true", "businessGroupIds": BG_ID, "page": 1, "size": 50, "sort": "name,asc"}
if keyword:
    params["queryValue"] = keyword

resp = requests.get(url, headers=HEADERS, params=params, verify=False, timeout=30)
if resp.status_code != 200:
    print(f"HTTP {resp.status_code}: {resp.text}")
    sys.exit(1)

result = resp.json()
items = result.get("content", [])
total = result.get("totalElements", len(items))
print(f"Found {total} application(s):\n")
for i, g in enumerate(items):
    name = g.get("name", "N/A")
    print(f"  [{i+1}] {name}")
print()
print("请选择应用（输入编号）：")
print()

meta = [
    {
        "index": i + 1,
        "id": g.get("id", ""),
        "name": g.get("name", ""),
        "description": g.get("description", ""),
    }
    for i, g in enumerate(items)
]
_meta_json = json.dumps(meta, ensure_ascii=False, separators=(',', ':'))
print("##APPLICATION_META_START##", file=sys.stderr)
print(_meta_json, file=sys.stderr)
print("##APPLICATION_META_END##", file=sys.stderr)
