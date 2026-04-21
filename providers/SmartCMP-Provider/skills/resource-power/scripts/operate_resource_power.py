#!/usr/bin/env python3
"""Start or stop SmartCMP cloud resources through the native power endpoint."""

from __future__ import annotations

import argparse
import json
import sys

import requests
from requests import RequestException

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
    parser = argparse.ArgumentParser(
        description="Start or stop SmartCMP cloud resources by resource ID."
    )
    parser.add_argument("resource_ids", nargs="+", help="One or more SmartCMP resource IDs.")
    parser.add_argument("--action", required=True, help="Power action: start or stop.")
    return parser.parse_args(argv)


def normalize_action(action: str) -> str:
    normalized = (action or "").strip().lower().replace("-", "_").replace(" ", "_")
    mapped = ACTION_ALIASES.get(normalized)
    if mapped:
        return mapped

    valid_actions = ", ".join(sorted({"start", "stop"}))
    raise ValueError(f"Unsupported action '{action}'. Expected one of: {valid_actions}.")


def normalize_resource_ids(values: list[str]) -> list[str]:
    resource_ids: list[str] = []
    for value in values:
        for candidate in str(value).split(","):
            normalized = candidate.strip()
            if normalized and normalized not in resource_ids:
                resource_ids.append(normalized)

    if not resource_ids:
        raise ValueError("At least one resource ID is required.")
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


def build_operation_result(
    *,
    resource_ids: list[str],
    action: str,
    request_payload: dict[str, object],
    response_body=None,
) -> dict[str, object]:
    return {
        "action": action,
        "resourceIds": list(resource_ids),
        "submitted": True,
        "request": request_payload,
        "message": f"SmartCMP {action} request submitted.",
        "verificationHint": "Refresh the resource list or resource detail to confirm the latest state.",
        "response": {} if response_body is None else response_body,
    }


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
        resource_ids = normalize_resource_ids(args.resource_ids)
        request_payload = build_request_payload(resource_ids, action)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 1

    base_url, _auth_token, headers, _instance = require_config()

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

    if response.text:
        try:
            body = response.json()
        except (ValueError, TypeError) as exc:
            print(f"[ERROR] SmartCMP returned an invalid JSON response: {exc}")
            return 1
    else:
        body = {}

    result = build_operation_result(
        resource_ids=resource_ids,
        action=action,
        request_payload=request_payload,
        response_body=body,
    )
    print(render_operation_result(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
