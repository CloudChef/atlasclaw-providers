#!/usr/bin/env python3
"""Execute a SmartCMP-native cost optimization fix."""

import argparse
import json
import sys

import requests

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

def main() -> int:
    parser = argparse.ArgumentParser(description="Execute a SmartCMP-native day2 cost optimization fix.")
    parser.add_argument("--id", required=True, help="Violation identifier.")
    args = parser.parse_args()

    violation_id = (args.id or "").strip()
    if not violation_id:
        print("[ERROR] --id must not be empty.")
        return 1

    base_url, auth_token, _, _ = require_config()
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "CloudChef-Authenticate": auth_token,
    }
    response = requests.post(
        f"{base_url}/compliance-policies/violations/day2/fix/{violation_id}",
        headers=headers,
        json={},
        verify=False,
        timeout=30,
    )
    if response.status_code != 200:
        print(f"[ERROR] HTTP {response.status_code}: {response.text}")
        return 1

    body = response.json() if response.text else {}
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
