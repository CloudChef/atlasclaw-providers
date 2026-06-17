#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Inspect SmartCMP form schema JavaScript expressions without executing them."""

from __future__ import annotations

import re
from typing import Any


_EXPECTED_FUNCTION_PATTERN = re.compile(
    r"^\s*function\s*\(\s*model\s*,\s*sourceParams\s*,\s*schema\s*,\s*unused\s*,\s*cfg\s*\)",
    re.DOTALL,
)

_RISK_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\beval\s*\(", "eval(...)"),
    (
        r"(?<![\w$])(?:new\s+)?(?:Function|(?:[A-Za-z_$][\w$]*\s*\.\s*)+Function)\s*\(",
        "Function constructor",
    ),
    (r"\bfetch\s*\(", "fetch(...)"),
    (r"\bXMLHttpRequest\b", "XMLHttpRequest"),
    (r"\bdocument\s*\.\s*cookie\b", "document.cookie"),
    (r"https?://", "external URL"),
)


def expression_from_field(field: dict[str, Any]) -> str:
    """Return a field-level value expression when it is stored as a string.

    SmartCMP keeps dynamic field expressions at
    `field.config.value.expression`. The normalizer must preserve that raw
    value, so this helper only reads the nested value and never coerces or
    rewrites non-string shapes.

    Args:
        field: A SmartCMP schema field object.

    Returns:
        The exact expression string, or an empty string when no string
        expression is present.
    """
    config = field.get("config")
    if not isinstance(config, dict):
        return ""

    value = config.get("value")
    if not isinstance(value, dict):
        return ""

    expression = value.get("expression")
    if not isinstance(expression, str):
        return ""
    return expression


def validate_javascript_expression(expression: str, *, field_key: str) -> list[str]:
    """Return warnings for risky or unexpected JavaScript expression text.

    The check is intentionally conservative: it does not parse or execute
    JavaScript, and it never rejects or mutates schema content. Warnings call
    out patterns that deserve manual review before a generated schema is copied
    into SmartCMP.

    Args:
        expression: Raw JavaScript expression text from a schema field.
        field_key: Field key used to identify the warning source.

    Returns:
        Human-readable warnings for the caller to surface alongside normalized
        schema output.
    """
    if not expression:
        return []

    warnings: list[str] = []
    if not _EXPECTED_FUNCTION_PATTERN.search(expression):
        warnings.append(
            "JavaScript expression for field "
            f"{field_key!r} is not a function(model, sourceParams, schema, unused, cfg) "
            "expression; verify the SmartCMP runtime contract before use."
        )

    for pattern, label in _RISK_PATTERNS:
        if re.search(pattern, expression):
            warnings.append(
                f"JavaScript expression for field {field_key!r} contains {label}; "
                "review the trust boundary before use."
            )

    return warnings
