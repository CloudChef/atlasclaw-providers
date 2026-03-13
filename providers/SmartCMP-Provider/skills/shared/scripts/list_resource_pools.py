"""List available resource pools for a given business group.

Usage:
  python list_resource_pools.py <BUSINESS_GROUP_ID> <SOURCE_KEY> <NODE_TYPE>

Arguments:
  BUSINESS_GROUP_ID    Business group ID from list_business_groups.py
  SOURCE_KEY           Service type key from list_services.py (##CATALOG_META##)
  NODE_TYPE            Component typeName from list_components.py (##COMPONENT_META##)

  ❌ WRONG: list_resource_pools.py <catalogId> <businessGroupId>
  ✓ RIGHT:  list_resource_pools.py <businessGroupId> <sourceKey> <nodeType>

Output:
  - Numbered list of resource pool names (user-visible)
  - ##RESOURCE_POOL_META_START## ... ##RESOURCE_POOL_META_END##
      JSON array: [{index, id, name, cloudEntryTypeId}, ...]
  - ##RESOURCE_POOL_RAW_START## ... ##RESOURCE_POOL_RAW_END##
      Simplified JSON for extra fields

Environment:
  CMP_URL    - Base URL (IP, hostname, or full path; auto-normalized)
  CMP_COOKIE - Session cookie string

Examples:
  python list_resource_pools.py 47673d8d-6b3f-... resource.iaas.machine.instance.abstract cloudchef.nodes.Compute

API Reference:
  GET /resource-bundles?businessGroupId=xxx&componentType=xxx&nodeType=xxx
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

# ── Parse positional arguments (require exactly 3) ───────────────────────────
if len(sys.argv) != 4:
    print("[ERROR] This script requires EXACTLY 3 arguments:")
    print()
    print("  python list_resource_pools.py <ARG1> <ARG2> <ARG3>")
    print()
    print("  ARG1 = businessGroupId   (from list_business_groups.py)")
    print("  ARG2 = componentType     (sourceKey from list_services.py)")
    print("  ARG3 = nodeType          (typeName from list_components.py)")
    print()
    print("Example:")
    print("  python list_resource_pools.py \\")
    print("    47673d8d-6b3f-41e1-8ec0-c37e082d9020 \\")
    print("    resource.iaas.machine.instance.abstract \\")
    print("    cloudchef.nodes.Compute")
    sys.exit(1)

bg_id         = sys.argv[1].strip()
component_type = sys.argv[2].strip()
node_type     = sys.argv[3].strip()

headers = {"Content-Type": "application/json; charset=utf-8", "Cookie": COOKIE}

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

# ── META block (agent reads silently, do NOT display to user) ─────────────────
meta = [
    {
        "index":            i + 1,
        "id":               rb.get("id", ""),
        "name":             rb.get("name", ""),
        "cloudEntryTypeId": rb.get("cloudEntryTypeId", ""),
    }
    for i, rb in enumerate(items)
]
print("##RESOURCE_POOL_META_START##")
print(json.dumps(meta, ensure_ascii=False))
print("##RESOURCE_POOL_META_END##")

# ── RAW block (simplified - only essential fields to reduce output size) ─────
raw_simplified = [
    {
        "id":               rb.get("id", ""),
        "name":             rb.get("name", ""),
        "cloudEntryTypeId": rb.get("cloudEntryTypeId", ""),
        "cloudEntryType":   rb.get("cloudEntryType", ""),
        "enabled":          rb.get("enabled", True),
        "readOnly":         rb.get("readOnly", False),
    }
    for rb in items
]
print("##RESOURCE_POOL_RAW_START##")
print(json.dumps(raw_simplified, ensure_ascii=False))
print("##RESOURCE_POOL_RAW_END##")
