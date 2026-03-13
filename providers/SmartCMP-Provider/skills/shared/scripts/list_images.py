"""List available images for a given resource bundle and OS template.

Queries the cloud provider for images filtered by resource bundle and OS template type.
Only supports PRIVATE_CLOUD resource bundles. For PUBLIC_CLOUD, handle manually.

Usage:
  python list_images.py <RESOURCE_BUNDLE_ID> <LOGIC_TEMPLATE_ID> <CLOUD_ENTRY_TYPE_ID>

Arguments:
  RESOURCE_BUNDLE_ID    From list_resource_pools.py ##RESOURCE_POOL_META## (id field)
  LOGIC_TEMPLATE_ID     From list_os_templates.py output ([ID: ...])
  CLOUD_ENTRY_TYPE_ID   From list_resource_pools.py ##RESOURCE_POOL_META## (cloudEntryTypeId)

cloudResourceType Construction:
  - If CLOUD_ENTRY_TYPE_ID contains "generic-cloud"
    → cloudResourceType = "yacmp:cloudentry:type:generic-cloud::images"
  - Otherwise
    → cloudResourceType = "<CLOUD_ENTRY_TYPE_ID>::images"

Output:
  - Numbered list of images with IDs and OS info (user-visible)

Environment:
  CMP_URL    - Base URL (IP, hostname, or full path; auto-normalized)
  CMP_COOKIE - Session cookie string

Examples:
  python list_images.py abc123 def456 yacmp:cloudentry:type:vsphere
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

if len(sys.argv) < 4:
    print("Usage: python list_images.py <RESOURCE_BUNDLE_ID> <LOGIC_TEMPLATE_ID> <CLOUD_ENTRY_TYPE_ID>")
    sys.exit(1)

resource_bundle_id  = sys.argv[1]
logic_template_id   = sys.argv[2]
cloud_entry_type_id = sys.argv[3]
headers = {"Content-Type": "application/json; charset=utf-8", "Cookie": COOKIE}

# ── Construct cloudResourceType from cloudEntryTypeId ────────────────────────
if "generic-cloud" in cloud_entry_type_id.lower():
    cloud_resource_type = "yacmp:cloudentry:type:generic-cloud::images"
else:
    cloud_resource_type = f"{cloud_entry_type_id}::images"

# ── Build request body ────────────────────────────────────────────────────────
body = {
    "cloudResourceType": cloud_resource_type,
    "cloudEntryId":      None,
    "businessGroupId":   None,
    "queryProperties": {
        "resourceBundleId":    resource_bundle_id,
        "logicTemplateId":     logic_template_id,
        "queryResourceBundle": False,
        "instanceType":        None,
    },
    "limit": 500,
}

url = f"{BASE_URL}/cloudprovider?action=queryCloudResource"
try:
    resp = requests.post(url, headers=headers, json=body, verify=False, timeout=30)
    resp.raise_for_status()
    data = resp.json()
except requests.exceptions.RequestException as e:
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

print(f"\nImages  (cloudResourceType={cloud_resource_type})")
print("=" * 60)

if not items:
    print("[INFO] No images found.")
    sys.exit(0)

for i, img in enumerate(items, 1):
    name   = img.get("nameZh") or img.get("name") or img.get("imageName") or img.get("id", "Unknown")
    img_id = img.get("id", "N/A")
    os_ver = img.get("osType") or img.get("osVersion") or img.get("version", "")
    display = f"  [{i}] {name}  [ID: {img_id}]"
    if os_ver:
        display += f"  [{os_ver}]"
    print(display)

print()
