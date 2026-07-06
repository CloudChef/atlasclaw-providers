#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Normalize SmartCMP Angular form schema JSON."""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path
from typing import Any


class SchemaNormalizationError(ValueError):
    """Raised when a schema cannot be interpreted as a JSON object."""


def _load_module_from_path(module_path: Path, module_name: str) -> Any:
    """Load a module by file path without permanently changing global import paths."""
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
    from _catalog_fields import resolve_catalog_field_alias
except ModuleNotFoundError as exc:
    if exc.name != "_catalog_fields":
        raise
    _catalog_fields = _load_module_from_path(
        Path(__file__).with_name("_catalog_fields.py"),
        "_smartcmp_form_designer_catalog_fields",
    )
    resolve_catalog_field_alias = _catalog_fields.resolve_catalog_field_alias

try:
    from _schema_scripts import expression_from_field, validate_javascript_expression
except ModuleNotFoundError as exc:
    if exc.name != "_schema_scripts":
        raise
    _schema_scripts = _load_module_from_path(
        Path(__file__).with_name("_schema_scripts.py"),
        "_smartcmp_form_designer_schema_scripts",
    )
    expression_from_field = _schema_scripts.expression_from_field
    validate_javascript_expression = _schema_scripts.validate_javascript_expression

try:
    from _schema_field_normalize import (
        infer_type,
        is_table_array_field,
        normalize_array_field,
        normalize_visibility,
        normalize_widget,
    )
except ModuleNotFoundError as exc:
    if exc.name != "_schema_field_normalize":
        raise
    _schema_field_normalize = _load_module_from_path(
        Path(__file__).with_name("_schema_field_normalize.py"),
        "_smartcmp_form_designer_schema_field_normalize",
    )
    infer_type = _schema_field_normalize.infer_type
    is_table_array_field = _schema_field_normalize.is_table_array_field
    normalize_array_field = _schema_field_normalize.normalize_array_field
    normalize_visibility = _schema_field_normalize.normalize_visibility
    normalize_widget = _schema_field_normalize.normalize_widget


def normalize_schema(schema: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Return a normalized SmartCMP Angular form schema.

    The normalizer repairs deterministic structural issues only. It preserves
    unknown keys and reports changes through warnings so that the LLM and user
    can review the result before copying it into CMP.

    Args:
        schema: Draft or existing SmartCMP form schema.

    Returns:
        A tuple of `(normalized_schema, warnings)`.

    Raises:
        SchemaNormalizationError: If `schema` is not a JSON object.
    """
    if not isinstance(schema, dict):
        raise SchemaNormalizationError("Schema must be a JSON object.")

    warnings: list[str] = []
    normalized = copy.deepcopy(schema)

    if "properties" not in normalized and isinstance(normalized.get("schema"), dict):
        normalized = copy.deepcopy(normalized["schema"])
        warnings.append(
            "Unwrapped top-level schema container; return the SmartCMP schema object directly instead of {'schema': ...}."
        )

    if normalized.get("type") != "object":
        previous = normalized.get("type")
        normalized["type"] = "object"
        warnings.append(f"Set root type to object (was {previous!r}).")

    properties = normalized.get("properties")
    if not isinstance(properties, dict):
        normalized["properties"] = {}
        warnings.append("Created missing root properties object.")
        properties = normalized["properties"]

    widget = normalized.get("widget")
    if not isinstance(widget, dict):
        normalized["widget"] = {"id": "object"}
        warnings.append("Added root widget.id=object.")
    elif widget.get("id") != "object":
        widget["id"] = "object"
        warnings.append("Set root widget.id=object.")

    _normalize_root_fieldsets(normalized, properties, warnings)

    for index, (field_key, field_value) in enumerate(properties.items()):
        properties[field_key] = _normalize_top_level_field(
            field_key,
            field_value,
            index,
            warnings,
        )
    _deduplicate_top_level_indexes(properties, warnings)

    return normalized, warnings


def _normalize_root_fieldsets(
    normalized: dict[str, Any],
    properties: dict[str, Any],
    warnings: list[str],
) -> None:
    """Normalize root fieldsets without preserving non-renderable field lists."""
    if "fieldsets" not in normalized:
        return

    fieldsets = normalized.get("fieldsets")
    if not isinstance(fieldsets, list):
        normalized["fieldsets"] = (
            [{"id": "default", "fields": list(properties.keys())}]
            if properties
            else []
        )
        warnings.append("Replaced invalid root fieldsets with a deterministic field list.")
        return

    for index, fieldset in enumerate(fieldsets):
        if not isinstance(fieldset, dict):
            continue
        if isinstance(fieldset.get("fields"), list):
            continue
        legacy_properties = fieldset.get("properties")
        if isinstance(legacy_properties, list):
            fields = [
                field_key
                for field_key in legacy_properties
                if isinstance(field_key, str) and field_key in properties
            ]
            if fields:
                fieldset["fields"] = fields
                fieldset.pop("properties", None)
                warnings.append(
                    "Converted root fieldset properties to fields "
                    f"for fieldset at index {index}."
                )


def _deduplicate_top_level_indexes(
    properties: dict[str, Any],
    warnings: list[str],
) -> None:
    """Resolve ambiguous top-level field ordering without dropping fields."""
    seen_indexes: set[int] = set()
    has_duplicate = False
    for field in properties.values():
        field_index = field.get("index") if isinstance(field, dict) else None
        if not _is_valid_integer_index(field_index):
            continue
        if field_index in seen_indexes:
            has_duplicate = True
            break
        seen_indexes.add(field_index)

    if not has_duplicate:
        return

    for index, (field_key, field) in enumerate(properties.items()):
        if not isinstance(field, dict):
            continue
        if field.get("index") != index:
            field["index"] = index
            warnings.append(
                f"Reassigned index={index} for field {field_key!r} "
                "to avoid duplicate top-level indexes."
            )


def _normalize_top_level_field(
    field_key: str,
    raw_field: Any,
    index: int,
    warnings: list[str],
) -> dict[str, Any]:
    if not isinstance(raw_field, dict):
        warnings.append(f"Replaced non-object field {field_key!r} with a string field.")
        raw_field = {"title": field_key}

    field = raw_field
    if not field.get("id"):
        field["id"] = field_key
        warnings.append(f"Added id for field {field_key!r}.")

    if not _is_valid_integer_index(field.get("index")):
        field["index"] = index
        warnings.append(f"Added numeric index for field {field_key!r}.")

    field_type = field.get("type")
    if not isinstance(field_type, str) or not field_type.strip():
        field["type"] = infer_type(field)
        warnings.append(f"Added type={field['type']} for field {field_key!r}.")

    normalize_widget(field, field_key, warnings)
    normalize_visibility(field, field_key, warnings)
    warnings.extend(
        validate_javascript_expression(
            expression_from_field(field),
            field_key=field_key,
        )
    )
    _validate_builtin_catalog_metadata(field, field_key, warnings)

    if field.get("type") == "array" and is_table_array_field(field):
        normalize_array_field(field, field_key, warnings)

    return field


def _is_valid_integer_index(value: Any) -> bool:
    """Return whether a schema index is an integer, excluding bool aliases."""
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_builtin_catalog_metadata(
    field: dict[str, Any],
    field_key: str,
    warnings: list[str],
) -> None:
    """Warn when top-level catalog metadata names an unsupported built-in field.

    Missing, non-object, blank, or non-string metadata values are intentionally
    ignored because they do not express a catalog field contract. The
    normalizer preserves those shapes unchanged for manual review.
    """
    smartcmp_metadata = field.get("x-smartcmp")
    if not isinstance(smartcmp_metadata, dict):
        return

    builtin_field = smartcmp_metadata.get("builtinCatalogField")
    if not isinstance(builtin_field, str) or not builtin_field.strip():
        return

    if resolve_catalog_field_alias(builtin_field) is not None:
        return

    warnings.append(
        "Unknown SmartCMP catalog field "
        f"{builtin_field!r} on field {field_key!r}; "
        "preserved metadata for manual review."
    )
