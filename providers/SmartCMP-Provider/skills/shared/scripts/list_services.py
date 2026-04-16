# -*- coding: utf-8 -*-
"""List published service catalogs from SmartCMP.

Usage:
  python list_services.py [KEYWORD]

Arguments:
  KEYWORD    Optional filter keyword for catalog name search

Output:
  - Numbered list of catalog names (user-visible)
  - ##CATALOG_META_START## ... ##CATALOG_META_END##
      JSON array: [{index, id, name, sourceKey, serviceCategory, description}, ...]
      Parse silently — do NOT display to user.

      IMPORTANT: Check 'serviceCategory' to determine service type:
        - "GENERIC_SERVICE" → Ticket/Work Order (use manualRequest structure)
        - Others → Cloud Resource (use resourceSpecs structure)

Environment:
  CMP_URL    - Base URL (IP, hostname, or full path; auto-normalized)
  CMP_COOKIE - Session cookie string

Examples:
  python list_services.py              # List all catalogs
  python list_services.py "Linux"      # Filter by keyword
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


def _normalize_param(raw_param: dict) -> dict:
    """Preserve the instruction fields that drive the request workflow."""
    normalized = {
        "key": raw_param.get("key", ""),
        "label": raw_param.get("label") or raw_param.get("key", ""),
        "required": bool(raw_param.get("required", False)),
        "source": raw_param.get("source"),
        "defaultValue": raw_param.get("defaultValue"),
    }

    if raw_param.get("description") is not None:
        normalized["description"] = raw_param.get("description")
    if raw_param.get("type") is not None:
        normalized["type"] = raw_param.get("type")

    return normalized

keyword = sys.argv[1] if len(sys.argv) > 1 else ""
url = f"{BASE_URL}/catalogs/published"
params = {"query": "", "states": "PUBLISHED", "page": 1, "size": 50, "sort": "catalogIndex,asc"}
if keyword:
    params["queryValue"] = keyword
headers = HEADERS

resp = requests.get(url, headers=headers, params=params, verify=False, timeout=30)
if resp.status_code != 200:
    print(f"HTTP {resp.status_code}: {resp.text}")
    sys.exit(1)

result = resp.json()
items = result.get("content", [])
total = result.get("totalElements", len(items))
print(f"Found {total} published catalog(s):\n")

# ── User-visible list (name only) ─────────────────────────────────────────
for i, c in enumerate(items):
    name = c.get("nameZh") or c.get("name", "N/A")
    print(f"  [{i+1}] {name}")
print()
print("请选择您要申请的服务（输入编号）：")
print()

# ── Machine-readable metadata (agent reads silently, do NOT display to user)
# IMPORTANT: Do NOT show this block to user. Parse it silently.
#   - serviceCategory: "GENERIC_SERVICE" = Ticket, others = Cloud Resource
#   - params: normalized instruction parameters for the workflow
meta = []
for i, c in enumerate(items):
    entry = {
        "index": i + 1,
        "id":    c.get("id", ""),
        "name":  c.get("nameZh") or c.get("name", ""),
        "sourceKey":   c.get("sourceKey", ""),
        "serviceCategory": c.get("serviceCategory", ""),
    }
    # Extract normalized instruction parameters from instructions
    raw_instructions = (c.get("instructions") or "").strip()
    if raw_instructions:
        try:
            instr = json.loads(raw_instructions)
            params_list = instr.get("parameters", [])
            if isinstance(params_list, list):
                normalized_params = [_normalize_param(p) for p in params_list if isinstance(p, dict)]
                entry["instructions"] = {"parameters": normalized_params}
                entry["params"] = normalized_params
        except (json.JSONDecodeError, TypeError):
            pass
    meta.append(entry)
_meta_json = json.dumps(meta, ensure_ascii=False, separators=(',', ':'))
print(f"##CATALOG_META_START##", file=sys.stderr)
print(_meta_json, file=sys.stderr)
print(f"##CATALOG_META_END##", file=sys.stderr)
