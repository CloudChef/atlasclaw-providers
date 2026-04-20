# -*- coding: utf-8 -*-
"""List available business groups for a catalog.

Usage:
  python list_business_groups.py <CATALOG_ID>

Arguments:
  CATALOG_ID    Catalog ID from list_services.py output (##CATALOG_META##)

Output:
  - Numbered list of business groups with IDs (user-visible)
  - ##BG_META_START## ... ##BG_META_END##
      JSON array: [{index, id, name}, ...]
      Parse silently - do NOT display to user.

Environment:
  CMP_URL       - Base URL (IP, hostname, or full path; auto-normalized)
  CMP_COOKIE    - Session cookie string
  CATALOG_ID    - (Optional) Catalog ID passed from framework

Examples:
  python list_business_groups.py abc123-def456
"""
import os
import sys
import json
import base64
import requests

# Import shared utilities (handles URL normalization, SSL warnings)
try:
    from _common import require_config
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _common import require_config

BASE_URL, AUTH_TOKEN, HEADERS, _ = require_config()

# Priority: Environment variable > Command line argument
CATALOG_ID = os.environ.get("CATALOG_ID", "")
if not CATALOG_ID and len(sys.argv) >= 2:
    CATALOG_ID = sys.argv[1]

if CATALOG_ID:
    url = f"{BASE_URL}/catalogs/{CATALOG_ID}/available-bgs"
else:
    # Fallback: list all business groups when catalog_id is not provided
    url = f"{BASE_URL}/business-groups"
    import sys as _sys
    print("[WARN] No CATALOG_ID provided, listing all business groups.", file=_sys.stderr)

resp = requests.get(url, headers=HEADERS, verify=False, timeout=30)
if resp.status_code != 200:
    print(f"HTTP {resp.status_code}: {resp.text}")
    sys.exit(1)

result = resp.json()
items = result if isinstance(result, list) else result.get("content", [])

# -- User-visible list ---------------------------------------------------------
print(f"Found {len(items)} business group(s):\n")
for i, bg in enumerate(items):
    name = bg.get("name", "N/A")
    print(f"  [{i+1}] {name}")
print()
print("请选择业务组（输入编号）：")
print()

# -- META block (agent reads silently, do NOT display to user) -----------------
_trace_id = os.environ.get("INTERNAL_REQUEST_TRACE_ID", "")
meta = [
    {
        "index": i + 1,
        "id":    bg.get("id", ""),
        "name":  bg.get("name", ""),
    }
    for i, bg in enumerate(items)
]
_envelope = {"business_groups": meta}
if _trace_id:
    _envelope["internal_request_trace_id"] = _trace_id
_meta_json = json.dumps(_envelope, ensure_ascii=False, separators=(',', ':'))
print("##BG_META_START##", file=sys.stderr)
print(_meta_json, file=sys.stderr)
print("##BG_META_END##", file=sys.stderr)
