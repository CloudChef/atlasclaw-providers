# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Analyze a SmartCMP alert and emit a structured assessment block."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SHARED_SCRIPT_DIR = SCRIPT_DIR.parent.parent / "shared" / "scripts"
DATASOURCE_SCRIPT_DIR = SCRIPT_DIR.parent.parent / "datasource" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _alarm_common import get_connection, get_json


def _load_local_analysis_module():
    """Load the sibling alarm analysis helper without colliding with other skills."""
    module_path = SCRIPT_DIR / "_analysis.py"
    spec = importlib.util.spec_from_file_location("_smartcmp_alarm_analysis", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load analysis helpers from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_shared_resource_module():
    """Load the shared resource discovery helper used by datasource skill."""
    module_path = DATASOURCE_SCRIPT_DIR / "list_resource.py"
    spec = importlib.util.spec_from_file_location("_smartcmp_shared_list_resource", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load shared resource helpers from {module_path}")
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


_resource_module = _load_shared_resource_module()
collect_resource_ids_from_summaries = _resource_module.collect_resource_ids_from_summaries
load_resource_records = _resource_module.load_resource_records
resource_request_json = _resource_module.request_json
search_resource_summaries = _resource_module.search_resource_summaries


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


def extract_resource_ids(alert: dict[str, Any]) -> list[str]:
    """Collect SmartCMP resource identifiers that can be resolved via datasource."""
    resource_ids: list[str] = []
    raw_ids = alert.get("entityInstanceId")
    if isinstance(raw_ids, list):
        resource_ids.extend(str(item) for item in raw_ids if item not in (None, ""))
    elif raw_ids not in (None, ""):
        resource_ids.append(str(raw_ids))

    node_instance_id = alert.get("nodeInstanceId")
    if node_instance_id not in (None, ""):
        resource_ids.append(str(node_instance_id))

    deduped: list[str] = []
    for resource_id in resource_ids:
        if not resource_id or resource_id in deduped:
            continue
        deduped.append(resource_id)
    return deduped


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if not value or value in deduped:
            continue
        deduped.append(value)
    return deduped


def _has_resolved_resource(records: list[dict[str, Any]]) -> bool:
    return any(record.get("fetchStatus") == "ok" for record in records)


def _load_resource_records_by_ids(
    resource_ids: list[str],
    *,
    base_url: str,
    headers: dict[str, str],
) -> list[dict[str, Any]]:
    if not resource_ids:
        return []
    try:
        records = load_resource_records(
            resource_ids,
            base_url=base_url,
            headers=headers,
            request_fn=resource_request_json,
        )
    except (Exception, SystemExit):
        return []

    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, dict)]


def safe_load_resource_records(alert: dict[str, Any]) -> list[dict[str, Any]]:
    """Best-effort resource enrichment using datasource list_resource helpers."""
    try:
        base_url, headers, _ = get_connection()
    except (Exception, SystemExit):
        return []

    candidate_ids = extract_resource_ids(alert)
    records = _load_resource_records_by_ids(candidate_ids, base_url=base_url, headers=headers)
    if _has_resolved_resource(records):
        return records

    fallback_lookup_ids: list[str] = []

    node_instance_id = str(alert.get("nodeInstanceId") or "").strip()
    if node_instance_id:
        try:
            fallback_lookup_ids.extend(
                collect_resource_ids_from_summaries(
                    search_resource_summaries(
                        base_url=base_url,
                        headers=headers,
                        request_fn=resource_request_json,
                        params={"nodeInstanceId": node_instance_id},
                    )
                )
            )
        except Exception:
            pass

    resource_external_id = str(alert.get("resourceExternalId") or "").strip()
    if not fallback_lookup_ids and resource_external_id:
        try:
            fallback_lookup_ids.extend(
                collect_resource_ids_from_summaries(
                    search_resource_summaries(
                        base_url=base_url,
                        headers=headers,
                        request_fn=resource_request_json,
                        params={"externalIds": resource_external_id},
                    )
                )
            )
        except Exception:
            pass

    resource_name = (
        str(alert.get("resourceExternalName") or "").strip()
        or str(alert.get("entityInstanceName") or "").strip()
    )
    if not fallback_lookup_ids and resource_name:
        try:
            fallback_lookup_ids.extend(
                collect_resource_ids_from_summaries(
                    search_resource_summaries(
                        base_url=base_url,
                        headers=headers,
                        request_fn=resource_request_json,
                        payload={"queryValue": resource_name},
                    ),
                    expected_name=resource_name,
                    preferred_external_id=resource_external_id,
                    preferred_node_instance_id=node_instance_id,
                )
            )
        except Exception:
            pass

    fallback_lookup_ids = [
        resource_id for resource_id in _dedupe_strings(fallback_lookup_ids) if resource_id not in candidate_ids
    ]
    if not fallback_lookup_ids:
        return records

    fallback_records = _load_resource_records_by_ids(
        fallback_lookup_ids,
        base_url=base_url,
        headers=headers,
    )
    return records + fallback_records


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
    resource_records = safe_load_resource_records(alert)
    fact = normalize_alert_fact(alert, policy, detail=detail, resource_records=resource_records)
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
    resource_name = ""
    facts = payload.get("facts", [])
    if facts:
        resource = facts[0].get("resource", {})
        resource_name = (
            resource.get("resolved_name")
            or resource.get("entity_instance_name")
            or resource.get("resource_external_name")
            or resource.get("deployment_name")
            or ""
        )

    summary = f"Analyzed {alert_count} alert(s). Pattern: {pattern}. Risk: {risk}."
    if resource_name:
        summary = f"{summary} Resource: {resource_name}."
    print(summary)


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
