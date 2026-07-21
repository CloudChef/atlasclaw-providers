# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""List SmartCMP resources from the standalone CMP UI list endpoint.

Usage:
  python list_resources.py [--scope all_resources|virtual_machines] [--query-value KEYWORD] [--page N] [--size N]

Environment:
  RESOURCE_SCOPE  Optional listing scope
  QUERY_VALUE     Optional keyword filter
  PAGE            Optional page number
  SIZE            Optional page size

Output:
  - Standard Markdown table of resources plus status (user-visible)
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

from _common import request_timeout, require_config  # noqa: E402
from _resource_object_actions import build_resource_object_actions  # noqa: E402


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


def meta_item(index: int, item: dict, scope: str, *, base_url: str = "") -> dict:
    href_category = "virtual-machines" if scope == "virtual_machines" else "cloud-resource"
    resource_id = str(item.get("id", ""))
    name = display_name(item)
    # Resource rows expose actions through sidecar metadata rather than
    # Markdown links. Core can render buttons when it understands the protocol,
    # while plain Markdown consumers still receive a readable resource table.
    object_actions = build_resource_object_actions(
        base_url,
        resource_id,
        category=href_category,
        resource_name=name,
        include_detail_action=True,
    )
    return {
        "index": index,
        "object_type": "virtual_machine" if scope == "virtual_machines" else "cloud_resource",
        "object_id": resource_id,
        "object_name": name,
        "object_actions": object_actions,
        "id": item.get("id", ""),
        "name": name,
        "scope": scope,
        "resourceType": item.get("resourceType", ""),
        "componentType": item.get("componentType", ""),
        "status": item.get("status", ""),
        "os": extract_os(item),
        "cloudEntryType": item.get("cloudEntryType", ""),
    }


def escape_markdown_cell(value: object) -> str:
    """Render one value safely inside a Markdown table cell."""
    rendered = str(value or "").replace("\n", " ").replace("\r", " ").strip()
    rendered = " ".join(rendered.split())
    return rendered.replace("|", "\\|")


def summary_label(scope: str) -> str:
    return "virtual machine(s)" if scope == "virtual_machines" else "resource(s)"


def render_resource_table(items: list[dict], *, scope: str) -> str:
    """Render SmartCMP resource list output as a standard Markdown table."""
    headers = ["#", "Name", "Status"]
    if scope == "virtual_machines":
        headers.append("OS")
    else:
        headers.extend(["Resource Type", "Component Type"])

    lines = [
        f"Found {len(items)} {summary_label(scope)}:",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for index, item in enumerate(items, start=1):
        row = [
            index,
            display_name(item),
            display_status(item),
        ]
        if scope == "virtual_machines":
            row.append(extract_os(item) or "N/A")
        else:
            row.extend(
                [
                    item.get("resourceType") or "N/A",
                    item.get("componentType") or "N/A",
                ]
            )
        lines.append("| " + " | ".join(escape_markdown_cell(value) for value in row) + " |")
    return "\n".join(lines)


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
        response = requests.get(url, headers=headers, verify=False, timeout=request_timeout())
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

    print(render_resource_table(items, scope=scope))
    print()

    meta = [
        meta_item(index, item, scope, base_url=base_url)
        for index, item in enumerate(items, start=1)
    ]
    print("##RESOURCE_DIRECTORY_META_START##", file=sys.stderr)
    print(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
    print("##RESOURCE_DIRECTORY_META_END##", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
