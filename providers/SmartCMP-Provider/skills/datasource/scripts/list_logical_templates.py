#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""List SmartCMP logical templates with optional provisioning filters.

Usage:
  python list_logical_templates.py [QUERY] [--resource-bundle-id ID]
      [--catalog-id ID] [--node-template-name NAME] [--os-type TYPE]

Arguments:
  QUERY                  Optional logical-template-name filter.
  --resource-bundle-id  Optional resource pool filter.
  --catalog-id          Optional catalog filter.
  --node-template-name  Optional catalog node filter.
  --os-type             Optional OS type, such as Linux or Windows.

Output:
  - Numbered logical-template list
  - ##LOGICAL_TEMPLATE_META_START## ... ##LOGICAL_TEMPLATE_META_END##
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests


SCRIPT_DIR = Path(__file__).resolve().parent
SHARED_SCRIPTS_DIR = SCRIPT_DIR.parents[1] / "shared" / "scripts"
if str(SHARED_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPTS_DIR))

from _common import request_timeout, render_markdown_table, require_config  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Optional argument list.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(description="List SmartCMP logical templates")
    parser.add_argument(
        "query",
        nargs="?",
        default="",
        help="Optional logical-template-name filter",
    )
    parser.add_argument(
        "--resource-bundle-id",
        default="",
        help="Optional resource pool ID",
    )
    parser.add_argument("--catalog-id", default="", help="Optional catalog ID")
    parser.add_argument(
        "--node-template-name",
        default="",
        help="Optional catalog node template name",
    )
    parser.add_argument("--os-type", default="", help="Optional OS type")
    return parser.parse_args(argv)


def _display_name(item: dict) -> str:
    """Return the logical template's user-facing name."""
    return (
        item.get("nameZh")
        or item.get("name")
        or item.get("displayName")
        or item.get("id")
        or "N/A"
    )


def _meta_item(index: int, item: dict) -> dict:
    """Build compact machine-readable logical-template metadata."""
    template_id = item.get("id", "")
    return {
        "index": index,
        "id": template_id,
        "logicTemplateId": template_id,
        "name": _display_name(item),
        "osType": item.get("osType", ""),
        "patternImageName": item.get("patternImageName", ""),
    }


def fetch_logical_templates(
    *,
    base_url: str,
    headers: dict,
    query: str = "",
    resource_bundle_id: str = "",
    catalog_id: str = "",
    node_template_name: str = "",
    os_type: str = "",
) -> list[dict]:
    """Fetch logical templates from SmartCMP.

    Args:
        base_url: SmartCMP platform-api base URL.
        headers: HTTP headers containing provider authentication.
        query: Optional logical-template-name filter.
        resource_bundle_id: Optional resource pool ID.
        catalog_id: Optional catalog ID.
        node_template_name: Optional node template name.
        os_type: Optional OS type.

    Returns:
        Logical-template records returned by SmartCMP.

    Raises:
        RuntimeError: If SmartCMP returns an unsuccessful response or violates
            the logical-template list contract.
    """
    params = {
        "expand": "",
        "queryValue": query.strip(),
        "resourceBundleId": resource_bundle_id,
        "catalogId": catalog_id,
        "nodeTemplateName": node_template_name,
        "osType": os_type.strip(),
    }
    response = requests.get(
        f"{base_url}/logic-templates/search",
        headers=headers,
        params=params,
        verify=False,
        timeout=request_timeout(),
    )
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("Response did not contain valid JSON.") from exc
    if not isinstance(payload, list):
        raise RuntimeError("Logical-template query returned an unexpected JSON shape.")
    if any(not isinstance(item, dict) for item in payload):
        raise RuntimeError("Logical-template query returned a non-object item.")
    return payload


def main(argv: list[str] | None = None) -> int:
    """Run the logical-template lookup command.

    Args:
        argv: Optional argument list.

    Returns:
        Process exit code.
    """
    args = parse_args(argv)
    base_url, _auth_token, headers, _instance = require_config()

    try:
        templates = fetch_logical_templates(
            base_url=base_url,
            headers=headers,
            query=args.query,
            resource_bundle_id=args.resource_bundle_id,
            catalog_id=args.catalog_id,
            node_template_name=args.node_template_name,
            os_type=args.os_type,
        )
    except (RuntimeError, requests.RequestException) as exc:
        print(f"[ERROR] {exc}")
        return 1

    meta = [_meta_item(index, item) for index, item in enumerate(templates, start=1)]
    print(
        render_markdown_table(
            f"Found {len(meta)} logical template(s):",
            ["#", "Name", "OS Type"],
            [[item["index"], item["name"], item["osType"]] for item in meta],
        )
    )
    internal_metadata = {
        "internal_request_trace_id": os.environ.get("INTERNAL_REQUEST_TRACE_ID", ""),
        "logicalTemplates": meta,
    }
    print("##LOGICAL_TEMPLATE_META_START##", file=sys.stderr)
    print(
        json.dumps(internal_metadata, ensure_ascii=False, separators=(",", ":")),
        file=sys.stderr,
    )
    print("##LOGICAL_TEMPLATE_META_END##", file=sys.stderr)
    return 0


_EXIT_CODE = main()
if _EXIT_CODE:
    raise SystemExit(_EXIT_CODE)
