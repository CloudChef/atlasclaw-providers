#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Execute user-scoped no-parameter SmartCMP resource operations."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import requests
from requests import RequestException

try:
    from list_resource_operations import (
        DEFAULT_RESOURCE_CATEGORY,
        fetch_resource_operations,
        normalize_operation_id,
        operation_rejection_reason,
        parse_resource_reference,
    )
except ImportError:
    import os

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from list_resource_operations import (
        DEFAULT_RESOURCE_CATEGORY,
        fetch_resource_operations,
        normalize_operation_id,
        operation_rejection_reason,
        parse_resource_reference,
    )

try:
    from _common import require_config
except ImportError:
    import os

    sys.path.insert(
        0,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared", "scripts"),
    )
    from _common import require_config


ACTION_ALIASES = {
    "start": "start",
    "power_on": "start",
    "poweron": "start",
    "open": "start",
    "启动": "start",
    "开机": "start",
    "开启": "start",
    "stop": "stop",
    "power_off": "stop",
    "poweroff": "stop",
    "shutdown": "stop",
    "关机": "stop",
    "停止": "stop",
    "停机": "stop",
    "关闭": "stop",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for executing a SmartCMP resource operation."""
    parser = argparse.ArgumentParser(
        description="Execute SmartCMP no-parameter resource operations by resource ID."
    )
    parser.add_argument("resource_ids", nargs="+", help="One or more SmartCMP resource IDs or detail URLs.")
    parser.add_argument(
        "--category",
        default=DEFAULT_RESOURCE_CATEGORY,
        help="Fallback resource category when a target is a raw ID. Default: virtual-machines.",
    )
    parser.add_argument(
        "--action",
        required=True,
        help="SmartCMP operation ID to execute. start/stop aliases are still supported.",
    )
    return parser.parse_args(argv)


def normalize_action(action: str) -> str:
    """Resolve legacy power aliases and arbitrary operation IDs to SmartCMP IDs."""
    normalized = normalize_operation_id(action)
    mapped = ACTION_ALIASES.get(normalized)
    if mapped:
        return mapped
    if normalized:
        return normalized

    raise ValueError("action is required.")


def normalize_resource_targets(
    values: list[str],
    default_category: str = DEFAULT_RESOURCE_CATEGORY,
) -> list[dict[str, str]]:
    """Parse resource IDs or detail URLs into category/resource ID targets."""
    targets: list[dict[str, str]] = []
    for value in values:
        for candidate in str(value).split(","):
            normalized = candidate.strip()
            if not normalized:
                continue
            category, resource_id = parse_resource_reference(normalized, default_category)
            target = {"category": category, "resourceId": resource_id}
            if target not in targets:
                targets.append(target)

    if not targets:
        raise ValueError("At least one resource ID is required.")
    return targets


def normalize_resource_ids(values: list[str]) -> list[str]:
    """Return de-duplicated resource IDs from raw IDs or SmartCMP detail URLs."""
    targets = normalize_resource_targets(values)
    resource_ids: list[str] = []
    for target in targets:
        resource_id = target["resourceId"]
        if resource_id not in resource_ids:
            resource_ids.append(resource_id)
    return resource_ids


def serialize_resource_ids(resource_ids: list[str]) -> str:
    if len(resource_ids) == 1:
        return resource_ids[0]
    return ",".join(resource_ids)


def build_request_payload(resource_ids: list[str], action: str) -> dict[str, object]:
    normalized_action = normalize_action(action)
    return {
        "operationId": normalized_action,
        "resourceIds": serialize_resource_ids(resource_ids),
        "scheduledTaskMetadataRequest": {
            "cronExpression": "",
            "cycleDescription": "",
            "cycled": False,
            "scheduleEnabled": False,
            "scheduledTime": None,
        },
    }


def find_operation(operations: list[dict[str, Any]], action: str) -> dict[str, Any] | None:
    """Find a SmartCMP operation by normalized operation ID."""
    normalized_action = normalize_action(action)
    for operation in operations:
        if normalize_operation_id(str(operation.get("id") or "")) == normalized_action:
            return operation
    return None


def validate_operation_for_targets(
    *,
    base_url: str,
    headers: dict[str, str],
    targets: list[dict[str, str]],
    action: str,
) -> None:
    """Verify the current user can execute the no-parameter action on every target.

    Raises:
        ValueError: If SmartCMP does not expose the action for this user/resource or
            the operation requires web/form/parameter handling outside this tool's scope.
    """
    normalized_action = normalize_action(action)
    for target in targets:
        category = target["category"]
        resource_id = target["resourceId"]
        operations = fetch_resource_operations(base_url, headers, category, resource_id)
        operation = find_operation(operations, normalized_action)
        if operation is None:
            raise ValueError(
                f"Operation '{normalized_action}' is not available for resource {resource_id} "
                f"under category {category}."
            )

        reason = operation_rejection_reason(operation)
        if reason:
            raise ValueError(
                f"Operation '{normalized_action}' is not executable for resource {resource_id}: {reason}"
            )


def build_operation_result(
    *,
    resource_ids: list[str],
    action: str,
) -> dict[str, object]:
    return {
        "action": action,
        "resourceIds": list(resource_ids),
        "submitted": True,
        "message": f"SmartCMP {action} request submitted.",
        "verificationHint": "Refresh the resource list or resource detail to confirm the latest state.",
    }


def normalize_flag(value) -> str:
    return str(value).strip().lower()


def business_error_message(body) -> str:
    if not isinstance(body, dict):
        return ""

    message = str(body.get("message") or body.get("error") or body.get("errMsg") or "").strip()
    success = body.get("success")
    if success is False or normalize_flag(success) == "false":
        return message or "SmartCMP reported operation failure."

    state = normalize_flag(body.get("status") or body.get("state"))
    if state in {"failed", "failure", "error", "rejected", "canceled", "cancelled"}:
        return message or f"SmartCMP reported operation state: {state}."

    code = body.get("code")
    if code not in (None, "", 0, "0", 200, "200") and normalize_flag(code) not in {"ok", "success"}:
        return message or f"SmartCMP returned business code: {code}."

    return ""


def render_operation_result(result: dict[str, object]) -> str:
    resource_ids = result.get("resourceIds") or []
    action = str(result.get("action") or "")
    lines = [
        f"Submitted {action} request for {len(resource_ids)} resource(s).",
        f"Resource IDs: {', '.join(resource_ids)}",
        "",
        "##RESOURCE_POWER_OPERATION_START##",
        json.dumps(result, ensure_ascii=False),
        "##RESOURCE_POWER_OPERATION_END##",
    ]
    return "\n".join(lines)


def extract_error_message(response) -> str:
    try:
        body = response.json()
    except (ValueError, TypeError, AttributeError):
        body = None

    if isinstance(body, dict):
        message = str(body.get("message") or "").strip()
        if message:
            return message

    return (response.text or "").strip()


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        action = normalize_action(args.action)
        targets = normalize_resource_targets(args.resource_ids, args.category)
        resource_ids = [target["resourceId"] for target in targets]
        request_payload = build_request_payload(resource_ids, action)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 1

    base_url, _auth_token, headers, _instance = require_config()
    try:
        validate_operation_for_targets(
            base_url=base_url,
            headers=headers,
            targets=targets,
            action=action,
        )
    except (RuntimeError, ValueError) as exc:
        print(f"[ERROR] {exc}")
        return 1

    try:
        response = requests.post(
            f"{base_url}/nodes/resource-operations",
            headers=headers,
            json=request_payload,
            verify=False,
            timeout=30,
        )
    except RequestException as exc:
        print(f"[ERROR] SmartCMP resource power request failed: {exc}")
        return 1

    if response.status_code != 200:
        print(f"[ERROR] HTTP {response.status_code}: {extract_error_message(response)}")
        return 1

    body = {}
    if response.text:
        try:
            body = response.json()
        except (ValueError, TypeError) as exc:
            print(f"[ERROR] SmartCMP returned an invalid JSON response: {exc}")
            return 1

    business_error = business_error_message(body)
    if business_error:
        print(f"[ERROR] SmartCMP resource operation was not submitted: {business_error}")
        return 1

    result = build_operation_result(
        resource_ids=resource_ids,
        action=action,
    )
    print(render_operation_result(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
