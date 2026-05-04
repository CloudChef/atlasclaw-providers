#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""List SmartCMP applications for a business group."""

from __future__ import annotations

import json
import os
import sys

import requests

try:
    from _common import require_config
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _common import require_config


def _extract_items(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("content", "items", "result", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                nested = _extract_items(value)
                if nested:
                    return nested
    return []


def _normalize(item, index):
    return {
        "index": index,
        "id": item.get("id", ""),
        "name": item.get("name") or item.get("nameZh") or item.get("displayName", ""),
        "description": item.get("description") or "",
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or not str(argv[0]).strip():
        print("[ERROR] businessGroupId is required.")
        return 1

    business_group_id = str(argv[0]).strip()
    base_url, _auth_token, headers, _instance = require_config()
    response = requests.get(
        f"{base_url}/groups",
        headers=headers,
        params={"businessGroupIds": business_group_id},
        verify=False,
        timeout=30,
    )
    response.raise_for_status()

    payload = response.json()
    raw_items = _extract_items(payload)
    total = payload.get("totalElements", len(raw_items)) if isinstance(payload, dict) else len(raw_items)
    items = [_normalize(item, index) for index, item in enumerate(raw_items, start=1) if isinstance(item, dict)]

    print(f"Found {total} application(s):")
    for item in items:
        suffix = f" - {item['description']}" if item.get("description") else ""
        print(f"  [{item['index']}] {item['name']}{suffix}")
    print("请选择应用（输入编号）：")

    print("##APPLICATION_META_START##", file=sys.stderr)
    print(json.dumps(items, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
    print("##APPLICATION_META_END##", file=sys.stderr)
    return 0


_EXIT_CODE = main()
if _EXIT_CODE:
    raise SystemExit(_EXIT_CODE)
