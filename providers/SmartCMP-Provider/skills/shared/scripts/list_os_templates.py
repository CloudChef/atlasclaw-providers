# -*- coding: utf-8 -*-
"""List available OS templates (logic templates) for a given resource bundle.

Usage:
  python list_os_templates.py <OS_TYPE> <RESOURCE_BUNDLE_ID>

Arguments:
  OS_TYPE              "Linux" or "Windows" (determined by caller from typeName)
  RESOURCE_BUNDLE_ID   Resource bundle ID from list_resource_pools.py

Output:
  - Numbered list of OS templates with IDs and versions (user-visible)
  - ##OS_TEMPLATE_META_START## ... ##OS_TEMPLATE_META_END##
      JSON array: [{index, id, name}, ...]
      Parse silently - do NOT display to user.

Environment:
  CMP_URL             - Base URL (IP, hostname, or full path; auto-normalized)
  CMP_COOKIE          - Session cookie string
  OS_TYPE             - (Optional) Operating system type passed from framework
  RESOURCE_BUNDLE_ID  - (Optional) Resource bundle ID passed from framework

Examples:
  python list_os_templates.py Linux abc123-def456
  python list_os_templates.py Windows abc123-def456
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
os_type = os.environ.get("OS_TYPE", "")
resource_bundle_id = os.environ.get("RESOURCE_BUNDLE_ID", "")

if not os_type and len(sys.argv) >= 2:
    os_type = sys.argv[1]
if not resource_bundle_id and len(sys.argv) >= 3:
    resource_bundle_id = sys.argv[2]

if not os_type or not resource_bundle_id:
    print("[ERROR] This script requires 2 parameters:")
    print()
    print("  OS_TYPE            - 'Linux' or 'Windows'")
    print("  RESOURCE_BUNDLE_ID - from list_resource_pools.py (##RESOURCE_POOL_META##)")
    print()
    print("Usage: python list_os_templates.py <OS_TYPE> <RESOURCE_BUNDLE_ID>")
    print("   Or: Set OS_TYPE and RESOURCE_BUNDLE_ID environment variables")
    sys.exit(1)

headers = {"Cookie": COOKIE}

# ── Query logic templates ─────────────────────────────────────────────────────
url = f"{BASE_URL}/logic-templates/search?expand&osType={os_type}&resourceBundleId={resource_bundle_id}"
try:
    resp = requests.get(url, headers=headers, verify=False, timeout=30)
    resp.raise_for_status()
    data = resp.json()
except requests.exceptions.RequestException as e:
    print(f"[ERROR] Request failed: {e}")
    sys.exit(1)

templates = data if isinstance(data, list) else data.get("content", data.get("data", []))

print(f"\nOS Templates  (osType={os_type}, resourceBundleId={resource_bundle_id})")
print("=" * 60)

if not templates:
    print("[INFO] No OS templates found.")
    sys.exit(0)

for i, t in enumerate(templates, 1):
    name    = t.get("nameZh") or t.get("name") or t.get("templateName", "Unknown")
    eng     = t.get("name", "")
    tid     = t.get("id", "N/A")
    os_ver  = t.get("osVersion") or t.get("version", "")
    display = f"  [{i}] {name}"
    if eng and eng != name:
        display += f"  ({eng})"
    if os_ver:
        display += f"  v{os_ver}"
    display += f"  [ID: {tid}]"
    print(display)

print()

# -- META block (agent reads silently, do NOT display to user) -----------------
meta = [
    {
        "index": i + 1,
        "id":    t.get("id", ""),
        "name":  t.get("nameZh") or t.get("name") or t.get("templateName", ""),
    }
    for i, t in enumerate(templates)
]
print("##OS_TEMPLATE_META_START##")
print(json.dumps(meta, ensure_ascii=False))
print("##OS_TEMPLATE_META_END##")
