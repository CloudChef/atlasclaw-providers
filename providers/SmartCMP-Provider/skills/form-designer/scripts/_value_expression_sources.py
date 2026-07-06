#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Resolve declarative value-expression source specs."""

from __future__ import annotations

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
    from _catalog_fields import resolve_catalog_field_alias
except ModuleNotFoundError as exc:
    if exc.name != "_catalog_fields":
        raise
    _catalog_fields = _load_module_from_path(
        Path(__file__).with_name("_catalog_fields.py"),
        "_smartcmp_form_designer_catalog_fields",
    )
    resolve_catalog_field_alias = _catalog_fields.resolve_catalog_field_alias


def parse_projection_fields(raw_fields: Any, warnings: list[str]) -> list[dict[str, Any]]:
    if not isinstance(raw_fields, list):
        return []

    fields: list[dict[str, Any]] = []
    for raw_field in raw_fields:
        if not isinstance(raw_field, dict):
            warnings.append("Ignored non-object projection field.")
            continue

        label = first_non_blank_string(
            raw_field.get("label"),
            raw_field.get("output"),
            raw_field.get("title"),
            raw_field.get("field"),
            raw_field.get("path"),
        )
        path = first_non_blank_string(raw_field.get("path"))
        labels: list[str] = []
        if path is None:
            source_field = first_non_blank_string(raw_field.get("field"), label)
            definition = _resolve_catalog_source_definition(source_field)
            if definition is not None:
                paths = list(definition.value_read_paths or (definition.default_field_key,))
                labels = _catalog_label_aliases(definition, label)
                path = paths[0] if len(paths) == 1 else paths
            else:
                paths = _paths_from_field_alias(source_field)
                path = paths[0] if paths and len(paths) == 1 else paths or source_field

        if label is None or path is None:
            warnings.append("Ignored projection field without label or path.")
            continue
        field_spec: dict[str, Any] = {"label": label, "path": path}
        if labels:
            field_spec["labels"] = labels
        fields.append(field_spec)

    return fields


def repair_fullwidth_json_punctuation(value: str) -> str:
    """Replace common full-width JSON separators only when outside string literals."""
    output: list[str] = []
    quote: str | None = None
    escaped = False
    changed = False

    for char in value:
        if quote is not None:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue

        if char in {'"', "'"}:
            quote = char
            output.append(char)
            continue

        if char == "，":
            output.append(",")
            changed = True
            continue
        if char == "：":
            output.append(":")
            changed = True
            continue
        output.append(char)

    return "".join(output) if changed else value


def resolve_compose_spec(value: Any, warnings: list[str], output_label: str | None = None) -> Any:
    """Resolve catalog field aliases inside a JSON composition spec."""
    if isinstance(value, list):
        return [resolve_compose_spec(item, warnings, output_label) for item in value]
    if not isinstance(value, dict):
        return value

    helper_keys = {"label", "labels", "$label", "$labels", "field", "path", "paths", "$paths"}
    if "$field" in value and set(value).issubset(helper_keys | {"$field"}):
        field_name = value.get("$field")
        label = first_non_blank_string(output_label, value.get("label"), field_name)
        return _source_reference_from_field_alias(
            field_name,
            label=label,
            warnings=warnings,
        )

    if "$path" in value and set(value).issubset(helper_keys | {"$path"}):
        path = value.get("$path")
        return {"$path": path.strip()} if isinstance(path, str) and path.strip() else {"$path": ""}

    if "field" in value and set(value).issubset(helper_keys):
        field_name = value.get("field")
        label = first_non_blank_string(output_label, value.get("label"), field_name)
        return _source_reference_from_field_alias(
            field_name,
            label=label,
            warnings=warnings,
        )

    if "path" in value and set(value).issubset(helper_keys):
        path = value.get("path")
        return {"$path": path.strip()} if isinstance(path, str) and path.strip() else {"$path": ""}

    marker_keys = {"$field", "$path", "field", "path", "$concat", "$literal"}
    used_marker_keys = marker_keys.intersection(value)
    if used_marker_keys and len(value) != 1:
        marker_list = ", ".join(sorted(used_marker_keys))
        raise ValueError(
            "source marker objects cannot include sibling output keys "
            f"({marker_list}); nest output keys outside the marker leaf."
        )

    if "$concat" in value:
        items = value.get("$concat")
        if not isinstance(items, list):
            warnings.append("Ignored non-array $concat composition; using an empty string.")
            return ""
        return {"$concat": [resolve_compose_spec(item, warnings, output_label) for item in items]}

    if "$literal" in value:
        return {"$literal": value.get("$literal")}

    return {
        key: resolve_compose_spec(item, warnings, key if isinstance(key, str) else output_label)
        for key, item in value.items()
    }


def first_non_blank_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _paths_from_field_alias(value: Any) -> list[str] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    definition = _resolve_catalog_source_definition(value)
    if definition is not None:
        return list(definition.value_read_paths or (definition.default_field_key,))
    return [value.strip()]


def _source_reference_from_field_alias(
    value: Any,
    *,
    label: Any = None,
    warnings: list[str],
) -> dict[str, Any]:
    if not isinstance(value, str) or not value.strip():
        warnings.append(f"Unknown projection source field {value!r}; using it as a model path.")
        return {"$path": str(value or "")}
    definition = _resolve_catalog_source_definition(value)
    if definition is not None:
        return _source_reference_from_paths(
            list(definition.value_read_paths or (definition.default_field_key,)),
            label=label,
            labels=_catalog_label_aliases(definition, label),
        )
    return _source_reference_from_paths([value.strip()], label=label)


def _resolve_catalog_source_definition(value: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return None
    return resolve_catalog_field_alias(value)


def _catalog_label_aliases(definition: Any, primary_label: Any = None) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for value in (
        primary_label,
        definition.title_zh,
        definition.title_en,
        definition.canonical_key,
        definition.default_field_key,
        *definition.aliases,
    ):
        if not isinstance(value, str) or not value.strip():
            continue
        label = value.strip()
        if label in seen:
            continue
        labels.append(label)
        seen.add(label)
    return labels


def _source_reference_from_paths(
    paths: list[str],
    *,
    label: Any = None,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    cleaned_paths = [path for path in paths if isinstance(path, str) and path.strip()]
    if not cleaned_paths:
        return {"$path": ""}
    reference: dict[str, Any]
    if len(cleaned_paths) == 1:
        reference = {"$path": cleaned_paths[0]}
    else:
        reference = {"$paths": cleaned_paths}
    if isinstance(label, str) and label.strip():
        reference["$label"] = label.strip()
    if labels:
        reference["$labels"] = labels
    return reference
