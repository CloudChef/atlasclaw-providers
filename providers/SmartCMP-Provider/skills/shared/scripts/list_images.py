# -*- coding: utf-8 -*-
"""List available images for a given resource bundle and OS template.

Queries the cloud provider for images filtered by resource bundle and OS template.
The request body is built dynamically from the selected resource pool's
`cloudEntryTypeId`, so the script can work across different cloud platforms
without hardcoding a single provider such as vSphere.

Usage:
  python list_images.py <RESOURCE_BUNDLE_ID> <LOGIC_TEMPLATE_ID> <CLOUD_ENTRY_TYPE_ID>

Arguments:
  RESOURCE_BUNDLE_ID    From list_resource_pools.py ##RESOURCE_POOL_META## (id field)
  LOGIC_TEMPLATE_ID     From list_os_templates.py output ([ID: ...])
  CLOUD_ENTRY_TYPE_ID   From list_resource_pools.py ##RESOURCE_POOL_META## (cloudEntryTypeId)

cloudResourceType Construction:
  - If CLOUD_ENTRY_TYPE_ID already ends with "::images", keep it
  - Otherwise append "::images"

Environment:
  CMP_URL                     - Base URL (IP, hostname, or full path; auto-normalized)
  CMP_COOKIE                  - Session cookie string
  IMAGE_QUERY_LIMIT           - Optional limit override (default: 500)
  IMAGE_QUERY_PROPERTIES_JSON - Optional JSON object merged into queryProperties
  IMAGE_QUERY_BODY_JSON       - Optional JSON object merged into the top-level body

Examples:
  python list_images.py abc123 def456 yacmp:cloudentry:type:vsphere
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


def _load_json_object_from_env(env_name):
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"[ERROR] {env_name} must be a valid JSON object: {exc}")
        sys.exit(1)
    if not isinstance(payload, dict):
        print(f"[ERROR] {env_name} must be a JSON object.")
        sys.exit(1)
    return payload


def _merge_dict(target, overrides):
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge_dict(target[key], value)
            continue
        target[key] = value


def _drop_none_values(value):
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            cleaned_item = _drop_none_values(item)
            if cleaned_item is None:
                continue
            cleaned[key] = cleaned_item
        return cleaned
    if isinstance(value, list):
        cleaned = []
        for item in value:
            cleaned_item = _drop_none_values(item)
            if cleaned_item is None:
                continue
            cleaned.append(cleaned_item)
        return cleaned
    return value


def _build_cloud_resource_type(cloud_entry_type_id):
    normalized = str(cloud_entry_type_id or "").strip()
    if not normalized:
        return ""
    if normalized.lower().endswith("::images"):
        return normalized
    if normalized.startswith("yacmp:cloudentry:type:") or ":" in normalized:
        return f"{normalized}::images"
    return f"yacmp:cloudentry:type:{normalized}::images"

# Priority: Environment variable > Command line argument
resource_bundle_id  = os.environ.get("RESOURCE_BUNDLE_ID", "")
logic_template_id   = os.environ.get("LOGIC_TEMPLATE_ID", "")
cloud_entry_type_id = os.environ.get("CLOUD_ENTRY_TYPE_ID", "")

if not resource_bundle_id and len(sys.argv) >= 2:
    resource_bundle_id = sys.argv[1]
if not logic_template_id and len(sys.argv) >= 3:
    logic_template_id = sys.argv[2]
if not cloud_entry_type_id and len(sys.argv) >= 4:
    cloud_entry_type_id = sys.argv[3]

if not resource_bundle_id or not logic_template_id or not cloud_entry_type_id:
    print("[ERROR] This script requires 3 parameters:")
    print()
    print("  RESOURCE_BUNDLE_ID    - from list_resource_pools.py")
    print("  LOGIC_TEMPLATE_ID     - from list_os_templates.py")
    print("  CLOUD_ENTRY_TYPE_ID   - from list_resource_pools.py (cloudEntryTypeId)")
    print()
    print("Usage: python list_images.py <RESOURCE_BUNDLE_ID> <LOGIC_TEMPLATE_ID> <CLOUD_ENTRY_TYPE_ID>")
    sys.exit(1)
headers = HEADERS

# ── Construct cloudResourceType from cloudEntryTypeId ────────────────────────
cloud_resource_type = _build_cloud_resource_type(cloud_entry_type_id)
if not cloud_resource_type:
    print("[ERROR] Failed to build cloudResourceType from cloudEntryTypeId.")
    sys.exit(1)

query_properties = {
    "resourceBundleId": resource_bundle_id,
    "logicTemplateId": logic_template_id,
    "queryResourceBundle": False,
}
_merge_dict(query_properties, _load_json_object_from_env("IMAGE_QUERY_PROPERTIES_JSON"))
query_properties = _drop_none_values(query_properties)

# ── Build request body ────────────────────────────────────────────────────────
body = {
    "cloudResourceType": cloud_resource_type,
    "cloudEntryId":      None,
    "businessGroupId":   None,
    "queryProperties":   query_properties,
    "limit":             int(os.environ.get("IMAGE_QUERY_LIMIT", "500") or "500"),
}
_merge_dict(body, _load_json_object_from_env("IMAGE_QUERY_BODY_JSON"))
body["queryProperties"] = _drop_none_values(body.get("queryProperties", {}))

url = f"{BASE_URL}/cloudprovider?action=queryCloudResource"
try:
    resp = requests.post(url, headers=headers, json=body, verify=False, timeout=30)
    resp.raise_for_status()
    data = resp.json()
except json.JSONDecodeError:
    print(f"[ERROR] API returned invalid JSON. Status={resp.status_code}, Body={resp.text[:200]}")
    sys.exit(1)
except requests.exceptions.RequestException as e:
    detail = ""
    if "resp" in locals():
        detail = (resp.text or "").strip()[:300]
    if detail:
        print(f"[ERROR] Request failed: {e}. Response={detail}")
    else:
        print(f"[ERROR] Request failed: {e}")
    sys.exit(1)

def _extract_list(d):
    if isinstance(d, list):
        return d
    for key in ("content", "data", "items", "result"):
        if isinstance(d.get(key), list):
            return d[key]
    return []

items = _extract_list(data) if isinstance(data, dict) else (data if isinstance(data, list) else [])

if not items:
    print("[INFO] No images found.")
    sys.exit(0)

# ── User-visible list (name only) ─────────────────────────────────────────────
print(f"Found {len(items)} image(s):\n")
for i, img in enumerate(items, 1):
    name   = img.get("nameZh") or img.get("name") or img.get("imageName") or img.get("id", "Unknown")
    os_ver = img.get("osType") or img.get("osVersion") or img.get("version", "")
    display = f"  [{i}] {name}"
    if os_ver:
        display += f"  ({os_ver})"
    print(display)
print()
print("请选择镜像（输入编号）：")
print()

# ── META block (agent reads silently, do NOT display to user) ─────────────────
meta = [
    {
        "index": i + 1,
        "id":    img.get("id", ""),
        "name":  img.get("nameZh") or img.get("name") or img.get("imageName", ""),
    }
    for i, img in enumerate(items)
]
_meta_json = json.dumps(meta, ensure_ascii=False, separators=(',', ':'))
print("##IMAGE_META_START##", file=sys.stderr)
print(_meta_json, file=sys.stderr)
print("##IMAGE_META_END##", file=sys.stderr)
