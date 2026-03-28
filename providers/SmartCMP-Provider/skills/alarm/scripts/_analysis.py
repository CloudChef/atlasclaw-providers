"""Deterministic helpers for SmartCMP alarm analysis."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _alarm_common import normalize_timestamp


def normalize_alert_fact(
    alert: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    detail: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge SmartCMP alert and policy data into a stable fact object."""
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
    reasoning.append(f"Overall operational risk is {risk}.")
    return reasoning


def build_evidence(fact: Mapping[str, Any]) -> list[str]:
    """Build compact evidence strings for downstream recommendation output."""
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
