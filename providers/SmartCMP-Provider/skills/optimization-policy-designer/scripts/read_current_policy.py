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


_EDITABLE_FIELDS = (
    "name",
    "nameZh",
    "description",
    "descriptionZh",
    "remedie",
    "remedieZh",
    "category",
    "type",
    "resourceType",
    "severity",
    "ruleContent",
    "policyConfigs",
)


async def read_current_policy(ctx: RunContext[Any]) -> dict[str, Any]:
    """Return the complete current cost-policy rule and editable definition."""
    try:
        payload = await fetch_current_page_object(
            ctx,
            expected_object_type="optimization_policy",
            api_collection="compliance-policies",
        )
    except CurrentPageObjectError as exc:
        return {"success": False, "error": str(exc)}

    category = str(payload.get("category") or "").strip().upper()
    if category != "COST-OPTIMIZATION" and not category.startswith(
        "COST-OPTIMIZATION."
    ):
        return {
            "success": False,
            "error": "Current policy is not a SmartCMP cost-optimization policy.",
        }
    rule_content = payload.get("ruleContent")
    if not isinstance(rule_content, str):
        return {
            "success": False,
            "error": "SmartCMP current policy ruleContent must be a string.",
        }
    editable = {key: payload.get(key) for key in _EDITABLE_FIELDS if key in payload}
    return {
        "success": True,
        "output": "\n".join(
            [
                f"Current saved SmartCMP optimization policy: {payload.get('name') or payload['id']}",
                f"Policy ID: {payload['id']}",
                "",
                "Complete editable policy definition:",
                "```json",
                json.dumps(editable, ensure_ascii=False, indent=2),
                "```",
            ]
        ),
        "policy": {
            "id": payload["id"],
            "definition": editable,
        },
    }
