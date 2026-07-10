#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Collect SmartCMP schema strings that execute as JavaScript."""

from __future__ import annotations

from typing import Any


_TOP_LEVEL_JS_KEYS = (
    "changeEvent",
    "dynamicValidate",
    "asyncValidate",
    "condition",
)
_CONFIG_VALUE_JS_KEYS = (
    "expression",
    "label",
    "value",
    "filter",
    "process",
    "calculate",
)


def iter_field_javascript(field: dict[str, Any], field_key: str) -> list[tuple[str, str]]:
    expressions: list[tuple[str, str]] = []
    config = field.get("config")
    value = config.get("value") if isinstance(config, dict) else None
    if isinstance(value, dict):
        for key in _CONFIG_VALUE_JS_KEYS:
            _append_js_value(
                expressions,
                field_key if key == "expression" else f"{field_key}.config.value.{key}",
                value.get(key),
            )
    for key in _TOP_LEVEL_JS_KEYS:
        _append_js_value(expressions, f"{field_key}.{key}", field.get(key))
    return expressions


def _append_js_value(
    expressions: list[tuple[str, str]],
    field_key: str,
    value: Any,
) -> None:
    if isinstance(value, str) and _looks_like_javascript(value):
        expressions.append((field_key, value))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, str) and _looks_like_javascript(item):
                expressions.append((f"{field_key}[{index}]", item))


def _looks_like_javascript(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    return (
        "function" in text
        or "sourceParams" in text
        or "model" in text
        or "cfg" in text
        or "schema" in text
    )
