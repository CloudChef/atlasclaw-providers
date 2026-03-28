#!/usr/bin/env python3
"""Deterministic analysis helpers for SmartCMP cost optimization."""

from __future__ import annotations


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


def build_recommendations(facts: dict) -> list[dict]:
    """Build a deterministic recommendation list."""
    theme = classify_optimization_theme(
        saving_operation_type=facts.get("savingOperationType", ""),
        policy_name=facts.get("policyName", ""),
        remedie=facts.get("remedie", ""),
    )
    readiness = determine_execution_readiness(facts)
    platform_executable = readiness == "ready"
    missing_repair_action = readiness == "manual_review" and not _has_platform_repair(facts)
    if readiness == "skip":
        action = "observe"
        confidence = "medium"
        reason = "SmartCMP does not show positive savings or the finding already looks complete."
    elif readiness == "ready":
        action = "execute_fix"
        confidence = "high"
        reason = "SmartCMP exposes enough remediation hints to submit the day2 fix safely."
    elif missing_repair_action:
        action = "configure_platform_policy"
        confidence = "high"
        reason = (
            "The finding is active, but the SmartCMP policy does not expose a repair action. "
            "Configure a day2 repair task before calling the fix endpoint."
        )
    else:
        action = "manual_review"
        confidence = "medium"
        reason = "The finding looks relevant, but SmartCMP remediation readiness is incomplete."

    evidence = []
    if facts.get("monthlySaving") is not None:
        evidence.append(f"monthlySaving={facts['monthlySaving']}")
    if facts.get("savingOperationType"):
        evidence.append(f"savingOperationType={facts['savingOperationType']}")
    if facts.get("fixType"):
        evidence.append(f"fixType={facts['fixType']}")
    if facts.get("taskDefinitionName"):
        evidence.append(f"taskDefinitionName={facts['taskDefinitionName']}")

    return [
        {
            "action": action,
            "confidence": confidence,
            "reason": reason,
            "evidence": evidence,
            "bestPractice": BEST_PRACTICE_GUIDANCE[theme],
            "platformExecutable": platform_executable,
        }
    ]


def build_placeholder_analysis(violation_id: str) -> dict:
    """Return a stable placeholder analysis payload."""
    facts = normalize_analysis_facts({"id": violation_id})
    return {
        "violationId": violation_id,
        "facts": facts,
        "assessment": {
            "optimizationTheme": classify_optimization_theme(),
            "cloudBestPractice": BEST_PRACTICE_GUIDANCE["manual_review"],
            "executionReadiness": determine_execution_readiness(facts),
        },
        "recommendations": build_recommendations(facts),
        "suggestedNextStep": "manual_review",
    }
