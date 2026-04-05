#!/usr/bin/env python3
"""Deterministic analysis helpers for SmartCMP cost optimization."""

from __future__ import annotations

import os


def _currency() -> str:
    """Return currency symbol from env CMP_CURRENCY, default ¥."""
    return os.environ.get("CMP_CURRENCY", "¥")


THEME_RULES = {
    "RIGHTSIZE": "rightsizing",
    "RESIZE": "rightsizing",
    "STOP_IDLE": "idle_shutdown",
    "SHUTDOWN_IDLE": "idle_shutdown",
    "DELETE_UNUSED": "orphan_cleanup",
    "RELEASE_UNUSED": "orphan_cleanup",
    "STORAGE_TIER": "storage_optimization",
    "RIGHTSIZE_STORAGE": "storage_optimization",
}

BEST_PRACTICE_GUIDANCE = {
    "rightsizing": "Reduce over-provisioned compute for low-utilization workloads on AWS or Azure.",
    "idle_shutdown": "Stop or schedule idle compute resources to avoid steady-state waste.",
    "orphan_cleanup": "Remove unattached or unused resources such as disks or public IPs.",
    "storage_optimization": "Move data to a more appropriate storage tier and right-size capacity.",
    "manual_review": "Review the SmartCMP recommendation before taking action.",
}

BEST_PRACTICE_GUIDANCE_ZH = {
    "rightsizing": "降低过度配置的计算资源规格，以匹配低利用率工作负载的实际需求。",
    "idle_shutdown": "停止或调度空闲计算资源，避免持续产生浪费。",
    "orphan_cleanup": "清理未挂载或未使用的资源（如磁盘、公网IP），减少资源浪费。",
    "storage_optimization": "将数据迁移到更合适的存储层级，并合理调整容量。",
    "manual_review": "请在执行前审阅 SmartCMP 的优化建议。",
}

# Mapping from SavingOperationType to ViolationType
VIOLATION_TYPE_MAP = {
    "RESIZE": "OVERSIZED_SPEC",
    "RIGHTSIZE": "OVERSIZED_SPEC",
    "TEAR_DOWN_IN_RESOURCE": "IDLE_RESOURCE",
    "STOP_IDLE": "IDLE_RESOURCE",
    "SHUTDOWN_IDLE": "IDLE_RESOURCE",
    "DELETE_UNUSED": "IDLE_RESOURCE",
    "CHANGE_PAY_TYPE": "SUBOPTIMAL_BILLING",
    "SWITCH_TO_SUBSCRIPTION": "SUBOPTIMAL_BILLING",
}

# Operation-specific guidance per SavingOperationType (bilingual + risk level)
OPERATION_SPECIFIC_GUIDANCE = {
    "RESIZE": {
        "zh": "检测到计算资源规格过大，建议根据近30天CPU/内存峰值利用率降配至合适规格。降配前请确认业务峰值时段，避免影响生产可用性。",
        "en": "Downsize compute to match observed peak utilization over 30 days. Verify business peak windows before applying changes.",
        "risk": "medium",
        "risk_notes": ["May impact performance during peak hours", "Execute within a maintenance window", "Backup resource configuration before applying"],
    },
    "TEAR_DOWN_IN_RESOURCE": {
        "zh": "检测到长期空闲资源，建议先确认资源归属业务方，确认无使用需求后再执行卸载，以避免误删。",
        "en": "Confirm resource ownership and absence of planned usage before tearing down idle resources.",
        "risk": "high",
        "risk_notes": ["Operation is irreversible", "Confirm no dependent resources before executing", "Notify resource owner before proceeding"],
    },
    "CHANGE_PAY_TYPE": {
        "zh": "当前资源采用非最优计费模式，建议切换为更适合使用频率的计费方式以降低费用。",
        "en": "Switch to a billing model that better matches actual usage patterns.",
        "risk": "low",
        "risk_notes": ["A brief billing gap may occur during the switch"],
    },
    "SWITCH_TO_SUBSCRIPTION": {
        "zh": "资源长期稳定运行，建议从按需付费切换为包年包月，可节省约30-40%费用。",
        "en": "Convert steady-state on-demand resources to reserved/subscription pricing for 30-40% savings.",
        "risk": "low",
        "risk_notes": ["Subscription commitments are generally non-refundable", "Confirm resource usage plan before committing"],
    },
}

ACTIVE_STATUSES = {"ACTIVE", "ACTIVED", "OPEN", "NEW", "PENDING", "RUNNING"}
COMPLETED_STATUSES = {"FIXED", "RESOLVED", "SUCCESS", "DONE", "CLOSED"}


def classify_optimization_theme(
    saving_operation_type: str = "",
    policy_name: str = "",
    remedie: str = "",
) -> str:
    """Map SmartCMP recommendation hints to a stable optimization theme."""
    operation_key = (saving_operation_type or "").strip().upper()
    if operation_key in THEME_RULES:
        return THEME_RULES[operation_key]

    hint_text = " ".join(part.lower() for part in (policy_name, remedie) if part)
    if "rightsize" in hint_text or "over-provision" in hint_text:
        return "rightsizing"
    if "idle" in hint_text or "shutdown" in hint_text or "deallocate" in hint_text:
        return "idle_shutdown"
    if "unattached" in hint_text or "unused" in hint_text or "orphan" in hint_text:
        return "orphan_cleanup"
    if "storage" in hint_text or "tier" in hint_text:
        return "storage_optimization"
    return "manual_review"


def classify_violation_type(saving_operation_type: str = "") -> str:
    """Map SavingOperationType to ViolationType."""
    operation_key = (saving_operation_type or "").strip().upper()
    return VIOLATION_TYPE_MAP.get(operation_key, "UNKNOWN")


def normalize_analysis_facts(violation: dict, policy: dict | None = None) -> dict:
    """Combine violation and policy data into stable platform facts."""
    policy = policy or {}
    task_definition = violation.get("taskDefinition") or {}
    policy_remedie = policy.get("remedie")
    return {
        "violationId": violation.get("id", ""),
        "policyId": violation.get("policyId") or policy.get("id", ""),
        "policyName": violation.get("policyName") or policy.get("name", ""),
        "resourceId": violation.get("resourceId", ""),
        "resourceName": violation.get("resourceName", ""),
        "status": violation.get("status", ""),
        "severity": violation.get("severity", ""),
        "category": violation.get("category", ""),
        "monthlyCost": violation.get("monthlyCost"),
        "monthlySaving": violation.get("monthlySaving"),
        "savingOperationType": violation.get("savingOperationType", ""),
        "fixType": violation.get("fixType", ""),
        "taskDefinitionName": task_definition.get("name", ""),
        "policyDescription": policy.get("description", ""),
        "remedie": violation.get("remedie") or policy_remedie or "",
        "times": violation.get("times", 0),
        "resourceType": violation.get("resourceType", ""),
        "componentType": violation.get("componentType", ""),
        "resourceStatus": violation.get("resourceStatus", ""),
        "osType": violation.get("osType", ""),
        "osDescription": violation.get("osDescription", ""),
        "resourceContextAvailable": bool(violation.get("resourceContextAvailable")),
        "resourceFetchStatus": violation.get("resourceFetchStatus", ""),
        "resourceContext": violation.get("resourceContext")
        if isinstance(violation.get("resourceContext"), dict)
        else {
            "requestedResourceIds": [violation.get("resourceId", "")] if violation.get("resourceId") else [],
            "resolvedCount": 0,
            "resources": [],
        },
    }


def _status_key(facts: dict) -> str:
    """Normalize SmartCMP status text for downstream decisions."""
    return (facts.get("status") or "").strip().upper()


def _has_platform_repair(facts: dict) -> bool:
    """Return True when SmartCMP exposes a native repair action for the finding."""
    return bool(facts.get("fixType") or facts.get("taskDefinitionName"))


def determine_execution_readiness(facts: dict) -> str:
    """Decide whether SmartCMP-native execution is ready, manual, or skippable."""
    status = _status_key(facts)
    if status in COMPLETED_STATUSES:
        return "skip"

    if _has_platform_repair(facts):
        return "ready"

    # Active findings without a repair action should stay reviewable instead of
    # being skipped just because SmartCMP omitted a savings estimate.
    if status in ACTIVE_STATUSES or facts.get("policyId") or facts.get("remedie"):
        return "manual_review"

    saving = facts.get("monthlySaving")
    if saving is None or saving <= 0:
        return "skip"
    return "manual_review"


def build_recommendations(facts: dict, context: dict | None = None) -> list[dict]:
    """Build a multi-dimensional recommendation list with risk assessment."""
    context = context or {}
    theme = classify_optimization_theme(
        saving_operation_type=facts.get("savingOperationType", ""),
        policy_name=facts.get("policyName", ""),
        remedie=facts.get("remedie", ""),
    )
    violation_type = classify_violation_type(facts.get("savingOperationType", ""))
    readiness = determine_execution_readiness(facts)
    platform_executable = readiness == "ready"
    missing_repair_action = readiness == "manual_review" and not _has_platform_repair(facts)

    recommendations = []

    # P0: Primary action recommendation
    if readiness == "skip":
        action = "observe"
        confidence = "medium"
        reason = "SmartCMP does not show positive savings or the finding already looks complete."
    elif readiness == "ready":
        action = "execute_fix"
        confidence = "high"
        reason = "A repair action is configured on the platform; the day2 fix can be executed safely."
    elif missing_repair_action:
        action = "configure_platform_policy"
        confidence = "high"
        reason = "The finding is active but the policy has no repair action configured. Configure a day2 repair task first."
    else:
        action = "manual_review"
        confidence = "medium"
        reason = "The finding is valid but SmartCMP remediation readiness is incomplete; manual review is recommended."

    evidence = []
    if facts.get("monthlySaving") is not None:
        evidence.append(f"monthlySaving={facts['monthlySaving']}")
    if facts.get("savingOperationType"):
        evidence.append(f"savingOperationType={facts['savingOperationType']}")
    if facts.get("fixType"):
        evidence.append(f"fixType={facts['fixType']}")
    if facts.get("taskDefinitionName"):
        evidence.append(f"taskDefinitionName={facts['taskDefinitionName']}")
    if facts.get("componentType"):
        evidence.append(f"componentType={facts['componentType']}")
    if facts.get("resourceType"):
        evidence.append(f"resourceType={facts['resourceType']}")
    if facts.get("resourceStatus"):
        evidence.append(f"resourceStatus={facts['resourceStatus']}")
    if facts.get("osType"):
        evidence.append(f"osType={facts['osType']}")

    # Get operation-specific guidance
    operation_type = (facts.get("savingOperationType") or "").upper()
    op_guidance = OPERATION_SPECIFIC_GUIDANCE.get(operation_type, {})
    risk_level = op_guidance.get("risk", "medium")
    risk_notes = op_guidance.get("risk_notes", [])
    best_practice_zh = op_guidance.get("zh") or BEST_PRACTICE_GUIDANCE_ZH.get(theme, BEST_PRACTICE_GUIDANCE_ZH["manual_review"])
    best_practice_en = op_guidance.get("en") or BEST_PRACTICE_GUIDANCE.get(theme, BEST_PRACTICE_GUIDANCE["manual_review"])

    # P0: Primary action
    recommendations.append({
        "type": "primary_action",
        "action": action,
        "confidence": confidence,
        "priority": "P0",
        "reason": reason,
        "reasonEn": _get_reason_en(readiness, missing_repair_action),
        "evidence": evidence,
        "bestPractice": best_practice_en,
        "bestPracticeZh": best_practice_zh,
        "platformExecutable": platform_executable,
        "risk": risk_level,
        "riskNotes": risk_notes,
    })

    # P1: Risk assessment (always include)
    recommendations.append(build_risk_assessment(facts, operation_type, op_guidance))

    # P1: Configuration guide (only when fixType missing and active)
    if missing_repair_action:
        recommendations.append(build_configuration_guide(facts))

    # P1: Saving priority (when context available)
    saving_summary = context.get("saving_summary")
    if saving_summary and facts.get("monthlySaving"):
        currency = context.get("currency", _currency())
        recommendations.append(build_saving_priority(facts, saving_summary, currency=currency))

    # P2: Policy execution history (when context available)
    policy_executions = context.get("policy_executions")
    if policy_executions:
        recommendations.append(build_policy_history_insight(facts, policy_executions))

    return recommendations


def _get_reason_en(readiness: str, missing_repair_action: bool) -> str:
    """Get English reason text for backward compatibility."""
    if readiness == "skip":
        return "SmartCMP does not show positive savings or the finding already looks complete."
    elif readiness == "ready":
        return "SmartCMP exposes enough remediation hints to submit the day2 fix safely."
    elif missing_repair_action:
        return "The finding is active, but the SmartCMP policy does not expose a repair action. Configure a day2 repair task before calling the fix endpoint."
    else:
        return "The finding looks relevant, but SmartCMP remediation readiness is incomplete."


def build_risk_assessment(facts: dict, operation_type: str, op_guidance: dict) -> dict:
    """Build risk assessment recommendation."""
    risk_level = op_guidance.get("risk", "medium")
    risk_notes = op_guidance.get("risk_notes", [])

    if operation_type == "TEAR_DOWN_IN_RESOURCE":
        risk_level = "high"
        risk_notes = ["Operation is irreversible; resource cannot be recovered after deletion", "Confirm no dependent resources before executing", "Notify resource owner before proceeding"]
    elif operation_type == "RESIZE":
        risk_level = "medium"
        risk_notes = ["May impact performance during peak hours", "Execute within a maintenance window", "Backup resource configuration before applying"]
    elif operation_type in ("CHANGE_PAY_TYPE", "SWITCH_TO_SUBSCRIPTION"):
        risk_level = "low"
        if not risk_notes:
            risk_notes = ["Billing model change carries low risk"]
    else:
        risk_level = "medium"
        risk_notes = ["Assess potential impact before executing"]

    return {
        "type": "risk_assessment",
        "action": "assess_risk",
        "confidence": "high",
        "priority": "P1",
        "reason": f"Risk level: {risk_level}. {risk_notes[0] if risk_notes else ''}",
        "reasonEn": f"Risk level: {risk_level}. {risk_notes[0] if risk_notes else ''}",
        "evidence": [f"operationType={operation_type}", f"riskLevel={risk_level}"],
        "bestPractice": op_guidance.get("en", "Assess execution risk before proceeding."),
        "bestPracticeZh": op_guidance.get("zh", "执行前请评估风险。"),
        "platformExecutable": False,
        "risk": risk_level,
        "riskNotes": risk_notes,
    }


def build_configuration_guide(facts: dict) -> dict:
    """Build configuration guide recommendation when fixType is missing."""
    policy_name = facts.get("policyName") or "unknown-policy"
    return {
        "type": "configuration_guide",
        "action": "configure_platform_policy",
        "confidence": "high",
        "priority": "P1",
        "reason": f"Policy '{policy_name}' has no repair action configured. Configure a day2 repair task in SmartCMP before executing auto-fix.",
        "reasonEn": f"Policy '{policy_name}' has no repair action configured. Configure a day2 repair task in SmartCMP before executing auto-fix.",
        "evidence": ["fixType=", "taskDefinitionName="],
        "bestPractice": "Configure a day2 repair task for the policy to enable automatic remediation.",
        "bestPracticeZh": "为策略配置 day2 修复任务以启用自动修复能力。",
        "platformExecutable": False,
        "risk": "none",
        "riskNotes": [],
    }


def build_saving_priority(facts: dict, saving_summary: dict, currency: str = "") -> dict:
    """Build saving priority recommendation based on global summary."""
    sym = currency or _currency()
    monthly_saving = facts.get("monthlySaving") or 0
    optimizable = saving_summary.get("optimizableAmount") or saving_summary.get("currentMonthOptimizable") or 0

    contribution_pct = None
    if optimizable and optimizable > 0:
        contribution_pct = round((monthly_saving / optimizable) * 100, 2)

    return {
        "type": "saving_priority",
        "action": "evaluate_priority",
        "confidence": "high",
        "priority": "P1",
        "reason": f"This recommendation saves {sym}{monthly_saving:.2f}/month, {contribution_pct or 'N/A'}% of total optimizable amount.",
        "reasonEn": f"This recommendation saves {sym}{monthly_saving:.2f}/month, {contribution_pct or 'N/A'}% of total optimizable amount.",
        "evidence": [f"monthlySaving={monthly_saving}", f"contributionPct={contribution_pct}"],
        "bestPractice": "Prioritize recommendations with higher saving potential.",
        "bestPracticeZh": "优先处理节省金额较高的建议。",
        "platformExecutable": False,
        "risk": "none",
        "riskNotes": [],
    }


def build_policy_history_insight(facts: dict, policy_executions: list) -> dict:
    """Build insight from policy execution history."""
    if not policy_executions:
        return {
            "type": "policy_history",
            "action": "check_history",
            "confidence": "low",
            "priority": "P2",
            "reason": "No execution history found for this policy.",
            "reasonEn": "No execution history found for this policy.",
            "evidence": [],
            "bestPractice": "Monitor policy execution frequency.",
            "bestPracticeZh": "监控策略执行频率。",
            "platformExecutable": False,
            "risk": "none",
            "riskNotes": [],
        }

    latest = policy_executions[0] if policy_executions else {}
    compliance_rate = latest.get("complianceRate") or latest.get("compliance") or "N/A"
    execution_time = latest.get("startTime") or latest.get("createdTime") or ""

    times = facts.get("times", 0)
    recurrence_text = "first occurrence" if times <= 1 else f"triggered {times} time(s)"

    return {
        "type": "policy_history",
        "action": "review_history",
        "confidence": "medium",
        "priority": "P2",
        "reason": f"Policy compliance rate: {compliance_rate}%. This violation is a {recurrence_text}.",
        "reasonEn": f"Policy compliance rate: {compliance_rate}%. This violation has been triggered {times} time(s).",
        "evidence": [f"complianceRate={compliance_rate}", f"violationTimes={times}"],
        "bestPractice": "Review repeated violations for root cause analysis.",
        "bestPracticeZh": "对反复出现的违规进行根因分析。",
        "platformExecutable": False,
        "risk": "none",
        "riskNotes": [],
    }


def build_placeholder_analysis(violation_id: str) -> dict:
    """Return a stable placeholder analysis payload."""
    facts = normalize_analysis_facts({"id": violation_id})
    theme = classify_optimization_theme()
    violation_type = classify_violation_type()
    return {
        "violationId": violation_id,
        "facts": facts,
        "assessment": {
            "optimizationTheme": theme,
            "violationType": violation_type,
            "cloudBestPractice": BEST_PRACTICE_GUIDANCE["manual_review"],
            "cloudBestPracticeZh": BEST_PRACTICE_GUIDANCE_ZH["manual_review"],
            "executionReadiness": determine_execution_readiness(facts),
        },
        "recommendations": build_recommendations(facts),
        "suggestedNextStep": "manual_review",
    }
