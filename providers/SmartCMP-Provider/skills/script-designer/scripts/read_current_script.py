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
except ImportError:  # Provider-only unit tests do not install the AtlasClaw runtime.
    RunContext = Any


sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "shared", "scripts")
    ),
)

from _current_page_object import fetch_current_page_object  # noqa: E402
from smartcmp_provider.services.designers import (  # noqa: E402
    project_script_definition,
)


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
        script = project_script_definition(payload)
    except RuntimeError as exc:
        return {"success": False, "error": str(exc)}

    output = "\n".join(
        [
            f"Current saved SmartCMP script: {script.name or script.object_id}",
            f"Script ID: {script.object_id}",
            "",
            "Editable definition metadata:",
            "```json",
            json.dumps(script.metadata, ensure_ascii=False, indent=2),
            "```",
            "",
            "Complete script content:",
            _fence(script.content, script.language),
        ]
    )
    return {
        "success": True,
        "output": output,
        "script": {
            "id": script.object_id,
            "metadata": script.metadata,
            "content": script.content,
        },
    }
