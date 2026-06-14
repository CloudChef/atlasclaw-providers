# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Shared pre-approval analysis rules for SmartCMP approval workflows."""

from __future__ import annotations

import re
from typing import Any


PREAPPROVAL_HEADINGS = (
    "# Pre Approval Instructions",
    "# Preapproval Instructions",
    "# Pre-Approval Instructions",
)

_VAGUE_DESCRIPTIONS = {
    "test",
    "testing",
    "for business",
    "urgent",
    "none",
    "n/a",
    "na",
    "无",
    "测试",
    "业务",
    "紧急",
}


def unavailable_catalog_policy(
    *,
    status: str,
    error: str = "",
    catalog_id: str = "",
) -> dict[str, Any]:
    """Build a fail-closed catalog policy result when catalog policy is unavailable."""
    policy: dict[str, Any] = {
        "status": status,
        "catalogId": catalog_id,
        "hasPreApprovalInstructions": False,
        "instructions": "",
        "heading": "",
    }
    if error:
        policy["error"] = error
    return policy


def build_catalog_policy(catalog: dict[str, Any], catalog_id: str) -> dict[str, Any]:
    """Extract pre-approval policy metadata from a SmartCMP catalog response."""
    instructions, heading = extract_preapproval_section(first_text(catalog.get("instructions")))
    return {
        "status": "ok",
        "catalogId": catalog_id,
        "catalogName": first_text(catalog.get("nameZh"), catalog.get("name"), catalog.get("displayName")),
        "hasPreApprovalInstructions": bool(instructions),
        "instructions": instructions,
        "heading": heading,
    }


def extract_preapproval_section(markdown_text: str) -> tuple[str, str]:
    """Return the catalog pre-approval instruction section and matched heading."""
    lines = markdown_text.splitlines()
    start_index = -1
    matched_heading = ""
    normalized_headings = {heading.strip(): heading.strip() for heading in PREAPPROVAL_HEADINGS}

    for index, line in enumerate(lines):
        stripped = line.strip().lstrip("\ufeff")
        if stripped in normalized_headings:
            start_index = index + 1
            matched_heading = normalized_headings[stripped]
            break
    if start_index == -1:
        return "", ""

    section_lines: list[str] = []
    for line in lines[start_index:]:
        if line.startswith("# "):
            break
        section_lines.append(line)
    return "\n".join(section_lines).strip(), matched_heading


def first_text(*values: Any) -> str:
    """Return the first non-empty text value, unwrapping SmartCMP value objects."""
    for value in values:
        if isinstance(value, dict) and "value" in value:
            value = value.get("value")
        if isinstance(value, (str, int, float)):
            text = str(value).strip()
            if text:
                return text
    return ""


def analyze_preapproval_request(
    detail: dict[str, Any],
    catalog_policy: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate one approval request using the shared pre-approval review contract."""
    reasoning: list[str] = []
    concerns: list[str] = []
    suggestions: list[str] = []

    description = str(detail.get("description") or "").strip()
    specs = [str(item) for item in detail.get("resourceSpecs") or [] if str(item).strip()]
    cost = str(detail.get("costEstimate") or "").strip()

    if has_meaningful_description(description):
        reasoning.append("Requester provided a concrete description for the approval context.")
    else:
        concerns.append("Business purpose is missing or too vague for an auditable approval.")
        suggestions.append("Ask the requester to provide concrete business purpose and target workload.")

    if specs:
        reasoning.append(f"Resource specs are visible: {', '.join(specs[:4])}.")
    else:
        concerns.append("No detailed resource sizing facts were found in the request metadata.")
        suggestions.append("Verify CPU, memory, storage, and environment before approval.")

    high_spec_signals = high_spec_signals_from_specs(specs)
    if high_spec_signals:
        concerns.append("Requested capacity may need justification: " + "; ".join(high_spec_signals) + ".")
        suggestions.append("Confirm why this sizing is required instead of a smaller option.")

    if cost and cost != "not_estimated":
        reasoning.append(f"Cost estimate is available: {cost}.")
    else:
        concerns.append("Cost estimate is not available from SmartCMP.")

    policy_status = str(catalog_policy.get("status") or "")
    has_catalog_policy = bool(catalog_policy.get("hasPreApprovalInstructions"))
    if has_catalog_policy:
        reasoning.append(
            "Catalog-level pre-approval instructions were found and are authoritative for the final decision."
        )
        concerns.append(
            "Catalog policy exists and must be applied by the approval workflow before any mutating decision."
        )
        suggestions.append("Review the catalog pre-approval instructions before approving or rejecting.")
    elif policy_status == "missing_catalog_id":
        concerns.append("Catalog ID is missing, so catalog-specific pre-approval policy could not be checked.")
        suggestions.append("Do not approve automatically without confirming the catalog policy.")
    elif policy_status == "unavailable":
        concerns.append("Catalog policy could not be fetched from SmartCMP.")
        suggestions.append("Treat the request as requiring manual review until catalog policy is available.")
    else:
        reasoning.append("No catalog-specific pre-approval instructions were found; using the default rubric.")

    if detail.get("waitHours", 0) and float(detail["waitHours"]) >= 168:
        reasoning.append("The request has waited more than seven days, so it should be handled soon.")

    decision_guidance = decision_guidance_for(concerns, high_spec_signals, catalog_policy)
    return {
        "decision_guidance": decision_guidance,
        "confidence": confidence_for(decision_guidance, catalog_policy),
        "reasoning": reasoning,
        "concerns": concerns,
        "improvement_suggestions": dedupe(suggestions),
    }


def has_meaningful_description(description: str) -> bool:
    """Return whether requester notes are concrete enough for audit review."""
    normalized = " ".join(description.lower().split())
    if not normalized or normalized in _VAGUE_DESCRIPTIONS:
        return False
    return len(normalized) >= 8 and any(char.isalnum() for char in normalized)


def high_spec_signals_from_specs(specs: list[str]) -> list[str]:
    """Detect resource sizing signals that require justification."""
    signals: list[str] = []
    for spec in specs:
        lowered = spec.lower()
        if any(keyword in lowered for keyword in ("xlarge", "large", "premium", "high")):
            signals.append(spec)
            continue
        if lowered.startswith("cpu_cores=") and number_after_equals(lowered) >= 8:
            signals.append(spec)
            continue
        if lowered.startswith("memory=") and number_after_equals(lowered) >= 32768:
            signals.append(spec)
            continue
        if lowered.startswith("storage=") and number_after_equals(lowered) >= 1024:
            signals.append(spec)
    return dedupe(signals)


def number_after_equals(value: str) -> float:
    """Parse a numeric value after ``=`` for simple resource spec comparisons."""
    match = re.search(r"=\s*([0-9]+(?:\.[0-9]+)?)", value)
    return float(match.group(1)) if match else 0.0


def decision_guidance_for(
    concerns: list[str],
    high_spec_signals: list[str],
    catalog_policy: dict[str, Any],
) -> str:
    """Return conservative decision guidance from shared pre-approval signals."""
    if catalog_policy.get("hasPreApprovalInstructions"):
        return "manual_review_required"
    if any("Business purpose" in concern for concern in concerns):
        return "manual_review_required"
    if high_spec_signals:
        return "manual_review_required"
    if any("Catalog" in concern for concern in concerns):
        return "manual_review_required"
    return "likely_approvable"


def confidence_for(decision_guidance: str, catalog_policy: dict[str, Any]) -> str:
    """Return confidence for non-mutating guidance."""
    if catalog_policy.get("hasPreApprovalInstructions"):
        return "low"
    if decision_guidance == "likely_approvable":
        return "medium"
    return "low"


def dedupe(values: list[str]) -> list[str]:
    """Preserve order while removing duplicate text entries."""
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped
