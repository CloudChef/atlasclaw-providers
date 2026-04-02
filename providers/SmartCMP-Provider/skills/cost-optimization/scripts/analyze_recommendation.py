#!/usr/bin/env python3
"""Analyze a SmartCMP cost optimization recommendation."""

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

try:
    from _analysis import (
        BEST_PRACTICE_GUIDANCE,
        BEST_PRACTICE_GUIDANCE_ZH,
        build_recommendations,
        classify_optimization_theme,
        classify_violation_type,
        determine_execution_readiness,
        normalize_analysis_facts,
    )
    from _cost_common import normalize_money, get_currency_symbol
except ImportError:
    import os

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _analysis import (  # type: ignore
        BEST_PRACTICE_GUIDANCE,
        BEST_PRACTICE_GUIDANCE_ZH,
        build_recommendations,
        classify_optimization_theme,
        classify_violation_type,
        determine_execution_readiness,
        normalize_analysis_facts,
    )
    from _cost_common import normalize_money, get_currency_symbol  # type: ignore


def build_analysis_payload(
    violation: dict,
    policy: dict | None = None,
    saving_summary: dict | None = None,
    operation_summary: dict | None = None,
    saving_trend: dict | None = None,
    resource_top: list | None = None,
    policy_executions: list | None = None,
    related_policy_count: int = 0,
    base_url: str = "",
    auth_token: str = "",
) -> dict:
    """Build the structured analysis payload with enriched context."""
    normalized_violation = dict(violation)
    normalized_violation["monthlyCost"] = normalize_money(violation.get("monthlyCost"))
    normalized_violation["monthlySaving"] = normalize_money(violation.get("monthlySaving"))
    facts = normalize_analysis_facts(normalized_violation, policy)
    theme = classify_optimization_theme(
        saving_operation_type=facts.get("savingOperationType", ""),
        policy_name=facts.get("policyName", ""),
        remedie=facts.get("remedie", ""),
    )
    violation_type = classify_violation_type(facts.get("savingOperationType", ""))
    readiness = determine_execution_readiness(facts)
    task_definition_present = bool(facts.get("taskDefinitionName"))

    # Build context for multi-dimensional recommendations
    context = {
        "saving_summary": saving_summary,
        "operation_summary": operation_summary,
        "saving_trend": saving_trend,
        "resource_top": resource_top,
        "policy_executions": policy_executions,
        "currency": get_currency_symbol(base_url, auth_token),
    }
    recommendations = build_recommendations(facts, context)
    suggested_next_step = recommendations[0]["action"] if recommendations else "manual_review"

    # Calculate saving contribution percentage
    saving_contribution_pct = None
    if saving_summary and facts.get("monthlySaving"):
        optimizable = saving_summary.get("optimizableAmount") or saving_summary.get("currentMonthOptimizable") or 0
        if optimizable and optimizable > 0:
            saving_contribution_pct = round((facts["monthlySaving"] / optimizable) * 100, 2)

    # Check if resource is in Top10
    is_top_saving_resource = False
    if resource_top and facts.get("resourceId"):
        for item in resource_top:
            if item.get("resourceId") == facts.get("resourceId"):
                is_top_saving_resource = True
                break

    # Get policy compliance rate from executions
    policy_compliance_rate = None
    if policy_executions:
        latest = policy_executions[0] if policy_executions else {}
        policy_compliance_rate = latest.get("complianceRate") or latest.get("compliance")

    # Determine risk level
    operation_type = (facts.get("savingOperationType") or "").upper()
    if operation_type == "TEAR_DOWN_IN_RESOURCE":
        risk_level = "high"
    elif operation_type == "RESIZE":
        risk_level = "medium"
    elif operation_type in ("CHANGE_PAY_TYPE", "SWITCH_TO_SUBSCRIPTION"):
        risk_level = "low"
    else:
        risk_level = "medium"

    return {
        "violationId": facts["violationId"],
        "facts": facts,
        "assessment": {
            "optimizationTheme": theme,
            "violationType": violation_type,
            "cloudBestPractice": BEST_PRACTICE_GUIDANCE.get(theme, BEST_PRACTICE_GUIDANCE["manual_review"]),
            "cloudBestPracticeZh": BEST_PRACTICE_GUIDANCE_ZH.get(theme, BEST_PRACTICE_GUIDANCE_ZH["manual_review"]),
            "executionReadiness": readiness,
            "taskDefinitionPresent": task_definition_present,
            "savingSummaryAvailable": bool(saving_summary),
            "operationSummaryAvailable": bool(operation_summary),
            "savingContributionPct": saving_contribution_pct,
            "isTopSavingResource": is_top_saving_resource,
            "riskLevel": risk_level,
            "policyComplianceRate": policy_compliance_rate,
            "violationRecurrence": facts.get("times", 0),
            "relatedPolicyCount": related_policy_count,
        },
        "recommendations": recommendations,
        "suggestedNextStep": suggested_next_step,
    }


def render_analysis(payload: dict, base_url: str = "", auth_token: str = "") -> str:
    """Render human-readable text in English plus the structured payload block."""
    facts = payload["facts"]
    assessment = payload["assessment"]
    recommendations = payload.get("recommendations", [])

    saving = facts.get("monthlySaving")
    saving_text = "unknown"
    if saving is not None:
        saving_text = f"{get_currency_symbol(base_url, auth_token)}{saving:.2f}"

    # Contribution percentage
    contribution = assessment.get("savingContributionPct")
    contribution_text = ""
    if contribution is not None:
        contribution_text = f" ({contribution}% of total optimizable)"

    # Risk level
    risk_level = assessment.get("riskLevel", "medium")
    risk_text = {"high": "High", "medium": "Medium", "low": "Low"}.get(risk_level, "Medium")

    # Policy compliance rate
    compliance_rate = assessment.get("policyComplianceRate")
    compliance_text = "Unknown"
    if compliance_rate is not None:
        compliance_text = f"{compliance_rate}%"

    # Violation recurrence
    recurrence = assessment.get("violationRecurrence", 0)
    recurrence_text = "First occurrence" if recurrence <= 1 else f"Triggered {recurrence} times"

    lines = [
        f"Violation {payload['violationId']}: {assessment['executionReadiness']}",
        f"Theme: {assessment['optimizationTheme']} ({assessment.get('violationType', 'UNKNOWN')})",
        f"Resource: {facts.get('resourceName') or 'unknown-resource'}",
        f"Estimated monthly saving: {saving_text}{contribution_text}",
        f"Policy compliance: {compliance_text} | Occurrences: {recurrence_text}",
        f"Risk level: {risk_text}",
        "",
    ]

    # Render recommendations by priority
    for rec in recommendations:
        priority = rec.get("priority", "P2")
        rec_type = rec.get("type", "unknown")
        reason = rec.get("reason", "")
        reason_en = rec.get("reasonEn", reason)
        risk = rec.get("risk", "none")
        risk_notes = rec.get("riskNotes", [])

        if rec_type == "primary_action":
            lines.append(f"[{priority}] Primary Action: {rec.get('action')} - {reason_en}")
        elif rec_type == "risk_assessment":
            notes_text = "; ".join(risk_notes[:2]) if risk_notes else ""
            lines.append(f"[{priority}] Risk Assessment: Level {risk} - {notes_text}")
        elif rec_type == "configuration_guide":
            lines.append(f"[{priority}] Configuration Guide: {reason_en}")
        elif rec_type == "saving_priority":
            lines.append(f"[{priority}] Saving Priority: {reason_en}")
        elif rec_type == "policy_history":
            lines.append(f"[{priority}] Policy History: {reason_en}")

    # Best practice
    best_practice = assessment.get("cloudBestPractice") or recommendations[0].get("bestPractice", "") if recommendations else ""
    if best_practice:
        lines.extend(["", "Best Practice:", f"  {best_practice}"])

    lines.extend([
        "",
        "##COST_ANALYSIS_START##",
        json.dumps(payload, ensure_ascii=False),
        "##COST_ANALYSIS_END##",
    ])
    return "\n".join(lines)


def safe_get_json(url: str, headers: dict, params: dict | None = None):
    """Return JSON from a GET request or None when enrichment is unavailable."""
    try:
        response = requests.get(url, headers=headers, params=params, verify=False, timeout=30)
    except RequestException:
        return None

    if response.status_code != 200:
        return None

    try:
        return response.json()
    except (ValueError, json.JSONDecodeError):
        return None


def extract_list_payload(payload) -> list:
    """Extract list payloads from common SmartCMP response wrappers."""
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    for key in ("content", "items", "result"):
        value = payload.get(key)
        if isinstance(value, list):
            return value

    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("content", "items", "result"):
            value = data.get(key)
            if isinstance(value, list):
                return value

    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze one SmartCMP cost optimization recommendation.")
    parser.add_argument("--id", required=True, help="Violation identifier.")
    args = parser.parse_args()

    base_url, auth_token, _, _ = require_config()
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "CloudChef-Authenticate": auth_token,
    }

    violation_response = requests.get(
        f"{base_url}/compliance-policies/violations/{args.id}",
        headers=headers,
        verify=False,
        timeout=30,
    )
    if violation_response.status_code != 200:
        print(f"[ERROR] HTTP {violation_response.status_code}: {violation_response.text}")
        return 1

    violation = violation_response.json()
    policy = None
    policy_id = violation.get("policyId")
    if policy_id:
        policy = safe_get_json(f"{base_url}/compliance-policies/{policy_id}", headers=headers)

    # Existing API calls
    saving_summary = safe_get_json(
        f"{base_url}/compliance-policies/overview/saving-summary",
        headers=headers,
    )
    operation_summary = safe_get_json(
        f"{base_url}/compliance-policies/overview/saving-operation-type-summary",
        headers=headers,
    )

    # New API calls for enriched context
    saving_trend = safe_get_json(
        f"{base_url}/compliance-policies/overview/saving-trend",
        headers=headers,
    )
    resource_top = safe_get_json(
        f"{base_url}/compliance-policies/overview/saving-resource-top",
        headers=headers,
    )

    # Policy execution history (recent 5)
    policy_executions = None
    if policy_id:
        exec_response = safe_get_json(
            f"{base_url}/compliance-policies/policy-executions/search",
            headers=headers,
            params={"policyId": policy_id, "page": 0, "size": 5},
        )
        if exec_response:
            policy_executions = extract_list_payload(exec_response)

    # Related policies count (same category)
    related_policy_count = 0
    category = violation.get("category")
    if category:
        policies_response = safe_get_json(
            f"{base_url}/compliance-policies/search",
            headers=headers,
            params={"category": category, "page": 0, "size": 100},
        )
        if policies_response:
            all_policies = extract_list_payload(policies_response)
            # Exclude current policy from count
            related_policy_count = max(0, len(all_policies) - 1)

    payload = build_analysis_payload(
        violation=violation,
        policy=policy,
        saving_summary=saving_summary,
        operation_summary=operation_summary,
        saving_trend=saving_trend,
        resource_top=resource_top,
        policy_executions=policy_executions,
        related_policy_count=related_policy_count,
        base_url=base_url,
        auth_token=auth_token,
    )
    print(render_analysis(payload, base_url=base_url, auth_token=auth_token))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
