#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Shared helpers for SmartCMP cost optimization scripts."""

from __future__ import annotations

import os
from datetime import datetime, timezone

# In-process cache: (base_url, auth_token) -> symbol
_CURRENCY_CACHE: dict[str, str] = {}


def get_currency_symbol(base_url: str = "", auth_token: str = "") -> str:
    """Fetch currency symbol from SmartCMP tenant settings.

    Resolution order:
    1. env CMP_CURRENCY (override)
    2. API: GET /tenants/current/setting -> currencyUnitType (e.g. "CNY")
             GET /tenants/currencyUnits  -> match code -> symbol (e.g. "¥")
    3. Fallback: "¥"
    """
    # 1. Explicit env override
    env_override = os.environ.get("CMP_CURRENCY", "").strip()
    if env_override:
        return env_override

    # 2. Try API (with in-process cache keyed by base_url)
    cache_key = base_url or "_default"
    if cache_key in _CURRENCY_CACHE:
        return _CURRENCY_CACHE[cache_key]

    symbol = _fetch_currency_symbol(base_url, auth_token)
    _CURRENCY_CACHE[cache_key] = symbol
    return symbol


def _fetch_currency_symbol(base_url: str, auth_token: str) -> str:
    """Internal: fetch symbol from CMP API, return '¥' on any failure."""
    if not base_url or not auth_token:
        # Try to build from env as fallback
        raw_url = os.environ.get("CMP_URL", "").strip()
        user_token = os.environ.get("CMP_API_TOKEN", "").strip()
        cookie = os.environ.get("CMP_COOKIE", "")
        if not raw_url:
            return "¥"
        # Normalize URL
        if not raw_url.endswith("/platform-api"):
            raw_url = raw_url.rstrip("/") + "/platform-api"
        base_url = raw_url
        # Use user token if available, otherwise extract from cookie
        if user_token:
            auth_token = user_token
        else:
            for part in cookie.split(";"):
                part = part.strip()
                if part.startswith("CloudChef-Authenticate="):
                    auth_token = part.split("=", 1)[1]
                    break
        if not auth_token:
            return "¥"

    try:
        import requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        # Build correct header based on token type
        if auth_token.startswith("cmp_tk_"):
            headers = {"Authorization": f"Bearer {auth_token}"}
        else:
            headers = {"CloudChef-Authenticate": auth_token}

        # Step 1: get currencyUnitType code
        r_setting = requests.get(
            f"{base_url}/tenants/current/setting",
            headers=headers,
            verify=False,
            timeout=5,
        )
        if r_setting.status_code != 200:
            return "¥"
        currency_code = (r_setting.json() or {}).get("currencyUnitType", "")
        if not currency_code:
            return "¥"

        # Step 2: get symbol from currencyUnits list
        r_units = requests.get(
            f"{base_url}/tenants/currencyUnits",
            headers=headers,
            verify=False,
            timeout=5,
        )
        if r_units.status_code != 200:
            return "¥"
        units = r_units.json()
        if isinstance(units, list):
            for unit in units:
                if unit.get("code") == currency_code:
                    return unit.get("symbol", "¥")
    except Exception:
        pass

    return "¥"


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
