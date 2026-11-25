# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.
"""Report number extraction for the document list."""

from __future__ import annotations

import re

_PATTERNS = (
    re.compile(r"报告编号\s*[:：]\s*([A-Za-z0-9][A-Za-z0-9\-/_]{3,40})"),
    re.compile(r"报告号\s*[:：]\s*([A-Za-z0-9][A-Za-z0-9\-/_]{3,40})"),
    re.compile(r"\b(RPT-\d{4}-\d{3,6}[A-Za-z]?)\b"),
    re.compile(r"\b(JC-\d{4}-\d{5,9}[A-Za-z]?)\b"),
    re.compile(r"\b([A-Z]{2,5}-\d{4}-\d{4,8}[A-Za-z]?)\b"),
)


def extract_report_no(text: str) -> str:
    """Return the first plausible report number, or an empty string."""
    normalized = str(text or "")
    for pattern in _PATTERNS:
        match = pattern.search(normalized)
        if match:
            return match.group(1).strip()
    return ""
