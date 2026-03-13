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
import requests

# Import shared utilities (handles URL normalization, SSL warnings)
try:
    from _common import require_config
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _common import require_config

BASE_URL, COOKIE, HEADERS = require_config()

# Priority: Environment variable > Command line argument
CATALOG_ID = os.environ.get("CATALOG_ID", "")
if not CATALOG_ID and len(sys.argv) >= 2:
    CATALOG_ID = sys.argv[1]

if not CATALOG_ID:
    print("[ERROR] CATALOG_ID is required.")
    print()
    print("Usage: python list_business_groups.py <CATALOG_ID>")
    print("   Or: Set CATALOG_ID environment variable")
    print()
    print("Get CATALOG_ID from: python list_services.py -> ##CATALOG_META##")
    sys.exit(1)
url = f"{BASE_URL}/catalogs/{CATALOG_ID}/available-bgs"
headers = {"Content-Type": "application/json; charset=utf-8", "Cookie": COOKIE}

resp = requests.get(url, headers=headers, verify=False, timeout=30)
if resp.status_code != 200:
    print(f"HTTP {resp.status_code}: {resp.text}")
    sys.exit(1)

result = resp.json()
items = result if isinstance(result, list) else result.get("content", [])

# -- User-visible list ---------------------------------------------------------
print(f"Found {len(items)} business group(s):\n")
for i, bg in enumerate(items):
    name = bg.get("name", "N/A")
    bid = bg.get("id", "N/A")
    print(f"  [{i+1}] {name} (id: {bid})")
print()

# -- META block (agent reads silently, do NOT display to user) -----------------
meta = [
    {
        "index": i + 1,
        "id":    bg.get("id", ""),
        "name":  bg.get("name", ""),
    }
    for i, bg in enumerate(items)
]
print("##BG_META_START##")
print(json.dumps(meta, ensure_ascii=False))
print("##BG_META_END##")
