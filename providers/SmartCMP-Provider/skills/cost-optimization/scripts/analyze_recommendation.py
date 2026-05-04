#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Analyze a SmartCMP cost optimization recommendation."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys

import requests
from requests import RequestException

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_SCRIPT_DIR = os.path.join(SCRIPT_DIR, "..", "..", "shared", "scripts")
DATASOURCE_SCRIPT_DIR = os.path.join(SCRIPT_DIR, "..", "..", "datasource", "scripts")


def _load_module_from_path(module_name: str, file_path: str):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to load module from path: {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

try:
    from _common import require_config
except ImportError:
    sys.path.insert(
        0,
        SHARED_SCRIPT_DIR,
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
    sys.path.insert(0, SCRIPT_DIR)
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


resource_module = _load_module_from_path(
    "cost_optimization_shared_list_resource_local",
    os.path.join(DATASOURCE_SCRIPT_DIR, "list_resource.py"),
)
collect_resource_ids_from_summaries = resource_module.collect_resource_ids_from_summaries
load_resource_records = resource_module.load_resource_records
shared_request_json = resource_module.request_json
search_resource_summaries = resource_module.search_resource_summaries


def _pick_first(*values) -> str:
    for value in values:
        if value not in (None, ""):
            return str(value)
    return ""


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if not value or value in deduped:
            continue
        deduped.append(value)
    return deduped


def _has_resolved_resource(resource_records: list[dict]) -> bool:
    return any(record.get("fetchStatus") == "ok" for record in resource_records)


def _load_resource_records_by_ids(
    resource_ids: list[str],
    *,
    base_url: str,
    headers: dict,
) -> list[dict]:
    if not resource_ids:
        return []

    try:
        records = load_resource_records(
            resource_ids,
            base_url=base_url,
            headers=headers,
            request_fn=shared_request_json,
        )
    except (RuntimeError, RequestException):
        return []

    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, dict)]


def _safe_load_resource_records(violation: dict, *, base_url: str, headers: dict) -> list[dict]:
    candidate_ids = _dedupe_strings([
        str(violation.get("resourceId") or "").strip(),
    ])
    records = _load_resource_records_by_ids(candidate_ids, base_url=base_url, headers=headers)
    if _has_resolved_resource(records):
        return records

    fallback_lookup_ids: list[str] = []

    node_instance_id = _pick_first(
        violation.get("nodeInstanceId"),
        violation.get("resourceNodeInstanceId"),
    ).strip()
    if node_instance_id:
        try:
            fallback_lookup_ids.extend(
                collect_resource_ids_from_summaries(
                    search_resource_summaries(
                        base_url=base_url,
                        headers=headers,
                        request_fn=shared_request_json,
                        params={"nodeInstanceId": node_instance_id},
                    )
                )
            )
        except Exception:
            pass

    resource_external_id = _pick_first(
        violation.get("resourceExternalId"),
        violation.get("externalId"),
    ).strip()
    if not fallback_lookup_ids and resource_external_id:
        try:
            fallback_lookup_ids.extend(
                collect_resource_ids_from_summaries(
                    search_resource_summaries(
                        base_url=base_url,
                        headers=headers,
                        request_fn=shared_request_json,
                        params={"externalIds": resource_external_id},
                    )
                )
            )
        except Exception:
            pass

    resource_name = _pick_first(
        violation.get("resourceExternalName"),
        violation.get("resourceName"),
    ).strip()
    if not fallback_lookup_ids and resource_name:
        try:
            fallback_lookup_ids.extend(
                collect_resource_ids_from_summaries(
                    search_resource_summaries(
                        base_url=base_url,
                        headers=headers,
                        request_fn=shared_request_json,
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
        resource_id
        for resource_id in _dedupe_strings(fallback_lookup_ids)
        if resource_id not in candidate_ids
    ]
    if not fallback_lookup_ids:
        return records

    fallback_records = _load_resource_records_by_ids(
        fallback_lookup_ids,
        base_url=base_url,
        headers=headers,
    )
    return records + fallback_records


def _project_resource_records(resource_records: list | None) -> list[dict]:
    projected: list[dict] = []
    for record in resource_records or []:
        if not isinstance(record, dict):
            continue
        summary = record.get("summary") or {}
        resource = record.get("data") or record.get("resource") or {}
        normalized = record.get("normalized") or {}
        projected.append(
            {
                "resourceId": record.get("resourceId", ""),
                "sourceEndpoint": record.get("sourceEndpoint", ""),
                "name": _pick_first(summary.get("name"), resource.get("name")),
                "resourceType": _pick_first(summary.get("resourceType"), resource.get("resourceType")),
                "componentType": _pick_first(summary.get("componentType"), resource.get("componentType")),
                "status": _pick_first(summary.get("status"), resource.get("status")),
                "osType": _pick_first(summary.get("osType"), resource.get("osType")),
                "osDescription": _pick_first(summary.get("osDescription"), resource.get("osDescription")),
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


def _select_primary_resource(resource_records: list[dict]) -> dict:
    for record in resource_records:
        if record.get("fetchStatus") == "ok":
            return dict(record)
    return dict(resource_records[0]) if resource_records else {}


def _build_resource_context(resource_id: str, resource_records: list | None) -> dict:
    projected_records = _project_resource_records(resource_records)
    requested_resource_ids: list[str] = []
    if resource_id:
        requested_resource_ids.append(resource_id)
    for item in projected_records:
        projected_resource_id = str(item.get("resourceId", "") or "").strip()
        if projected_resource_id and projected_resource_id not in requested_resource_ids:
            requested_resource_ids.append(projected_resource_id)
    return {
        "requestedResourceIds": requested_resource_ids,
        "resolvedCount": sum(1 for item in projected_records if item.get("fetchStatus") == "ok"),
        "resources": projected_records,
    }


def _enrich_violation_with_resource_context(violation: dict, resource_records: list | None) -> dict:
    enriched_violation = dict(violation)
    resource_id = str(enriched_violation.get("resourceId", "") or "")
    resource_context = _build_resource_context(resource_id, resource_records)
    primary_resource = _select_primary_resource(resource_context["resources"])

    enriched_violation["resourceContext"] = resource_context
    enriched_violation["resourceContextAvailable"] = resource_context["resolvedCount"] > 0
    enriched_violation["resourceFetchStatus"] = primary_resource.get("fetchStatus", "")

    if primary_resource.get("fetchStatus") == "ok":
        enriched_violation["resourceId"] = _pick_first(
            primary_resource.get("resourceId"),
            enriched_violation.get("resourceId"),
        )
        enriched_violation["resourceName"] = _pick_first(
            enriched_violation.get("resourceName"),
            primary_resource.get("name"),
        )
        enriched_violation["resourceType"] = _pick_first(
            primary_resource.get("resourceType"),
            (primary_resource.get("normalized") or {}).get("type"),
        )
        enriched_violation["componentType"] = primary_resource.get("componentType", "")
        enriched_violation["resourceStatus"] = primary_resource.get("status", "")
        enriched_violation["osType"] = primary_resource.get("osType", "")
        enriched_violation["osDescription"] = primary_resource.get("osDescription", "")

    return enriched_violation


def build_analysis_payload(
    violation: dict,
    policy: dict | None = None,
    saving_summary: dict | None = None,
    operation_summary: dict | None = None,
    saving_trend: dict | None = None,
    resource_top: list | None = None,
    policy_executions: list | None = None,
    resource_records: list | None = None,
    related_policy_count: int = 0,
    base_url: str = "",
    auth_token: str = "",
) -> dict:
    """Build the structured analysis payload with enriched context."""
    normalized_violation = _enrich_violation_with_resource_context(violation, resource_records)
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
            "resourceContextAvailable": bool(facts.get("resourceContextAvailable")),
            "resourceFetchStatus": facts.get("resourceFetchStatus", ""),
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

    resource_line = "Resource: " + " | ".join(
        part
        for part in (
            facts.get("resourceName") or "unknown-resource",
            f"type={facts.get('componentType') or facts.get('resourceType')}"
            if (facts.get("componentType") or facts.get("resourceType"))
            else "",
            f"status={facts.get('resourceStatus')}" if facts.get("resourceStatus") else "",
        )
        if part
    )

    lines = [
        f"Violation {payload['violationId']}: {assessment['executionReadiness']}",
        f"Theme: {assessment['optimizationTheme']} ({assessment.get('violationType', 'UNKNOWN')})",
        resource_line,
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

    base_url, auth_token, headers, _ = require_config()

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

    resource_records = _safe_load_resource_records(
        violation,
        base_url=base_url,
        headers=headers,
    )

    payload = build_analysis_payload(
        violation=violation,
        policy=policy,
        saving_summary=saving_summary,
        operation_summary=operation_summary,
        saving_trend=saving_trend,
        resource_top=resource_top,
        policy_executions=policy_executions,
        resource_records=resource_records,
        related_policy_count=related_policy_count,
        base_url=base_url,
        auth_token=auth_token,
    )
    print(render_analysis(payload, base_url=base_url, auth_token=auth_token))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
