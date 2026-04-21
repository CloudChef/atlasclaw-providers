# -*- coding: utf-8 -*-
"""List SmartCMP resources from the standalone CMP UI list endpoint.

Usage:
  python list_resources.py [--scope all_resources|virtual_machines] [--query-value KEYWORD] [--page N] [--size N]

Environment:
  RESOURCE_SCOPE  Optional listing scope
  QUERY_VALUE     Optional keyword filter
  PAGE            Optional page number
  SIZE            Optional page size

Output:
  - Numbered list of resource names plus status (user-visible)
  - ##RESOURCE_DIRECTORY_META_START## ... ##RESOURCE_DIRECTORY_META_END##
      JSON array with normalized list metadata
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

import requests


SCRIPT_DIR = Path(__file__).resolve().parent
SHARED_SCRIPTS_DIR = SCRIPT_DIR.parents[1] / "shared" / "scripts"
if str(SHARED_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPTS_DIR))

from _common import require_config  # noqa: E402


VALID_SCOPES = {"all_resources", "virtual_machines"}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="List SmartCMP resources or virtual machines.")
    parser.add_argument(
        "--scope",
        default=os.environ.get("RESOURCE_SCOPE", "all_resources"),
        help="Listing scope: all_resources or virtual_machines.",
    )
    parser.add_argument(
        "--query-value",
        default=os.environ.get("QUERY_VALUE", ""),
        help="Optional keyword filter.",
    )
    parser.add_argument(
        "--page",
        type=int,
        default=int(os.environ.get("PAGE", "1")),
        help="Page number. Default: 1.",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=int(os.environ.get("SIZE", "20")),
        help="Page size. Default: 20.",
    )
    return parser.parse_args(argv)


def normalize_scope(raw_scope: str) -> str:
    value = (raw_scope or "").strip().lower()
    aliases = {
        "all": "all_resources",
        "resources": "all_resources",
        "all_resources": "all_resources",
        "vm": "virtual_machines",
        "vms": "virtual_machines",
        "virtual_machine": "virtual_machines",
        "virtual_machines": "virtual_machines",
    }
    normalized = aliases.get(value, value)
    if normalized not in VALID_SCOPES:
        raise ValueError("scope must be one of: all_resources, virtual_machines")
    return normalized


def build_url(base_url: str, *, scope: str, query_value: str, page: int, size: int) -> str:
    encoded_query_value = quote(query_value or "", safe="")

    if scope == "virtual_machines":
        return (
            f"{base_url}/nodes/search"
            f"?query&page={page}&size={size}&catalogGroupIds=&sort=createdDate%2Cdesc"
            f"&queryValue={encoded_query_value}&category=iaas.machine.virtual_machine"
            f"&componentType=&monitorEnabled=&cloudEntryType=&isAgentInstalled=&os="
            f"&groupIds=&isImported=&relation=AND&fullMatch=false"
        )

    return (
        f"{base_url}/nodes/search"
        f"?page={page}&size={size}&queryValue={encoded_query_value}"
        f"&sort=createdDate%2Cdesc&relation=AND&fullMatch=false&category=-1"
    )


def extract_items(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("content", "data", "items", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def display_name(item: dict) -> str:
    return (
        item.get("name")
        or item.get("nameZh")
        or item.get("displayName")
        or item.get("label")
        or item.get("instanceName")
        or item.get("id")
        or "N/A"
    )


def extract_os(item: dict) -> str:
    return (
        item.get("os")
        or item.get("osType")
        or item.get("osDescription")
        or ""
    )


def display_status(item: dict) -> str:
    return (
        item.get("status")
        or item.get("powerState")
        or item.get("state")
        or item.get("phase")
        or "unknown"
    )


def meta_item(index: int, item: dict, scope: str) -> dict:
    return {
        "index": index,
        "id": item.get("id", ""),
        "name": display_name(item),
        "scope": scope,
        "resourceType": item.get("resourceType", ""),
        "componentType": item.get("componentType", ""),
        "status": item.get("status", ""),
        "os": extract_os(item),
        "cloudEntryType": item.get("cloudEntryType", ""),
    }


def summary_label(scope: str) -> str:
    return "virtual machine(s)" if scope == "virtual_machines" else "resource(s)"


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        scope = normalize_scope(args.scope)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 1

    base_url, _auth_token, headers, _instance = require_config()
    url = build_url(
        base_url,
        scope=scope,
        query_value=args.query_value,
        page=args.page,
        size=args.size,
    )

    try:
        response = requests.get(url, headers=headers, verify=False, timeout=30)
        response.raise_for_status()
        payload = response.json()
    except json.JSONDecodeError:
        print(
            f"[ERROR] API returned invalid JSON. Status={response.status_code}, "
            f"Body={response.text[:200]}"
        )
        return 1
    except requests.RequestException as exc:
        print(f"[ERROR] Request failed: {exc}")
        return 1

    items = extract_items(payload)
    if not items:
        if scope == "virtual_machines":
            print("No virtual machines found.")
        else:
            print("No resources found.")
        return 0

    print(f"Found {len(items)} {summary_label(scope)}:\n")
    for index, item in enumerate(items, start=1):
        print(f"  [{index}] {display_name(item)} | status: {display_status(item)}")
    print()

    meta = [meta_item(index, item, scope) for index, item in enumerate(items, start=1)]
    print("##RESOURCE_DIRECTORY_META_START##", file=sys.stderr)
    print(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
    print("##RESOURCE_DIRECTORY_META_END##", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
