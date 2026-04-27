# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""List available business groups for a specific catalog in SmartCMP.

Usage:
  python list_available_bgs.py <catalog_id>

Arguments:
  catalog_id    UUID of the service catalog

Output:
  - Business group list with id and name

Environment:
  CMP_URL    - Base URL (IP, hostname, or full path; auto-normalized)
  CMP_COOKIE - Session cookie string

API Reference:
  GET /catalogs/{catalogId}/available-bgs
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
    parser = argparse.ArgumentParser(description='List available business groups for a catalog')
    parser.add_argument('catalog_id', help='UUID of the service catalog')
    return parser.parse_args(argv)


def fetch_available_bgs(*, base_url, headers, catalog_id):
    """Fetch available business groups for a specific catalog.

    Args:
        base_url: SmartCMP platform-api base URL
        headers: HTTP headers with auth token
        catalog_id: UUID of the catalog

    Returns:
        List of business group objects
    """
    url = f"{base_url}/catalogs/{catalog_id}/available-bgs"
    resp = requests.get(url, headers=headers, verify=False, timeout=30)
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
        return [data]

    return []


def main(argv=None) -> int:
    args = parse_args(argv)
    base_url, _, headers, _ = require_config()

    try:
        bgs = fetch_available_bgs(
            base_url=base_url,
            headers=headers,
            catalog_id=args.catalog_id,
        )
    except (RuntimeError, requests.RequestException) as exc:
        print(f"[ERROR] {exc}")
        return 1

    if not bgs:
        print("No available business groups found.")
        return 0

    print(f"Found {len(bgs)} available business group(s):\n")
    for i, bg in enumerate(bgs, start=1):
        bg_id = bg.get("id", "")
        bg_name = bg.get("name", "")
        print(f"  {i}) {bg_name} (id={bg_id})")

    print()
    print("##BG_META_START##")
    print(json.dumps(bgs, ensure_ascii=False))
    print("##BG_META_END##")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
