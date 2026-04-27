# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""List available compute flavors (specifications) from SmartCMP.

Usage:
  python list_flavors.py [--query QUERY] [--page PAGE] [--size SIZE]

Arguments:
  --query, -q   Optional search keyword to filter flavors
  --page, -p    Page number (default: 1)
  --size, -s    Page size (default: 100)

Output:
  - Flavor list with id, name, and spec details

Environment:
  CMP_URL    - Base URL (IP, hostname, or full path; auto-normalized)
  CMP_COOKIE - Session cookie string

API Reference:
  GET /flavors?query&page=1&size=100&queryValue=&sort=createdDate,desc
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
    parser = argparse.ArgumentParser(description='List available compute flavors from SmartCMP')
    parser.add_argument('--query', '-q', default='', help='Optional search keyword')
    parser.add_argument('--page', '-p', type=int, default=1, help='Page number (default: 1)')
    parser.add_argument('--size', '-s', type=int, default=100, help='Page size (default: 100)')
    return parser.parse_args(argv)


def fetch_flavors(*, base_url, headers, query="", page=1, size=100):
    """Fetch available compute flavors from SmartCMP API.

    Args:
        base_url: SmartCMP platform-api base URL
        headers: HTTP headers with auth token
        query: Optional search keyword
        page: Page number
        size: Page size

    Returns:
        List of flavor objects
    """
    url = f"{base_url}/flavors"
    params = {
        "query": "",
        "page": page,
        "size": size,
        "queryValue": query,
        "sort": "createdDate,desc",
    }

    resp = requests.get(url, headers=headers, params=params, verify=False, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")

    try:
        data = resp.json()
    except ValueError as exc:
        raise RuntimeError("Response did not contain valid JSON.") from exc

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("content", "items", "result", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def format_flavor_summary(flavor):
    """Format a single flavor for display."""
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


def main(argv=None) -> int:
    args = parse_args(argv)
    base_url, _, headers, _ = require_config()

    try:
        flavors = fetch_flavors(
            base_url=base_url,
            headers=headers,
            query=args.query,
            page=args.page,
            size=args.size,
        )
    except (RuntimeError, requests.RequestException) as exc:
        print(f"[ERROR] {exc}")
        return 1

    if not flavors:
        print("No flavors found.")
        return 0

    print(f"Found {len(flavors)} flavor(s):\n")
    for i, flavor in enumerate(flavors, start=1):
        print(f"  {i}) {format_flavor_summary(flavor)}")

    print()
    print("##FLAVOR_META_START##")
    print(json.dumps(flavors, ensure_ascii=False))
    print("##FLAVOR_META_END##")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
