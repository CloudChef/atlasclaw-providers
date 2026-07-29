#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""List SmartCMP images for datasource discovery and request provisioning."""

from __future__ import annotations

import json
import os
import sys

import requests

try:
    from _common import request_timeout, render_markdown_table, require_config
except ImportError:
    sys.path.insert(
        0,
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..",
            "..",
            "shared",
            "scripts",
        ),
    )
    from _common import request_timeout, render_markdown_table, require_config


def _normalize_item(item, index):
    properties = item.get("properties")
    extra = properties.get("extra") if isinstance(properties, dict) else None
    configured_template_id = (
        extra.get("templateId") if isinstance(extra, dict) else None
    )
    template_id = configured_template_id or item.get("id", "")
    return {
        "index": index,
        "id": template_id,
        "templateId": template_id,
        "name": item.get("nameZh") or item.get("name") or item.get("displayName", ""),
    }


def main(argv: list[str] | None = None) -> int:
    """Run the cloud-image lookup command.

    Args:
        argv: Optional argument list.

    Returns:
        Process exit code.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 3:
        print("[ERROR] Usage: list_images.py <resourceBundleId> <logicTemplateId> <cloudEntryType>")
        return 1

    resource_bundle_id, logic_template_id, cloud_entry_type = [str(value).strip() for value in argv[:3]]
    if not cloud_entry_type.startswith("yacmp:cloudentry:type:"):
        print(
            "[ERROR] cloudEntryTypeId must come from the selected resource pool "
            "and start with 'yacmp:cloudentry:type:'."
        )
        return 1
    base_url, _auth_token, headers, _instance = require_config()

    body = {
        "cloudResourceType": f"{cloud_entry_type}::images",
        "limit": 500,
        "queryProperties": {
            "resourceBundleId": resource_bundle_id,
            "logicTemplateId": logic_template_id,
            "queryResourceBundle": False,
        },
    }

    try:
        response = requests.post(
            f"{base_url}/cloudprovider?action=queryCloudResource",
            headers=headers,
            json=body,
            verify=False,
            timeout=request_timeout(),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"[ERROR] Image query request failed: {exc}")
        return 1

    try:
        payload = response.json()
    except ValueError:
        print("[ERROR] Image query returned invalid JSON.")
        return 1
    if not isinstance(payload, list):
        print("[ERROR] Image query returned an unexpected JSON shape.")
        return 1

    items = [
        _normalize_item(item, index)
        for index, item in enumerate(payload, start=1)
        if isinstance(item, dict)
    ]
    print(
        render_markdown_table(
            f"Found {len(items)} image(s):",
            ["#", "Name"],
            [[item["index"], item["name"]] for item in items],
        )
    )

    internal_metadata = {
        "internal_request_trace_id": os.environ.get("INTERNAL_REQUEST_TRACE_ID", ""),
        "images": items,
    }
    print("##IMAGE_META_START##", file=sys.stderr)
    print(
        json.dumps(internal_metadata, ensure_ascii=False, separators=(",", ":")),
        file=sys.stderr,
    )
    print("##IMAGE_META_END##", file=sys.stderr)
    return 0


_EXIT_CODE = main()
if _EXIT_CODE:
    raise SystemExit(_EXIT_CODE)
