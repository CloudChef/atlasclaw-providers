"""Operate on SmartCMP alerts with validated English action names."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _alarm_common import map_action_to_status, normalize_action, put_json


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Operate on SmartCMP alert(s).")
    parser.add_argument("alert_ids", nargs="+", help="One or more alert identifiers.")
    parser.add_argument("--action", required=True, help="English action: mute, resolve, or reopen.")
    return parser.parse_args(argv)


def build_request_payload(alert_ids: list[str], action: str) -> dict[str, object]:
    """Build the SmartCMP operation payload from validated inputs."""
    normalized_action = normalize_action(action)
    return {
        "ids": list(alert_ids),
        "status": map_action_to_status(normalized_action),
    }


def emit_summary(alert_ids: list[str], action: str, status: str) -> None:
    """Print a short human summary for the operation."""
    print(f"Updated {len(alert_ids)} alert(s). Action: {action}. Status: {status}.")


def emit_operation_block(payload: dict[str, object]) -> None:
    """Print the structured operation result payload."""
    print("##ALARM_OPERATION_START##")
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    print("##ALARM_OPERATION_END##")


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        action = normalize_action(args.action)
        request_payload = build_request_payload(args.alert_ids, action)
        result = put_json("/alarm-alert/operation", payload=request_payload)

        payload = {
            "action": action,
            "status": request_payload["status"],
            "alert_ids": list(args.alert_ids),
            "request": request_payload,
            "result": result,
        }
        emit_summary(args.alert_ids, action, str(request_payload["status"]))
        emit_operation_block(payload)
        return 0
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 1
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
