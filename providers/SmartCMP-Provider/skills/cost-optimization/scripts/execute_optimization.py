#!/usr/bin/env python3
"""Execute a SmartCMP-native cost optimization fix."""

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


def build_execution_result(violation_id: str, submitted: bool, message: str, response_body=None) -> dict:
    """Build the structured execution result."""
    return {
        "violationId": violation_id,
        "requested": True,
        "executionSubmitted": submitted,
        "executionMode": "smartcmp_day2_fix",
        "message": message,
        "followUpRequired": True,
        "response": response_body or {},
    }


def render_execution_result(result: dict) -> str:
    """Render a human-readable execution summary plus structured block."""
    lines = [
        f"Violation {result['violationId']}: {'submitted' if result['executionSubmitted'] else 'not submitted'}",
        result["message"],
        "",
        "##COST_EXECUTION_START##",
        json.dumps(result, ensure_ascii=False),
        "##COST_EXECUTION_END##",
    ]
    return "\n".join(lines)


def extract_error_message(response) -> str:
    """Extract a user-facing error message from a SmartCMP response."""
    try:
        body = response.json()
    except (ValueError, TypeError, AttributeError):
        body = None

    if isinstance(body, dict):
        message = str(body.get("message") or "").strip()
        if message:
            return message

    return (response.text or "").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute a SmartCMP-native day2 cost optimization fix.")
    parser.add_argument("--id", required=True, help="Violation identifier.")
    args = parser.parse_args()

    violation_id = (args.id or "").strip()
    if not violation_id:
        print("[ERROR] --id must not be empty.")
        return 1

    base_url, auth_token, headers, _ = require_config()
    try:
        response = requests.post(
            f"{base_url}/compliance-policies/violations/day2/fix/{violation_id}",
            headers=headers,
            json={},
            verify=False,
            timeout=30,
        )
    except RequestException as exc:
        print(f"[ERROR] SmartCMP day2 fix request failed: {exc}")
        return 1

    if response.status_code != 200:
        message = extract_error_message(response)
        if "no repair action configured" in message.lower():
            print(
                "[ERROR] SmartCMP rejected remediation because the policy has no repair action "
                "configured. Configure the policy's day2 repair task before retrying."
            )
        else:
            print(f"[ERROR] HTTP {response.status_code}: {message}")
        return 1

    if response.text:
        try:
            body = response.json()
        except (ValueError, TypeError) as exc:
            print(f"[ERROR] SmartCMP returned an invalid JSON response: {exc}")
            return 1
    else:
        body = {}

    result = build_execution_result(
        violation_id=violation_id,
        submitted=True,
        message="SmartCMP day2 fix request submitted.",
        response_body=body,
    )
    print(render_execution_result(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
