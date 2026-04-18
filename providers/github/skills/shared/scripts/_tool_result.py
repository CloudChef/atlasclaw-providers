# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any


def tool_text(text: str, details: dict[str, Any] | None = None, *, is_error: bool = False) -> dict:
    return {
        "content": [{"type": "text", "text": str(text or "")}],
        "details": details or {},
        "is_error": bool(is_error),
    }


def tool_error(text: str, details: dict[str, Any] | None = None) -> dict:
    return tool_text(text, details=details, is_error=True)


def primary_text(result: dict[str, Any]) -> str:
    if not isinstance(result, dict):
        return ""
    content = result.get("content")
    if not isinstance(content, list):
        return ""
    for item in content:
        if isinstance(item, dict):
            text = str(item.get("text", "") or "").strip()
            if text:
                return text
    return ""


def emit_cli_result(result: dict[str, Any]) -> int:
    text = primary_text(result)
    if text:
        print(text)
    return 1 if bool(result.get("is_error")) else 0
