"""List published service catalogs from SmartCMP.

Usage:
  python list_services.py [KEYWORD]

Arguments:
  KEYWORD    Optional filter keyword for catalog name search

Output:
  - Numbered list of catalog names (user-visible)
  - ##CATALOG_META_START## ... ##CATALOG_META_END##
      JSON array: [{index, id, name, sourceKey, description}, ...]
      Parse silently — do NOT display to user.

Environment:
  CMP_URL    - Base URL (IP, hostname, or full path; auto-normalized)
  CMP_COOKIE - Session cookie string

Examples:
  python list_services.py              # List all catalogs
  python list_services.py "Linux"      # Filter by keyword
"""
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

BASE_URL, COOKIE, HEADERS = require_config()

keyword = sys.argv[1] if len(sys.argv) > 1 else ""
url = f"{BASE_URL}/catalogs/published"
params = {"query": "", "states": "PUBLISHED", "page": 1, "size": 50, "sort": "catalogIndex,asc"}
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
print(f"Found {total} published catalog(s):\n")

# ── User-visible list (name only) ─────────────────────────────────────────
for i, c in enumerate(items):
    name = c.get("nameZh") or c.get("name", "N/A")
    print(f"  [{i+1}] {name}")
print()

# ── Machine-readable metadata (agent reads silently, do NOT display to user)
# Contains: id, name, sourceKey, description (from 'instructions' field only)
meta = [
    {
        "index": i + 1,
        "id":    c.get("id", ""),
        "name":  c.get("nameZh") or c.get("name", ""),
        "sourceKey":   c.get("sourceKey", ""),
        "description": (c.get("instructions") or "").strip(),
    }
    for i, c in enumerate(items)
]
print("##CATALOG_META_START##")
print(json.dumps(meta, ensure_ascii=False))
print("##CATALOG_META_END##")
