# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Get SmartCMP catalog detail by catalog ID.

Usage:
  python get_catalog_detail.py <catalog_id>

Output:
  - Human-readable catalog summary
  - ##CATALOG_DETAIL_META_START## ... ##CATALOG_DETAIL_META_END##
      JSON object with structured catalog info for agent processing
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

import requests
try:
    import yaml
except ImportError:
    yaml = None

try:
    from _common import require_config
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _common import require_config


BASE_URL, AUTH_TOKEN, HEADERS, _ = require_config()

_PREAPPROVAL_HEADINGS = (
    "# Pre Approval Instructions",
    "# Preapproval Instructions",
    "# Pre-Approval Instructions",
)
_REQUEST_PARAMETER_HEADINGS = ("# Request Parameter Instructions",)
_REQUEST_INSTRUCTION_HEADINGS = ("# Request Instructions",)


def _yaml_error_types() -> tuple[type[BaseException], ...]:
    if yaml is None:
        return (TypeError, ValueError)
    return (TypeError, ValueError, yaml.YAMLError)


def _yaml_scalar(value: str) -> Any:
    # Minimal scalar parser used when PyYAML is unavailable in the skill runtime.
    value = value.strip()
    if not value:
        return ""
    if (value[0], value[-1]) in {('"', '"'), ("'", "'")}:
        return value[1:-1]
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none", "~"}:
        return None
    if value.startswith("[") and value.endswith("]"):
        body = value[1:-1].strip()
        return [] if not body else [_yaml_scalar(item) for item in body.split(",")]
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def _yaml_lines(text: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        lines.append((indent, raw_line.strip()))
    return lines


def _split_yaml_key_value(content: str) -> tuple[str, str]:
    if ":" not in content:
        raise ValueError(f"Invalid YAML line: {content}")
    key, value = content.split(":", 1)
    key = key.strip()
    if not key:
        raise ValueError(f"Invalid YAML key: {content}")
    return key, value.strip()


def _parse_yaml_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    # Parse only the simple mapping/list shapes used in catalog instruction blocks.
    if index >= len(lines):
        return {}, index
    if lines[index][1].startswith("- "):
        result: list[Any] = []
        while index < len(lines) and lines[index][0] == indent and lines[index][1].startswith("- "):
            rest = lines[index][1][2:].strip()
            index += 1
            if not rest:
                item, index = _parse_yaml_block(lines, index, lines[index][0]) if index < len(lines) else ({}, index)
            elif ":" in rest:
                key, value = _split_yaml_key_value(rest)
                item = {key: _yaml_scalar(value)} if value else {key: {}}
                if index < len(lines) and lines[index][0] > indent:
                    child, index = _parse_yaml_block(lines, index, lines[index][0])
                    if isinstance(child, dict):
                        item.update(child)
            else:
                item = _yaml_scalar(rest)
            result.append(item)
        return result, index

    result: dict[str, Any] = {}
    while index < len(lines) and lines[index][0] == indent and not lines[index][1].startswith("- "):
        key, value = _split_yaml_key_value(lines[index][1])
        index += 1
        if value:
            result[key] = _yaml_scalar(value)
        elif index < len(lines) and lines[index][0] > indent:
            result[key], index = _parse_yaml_block(lines, index, lines[index][0])
        else:
            result[key] = {}
    return result, index


def _safe_load_yaml(text: str) -> Any:
    if yaml is not None:
        return yaml.safe_load(text)
    lines = _yaml_lines(text)
    if not lines:
        return None
    parsed, _ = _parse_yaml_block(lines, 0, lines[0][0])
    return parsed


def _extract_markdown_section(markdown_text: str, headings: tuple[str, ...]) -> tuple[str, str]:
    lines = markdown_text.splitlines()
    start_index = -1
    matched_heading = ""
    normalized_headings = {heading.strip(): heading.strip() for heading in headings}

    for index, line in enumerate(lines):
        stripped = line.strip().lstrip(chr(0xFEFF))
        if stripped in normalized_headings:
            start_index = index + 1
            matched_heading = normalized_headings[stripped]
            break

    if start_index == -1:
        return "", ""

    section_lines: list[str] = []
    for line in lines[start_index:]:
        if line.startswith("# "):
            break
        section_lines.append(line)
    return "\n".join(section_lines).strip(), matched_heading


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, dict) and "value" in value:
            value = value.get("value")
        if isinstance(value, (str, int, float)):
            text = str(value).strip()
            if text:
                return text
    return ""


def _localized_text(value: Any) -> str:
    if not isinstance(value, dict):
        return _first_text(value)
    return _first_text(
        value.get("zh"),
        value.get("zh_CN"),
        value.get("zh-CN"),
        value.get("cn"),
        value.get("en"),
        value.get("value"),
    )


def _label_from_mapping(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return _first_text(
        value.get("label"),
        value.get("title"),
        _localized_text(value.get("i18nTitle")),
        _localized_text(value.get("i18n_title")),
        value.get("displayName"),
        value.get("nameZh"),
        value.get("name"),
    )


def _schema_i18n_label(schema: dict[str, Any], field_key: str) -> str:
    i18n = schema.get("i18n")
    if not isinstance(i18n, dict):
        return ""
    for locale_key in ("zh", "zh_CN", "zh-CN", "cn", "en"):
        locale_map = i18n.get(locale_key)
        if not isinstance(locale_map, dict):
            continue
        if label := _first_text(locale_map.get(field_key)):
            return label
        field_i18n = locale_map.get(field_key)
        if isinstance(field_i18n, dict) and (label := _label_from_mapping(field_i18n)):
            return label
    field_i18n = i18n.get(field_key)
    if isinstance(field_i18n, dict):
        return _localized_text(field_i18n) or _label_from_mapping(field_i18n)
    return ""


def _catalog_name(catalog: dict[str, Any]) -> str:
    return _first_text(catalog.get("nameZh"), catalog.get("name"), catalog.get("displayName"))


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


def _resolve_runtime_default_only(raw_param: dict[str, Any]) -> bool:
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


def _default_value(raw_param: dict[str, Any]) -> Any:
    if "defaultValue" in raw_param:
        return raw_param.get("defaultValue")
    return raw_param.get("default_value")


def _normalize_param(raw_param: dict[str, Any]) -> dict[str, Any]:
    # Keep a stable parameter shape for agents regardless of source spelling.
    key = str(raw_param.get("key") or "")
    default_value = _default_value(raw_param)
    runtime_default_only = _resolve_runtime_default_only(raw_param) and default_value not in (None, "")

    normalized: dict[str, Any] = {
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


def _field_param(field_key: str, raw_field: object, *, location: str, node: str | None = None) -> dict[str, Any]:
    field = dict(raw_field) if isinstance(raw_field, dict) else {}
    if isinstance(raw_field, str) and raw_field.strip():
        field["label"] = raw_field.strip()
        field["description"] = raw_field.strip()
    field["key"] = field_key
    field["location"] = location
    if node:
        field["node"] = node
    return _normalize_param(field)


def _normalize_resource_specs(raw_specs: object) -> list[dict[str, Any]]:
    # Resource specs can nest params under several SmartCMP-specific containers.
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
    normalized_specs: list[dict[str, Any]] = []
    for raw_spec in raw_specs:
        if not isinstance(raw_spec, dict):
            continue

        node = str(raw_spec.get("node") or "").strip()
        normalized_spec: dict[str, Any] = {}
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
            normalized_bundle_params: dict[str, Any] = {}
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
            normalized_params: dict[str, Any] = {}
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


def _normalize_generic_request(raw_generic_request: object) -> dict[str, Any]:
    # Normalize generic request fields, especially processForm backend parameters.
    if not isinstance(raw_generic_request, dict):
        return {}

    normalized: dict[str, Any] = {}
    for field_key, raw_field in raw_generic_request.items():
        field_name = str(field_key)
        if field_name in {"processForm", "process_form"}:
            if not isinstance(raw_field, dict):
                continue
            process_form: dict[str, Any] = {}
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


def _normalize_instructions(raw_instructions: dict[str, Any]) -> dict[str, Any]:
    # Convert markdown YAML instructions into the same metadata shape as payload fields.
    normalized: dict[str, Any] = {}
    for key in ("node", "type", "osType", "cloudEntryTypeIds"):
        value = raw_instructions.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            if value.strip():
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
        normalized_root_params: dict[str, Any] = {}
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
        normalized_top_level_fields: dict[str, Any] = {}
        for field_key, raw_field in top_level_fields.items():
            normalized_top_level_fields[str(field_key)] = _field_param(
                str(field_key),
                raw_field,
                location="topLevel",
            )
        if normalized_top_level_fields:
            normalized["topLevelFields"] = normalized_top_level_fields

    return normalized


def _strip_markdown_code_fence(section_text: str) -> str:
    lines = section_text.strip().splitlines()
    if not lines:
        return ""
    if lines[0].strip().startswith("```"):
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_request_parameter_instructions(raw_instructions_text: str) -> dict[str, Any] | None:
    parameter_section, _ = _extract_markdown_section(raw_instructions_text, _REQUEST_PARAMETER_HEADINGS)
    yaml_text = _strip_markdown_code_fence(parameter_section)
    if not yaml_text:
        return None
    try:
        parsed = _safe_load_yaml(yaml_text)
    except _yaml_error_types():
        return None
    return parsed if isinstance(parsed, dict) else None


def _raw_request_parameter_section(raw_instructions_text: str) -> str:
    parameter_section, _ = _extract_markdown_section(raw_instructions_text, _REQUEST_PARAMETER_HEADINGS)
    return parameter_section


def _add_request_instruction_section(normalized: dict[str, Any], raw_instructions_text: str) -> None:
    request_section, _ = _extract_markdown_section(raw_instructions_text, _REQUEST_INSTRUCTION_HEADINGS)
    if request_section:
        normalized["requestInstructions"] = request_section


def _field_key_summary(instructions: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "topLevelFields": sorted((instructions.get("topLevelFields") or {}).keys()),
        "params": sorted((instructions.get("params") or {}).keys()),
        "genericRequest.processForm": sorted(
            ((instructions.get("genericRequest") or {}).get("processForm") or {}).keys()
        ),
        "resourceSpecs": [],
    }

    resource_specs = instructions.get("resourceSpecs")
    if isinstance(resource_specs, list):
        for spec in resource_specs:
            if not isinstance(spec, dict):
                continue
            reserved = {
                "node",
                "type",
                "resourceBundleId",
                "resourceBundleParams",
                "resourceBundleTags",
                "params",
            }
            direct_fields = [
                key
                for key, value in spec.items()
                if key not in reserved and isinstance(value, dict)
            ]
            summary["resourceSpecs"].append(
                {
                    "node": spec.get("node", ""),
                    "type": spec.get("type", ""),
                    "params": sorted((spec.get("params") or {}).keys()),
                    "resourceBundleParams": sorted((spec.get("resourceBundleParams") or {}).keys()),
                    "resourceSpecFields": sorted(direct_fields),
                }
            )

    return summary


def _looks_like_field_definition(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    markers = {
        "title",
        "label",
        "displayName",
        "nameZh",
        "type",
        "widget",
        "config",
        "templateOptions",
        "props",
        "i18nTitle",
        "defaultValue",
        "default_value",
        "required",
    }
    return any(key in value for key in markers)


def _payload_field_label(raw_field: dict[str, Any], key: str) -> str:
    nested_label = ""
    for nested_key in ("templateOptions", "template_options", "props", "options", "ui"):
        nested_label = _label_from_mapping(raw_field.get(nested_key))
        if nested_label:
            break
    return _first_text(
        raw_field.get("label"),
        raw_field.get("title"),
        _localized_text(raw_field.get("i18nTitle")),
        _localized_text(raw_field.get("i18n_title")),
        nested_label,
        raw_field.get("displayName"),
        raw_field.get("nameZh"),
        raw_field.get("name"),
        key,
    )


def _payload_field_param(field_key: str, raw_field: object, location: str) -> dict[str, Any]:
    field = dict(raw_field) if isinstance(raw_field, dict) else {}
    field["key"] = field_key
    field["label"] = _payload_field_label(field, field_key)
    field["location"] = location
    return _normalize_param(field)


def _add_mapping_fields(out: dict[str, Any], mapping: object, location: str) -> None:
    if not isinstance(mapping, dict):
        return
    for field_key, raw_field in mapping.items():
        if isinstance(field_key, str) and _looks_like_field_definition(raw_field):
            out.setdefault(field_key, _payload_field_param(field_key, raw_field, location))


def _add_schema_properties(out: dict[str, Any], schema: dict[str, Any], location: str) -> None:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return
    for field_key, raw_field in properties.items():
        if not isinstance(field_key, str) or not _looks_like_field_definition(raw_field):
            continue
        field = dict(raw_field) if isinstance(raw_field, dict) else {}
        if "label" not in field:
            field["label"] = _schema_i18n_label(schema, field_key)
        out.setdefault(field_key, _payload_field_param(field_key, field, location))


def _add_component_fields(out: dict[str, Any], components: object, location: str) -> None:
    if not isinstance(components, list):
        return
    for component in components:
        if not isinstance(component, dict):
            continue
        field_key = _first_text(component.get("key"), component.get("id"), component.get("name"))
        if field_key and _looks_like_field_definition(component):
            out.setdefault(field_key, _payload_field_param(field_key, component, location))
        _add_component_fields(out, component.get("components"), f"{location}.components")
        _add_component_fields(out, component.get("columns"), f"{location}.columns")
        _add_component_fields(out, component.get("rows"), f"{location}.rows")


def _extract_payload_form_fields(catalog: dict[str, Any], root_label: str = "catalog") -> dict[str, Any]:
    # Walk embedded form payloads without assuming one exact SmartCMP response shape.
    fields: dict[str, Any] = {}

    def visit(node: object, path: str, depth: int = 0) -> None:
        if depth > 6 or not isinstance(node, dict):
            return
        schema = node.get("schema")
        if isinstance(schema, dict):
            _add_schema_properties(fields, schema, f"{path}.schema.properties")
        _add_mapping_fields(fields, node.get("properties"), f"{path}.properties")
        _add_mapping_fields(fields, node.get("processForm"), f"{path}.processForm")
        _add_mapping_fields(fields, node.get("process_form"), f"{path}.process_form")
        _add_component_fields(fields, node.get("components"), f"{path}.components")

        for child_key in ("content", "form", "formDefinition", "formSchema", "modelForm", "requestForm"):
            child = node.get(child_key)
            if isinstance(child, dict):
                visit(child, f"{path}.{child_key}", depth + 1)

    visit(catalog, root_label)
    return fields


def _iter_form_ids(value: object, depth: int = 0) -> list[str]:
    # Collect related form ids from catalog payloads so missing embedded schemas can be fetched.
    if depth > 6:
        return []

    ids: list[str] = []
    id_keys = {
        "formId",
        "form_id",
        "requestFormId",
        "request_form_id",
        "requestParameterFormId",
        "request_parameter_form_id",
        "serviceModelFormId",
        "service_model_form_id",
        "modelFormId",
        "model_form_id",
    }
    container_keys = {
        "form",
        "forms",
        "requestForm",
        "requestForms",
        "formDefinition",
        "formDefinitions",
        "modelForm",
        "modelForms",
    }

    def add(raw: object) -> None:
        text = str(raw).strip() if isinstance(raw, (str, int, float)) else ""
        if text and text not in ids:
            ids.append(text)

    if isinstance(value, dict):
        for key, child in value.items():
            if key in id_keys:
                add(child)
                continue
            if key in container_keys and isinstance(child, dict):
                add(child.get("id"))
                add(child.get("uuid"))
                ids.extend(form_id for form_id in _iter_form_ids(child, depth + 1) if form_id not in ids)
                continue
            if key in container_keys and isinstance(child, list):
                ids.extend(form_id for form_id in _iter_form_ids(child, depth + 1) if form_id not in ids)
                continue
            if isinstance(child, (dict, list)):
                ids.extend(form_id for form_id in _iter_form_ids(child, depth + 1) if form_id not in ids)
    elif isinstance(value, list):
        for child in value:
            ids.extend(form_id for form_id in _iter_form_ids(child, depth + 1) if form_id not in ids)
    return ids


def _fetch_optional_json(path: str) -> object | None:
    try:
        response = requests.get(
            f"{BASE_URL}{path}",
            headers=HEADERS,
            verify=False,
            timeout=30,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException:
        return None
    payload = response.json()
    return payload if isinstance(payload, (dict, list)) else None


def _extract_payload_fields_from_any(payload: object, root_label: str) -> dict[str, Any]:
    if isinstance(payload, dict):
        return _extract_payload_form_fields(payload, root_label)
    if not isinstance(payload, list):
        return {}

    fields: dict[str, Any] = {}
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            continue
        fields.update(_extract_payload_form_fields(item, f"{root_label}[{index}]"))
    return fields


def _fetch_related_payload_form_fields(catalog: dict[str, Any], catalog_id: str) -> tuple[dict[str, Any], str]:
    # Try known form/detail endpoints as a fallback when the catalog payload is sparse.
    for form_id in _iter_form_ids(catalog):
        for path in (f"/forms/{form_id}", f"/service-model/forms/{form_id}"):
            payload = _fetch_optional_json(path)
            fields = _extract_payload_fields_from_any(payload, f"form:{form_id}")
            if fields:
                return fields, path

    for path in (
        f"/catalogs/{catalog_id}/request-form",
        f"/catalogs/{catalog_id}/requestForm",
        f"/catalogs/{catalog_id}/form",
        f"/catalogs/{catalog_id}/forms",
        f"/catalogs/published/{catalog_id}",
        f"/catalogs/{catalog_id}/detail",
    ):
        payload = _fetch_optional_json(path)
        fields = _extract_payload_fields_from_any(payload, f"catalogEndpoint:{path}")
        if fields:
            return fields, path

    return {}, ""


def _build_meta(catalog: dict[str, Any], catalog_id: str) -> dict[str, Any]:
    # Merge explicit markdown instructions and discovered form fields into one agent-facing meta block.
    raw_instructions = _first_text(catalog.get("instructions"))
    preapproval_instructions, preapproval_heading = _extract_markdown_section(
        raw_instructions,
        _PREAPPROVAL_HEADINGS,
    )
    parsed_request_instructions = _parse_request_parameter_instructions(raw_instructions)
    raw_parameter_section = _raw_request_parameter_section(raw_instructions)
    normalized_request_instructions: dict[str, Any] = {}
    if parsed_request_instructions:
        normalized_request_instructions = _normalize_instructions(parsed_request_instructions)
        _add_request_instruction_section(normalized_request_instructions, raw_instructions)
    payload_fields = _extract_payload_form_fields(catalog)
    payload_field_source = "catalog" if payload_fields else ""
    if not payload_fields:
        payload_fields, payload_field_source = _fetch_related_payload_form_fields(catalog, catalog_id)

    meta = {
        "id": _first_text(catalog.get("id")) or catalog_id,
        "name": _catalog_name(catalog),
        "sourceKey": _first_text(catalog.get("sourceKey")),
        "serviceCategory": _first_text(catalog.get("serviceCategory")),
        "catalogType": _first_text(catalog.get("type")),
        "hasInstructions": bool(raw_instructions),
        "hasRequestParameterInstructions": bool(normalized_request_instructions),
        "hasCatalogPayloadFields": bool(payload_fields),
        "hasPreApprovalInstructions": bool(preapproval_instructions),
    }
    if normalized_request_instructions:
        meta["instructions"] = normalized_request_instructions
        meta["catalogFieldKeys"] = _field_key_summary(normalized_request_instructions)
    if raw_parameter_section:
        meta["requestParameterInstructions"] = raw_parameter_section
    if payload_fields:
        meta["catalogPayloadFields"] = payload_fields
        meta["catalogPayloadFieldSource"] = payload_field_source
        meta.setdefault("catalogFieldKeys", {})["payloadFields"] = sorted(payload_fields.keys())
    if preapproval_instructions:
        meta["preApprovalInstructions"] = preapproval_instructions
        meta["preApprovalInstructionHeading"] = preapproval_heading
    return meta


def _fetch_catalog(catalog_id: str) -> dict[str, Any]:
    response = requests.get(
        f"{BASE_URL}/catalogs/{catalog_id}",
        headers=HEADERS,
        verify=False,
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    catalog_id = argv[0].strip() if argv else ""
    if not catalog_id:
        print("[ERROR] Missing required catalog_id argument.")
        return 1

    try:
        catalog = _fetch_catalog(catalog_id)
    except requests.exceptions.RequestException as error:
        print(f"[ERROR] Request failed: {error}")
        return 1

    meta = _build_meta(catalog, catalog_id)
    print(f"Catalog Detail: {meta.get('name') or catalog_id}")
    print(f"Catalog ID: {meta.get('id') or catalog_id}")
    print(f"Has Request Parameter Instructions: {str(meta.get('hasRequestParameterInstructions')).lower()}")
    print(f"Has Catalog Payload Fields: {str(meta.get('hasCatalogPayloadFields')).lower()}")
    print(f"Has Pre Approval Instructions: {str(meta.get('hasPreApprovalInstructions')).lower()}")
    print("##CATALOG_DETAIL_META_START##", file=sys.stderr)
    print(json.dumps(meta, ensure_ascii=False), file=sys.stderr)
    print("##CATALOG_DETAIL_META_END##", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
