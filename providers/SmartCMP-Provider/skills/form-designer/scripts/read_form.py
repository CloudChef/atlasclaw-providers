#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Read a SmartCMP form schema from a UI edit URL."""

from __future__ import annotations

import argparse
import json
import os
import sys

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
    from _form_fetch import fetch_form_definition
    from _schema_normalize import normalize_schema
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _form_fetch import fetch_form_definition
    from _schema_normalize import normalize_schema


def main(argv: list[str] | None = None) -> int:
    """Run the read-only SmartCMP form schema tool."""
    parser = argparse.ArgumentParser(description="Read a SmartCMP form schema from a UI edit URL.")
    parser.add_argument("form_url", help="SmartCMP UI URL: #/main/service-model/forms/edit/<uuid>")
    args = parser.parse_args(argv)

    try:
        base_url, _auth_token, headers, _instance = require_config()
        # Read-only boundary: the tool obtains the current schema, normalizes it
        # locally, and returns text for the user to copy. No CMP persistence call
        # happens in this script.
        form = fetch_form_definition(args.form_url, base_url, headers)
        schema, warnings = normalize_schema(form.schema)
    except (ValueError, requests.RequestException) as error:
        print(f"[ERROR] {error}")
        return 1

    print(f"SmartCMP Form: {form.name or form.form_id}")
    print(f"Form ID: {form.form_id}")
    if form.design_mode or form.model or form.component_count:
        print("\nContent Context:")
        if form.design_mode:
            print(f"- Design Mode: {form.design_mode}")
        if form.model:
            print(f"- Model Keys: {', '.join(sorted(form.model))}")
        if form.component_count:
            print(f"- Component Count: {form.component_count}")
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")
    print("\nSchema JSON:")
    print("```json")
    print(json.dumps(schema, ensure_ascii=False, indent=2))
    print("```")

    meta = {
        "source": {
            "formId": form.form_id,
            "route": form.source_route,
        },
        "formId": form.form_id,
        "name": form.name,
        "description": form.description,
        "contentKeys": form.raw_content_keys,
        "model": form.model,
        "designMode": form.design_mode,
        "componentCount": form.component_count,
        "warnings": warnings,
        "schema": schema,
    }
    print("##FORM_SCHEMA_META_START##", file=sys.stderr)
    print(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
    print("##FORM_SCHEMA_META_END##", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
