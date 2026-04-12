# -*- coding: utf-8 -*-
"""Query component type information for a given resource type (sourceKey).

Usage:
  python list_components.py <SOURCE_KEY>

Arguments:
  SOURCE_KEY    Resource type key from list_services.py output (##CATALOG_META##)

Output:
  ##COMPONENT_META_START## ... ##COMPONENT_META_END##
    JSON object: {sourceKey, typeName, id, name}
    - typeName is used as nodeType for list_resource_pools.py
    - Detect osType: "windows" in typeName.lower() → Windows, else Linux

Environment:
  CMP_URL    - Base URL (IP, hostname, or full path; auto-normalized)
  CMP_COOKIE - Session cookie string

Examples:
  python list_components.py resource.iaas.machine.instance.abstract
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

if len(sys.argv) < 2:
    print("Usage: python list_components.py <SOURCE_KEY>")
    sys.exit(1)

source_key = sys.argv[1]

# ── Query /components ─────────────────────────────────────────────────────────
url = f"{BASE_URL}/components"
try:
    resp = requests.get(url, headers=HEADERS, params={"resourceType": source_key},
                        verify=False, timeout=30)
    resp.raise_for_status()
    data = resp.json()
except requests.exceptions.RequestException as e:
    print(f"[ERROR] Request failed: {e}")
    sys.exit(1)

items = data if isinstance(data, list) else \
        data.get("content", data.get("data", data.get("items", [])))

# Fallback: API returned a single component object directly (has "model" field at root)
if not items and isinstance(data, dict) and "model" in data:
    items = [data]

if not items:
    print(f"[INFO] No component found for sourceKey='{source_key}'.")
    sys.exit(0)

comp      = items[0]
model     = comp.get("model", {})
type_name = model.get("typeName", comp.get("typeName", comp.get("type", "")))
comp_id   = comp.get("id", "N/A")
comp_name = comp.get("nameZh") or comp.get("name", "N/A")

# Extract node from typeName (last segment after final dot)
# e.g., "resource.infra.server_room" -> "server_room"
node_name = type_name.rsplit(".", 1)[-1] if type_name else ""

# Get cloudEntryTypeIds (empty string means useResourceBundle: false is required)
cloud_entry_type_ids = model.get("cloudEntryTypeIds", comp.get("cloudEntryTypeIds", ""))

# Structured block FIRST — agent reads this immediately
print("##COMPONENT_META_START##")
print(json.dumps({
    "sourceKey": source_key,
    "typeName": type_name,
    "id": comp_id,
    "name": comp_name,
    "node": node_name,
    "cloudEntryTypeIds": cloud_entry_type_ids
}, ensure_ascii=False))
print("##COMPONENT_META_END##")

# Human-readable summary (after the block, for reference only)
print(f"[INFO] sourceKey={source_key}  typeName={type_name}  id={comp_id}")
