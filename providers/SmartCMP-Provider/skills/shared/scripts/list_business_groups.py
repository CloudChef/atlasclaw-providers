"""List available business groups for a catalog.

Usage:
  python list_business_groups.py <CATALOG_ID>

Arguments:
  CATALOG_ID    Catalog ID from list_services.py output (##CATALOG_META##)

Output:
  - Numbered list of business groups with IDs (user-visible)

Environment:
  CMP_URL    - Base URL (IP, hostname, or full path; auto-normalized)
  CMP_COOKIE - Session cookie string

Examples:
  python list_business_groups.py abc123-def456
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
    print("Usage: python scripts/datasource/list_business_groups.py <CATALOG_ID>")
    sys.exit(1)

CATALOG_ID = sys.argv[1]
url = f"{BASE_URL}/catalogs/{CATALOG_ID}/available-bgs"
headers = {"Content-Type": "application/json; charset=utf-8", "Cookie": COOKIE}

resp = requests.get(url, headers=headers, verify=False, timeout=30)
if resp.status_code != 200:
    print(f"HTTP {resp.status_code}: {resp.text}")
    sys.exit(1)

result = resp.json()
items = result if isinstance(result, list) else result.get("content", [])
print(f"Found {len(items)} business group(s):\n")
for i, bg in enumerate(items):
    name = bg.get("name", "N/A")
    bid = bg.get("id", "N/A")
    print(f"  [{i+1}] {name} (id: {bid})")
