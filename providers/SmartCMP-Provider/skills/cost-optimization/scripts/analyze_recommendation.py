#!/usr/bin/env python3
"""Analyze a SmartCMP cost optimization recommendation."""

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

try:
    from _analysis import (
        BEST_PRACTICE_GUIDANCE,
        build_recommendations,
        classify_optimization_theme,
        determine_execution_readiness,
        normalize_analysis_facts,
    )
    from _cost_common import normalize_money
except ImportError:
    import os

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _analysis import (  # type: ignore
        BEST_PRACTICE_GUIDANCE,
        build_recommendations,
        classify_optimization_theme,
        determine_execution_readiness,
        normalize_analysis_facts,
    )
    from _cost_common import normalize_money  # type: ignore


def build_analysis_payload(
    violation: dict,
    policy: dict | None = None,
    saving_summary: dict | None = None,
    operation_summary: dict | None = None,
) -> dict:
    """Build the structured analysis payload."""
    normalized_violation = dict(violation)
    normalized_violation["monthlyCost"] = normalize_money(violation.get("monthlyCost"))
    normalized_violation["monthlySaving"] = normalize_money(violation.get("monthlySaving"))
    facts = normalize_analysis_facts(normalized_violation, policy)
    theme = classify_optimization_theme(
        saving_operation_type=facts.get("savingOperationType", ""),
        policy_name=facts.get("policyName", ""),
        remedie=facts.get("remedie", ""),
    )
    readiness = determine_execution_readiness(facts)
    recommendations = build_recommendations(facts)
    suggested_next_step = recommendations[0]["action"] if recommendations else "manual_review"
    return {
        "violationId": facts["violationId"],
        "facts": facts,
        "assessment": {
            "optimizationTheme": theme,
            "cloudBestPractice": BEST_PRACTICE_GUIDANCE[theme],
            "executionReadiness": readiness,
            "savingSummaryAvailable": bool(saving_summary),
            "operationSummaryAvailable": bool(operation_summary),
        },
        "recommendations": recommendations,
        "suggestedNextStep": suggested_next_step,
    }


def render_analysis(payload: dict) -> str:
    """Render human-readable text plus the structured payload block."""
    facts = payload["facts"]
    assessment = payload["assessment"]
    saving = facts.get("monthlySaving")
    saving_text = "unknown"
    if saving is not None:
        saving_text = f"{saving:.2f}"
    lines = [
        f"Violation {payload['violationId']}: {assessment['executionReadiness']}",
        f"Theme: {assessment['optimizationTheme']}",
        f"Resource: {facts.get('resourceName') or 'unknown-resource'}",
        f"Estimated monthly saving: {saving_text}",
        "",
        "##COST_ANALYSIS_START##",
        json.dumps(payload, ensure_ascii=False),
        "##COST_ANALYSIS_END##",
    ]
    return "\n".join(lines)


def safe_get_json(url: str, headers: dict, params: dict | None = None):
    """Return JSON from a GET request or None when enrichment is unavailable."""
    response = requests.get(url, headers=headers, params=params, verify=False, timeout=30)
    if response.status_code != 200:
        return None
    return response.json()

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

    saving_summary = safe_get_json(
        f"{base_url}/compliance-policies/overview/saving-summary",
        headers=headers,
    )
    operation_summary = safe_get_json(
        f"{base_url}/compliance-policies/overview/saving-operation-type-summary",
        headers=headers,
    )

    payload = build_analysis_payload(
        violation=violation,
        policy=policy,
        saving_summary=saving_summary,
        operation_summary=operation_summary,
    )
    print(render_analysis(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
