# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""List request catalog choices while deferring selected-catalog schema loading."""

from __future__ import annotations

import json
import os
import sys

try:
    from _catalog_tool_proxy import build_catalog_summary, load_catalog_envelope
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _catalog_tool_proxy import build_catalog_summary, load_catalog_envelope


def _render_catalog_choices(catalogs: list[dict]) -> str:
    lines = [f"Found {len(catalogs)} matching published catalog(s):"]
    for catalog in catalogs:
        index = catalog.get("index", "")
        name = catalog.get("name", "")
        category = catalog.get("serviceCategory", "")
        lines.append(f"{index}. {name} ({category})")
    return "\n".join(lines)


def _build_compact_catalogs(catalogs: list[object]) -> tuple[list[dict], str]:
    compact_catalogs: list[dict] = []
    seen_ids: set[str] = set()
    seen_indices: set[int] = set()
    for position, catalog in enumerate(catalogs, start=1):
        if not isinstance(catalog, dict):
            return [], f"Catalog metadata item {position} must be an object."

        summary = build_catalog_summary(catalog)
        catalog_id = str(summary.get("id") or "").strip()
        catalog_name = str(summary.get("name") or "").strip()
        catalog_index = summary.get("index")
        if not catalog_id:
            return [], f"Catalog metadata item {position} has no catalog UUID."
        if not catalog_name:
            return [], f"Catalog metadata item {position} has no display name."
        if (
            isinstance(catalog_index, bool)
            or not isinstance(catalog_index, int)
            or catalog_index <= 0
        ):
            return [], f"Catalog metadata item {position} has no usable display index."
        if catalog_id in seen_ids:
            return [], f"Catalog metadata contains duplicate catalog UUID: {catalog_id}."
        if catalog_index in seen_indices:
            return [], f"Catalog metadata contains duplicate display index: {catalog_index}."

        seen_ids.add(catalog_id)
        seen_indices.add(catalog_index)
        summary["id"] = catalog_id
        summary["name"] = catalog_name
        compact_catalogs.append(summary)
    return compact_catalogs, ""


def main(argv: list[str] | None = None) -> int:
    """List catalog choices and emit compact identity metadata.

    Args:
        argv: Optional CLI arguments containing a single catalog-name keyword.

    Returns:
        Zero on success, or a non-zero child/metadata error code.
    """
    argv = argv if argv is not None else sys.argv[1:]
    keyword = argv[0].strip() if argv else ""
    exit_code, envelope, error = load_catalog_envelope(keyword)
    if exit_code:
        print(f"[ERROR] {error}")
        return exit_code

    compact_catalogs, error = _build_compact_catalogs(envelope["catalogs"])
    if error:
        print(f"[ERROR] {error}")
        return 1
    compact_envelope = {
        "internal_request_trace_id": envelope.get("internal_request_trace_id", ""),
        "catalogs": compact_catalogs,
        "catalog_detail_required_after_selection": True,
    }

    print(_render_catalog_choices(compact_catalogs))
    print("##CATALOG_META_START##", file=sys.stderr)
    print(
        json.dumps(compact_envelope, ensure_ascii=False, separators=(",", ":")),
        file=sys.stderr,
    )
    print("##CATALOG_META_END##", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
