#!/usr/bin/env python3
"""Deterministic analysis helpers for SmartCMP cost optimization."""


def build_placeholder_analysis(violation_id: str) -> dict:
    """Return a stable placeholder analysis payload."""
    return {
        "violationId": violation_id,
        "facts": {},
        "assessment": {},
        "recommendations": [],
        "suggestedNextStep": "manual_review",
    }
