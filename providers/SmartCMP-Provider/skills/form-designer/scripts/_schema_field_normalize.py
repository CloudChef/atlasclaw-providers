#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Normalize SmartCMP field-level schema details."""

from __future__ import annotations

import copy
import importlib.util
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
    from _schema_js_fields import iter_field_javascript
except ModuleNotFoundError as exc:
    if exc.name != "_schema_js_fields":
        raise
    _schema_js_fields = _load_module_from_path(
        Path(__file__).with_name("_schema_js_fields.py"),
        "_smartcmp_form_designer_schema_js_fields",
    )
    iter_field_javascript = _schema_js_fields.iter_field_javascript

try:
    from _schema_js_validate import validate_javascript_expression
except ModuleNotFoundError as exc:
    if exc.name != "_schema_js_validate":
        raise
    _schema_js_validate = _load_module_from_path(
        Path(__file__).with_name("_schema_js_validate.py"),
        "_smartcmp_form_designer_schema_js_validate",
    )
    validate_javascript_expression = _schema_js_validate.validate_javascript_expression


def infer_type(field: dict[str, Any]) -> str:
    widget = field.get("widget") if isinstance(field.get("widget"), dict) else {}
    widget_id = str(widget.get("id") or "").strip()
    if widget_id == "number":
        return "number"
    if field.get("items") is not None or widget_id == "table-head":
        return "array"
    return "string"


def normalize_widget(field: dict[str, Any], field_key: str, warnings: list[str]) -> None:
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
    _promote_widget_config(field, field_key, warnings)


def is_table_array_field(field: dict[str, Any]) -> bool:
    widget = field.get("widget") if isinstance(field.get("widget"), dict) else {}
    widget_id = str(widget.get("id") or "").strip()
    return widget_id == "table-head" or isinstance(field.get("items"), dict)


def normalize_visibility(field: dict[str, Any], field_key: str, warnings: list[str]) -> None:
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


def normalize_array_field(field: dict[str, Any], field_key: str, warnings: list[str]) -> None:
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

    _normalize_array_item_properties(field_key, item_properties, warnings)
    _normalize_array_fieldsets(field, field_key, item_properties, warnings)


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


def _promote_widget_config(
    field: dict[str, Any],
    field_key: str,
    warnings: list[str],
) -> None:
    widget = field.get("widget")
    if not isinstance(widget, dict):
        return

    widget_config = widget.get("config")
    if not isinstance(widget_config, dict):
        return

    field_config = field.get("config")
    if isinstance(field_config, dict):
        field["config"] = _merge_dict_preserving_existing(widget_config, field_config)
    else:
        field["config"] = copy.deepcopy(widget_config)
    widget.pop("config", None)
    warnings.append(f"Moved widget.config to field-level config for field {field_key!r}.")


def _merge_dict_preserving_existing(
    template: dict[str, Any],
    existing: dict[str, Any],
) -> dict[str, Any]:
    merged = copy.deepcopy(template)
    for key, value in existing.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict_preserving_existing(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _default_widget_for_field(field: dict[str, Any]) -> str:
    field_type = field.get("type")
    if field_type == "array":
        return "table-head"
    if field_type == "number":
        return "number"
    return "string"


def _normalize_array_item_properties(
    field_key: str,
    item_properties: dict[str, Any],
    warnings: list[str],
) -> None:
    for nested_key, nested_value in item_properties.items():
        nested_path = f"{field_key}.{nested_key}"
        if not isinstance(nested_value, dict):
            item_properties[nested_key] = {
                "type": "string",
                "title": nested_key,
                "hideTitle": True,
                "widget": {"id": "string"},
            }
            warnings.append(f"Replaced non-object nested field {nested_path} with a string field.")
            continue
        _normalize_nested_field(nested_value, nested_path, warnings)


def _normalize_nested_field(
    nested_value: dict[str, Any],
    nested_path: str,
    warnings: list[str],
) -> None:
    if not nested_value.get("type"):
        nested_value["type"] = infer_type(nested_value)
        warnings.append(f"Added type for nested field {nested_path}.")
    if not isinstance(nested_value.get("widget"), dict):
        nested_value["widget"] = {"id": _default_widget_for_field(nested_value)}
        warnings.append(f"Added widget.id for nested field {nested_path}.")
    elif not nested_value["widget"].get("id"):
        nested_value["widget"]["id"] = _default_widget_for_field(nested_value)
        warnings.append(f"Added widget.id for nested field {nested_path}.")
    else:
        _normalize_widget_alias(nested_value, nested_path, warnings)
    _promote_select_keys_from_widget(nested_value, nested_path, warnings)
    _promote_widget_config(nested_value, nested_path, warnings)
    for js_field_key, expression in iter_field_javascript(nested_value, nested_path):
        warnings.extend(validate_javascript_expression(expression, field_key=js_field_key))


def _normalize_array_fieldsets(
    field: dict[str, Any],
    field_key: str,
    item_properties: dict[str, Any],
    warnings: list[str],
) -> None:
    items = field["items"]
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
