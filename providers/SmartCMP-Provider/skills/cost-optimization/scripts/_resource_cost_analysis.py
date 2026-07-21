#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Pure helpers for resource-first SmartCMP cost optimization analysis."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from _cost_common import normalize_money, normalize_timestamp


RULE_CONTENT_LIMIT = 8_000
POLICY_TEXT_LIMIT = 4_000
SCOPE_VALUE_LIMIT = 200
EXECUTION_EVIDENCE_MAX_DEPTH = 4
EXECUTION_EVIDENCE_MAX_ITEMS = 40
EXECUTION_EVIDENCE_MAX_STRING = 1_000
EXECUTION_EVIDENCE_MAX_SERIALIZED = 8_000
KNOWN_SCOPE_KEYS = {"cloudEntryTypes", "resourceIds"}
FAILURE_STATUSES = {"ERROR", "FAILED", "FAILURE"}
NONCOMPLIANT_STATUSES = {"NONCOMPLIANCE", "NON_COMPLIANCE", "VIOLATION"}

_SENSITIVE_KEY_FRAGMENTS = (
    "apikey",
    "authentication",
    "accesstoken",
    "accesskey",
    "authorization",
    "bearer",
    "clientsecret",
    "cookie",
    "credential",
    "passphrase",
    "password",
    "privatekey",
    "secret",
    "secretaccesskey",
    "secrettoken",
    "token",
)

_COST_ATTRIBUTE_KEYS = (
    "payType",
    "currentBilling",
    "historyTotalBilling",
    "cpu",
    "memory",
    "storage",
    "flavor",
    "instanceType",
    "instance_type",
    "size",
    "storageType",
    "storage_type",
    "engine",
    "engineVersion",
    "engine_version",
    "multiZone",
    "multi_zone",
    "isReadReplica",
    "is_read_replica",
    "backupRetention",
    "backup_retention",
    "publiclyAccessible",
    "publicly_accessible",
    "usage",
    "lastStartedDate",
)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _first_value(sources: list[Mapping[str, Any]], key: str) -> Any:
    for source in sources:
        value = source.get(key)
        if value not in (None, ""):
            return value
    return None


def _primitive(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _resource_sources(record: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[Mapping[str, Any]]]:
    resource = _mapping(record.get("data") or record.get("resource"))
    normalized = _mapping(record.get("normalized"))
    properties = _mapping(normalized.get("properties"))
    exts = _mapping(resource.get("exts"))
    custom_property = _mapping(exts.get("customProperty") or resource.get("customProperty"))
    resource_info = _mapping(resource.get("resourceInfo"))
    return resource, custom_property, [resource, properties, resource_info, custom_property]


def build_resource_projection(record: Mapping[str, Any]) -> dict[str, Any]:
    """Project one datasource record into a bounded cost-analysis evidence object.

    Args:
        record: Datasource resource record containing raw and normalized SmartCMP data.

    Returns:
        A JSON-compatible resource projection containing only cost-relevant fields.
    """
    resource, custom_property, sources = _resource_sources(record)
    normalized = _mapping(record.get("normalized"))
    summary = _mapping(record.get("summary"))
    component_type = str(
        normalized.get("type")
        or resource.get("componentType")
        or summary.get("componentType")
        or resource.get("resourceType")
        or summary.get("resourceType")
        or ""
    ).strip()
    resource_type = str(
        resource.get("resourceType") or summary.get("resourceType") or component_type
    ).strip()

    cloud_entry_type = resource.get("cloudEntryType")
    if isinstance(cloud_entry_type, Mapping):
        cloud_entry_type = cloud_entry_type.get("id") or cloud_entry_type.get("name")
    cloud_entry_type = (
        cloud_entry_type
        or custom_property.get("cloud_entry_type")
        or _first_value(sources, "cloudEntryTypeId")
        or ""
    )

    cost_attributes: dict[str, Any] = {}
    for key in _COST_ATTRIBUTE_KEYS:
        value = _first_value(sources, key)
        if value not in (None, "") and _primitive(value):
            cost_attributes[key] = value

    metric_health = resource.get("metricHealth")
    if metric_health in (None, ""):
        metric_health = _mapping(normalized.get("properties")).get("metricHealth")

    cmp_status = str(resource.get("status") or summary.get("status") or "").strip()
    provider_status = str(custom_property.get("status") or "").strip()
    return {
        "name": str(resource.get("name") or summary.get("name") or "unknown resource").strip(),
        "resourceType": resource_type,
        "componentType": component_type,
        "status": cmp_status,
        "providerStatus": provider_status,
        "regionId": str(_first_value(sources, "regionId") or "").strip(),
        "zoneId": str(_first_value(sources, "zoneId") or "").strip(),
        "cloudEntryType": str(cloud_entry_type or "").strip(),
        "monitorEnabled": _first_value(sources, "monitorEnabled"),
        "monitorSourceType": str(_first_value(sources, "monitorSourceType") or "").strip(),
        "monitorResourceType": str(_first_value(sources, "monitorResourceType") or "").strip(),
        "monitoringEvidenceAvailable": bool(metric_health),
        "createdDate": normalize_timestamp(resource.get("createdDate")),
        "updatedDate": normalize_timestamp(resource.get("updatedDate")),
        "costAttributes": cost_attributes,
    }


def match_resource_type(resource_types: list[str], policy_types: list[str]) -> str:
    """Match policy resource types against concrete resource types.

    Args:
        resource_types: Concrete component and resource types for the selected resource.
        policy_types: Resource types declared by a SmartCMP policy.

    Returns:
        ``exact``, ``ancestor``, or an empty string when no type is compatible.
    """
    normalized_resources = [str(value or "").strip() for value in resource_types if value]
    normalized_policies = [str(value or "").strip() for value in policy_types if value]
    if any(
        resource_type == policy_type
        for resource_type in normalized_resources
        for policy_type in normalized_policies
    ):
        return "exact"
    if any(
        resource_type.startswith(f"{policy_type}.")
        for resource_type in normalized_resources
        for policy_type in normalized_policies
    ):
        return "ancestor"
    return ""


def match_policy_scope(
    scope: Mapping[str, Any] | None,
    *,
    resource_id: str,
    cloud_entry_type: str,
) -> tuple[str, list[str]]:
    """Evaluate supported SmartCMP policy scope fields conservatively.

    Args:
        scope: Policy configuration scope.
        resource_id: Internal resource ID used only for exact scope matching.
        cloud_entry_type: Resource cloud-entry type identifier.

    Returns:
        Scope status (``matched``, ``excluded``, or ``scope_unknown``) and reasons.
    """
    normalized_scope = _mapping(scope)
    reasons: list[str] = []
    unknown_keys = [
        key
        for key, value in normalized_scope.items()
        if key not in KNOWN_SCOPE_KEYS and value not in (None, "", [], {})
    ]

    resource_ids = [str(value) for value in normalized_scope.get("resourceIds") or [] if value not in (None, "")]
    if resource_ids and resource_id not in resource_ids:
        return "excluded", ["resource is outside scope.resourceIds"]
    if resource_ids:
        reasons.append("resource matched scope.resourceIds")

    cloud_entry_types = [
        str(value) for value in normalized_scope.get("cloudEntryTypes") or [] if value not in (None, "")
    ]
    if cloud_entry_types and "-1" not in cloud_entry_types:
        if not cloud_entry_type:
            return "scope_unknown", ["resource cloud entry type is unavailable"]
        if cloud_entry_type not in cloud_entry_types:
            return "excluded", ["resource is outside scope.cloudEntryTypes"]
        reasons.append("resource matched scope.cloudEntryTypes")
    elif "-1" in cloud_entry_types:
        reasons.append("scope includes all cloud entry types")

    if unknown_keys:
        return "scope_unknown", [f"unsupported scope fields: {', '.join(sorted(unknown_keys))}"]
    return "matched", reasons or ["policy scope has no resource restriction"]


def _bounded_rule_content(value: Any) -> tuple[str, bool]:
    rendered = str(value or "")
    if len(rendered) <= RULE_CONTENT_LIMIT:
        return rendered, False
    return rendered[:RULE_CONTENT_LIMIT], True


def _bounded_policy_text(value: Any) -> tuple[str, bool]:
    rendered = str(value or "")
    if len(rendered) <= POLICY_TEXT_LIMIT:
        return rendered, False
    return rendered[:POLICY_TEXT_LIMIT], True


def _project_scope(scope: Mapping[str, Any]) -> tuple[dict[str, list[str]], bool]:
    projected: dict[str, list[str]] = {}
    truncated = False
    for key in sorted(KNOWN_SCOPE_KEYS):
        raw_values = scope.get(key)
        if not isinstance(raw_values, (list, tuple, set)):
            continue
        values = [str(value) for value in raw_values if value not in (None, "")]
        if len(values) > SCOPE_VALUE_LIMIT:
            truncated = True
        projected[key] = values[:SCOPE_VALUE_LIMIT]
    return projected, truncated


def _normalized_key(value: Any) -> str:
    return "".join(character for character in str(value or "").casefold() if character.isalnum())


def _is_sensitive_key(value: Any) -> bool:
    normalized = _normalized_key(value)
    return any(fragment in normalized for fragment in _SENSITIVE_KEY_FRAGMENTS)


def _sanitize_execution_value(
    value: Any,
    *,
    depth: int,
    state: dict[str, bool],
) -> Any:
    if depth >= EXECUTION_EVIDENCE_MAX_DEPTH:
        state["truncated"] = True
        return "[depth-truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) > EXECUTION_EVIDENCE_MAX_STRING:
            state["truncated"] = True
        return value[:EXECUTION_EVIDENCE_MAX_STRING]
    if isinstance(value, Mapping):
        projected: dict[str, Any] = {}
        items = list(value.items())
        if len(items) > EXECUTION_EVIDENCE_MAX_ITEMS:
            state["truncated"] = True
        for key, nested_value in items[:EXECUTION_EVIDENCE_MAX_ITEMS]:
            if _is_sensitive_key(key):
                state["redacted"] = True
                continue
            projected[str(key)[:200]] = _sanitize_execution_value(
                nested_value,
                depth=depth + 1,
                state=state,
            )
        return projected
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        if len(items) > EXECUTION_EVIDENCE_MAX_ITEMS:
            state["truncated"] = True
        return [
            _sanitize_execution_value(item, depth=depth + 1, state=state)
            for item in items[:EXECUTION_EVIDENCE_MAX_ITEMS]
        ]
    rendered = str(value)
    if len(rendered) > EXECUTION_EVIDENCE_MAX_STRING:
        state["truncated"] = True
    return rendered[:EXECUTION_EVIDENCE_MAX_STRING]


def project_execution_extra(extra: Any) -> dict[str, Any]:
    """Project resource-execution evidence with strict size and secret limits.

    Args:
        extra: Raw SmartCMP resource-execution ``extra`` value.

    Returns:
        Completeness flags and bounded evidence fields. Oversized evidence details
        are omitted rather than allowing an unbounded LLM context.
    """
    if not isinstance(extra, Mapping):
        return {}

    projected: dict[str, Any] = {}
    for key in ("evidenceComplete", "evaluationEvidenceComplete"):
        if isinstance(extra.get(key), bool):
            projected[key] = extra[key]

    state = {"redacted": False, "truncated": False}
    for key in ("evidence", "metrics", "observations"):
        if key in extra:
            projected[key] = _sanitize_execution_value(
                extra[key],
                depth=0,
                state=state,
            )

    if state["redacted"]:
        projected["redactionApplied"] = True
    if state["truncated"]:
        projected["evidenceTruncated"] = True
    if len(json.dumps(projected, ensure_ascii=False, default=str)) > EXECUTION_EVIDENCE_MAX_SERIALIZED:
        return {
            key: value
            for key, value in projected.items()
            if key in {"evidenceComplete", "evaluationEvidenceComplete", "redactionApplied"}
        } | {"evidenceTruncated": True}
    return projected


def build_policy_coverages(
    policies: list[Mapping[str, Any]],
    *,
    resource: Mapping[str, Any],
    resource_id: str,
) -> list[dict[str, Any]]:
    """Build enabled, type-compatible policy configuration evidence.

    Args:
        policies: SmartCMP cost optimization policy records.
        resource: Projected selected resource.
        resource_id: Internal resource ID for policy scope matching.

    Returns:
        Coverage records for enabled configurations whose policy type matches the resource.
    """
    resource_types = [
        str(resource.get("componentType") or ""),
        str(resource.get("resourceType") or ""),
    ]
    coverages: list[dict[str, Any]] = []
    for policy in policies:
        policy_types = [str(value) for value in policy.get("resourceType") or []]
        type_match = match_resource_type(resource_types, policy_types)
        if not type_match:
            continue
        description, description_truncated = _bounded_policy_text(policy.get("description"))
        remedie, remedie_truncated = _bounded_policy_text(policy.get("remedie"))
        rule_content, rule_truncated = _bounded_rule_content(policy.get("ruleContent"))
        for config in policy.get("policyConfigs") or []:
            if not isinstance(config, Mapping) or config.get("enabled") is not True:
                continue
            config_scope = _mapping(config.get("scope"))
            scope_status, scope_reasons = match_policy_scope(
                config_scope,
                resource_id=resource_id,
                cloud_entry_type=str(resource.get("cloudEntryType") or ""),
            )
            projected_scope, scope_truncated = _project_scope(config_scope)
            coverages.append(
                {
                    "policyId": str(policy.get("id") or ""),
                    "policyName": str(policy.get("name") or ""),
                    "category": str(policy.get("category") or ""),
                    "severity": str(policy.get("severity") or ""),
                    "description": description,
                    "descriptionTruncated": description_truncated,
                    "remedie": remedie,
                    "remedieTruncated": remedie_truncated,
                    "resourceTypes": policy_types,
                    "typeMatch": type_match,
                    "configId": str(config.get("id") or ""),
                    "scope": projected_scope,
                    "scopeTruncated": scope_truncated,
                    "scopeStatus": scope_status,
                    "scopeReasons": scope_reasons,
                    "applicable": scope_status == "matched",
                    "lastExecuteStatus": str(config.get("lastExecuteStatus") or ""),
                    "lastExecuteDate": normalize_timestamp(config.get("lastExecuteDate")),
                    "lastExecutionId": str(config.get("lastExecutionId") or ""),
                    "ruleContent": rule_content,
                    "ruleContentTruncated": rule_truncated,
                    "resourceExecution": None,
                }
            )
    return coverages


def project_violation(violation: Mapping[str, Any]) -> dict[str, Any]:
    """Project one platform violation into bounded cost evidence.

    Args:
        violation: SmartCMP policy violation record.

    Returns:
        Normalized violation fields required for cost reasoning and follow-up analysis.
    """
    task_definition = _mapping(violation.get("taskDefinition"))
    return {
        "violationId": str(violation.get("id") or ""),
        "policyId": str(violation.get("policyId") or ""),
        "policyName": str(violation.get("policyName") or ""),
        "status": str(violation.get("status") or ""),
        "severity": str(violation.get("severity") or ""),
        "category": str(violation.get("category") or ""),
        "monthlyCost": normalize_money(violation.get("monthlyCost")),
        "monthlySaving": normalize_money(violation.get("monthlySaving")),
        "savingOperationType": str(violation.get("savingOperationType") or ""),
        "fixType": str(violation.get("fixType") or ""),
        "taskDefinitionName": str(task_definition.get("name") or ""),
        "lastExecuteDate": normalize_timestamp(violation.get("lastExecuteDate")),
    }


def _execution_status(coverage: Mapping[str, Any]) -> str:
    execution = coverage.get("resourceExecution")
    if isinstance(execution, Mapping):
        return str(execution.get("status") or "").strip().upper()
    return ""


def _has_complete_execution_evidence(coverage: Mapping[str, Any]) -> bool:
    execution = coverage.get("resourceExecution")
    if not isinstance(execution, Mapping):
        return False
    extra = execution.get("extra")
    if not isinstance(extra, Mapping):
        return False
    return extra.get("evidenceComplete") is True or extra.get("evaluationEvidenceComplete") is True


def build_platform_assessment(
    policy_coverages: list[Mapping[str, Any]],
    active_violations: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Derive a conservative platform status from coverage and execution facts.

    Args:
        policy_coverages: Enabled type-compatible policy configuration evidence.
        active_violations: Active SmartCMP violations exactly matched to the resource.

    Returns:
        Platform status with separate coverage, evaluation, and evidence-completeness fields.
    """
    if active_violations:
        return {
            "platformStatus": "platform_detected",
            "coverageStatus": "active_violation",
            "evaluationStatus": "violation",
            "evidenceCompleteness": "platform_confirmed",
            "conclusion": "SmartCMP has an active cost optimization violation for this resource.",
        }

    applicable = [coverage for coverage in policy_coverages if coverage.get("applicable") is True]
    if not applicable:
        scope_unknown = any(coverage.get("scopeStatus") == "scope_unknown" for coverage in policy_coverages)
        scope_excluded = any(coverage.get("scopeStatus") == "excluded" for coverage in policy_coverages)
        coverage_status = "scope_unknown" if scope_unknown else "scope_excluded" if scope_excluded else "none"
        return {
            "platformStatus": "not_covered",
            "coverageStatus": coverage_status,
            "evaluationStatus": "not_evaluated",
            "evidenceCompleteness": "unknown",
            "conclusion": "No enabled policy configuration is proven applicable to this resource.",
        }

    execution_statuses = [_execution_status(coverage) for coverage in applicable]
    nonempty_statuses = [status for status in execution_statuses if status]
    if nonempty_statuses and all(status in FAILURE_STATUSES for status in nonempty_statuses):
        return {
            "platformStatus": "execution_failed",
            "coverageStatus": "active_applicable",
            "evaluationStatus": "failed",
            "evidenceCompleteness": "incomplete",
            "conclusion": "Applicable policy execution failed for this resource.",
        }
    if any(status in NONCOMPLIANT_STATUSES for status in nonempty_statuses):
        return {
            "platformStatus": "platform_detected",
            "coverageStatus": "active_applicable",
            "evaluationStatus": "noncompliant",
            "evidenceCompleteness": "partial",
            "conclusion": "A resource execution reports noncompliance, but no active violation detail was returned.",
        }

    all_complete_compliance = bool(applicable) and all(
        _execution_status(coverage) == "COMPLIANCE" and _has_complete_execution_evidence(coverage)
        for coverage in applicable
    )
    if all_complete_compliance:
        return {
            "platformStatus": "evaluated_clear",
            "coverageStatus": "active_applicable",
            "evaluationStatus": "compliant",
            "evidenceCompleteness": "complete",
            "conclusion": "All applicable policies report compliance with explicit complete evidence.",
        }
    if nonempty_statuses:
        return {
            "platformStatus": "insufficient_evidence",
            "coverageStatus": "active_applicable",
            "evaluationStatus": "incomplete",
            "evidenceCompleteness": "unknown",
            "conclusion": "Policy execution exists, but the result does not prove complete evaluation evidence.",
        }
    return {
        "platformStatus": "covered_not_evaluated",
        "coverageStatus": "active_applicable",
        "evaluationStatus": "not_evaluated",
        "evidenceCompleteness": "missing",
        "conclusion": "Enabled policies apply, but no resource execution was found.",
    }


def build_financial_evidence(
    resource: Mapping[str, Any],
    active_violations: list[Mapping[str, Any]],
    *,
    currency: str | None,
    currency_code: str = "",
    currency_source: str = "",
) -> dict[str, Any]:
    """Build non-overlapping financial evidence without inventing savings.

    Args:
        resource: Projected resource cost facts.
        active_violations: Projected platform violations.
        currency: Verified SmartCMP tenant currency symbol, or ``None``.
        currency_code: Verified SmartCMP tenant currency code, when available.
        currency_source: Source of the verified currency metadata.

    Returns:
        Resource billing facts and per-violation platform saving estimates.
    """
    attributes = _mapping(resource.get("costAttributes"))
    estimates = [
        {
            "violationId": violation.get("violationId", ""),
            "policyId": violation.get("policyId", ""),
            "monthlyCost": normalize_money(violation.get("monthlyCost")),
            "monthlySaving": normalize_money(violation.get("monthlySaving")),
            "source": "smartcmp_violation",
        }
        for violation in active_violations
        if normalize_money(violation.get("monthlyCost")) is not None
        or normalize_money(violation.get("monthlySaving")) is not None
    ]
    return {
        "currency": currency,
        "currencyCode": currency_code or None,
        "currencySource": currency_source or None,
        "resourceCurrentBilling": normalize_money(attributes.get("currentBilling")),
        "resourceHistoryTotalBilling": normalize_money(attributes.get("historyTotalBilling")),
        "violationEstimates": estimates,
        "hasExactSavingEvidence": any(item.get("monthlySaving") is not None for item in estimates),
        "aggregationPolicy": "Do not sum estimates because multiple recommendations may overlap.",
    }


def build_missing_evidence(
    resource: Mapping[str, Any],
    financial_evidence: Mapping[str, Any],
    platform_assessment: Mapping[str, Any],
    policy_coverages: list[Mapping[str, Any]],
) -> list[str]:
    """List evidence gaps that constrain resource cost conclusions.

    Args:
        resource: Projected resource evidence.
        financial_evidence: Normalized billing and saving evidence.
        platform_assessment: Derived platform assessment.
        policy_coverages: Enabled type-compatible policy evidence.

    Returns:
        Stable evidence-gap identifiers for LLM reasoning.
    """
    missing: list[str] = []
    if financial_evidence.get("resourceCurrentBilling") is None and not financial_evidence.get(
        "hasExactSavingEvidence"
    ):
        missing.append("financial.currentBillingOrPlatformSaving")
    if financial_evidence.get("currency") is None:
        missing.append("financial.currency")
    if not resource.get("monitoringEvidenceAvailable"):
        missing.append("resource.monitoringEvidence")
    if platform_assessment.get("platformStatus") in {
        "insufficient_evidence",
        "covered_not_evaluated",
        "execution_failed",
    }:
        missing.append("policy.completeResourceEvaluation")
    if any(coverage.get("scopeStatus") == "scope_unknown" for coverage in policy_coverages):
        missing.append("policy.scopeCompatibility")
    cmp_status = str(resource.get("status") or "").casefold()
    provider_status = str(resource.get("providerStatus") or "").casefold()
    if cmp_status and provider_status and cmp_status != provider_status:
        missing.append("resource.inventoryStateConsistency")
    return missing


def build_analysis_contract() -> dict[str, Any]:
    """Return the required outer-LLM cost analysis contract.

    Returns:
        Model instructions that keep platform facts separate from inference.
    """
    return {
        "analysisMode": "llm_resource_cost",
        "allowedVerdicts": [
            "confirmed_optimization",
            "potential_optimization",
            "no_confirmed_opportunity",
            "indeterminate",
        ],
        "requiredOutput": [
            "verdict",
            "confidence",
            "platformFindings",
            "potentialOpportunities",
            "financialImpact",
            "missingEvidence",
            "risks",
            "recommendedActions",
        ],
        "rules": [
            "Label model-only opportunities as llm_potential.",
            "Do not present LLM inference as a SmartCMP policy result.",
            "Use an exact saving amount only from "
            "financialEvidence.violationEstimates[].monthlySaving; current billing is not saving.",
            "When no platform monthlySaving exists, set financialImpact.amount to null.",
            "Do not claim that no violation means no optimization opportunity.",
            "Do not turn backup, security, or reliability gaps into cost savings.",
            "For llm_potential findings, recommend read-only validation only; do not propose "
            "remediation until an active platform violation exists.",
        ],
    }


def build_analysis_payload(
    *,
    resource_id: str,
    resource: Mapping[str, Any],
    policy_coverages: list[dict[str, Any]],
    active_violations: list[dict[str, Any]],
    currency: str | None,
    currency_code: str = "",
    currency_source: str = "",
    errors: list[str] | None = None,
    object_actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble the resource-first cost analysis evidence payload.

    Args:
        resource_id: Internal SmartCMP resource identifier for object metadata.
        resource: Projected resource facts.
        policy_coverages: Applicable and uncertain policy configuration evidence.
        active_violations: Active cost violations exactly matched to the resource.
        currency: Verified SmartCMP tenant currency symbol, or ``None``.
        currency_code: Verified SmartCMP tenant currency code, when available.
        currency_source: Source of the verified currency metadata.
        errors: Best-effort enrichment errors that did not prevent analysis.
        object_actions: Read-only UI actions for the selected resource.

    Returns:
        Structured context consumed by the AtlasClaw LLM.
    """
    platform_assessment = build_platform_assessment(policy_coverages, active_violations)
    financial_evidence = build_financial_evidence(
        resource,
        active_violations,
        currency=currency,
        currency_code=currency_code,
        currency_source=currency_source,
    )
    return {
        "object_type": "cost_optimization_resource",
        "object_id": resource_id,
        "object_name": str(resource.get("name") or resource_id),
        "object_actions": list(object_actions or []),
        "resource": dict(resource),
        "financialEvidence": financial_evidence,
        "policyCoverage": policy_coverages,
        "activeViolations": active_violations,
        "platformAssessment": platform_assessment,
        "analysisContract": build_analysis_contract(),
        "missingEvidence": build_missing_evidence(
            resource,
            financial_evidence,
            platform_assessment,
            policy_coverages,
        ),
        "errors": list(errors or []),
    }


def render_output(payload: Mapping[str, Any]) -> str:
    """Render a safe human summary and structured resource-cost context.

    Args:
        payload: Resource-first cost analysis payload.

    Returns:
        Human-readable English text plus a delimited JSON context block.
    """
    resource = _mapping(payload.get("resource"))
    assessment = _mapping(payload.get("platformAssessment"))
    financial = _mapping(payload.get("financialEvidence"))
    applicable_count = sum(1 for item in payload.get("policyCoverage") or [] if item.get("applicable"))
    violation_count = len(payload.get("activeViolations") or [])
    exact_saving_count = sum(
        1 for item in financial.get("violationEstimates") or [] if item.get("monthlySaving") is not None
    )
    lines = [
        f"Resource {resource.get('name') or 'unknown resource'}: {assessment.get('platformStatus') or 'indeterminate'}",
        "Type: "
        f"{resource.get('componentType') or resource.get('resourceType') or 'unknown'} | "
        f"Status: {resource.get('status') or 'unknown'}",
        f"Applicable enabled policies: {applicable_count} | Active violations: {violation_count}",
        f"Exact platform saving evidence: {exact_saving_count} finding(s)",
        f"Evidence completeness: {assessment.get('evidenceCompleteness') or 'unknown'}",
        "",
        "##RESOURCE_COST_ANALYSIS_START##",
        json.dumps(dict(payload), ensure_ascii=False),
        "##RESOURCE_COST_ANALYSIS_END##",
    ]
    return "\n".join(lines)
