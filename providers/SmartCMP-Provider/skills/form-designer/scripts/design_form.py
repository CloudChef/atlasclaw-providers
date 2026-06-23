#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Normalize and present a SmartCMP Angular form schema draft."""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import requests


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


def _load_sibling_module(module_filename: str, module_name: str) -> Any:
    """Load a sibling script without permanently changing global import paths."""
    return _load_module_from_path(Path(__file__).with_name(module_filename), module_name)


try:
    from _common import require_config
except ModuleNotFoundError as exc:
    if exc.name != "_common":
        raise
    _common = _load_module_from_path(
        Path(__file__).resolve().parents[2] / "shared" / "scripts" / "_common.py",
        "_smartcmp_form_designer_common",
    )
    require_config = _common.require_config


try:
    from _catalog_fields import build_catalog_field_schema, resolve_catalog_field_alias
except ModuleNotFoundError as exc:
    if exc.name != "_catalog_fields":
        raise
    _catalog_fields = _load_sibling_module(
        "_catalog_fields.py",
        "_smartcmp_form_designer_catalog_fields",
    )
    build_catalog_field_schema = _catalog_fields.build_catalog_field_schema
    resolve_catalog_field_alias = _catalog_fields.resolve_catalog_field_alias

try:
    from _catalog_context_sync import apply_catalog_context_sync
except ModuleNotFoundError as exc:
    if exc.name != "_catalog_context_sync":
        raise
    _catalog_context_sync = _load_sibling_module(
        "_catalog_context_sync.py",
        "_smartcmp_form_designer_catalog_context_sync",
    )
    apply_catalog_context_sync = _catalog_context_sync.apply_catalog_context_sync

try:
    from _form_fetch import fetch_form_definition, parse_form_edit_url
except ModuleNotFoundError as exc:
    if exc.name != "_form_fetch":
        raise
    _form_fetch = _load_sibling_module("_form_fetch.py", "_smartcmp_form_designer_form_fetch")
    fetch_form_definition = _form_fetch.fetch_form_definition
    parse_form_edit_url = _form_fetch.parse_form_edit_url

try:
    from _schema_normalize import SchemaNormalizationError, normalize_schema
except ModuleNotFoundError as exc:
    if exc.name != "_schema_normalize":
        raise
    _schema_normalize = _load_sibling_module(
        "_schema_normalize.py",
        "_smartcmp_form_designer_schema_normalize",
    )
    SchemaNormalizationError = _schema_normalize.SchemaNormalizationError
    normalize_schema = _schema_normalize.normalize_schema


def _load_schema(schema_json: str) -> dict[str, Any]:
    """Parse a draft schema JSON string."""
    try:
        parsed = json.loads(schema_json)
    except json.JSONDecodeError as error:
        raise ValueError(f"schema_json is not valid JSON: {error}") from error
    if not isinstance(parsed, dict):
        raise ValueError("schema_json must be a JSON object.")
    return parsed


def _apply_catalog_fields(schema: dict[str, Any], catalog_fields_json: str) -> list[str]:
    """Insert requested SmartCMP catalog fields into a draft schema.

    Args:
        schema: Mutable schema object whose top-level `properties` receives
            deterministic catalog field templates.
        catalog_fields_json: JSON array of field insertion requests. Blank
            input leaves the schema unchanged.

    Returns:
        Warnings for ignored malformed requests and unknown catalog fields.

    Raises:
        ValueError: If the request JSON or target schema shape cannot support
            deterministic field insertion.
    """
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
                if (
                    requested_field_key
                    and requested_field_key != definition.default_field_key
                ):
                    warnings.append(
                        "Custom fieldKey "
                        f"{requested_field_key!r} for catalog field "
                        f"{definition.canonical_key!r} differs from SmartCMP "
                        f"UI key {definition.default_field_key!r}; backend "
                        "standard-field handling may not recognize it."
                    )
            target_key = field_key or definition.default_field_key
            previous_canonical_key = requested_targets.get(target_key)
            if (
                previous_canonical_key is not None
                and previous_canonical_key != definition.canonical_key
            ):
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

    return warnings


_BEHAVIORAL_FIELD_KEYS = frozenset(("condition", "hidden", "selectDatas", "value"))
_STRUCTURAL_TEMPLATE_KEYS = frozenset(("description", "id", "items", "title", "type", "widget"))


def _merge_existing_catalog_field(
    properties: dict[str, Any],
    field: dict[str, Any],
    warnings: list[str],
    explicit_replace_keys: set[str],
) -> None:
    """Merge a catalog template with an existing field of the same schema key.

    Catalog templates intentionally own structural keys such as `type`, `widget`,
    and catalog metadata. Existing forms, however, may attach behavior such as
    JavaScript expressions, conditions, visibility, or select metadata to that
    same SmartCMP UI field. Preserve existing behavior unless the caller made an
    explicit catalog-field request for a supported replacement.
    """
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


def _empty_schema_warning(mode: str) -> tuple[dict[str, Any], list[str]]:
    """Return an empty schema when callers omit schema_json."""
    return (
        {"type": "object", "properties": {}, "widget": {"id": "object"}},
        [
            (
                "No schema_json was provided; returned an empty normalized schema. "
                f"The LLM should provide a complete draft schema for {mode} mode."
            )
        ],
    )


def _source_schema_from_url(form_url: str) -> tuple[dict[str, Any], dict[str, str]]:
    """Read the source schema for modify mode when no draft schema is supplied."""
    base_url, _auth_token, headers, _instance = require_config()
    form = fetch_form_definition(form_url, base_url, headers)
    return form.schema, {"formId": form.form_id, "name": form.name}


def _validate_source_url(form_url: str) -> dict[str, str]:
    """Validate a source form URL without reading CMP."""
    if not form_url:
        return {}
    base_url, _auth_token, _headers, _instance = require_config()
    source = parse_form_edit_url(form_url, base_url)
    return {"formId": source.form_id}


def main(argv: list[str] | None = None) -> int:
    """Run the SmartCMP form schema design tool."""
    parser = argparse.ArgumentParser(description="Normalize a SmartCMP Angular form schema draft.")
    parser.add_argument("--mode", choices=("new", "modify", "regenerate"), required=True)
    parser.add_argument("--schema-json", default="", help="Complete form schema JSON draft.")
    parser.add_argument(
        "--catalog-fields-json",
        default="",
        help="Optional JSON array of SmartCMP catalog standard fields to insert.",
    )
    parser.add_argument(
        "--catalog-context-sync-json",
        default="",
        help="Optional JSON object for SmartCMP catalog context sync field generation.",
    )
    parser.add_argument("--form-url", default="", help="Optional source form edit URL for modify mode.")
    parser.add_argument("--change-summary", default="", help="Short user-facing change summary.")
    args = parser.parse_args(argv)

    warnings: list[str] = []
    source: dict[str, str] = {}

    try:
        if args.mode == "regenerate" and not args.schema_json:
            raise ValueError(
                "schema_json is required for regenerate mode. Read the source form separately, "
                "then pass the complete replacement schema_json generated from the user's requirements."
            )

        if args.schema_json:
            schema = _load_schema(args.schema_json)
            # A provided source URL is provenance only for this path. Validate it,
            # but keep the caller-provided draft as the authoritative schema.
            source = _validate_source_url(args.form_url)
        elif args.mode == "modify" and args.form_url:
            # This fallback avoids asking the LLM to copy long existing schemas
            # when the requested change can be handled deterministically.
            schema, source = _source_schema_from_url(args.form_url)
            if args.catalog_fields_json.strip():
                warnings.append(
                    "No schema_json was provided; loaded the source form before "
                    "deterministic catalog field insertion."
                )
            else:
                warnings.append(
                    "No schema_json was provided; normalized the source form without changes."
                )
        else:
            schema, warnings = _empty_schema_warning(args.mode)

        warnings.extend(_apply_catalog_fields(schema, args.catalog_fields_json))
        context_warnings, context_summary = apply_catalog_context_sync(
            schema,
            args.catalog_context_sync_json,
        )
        warnings.extend(context_warnings)
        if context_summary:
            warnings.append(context_summary)
        schema, normalization_warnings = normalize_schema(schema)
        warnings.extend(normalization_warnings)
    except (
        ValueError,
        SchemaNormalizationError,
        requests.RequestException,
    ) as error:
        print(f"[ERROR] {error}")
        return 1

    summary = args.change_summary.strip()
    if not summary:
        if args.mode == "new":
            summary = "Generated a new SmartCMP form schema."
        elif args.mode == "regenerate":
            summary = "Regenerated a replacement SmartCMP form schema."
        else:
            summary = "Prepared a normalized SmartCMP form schema."

    print("Change Summary:")
    print(summary)
    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"- {warning}")
    print("\nSchema JSON:")
    print("```json")
    print(json.dumps(schema, ensure_ascii=False, indent=2))
    print("```")

    meta = {
        "mode": args.mode,
        "source": source,
        "warnings": warnings,
        "changeSummary": summary,
        "schema": schema,
    }
    print("##FORM_DESIGN_META_START##", file=sys.stderr)
    print(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
    print("##FORM_DESIGN_META_END##", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
