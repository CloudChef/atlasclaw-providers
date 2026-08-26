# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Normalize opaque SmartCMP user-facing request identifiers."""

from __future__ import annotations

from typing import Any


MAX_REQUEST_ID_LENGTH = 256


def normalize_request_id(value: Any) -> str:
    """Normalize one request identifier without interpreting its business format.

    Args:
        value: String or integer identifier supplied by SmartCMP or a caller.

    Returns:
        The trimmed identifier when it is non-empty and at most 256 characters;
        otherwise an empty string. Letter case and internal punctuation or
        whitespace are preserved exactly.
    """

    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return ""
    candidate = str(value).strip()
    if not candidate or len(candidate) > MAX_REQUEST_ID_LENGTH:
        return ""
    return candidate


def is_request_id(value: Any) -> bool:
    """Return whether a value is a bounded opaque SmartCMP request identifier.

    Args:
        value: Candidate value; strings and integers are accepted as identifier
            containers, while booleans and other object types are rejected.

    Returns:
        ``True`` only when normalization produces a non-empty value of at most
        256 characters.
    """

    return bool(normalize_request_id(value))
