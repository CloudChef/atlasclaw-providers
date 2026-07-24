# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""List published service catalogs from SmartCMP.

Usage:
  python list_services.py [KEYWORD]
  python list_services.py --catalog-id CATALOG_ID

Arguments:
  KEYWORD       Optional filter keyword for catalog name search
  --catalog-id  Internal exact-ID mode used by the request skill to normalize
                one selected catalog through the catalog-detail endpoint

Output:
  - Numbered list of catalog names (user-visible)
  - ##CATALOG_META_START## ... ##CATALOG_META_END##
      JSON array: [{index, id, name, sourceKey, serviceCategory, description}, ...]
      Parse silently — do NOT display to user.

      IMPORTANT: Check 'serviceCategory' to determine service type:
        - "GENERIC_SERVICE" → Ticket/Work Order (use genericRequest structure)
        - Others → Cloud Resource (use resourceSpecs structure, plus optional root params)

Environment:
  CMP_URL    - Base URL (IP, hostname, or full path; auto-normalized)
  CMP_COOKIE - Session cookie string

Examples:
  python list_services.py              # List all catalogs
  python list_services.py "Linux"      # Filter by keyword
  python list_services.py --catalog-id "catalog-uuid"  # Internal detail lookup
"""
import json
import os
import re
import sys
import uuid
from urllib.parse import quote

import requests
import yaml

# Import shared utilities (handles URL normalization, SSL warnings)
try:
    from _common import request_timeout, render_markdown_table, require_config
except ImportError:
    sys.path.insert(
        0,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared", "scripts"),
    )
    from _common import request_timeout, render_markdown_table, require_config

REQUEST_SCRIPTS_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "request", "scripts")
)
if REQUEST_SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, REQUEST_SCRIPTS_ROOT)

from _request_object_actions import attach_catalog_object_metadata

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


def _default_value(raw_param: dict):
    if "defaultValue" in raw_param:
        return raw_param.get("defaultValue")
    return raw_param.get("default_value")


def _normalize_param(raw_param: dict) -> dict:
    """Preserve generated Markdown fields that drive the request workflow."""
    key = str(raw_param.get("key") or "")
    default_value = _default_value(raw_param)
    runtime_default_only = _resolve_runtime_default_only(raw_param) and default_value not in (None, "")

    normalized = {
        "key": key,
        "label": raw_param.get("label") or key,
        "required": bool(raw_param.get("required", False)),
        "defaultValue": None if runtime_default_only else default_value,
    }

    if runtime_default_only:
        normalized["runtimeDefaultOnly"] = True

    for field in ("description", "type", "when", "ask", "location", "node"):
        if raw_param.get(field) is not None:
            normalized[field] = raw_param.get(field)

    options = raw_param.get("options")
    if isinstance(options, list):
        normalized["options"] = options

    return normalized


def _field_param(field_key: str, raw_field: object, *, location: str, node: str | None = None) -> dict:
    field = dict(raw_field) if isinstance(raw_field, dict) else {}
    field["key"] = field_key
    field["location"] = location
    if node:
        field["node"] = node
    return _normalize_param(field)


def _normalize_resource_specs(raw_specs: object) -> list[dict]:
    """Normalize generated Markdown resource_specs into request metadata."""
    if not isinstance(raw_specs, list):
        return []

    reserved_keys = {
        "node",
        "type",
        "resourceBundleId",
        "resourceBundleParams",
        "resourceBundleTags",
        "params",
        "fields",
    }
    normalized_specs: list[dict] = []
    for raw_spec in raw_specs:
        if not isinstance(raw_spec, dict):
            continue

        node = str(raw_spec.get("node") or "").strip()
        normalized_spec: dict = {}
        if node:
            normalized_spec["node"] = node

        spec_type = raw_spec.get("type")
        if isinstance(spec_type, str) and spec_type.strip():
            normalized_spec["type"] = spec_type.strip()

        resource_bundle_id = raw_spec.get("resourceBundleId")
        if isinstance(resource_bundle_id, dict):
            normalized_spec["resourceBundleId"] = _field_param(
                "resourceBundleId",
                resource_bundle_id,
                location="resourceSpecs",
                node=node,
            )

        resource_bundle_params = raw_spec.get("resourceBundleParams")
        if isinstance(resource_bundle_params, dict):
            normalized_bundle_params: dict = {}
            for param_key, raw_param in resource_bundle_params.items():
                normalized_bundle_params[str(param_key)] = _field_param(
                    str(param_key),
                    raw_param,
                    location="resourceBundleParams",
                    node=node,
                )
            if normalized_bundle_params:
                normalized_spec["resourceBundleParams"] = normalized_bundle_params

        resource_bundle_tags = raw_spec.get("resourceBundleTags")
        if isinstance(resource_bundle_tags, dict):
            normalized_spec["resourceBundleTags"] = _field_param(
                "resourceBundleTags",
                resource_bundle_tags,
                location="resourceBundleTags",
                node=node,
            )

        params = raw_spec.get("params")
        if isinstance(params, dict):
            normalized_params: dict = {}
            for param_key, raw_param in params.items():
                normalized_params[str(param_key)] = _field_param(
                    str(param_key),
                    raw_param,
                    location="params",
                    node=node,
                )
            if normalized_params:
                normalized_spec["params"] = normalized_params

        for field_key, raw_field in raw_spec.items():
            if field_key in reserved_keys or not isinstance(raw_field, dict):
                continue
            normalized_spec[str(field_key)] = _field_param(
                str(field_key),
                raw_field,
                location="resourceSpecFields",
                node=node,
            )

        normalized_specs.append(normalized_spec)

    return normalized_specs


def _normalize_generic_request(raw_generic_request: object) -> dict:
    """Normalize generated Markdown generic_request into ticket request metadata."""
    if not isinstance(raw_generic_request, dict):
        return {}

    normalized: dict = {}
    for field_key, raw_field in raw_generic_request.items():
        field_name = str(field_key)
        if field_name in {"processForm", "process_form"}:
            if not isinstance(raw_field, dict):
                continue
            process_form: dict = {}
            for param_key, raw_param in raw_field.items():
                process_form[str(param_key)] = _field_param(
                    str(param_key),
                    raw_param,
                    location="genericRequest.processForm",
                )
            if process_form:
                normalized["processForm"] = process_form
            continue

        if isinstance(raw_field, dict):
            normalized[field_name] = _field_param(
                field_name,
                raw_field,
                location="genericRequest",
            )

    return normalized


def _normalize_instructions(raw_instructions: dict) -> dict:
    """Preserve generated Markdown instruction metadata for the request skill."""
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

    catalog_metadata = raw_instructions.get("catalog")
    if isinstance(catalog_metadata, dict):
        component_type = catalog_metadata.get("component_type") or catalog_metadata.get("componentType")
        if isinstance(component_type, str) and component_type.strip():
            normalized["componentType"] = component_type.strip()

    root_params = raw_instructions.get("params")
    if isinstance(root_params, dict):
        normalized_root_params: dict = {}
        for param_key, raw_param in root_params.items():
            normalized_root_params[str(param_key)] = _field_param(
                str(param_key),
                raw_param,
                location="rootParams",
            )
        if normalized_root_params:
            normalized["params"] = normalized_root_params

    generic_request = raw_instructions.get("generic_request") or raw_instructions.get("genericRequest")
    normalized_generic_request = _normalize_generic_request(generic_request)
    if normalized_generic_request:
        normalized["genericRequest"] = normalized_generic_request

    resource_specs = _normalize_resource_specs(
        raw_instructions.get("resource_specs") or raw_instructions.get("resourceSpecs")
    )
    if resource_specs:
        normalized["resourceSpecs"] = resource_specs
        if "node" not in normalized and resource_specs[0].get("node"):
            normalized["node"] = resource_specs[0]["node"]
        if "type" not in normalized and resource_specs[0].get("type"):
            normalized["type"] = resource_specs[0]["type"]
    top_level_required = raw_instructions.get("top_level_required") or raw_instructions.get("topLevelRequired")
    if isinstance(top_level_required, list):
        normalized["topLevelRequired"] = [v for v in top_level_required if isinstance(v, str) and v.strip()]

    top_level_fields = raw_instructions.get("top_level_fields") or raw_instructions.get("topLevelFields")
    if isinstance(top_level_fields, dict):
        normalized_top_level_fields: dict = {}
        for field_key, raw_field in top_level_fields.items():
            normalized_top_level_fields[str(field_key)] = _field_param(
                str(field_key),
                raw_field,
                location="topLevel",
            )
        if normalized_top_level_fields:
            normalized["topLevelFields"] = normalized_top_level_fields

    return normalized


def _add_request_instruction_section(normalized: dict, raw_instructions_text: str) -> None:
    """Attach only the request instruction section to normalized metadata."""
    request_section = _extract_markdown_section(raw_instructions_text, "# Request Instructions")
    if request_section:
        normalized["requestInstructions"] = request_section


def _extract_markdown_section(markdown_text: str, heading: str) -> str:
    """Extract one top-level Markdown section by exact heading."""
    lines = markdown_text.splitlines()
    start_index = -1
    for index, line in enumerate(lines):
        if line.strip().lstrip("\ufeff") == heading:
            start_index = index + 1
            break
    if start_index == -1:
        return ""

    section_lines: list[str] = []
    for line in lines[start_index:]:
        if line.startswith("# "):
            break
        section_lines.append(line)
    return "\n".join(section_lines).strip()


def _strip_markdown_code_fence(section_text: str) -> str:
    """Strip an optional fenced code block around section content."""
    lines = section_text.strip().splitlines()
    if not lines:
        return ""
    if lines[0].strip().startswith("```"):
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_markdown_instructions(raw_instructions: str) -> dict | None:
    parameter_section = _extract_markdown_section(raw_instructions, "# Request Parameter Instructions")
    yaml_text = _strip_markdown_code_fence(parameter_section)
    if not yaml_text:
        return None
    try:
        parsed = yaml.safe_load(yaml_text)
    except (TypeError, ValueError, yaml.YAMLError):
        return None
    return parsed if isinstance(parsed, dict) else None


_NODE_TEMPLATE_PATTERN = re.compile(r"^\s{2}([A-Za-z0-9_.-]+):\s*$")
_NODE_TYPE_PATTERN = re.compile(r"^\s{4}type:\s*[\"']?([^\"'\s]+)[\"']?\s*$")


def _iter_blueprint_yaml(raw_catalog: dict):
    blueprint = raw_catalog.get("blueprint")
    if not isinstance(blueprint, dict):
        return
    for key in ("mainYaml", "toscaYaml", "originalToscaYaml", "plannedMainYaml", "bpYaml"):
        value = blueprint.get(key)
        if isinstance(value, str) and value.strip():
            yield value


def _extract_node_types_from_yaml(yaml_text: str) -> list[tuple[str, str]]:
    nodes: list[tuple[str, str]] = []
    current_node = ""
    in_node_templates = False

    for line in yaml_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped == "node_templates:":
            in_node_templates = True
            current_node = ""
            continue

        if not in_node_templates:
            continue

        if line and not line.startswith(" "):
            in_node_templates = False
            current_node = ""
            continue

        node_match = _NODE_TEMPLATE_PATTERN.match(line)
        if node_match:
            current_node = node_match.group(1)
            continue

        type_match = _NODE_TYPE_PATTERN.match(line)
        if current_node and type_match:
            node_type = type_match.group(1).strip()
            if node_type.startswith("cloudchef.nodes."):
                nodes.append((current_node, node_type))

    return nodes


def _derive_blueprint_resource_type(raw_catalog: dict) -> dict:
    for yaml_text in _iter_blueprint_yaml(raw_catalog) or ():
        nodes = _extract_node_types_from_yaml(yaml_text)
        if not nodes:
            continue
        for node_name, node_type in nodes:
            if node_type == "cloudchef.nodes.Compute":
                return {"node": node_name, "type": node_type}
        node_name, node_type = nodes[0]
        return {"node": node_name, "type": node_type}
    return {}


keyword = ""
exact_catalog_id = ""
if len(sys.argv) > 1 and sys.argv[1] == "--catalog-id":
    exact_catalog_id = sys.argv[2].strip() if len(sys.argv) > 2 else ""
    if not exact_catalog_id:
        print("[ERROR] Missing catalog ID for --catalog-id.")
        sys.exit(1)
elif len(sys.argv) > 1:
    keyword = sys.argv[1]

if exact_catalog_id:
    url = f"{BASE_URL}/catalogs/{quote(exact_catalog_id, safe='')}"
    params = None
else:
    url = f"{BASE_URL}/catalogs/published/simples"
    params = {
        "query": "",
        "states": "PUBLISHED",
        "page": 1,
        "size": 50,
        "sort": "catalogIndex,asc",
    }
    if keyword:
        params["queryValue"] = keyword
headers = HEADERS

try:
    resp = requests.get(url, headers=headers, params=params, verify=False, timeout=request_timeout())
except requests.exceptions.ReadTimeout:
    print(f"[ERROR] SmartCMP catalog lookup timed out after {request_timeout()} seconds.")
    sys.exit(1)
except requests.exceptions.RequestException as exc:
    print(f"[ERROR] SmartCMP catalog lookup failed: {exc}")
    sys.exit(1)

if resp.status_code != 200:
    print(f"[ERROR] SmartCMP catalog lookup failed: HTTP {resp.status_code}: {resp.text}")
    sys.exit(1)

try:
    result = resp.json()
except ValueError:
    print("[ERROR] SmartCMP catalog lookup returned invalid JSON.")
    sys.exit(1)
if exact_catalog_id:
    if not isinstance(result, dict):
        print("[ERROR] SmartCMP catalog detail must be a JSON object.")
        sys.exit(1)
    returned_catalog_id = str(result.get("id") or "").strip()
    if returned_catalog_id != exact_catalog_id:
        print(
            "[ERROR] SmartCMP catalog detail returned a different catalog ID: "
            f"{returned_catalog_id or '<missing>'}."
        )
        sys.exit(1)
    items = [result]
    total = 1
else:
    items = result.get("content", [])
    total = result.get("totalElements", len(items))

# ── Machine-readable metadata (agent reads silently, do NOT display to user)
# IMPORTANT: Do NOT show this block to user. Parse it silently.
#   - serviceCategory: "GENERIC_SERVICE" = Ticket, others = Cloud Resource
#   - instructions: normalized generated Markdown metadata for the workflow
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
    catalog_type = c.get("type")
    if catalog_type:
        entry["catalogType"] = catalog_type

    is_generic_service = str(entry.get("serviceCategory") or "").upper() == "GENERIC_SERVICE"
    derived_resource_type = {} if is_generic_service else _derive_blueprint_resource_type(c)
    # Extract normalized generated Markdown instructions from catalog instructions.
    raw_instructions = (c.get("instructions") or "").strip()
    if raw_instructions:
        instr = _parse_markdown_instructions(raw_instructions)
        if isinstance(instr, dict):
            normalized_instructions = _normalize_instructions(instr)
            _add_request_instruction_section(normalized_instructions, raw_instructions)
            if normalized_instructions:
                entry["instructions"] = normalized_instructions
                for key in ("node", "type", "osType", "cloudEntryTypeIds", "componentType"):
                    value = normalized_instructions.get(key)
                    if value is not None:
                        entry[key] = value

    for key in ("node", "type"):
        if key not in entry and derived_resource_type.get(key):
            entry[key] = derived_resource_type[key]
    if exact_catalog_id:
        status = str(c.get("status") or c.get("state") or "").strip()
        if status:
            entry["status"] = status
    else:
        # The published-list endpoint is the authoritative proof that the
        # Request action is currently available.
        entry["status"] = "PUBLISHED"
    meta.append(
        attach_catalog_object_metadata(
            entry,
            base_url=BASE_URL,
        )
    )

# ── User-visible output ──────────────────────────────────────────────────
print(
    render_markdown_table(
        f"Found {total} published catalog(s):",
        ["#", "Name", "Service Category", "Source Key"],
        [
            [
                item["index"],
                item.get("name") or "",
                item.get("serviceCategory") or "",
                item.get("sourceKey") or "",
            ]
            for item in meta
        ],
    )
)

_envelope = json.dumps({
    "internal_request_trace_id": _trace_id,
    "catalogs": meta,
}, ensure_ascii=False, separators=(',', ':'))
print(f"##CATALOG_META_START##", file=sys.stderr)
print(_envelope, file=sys.stderr)
print(f"##CATALOG_META_END##", file=sys.stderr)
