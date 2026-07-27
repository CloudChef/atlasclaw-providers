# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Read the saved form bound to the current SmartCMP page Context."""

from __future__ import annotations

import json
import os
import sys
from typing import Any


try:
    from pydantic_ai import RunContext
except ImportError:  # Provider-only unit tests do not install the Core runtime.
    RunContext = Any


sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "shared", "scripts")
    ),
)

from _current_page_object import (  # noqa: E402
    CurrentPageObjectError,
    fetch_current_page_object,
)
from _form_fetch import extract_model_from_payload, extract_schema_from_payload  # noqa: E402
from _schema_normalize import normalize_schema  # noqa: E402


async def read_current_form(ctx: RunContext[Any]) -> dict[str, Any]:
    """Return the current saved form schema for user-directed replacement drafting."""
    try:
        payload = await fetch_current_page_object(
            ctx,
            expected_object_type="form_definition",
            api_collection="forms",
        )
        schema, warnings = normalize_schema(extract_schema_from_payload(payload))
    except (CurrentPageObjectError, ValueError) as exc:
        return {"success": False, "error": str(exc)}

    content = payload.get("content")
    content = content if isinstance(content, dict) else {}
    model = extract_model_from_payload(payload)
    lines = [
        f"Current saved SmartCMP form: {payload.get('name') or payload['id']}",
        f"Form ID: {payload['id']}",
        "",
        "Schema JSON:",
        "```json",
        json.dumps(schema, ensure_ascii=False, indent=2),
        "```",
    ]
    if warnings:
        lines.extend(["", "Normalization warnings:"])
        lines.extend(f"- {warning}" for warning in warnings)
    return {
        "success": True,
        "output": "\n".join(lines),
        "form": {
            "id": payload["id"],
            "name": str(payload.get("name") or ""),
            "description": str(payload.get("description") or ""),
            "model": model,
            "designMode": str(content.get("designMode") or ""),
            "componentCount": len(content.get("components"))
            if isinstance(content.get("components"), list)
            else 0,
            "schema": schema,
        },
    }
