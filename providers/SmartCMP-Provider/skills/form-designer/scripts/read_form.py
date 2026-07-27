#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Read a SmartCMP form schema from a UI edit URL."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

import requests

try:
    from pydantic_ai import RunContext
except ImportError:  # Provider-only unit tests do not install the Core runtime.
    RunContext = Any

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
    from _schema_normalize import normalize_schema
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _form_fetch import fetch_form_definition, parse_form_edit_url
    from _schema_normalize import normalize_schema

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "shared", "scripts")
    ),
)

from _current_page_object import (  # noqa: E402
    CurrentPageObjectError,
    embedded_object_id,
    selected_provider_read_config,
)


def _form_read_result(form: Any) -> dict[str, Any]:
    """Render a fetched form definition as a structured read-only Tool result."""
    schema, warnings = normalize_schema(form.schema)
    lines = [
        f"SmartCMP Form: {form.name or form.form_id}",
        f"Form ID: {form.form_id}",
    ]
    if form.design_mode or form.model or form.component_count:
        lines.extend(["", "Content Context:"])
        if form.design_mode:
            lines.append(f"- Design Mode: {form.design_mode}")
        if form.model:
            lines.append(f"- Model Keys: {', '.join(sorted(form.model))}")
        if form.component_count:
            lines.append(f"- Component Count: {form.component_count}")
    if warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in warnings)
    lines.extend(
        [
            "",
            "Schema JSON:",
            "```json",
            json.dumps(schema, ensure_ascii=False, indent=2),
            "```",
        ]
    )
    return {
        "success": True,
        "output": "\n".join(lines),
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


async def read_form(
    ctx: RunContext[Any],
    form_url: str,
) -> dict[str, Any]:
    """Read one URL-selected form without permitting an embedded cross-object read.

    Args:
        ctx: AtlasClaw request Context and selected SmartCMP instance.
        form_url: Current-instance SmartCMP form edit or design URL.

    Returns:
        Complete normalized schema or a validation/read error.
    """
    try:
        context_form_id = embedded_object_id(
            ctx,
            expected_object_type="form_definition",
        )
        base_url, headers, timeout = await asyncio.to_thread(
            selected_provider_read_config,
            ctx,
            request_cookie_only=context_form_id is not None,
        )
        source = parse_form_edit_url(form_url, base_url)
        if context_form_id is not None and source.form_id != context_form_id:
            raise CurrentPageObjectError(
                "form_url does not match the current SmartCMP form page Context."
            )
        form = await asyncio.to_thread(
            fetch_form_definition,
            form_url,
            base_url,
            headers,
            timeout=timeout,
        )
        return _form_read_result(form)
    except (CurrentPageObjectError, ValueError, requests.RequestException) as error:
        return {"success": False, "error": str(error)}


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
        result = _form_read_result(form)
    except (ValueError, requests.RequestException) as error:
        print(f"[ERROR] {error}")
        return 1

    print(result["output"])

    meta = {
        key: value
        for key, value in result.items()
        if key not in {"success", "output"}
    }
    print("##FORM_SCHEMA_META_START##", file=sys.stderr)
    print(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
    print("##FORM_SCHEMA_META_END##", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
