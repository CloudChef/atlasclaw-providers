"""Analyze a SmartCMP alert and emit a structured assessment block."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _alarm_common import get_json


def _load_local_analysis_module():
    """Load the sibling alarm analysis helper without colliding with other skills."""
    module_path = SCRIPT_DIR / "_analysis.py"
    spec = importlib.util.spec_from_file_location("_smartcmp_alarm_analysis", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load analysis helpers from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


try:
    from _analysis import (
        build_assessment,
        build_recommendations,
        normalize_alert_fact,
        suggest_status_operation,
    )
except ImportError:
    _analysis_module = _load_local_analysis_module()
    build_assessment = _analysis_module.build_assessment
    build_recommendations = _analysis_module.build_recommendations
    normalize_alert_fact = _analysis_module.normalize_alert_fact
    suggest_status_operation = _analysis_module.suggest_status_operation


def positive_int(value: str) -> int:
    """Parse a strictly positive integer argument."""
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze a SmartCMP alert.")
    parser.add_argument("alert_id", help="Alert identifier to analyze.")
    parser.add_argument("--days", type=positive_int, default=7, help="Trend lookback window in days.")
    return parser.parse_args(argv)


def safe_get_json(path: str, *, params: dict[str, Any] | None = None, timeout: int = 30) -> Any:
    """Best-effort JSON fetch for optional context endpoints."""
    try:
        return get_json(path, params=params, timeout=timeout)
    except Exception:
        return None


def build_detail_context(alert: dict[str, Any], days: int) -> dict[str, Any]:
    """Collect optional supporting context without failing the core analysis."""
    return {
        "recent_overview": safe_get_json("/alarm-overview/recent"),
        "alarm_trend": safe_get_json("/alarm-overview/alarm-trend", params={"days": days}),
        "alert_detail_stats": safe_get_json(
            "/stats/alarm-alert/detail",
            params={"alertId": alert.get("id", "")},
        ),
    }


def analyze_single_alert(alert_id: str, *, days: int) -> dict[str, Any]:
    """Fetch, normalize, and assess a single alert."""
    alert = get_json(f"/alarm-alert/{alert_id}")
    if not isinstance(alert, dict) or not alert:
        raise RuntimeError(f"Alert '{alert_id}' was not found.")

    policy_id = alert.get("alarmPolicyId", "")
    if not policy_id:
        raise RuntimeError(f"Alert '{alert_id}' does not reference an alarm policy.")

    policy = get_json(f"/alarm-policies/{policy_id}")
    if not isinstance(policy, dict) or not policy:
        raise RuntimeError(f"Alarm policy '{policy_id}' was not found for alert '{alert_id}'.")

    detail = build_detail_context(alert, days)
    fact = normalize_alert_fact(alert, policy, detail=detail)
    assessment = build_assessment(fact)
    recommendations = build_recommendations(fact, assessment)
    suggested_status_operation = suggest_status_operation(fact, assessment)

    return {
        "alert_ids": [alert_id],
        "facts": [fact],
        "assessment": assessment,
        "recommendations": recommendations,
        "suggested_status_operation": suggested_status_operation,
    }


def emit_summary(payload: dict[str, Any]) -> None:
    """Print a short human-readable summary before the machine block."""
    assessment = payload.get("assessment", {})
    pattern = assessment.get("pattern", "unknown")
    risk = assessment.get("risk", "low")
    alert_count = len(payload.get("alert_ids", []))
    print(f"Analyzed {alert_count} alert(s). Pattern: {pattern}. Risk: {risk}.")


def emit_analysis_block(payload: dict[str, Any]) -> None:
    """Print the structured alarm analysis payload."""
    print("##ALARM_ANALYSIS_START##")
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    print("##ALARM_ANALYSIS_END##")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = analyze_single_alert(args.alert_id, days=args.days)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 1

    emit_summary(payload)
    emit_analysis_block(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
