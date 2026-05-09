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
import json
import argparse
import sys

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


def _text(value):
    """Return the best display text from string or i18n dictionary values."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("zh", "zh_CN", "nameZh", "label", "en", "name"):
            text = value.get(key)
            if isinstance(text, str) and text:
                return text
        for text in value.values():
            if isinstance(text, str) and text:
                return text
    return ""


def _display_name(item):
    """Resolve a user-facing display name from common SmartCMP shapes."""
    if not isinstance(item, dict):
        return _text(item)
    for key in ("nameZh", "labelZh", "displayName", "label", "name", "title", "i18nTitle"):
        text = _text(item.get(key))
        if text:
            return text
    return ""


def _option_key(option):
    """Resolve the stable option key used in resourceBundleTags."""
    if not isinstance(option, dict):
        return str(option) if option is not None else ""
    for key in ("key", "id", "value", "code"):
        value = option.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _option_items(facet):
    """Return selectable options from common API field names."""
    if not isinstance(facet, dict):
        return []
    for key in ("options", "values", "items", "children", "source", "selectDatas"):
        value = facet.get(key)
        if isinstance(value, list):
            return value
    return []


def compact_facets(facets):
    """Keep only facet fields that the request skill needs."""
    compacted = []
    for facet in facets:
        if not isinstance(facet, dict):
            continue

        facet_key = facet.get("key") or facet.get("id") or facet.get("code") or ""
        if not facet_key:
            continue

        options = []
        for option in _option_items(facet):
            option_key = _option_key(option)
            if not option_key:
                continue
            options.append({
                "key": option_key,
                "label": _display_name(option) or option_key,
            })

        compacted.append({
            "key": facet_key,
            "label": _display_name(facet) or facet_key,
            "options": options,
        })
    return compacted


def format_facet_summary(facet):
    """Format a compact facet for display output."""
    lines = [f"  Facet: {facet['label']} (key={facet['key']})"]
    if not facet["options"]:
        lines.append("    No selectable options returned.")
        return "\n".join(lines)

    for i, option in enumerate(facet["options"], start=1):
        lines.append(f"    {i}) {option['label']} (key={option['key']})")
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

    compacted_facets = compact_facets(facets)
    if not compacted_facets:
        print("No facets found.")
        return 0

    print(f"Found {len(compacted_facets)} facet(s):\n")
    for facet in compacted_facets:
        print(format_facet_summary(facet))
        print()

    # Output machine-readable metadata for agent consumption
    print("##FACET_META_START##")
    print(json.dumps(compacted_facets, ensure_ascii=False))
    print("##FACET_META_END##")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
