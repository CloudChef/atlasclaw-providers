#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Generate SmartCMP field value expressions from declarative source specs."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


def _load_module_from_path(module_path: Path, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {module_path}")

    module = importlib.util.module_from_spec(spec)
    previous_module = sys.modules.get(module_name)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if previous_module is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous_module
    return module


try:
    from _value_expression_sources import (
        first_non_blank_string,
        parse_projection_fields,
        repair_fullwidth_json_punctuation,
        resolve_compose_spec,
    )
except ModuleNotFoundError as exc:
    if exc.name != "_value_expression_sources":
        raise
    _value_expression_sources = _load_module_from_path(
        Path(__file__).with_name("_value_expression_sources.py"),
        "_smartcmp_form_designer_value_expression_sources",
    )
    first_non_blank_string = _value_expression_sources.first_non_blank_string
    parse_projection_fields = _value_expression_sources.parse_projection_fields
    repair_fullwidth_json_punctuation = _value_expression_sources.repair_fullwidth_json_punctuation
    resolve_compose_spec = _value_expression_sources.resolve_compose_spec

try:
    from _schema_scripts import build_model_composition_expression, build_model_projection_expression
except ModuleNotFoundError as exc:
    if exc.name != "_schema_scripts":
        raise
    _schema_scripts = _load_module_from_path(
        Path(__file__).with_name("_schema_scripts.py"),
        "_smartcmp_form_designer_schema_scripts",
    )
    build_model_composition_expression = _schema_scripts.build_model_composition_expression
    build_model_projection_expression = _schema_scripts.build_model_projection_expression

try:
    from _schema_layout import ensure_field_in_root_fieldsets
except ModuleNotFoundError as exc:
    if exc.name != "_schema_layout":
        raise
    _schema_layout = _load_module_from_path(
        Path(__file__).with_name("_schema_layout.py"),
        "_smartcmp_form_designer_schema_layout",
    )
    ensure_field_in_root_fieldsets = _schema_layout.ensure_field_in_root_fieldsets


def apply_value_expressions(schema: dict[str, Any], value_expressions_json: str) -> list[str]:
    """Insert target fields whose value is generated from model/source paths."""
    if not value_expressions_json.strip():
        return []

    warnings: list[str] = []
    try:
        requests_json = json.loads(value_expressions_json)
    except json.JSONDecodeError as error:
        repaired_json = repair_fullwidth_json_punctuation(value_expressions_json)
        if repaired_json == value_expressions_json:
            raise ValueError(f"value_expressions_json is not valid JSON: {error}") from error
        try:
            requests_json = json.loads(repaired_json)
        except json.JSONDecodeError:
            raise ValueError(f"value_expressions_json is not valid JSON: {error}") from error
        warnings.append(
            "Repaired full-width JSON punctuation outside strings in value_expressions_json."
        )
    if not isinstance(requests_json, list):
        raise ValueError("value_expressions_json must be a JSON array.")

    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise ValueError(
            "schema.properties must be an object before value expressions can be inserted."
        )

    for request in requests_json:
        if not isinstance(request, dict):
            warnings.append("Ignored non-object value expression request.")
            continue

        field_key = request.get("fieldKey")
        if not isinstance(field_key, str) or not field_key.strip():
            warnings.append("Ignored value expression request without fieldKey.")
            continue
        field_key = field_key.strip()

        has_compose = "compose" in request
        has_fields = "fields" in request
        if has_compose == has_fields:
            raise ValueError(
                f"value expression for field {field_key!r} must include exactly one of fields or compose."
            )
        existing_field = properties.get(field_key)
        value_type = _normalize_value_type(
            first_non_blank_string(
                request.get("valueType"),
                request.get("outputType"),
                request.get("targetType"),
            ),
            existing_field,
            field_key,
            warnings,
        )

        try:
            if has_compose:
                raw_compose = request.get("compose")
                compose_spec = resolve_compose_spec(raw_compose, warnings)
                expression = build_model_composition_expression(
                    compose_spec,
                    target_field_key=field_key,
                    output_type=value_type,
                )
            else:
                projection_fields = parse_projection_fields(request.get("fields"), warnings)
                if not projection_fields:
                    raise ValueError(
                        f"value expression for field {field_key!r} has no usable fields."
                    )
                expression = build_model_projection_expression(
                    projection_fields,
                    target_field_key=field_key,
                    output_type=value_type,
                )
        except ValueError as error:
            raise ValueError(f"Invalid value expression for field {field_key!r}: {error}") from error

        target_field = _build_or_update_value_expression_field(
            existing_field,
            field_key,
            request,
            expression,
            value_type,
            warnings,
        )
        properties[field_key] = target_field
        ensure_field_in_root_fieldsets(schema, field_key, warnings)

    return warnings


def _normalize_value_type(
    explicit_value: Any,
    existing_field: Any,
    field_key: str,
    warnings: list[str],
) -> str:
    normalized = str(explicit_value or "").strip().replace("-", "").replace("_", "").lower()
    existing_value_type = _value_type_from_existing_field(existing_field)

    if not normalized or normalized in {"string", "text", "str"}:
        value_type = existing_value_type if not normalized else "string"
    elif normalized in {"jsonstring", "json"}:
        value_type = "jsonString"
    elif normalized in {"object", "jsonobject", "rawobject"}:
        value_type = "object"
    elif normalized in {"array", "jsonarray", "rawarray"}:
        value_type = "array"
    else:
        warnings.append(f"Unknown valueType {explicit_value!r}; using existing runtime value type.")
        return existing_value_type

    if normalized and existing_value_type != "string" and value_type != existing_value_type:
        warnings.append(
            f"valueType {value_type!r} overrides existing runtime value type "
            f"{existing_value_type!r} for field {field_key!r}."
        )
    return value_type


def _value_type_from_existing_field(existing_field: Any) -> str:
    if not isinstance(existing_field, dict):
        return "string"
    field_type = str(existing_field.get("type") or "").strip().replace("-", "").replace("_", "").lower()
    if field_type in {"object", "jsonobject", "rawobject"}:
        return "object"
    if field_type in {"array", "jsonarray", "rawarray"}:
        return "array"
    return "string"


def _schema_type_for_value_type(value_type: str) -> str:
    # SmartCMP evaluates config.value.expression on scalar controls. Object and
    # array containers can turn the target model into an empty schema-shaped
    # object before the expression has a chance to write the requested value.
    return "string"


def _widget_id_for_value_type(value_type: str) -> str:
    # Keep raw object/array outputs on an executable scalar field; the
    # expression writes the typed value into model[fieldKey].
    return "string"


def _build_or_update_value_expression_field(
    existing: Any,
    field_key: str,
    request: dict[str, Any],
    expression: str,
    value_type: str,
    warnings: list[str],
) -> dict[str, Any]:
    field = copy.deepcopy(existing) if isinstance(existing, dict) else {}
    if existing is not None and not isinstance(existing, dict):
        warnings.append(f"Replaced non-object field {field_key!r} with a value expression field.")

    field["id"] = field_key
    title = request.get("title")
    if isinstance(title, str) and title.strip():
        field["title"] = title.strip()
    else:
        field.setdefault("title", field_key)
    field["type"] = _schema_type_for_value_type(value_type)
    widget = field.get("widget")
    if not isinstance(widget, dict):
        field["widget"] = {"id": _widget_id_for_value_type(value_type)}
    else:
        widget["id"] = _widget_id_for_value_type(value_type)
    _remove_container_schema_keys(field)

    description = request.get("description")
    if isinstance(description, str) and description.strip():
        field["description"] = description.strip()

    hidden = request.get("hidden")
    if isinstance(hidden, bool):
        field["hidden"] = hidden
        if hidden is False:
            if field.get("condition") == "1 === 2":
                field.pop("condition", None)
            if field.get("hideTitle") is True:
                field.pop("hideTitle", None)
            _remove_input_class(field, "hidden")

    field.pop("defaultValue", None)
    field.pop("default", None)

    config = field.get("config")
    if not isinstance(config, dict):
        config = {}
        field["config"] = config
    visibility = config.get("visibility")
    if not isinstance(visibility, dict):
        visibility = {}
        config["visibility"] = visibility
    visibility.setdefault("allowInRequest", True)
    visibility.setdefault("allowInApproval", True)

    previous_value = config.get("value")
    if isinstance(previous_value, dict) and previous_value.get("expression") not in (None, expression):
        warnings.append(f"Replaced existing value expression for field {field_key!r}.")
    config["value"] = {
        "source": "mock",
        "method": "mock",
        "expression": expression,
    }
    return field


def _remove_container_schema_keys(field: dict[str, Any]) -> None:
    for key in ("properties", "items", "fieldsets", "columnsets", "format"):
        field.pop(key, None)


def _remove_input_class(field: dict[str, Any], class_name: str) -> None:
    current = field.get("inputClass")
    if not isinstance(current, str):
        return
    classes = [item for item in current.split() if item != class_name]
    if classes:
        field["inputClass"] = " ".join(classes)
    else:
        field.pop("inputClass", None)
