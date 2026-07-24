# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Load normalized request metadata for one selected SmartCMP catalog."""

from __future__ import annotations

import json
import os
import sys

try:
    from _catalog_tool_proxy import load_catalog_envelope
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _catalog_tool_proxy import load_catalog_envelope


def main(argv: list[str] | None = None) -> int:
    """Resolve one catalog UUID to its full normalized request metadata.

    Args:
        argv: Optional CLI arguments whose first value is the selected catalog UUID.

    Returns:
        Zero when the catalog is found, otherwise a non-zero validation or lookup
        error code.
    """
    argv = argv if argv is not None else sys.argv[1:]
    catalog_id = argv[0].strip() if argv else ""
    if not catalog_id:
        print("[ERROR] Missing required catalog_id argument.")
        return 1

    exit_code, envelope, error = load_catalog_envelope(catalog_id=catalog_id)
    if exit_code:
        print(f"[ERROR] {error}")
        return exit_code

    catalogs = envelope["catalogs"]
    if len(catalogs) != 1 or not isinstance(catalogs[0], dict):
        print("[ERROR] Exact catalog lookup must return one catalog metadata object.")
        return 1

    selected = catalogs[0]
    selected_id = str(selected.get("id") or "").strip()
    if selected_id != catalog_id:
        print(
            "[ERROR] Exact catalog lookup returned a different catalog UUID: "
            f"{selected_id or '<missing>'}."
        )
        return 1
    status = str(selected.get("status") or "").strip().upper()
    if status and status != "PUBLISHED":
        print(f"[ERROR] Selected catalog is no longer published: {catalog_id}")
        return 1

    print(f"Selected catalog: {selected.get('name') or catalog_id}")
    print("##CATALOG_DETAIL_META_START##", file=sys.stderr)
    print(
        json.dumps(
            {
                "internal_request_trace_id": envelope.get("internal_request_trace_id", ""),
                "catalog": selected,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        file=sys.stderr,
    )
    print("##CATALOG_DETAIL_META_END##", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
