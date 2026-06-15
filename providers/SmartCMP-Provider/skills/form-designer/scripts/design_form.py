#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Normalize and present a SmartCMP Angular form schema draft."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import requests

try:
    from _common import require_config
except ImportError:
    sys.path.insert(
        0,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared", "scripts"),
    )
    from _common import require_config

try:
    from _form_fetch import fetch_form_definition, parse_form_edit_url
    from _schema_normalize import SchemaNormalizationError, normalize_schema
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _form_fetch import fetch_form_definition, parse_form_edit_url
    from _schema_normalize import SchemaNormalizationError, normalize_schema


def _load_schema(schema_json: str) -> dict[str, Any]:
    """Parse a draft schema JSON string."""
    try:
        parsed = json.loads(schema_json)
    except json.JSONDecodeError as error:
        raise ValueError(f"schema_json is not valid JSON: {error}") from error
    if not isinstance(parsed, dict):
        raise ValueError("schema_json must be a JSON object.")
    return parsed


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
    parser.add_argument("--mode", choices=("new", "modify"), required=True)
    parser.add_argument("--schema-json", default="", help="Complete form schema JSON draft.")
    parser.add_argument("--form-url", default="", help="Optional source form edit URL for modify mode.")
    parser.add_argument("--change-summary", default="", help="Short user-facing change summary.")
    args = parser.parse_args(argv)

    warnings: list[str] = []
    source: dict[str, str] = {}

    try:
        if args.schema_json:
            schema = _load_schema(args.schema_json)
            # A provided source URL is provenance only for this path. Validate it,
            # but keep the caller-provided draft as the authoritative schema.
            source = _validate_source_url(args.form_url)
        elif args.mode == "modify" and args.form_url:
            # This fallback supports read/normalize inspection. Real modifications
            # should still be supplied by the LLM through schema_json.
            schema, source = _source_schema_from_url(args.form_url)
            warnings.append("No schema_json was provided; normalized the source form without changes.")
        else:
            schema, warnings = _empty_schema_warning(args.mode)

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
        summary = (
            "Generated a new SmartCMP form schema."
            if args.mode == "new"
            else "Prepared a normalized SmartCMP form schema."
        )

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
