#!/usr/bin/env python3
"""Shared helpers for SmartCMP cost optimization scripts."""

from __future__ import annotations

from datetime import datetime, timezone


def build_pageable_request(page: int = 0, size: int = 20) -> dict:
    """Return a stable pageable request payload."""
    return {"page": max(page, 0), "size": max(size, 1)}


def build_query_request(query_value: str = "") -> dict:
    """Return a stable query request payload."""
    return {"queryValue": query_value or ""}


def extract_list_payload(payload) -> list:
    """Extract list payloads from common SmartCMP response wrappers."""
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    for key in ("content", "items", "result"):
        value = payload.get(key)
        if isinstance(value, list):
            return value

    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("content", "items", "result"):
            value = data.get(key)
            if isinstance(value, list):
                return value

    return []


def normalize_money(value):
    """Normalize cost-like values to float or None."""
    if value in (None, "", "null"):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if cleaned.startswith("$") or cleaned.startswith("¥"):
            cleaned = cleaned[1:]
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def normalize_timestamp(value):
    """Normalize timestamps to UTC ISO-8601 strings or None."""
    if value in (None, "", "null"):
        return None

    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None

    if not isinstance(value, (int, float)):
        return None

    timestamp = float(value)
    if timestamp <= 0:
        return None

    if timestamp > 10_000_000_000:
        timestamp /= 1000.0

    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")
