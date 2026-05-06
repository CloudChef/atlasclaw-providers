#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""List SmartCMP resource operations executable by the current user."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

import requests


SCRIPT_DIR = Path(__file__).resolve().parent
SHARED_SCRIPTS_DIR = SCRIPT_DIR.parents[1] / "shared" / "scripts"
if str(SHARED_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPTS_DIR))

from _common import require_config  # noqa: E402


DEFAULT_RESOURCE_CATEGORY = "virtual-machines"
RESOURCE_OPERATIONS_META_START = "##RESOURCE_OPERATIONS_META_START##"
RESOURCE_OPERATIONS_META_END = "##RESOURCE_OPERATIONS_META_END##"


def parse_resource_reference(
    resource_ref: str,
    default_category: str = DEFAULT_RESOURCE_CATEGORY,
) -> tuple[str, str]:
    """Extract the SmartCMP resource category and ID from a URL, route, or raw UUID.

    Args:
        resource_ref: SmartCMP detail URL, front-end route, or raw resource ID.
        default_category: Category to use when `resource_ref` is only an ID.

    Returns:
        A `(category, resource_id)` tuple suitable for `/nodes/{category}/{id}/resource-actions`.

    Raises:
        ValueError: If the resource ID cannot be extracted.
    """
    value = (resource_ref or "").strip()
    if not value:
        raise ValueError("resource_ref is required.")

    parsed = urlparse(value)
    route = parsed.fragment or parsed.path
    if not route and "#" in value:
        route = value.split("#", 1)[1]

    parts = [unquote(part) for part in route.split("/") if part]
    if "main" in parts:
        main_index = parts.index("main")
        if len(parts) > main_index + 2:
            return parts[main_index + 1], parts[main_index + 2]

    if len(parts) >= 3 and parts[-1] == "details":
        return parts[-3], parts[-2]

    if len(parts) >= 2 and "/" in value:
        return parts[0], parts[1]

    resource_id = unquote(parts[0]) if parts else value
    if not resource_id:
        raise ValueError("resource ID could not be extracted from resource_ref.")
    return default_category, resource_id


def normalize_operation_id(operation_id: str) -> str:
    """Normalize a user-supplied operation ID to SmartCMP's lowercase underscore form."""
    return (operation_id or "").strip().lower().replace("-", "_").replace(" ", "_")


def parameters_are_empty(value: Any) -> bool:
    """Return whether a SmartCMP operation parameter declaration is empty enough to execute."""
    if value in (None, "", {}, []):
        return True
    if isinstance(value, str):
        stripped = value.strip()
        if stripped in ("", "{}"):
            return True
        try:
            parsed = json.loads(stripped)
        except (TypeError, ValueError):
            return False
        return parsed in ({}, [])
    return False


def operation_rejection_reason(operation: dict[str, Any]) -> str:
    """Explain why an operation is outside this tool's executable no-parameter scope."""
    if not normalize_operation_id(str(operation.get("id") or "")):
        return "Operation has no ID."
    if operation.get("enabled") is not True:
        return str(
            operation.get("disabledMsgZh")
            or operation.get("disabledMsg")
            or "Operation is not enabled for the current user or resource state."
        )
    if operation.get("webOperation") is True:
        return "Operation must be executed in the SmartCMP web UI."
    if operation.get("inputsForm") not in (None, "", {}, []):
        return "Operation requires form input, which is not supported by this tool."
    if not parameters_are_empty(operation.get("parameters")):
        return "Operation requires parameters, which is not supported by this tool."
    return ""


def operation_is_executable(operation: dict[str, Any]) -> bool:
    """Return whether the operation can be executed by this user-scoped no-parameter tool."""
    return not operation_rejection_reason(operation)


def normalize_operation(index: int, operation: dict[str, Any]) -> dict[str, Any]:
    """Build structured metadata for an operation returned by SmartCMP."""
    action_category = operation.get("actionCategory") or {}
    category_name = ""
    if isinstance(action_category, dict):
        category_name = str(action_category.get("name") or "")
    elif action_category:
        category_name = str(action_category)

    name = str(operation.get("name") or "")
    name_zh = str(operation.get("nameZh") or "")
    return {
        "index": index,
        "id": normalize_operation_id(str(operation.get("id") or "")),
        "name": name,
        "nameZh": name_zh,
        "displayName": name_zh or name or normalize_operation_id(str(operation.get("id") or "")),
        "category": category_name,
        "type": operation.get("type") or "",
        "supportBatchAction": bool(operation.get("supportBatchAction")),
        "supportScheduledTask": bool(operation.get("supportScheduledTask")),
    }


def build_resource_actions_url(base_url: str, category: str, resource_id: str) -> str:
    """Build the user-scoped SmartCMP resource-actions URL for one resource."""
    encoded_category = quote(category, safe="")
    encoded_resource_id = quote(resource_id, safe="")
    return f"{base_url}/nodes/{encoded_category}/{encoded_resource_id}/resource-actions"


def extract_error_message(response: requests.Response) -> str:
    """Extract a concise SmartCMP error message from an HTTP response."""
    try:
        body = response.json()
    except (ValueError, TypeError, AttributeError):
        body = None

    if isinstance(body, dict):
        message = str(body.get("message") or body.get("error") or body.get("errMsg") or "").strip()
        if message:
            return message
    return (response.text or "").strip()


def fetch_resource_operations(
    base_url: str,
    headers: dict[str, str],
    category: str,
    resource_id: str,
) -> list[dict[str, Any]]:
    """Fetch resource-scoped operations using the current SmartCMP user context.

    Raises:
        RuntimeError: If SmartCMP rejects the request or returns an unexpected payload.
    """
    url = build_resource_actions_url(base_url, category, resource_id)
    try:
        response = requests.get(url, headers=headers, verify=False, timeout=30)
    except requests.RequestException as exc:
        raise RuntimeError(f"SmartCMP resource operation list request failed: {exc}") from exc

    if response.status_code != 200:
        message = extract_error_message(response)
        raise RuntimeError(f"HTTP {response.status_code}: {message}")

    try:
        payload = response.json()
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"SmartCMP returned an invalid JSON operation list: {exc}") from exc

    if not isinstance(payload, list):
        raise RuntimeError("SmartCMP returned an unexpected operation list payload.")

    return [item for item in payload if isinstance(item, dict)]


def get_executable_operations(
    base_url: str,
    headers: dict[str, str],
    category: str,
    resource_id: str,
) -> list[dict[str, Any]]:
    """Return operations executable by the current user and this no-parameter tool."""
    operations = fetch_resource_operations(base_url, headers, category, resource_id)
    return [operation for operation in operations if operation_is_executable(operation)]


def render_operation_list(
    *,
    category: str,
    resource_id: str,
    operations: list[dict[str, Any]],
) -> str:
    """Render a concise human-readable operation list and stderr metadata block."""
    lines = [f"Executable operations for resource {resource_id} ({category}):"]
    if not operations:
        lines.append("No executable no-parameter operations were returned for the current user.")
        return "\n".join(lines)

    for index, operation in enumerate(operations, start=1):
        item = normalize_operation(index, operation)
        suffixes = []
        if item["category"]:
            suffixes.append(str(item["category"]))
        if item["supportBatchAction"]:
            suffixes.append("batch")
        if item["supportScheduledTask"]:
            suffixes.append("scheduled")
        suffix = f" | {'; '.join(suffixes)}" if suffixes else ""
        lines.append(f"  [{index}] {item['displayName']} ({item['id']}){suffix}")

    return "\n".join(lines)


def emit_operations_meta(operations: list[dict[str, Any]]) -> None:
    """Emit structured operation metadata for agent selection by index or ID."""
    meta = [normalize_operation(index, item) for index, item in enumerate(operations, start=1)]
    print(RESOURCE_OPERATIONS_META_START, file=sys.stderr)
    print(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
    print(RESOURCE_OPERATIONS_META_END, file=sys.stderr)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for listing user-executable resource operations."""
    parser = argparse.ArgumentParser(
        description="List SmartCMP resource operations executable by the current user."
    )
    parser.add_argument(
        "resource_ref",
        help="SmartCMP resource ID or detail URL such as #/main/virtual-machines/<id>/details.",
    )
    parser.add_argument(
        "--category",
        default=DEFAULT_RESOURCE_CATEGORY,
        help="Fallback resource category when resource_ref is a raw ID. Default: virtual-machines.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for permission-scoped SmartCMP operation discovery."""
    try:
        args = parse_args(argv)
        category, resource_id = parse_resource_reference(args.resource_ref, args.category)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 1

    base_url, _auth_token, headers, _instance = require_config()
    try:
        operations = get_executable_operations(base_url, headers, category, resource_id)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 1

    print(render_operation_list(category=category, resource_id=resource_id, operations=operations))
    emit_operations_meta(operations)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
