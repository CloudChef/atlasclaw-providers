# -*- coding: utf-8 -*-
"""List available resource pools for a given business group.

Usage:
  python list_resource_pools.py <BUSINESS_GROUP_ID> <SOURCE_KEY> <NODE_TYPE>

Arguments:
  BUSINESS_GROUP_ID    Business group ID from list_business_groups.py
  SOURCE_KEY           Service type key from list_services.py (##CATALOG_META##)
  NODE_TYPE            Component type from the selected catalog instructions
                       (usually instructions.type, e.g. cloudchef.nodes.Compute)

Output:
  - Numbered list of resource pool names (user-visible)
  - ##RESOURCE_POOL_META_START## ... ##RESOURCE_POOL_META_END##
      JSON array: [{index, id, name, cloudEntryTypeId}, ...]

Environment:
  CMP_URL             - Base URL (IP, hostname, or full path; auto-normalized)
  CMP_COOKIE          - Session cookie string
  BUSINESS_GROUP_ID   - (Optional) Business group ID passed from framework
  SOURCE_KEY          - (Optional) Source key passed from framework
  NODE_TYPE           - (Optional) Node type passed from framework

Examples:
  python list_resource_pools.py 47673d8d-... resource.iaas.machine.instance.abstract cloudchef.nodes.Compute

API Reference:
  GET /resource-bundles?businessGroupId=xxx&componentType=xxx&nodeType=xxx
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

# ── Parse arguments: Environment variable > Command line ─────────────────────
bg_id = os.environ.get("BUSINESS_GROUP_ID", "")
component_type = os.environ.get("SOURCE_KEY", "")
node_type = os.environ.get("NODE_TYPE", "")

# Fall back to command line arguments
if not bg_id and len(sys.argv) >= 2:
    bg_id = sys.argv[1].strip()
if not component_type and len(sys.argv) >= 3:
    component_type = sys.argv[2].strip()
if not node_type and len(sys.argv) >= 4:
    node_type = sys.argv[3].strip()

if not bg_id or not component_type or not node_type:
    print("[ERROR] This script requires 3 parameters:")
    print()
    print("  BUSINESS_GROUP_ID - from list_business_groups.py")
    print("  SOURCE_KEY        - from list_services.py (##CATALOG_META##)")
    print("  NODE_TYPE         - from selected catalog instructions.type")
    print()
    print("Usage: python list_resource_pools.py <BG_ID> <SOURCE_KEY> <NODE_TYPE>")
    print("   Or: Set BUSINESS_GROUP_ID, SOURCE_KEY, NODE_TYPE environment variables")
    sys.exit(1)

headers = HEADERS

# ── Query resource pools ──────────────────────────────────────────────────────
url = f"{BASE_URL}/resource-bundles"
params = {
    "businessGroupId":  bg_id,
    "componentType":    component_type,
    "nodeType":         node_type,
    "cloudEntryTypeId": "",
    "enabled":          "true",
    "readOnly":         "false",
    "strategy":         "RB_POLICY_STATIC",
}

try:
    resp = requests.get(url, headers=headers, params=params, verify=False, timeout=30)
    resp.raise_for_status()
    data = resp.json()
except json.JSONDecodeError:
    print(f"[ERROR] API returned invalid JSON. Status={resp.status_code}, Body={resp.text[:200]}")
    sys.exit(1)
except requests.exceptions.RequestException as e:
    print(f"[ERROR] Request failed: {e}")
    sys.exit(1)

# ── Extract list from response ────────────────────────────────────────────────
def _extract_list(d):
    if isinstance(d, list):
        return d
    for key in ("content", "data", "items", "result"):
        if isinstance(d.get(key), list):
            return d[key]
    return []

items = _extract_list(data) if isinstance(data, dict) else (data if isinstance(data, list) else [])

if not items:
    print("No resource pools found for this business group.")
    sys.exit(0)

# ── User-visible list (name only) ─────────────────────────────────────────────
print(f"Found {len(items)} resource pool(s):\n")
for i, rb in enumerate(items):
    name = rb.get("name", "N/A")
    print(f"  [{i+1}] {name}")
print()
print("请选择资源池（输入编号）：")
print()

# ── META block (agent reads silently, do NOT display to user) ─────────────────
_trace_id = os.environ.get("INTERNAL_REQUEST_TRACE_ID", "")
meta = [
    {
        "index":            i + 1,
        "id":               rb.get("id", ""),
        "name":             rb.get("name", ""),
        "cloudEntryTypeId": rb.get("cloudEntryTypeId", ""),
    }
    for i, rb in enumerate(items)
]
_envelope = {"resource_pools": meta}
if _trace_id:
    _envelope["internal_request_trace_id"] = _trace_id
_meta_json = json.dumps(_envelope, ensure_ascii=False, separators=(',', ':'))
print("##RESOURCE_POOL_META_START##", file=sys.stderr)
print(_meta_json, file=sys.stderr)
print("##RESOURCE_POOL_META_END##", file=sys.stderr)

