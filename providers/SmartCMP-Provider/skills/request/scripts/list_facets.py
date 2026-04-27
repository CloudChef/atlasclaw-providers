# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""List available resource bundle tag facets from SmartCMP.

Usage:
  python list_facets.py <business_group_id> [--node-type NODE_TYPE]

Arguments:
  business_group_id   REQUIRED. UUID of the selected business group.
  --node-type, -n     Node type filter (default: cloudchef.nodes.Compute)

Output:
  - Facet definitions with keys and selectable options

Environment:
  CMP_URL    - Base URL (IP, hostname, or full path; auto-normalized)
  CMP_COOKIE - Session cookie string

API Reference:
  GET /resource-bundles/available-facets?businessGroupId=xxx&cloudEntryId=&nodeType=cloudchef.nodes.Compute
"""
import sys
import json
import argparse

import requests

try:
    from _common import require_config
except ImportError:
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'shared', 'scripts'))
    from _common import require_config


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='List resource bundle tag facets from SmartCMP')
    parser.add_argument('business_group_id',
                        help='REQUIRED. UUID of the selected business group.')
    parser.add_argument('--node-type', '-n', default='cloudchef.nodes.Compute',
                        help='Node type filter (default: cloudchef.nodes.Compute)')
    return parser.parse_args(argv)


def fetch_facets(*, base_url, headers, business_group_id, node_type="cloudchef.nodes.Compute"):
    """Fetch available facet definitions from SmartCMP API.

    Args:
        base_url: SmartCMP platform-api base URL
        headers: HTTP headers with auth token
        business_group_id: UUID of the selected business group
        node_type: Node type filter (e.g. cloudchef.nodes.Compute)

    Returns:
        List of facet objects with keys and options
    """
    url = f"{base_url}/resource-bundles/available-facets"
    params = {"businessGroupId": business_group_id, "cloudEntryId": "", "nodeType": node_type}

    resp = requests.get(url, headers=headers, params=params, verify=False, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")

    try:
        data = resp.json()
    except ValueError as exc:
        raise RuntimeError("Response did not contain valid JSON.") from exc

    # API may return list directly or wrapped in a container
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("content", "items", "result", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return value
        return [data]

    return []


def format_facet_summary(facet):
    """Format a single facet for display output."""
    key = facet.get("key", "")
    name = facet.get("name", "")
    name_zh = facet.get("nameZh", "")
    option_mode = facet.get("optionMode", "")
    options = facet.get("options", [])

    display_name = name_zh or name or key
    lines = [f"  Facet: {display_name} (key={key}, mode={option_mode})"]

    for i, opt in enumerate(options, start=1):
        opt_key = opt.get("key", "")
        opt_name = opt.get("name", "")
        opt_name_zh = opt.get("nameZh", "")
        opt_display = opt_name_zh or opt_name or opt_key
        lines.append(f"    {i}) {opt_display} (key={opt_key})")

    return "\n".join(lines)


def main(argv=None) -> int:
    args = parse_args(argv)
    base_url, _, headers, _ = require_config()

    try:
        facets = fetch_facets(base_url=base_url, headers=headers,
                              business_group_id=args.business_group_id,
                              node_type=args.node_type)
    except (RuntimeError, requests.RequestException) as exc:
        print(f"[ERROR] {exc}")
        return 1

    if not facets:
        print("No facets found.")
        return 0

    print(f"Found {len(facets)} facet(s):\n")
    for facet in facets:
        print(format_facet_summary(facet))
        print()

    # Output machine-readable metadata for agent consumption
    print("##FACET_META_START##")
    print(json.dumps(facets, ensure_ascii=False))
    print("##FACET_META_END##")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
