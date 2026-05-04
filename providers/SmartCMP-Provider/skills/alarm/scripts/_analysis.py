# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Deterministic helpers for SmartCMP alarm analysis."""

from __future__ import annotations

import sys
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _alarm_common import normalize_timestamp


def normalize_alert_fact(
    alert: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    detail: Mapping[str, Any] | None = None,
    resource_records: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Merge SmartCMP alert and policy data into a stable fact object."""
    projected_resources = _project_resource_records(resource_records or [])
    resolved_resource_count = sum(1 for item in projected_resources if item.get("fetchStatus") == "ok")
    primary_resource = _select_primary_resource(projected_resources)
    observed_name = _pick_first(
        alert.get("entityInstanceName", ""),
        alert.get("resourceExternalName", ""),
        alert.get("deploymentName", ""),
    )
    observed_type = _pick_first(
        policy.get("resourceType", ""),
        alert.get("resourceType", ""),
    )
    resolved_name = _pick_first(primary_resource.get("name", ""))
    resolved_type = _pick_first(
        primary_resource.get("componentType", ""),
        primary_resource.get("resourceType", ""),
        (primary_resource.get("normalized") or {}).get("type", ""),
    )
    fact = {
        "alert_id": alert.get("id", ""),
        "alarm_activity_id": alert.get("alarmActivityId", ""),
        "alarm_activity_name": alert.get("alarmActivityName", ""),
        "status": alert.get("status", ""),
        "level": alert.get("level"),
        "trigger_count": alert.get("triggerCount", 0),
        "trigger_at": normalize_timestamp(alert.get("triggerAt")),
        "last_trigger_at": normalize_timestamp(alert.get("lastTriggerAt")),
        "last_triggered_status": alert.get("lastTriggeredStatus", ""),
        "metric_name": alert.get("metricName", ""),
        "query_expression": alert.get("queryExpression", ""),
        "rule_expression": alert.get("ruleExpression", ""),
        "resource": {
            "deployment_id": alert.get("deploymentId", ""),
            "deployment_name": alert.get("deploymentName", ""),
            "entity_instance_id": _normalize_entity_ids(alert.get("entityInstanceId")),
            "entity_instance_name": alert.get("entityInstanceName", ""),
            "node_instance_id": alert.get("nodeInstanceId", ""),
            "resource_external_id": alert.get("resourceExternalId", ""),
            "resource_external_name": alert.get("resourceExternalName", ""),
            "candidate_resource_ids": _collect_candidate_resource_ids(alert),
            "resource_context_available": resolved_resource_count > 0,
            "resolved_resource_count": resolved_resource_count,
            "resolved_resources": projected_resources,
            "resolved_resource": primary_resource,
            "observed_name": observed_name,
            "observed_type": observed_type,
            "resolved_name": resolved_name,
            "resolved_type": resolved_type,
            "display_name": _pick_first(resolved_name, observed_name),
            "display_type": _pick_first(resolved_type, observed_type),
            "resolved_status": primary_resource.get("status", ""),
        },
        "rule": {
            "policy_id": policy.get("id") or alert.get("alarmPolicyId", ""),
            "name": policy.get("name") or alert.get("alarmPolicyName", ""),
            "description": policy.get("description") or alert.get("alarmPolicyDescription", ""),
            "category": policy.get("category") or alert.get("category", ""),
            "type": policy.get("type") or alert.get("alarmType", ""),
            "metric": policy.get("metric") or alert.get("metricName", ""),
            "expression": policy.get("expression") or alert.get("ruleExpression", ""),
            "resource_type": policy.get("resourceType", ""),
        },
        "context": {
            "detail": dict(detail or {}),
        },
    }
    fact["trigger_span_minutes"] = calculate_trigger_span_minutes(fact)
    fact["alarm_health"] = build_alarm_health(fact)
    fact["rule_consistency"] = assess_rule_consistency(fact)
    return fact


def classify_alert_pattern(fact: Mapping[str, Any]) -> str:
    """Classify the alert as persistent, noisy, recovered, muted, or active."""
    status = str(fact.get("status", "") or "")
    trigger_count = int(fact.get("trigger_count") or 0)
    span_minutes = float(fact.get("trigger_span_minutes") or 0.0)

    if status == "ALERT_RESOLVED":
        return "recovered"
    if status == "ALERT_MUTED":
        return "muted"
    if trigger_count >= 6 and span_minutes and span_minutes <= 120:
        return "noisy"
    if status == "ALERT_FIRING" and trigger_count >= 3:
        return "persistent"
    if status == "ALERT_FIRING":
        return "active"
    return "unknown"


def build_assessment(fact: Mapping[str, Any]) -> dict[str, Any]:
    """Build a deterministic assessment from normalized facts."""
    pattern = classify_alert_pattern(fact)
    risk = label_risk(fact, pattern)
    reasoning = build_reasoning(fact, pattern, risk)
    return {
        "pattern": pattern,
        "risk": risk,
        "reasoning": reasoning,
        "resourceContextAvailable": bool((fact.get("resource") or {}).get("resource_context_available")),
        "impactedResourceCount": int((fact.get("resource") or {}).get("resolved_resource_count") or 0),
    }


def build_recommendations(
    fact: Mapping[str, Any],
    assessment: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Generate evidence-backed recommendations from the assessment."""
    pattern = assessment.get("pattern", "unknown")
    risk = assessment.get("risk", "low")
    evidence = build_evidence(fact)
    recommendations: list[dict[str, Any]] = []

    if pattern == "persistent":
        recommendations.append(
            make_recommendation(
                action="investigate",
                confidence="high" if risk == "high" else "medium",
                reason="Repeated firing over a sustained window suggests the condition is ongoing.",
                evidence=evidence,
            )
        )
    elif pattern == "noisy":
        recommendations.append(
            make_recommendation(
                action="mute",
                confidence="medium",
                reason="Frequent triggers in a short window suggest flapping or threshold noise.",
                evidence=evidence,
            )
        )
        recommendations.append(
            make_recommendation(
                action="investigate",
                confidence="medium",
                reason="Threshold tuning or underlying metric instability should be reviewed.",
                evidence=evidence,
            )
        )
    elif pattern == "muted":
        recommendations.append(
            make_recommendation(
                action="investigate",
                confidence="medium",
                reason="The alert is muted, but the underlying condition may still be active.",
                evidence=evidence,
            )
        )
    elif pattern == "recovered":
        recommendations.append(
            make_recommendation(
                action="observe",
                confidence="low",
                reason="The alert is already resolved. Watch for recurrence before further action.",
                evidence=evidence,
            )
        )
    else:
        recommendations.append(
            make_recommendation(
                action="observe",
                confidence="medium",
                reason="The alert is active but does not yet show a strong repeated pattern.",
                evidence=evidence,
            )
        )

    return recommendations


def suggest_status_operation(
    fact: Mapping[str, Any],
    assessment: Mapping[str, Any],
) -> dict[str, Any]:
    """Suggest whether a SmartCMP status operation is appropriate."""
    status = fact.get("status", "")
    pattern = assessment.get("pattern", "")

    if status == "ALERT_FIRING" and pattern == "noisy":
        return {
            "should_operate": True,
            "operation": "mute",
            "reason": "Short-window repeated triggers look noisy and may justify a temporary mute.",
        }
    if status == "ALERT_FIRING":
        return {
            "should_operate": False,
            "operation": "",
            "reason": "The alert is still active and should be investigated before changing status.",
        }
    return {
        "should_operate": False,
        "operation": "",
        "reason": "No status operation is recommended from the current alert state.",
    }


def calculate_trigger_span_minutes(fact: Mapping[str, Any]) -> float:
    """Calculate the elapsed minutes between first and last trigger timestamps."""
    start = parse_timestamp(fact.get("trigger_at"))
    end = parse_timestamp(fact.get("last_trigger_at"))
    if start is None or end is None:
        return 0.0
    return max((end - start).total_seconds() / 60.0, 0.0)


def build_alarm_health(fact: Mapping[str, Any], *, stale_after_days: int = 7) -> dict[str, Any]:
    """Detect stale firing alarms from SmartCMP alert timestamps."""
    status = str(fact.get("status", "") or "")
    last_trigger_at = parse_timestamp(fact.get("last_trigger_at"))
    age_days: float | None = None
    is_stale = False

    if last_trigger_at is not None:
        now = datetime.now(timezone.utc)
        age_days = round(max((now - last_trigger_at).total_seconds(), 0.0) / 86400.0, 1)
        is_stale = status == "ALERT_FIRING" and age_days > stale_after_days

    return {
        "is_stale_firing": is_stale,
        "last_trigger_age_days": age_days,
        "stale_after_days": stale_after_days,
    }


def assess_rule_consistency(fact: Mapping[str, Any]) -> dict[str, Any]:
    """Detect obvious threshold-direction mismatch between description and expression."""
    rule = fact.get("rule") or {}
    description = str(rule.get("description", "") or "").lower()
    expression = str(rule.get("expression", "") or fact.get("rule_expression", "") or "").lower()
    description_direction = infer_description_threshold_direction(description)
    expression_operator = extract_threshold_operator(expression)
    mismatch = (
        (description_direction == "greater-than" and expression_operator in {"<", "<="})
        or (description_direction == "less-than" and expression_operator in {">", ">="})
    )

    return {
        "description_direction": description_direction,
        "expression_operator": expression_operator,
        "threshold_direction_mismatch": mismatch,
    }


def infer_description_threshold_direction(description: str) -> str:
    """Infer threshold direction from English or Chinese alarm descriptions."""
    if not description:
        return ""
    if any(marker in description for marker in ("greater than", "more than", "above", "exceeds", "大于", "高于", ">")):
        return "greater-than"
    if any(marker in description for marker in ("less than", "below", "under", "小于", "低于", "<")):
        return "less-than"
    return ""


def extract_threshold_operator(expression: str) -> str:
    """Extract the first comparison operator from a PromQL-like expression."""
    match = re.search(r"(<=|>=|==|!=|<|>)\s*[-+]?\d", expression or "")
    if not match:
        return ""
    return match.group(1)


def label_risk(fact: Mapping[str, Any], pattern: str) -> str:
    """Assign a coarse risk label from alert level and current status."""
    status = fact.get("status", "")
    level = int(fact.get("level") or 0)
    trigger_count = int(fact.get("trigger_count") or 0)

    if status == "ALERT_FIRING" and level >= 3:
        return "high"
    if pattern in {"persistent", "noisy"} or (status == "ALERT_FIRING" and (level >= 2 or trigger_count >= 3)):
        return "medium"
    return "low"


def build_reasoning(fact: Mapping[str, Any], pattern: str, risk: str) -> list[str]:
    """Build short reasoning statements from the classified fact pattern."""
    trigger_count = int(fact.get("trigger_count") or 0)
    span_minutes = round(float(fact.get("trigger_span_minutes") or 0.0), 1)
    reasoning: list[str] = []
    resource = fact.get("resource") or {}

    if pattern == "persistent":
        reasoning.append("Repeated triggers over a sustained window indicate the condition is ongoing.")
    elif pattern == "noisy":
        reasoning.append("Many triggers in a short window suggest flapping or threshold noise.")
    elif pattern == "muted":
        reasoning.append("The alert is muted, which suppresses notifications but does not remove the condition.")
    elif pattern == "recovered":
        reasoning.append("The alert is already resolved.")
    else:
        reasoning.append("The alert is active, but the current data does not show a strong repeat pattern.")

    reasoning.append(f"Trigger count is {trigger_count} across about {span_minutes} minute(s).")
    resolved_name = resource.get("resolved_name", "")
    resolved_type = resource.get("resolved_type", "")
    resolved_status = resource.get("resolved_status", "")
    display_name = resource.get("display_name", "")
    display_type = resource.get("display_type", "")
    if resource.get("resource_context_available") and (resolved_name or resolved_type or resolved_status):
        parts = [part for part in (resolved_name, resolved_type, resolved_status) if part]
        reasoning.append(f"Datasource resource context: {' | '.join(parts)}.")
    elif display_name or display_type:
        parts = [part for part in (display_name, display_type) if part]
        reasoning.append(
            f"Alert payload references resource: {' | '.join(parts)}. "
            "Datasource enrichment did not return a matching node record."
        )
    elif resource.get("candidate_resource_ids"):
        reasoning.append("Resource identifiers are present, but datasource enrichment did not return normalized details.")
    alarm_health = fact.get("alarm_health") or {}
    if alarm_health.get("is_stale_firing"):
        reasoning.append(
            "Alert is still marked ALERT_FIRING, but the last trigger timestamp is old; "
            "verify current alarm state before mute or resolve operations."
        )
    rule_consistency = fact.get("rule_consistency") or {}
    if rule_consistency.get("threshold_direction_mismatch"):
        reasoning.append(
            "Alarm policy description and PromQL threshold direction appear inconsistent; "
            "review the policy expression before treating the alert as a true threshold breach."
        )
    reasoning.append(f"Overall operational risk is {risk}.")
    return reasoning


def build_evidence(fact: Mapping[str, Any]) -> list[str]:
    """Build compact evidence strings for downstream recommendation output."""
    resource = fact.get("resource") or {}
    evidence = [
        f"status={fact.get('status', '')}",
        f"level={fact.get('level', '')}",
        f"trigger_count={fact.get('trigger_count', 0)}",
    ]
    last_trigger_at = fact.get("last_trigger_at", "")
    if last_trigger_at:
        evidence.append(f"last_trigger_at={last_trigger_at}")
    policy_name = (fact.get("rule") or {}).get("name", "")
    if policy_name:
        evidence.append(f"rule={policy_name}")
    display_type = resource.get("display_type", "")
    if display_type:
        evidence.append(f"resource_type={display_type}")
    resolved_status = resource.get("resolved_status", "")
    if resolved_status:
        evidence.append(f"resource_status={resolved_status}")
    alarm_health = fact.get("alarm_health") or {}
    if alarm_health.get("is_stale_firing"):
        evidence.append(f"last_trigger_age_days={alarm_health.get('last_trigger_age_days')}")
    rule_consistency = fact.get("rule_consistency") or {}
    if rule_consistency.get("threshold_direction_mismatch"):
        evidence.append("rule_threshold_direction_mismatch=true")
    return evidence


def make_recommendation(
    *,
    action: str,
    confidence: str,
    reason: str,
    evidence: list[str],
) -> dict[str, Any]:
    """Create a stable recommendation record."""
    return {
        "action": action,
        "confidence": confidence,
        "reason": reason,
        "evidence": evidence,
    }


def parse_timestamp(value: Any) -> datetime | None:
    """Parse a normalized timestamp string into a UTC datetime."""
    normalized = normalize_timestamp(value)
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_entity_ids(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def _collect_candidate_resource_ids(alert: Mapping[str, Any]) -> list[str]:
    resource_ids = _normalize_entity_ids(alert.get("entityInstanceId"))
    node_instance_id = alert.get("nodeInstanceId")
    if node_instance_id not in (None, ""):
        resource_ids.append(str(node_instance_id))

    deduped: list[str] = []
    for resource_id in resource_ids:
        if not resource_id or resource_id in deduped:
            continue
        deduped.append(resource_id)
    return deduped


def _pick_first(*values: Any) -> str:
    for value in values:
        if value not in (None, ""):
            return str(value)
    return ""


def _project_resource_records(resource_records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    for record in resource_records:
        if not isinstance(record, Mapping):
            continue
        summary = record.get("summary") or {}
        data = record.get("data") or record.get("resource") or {}
        normalized = record.get("normalized") or {}
        projected.append(
            {
                "resourceId": record.get("resourceId", ""),
                "sourceEndpoint": record.get("sourceEndpoint", ""),
                "name": _pick_first(
                    summary.get("name", ""),
                    data.get("name", ""),
                ),
                "resourceType": _pick_first(summary.get("resourceType", ""), data.get("resourceType", "")),
                "componentType": _pick_first(summary.get("componentType", ""), data.get("componentType", "")),
                "status": _pick_first(summary.get("status", ""), data.get("status", "")),
                "osType": _pick_first(summary.get("osType", ""), data.get("osType", "")),
                "osDescription": _pick_first(summary.get("osDescription", ""), data.get("osDescription", "")),
                "fetchStatus": record.get("fetchStatus", ""),
                "missingEvidence": list(record.get("missingEvidence") or []),
                "errors": list(record.get("errors") or []),
                "normalized": {
                    "type": normalized.get("type", ""),
                    "properties": dict(normalized.get("properties") or {}),
                },
            }
        )
    return projected


def _select_primary_resource(resource_records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    for record in resource_records:
        if record.get("fetchStatus") == "ok":
            return dict(record)
    return {}
