#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""List physical templates available to a SmartCMP request resource pool.

Usage:
  python list_physical_templates.py <RESOURCE_BUNDLE_ID> <LOGIC_TEMPLATE_ID>

The logical template must already have been selected from the resource-pool
filtered logical-template lookup. Each result keeps both request IDs so the
caller can serialize logicTemplateId together with physicalTemplateId.
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
    """Parse physical-template lookup arguments.

    Args:
        argv: Optional command-line arguments.

    Returns:
        Parsed argument namespace.
    """
    parser = argparse.ArgumentParser(
        description="List physical templates available to a SmartCMP resource pool"
    )
    parser.add_argument("resource_bundle_id", help="Selected resource pool ID")
    parser.add_argument("logic_template_id", help="Selected logical template ID")
    return parser.parse_args(argv)


def _get_json(url: str, *, headers: dict, params: dict) -> list[dict]:
    """GET a SmartCMP list endpoint and enforce its response contract."""
    response = requests.get(
        url,
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
        raise RuntimeError("Physical-template query returned an unexpected JSON shape.")
    if any(not isinstance(item, dict) for item in payload):
        raise RuntimeError("Physical-template query returned a non-object item.")
    return payload


def fetch_physical_templates(
    *,
    base_url: str,
    headers: dict,
    resource_bundle_id: str,
    logic_template_id: str,
) -> list[dict]:
    """Fetch physical templates supported by one request resource pool.

    Args:
        base_url: SmartCMP platform-api base URL.
        headers: HTTP headers containing provider authentication.
        resource_bundle_id: Selected resource pool ID.
        logic_template_id: Selected logical-template ID.

    Returns:
        Physical-template records carrying both request field IDs.

    Raises:
        RuntimeError: If any SmartCMP lookup fails.
    """
    physical_templates = _get_json(
        f"{base_url}/logic-templates/{logic_template_id}/physical-templates",
        headers=headers,
        params={"resourceBundleId": resource_bundle_id},
    )

    results: list[dict] = []
    for physical_template in physical_templates:
        if not physical_template.get("id"):
            continue
        physical_template_id = physical_template["id"]
        results.append(
            {
                "id": physical_template_id,
                "physicalTemplateId": physical_template_id,
                "logicTemplateId": logic_template_id,
                "name": (
                    physical_template.get("alias")
                    or physical_template.get("name")
                    or physical_template_id
                ),
                "default": bool(
                    physical_template.get("default")
                    or physical_template.get("isDefault")
                ),
            }
        )
    return results


def main(argv: list[str] | None = None) -> int:
    """Run the physical-template lookup command.

    Args:
        argv: Optional command-line arguments.

    Returns:
        Process exit code.
    """
    args = parse_args(argv)
    base_url, _auth_token, headers, _instance = require_config()
    try:
        templates = fetch_physical_templates(
            base_url=base_url,
            headers=headers,
            resource_bundle_id=args.resource_bundle_id,
            logic_template_id=args.logic_template_id,
        )
    except (RuntimeError, requests.RequestException) as exc:
        print(f"[ERROR] {exc}")
        return 1

    if not templates:
        print("Found 0 physical template(s).")
        print("##PHYSICAL_TEMPLATE_META_START##", file=sys.stderr)
        print(
            json.dumps(
                {
                    "internal_request_trace_id": os.environ.get(
                        "INTERNAL_REQUEST_TRACE_ID", ""
                    ),
                    "physicalTemplates": [],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        print("##PHYSICAL_TEMPLATE_META_END##", file=sys.stderr)
        return 0

    meta = [
        {"index": index, **template}
        for index, template in enumerate(templates, start=1)
    ]
    print(
        render_markdown_table(
            f"Found {len(meta)} physical template(s):",
            ["#", "Physical Template"],
            [
                [
                    item["index"],
                    item["name"],
                ]
                for item in meta
            ],
        )
    )
    print("##PHYSICAL_TEMPLATE_META_START##", file=sys.stderr)
    print(
        json.dumps(
            {
                "internal_request_trace_id": os.environ.get(
                    "INTERNAL_REQUEST_TRACE_ID", ""
                ),
                "physicalTemplates": meta,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        file=sys.stderr,
    )
    print("##PHYSICAL_TEMPLATE_META_END##", file=sys.stderr)
    return 0


_EXIT_CODE = main()
if _EXIT_CODE:
    raise SystemExit(_EXIT_CODE)
