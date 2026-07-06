#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Insert SmartCMP service-catalog standard fields into form schemas."""

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
    from _catalog_fields import build_catalog_field_schema, resolve_catalog_field_alias
except ModuleNotFoundError as exc:
    if exc.name != "_catalog_fields":
        raise
    _catalog_fields = _load_module_from_path(
        Path(__file__).with_name("_catalog_fields.py"),
        "_smartcmp_form_designer_catalog_fields",
    )
    build_catalog_field_schema = _catalog_fields.build_catalog_field_schema
    resolve_catalog_field_alias = _catalog_fields.resolve_catalog_field_alias

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


def apply_catalog_fields(schema: dict[str, Any], catalog_fields_json: str) -> list[str]:
    """Insert requested SmartCMP catalog fields into a draft schema."""
    if not catalog_fields_json.strip():
        return []

    try:
        requests_json = json.loads(catalog_fields_json)
    except json.JSONDecodeError as error:
        raise ValueError(f"catalog_fields_json is not valid JSON: {error}") from error
    if not isinstance(requests_json, list):
        raise ValueError("catalog_fields_json must be a JSON array.")

    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise ValueError(
            "schema.properties must be an object before catalog fields can be inserted."
        )

    warnings: list[str] = []
    requested_targets: dict[str, str] = {}
    for request in requests_json:
        if not isinstance(request, dict):
            warnings.append("Ignored non-object catalog field request.")
            continue

        try:
            field_value = request.get("field")
            definition = resolve_catalog_field_alias(field_value)
            if definition is None:
                raise ValueError(f"Unknown SmartCMP catalog field: {field_value}")

            requested_field_key = request.get("fieldKey")
            field_key = None
            if isinstance(requested_field_key, str):
                requested_field_key = requested_field_key.strip()
                field_key = requested_field_key or None
                if requested_field_key and requested_field_key != definition.default_field_key:
                    warnings.append(
                        "Custom fieldKey "
                        f"{requested_field_key!r} for catalog field "
                        f"{definition.canonical_key!r} differs from SmartCMP "
                        f"UI key {definition.default_field_key!r}; backend "
                        "standard-field handling may not recognize it."
                    )
            target_key = field_key or definition.default_field_key
            previous_canonical_key = requested_targets.get(target_key)
            if previous_canonical_key is not None and previous_canonical_key != definition.canonical_key:
                warnings.append(
                    "Multiple catalog field requests "
                    f"{previous_canonical_key!r} and "
                    f"{definition.canonical_key!r} target schema key "
                    f"{target_key!r}; keeping a single SmartCMP UI field. "
                    "Use explicit custom fieldKey values when separate "
                    "display-only projections are required."
                )
                aggregate_definition = resolve_catalog_field_alias(target_key)
                if (
                    aggregate_definition is not None
                    and aggregate_definition.default_field_key == target_key
                ):
                    definition = aggregate_definition
                    field_key = target_key
            else:
                requested_targets[target_key] = definition.canonical_key

            language = request.get("language", "zh")
            hidden = request.get("hidden", False)
            field = build_catalog_field_schema(
                definition.canonical_key,
                field_key=field_key,
                language=language if isinstance(language, str) else "zh",
                hidden=hidden if isinstance(hidden, bool) else False,
            )
        except ValueError as error:
            warnings.append(str(error))
            continue
        explicit_replace_keys = {"hidden"} if hidden is True else set()
        _merge_existing_catalog_field(properties, field, warnings, explicit_replace_keys)
        properties[field["id"]] = field
        ensure_field_in_root_fieldsets(schema, field["id"], warnings)

    return warnings


_BEHAVIORAL_FIELD_KEYS = frozenset(("condition", "hidden", "selectDatas", "value"))
_STRUCTURAL_TEMPLATE_KEYS = frozenset(("description", "id", "items", "title", "type", "widget"))


def _merge_existing_catalog_field(
    properties: dict[str, Any],
    field: dict[str, Any],
    warnings: list[str],
    explicit_replace_keys: set[str],
) -> None:
    """Merge a catalog template with an existing field of the same schema key."""
    existing = properties.get(field["id"])
    if not isinstance(existing, dict):
        return

    preserved_keys: list[str] = []
    preserved_behavior_keys: list[str] = []
    overwritten_structural_keys: list[str] = []
    for key, value in existing.items():
        if key == "config" and isinstance(value, dict) and isinstance(field.get(key), dict):
            field[key] = _merge_dict_preserving_existing(field[key], value)
            preserved_behavior_keys.append(key)
            continue

        if key not in field:
            field[key] = copy.deepcopy(value)
            preserved_keys.append(key)
            continue

        if key in _BEHAVIORAL_FIELD_KEYS and key not in explicit_replace_keys:
            field[key] = copy.deepcopy(value)
            preserved_behavior_keys.append(key)
        elif key in _STRUCTURAL_TEMPLATE_KEYS and field.get(key) != value:
            overwritten_structural_keys.append(key)

    if preserved_keys:
        warnings.append(
            "Preserved unknown keys while replacing existing catalog field "
            f"{field['id']!r}: {', '.join(preserved_keys)}."
        )
    if preserved_behavior_keys:
        warnings.append(
            "Preserved existing behavior while replacing catalog field "
            f"{field['id']!r}: {', '.join(preserved_behavior_keys)}."
        )
    if overwritten_structural_keys:
        warnings.append(
            "Replaced existing structural keys with catalog template values "
            f"for field {field['id']!r}: {', '.join(overwritten_structural_keys)}."
        )


def _merge_dict_preserving_existing(
    template: dict[str, Any],
    existing: dict[str, Any],
) -> dict[str, Any]:
    """Return a deep config merge where existing behavior wins over defaults."""
    merged = copy.deepcopy(template)
    for key, value in existing.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict_preserving_existing(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged
