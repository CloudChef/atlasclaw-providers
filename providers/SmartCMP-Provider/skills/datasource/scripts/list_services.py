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
import uuid
import os
import requests

# Import shared utilities (handles URL normalization, SSL warnings)
try:
    from _common import require_config
except ImportError:
    import os
    sys.path.insert(
        0,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared", "scripts"),
    )
    from _common import require_config

BASE_URL, AUTH_TOKEN, HEADERS, _ = require_config()

def _coerce_optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return None


def _resolve_runtime_default_only(raw_param: dict) -> bool:
    for key in ("runtimeDefaultOnly", "runtime_default_only"):
        resolved = _coerce_optional_bool(raw_param.get(key))
        if resolved is not None:
            return resolved

    metadata = raw_param.get("metadata")
    if isinstance(metadata, dict):
        for key in ("runtimeDefaultOnly", "runtime_default_only"):
            resolved = _coerce_optional_bool(metadata.get(key))
            if resolved is not None:
                return resolved

    return False


def _normalize_param(raw_param: dict) -> dict:
    """Preserve the instruction fields that drive the request workflow."""
    key = raw_param.get("key", "")
    default_value = raw_param.get("defaultValue")
    runtime_default_only = (
        _resolve_runtime_default_only(raw_param) and default_value not in (None, "")
    )

    normalized = {
        "key": key,
        "label": raw_param.get("label") or key,
        "required": bool(raw_param.get("required", False)),
        "source": raw_param.get("source"),
        "defaultValue": None if runtime_default_only else default_value,
    }

    if runtime_default_only:
        normalized["runtimeDefaultOnly"] = True

    if raw_param.get("description") is not None:
        normalized["description"] = raw_param.get("description")
    if raw_param.get("type") is not None:
        normalized["type"] = raw_param.get("type")

    return normalized


def _normalize_instructions(raw_instructions: dict) -> dict:
    """Preserve workflow-driving instruction metadata for the request skill."""
    normalized: dict = {}
    for key in ("node", "type", "osType", "cloudEntryTypeIds"):
        value = raw_instructions.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            if not value.strip():
                continue
            normalized[key] = value.strip()
            continue
        normalized[key] = value

    params_list = raw_instructions.get("parameters", [])
    if isinstance(params_list, list):
        normalized_params = [_normalize_param(p) for p in params_list if isinstance(p, dict)]
        normalized["parameters"] = normalized_params

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

# ── Machine-readable metadata (agent reads silently, do NOT display to user)
# IMPORTANT: Do NOT show this block to user. Parse it silently.
#   - serviceCategory: "GENERIC_SERVICE" = Ticket, others = Cloud Resource
#   - params: normalized instruction parameters for the workflow
#   - internal_request_trace_id: unique flow instance ID for this request session

# Generate a new trace ID for this request flow instance
_trace_id = os.environ.get("INTERNAL_REQUEST_TRACE_ID") or f"trace-{uuid.uuid4().hex[:12]}"

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
            if isinstance(instr, dict):
                normalized_instructions = _normalize_instructions(instr)
                if normalized_instructions:
                    entry["instructions"] = normalized_instructions
                    entry["params"] = list(normalized_instructions.get("parameters", []) or [])
                    for key in ("node", "type", "osType", "cloudEntryTypeIds"):
                        value = normalized_instructions.get(key)
                        if value is not None:
                            entry[key] = value
        except (json.JSONDecodeError, TypeError):
            pass
    meta.append(entry)

# ── User-visible output (brief summary only) ─────────────────────────────
# Only print a short summary to stdout. The LLM will format the catalog list
# for the user based on the metadata, applying auto-selection when appropriate.
print(f"Found {total} published catalog(s).")

_envelope = json.dumps({
    "internal_request_trace_id": _trace_id,
    "catalogs": meta,
}, ensure_ascii=False, separators=(',', ':'))
print(f"##CATALOG_META_START##", file=sys.stderr)
print(_envelope, file=sys.stderr)
print(f"##CATALOG_META_END##", file=sys.stderr)
