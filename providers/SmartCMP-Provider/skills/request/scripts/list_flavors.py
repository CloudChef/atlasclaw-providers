# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""List SmartCMP compute flavors with optional provisioning filters.

Usage:
  python list_flavors.py [--query QUERY] [--resource-bundle-id ID]
      [--catalog-id ID] [--node-template-name NAME]

Arguments:
  --query, -q            Optional search keyword.
  --resource-bundle-id  Optional resource pool filter.
  --catalog-id          Optional catalog filter.
  --node-template-name  Optional catalog node filter.

Output:
  - Numbered compute-flavor list
  - ##FLAVOR_META_START## ... ##FLAVOR_META_END##

Environment:
  CMP_URL    - Base URL (IP, hostname, or full path; auto-normalized)
  CMP_COOKIE - Session cookie string

API Reference:
  GET /flavors/provision?query&flavorType=MACHINE
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
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared', 'scripts'))
    from _common import request_timeout, render_markdown_table, require_config


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse compute-flavor lookup arguments.

    Args:
        argv: Optional command-line arguments.

    Returns:
        Parsed argument namespace.
    """
    parser = argparse.ArgumentParser(description="List available compute flavors from SmartCMP")
    parser.add_argument("--query", "-q", default="", help="Optional search keyword")
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
    parser.add_argument("--page", "-p", type=int, default=1, help="Page number (default: 1)")
    parser.add_argument("--size", "-s", type=int, default=100, help="Page size (default: 100)")
    return parser.parse_args(argv)


def fetch_flavors(
    *,
    base_url: str,
    headers: dict,
    query: str = "",
    resource_bundle_id: str = "",
    catalog_id: str = "",
    node_template_name: str = "",
    page: int = 1,
    size: int = 100,
) -> list[dict]:
    """Fetch available compute flavors from SmartCMP API.

    Args:
        base_url: SmartCMP platform-api base URL
        headers: HTTP headers with auth token
        query: Optional search keyword
        resource_bundle_id: Optional resource pool ID
        catalog_id: Optional catalog ID
        node_template_name: Optional node template name
        page: Page number
        size: Page size

    Returns:
        List of flavor objects

    Raises:
        RuntimeError: If SmartCMP returns an unsuccessful response or violates
            the paged flavor response contract.
    """
    url = f"{base_url}/flavors/provision"
    params = {
        "query": "",
        "page": page,
        "size": size,
        "queryValue": query,
        "flavorType": "MACHINE",
        "resourceBundleId": resource_bundle_id,
        "catalogId": catalog_id,
        "nodeTemplateName": node_template_name,
    }

    resp = requests.get(url, headers=headers, params=params, verify=False, timeout=request_timeout())
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")

    try:
        data = resp.json()
    except ValueError as exc:
        raise RuntimeError("Response did not contain valid JSON.") from exc

    if not isinstance(data, dict) or not isinstance(data.get("content"), list):
        raise RuntimeError("Flavor query returned an unexpected JSON shape.")
    flavors = data["content"]
    if any(not isinstance(item, dict) for item in flavors):
        raise RuntimeError("Flavor query returned a non-object item.")
    return flavors


def format_flavor_summary(flavor: dict) -> str:
    """Format a single flavor for user-facing display.

    Args:
        flavor: SmartCMP flavor record.

    Returns:
        Compact display summary.
    """
    fid = flavor.get("id", "")
    name = flavor.get("name", "")
    spec_type = flavor.get("specType", "")
    flavors_detail = flavor.get("flavors", [])

    specs = []
    for f in flavors_detail:
        ftype = f.get("type", "")
        number = f.get("number")
        unit = f.get("unit", "")
        if number is not None:
            specs.append(f"{ftype}: {number} {unit}".strip())
        else:
            specs.append(f"{ftype}: (flexible)")

    spec_str = ", ".join(specs) if specs else "N/A"
    return f"{name} (id={fid}, type={spec_type}) [{spec_str}]"


def _meta_item(index: int, flavor: dict) -> dict:
    """Build compact machine-readable flavor metadata."""
    flavor_id = flavor.get("id", "")
    return {
        "index": index,
        "id": flavor_id,
        "computeProfileId": flavor_id,
        "name": flavor.get("name") or flavor_id or "N/A",
        "specType": flavor.get("specType", ""),
        "flavors": flavor.get("flavors", []),
    }


def main(argv: list[str] | None = None) -> int:
    """Run the compute-flavor lookup command.

    Args:
        argv: Optional command-line arguments.

    Returns:
        Process exit code.
    """
    args = parse_args(argv)
    base_url, _, headers, _ = require_config()

    try:
        flavors = fetch_flavors(
            base_url=base_url,
            headers=headers,
            query=args.query,
            resource_bundle_id=args.resource_bundle_id,
            catalog_id=args.catalog_id,
            node_template_name=args.node_template_name,
            page=args.page,
            size=args.size,
        )
    except (RuntimeError, requests.RequestException) as exc:
        print(f"[ERROR] {exc}")
        return 1

    if not flavors:
        print("No flavors found.")
        return 0

    meta = [_meta_item(index, flavor) for index, flavor in enumerate(flavors, start=1)]
    print(
        render_markdown_table(
            f"Found {len(flavors)} flavor(s):",
            ["#", "Flavor"],
            [
                [item["index"], format_flavor_summary(flavor)]
                for item, flavor in zip(meta, flavors)
            ],
        )
    )

    print()
    print("##FLAVOR_META_START##")
    print(json.dumps(meta, ensure_ascii=False, separators=(",", ":")))
    print("##FLAVOR_META_END##")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
