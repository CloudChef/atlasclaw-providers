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

try:
    from _catalog_fields import resolve_catalog_field_alias
except ModuleNotFoundError as exc:
    if exc.name != "_catalog_fields":
        raise

    _CATALOG_FIELDS_PATH = Path(__file__).with_name("_catalog_fields.py")
    _CATALOG_FIELDS_MODULE_NAME = "_smartcmp_form_designer_catalog_fields"
    _CATALOG_FIELDS_SPEC = importlib.util.spec_from_file_location(
        _CATALOG_FIELDS_MODULE_NAME,
        _CATALOG_FIELDS_PATH,
    )
    if _CATALOG_FIELDS_SPEC is None or _CATALOG_FIELDS_SPEC.loader is None:
        raise ImportError(f"Cannot load {_CATALOG_FIELDS_PATH}") from exc

    _catalog_fields = importlib.util.module_from_spec(_CATALOG_FIELDS_SPEC)
    _previous_catalog_fields = sys.modules.get(_CATALOG_FIELDS_MODULE_NAME)
    sys.modules[_CATALOG_FIELDS_MODULE_NAME] = _catalog_fields
    try:
        _CATALOG_FIELDS_SPEC.loader.exec_module(_catalog_fields)
    finally:
        if _previous_catalog_fields is None:
            sys.modules.pop(_CATALOG_FIELDS_MODULE_NAME, None)
        else:
            sys.modules[_CATALOG_FIELDS_MODULE_NAME] = _previous_catalog_fields
    resolve_catalog_field_alias = _catalog_fields.resolve_catalog_field_alias

try:
    from _schema_scripts import expression_from_field, validate_javascript_expression
except ModuleNotFoundError as exc:
    if exc.name != "_schema_scripts":
        raise

    _SCHEMA_SCRIPTS_PATH = Path(__file__).with_name("_schema_scripts.py")
    _SCHEMA_SCRIPTS_SPEC = importlib.util.spec_from_file_location(
        "_schema_scripts",
        _SCHEMA_SCRIPTS_PATH,
    )
    if _SCHEMA_SCRIPTS_SPEC is None or _SCHEMA_SCRIPTS_SPEC.loader is None:
        raise ImportError(f"Cannot load {_SCHEMA_SCRIPTS_PATH}") from exc

    _schema_scripts = importlib.util.module_from_spec(_SCHEMA_SCRIPTS_SPEC)
    _SCHEMA_SCRIPTS_SPEC.loader.exec_module(_schema_scripts)
    expression_from_field = _schema_scripts.expression_from_field
    validate_javascript_expression = _schema_scripts.validate_javascript_expression


class SchemaNormalizationError(ValueError):
    """Raised when a schema cannot be interpreted as a JSON object."""


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

    normalized = copy.deepcopy(schema)
    warnings: list[str] = []

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
    elif not widget.get("id"):
        widget["id"] = "object"
        warnings.append("Added root widget.id=object.")

    if "fieldsets" in normalized and not isinstance(normalized.get("fieldsets"), list):
        normalized["fieldsets"] = []
        warnings.append("Replaced invalid root fieldsets with an empty list.")

    for index, (field_key, field_value) in enumerate(properties.items()):
        properties[field_key] = _normalize_top_level_field(
            field_key,
            field_value,
            index,
            warnings,
        )
    _deduplicate_top_level_indexes(properties, warnings)

    return normalized, warnings


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
        field["type"] = _infer_type(field)
        warnings.append(f"Added type={field['type']} for field {field_key!r}.")

    _normalize_widget(field, field_key, warnings)
    _normalize_visibility(field, field_key, warnings)
    warnings.extend(
        validate_javascript_expression(
            expression_from_field(field),
            field_key=field_key,
        )
    )
    _validate_builtin_catalog_metadata(field, field_key, warnings)

    if field.get("type") == "array":
        _normalize_array_field(field, field_key, warnings)

    return field


def _is_valid_integer_index(value: Any) -> bool:
    """Return whether a schema index is an integer, excluding bool aliases."""
    return isinstance(value, int) and not isinstance(value, bool)


def _infer_type(field: dict[str, Any]) -> str:
    widget = field.get("widget") if isinstance(field.get("widget"), dict) else {}
    widget_id = str(widget.get("id") or "").strip()
    if widget_id == "number":
        return "number"
    if field.get("items") is not None or widget_id == "table-head":
        return "array"
    return "string"


def _normalize_widget(field: dict[str, Any], field_key: str, warnings: list[str]) -> None:
    widget = field.get("widget")
    if not isinstance(widget, dict):
        field["widget"] = {"id": _default_widget_for_field(field)}
        warnings.append(f"Added widget.id={field['widget']['id']} for field {field_key!r}.")
        return

    if not widget.get("id"):
        widget["id"] = _default_widget_for_field(field)
        warnings.append(f"Added widget.id={widget['id']} for field {field_key!r}.")
    else:
        # LLM drafts often use human-facing widget names. Normalize only aliases
        # with a deterministic SmartCMP equivalent, leaving unknown widgets intact.
        _normalize_widget_alias(field, field_key, warnings)

    _promote_select_keys_from_widget(field, field_key, warnings)


def _normalize_widget_alias(field: dict[str, Any], field_key: str, warnings: list[str]) -> None:
    widget = field.get("widget")
    if not isinstance(widget, dict):
        return

    widget_id = str(widget.get("id") or "").strip()
    if widget_id == "text":
        widget["id"] = "string"
        warnings.append(f"Changed widget.id=text to string for field {field_key!r}.")
    elif field.get("type") == "array" and widget_id in {"array", "table"}:
        widget["id"] = "table-head"
        warnings.append(
            f"Changed widget.id={widget_id} to table-head for array field {field_key!r}."
        )


def _promote_select_keys_from_widget(
    field: dict[str, Any],
    field_key: str,
    warnings: list[str],
) -> None:
    widget = field.get("widget")
    if not isinstance(widget, dict):
        return

    for key in ("selectDatas", "value"):
        if key in widget and key not in field:
            # SmartCMP schemas commonly keep select metadata at field level. Copy
            # it out for compatibility, but do not overwrite intentional fields.
            field[key] = copy.deepcopy(widget[key])
            warnings.append(
                f"Copied widget.{key} to field-level {key} for field {field_key!r}."
            )


def _default_widget_for_field(field: dict[str, Any]) -> str:
    field_type = field.get("type")
    if field_type == "array":
        return "table-head"
    if field_type == "number":
        return "number"
    return "string"


def _normalize_visibility(field: dict[str, Any], field_key: str, warnings: list[str]) -> None:
    config = field.get("config")
    if not isinstance(config, dict):
        config = {}
        field["config"] = config
        warnings.append(f"Added config object for field {field_key!r}.")

    visibility = config.get("visibility")
    if not isinstance(visibility, dict):
        visibility = {}
        config["visibility"] = visibility
        warnings.append(f"Added config.visibility for field {field_key!r}.")

    if "allowInRequest" not in visibility:
        visibility["allowInRequest"] = True
        warnings.append(f"Added allowInRequest=true for field {field_key!r}.")
    if "allowInApproval" not in visibility:
        visibility["allowInApproval"] = True
        warnings.append(f"Added allowInApproval=true for field {field_key!r}.")


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

    if resolve_catalog_field_alias(builtin_field) is None:
        warnings.append(
            "Unknown SmartCMP catalog field "
            f"{builtin_field!r} on field {field_key!r}; "
            "preserved metadata for manual review."
        )


def _normalize_array_field(field: dict[str, Any], field_key: str, warnings: list[str]) -> None:
    items = field.get("items")
    if not isinstance(items, dict):
        items = {"type": "object", "properties": {}, "widget": {"id": "table-body"}}
        field["items"] = items
        warnings.append(f"Added object items for array field {field_key!r}.")

    if items.get("type") != "object":
        items["type"] = "object"
        warnings.append(f"Set array field {field_key!r} items.type=object.")

    item_properties = items.get("properties")
    if not isinstance(item_properties, dict):
        items["properties"] = {}
        item_properties = items["properties"]
        warnings.append(f"Added items.properties for array field {field_key!r}.")

    item_widget = items.get("widget")
    if not isinstance(item_widget, dict):
        items["widget"] = {"id": "table-body"}
        warnings.append(f"Added items.widget.id=table-body for array field {field_key!r}.")
    elif not item_widget.get("id"):
        item_widget["id"] = "table-body"
        warnings.append(f"Added items.widget.id=table-body for array field {field_key!r}.")

    for nested_key, nested_value in item_properties.items():
        if not isinstance(nested_value, dict):
            # A table column must still be an object schema; use the smallest
            # visible string column rather than inventing domain-specific fields.
            item_properties[nested_key] = {
                "type": "string",
                "title": nested_key,
                "hideTitle": True,
                "widget": {"id": "string"},
            }
            warnings.append(
                f"Replaced non-object nested field {field_key}.{nested_key} with a string field."
            )
            continue
        if not nested_value.get("type"):
            nested_value["type"] = _infer_type(nested_value)
            warnings.append(f"Added type for nested field {field_key}.{nested_key}.")
        if not isinstance(nested_value.get("widget"), dict):
            nested_value["widget"] = {"id": _default_widget_for_field(nested_value)}
            warnings.append(f"Added widget.id for nested field {field_key}.{nested_key}.")
        elif not nested_value["widget"].get("id"):
            nested_value["widget"]["id"] = _default_widget_for_field(nested_value)
            warnings.append(f"Added widget.id for nested field {field_key}.{nested_key}.")
        else:
            _normalize_widget_alias(nested_value, f"{field_key}.{nested_key}", warnings)
        _promote_select_keys_from_widget(nested_value, f"{field_key}.{nested_key}", warnings)
        warnings.extend(
            validate_javascript_expression(
                expression_from_field(nested_value),
                field_key=f"{field_key}.{nested_key}",
            )
        )

    if "fieldsets" not in items:
        items["fieldsets"] = [
            {
                "id": f"{field_key}-fieldset-default",
                "title": field.get("title") or field_key,
                "description": "",
                "name": "",
                "fields": list(item_properties.keys()),
            }
        ]
        warnings.append(f"Added fieldsets for array field {field_key!r}.")
    elif not isinstance(items.get("fieldsets"), list):
        items["fieldsets"] = []
        warnings.append(f"Replaced invalid items.fieldsets for array field {field_key!r}.")
