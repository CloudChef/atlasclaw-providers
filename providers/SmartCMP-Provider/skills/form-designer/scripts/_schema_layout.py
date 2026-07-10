#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Small layout helpers for SmartCMP form schema edits."""

from __future__ import annotations

from typing import Any


_ROOT_FIELDSET_ID = "fieldset-default"
_SCHEMA_FORM_VALID_FIELD_KEY = "schemaFormValid"


def ensure_schema_form_valid_control(
    schema: dict[str, Any],
    warnings: list[str],
) -> None:
    """Add SmartCMP's hidden validity control and make it reachable."""
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return

    field = properties.get(_SCHEMA_FORM_VALID_FIELD_KEY)
    if not isinstance(field, dict):
        properties[_SCHEMA_FORM_VALID_FIELD_KEY] = _schema_form_valid_field()
        warnings.append("Added hidden SmartCMP schemaFormValid technical field.")
    else:
        _normalize_schema_form_valid_field(field, warnings)

    if schema.get("fieldsets") is None:
        schema["fieldsets"] = [_default_root_fieldset(list(properties))]
        warnings.append("Created root fieldsets for SmartCMP technical validity field.")
    else:
        ensure_field_in_root_fieldsets(schema, _SCHEMA_FORM_VALID_FIELD_KEY, warnings)

    _canonicalize_root_fieldsets(schema, properties, warnings)
    _normalize_catalog_request_field_indexes(schema, properties, warnings)


def ensure_field_in_root_fieldsets(
    schema: dict[str, Any],
    field_key: str,
    warnings: list[str],
) -> None:
    """Ensure an inserted top-level field is reachable from root fieldsets."""
    if not isinstance(field_key, str) or not field_key:
        return

    fieldsets = schema.get("fieldsets")
    if fieldsets is None:
        schema["fieldsets"] = [_default_root_fieldset([field_key])]
        warnings.append(f"Created root fieldsets for inserted field {field_key!r}.")
        return
    if not isinstance(fieldsets, list):
        return

    target_fieldset: dict[str, Any] | None = None
    for fieldset in fieldsets:
        if not isinstance(fieldset, dict):
            continue
        _normalize_root_fieldset_shell(fieldset)
        fields = fieldset.get("fields")
        if not isinstance(fields, list):
            legacy_fields = fieldset.get("properties")
            if not isinstance(legacy_fields, list):
                continue
            fields = _field_keys_from_refs(legacy_fields)
            fieldset["fields"] = fields
            fieldset.pop("properties", None)
            warnings.append("Converted root fieldset properties to fields before inserting fields.")
        if any(_fieldset_field_key(field_ref) == field_key for field_ref in fields):
            return
        if target_fieldset is None:
            target_fieldset = fieldset

    if target_fieldset is None:
        target_fieldset = _default_root_fieldset([])
        fieldsets.append(target_fieldset)

    fields = target_fieldset.setdefault("fields", [])
    if isinstance(fields, list):
        fields.append(field_key)
        warnings.append(f"Added inserted field {field_key!r} to root fieldsets.")


def _schema_form_valid_field() -> dict[str, Any]:
    return {
        "hidden": True,
        "type": "boolean",
        "default": True,
        "condition": "1 === 2",
        "widget": {"id": "hidden"},
    }


def _normalize_schema_form_valid_field(
    field: dict[str, Any],
    warnings: list[str],
) -> None:
    expected = _schema_form_valid_field()
    for key, value in expected.items():
        if key == "widget":
            widget = field.get("widget")
            if not isinstance(widget, dict):
                field["widget"] = {"id": "hidden"}
                warnings.append("Set schemaFormValid widget.id=hidden.")
            elif widget.get("id") != "hidden":
                widget["id"] = "hidden"
                warnings.append("Set schemaFormValid widget.id=hidden.")
            continue
        if field.get(key) != value:
            field[key] = value
            warnings.append(f"Set schemaFormValid {key}={value!r}.")


def _canonicalize_root_fieldsets(
    schema: dict[str, Any],
    properties: dict[str, Any],
    warnings: list[str],
) -> None:
    fieldsets = schema.get("fieldsets")
    if not isinstance(fieldsets, list):
        return

    for index, fieldset in enumerate(fieldsets):
        if not isinstance(fieldset, dict):
            continue
        if index == 0 and fieldset.get("id") != _ROOT_FIELDSET_ID:
            fieldset["id"] = _ROOT_FIELDSET_ID
            warnings.append("Set root fieldset id=fieldset-default for catalog request compatibility.")
        if "index" in fieldset:
            fieldset.pop("index", None)
            warnings.append("Removed root fieldset index for catalog request compatibility.")
        _normalize_root_fieldset_shell(fieldset)

        fields = fieldset.get("fields")
        if not isinstance(fields, list):
            continue
        canonical_fields = _canonical_root_fieldset_fields(fields, properties)
        if canonical_fields != fields:
            fieldset["fields"] = canonical_fields
            warnings.append("Canonicalized root fieldset field order for catalog request compatibility.")


def _canonical_root_fieldset_fields(
    fields: list[Any],
    properties: dict[str, Any],
) -> list[str]:
    business_fields: list[str] = []
    seen: set[str] = set()
    has_schema_form_valid = False
    for field_ref in fields:
        field_key = _fieldset_field_key(field_ref)
        if field_key is None or field_key not in properties or field_key in seen:
            continue
        seen.add(field_key)
        if field_key == _SCHEMA_FORM_VALID_FIELD_KEY:
            has_schema_form_valid = True
        else:
            business_fields.append(field_key)

    if _SCHEMA_FORM_VALID_FIELD_KEY in properties:
        has_schema_form_valid = True
    if has_schema_form_valid:
        business_fields.append(_SCHEMA_FORM_VALID_FIELD_KEY)
    return business_fields


def _normalize_catalog_request_field_indexes(
    schema: dict[str, Any],
    properties: dict[str, Any],
    warnings: list[str],
) -> None:
    fieldsets = schema.get("fieldsets")
    if not isinstance(fieldsets, list):
        return

    ordered_fields: list[str] = []
    seen: set[str] = set()
    for fieldset in fieldsets:
        if not isinstance(fieldset, dict) or not isinstance(fieldset.get("fields"), list):
            continue
        for field_ref in fieldset["fields"]:
            field_key = _fieldset_field_key(field_ref)
            if (
                field_key is None
                or field_key == _SCHEMA_FORM_VALID_FIELD_KEY
                or field_key in seen
                or field_key not in properties
            ):
                continue
            ordered_fields.append(field_key)
            seen.add(field_key)

    for index, field_key in enumerate(ordered_fields, start=1):
        field = properties.get(field_key)
        if not isinstance(field, dict):
            continue
        if field.get("index") != index:
            field["index"] = index
            warnings.append(
                f"Set catalog request field index={index} for field {field_key!r}."
            )

    technical_field = properties.get(_SCHEMA_FORM_VALID_FIELD_KEY)
    if isinstance(technical_field, dict) and "index" in technical_field:
        technical_field.pop("index", None)
        warnings.append("Removed schemaFormValid index for catalog request compatibility.")


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


def _field_keys_from_refs(field_refs: list[Any]) -> list[str]:
    fields: list[str] = []
    seen: set[str] = set()
    for field_ref in field_refs:
        field_key = _fieldset_field_key(field_ref)
        if field_key is None or field_key in seen:
            continue
        fields.append(field_key)
        seen.add(field_key)
    return fields
