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
    from _common import request_timeout, render_markdown_table, require_config
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _common import request_timeout, render_markdown_table, require_config


def _extract_items(payload):
    """Extract application rows from SmartCMP's common response envelopes.

    SmartCMP endpoints are not fully consistent across deployments: list
    payloads may be returned directly or under ``content``, ``items``,
    ``result``, or ``data``. Keeping that normalization here lets the user-facing
    rendering stay independent from the transport envelope.
    """
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
    """Build the compact application metadata used for user selection."""
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
        timeout=request_timeout(),
    )
    response.raise_for_status()

    payload = response.json()
    raw_items = _extract_items(payload)
    total = payload.get("totalElements", len(raw_items)) if isinstance(payload, dict) else len(raw_items)
    items = [_normalize(item, index) for index, item in enumerate(raw_items, start=1) if isinstance(item, dict)]

    print(
        render_markdown_table(
            f"Found {total} application(s):",
            ["#", "Name", "Description"],
            [[item["index"], item["name"], item.get("description") or ""] for item in items],
        )
    )
    print("请选择应用（输入编号）：")

    # The table above is for the user. The sidecar block is emitted on stderr so
    # the agent can resolve a later row-number selection without exposing raw
    # SmartCMP JSON in the conversation.
    print("##APPLICATION_META_START##", file=sys.stderr)
    print(json.dumps(items, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
    print("##APPLICATION_META_END##", file=sys.stderr)
    return 0


_EXIT_CODE = main()
if _EXIT_CODE:
    raise SystemExit(_EXIT_CODE)
