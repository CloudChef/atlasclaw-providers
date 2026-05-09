# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Get SmartCMP catalog detail by catalog ID.

Usage:
  python get_catalog_detail.py <catalog_id>

Output:
  - Human-readable catalog summary
  - ##CATALOG_DETAIL_META_START## ... ##CATALOG_DETAIL_META_END##
      JSON object with structured catalog info for agent processing
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import requests

try:
    from _common import require_config
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _common import require_config


BASE_URL, AUTH_TOKEN, HEADERS, _ = require_config()

_PREAPPROVAL_HEADINGS = (
    "# Pre Approval Instructions",
    "# Preapproval Instructions",
    "# Pre-Approval Instructions",
)


def _extract_markdown_section(markdown_text: str, headings: tuple[str, ...]) -> tuple[str, str]:
    lines = markdown_text.splitlines()
    start_index = -1
    matched_heading = ""
    normalized_headings = {heading.strip(): heading.strip() for heading in headings}

    for index, line in enumerate(lines):
        stripped = line.strip().lstrip("\ufeff")
        if stripped in normalized_headings:
            start_index = index + 1
            matched_heading = normalized_headings[stripped]
            break

    if start_index == -1:
        return "", ""

    section_lines: list[str] = []
    for line in lines[start_index:]:
        if line.startswith("# "):
            break
        section_lines.append(line)
    return "\n".join(section_lines).strip(), matched_heading


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, dict) and "value" in value:
            value = value.get("value")
        if isinstance(value, (str, int, float)):
            text = str(value).strip()
            if text:
                return text
    return ""


def _catalog_name(catalog: dict[str, Any]) -> str:
    return _first_text(catalog.get("nameZh"), catalog.get("name"), catalog.get("displayName"))


def _build_meta(catalog: dict[str, Any], catalog_id: str) -> dict[str, Any]:
    raw_instructions = _first_text(catalog.get("instructions"))
    preapproval_instructions, preapproval_heading = _extract_markdown_section(
        raw_instructions,
        _PREAPPROVAL_HEADINGS,
    )

    meta = {
        "id": _first_text(catalog.get("id")) or catalog_id,
        "name": _catalog_name(catalog),
        "sourceKey": _first_text(catalog.get("sourceKey")),
        "serviceCategory": _first_text(catalog.get("serviceCategory")),
        "catalogType": _first_text(catalog.get("type")),
        "hasInstructions": bool(raw_instructions),
        "hasPreApprovalInstructions": bool(preapproval_instructions),
    }
    if preapproval_instructions:
        meta["preApprovalInstructions"] = preapproval_instructions
        meta["preApprovalInstructionHeading"] = preapproval_heading
    return meta


def _fetch_catalog(catalog_id: str) -> dict[str, Any]:
    response = requests.get(
        f"{BASE_URL}/catalogs/{catalog_id}",
        headers=HEADERS,
        verify=False,
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    catalog_id = argv[0].strip() if argv else ""
    if not catalog_id:
        print("[ERROR] Missing required catalog_id argument.")
        return 1

    try:
        catalog = _fetch_catalog(catalog_id)
    except requests.exceptions.RequestException as error:
        print(f"[ERROR] Request failed: {error}")
        return 1

    meta = _build_meta(catalog, catalog_id)
    print(f"Catalog Detail: {meta.get('name') or catalog_id}")
    print(f"Catalog ID: {meta.get('id') or catalog_id}")
    print(f"Has Pre Approval Instructions: {str(meta.get('hasPreApprovalInstructions')).lower()}")
    print("##CATALOG_DETAIL_META_START##", file=sys.stderr)
    print(json.dumps(meta, ensure_ascii=False), file=sys.stderr)
    print("##CATALOG_DETAIL_META_END##", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
