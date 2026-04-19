# -*- coding: utf-8 -*-
"""List SmartCMP business groups from the standalone UI directory endpoint.

Usage:
  python list_all_business_groups.py [QUERY_VALUE]

Arguments:
  QUERY_VALUE   Optional keyword filter. Omit to list all business groups.

Environment:
  QUERY_VALUE   Optional keyword filter supplied by the framework

Output:
  - Numbered list of business-group names (user-visible)
  - ##BUSINESS_GROUP_DIRECTORY_META_START## ... ##BUSINESS_GROUP_DIRECTORY_META_END##
      JSON array: [{index, id, name, code}, ...]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

import requests


SCRIPT_DIR = Path(__file__).resolve().parent
SHARED_SCRIPTS_DIR = SCRIPT_DIR.parents[1] / "shared" / "scripts"
if str(SHARED_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPTS_DIR))

from _common import require_config  # noqa: E402


BASE_URL, _AUTH_TOKEN, HEADERS, _ = require_config()


def _extract_list(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("content", "data", "items", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def _display_name(item: dict) -> str:
    return (
        item.get("name")
        or item.get("nameZh")
        or item.get("displayName")
        or item.get("label")
        or "N/A"
    )


query_value = os.environ.get("QUERY_VALUE", "")
if not query_value and len(sys.argv) >= 2:
    query_value = sys.argv[1].strip()

encoded_query_value = quote(query_value, safe="")
url = (
    f"{BASE_URL}/business-groups/has-update-permission"
    f"?query&sort=updatedDate%2Cdesc&page=1&size=65535&queryValue={encoded_query_value}"
)

try:
    response = requests.get(url, headers=HEADERS, verify=False, timeout=30)
    response.raise_for_status()
    payload = response.json()
except json.JSONDecodeError:
    print(
        f"[ERROR] API returned invalid JSON. Status={response.status_code}, "
        f"Body={response.text[:200]}"
    )
    sys.exit(1)
except requests.RequestException as exc:
    print(f"[ERROR] Request failed: {exc}")
    sys.exit(1)

items = _extract_list(payload)
if not items:
    print("No business groups found.")
    sys.exit(0)

print(f"Found {len(items)} business group(s):\n")
for index, item in enumerate(items, start=1):
    print(f"  [{index}] {_display_name(item)}")
print()

meta = [
    {
        "index": index,
        "id": item.get("id", ""),
        "name": _display_name(item),
        "code": item.get("code", ""),
    }
    for index, item in enumerate(items, start=1)
]
print("##BUSINESS_GROUP_DIRECTORY_META_START##", file=sys.stderr)
print(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
print("##BUSINESS_GROUP_DIRECTORY_META_END##", file=sys.stderr)
