# -*- coding: utf-8 -*-
"""Query component type information for a given resource type (sourceKey).

Usage:
  python list_components.py <SOURCE_KEY>

Arguments:
  SOURCE_KEY    Resource type key from the selected service card `sourceKey`
                (from list_services.py output / CATALOG_META)

Output:
  ##COMPONENT_META_START## ... ##COMPONENT_META_END##
    JSON object: {sourceKey, typeName, id, name, node, cloudEntryTypeIds, osType}
    - typeName is used as nodeType for list_resource_pools.py
    - osType is read from the component model when available, otherwise inferred
      from typeName ("windows" → Windows, else Linux)

Environment:
  CMP_URL    - Base URL (IP, hostname, or full path; auto-normalized)
  CMP_COOKIE - Session cookie string

Examples:
  python list_components.py resource.iaas.machine.instance.abstract
"""
import os
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

source_key = sys.argv[1] if len(sys.argv) >= 2 else os.environ.get("SOURCE_KEY", "")
if not source_key:
    print("Usage: python list_components.py <SOURCE_KEY>")
    sys.exit(1)

if source_key.startswith("--"):
    print("[ERROR] list_components.py only accepts source_key.")
    print("Pass the selected service card's sourceKey, not catalog_id or CLI flags.")
    sys.exit(1)

if "CATALOG" in source_key.upper() and "." not in source_key:
    print("[ERROR] list_components.py only accepts source_key.")
    print("Do NOT pass catalog_id. Pass the selected service card's sourceKey instead.")
    sys.exit(1)

# ── Query /components ─────────────────────────────────────────────────────────
url = f"{BASE_URL}/components"
try:
    resp = requests.get(url, headers=HEADERS, params={"resourceType": source_key},
                        verify=False, timeout=30)
    resp.raise_for_status()
    if not resp.text.strip():
        print(f"[ERROR] API returned empty response. Status={resp.status_code}")
        sys.exit(1)
    data = resp.json()
except (json.JSONDecodeError, ValueError):
    print(f"[ERROR] API returned invalid JSON. Status={resp.status_code}, Body={resp.text[:200]}")
    sys.exit(1)
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
os_type = model.get("osType", comp.get("osType", ""))
if not os_type:
    lowered_type_name = type_name.lower()
    if "windows" in lowered_type_name:
        os_type = "Windows"
    elif type_name:
        os_type = "Linux"

# Structured block — agent reads this via stderr (not shown to user)
_comp_meta = json.dumps({
    "sourceKey": source_key,
    "typeName": type_name,
    "id": comp_id,
    "name": comp_name,
    "node": node_name,
    "cloudEntryTypeIds": cloud_entry_type_ids,
    "osType": os_type,
}, ensure_ascii=False, separators=(',', ':'))
print("##COMPONENT_META_START##", file=sys.stderr)
print(_comp_meta, file=sys.stderr)
print("##COMPONENT_META_END##", file=sys.stderr)

# Human-readable summary (stdout)
# Keep stdout generic because this lookup is a hidden backend step in request flow.
print("[INFO] Component metadata loaded.")
