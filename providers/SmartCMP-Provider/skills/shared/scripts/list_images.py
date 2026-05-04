#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""List SmartCMP images for a selected resource pool and logic template."""

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


def _normalize_platform(value: str) -> str:
    value = str(value or "").strip()
    if value.startswith("yacmp:cloudentry:type:"):
        return value
    return f"yacmp:cloudentry:type:{value}"


def _load_json_env(name: str, default):
    raw = os.environ.get(name, "")
    if not raw.strip():
        return default
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return default
    return value if isinstance(value, type(default)) else default


def _normalize_item(item, index):
    return {
        "index": index,
        "id": item.get("id", ""),
        "name": item.get("nameZh") or item.get("name") or item.get("displayName", ""),
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 3:
        print("[ERROR] Usage: list_images.py <resourceBundleId> <logicTemplateId> <cloudEntryType>")
        return 1

    resource_bundle_id, logic_template_id, cloud_entry_type = [str(value).strip() for value in argv[:3]]
    platform = _normalize_platform(cloud_entry_type)
    base_url, _auth_token, headers, _instance = require_config()

    query_properties = {
        "resourceBundleId": resource_bundle_id,
        "logicTemplateId": logic_template_id,
        "queryResourceBundle": False,
    }
    query_properties.update(_load_json_env("IMAGE_QUERY_PROPERTIES_JSON", {}))

    body = _load_json_env("IMAGE_QUERY_BODY_JSON", {})
    body_query_properties = body.pop("queryProperties", {}) if isinstance(body.get("queryProperties"), dict) else {}
    query_properties.update(body_query_properties)
    body.update(
        {
            "cloudResourceType": f"{platform}::images",
            "queryProperties": query_properties,
        }
    )
    limit = os.environ.get("IMAGE_QUERY_LIMIT", "").strip()
    if limit:
        try:
            body["limit"] = int(limit)
        except ValueError:
            body["limit"] = limit

    response = requests.post(
        f"{base_url}/cloudprovider?action=queryCloudResource",
        headers=headers,
        json=body,
        verify=False,
        timeout=30,
    )
    response.raise_for_status()

    items = [_normalize_item(item, index) for index, item in enumerate(_extract_items(response.json()), start=1) if isinstance(item, dict)]
    print(f"Found {len(items)} image(s):")
    for item in items:
        print(f"  [{item['index']}] {item['name']}")

    print("##IMAGE_META_START##", file=sys.stderr)
    print(json.dumps(items, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
    print("##IMAGE_META_END##", file=sys.stderr)
    return 0


_EXIT_CODE = main()
if _EXIT_CODE:
    raise SystemExit(_EXIT_CODE)
