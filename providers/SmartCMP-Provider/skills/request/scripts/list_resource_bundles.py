# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""List request-flow resource pools from SmartCMP.

Usage:
  python list_resource_bundles.py <business_group_id> <component_type> <node_type> [--cloud-entry-type-id CLOUD_ENTRY_TYPE_ID]

Arguments:
  business_group_id      REQUIRED. UUID of the selected business group.
  component_type         REQUIRED. Component resource type from generated Markdown, such as resource.iaas.machine.instance.abstract.
  node_type              REQUIRED. Node type from generated Markdown resourceSpecs[].type, such as cloudchef.nodes.Compute.
  cloud_entry_type_id    Optional cloud entry type filter.

Output:
  - Numbered resource pool list
  - ##RESOURCE_BUNDLE_META_START## ... ##RESOURCE_BUNDLE_META_END##

API Reference:
  GET /resource-bundles?businessGroupId=...&cloudEntryTypeId=...&componentType=...&enabled=true&nodeType=...&readOnly=false&strategy=RB_POLICY_STATIC
"""
from __future__ import annotations

import argparse
import json
import sys

import requests

try:
    from _common import request_timeout, render_markdown_table, require_config
except ImportError:
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared", "scripts"))
    from _common import request_timeout, render_markdown_table, require_config


def parse_args(argv=None):
    """Parse command-line arguments.

    Args:
        argv: Optional argument list.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(description="List request-flow resource pools from SmartCMP")
    parser.add_argument("business_group_id", help="UUID of the selected business group")
    parser.add_argument("component_type", help="Component resource type from generated Markdown")
    parser.add_argument("node_type", help="Node type from generated Markdown resourceSpecs[].type")
    parser.add_argument("--cloud-entry-type-id", default="", help="Optional cloud entry type filter")
    return parser.parse_args(argv)


def _extract_list(payload):
    """Extract a list from common SmartCMP response shapes.

    Args:
        payload: Decoded JSON payload.

    Returns:
        List of resource bundle objects.
    """
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("content", "data", "items", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return [payload]
    return []


def _display_name(item: dict) -> str:
    """Return a human-readable resource pool name.

    Args:
        item: Resource bundle item.

    Returns:
        Display name string.
    """
    return item.get("name") or item.get("nameZh") or item.get("displayName") or item.get("id") or "N/A"


def _meta_item(index: int, item: dict) -> dict:
    """Build compact machine-readable metadata for a resource pool.

    Args:
        index: 1-based display index.
        item: Resource bundle item.

    Returns:
        Compact metadata dictionary.
    """
    return {
        "index": index,
        "id": item.get("id", ""),
        "name": _display_name(item),
        "businessGroupId": item.get("businessGroupId", ""),
        "cloudEntryTypeId": item.get("cloudEntryTypeId", ""),
        "cloudEntryId": item.get("cloudEntryId", ""),
        "regionId": item.get("regionId", ""),
        "privateCloudEntry": item.get("privateCloudEntry", False),
        "facets": item.get("facets", []),
    }


def fetch_resource_bundles(
    *,
    base_url: str,
    headers: dict,
    business_group_id: str,
    component_type: str,
    node_type: str,
    cloud_entry_type_id: str = "",
) -> list[dict]:
    """Fetch request-flow resource pools.

    Args:
        base_url: SmartCMP platform-api base URL.
        headers: HTTP headers with authentication.
        business_group_id: Selected business group UUID.
        component_type: Component resource type.
        node_type: Node type from generated Markdown.
        cloud_entry_type_id: Optional cloud entry type filter.

    Returns:
        Resource pool list.

    Raises:
        RuntimeError: If the API response is not successful or JSON.
    """
    url = f"{base_url}/resource-bundles"
    params = {
        "businessGroupId": business_group_id,
        "cloudEntryTypeId": cloud_entry_type_id or "",
        "componentType": component_type,
        "enabled": "true",
        "nodeType": node_type,
        "readOnly": "false",
        "strategy": "RB_POLICY_STATIC",
    }
    resp = requests.get(url, headers=headers, params=params, verify=False, timeout=request_timeout())
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")

    try:
        payload = resp.json()
    except ValueError as exc:
        raise RuntimeError("Response did not contain valid JSON.") from exc

    return _extract_list(payload)


def main(argv=None) -> int:
    """Run the resource pool lookup command.

    Args:
        argv: Optional argument list.

    Returns:
        Process exit code.
    """
    args = parse_args(argv)
    base_url, _, headers, _ = require_config()

    try:
        bundles = fetch_resource_bundles(
            base_url=base_url,
            headers=headers,
            business_group_id=args.business_group_id,
            component_type=args.component_type,
            node_type=args.node_type,
            cloud_entry_type_id=args.cloud_entry_type_id,
        )
    except (RuntimeError, requests.RequestException) as exc:
        print(f"[ERROR] {exc}")
        return 1

    if not bundles:
        print("No resource pools found.")
        return 0

    meta = [_meta_item(index, item) for index, item in enumerate(bundles, start=1)]
    print(
        render_markdown_table(
            f"Found {len(bundles)} resource pool(s):",
            ["#", "Name", "ID"],
            [[item["index"], item["name"], item.get("id") or ""] for item in meta],
        )
    )
    print()
    print("##RESOURCE_BUNDLE_META_START##")
    print(json.dumps(meta, ensure_ascii=False))
    print("##RESOURCE_BUNDLE_META_END##")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
