#!/usr/bin/env python3
"""Integration-level tests for build_analysis_payload in analyze_recommendation.py."""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from analyze_recommendation import build_analysis_payload


def _make_violation(**kwargs) -> dict:
    base = {
        "id": "Violation_20260331000010",
        "policyId": "policy-001",
        "policyName": "Adjust Config - Fix Operation",
        "resourceId": "resource-001",
        "resourceName": "demo-vm",
        "status": "ACTIVE",
        "severity": "LOW",
        "category": "VM_OPTIMIZATION",
        "monthlyCost": 200.0,
        "monthlySaving": 86.70,
        "savingOperationType": "RESIZE",
        "fixType": "DAY2",
        "times": 3,
    }
    base.update(kwargs)
    return base


def _make_policy() -> dict:
    return {
        "id": "policy-001",
        "name": "Adjust Config - Fix Operation",
        "description": "Downsize over-provisioned VMs.",
        "category": "VM_OPTIMIZATION",
    }


def _make_saving_summary(optimizable: float = 500.0) -> dict:
    return {
        "optimizableAmount": optimizable,
        "savedAmount": 1121.0,
        "currentMonthOptimizable": optimizable,
        "lastMonthOptimizable": 400.0,
    }


def _make_resource_top(include_resource: bool = False) -> list:
    items = [
        {"resourceId": "resource-top-1", "resourceName": "top-vm-1", "totalSaving": 300.0},
        {"resourceId": "resource-top-2", "resourceName": "top-vm-2", "totalSaving": 200.0},
    ]
    if include_resource:
        items.append({"resourceId": "resource-001", "resourceName": "demo-vm", "totalSaving": 86.70})
    return items


def _make_policy_executions(compliance_rate: int = 75) -> list:
    return [
        {
            "complianceRate": compliance_rate,
            "startTime": "2026-04-01T01:01:00Z",
            "endTime": "2026-04-01T01:02:00Z",
        }
    ]


# ---------------------------------------------------------------------------
# Basic payload structure
# ---------------------------------------------------------------------------


class TestBuildAnalysisPayloadStructure:
    def test_payload_has_required_top_level_keys(self):
        payload = build_analysis_payload(violation=_make_violation())
        assert "violationId" in payload
        assert "facts" in payload
        assert "assessment" in payload
        assert "recommendations" in payload
        assert "suggestedNextStep" in payload

    def test_violation_id_mapped_correctly(self):
        payload = build_analysis_payload(violation=_make_violation())
        assert payload["violationId"] == "Violation_20260331000010"

    def test_suggested_next_step_equals_first_recommendation_action(self):
        """AC-32 acceptance #7: suggestedNextStep == recommendations[0]['action']."""
        payload = build_analysis_payload(violation=_make_violation())
        assert payload["suggestedNextStep"] == payload["recommendations"][0]["action"]

    def test_at_least_two_recommendations(self):
        """AC-32 acceptance #1: at least P0 + P1 recommendations."""
        payload = build_analysis_payload(violation=_make_violation())
        assert len(payload["recommendations"]) >= 2

    def test_first_recommendation_is_p0(self):
        payload = build_analysis_payload(violation=_make_violation())
        assert payload["recommendations"][0]["priority"] == "P0"


# ---------------------------------------------------------------------------
# assessment fields
# ---------------------------------------------------------------------------


class TestAssessmentFields:
    def test_violation_type_resize_is_oversized_spec(self):
        payload = build_analysis_payload(violation=_make_violation(savingOperationType="RESIZE"))
        assert payload["assessment"]["violationType"] == "OVERSIZED_SPEC"

    def test_violation_type_tear_down_is_idle_resource(self):
        payload = build_analysis_payload(violation=_make_violation(savingOperationType="TEAR_DOWN_IN_RESOURCE"))
        assert payload["assessment"]["violationType"] == "IDLE_RESOURCE"

    def test_violation_type_change_pay_is_suboptimal_billing(self):
        payload = build_analysis_payload(violation=_make_violation(savingOperationType="CHANGE_PAY_TYPE"))
        assert payload["assessment"]["violationType"] == "SUBOPTIMAL_BILLING"

    def test_risk_level_resize_is_medium(self):
        """AC-32 acceptance #2: RESIZE → riskLevel=medium."""
        payload = build_analysis_payload(violation=_make_violation(savingOperationType="RESIZE"))
        assert payload["assessment"]["riskLevel"] == "medium"

    def test_risk_level_tear_down_is_high(self):
        """AC-32 acceptance #3: TEAR_DOWN_IN_RESOURCE → riskLevel=high."""
        payload = build_analysis_payload(violation=_make_violation(savingOperationType="TEAR_DOWN_IN_RESOURCE"))
        assert payload["assessment"]["riskLevel"] == "high"

    def test_risk_level_change_pay_type_is_low(self):
        payload = build_analysis_payload(violation=_make_violation(savingOperationType="CHANGE_PAY_TYPE"))
        assert payload["assessment"]["riskLevel"] == "low"

    def test_violation_recurrence_mapped_from_times(self):
        """AC-32 acceptance #8: violationRecurrence = violation.times."""
        payload = build_analysis_payload(violation=_make_violation(times=7))
        assert payload["assessment"]["violationRecurrence"] == 7

    def test_task_definition_present_true_when_fix_type_set(self):
        violation = _make_violation(fixType="DAY2")
        violation["taskDefinition"] = {"id": "td-001", "name": "day2-task"}
        payload = build_analysis_payload(violation=violation)
        assert payload["assessment"]["taskDefinitionPresent"] is True

    def test_task_definition_present_false_when_missing(self):
        payload = build_analysis_payload(violation=_make_violation(fixType=""))
        assert payload["assessment"]["taskDefinitionPresent"] is False


# ---------------------------------------------------------------------------
# saving_summary enrichment
# ---------------------------------------------------------------------------


class TestSavingSummaryEnrichment:
    def test_saving_contribution_pct_non_null_when_summary_available(self):
        """AC-32 acceptance #5: savingContributionPct is non-null."""
        payload = build_analysis_payload(
            violation=_make_violation(monthlySaving=100.0),
            saving_summary=_make_saving_summary(optimizable=500.0),
        )
        assert payload["assessment"]["savingContributionPct"] is not None
        assert payload["assessment"]["savingContributionPct"] == 20.0

    def test_saving_contribution_pct_null_without_summary(self):
        payload = build_analysis_payload(violation=_make_violation())
        assert payload["assessment"]["savingContributionPct"] is None

    def test_saving_summary_available_flag(self):
        payload = build_analysis_payload(
            violation=_make_violation(),
            saving_summary=_make_saving_summary(),
        )
        assert payload["assessment"]["savingSummaryAvailable"] is True

    def test_saving_summary_unavailable_flag(self):
        payload = build_analysis_payload(violation=_make_violation())
        assert payload["assessment"]["savingSummaryAvailable"] is False


# ---------------------------------------------------------------------------
# resource_top — isTopSavingResource
# ---------------------------------------------------------------------------


class TestIsTopSavingResource:
    def test_is_top_saving_resource_true_when_in_list(self):
        """AC-32 acceptance #6: isTopSavingResource=true when resource in top list."""
        payload = build_analysis_payload(
            violation=_make_violation(),
            resource_top=_make_resource_top(include_resource=True),
        )
        assert payload["assessment"]["isTopSavingResource"] is True

    def test_is_top_saving_resource_false_when_not_in_list(self):
        payload = build_analysis_payload(
            violation=_make_violation(),
            resource_top=_make_resource_top(include_resource=False),
        )
        assert payload["assessment"]["isTopSavingResource"] is False

    def test_is_top_saving_resource_false_when_no_resource_top(self):
        payload = build_analysis_payload(violation=_make_violation())
        assert payload["assessment"]["isTopSavingResource"] is False


# ---------------------------------------------------------------------------
# policy_executions — policyComplianceRate
# ---------------------------------------------------------------------------


class TestPolicyComplianceRate:
    def test_compliance_rate_from_latest_execution(self):
        """AC-32 acceptance #9: policyComplianceRate from latest policy-execution."""
        payload = build_analysis_payload(
            violation=_make_violation(),
            policy_executions=_make_policy_executions(compliance_rate=75),
        )
        assert payload["assessment"]["policyComplianceRate"] == 75

    def test_compliance_rate_null_without_executions(self):
        payload = build_analysis_payload(violation=_make_violation())
        assert payload["assessment"]["policyComplianceRate"] is None


# ---------------------------------------------------------------------------
# relatedPolicyCount
# ---------------------------------------------------------------------------


class TestRelatedPolicyCount:
    def test_related_policy_count_passed_through(self):
        payload = build_analysis_payload(
            violation=_make_violation(),
            related_policy_count=5,
        )
        assert payload["assessment"]["relatedPolicyCount"] == 5

    def test_related_policy_count_default_zero(self):
        payload = build_analysis_payload(violation=_make_violation())
        assert payload["assessment"]["relatedPolicyCount"] == 0


# ---------------------------------------------------------------------------
# configuration_guide included when fixType missing
# ---------------------------------------------------------------------------


class TestConfigurationGuideInPayload:
    def test_configuration_guide_included_when_fix_type_missing(self):
        """AC-32 acceptance #4: configuration_guide in recommendations when fixType empty."""
        payload = build_analysis_payload(
            violation=_make_violation(fixType="", status="ACTIVE")
        )
        types = [r["type"] for r in payload["recommendations"]]
        assert "configuration_guide" in types

    def test_configuration_guide_absent_when_fix_type_present(self):
        payload = build_analysis_payload(
            violation=_make_violation(fixType="DAY2", status="ACTIVE")
        )
        types = [r["type"] for r in payload["recommendations"]]
        assert "configuration_guide" not in types
