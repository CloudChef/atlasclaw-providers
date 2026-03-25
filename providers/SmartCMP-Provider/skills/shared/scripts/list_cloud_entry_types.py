# -*- coding: utf-8 -*-
"""List all cloud entry types for the current tenant.

Usage:
  python list_cloud_entry_types.py

Arguments:
  No positional arguments required.

Output:
  - Numbered list of cloud entry types with IDs and groups (user-visible)
  - ##CLOUD_ENTRY_TYPES_META_START## ... ##CLOUD_ENTRY_TYPES_META_END##
      JSON array: [{id, name, group}, ...]
      group values: "PUBLIC_CLOUD" | "PRIVATE_CLOUD"

Environment:
  CMP_URL    - Base URL (IP, hostname, or full path; auto-normalized)
  CMP_COOKIE - Session cookie string

Examples:
  python list_cloud_entry_types.py
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

BASE_URL, AUTH_TOKEN, HEADERS, _ = require_config()

headers = {"CloudChef-Authenticate": AUTH_TOKEN}
url = f"{BASE_URL}/cloudentry-types/list_cloud_entry_types?queryByCurrentTenant"

try:
    resp = requests.get(url, headers=headers, verify=False, timeout=30)
    resp.raise_for_status()
    data = resp.json()
except requests.exceptions.RequestException as e:
    print(f"[ERROR] Request failed: {e}")
    sys.exit(1)

items = data if isinstance(data, list) else data.get("content", data.get("data", []))

if not items:
    print("[INFO] No cloud entry types found.")
    sys.exit(0)

print(f"\nFound {len(items)} cloud entry type(s):\n")
for i, ct in enumerate(items, 1):
    name  = ct.get("nameZh") or ct.get("name", "Unknown")
    cid   = ct.get("id", "N/A")
    group = ct.get("group", "")
    print(f"  [{i}] {name}  [ID: {cid}]  [Group: {group}]")

print()

# Machine-readable META block — used by agent to check PUBLIC/PRIVATE group
meta = [
    {
        "id":    ct.get("id"),
        "name":  ct.get("nameZh") or ct.get("name", ""),
        "group": ct.get("group", ""),
    }
    for ct in items
]
print("##CLOUD_ENTRY_TYPES_META_START##")
print(json.dumps(meta, ensure_ascii=False))
print("##CLOUD_ENTRY_TYPES_META_END##")
