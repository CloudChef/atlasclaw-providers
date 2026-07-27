# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Read the saved script bound to the current SmartCMP page Context."""

from __future__ import annotations

import json
import os
import re
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


def _code_language(payload: dict[str, Any]) -> str:
    script_type = str(payload.get("type") or "").strip().lower()
    name = str(payload.get("name") or "").strip().lower()
    if script_type == "python" or name.endswith(".py"):
        return "python"
    if script_type in {"shell", "bash"} or name.endswith((".sh", ".bash")):
        return "bash"
    if script_type in {"javascript", "nodejs"} or name.endswith((".js", ".mjs")):
        return "javascript"
    if script_type in {"powershell", "power_shell"} or name.endswith(".ps1"):
        return "powershell"
    return "text"


def _fence(content: str, language: str) -> str:
    longest = max((len(match.group(0)) for match in re.finditer(r"`+", content)), default=0)
    marker = "`" * max(3, longest + 1)
    return f"{marker}{language}\n{content}\n{marker}"


async def read_current_script(ctx: RunContext[Any]) -> dict[str, Any]:
    """Return the complete current saved script body and its editable metadata."""
    try:
        payload = await fetch_current_page_object(
            ctx,
            expected_object_type="script_definition",
            api_collection="scripts",
        )
    except CurrentPageObjectError as exc:
        return {"success": False, "error": str(exc)}

    content = payload.get("content")
    if not isinstance(content, str):
        return {
            "success": False,
            "error": "SmartCMP current script content must be a string.",
        }
    editable = {
        key: payload.get(key)
        for key in (
            "name",
            "alias",
            "aliasZh",
            "description",
            "descriptionZh",
            "type",
            "params",
            "properties",
            "formContent",
            "resourceTypes",
            "osType",
        )
        if key in payload
    }
    output = "\n".join(
        [
            f"Current saved SmartCMP script: {payload.get('alias') or payload.get('name') or payload['id']}",
            f"Script ID: {payload['id']}",
            "",
            "Editable definition metadata:",
            "```json",
            json.dumps(editable, ensure_ascii=False, indent=2),
            "```",
            "",
            "Complete script content:",
            _fence(content, _code_language(payload)),
        ]
    )
    return {
        "success": True,
        "output": output,
        "script": {
            "id": payload["id"],
            "metadata": editable,
            "content": content,
        },
    }
