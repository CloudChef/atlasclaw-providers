#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Apply exact top-level form-field constraints to SmartCMP schemas."""

from __future__ import annotations

import json
from typing import Any


_ROOT_FIELDSET_ID = "fieldset-default"
_SMARTCMP_TECHNICAL_FIELD_KEYS = {"schemaFormValid"}


def load_requested_fields(requested_fields_json: str) -> list[str]:
    """Parse an optional exact form-field list from a JSON array string."""
    if not requested_fields_json.strip():
        return []
    try:
        parsed = json.loads(requested_fields_json)
    except json.JSONDecodeError as error:
        raise ValueError(f"requested_fields_json is not valid JSON: {error}") from error
    if not isinstance(parsed, list):
        raise ValueError("requested_fields_json must be a JSON array.")

    fields: list[str] = []
    seen: set[str] = set()
    invalid_items: list[int] = []
    for index, item in enumerate(parsed):
        if not isinstance(item, str) or not item.strip():
            invalid_items.append(index)
            continue
        field_key = item.strip()
        if field_key in seen:
            continue
        fields.append(field_key)
        seen.add(field_key)
    if invalid_items:
        raise ValueError(
            "requested_fields_json items must be non-empty strings; "
            + "invalid item indexes: "
            + ", ".join(str(index) for index in invalid_items)
            + "."
        )
    return fields


def constrain_schema_to_requested_fields(
    schema: dict[str, Any],
    requested_fields: list[str],
    *,
    require_all: bool = False,
) -> list[str]:
    """Keep only the exact requested top-level form fields when supplied."""
    if not requested_fields:
        return []

    warnings: list[str] = []
    requested_set = set(requested_fields)
    properties = schema.get("properties")
    if isinstance(properties, dict):
        _constrain_properties(schema, properties, requested_fields, requested_set, warnings)
        if require_all:
            _raise_for_missing_requested_properties(properties, requested_fields)
    elif require_all:
        raise ValueError("schema.properties must be an object when requested_fields_json is provided.")

    fieldsets = schema.get("fieldsets")
    if isinstance(fieldsets, list):
        _constrain_fieldsets(schema, fieldsets, requested_fields, requested_set, warnings)
        if require_all and isinstance(schema.get("properties"), dict):
            _ensure_requested_fieldset_coverage(schema, requested_fields, warnings)
    else:
        schema["fieldsets"] = [_default_root_fieldset(_requested_and_technical_fields(schema, requested_fields))]
        warnings.append("Created root fieldsets from requested fields.")

    return warnings


def _raise_for_missing_requested_properties(
    properties: dict[str, Any],
    requested_fields: list[str],
) -> None:
    missing = [field_key for field_key in requested_fields if field_key not in properties]
    if missing:
        raise ValueError(
            "schema.properties is missing requested fields: "
            + ", ".join(repr(field_key) for field_key in missing)
        )


def _constrain_properties(
    schema: dict[str, Any],
    properties: dict[str, Any],
    requested_fields: list[str],
    requested_set: set[str],
    warnings: list[str],
) -> None:
    technical_fields = _technical_property_keys(properties)
    allowed_set = requested_set | set(technical_fields)
    removed = [field_key for field_key in list(properties) if field_key not in allowed_set]
    for field_key in removed:
        properties.pop(field_key, None)
    if removed:
        warnings.append(
            "Removed unrequested schema properties: "
            + ", ".join(repr(item) for item in removed)
        )

    ordered_properties: dict[str, Any] = {}
    for field_key in requested_fields:
        if field_key in properties:
            ordered_properties[field_key] = properties[field_key]
    for field_key in technical_fields:
        if field_key in properties and field_key not in ordered_properties:
            ordered_properties[field_key] = properties[field_key]
    for field_key, field_value in properties.items():
        if field_key not in ordered_properties:
            ordered_properties[field_key] = field_value
    schema["properties"] = ordered_properties


def _constrain_fieldsets(
    schema: dict[str, Any],
    fieldsets: list[Any],
    requested_fields: list[str],
    requested_set: set[str],
    warnings: list[str],
) -> None:
    properties = schema.get("properties")
    technical_fields = _technical_property_keys(properties) if isinstance(properties, dict) else []
    allowed_set = requested_set | set(technical_fields)
    for fieldset in fieldsets:
        if not isinstance(fieldset, dict):
            continue
        _normalize_root_fieldset_shell(fieldset)
        fields = fieldset.get("fields")
        if not isinstance(fields, list):
            continue
        filtered: list[str] = []
        removed: list[Any] = []
        normalized_object_refs = False
        for field_ref in fields:
            field_key = _fieldset_field_key(field_ref)
            if field_key is None:
                removed.append(field_ref)
                continue
            if field_key not in allowed_set:
                removed.append(field_ref)
                continue
            filtered.append(field_key)
            if field_key != field_ref:
                normalized_object_refs = True
        if filtered == fields:
            continue
        fieldset["fields"] = filtered
        if normalized_object_refs:
            warnings.append("Normalized object fieldset references to field keys.")
        if removed:
            warnings.append(
                "Removed unrequested fieldset references: "
                + ", ".join(repr(item) for item in removed)
            )

    if not any(
        isinstance(fieldset, dict)
        and isinstance(fieldset.get("fields"), list)
        and fieldset["fields"]
        for fieldset in fieldsets
    ):
        schema["fieldsets"] = [_default_root_fieldset(_requested_and_technical_fields(schema, requested_fields))]
        warnings.append("Rebuilt root fieldsets from requested fields.")


def _ensure_requested_fieldset_coverage(
    schema: dict[str, Any],
    requested_fields: list[str],
    warnings: list[str],
) -> None:
    properties = schema.get("properties")
    fieldsets = schema.get("fieldsets")
    if not isinstance(properties, dict) or not isinstance(fieldsets, list):
        return

    covered = {
        field_key
        for fieldset in fieldsets
        if isinstance(fieldset, dict) and isinstance(fieldset.get("fields"), list)
        for field_key in fieldset["fields"]
        if isinstance(field_key, str)
    }
    missing = [
        field_key
        for field_key in requested_fields
        if field_key in properties and field_key not in covered
    ]
    if not missing:
        return

    target_fieldset = None
    for fieldset in fieldsets:
        if isinstance(fieldset, dict) and isinstance(fieldset.get("fields"), list):
            target_fieldset = fieldset
            break
    if target_fieldset is None:
        target_fieldset = _default_root_fieldset([])
        fieldsets.append(target_fieldset)

    target_fieldset["fields"].extend(missing)
    warnings.append(
        "Added missing requested fieldset references: "
        + ", ".join(repr(field_key) for field_key in missing)
    )


def _fieldset_field_key(field_ref: Any) -> str | None:
    if isinstance(field_ref, str) and field_ref:
        return field_ref
    if not isinstance(field_ref, dict):
        return None
    for key in ("id", "key"):
        value = field_ref.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _technical_property_keys(properties: dict[str, Any]) -> list[str]:
    return [
        field_key
        for field_key in properties
        if field_key in _SMARTCMP_TECHNICAL_FIELD_KEYS
    ]


def _requested_and_technical_fields(schema: dict[str, Any], requested_fields: list[str]) -> list[str]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return list(requested_fields)
    fields = list(requested_fields)
    for field_key in _technical_property_keys(properties):
        if field_key not in fields:
            fields.append(field_key)
    return fields


def _default_root_fieldset(fields: list[str]) -> dict[str, Any]:
    return {
        "id": _ROOT_FIELDSET_ID,
        "title": "",
        "description": "",
        "name": "",
        "fields": fields,
    }


def _normalize_root_fieldset_shell(fieldset: dict[str, Any]) -> None:
    if not isinstance(fieldset.get("id"), str) or not fieldset["id"]:
        fieldset["id"] = _ROOT_FIELDSET_ID
    fieldset.setdefault("title", "")
    fieldset.setdefault("description", "")
    fieldset.setdefault("name", "")
