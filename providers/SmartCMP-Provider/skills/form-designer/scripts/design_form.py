#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Normalize and present a SmartCMP Angular form schema draft."""

from __future__ import annotations

import argparse
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
    from _catalog_insertions import apply_catalog_fields
except ModuleNotFoundError as exc:
    if exc.name != "_catalog_insertions":
        raise
    _catalog_insertions = _load_sibling_module(
        "_catalog_insertions.py",
        "_smartcmp_form_designer_catalog_insertions",
    )
    apply_catalog_fields = _catalog_insertions.apply_catalog_fields

try:
    from _value_expressions import apply_value_expressions
except ModuleNotFoundError as exc:
    if exc.name != "_value_expressions":
        raise
    _value_expressions = _load_sibling_module(
        "_value_expressions.py",
        "_smartcmp_form_designer_value_expressions",
    )
    apply_value_expressions = _value_expressions.apply_value_expressions

try:
    from _schema_layout import ensure_schema_form_valid_control
except ModuleNotFoundError as exc:
    if exc.name != "_schema_layout":
        raise
    _schema_layout = _load_sibling_module(
        "_schema_layout.py",
        "_smartcmp_form_designer_schema_layout",
    )
    ensure_schema_form_valid_control = _schema_layout.ensure_schema_form_valid_control

try:
    from _requested_fields import constrain_schema_to_requested_fields, load_requested_fields
except ModuleNotFoundError as exc:
    if exc.name != "_requested_fields":
        raise
    _requested_fields = _load_sibling_module(
        "_requested_fields.py",
        "_smartcmp_form_designer_requested_fields",
    )
    constrain_schema_to_requested_fields = _requested_fields.constrain_schema_to_requested_fields
    load_requested_fields = _requested_fields.load_requested_fields

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


def _raise_for_fatal_warnings(
    warnings: list[str],
    *,
    form_url: str = "",
    value_expressions_json: str = "",
) -> None:
    fatal_warnings = [
        warning
        for warning in warnings
        if "literal ellipsis placeholder" in warning or "JavaScript syntax" in warning
    ]
    if fatal_warnings:
        raise ValueError(
            "Generated schema contains abbreviated JavaScript. "
            "Use value_expressions_json or provide a complete function string. "
            + " ".join(fatal_warnings)
        )

    unresolved_context_warnings = [
        warning
        for warning in warnings
        if (
            "which is not a schema property" in warning
            or "uses an unverified sourceParams context container" in warning
            or "uses an unverified runtime context container" in warning
            or (warning.startswith("Value expression for field ") and not form_url.strip())
        )
    ]
    if unresolved_context_warnings:
        raise ValueError(
            "Generated schema contains JavaScript that can submit empty values "
            "because it reads unresolved service-catalog context. "
            + " ".join(unresolved_context_warnings)
        )

    if form_url.strip() and not value_expressions_json.strip():
        legacy_expression_warnings = [
            warning
            for warning in warnings
            if (
                "is not a function(model, sourceParams, schema, unused, cfg)"
                in warning
                or "does not assign model[" in warning
                or warning.startswith("Value expression for field ")
            )
        ]
        if legacy_expression_warnings:
            raise ValueError(
                "URL-based form changes cannot use legacy JavaScript expressions. "
                "Use value_expressions_json for deterministic catalog/model value "
                "updates, or provide a complete function(model, sourceParams, "
                "schema, unused, cfg) expression that writes model[fieldKey]. "
                + " ".join(legacy_expression_warnings)
            )


_ROUTINE_VISIBLE_WARNING_PREFIXES = (
    "Added root widget.id=object.",
    "Changed widget.id=text to string for field ",
    "Added config.visibility for field ",
    "Added allowInRequest=true for field ",
    "Added allowInApproval=true for field ",
    "Set root fieldset id=fieldset-default for catalog request compatibility.",
    "Removed root fieldset index for catalog request compatibility.",
    "Canonicalized root fieldset field order for catalog request compatibility.",
    "Set catalog request field index=",
    "Removed schemaFormValid index for catalog request compatibility.",
)


def _visible_warnings(warnings: list[str]) -> list[str]:
    return [
        warning
        for warning in warnings
        if not any(
            warning.startswith(prefix)
            for prefix in _ROUTINE_VISIBLE_WARNING_PREFIXES
        )
    ]


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


def _source_schema_from_url(form_url: str) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Read the source schema for modify mode when no draft schema is supplied."""
    base_url, _auth_token, headers, _instance = require_config()
    form = fetch_form_definition(form_url, base_url, headers)
    warnings: list[str] = []
    if form.component_count:
        warnings.append(
            "Source form contains visual designer components; schema-only replacement "
            "can be overwritten by SmartCMP visual designer component state. "
            "Review component/designMode state before saving the form."
        )
    if form.model:
        keys = ", ".join(sorted(form.model))
        warnings.append(
            "Source form content.model has existing keys "
            f"({keys}); value expressions must overwrite target model values at runtime."
        )
    return (
        form.schema,
        {
            "formId": form.form_id,
            "name": form.name,
            "route": form.source_route,
            "designMode": form.design_mode,
            "modelKeys": sorted(form.model),
            "componentCount": form.component_count,
        },
        warnings,
    )


def _validate_source_url(form_url: str) -> dict[str, str]:
    """Validate a source form URL without reading CMP."""
    if not form_url:
        return {}
    base_url, _auth_token, _headers, _instance = require_config()
    source = parse_form_edit_url(form_url, base_url)
    return {"formId": source.form_id, "route": source.route}


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
        "--value-expressions-json",
        default="",
        help="Optional JSON array of target fields whose values project and compose model paths.",
    )
    parser.add_argument(
        "--requested-fields-json",
        default="",
        help="Optional JSON array of exact top-level form fields requested by the user.",
    )
    parser.add_argument("--form-url", default="", help="Optional source form edit URL for modify mode.")
    parser.add_argument("--change-summary", default="", help="Short user-facing change summary.")
    args = parser.parse_args(argv)

    warnings: list[str] = []
    source: dict[str, str] = {}

    try:
        requested_fields = load_requested_fields(args.requested_fields_json)

        if args.mode == "modify" and not args.schema_json and not args.form_url:
            raise ValueError(
                "schema_json or form_url is required for modify mode. "
                "Provide complete JSON to normalize, or provide a source form edit URL "
                "for deterministic catalog field insertion or value expression updates."
            )

        if args.mode in {"new", "regenerate"} and not args.schema_json:
            raise ValueError(
                f"schema_json is required for {args.mode} mode. "
                "Generate the complete schema_json from the user's requirements before calling this tool."
            )

        if args.schema_json:
            schema = _load_schema(args.schema_json)
            # A provided source URL is provenance only for this path. Validate it,
            # but keep the caller-provided draft as the authoritative schema.
            source = _validate_source_url(args.form_url)
        elif args.mode == "modify" and args.form_url:
            # This fallback avoids asking the LLM to copy long existing schemas
            # when the requested change can be handled deterministically.
            schema, source, source_warnings = _source_schema_from_url(args.form_url)
            warnings.extend(source_warnings)
            if args.value_expressions_json.strip():
                warnings.append(
                    "No schema_json was provided; loaded the source form before "
                    "deterministic value expression update."
                )
            elif args.catalog_fields_json.strip():
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

        warnings.extend(constrain_schema_to_requested_fields(schema, requested_fields))
        warnings.extend(apply_catalog_fields(schema, args.catalog_fields_json))
        warnings.extend(apply_value_expressions(schema, args.value_expressions_json))
        warnings.extend(
            constrain_schema_to_requested_fields(schema, requested_fields, require_all=True)
        )
        schema, normalization_warnings = normalize_schema(schema)
        warnings.extend(normalization_warnings)
        ensure_schema_form_valid_control(schema, warnings)
        _raise_for_fatal_warnings(
            warnings,
            form_url=args.form_url,
            value_expressions_json=args.value_expressions_json,
        )
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
    if args.form_url:
        print("\nApply Note:")
        print(
            "This tool does not save changes to CMP. Review and copy the "
            "replacement Schema JSON into the SmartCMP form editor manually."
        )
    visible_warnings = _visible_warnings(warnings)
    if visible_warnings:
        print("\nWarnings:")
        for warning in visible_warnings:
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
