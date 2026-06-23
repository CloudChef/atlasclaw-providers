#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Build SmartCMP service-catalog context sync fields from the maintained JS template."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CatalogContextOutput:
    """One supported service-catalog context output."""

    alias: str
    state: str
    output: str
    keys: tuple[str, ...]
    labels: tuple[str, ...]


_STANDARD_CONTEXT_OUTPUTS: tuple[CatalogContextOutput, ...] = (
    CatalogContextOutput(
        alias="businessGroup",
        state="businessGroupName",
        output="业务组",
        keys=("catalogServiceRequest.exts.businessGroup.name",),
        labels=("业务组", "BusinessGroup"),
    ),
    CatalogContextOutput(
        alias="projects",
        state="projectName",
        output="应用系统",
        keys=("catalogServiceRequest.exts.project.name",),
        labels=("应用系统", "Projects"),
    ),
    CatalogContextOutput(
        alias="owner",
        state="ownerName",
        output="所有者",
        keys=("catalogServiceRequest.exts.owner.name",),
        labels=("所有者", "Owner", "Owners"),
    ),
    CatalogContextOutput(
        alias="name",
        state="requestName",
        output="名称",
        keys=("name",),
        labels=("名称", "Name"),
    ),
)

_OUTPUT_ALIASES = {
    "businessgroup": "businessGroup",
    "business_group": "businessGroup",
    "业务组": "businessGroup",
    "projects": "projects",
    "project": "projects",
    "应用系统": "projects",
    "owner": "owner",
    "owners": "owner",
    "所有者": "owner",
    "负责人": "owner",
    "name": "name",
    "名称": "name",
}


def apply_catalog_context_sync(
    schema: dict[str, Any],
    catalog_context_sync_json: str,
) -> tuple[list[str], str | None]:
    """Apply one deterministic service-catalog context sync field to a schema.

    Args:
        schema: Mutable SmartCMP schema object.
        catalog_context_sync_json: JSON object with `fieldKey` and `outputs`.

    Returns:
        A pair of `(warnings, summary)`. `summary` is intended for user-visible
        tool output when a field was applied.

    Raises:
        ValueError: If the JSON request is malformed or asks for unsupported
            outputs.
    """
    if not catalog_context_sync_json.strip():
        return [], None

    request = _load_request(catalog_context_sync_json)
    field_key = request["fieldKey"]
    outputs = [_resolve_output(value) for value in request["outputs"]]
    expression = build_catalog_context_sync_expression(field_key, request["outputs"])

    properties = schema.setdefault("properties", {})
    if not isinstance(properties, dict):
        raise ValueError("schema.properties must be an object before catalog context sync can be applied.")

    field = properties.get(field_key)
    if not isinstance(field, dict):
        field = {}
        properties[field_key] = field

    field.update(
        {
            "id": field_key,
            "type": "string",
            "title": field.get("title") or field_key,
            "widget": {"id": "string"},
            "default": "AUTO_SYNC_PENDING",
            "hideTitle": True,
            "hideTitleText": True,
            "notitle": True,
        }
    )
    config = field.setdefault("config", {})
    if not isinstance(config, dict):
        config = {}
        field["config"] = config
    config["value"] = {
        "source": "mock",
        "method": "mock",
        "expression": expression,
    }
    config["visibility"] = {
        "allowInRequest": True,
        "allowInCatalog": False,
        "allowInApproval": False,
    }
    config["modification"] = {
        "allowInRequest": True,
        "allowInCatalog": False,
        "allowInApproval": False,
    }

    output_labels = ", ".join(output.output for output in outputs)
    return [], f"Applied catalog context sync field {field_key!r} with outputs: {output_labels}."


def build_catalog_context_sync_expression(field_key: str, outputs: list[Any]) -> str:
    """Build the maintained service-catalog context sync expression.

    Args:
        field_key: Target SmartCMP schema field key receiving the JSON string.
        outputs: Requested fixed service-catalog output labels or aliases.

    Returns:
        A one-line JavaScript function string based on the maintained template.

    Raises:
        ValueError: If `field_key` or any output is unsupported.
    """
    if not isinstance(field_key, str) or not field_key.strip():
        raise ValueError("catalog_context_sync_json.fieldKey must be a non-empty string.")
    resolved_outputs = [_resolve_output(output) for output in outputs]
    return _build_expression(field_key.strip(), resolved_outputs)


def _load_request(catalog_context_sync_json: str) -> dict[str, Any]:
    try:
        request = json.loads(catalog_context_sync_json)
    except json.JSONDecodeError as error:
        raise ValueError(f"catalog_context_sync_json is not valid JSON: {error}") from error
    if not isinstance(request, dict):
        raise ValueError("catalog_context_sync_json must be a JSON object.")

    field_key = request.get("fieldKey", "expansion")
    if not isinstance(field_key, str) or not field_key.strip():
        raise ValueError("catalog_context_sync_json.fieldKey must be a non-empty string.")
    request["fieldKey"] = field_key.strip()

    outputs = request.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise ValueError("catalog_context_sync_json.outputs must be a non-empty array.")
    request["outputs"] = outputs
    return request


def _resolve_output(value: Any) -> CatalogContextOutput:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("catalog_context_sync_json outputs must be non-empty strings.")
    raw_key = value.strip()
    key = _OUTPUT_ALIASES.get(raw_key) or _OUTPUT_ALIASES.get(raw_key.lower())
    if key is None:
        raise ValueError(f"Unsupported catalog_context_sync_json output {value!r}.")
    for output in _STANDARD_CONTEXT_OUTPUTS:
        if output.alias == key:
            return output
    raise ValueError(f"Unsupported catalog_context_sync_json output {value!r}.")


def _build_expression(field_key: str, outputs: list[CatalogContextOutput]) -> str:
    template = _template_path().read_text(encoding="utf-8").strip()
    expression = _replace_key(template, field_key)
    return _replace_field_specs(expression, outputs)


def _template_path() -> Path:
    return Path(__file__).resolve().parents[1] / "references" / "catalog-context-expression.js"


def _replace_key(template: str, field_key: str) -> str:
    return template.replace("KEY='expansion'", f"KEY='{_js_string(field_key)}'", 1)


def _replace_field_specs(template: str, outputs: list[CatalogContextOutput]) -> str:
    marker = "FIELD_SPECS=["
    start = template.find(marker)
    if start < 0:
        raise ValueError("catalog context template is missing FIELD_SPECS.")
    array_start = start + len("FIELD_SPECS=")
    array_end = _find_matching_array_end(template, array_start)
    field_specs = "[" + ",".join(_field_spec(output) for output in outputs) + "]"
    return template[:array_start] + field_specs + template[array_end + 1 :]


def _find_matching_array_end(source: str, array_start: int) -> int:
    depth = 0
    quote = ""
    escape = False
    for index in range(array_start, len(source)):
        char = source[index]
        if quote:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                quote = ""
            continue
        if char in ("'", '"'):
            quote = char
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return index
    raise ValueError("catalog context template has an unterminated FIELD_SPECS array.")


def _field_spec(output: CatalogContextOutput) -> str:
    keys = ",".join(f"'{_js_string(key)}'" for key in output.keys)
    labels = ",".join(f"'{_js_string(label)}'" for label in output.labels)
    return (
        "{"
        f"state:'{_js_string(output.state)}',"
        f"output:'{_js_string(output.output)}',"
        f"keys:[{keys}],"
        f"labels:[{labels}]"
        "}"
    )


def _js_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")
