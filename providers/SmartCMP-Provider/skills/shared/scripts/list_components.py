#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""List SmartCMP components for a catalog source key."""

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


def _reject_catalog_id_like(value: str) -> bool:
    normalized = value.strip().upper()
    return normalized.startswith("BUILD-IN-CATALOG") or normalized.startswith("CATALOG-")


def _normalize_component(item):
    model = item.get("model") if isinstance(item.get("model"), dict) else {}
    return {
        "id": item.get("id", ""),
        "name": item.get("nameZh") or item.get("name") or item.get("displayName", ""),
        "typeName": model.get("typeName") or item.get("typeName", ""),
        "cloudEntryTypeIds": model.get("cloudEntryTypeIds") or item.get("cloudEntryTypeIds", ""),
        "osType": model.get("osType") or item.get("osType", ""),
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    source_key = str(argv[0] if argv else "").strip()
    if not source_key:
        print("[ERROR] source_key is required.")
        return 1
    if _reject_catalog_id_like(source_key):
        print("list_components.py only accepts source_key, for example resource.windows.")
        print("Do NOT pass catalog_id such as BUILD-IN-CATALOG-LINUX-VM.")
        return 1

    base_url, _auth_token, headers, _instance = require_config()
    response = requests.get(
        f"{base_url}/components",
        headers=headers,
        params={"resourceType": source_key},
        verify=False,
        timeout=30,
    )
    response.raise_for_status()

    items = [_normalize_component(item) for item in _extract_items(response.json()) if isinstance(item, dict)]
    selected = items[0] if items else {
        "id": "",
        "name": "",
        "typeName": "",
        "cloudEntryTypeIds": "",
        "osType": "",
    }

    print(f"Component: {selected.get('name') or selected.get('typeName') or 'N/A'}")
    print("##COMPONENT_META_START##", file=sys.stderr)
    print(json.dumps(selected, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
    print("##COMPONENT_META_END##", file=sys.stderr)
    return 0


_EXIT_CODE = main()
if _EXIT_CODE:
    raise SystemExit(_EXIT_CODE)
