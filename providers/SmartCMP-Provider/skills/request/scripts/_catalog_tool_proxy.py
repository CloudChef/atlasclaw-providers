# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Reuse datasource catalog normalization without exposing every schema to the model."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import Any


_CATALOG_META_PATTERN = re.compile(
    r"##CATALOG_META_START##\s*(.*?)\s*##CATALOG_META_END##",
    re.DOTALL,
)


def load_catalog_envelope(
    keyword: str = "",
    *,
    catalog_id: str = "",
) -> tuple[int, dict[str, Any], str]:
    """Run the canonical datasource catalog loader and parse its metadata envelope.

    Args:
        keyword: Optional catalog-name filter passed to the datasource script.
        catalog_id: Optional exact catalog UUID. When present, the canonical
            loader uses the detail endpoint instead of a paginated list.

    Returns:
        A tuple containing the process exit code, parsed metadata envelope, and
        an error message. The envelope is empty when the child script fails or
        returns malformed metadata.
    """
    datasource_script = os.path.abspath(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..",
            "..",
            "datasource",
            "scripts",
            "list_services.py",
        )
    )
    command = [sys.executable, datasource_script]
    if catalog_id:
        command.extend(["--catalog-id", catalog_id])
    elif keyword:
        command.append(keyword)

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        env=os.environ.copy(),
    )
    if completed.returncode != 0:
        error = completed.stdout.strip() or completed.stderr.strip() or "Catalog lookup failed."
        if error.startswith("[ERROR]"):
            error = error.removeprefix("[ERROR]").strip()
        return completed.returncode, {}, error

    match = _CATALOG_META_PATTERN.search(completed.stderr)
    if match is None:
        return 1, {}, "Catalog lookup returned no metadata envelope."
    try:
        envelope = json.loads(match.group(1))
    except (TypeError, ValueError, json.JSONDecodeError):
        return 1, {}, "Catalog lookup returned invalid metadata."
    if not isinstance(envelope, dict):
        return 1, {}, "Catalog lookup metadata must be an object."
    if not isinstance(envelope.get("catalogs"), list):
        return 1, {}, "Catalog lookup metadata field 'catalogs' must be a list."
    return 0, envelope, ""


def build_catalog_summary(catalog: dict[str, Any]) -> dict[str, Any]:
    """Return only the unambiguous identity needed for catalog selection.

    The datasource ``sourceKey`` may itself look like a UUID but is not a valid
    request ``catalogId``. Object actions also add substantial prompt payload and
    are restored by the selected-catalog detail lookup.
    """
    summary_keys = (
        "index",
        "id",
        "name",
        "serviceCategory",
        "catalogType",
        "status",
    )
    return {key: catalog[key] for key in summary_keys if key in catalog}
