#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Unit tests for _analysis.py helpers — AC-32 acceptance criteria #1–#9, #11."""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _analysis import (
    OPERATION_SPECIFIC_GUIDANCE,
    build_configuration_guide,
    build_policy_history_insight,
    build_recommendations,
    build_risk_assessment,
    build_saving_priority,
    classify_optimization_theme,
    classify_violation_type,
    determine_execution_readiness,
    normalize_analysis_facts,
)


# ---------------------------------------------------------------------------
# classify_violation_type
# ---------------------------------------------------------------------------


class TestClassifyViolationType:
    def test_resize_maps_to_oversized_spec(self):
        assert classify_violation_type("RESIZE") == "OVERSIZED_SPEC"

    def test_tear_down_maps_to_idle_resource(self):
        assert classify_violation_type("TEAR_DOWN_IN_RESOURCE") == "IDLE_RESOURCE"

    def test_change_pay_type_maps_to_suboptimal_billing(self):
        assert classify_violation_type("CHANGE_PAY_TYPE") == "SUBOPTIMAL_BILLING"

    def test_switch_to_subscription_maps_to_suboptimal_billing(self):
        assert classify_violation_type("SWITCH_TO_SUBSCRIPTION") == "SUBOPTIMAL_BILLING"

    def test_unknown_operation_returns_unknown(self):
        assert classify_violation_type("UNKNOWN_OP") == "UNKNOWN"

    def test_empty_string_returns_unknown(self):
        assert classify_violation_type("") == "UNKNOWN"

    def test_case_insensitive(self):
        assert classify_violation_type("resize") == "OVERSIZED_SPEC"


# ---------------------------------------------------------------------------
# classify_optimization_theme
# ---------------------------------------------------------------------------


class TestClassifyOptimizationTheme:
    def test_resize_maps_to_rightsizing(self):
        assert classify_optimization_theme(saving_operation_type="RESIZE") == "rightsizing"

    def test_tear_down_falls_back_to_manual_review(self):
        # TEAR_DOWN_IN_RESOURCE is not in THEME_RULES, falls back to text scan
        result = classify_optimization_theme(saving_operation_type="TEAR_DOWN_IN_RESOURCE")
        assert result in ("idle_shutdown", "manual_review")

    def test_policy_name_hint_rightsizing(self):
        result = classify_optimization_theme(policy_name="low utilization rightsize check")
        assert result == "rightsizing"

    def test_policy_name_hint_idle_shutdown(self):
        result = classify_optimization_theme(policy_name="idle vm shutdown policy")
        assert result == "idle_shutdown"

    def test_unknown_defaults_to_manual_review(self):
        result = classify_optimization_theme(saving_operation_type="", policy_name="", remedie="")
        assert result == "manual_review"


# ---------------------------------------------------------------------------
# build_risk_assessment
# ---------------------------------------------------------------------------


class TestBuildRiskAssessment:
    def _call(self, operation_type: str) -> dict:
        op_guidance = OPERATION_SPECIFIC_GUIDANCE.get(operation_type, {})
        facts: dict = {}
        return build_risk_assessment(facts, operation_type, op_guidance)

    def test_tear_down_is_high_risk(self):
        rec = self._call("TEAR_DOWN_IN_RESOURCE")
        assert rec["risk"] == "high"
        assert rec["type"] == "risk_assessment"
        assert rec["priority"] == "P1"
        assert len(rec["riskNotes"]) > 0

    def test_resize_is_medium_risk(self):
        rec = self._call("RESIZE")
        assert rec["risk"] == "medium"

    def test_change_pay_type_is_low_risk(self):
        rec = self._call("CHANGE_PAY_TYPE")
        assert rec["risk"] == "low"

    def test_switch_to_subscription_is_low_risk(self):
        rec = self._call("SWITCH_TO_SUBSCRIPTION")
        assert rec["risk"] == "low"

    def test_unknown_operation_is_medium_risk(self):
        rec = self._call("UNKNOWN_OP")
        assert rec["risk"] == "medium"

    def test_risk_notes_are_english(self):
        for op in ("RESIZE", "TEAR_DOWN_IN_RESOURCE", "CHANGE_PAY_TYPE", "SWITCH_TO_SUBSCRIPTION"):
            rec = self._call(op)
            for note in rec["riskNotes"]:
                assert all(ord(c) < 128 for c in note), f"Non-ASCII in riskNote for {op}: {note!r}"


# ---------------------------------------------------------------------------
# build_recommendations — multi-recommendation list
# ---------------------------------------------------------------------------


class TestBuildRecommendations:
    def _make_facts(self, **kwargs) -> dict:
        violation = {
            "id": "V001",
            "policyId": "P001",
            "policyName": "Test Policy",
            "resourceId": "R001",
            "resourceName": "test-vm",
            "status": "ACTIVE",
            "severity": "LOW",
            "category": "VM_OPTIMIZATION",
            "monthlyCost": 100.0,
            "monthlySaving": 50.0,
            "savingOperationType": "RESIZE",
            "fixType": "DAY2",
            "times": 3,
            **kwargs,
        }
        return normalize_analysis_facts(violation)

    def test_returns_at_least_two_recommendations(self):
        """AC-32 acceptance #1: at least P0 primary_action + P1 risk_assessment."""
        facts = self._make_facts()
        recs = build_recommendations(facts)
        assert len(recs) >= 2

    def test_first_recommendation_is_p0_primary_action(self):
        """AC-32 acceptance #7: suggestedNextStep must equal recommendations[0]['action']."""
        facts = self._make_facts()
        recs = build_recommendations(facts)
        assert recs[0]["priority"] == "P0"
        assert recs[0]["type"] == "primary_action"

    def test_ready_status_yields_execute_fix(self):
        """When fixType is present and status ACTIVE → action=execute_fix."""
        facts = self._make_facts(fixType="DAY2", status="ACTIVE")
        recs = build_recommendations(facts)
        assert recs[0]["action"] == "execute_fix"
        assert recs[0]["confidence"] == "high"

    def test_missing_fix_type_yields_configure_platform_policy(self):
        """AC-32 acceptance #4: no fixType → configuration_guide included."""
        facts = self._make_facts(fixType="", status="ACTIVE")
        recs = build_recommendations(facts)
        assert recs[0]["action"] == "configure_platform_policy"
        types = [r["type"] for r in recs]
        assert "configuration_guide" in types

    def test_completed_status_yields_observe(self):
        facts = self._make_facts(status="FIXED")
        recs = build_recommendations(facts)
        assert recs[0]["action"] == "observe"

    def test_resize_includes_medium_risk(self):
        """AC-32 acceptance #2: RESIZE → risk=medium."""
        facts = self._make_facts(savingOperationType="RESIZE", fixType="DAY2")
        recs = build_recommendations(facts)
        risk_rec = next((r for r in recs if r["type"] == "risk_assessment"), None)
        assert risk_rec is not None
        assert risk_rec["risk"] == "medium"

    def test_tear_down_includes_high_risk(self):
        """AC-32 acceptance #3: TEAR_DOWN_IN_RESOURCE → risk=high."""
        facts = self._make_facts(savingOperationType="TEAR_DOWN_IN_RESOURCE", fixType="DAY2")
        recs = build_recommendations(facts)
        risk_rec = next((r for r in recs if r["type"] == "risk_assessment"), None)
        assert risk_rec is not None
        assert risk_rec["risk"] == "high"

    def test_saving_priority_added_when_context_available(self):
        facts = self._make_facts()
        context = {"saving_summary": {"optimizableAmount": 500.0}}
        recs = build_recommendations(facts, context)
        types = [r["type"] for r in recs]
        assert "saving_priority" in types

    def test_policy_history_added_when_executions_available(self):
        facts = self._make_facts()
        executions = [{"complianceRate": 75, "startTime": "2026-04-01T01:00:00Z"}]
        context = {"policy_executions": executions}
        recs = build_recommendations(facts, context)
        types = [r["type"] for r in recs]
        assert "policy_history" in types

    def test_reason_field_is_english_only(self):
        """All reason fields must contain no Chinese characters."""
        facts = self._make_facts()
        recs = build_recommendations(facts)
        for rec in recs:
            reason = rec.get("reason", "")
            assert all(ord(c) < 0x4E00 or ord(c) > 0x9FFF for c in reason), \
                f"Chinese characters found in reason: {reason!r}"


# ---------------------------------------------------------------------------
# build_saving_priority — contribution percentage
# ---------------------------------------------------------------------------


class TestBuildSavingPriority:
    def test_contribution_pct_calculated_correctly(self):
        """AC-32 acceptance #5: savingContributionPct is non-null when saving_summary available."""
        facts = normalize_analysis_facts({"id": "V001", "monthlySaving": 100.0})
        saving_summary = {"optimizableAmount": 500.0}
        rec = build_saving_priority(facts, saving_summary)
        assert rec["type"] == "saving_priority"
        evidence_str = " ".join(rec["evidence"])
        assert "contributionPct=20.0" in evidence_str

    def test_contribution_pct_zero_optimizable(self):
        facts = normalize_analysis_facts({"id": "V001", "monthlySaving": 100.0})
        saving_summary = {"optimizableAmount": 0}
        rec = build_saving_priority(facts, saving_summary)
        # N/A when optimizable is 0
        assert "N/A" in rec["reason"]

    def test_reason_is_english(self):
        facts = normalize_analysis_facts({"id": "V001", "monthlySaving": 50.0})
        rec = build_saving_priority(facts, {"optimizableAmount": 200.0})
        assert all(ord(c) < 0x4E00 or ord(c) > 0x9FFF for c in rec["reason"])


# ---------------------------------------------------------------------------
# build_configuration_guide
# ---------------------------------------------------------------------------


class TestBuildConfigurationGuide:
    def test_returns_configuration_guide_type(self):
        facts = normalize_analysis_facts({"id": "V001", "policyName": "My Policy", "fixType": ""})
        rec = build_configuration_guide(facts)
        assert rec["type"] == "configuration_guide"
        assert rec["priority"] == "P1"

    def test_policy_name_in_reason(self):
        facts = normalize_analysis_facts({"id": "V001", "policyName": "My Policy", "fixType": ""})
        rec = build_configuration_guide(facts)
        assert "My Policy" in rec["reason"]

    def test_unknown_policy_fallback(self):
        # normalize_analysis_facts returns policyName="" when absent;
        # build_configuration_guide falls back to "unknown-policy" only when policyName is absent from facts dict
        facts = {"violationId": "V001", "policyName": None}
        rec = build_configuration_guide(facts)
        assert "unknown-policy" in rec["reason"]


# ---------------------------------------------------------------------------
# build_policy_history_insight
# ---------------------------------------------------------------------------


class TestBuildPolicyHistoryInsight:
    def test_violation_recurrence_mapped(self):
        """AC-32 acceptance #8: violationRecurrence maps from times field."""
        facts = normalize_analysis_facts({"id": "V001", "times": 5})
        executions = [{"complianceRate": 80}]
        rec = build_policy_history_insight(facts, executions)
        assert "5" in rec["reasonEn"]

    def test_first_occurrence_when_times_le_1(self):
        facts = normalize_analysis_facts({"id": "V001", "times": 1})
        executions = [{"complianceRate": 75}]
        rec = build_policy_history_insight(facts, executions)
        assert "first occurrence" in rec["reason"]

    def test_compliance_rate_in_reason(self):
        """AC-32 acceptance #9: policyComplianceRate from latest execution."""
        facts = normalize_analysis_facts({"id": "V001", "times": 3})
        executions = [{"complianceRate": 75}]
        rec = build_policy_history_insight(facts, executions)
        assert "75" in rec["reasonEn"]

    def test_empty_executions_returns_no_history(self):
        facts = normalize_analysis_facts({"id": "V001"})
        rec = build_policy_history_insight(facts, [])
        assert rec["confidence"] == "low"
        assert "No execution history" in rec["reasonEn"]

    def test_reason_is_english(self):
        facts = normalize_analysis_facts({"id": "V001", "times": 2})
        executions = [{"complianceRate": 90}]
        rec = build_policy_history_insight(facts, executions)
        assert all(ord(c) < 0x4E00 or ord(c) > 0x9FFF for c in rec["reason"])
