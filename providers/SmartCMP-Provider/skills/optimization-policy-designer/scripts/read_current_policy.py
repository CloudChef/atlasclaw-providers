# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Read the saved cost-optimization policy bound to the current page Context."""

from __future__ import annotations

import json
import os
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
    project_optimization_policy,
)


async def read_current_policy(ctx: RunContext[Any]) -> dict[str, Any]:
    """Return the complete current cost-policy rule and editable definition."""
    try:
        payload = await fetch_current_page_object(
            ctx,
            expected_object_type="optimization_policy",
            api_collection="compliance-policies",
        )
        policy = project_optimization_policy(payload)
    except RuntimeError as exc:
        return {"success": False, "error": str(exc)}

    return {
        "success": True,
        "output": "\n".join(
            [
                f"Current saved SmartCMP optimization policy: {policy.name or policy.object_id}",
                f"Policy ID: {policy.object_id}",
                "",
                "Complete editable policy definition:",
                "```json",
                json.dumps(policy.definition, ensure_ascii=False, indent=2),
                "```",
            ]
        ),
        "policy": {
            "id": policy.object_id,
            "definition": policy.definition,
        },
    }
