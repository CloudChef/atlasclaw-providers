#!/usr/bin/env python3
"""Render output layout tests for render_analysis() — AC-32 acceptance criteria #10."""

from __future__ import annotations

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from analyze_recommendation import build_analysis_payload, render_analysis


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


def _render(**kwargs) -> str:
    payload = build_analysis_payload(violation=_make_violation(**kwargs))
    return render_analysis(payload)


def _make_resource_records() -> list[dict]:
    return [
        {
            "resourceId": "resource-001",
            "summary": {
                "name": "demo-vm",
                "resourceType": "VirtualMachine",
                "componentType": "cloudchef.nodes.Compute",
                "status": "RUNNING",
                "osType": "Linux",
                "osDescription": "Ubuntu 22.04",
            },
            "resource": {"name": "demo-vm"},
            "normalized": {
                "type": "cloudchef.nodes.Compute",
                "properties": {"instanceType": "c6.large"},
            },
            "fetchStatus": "ok",
            "errors": [],
        }
    ]


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------


class TestOutputMarkers:
    def test_start_marker_present(self):
        output = _render()
        assert "##COST_ANALYSIS_START##" in output

    def test_end_marker_present(self):
        output = _render()
        assert "##COST_ANALYSIS_END##" in output

    def test_json_block_parseable(self):
        output = _render()
        start = output.index("##COST_ANALYSIS_START##") + len("##COST_ANALYSIS_START##\n")
        end = output.index("##COST_ANALYSIS_END##")
        json_str = output[start:end].strip()
        parsed = json.loads(json_str)
        assert "violationId" in parsed
        assert "assessment" in parsed
        assert "recommendations" in parsed


# ---------------------------------------------------------------------------
# Summary header lines
# ---------------------------------------------------------------------------


class TestSummaryHeaderLines:
    def test_violation_id_in_first_line(self):
        output = _render()
        lines = output.splitlines()
        assert "Violation_20260331000010" in lines[0]

    def test_resource_name_in_output(self):
        output = _render()
        assert "demo-vm" in output

    def test_estimated_saving_in_output(self):
        output = _render()
        assert "86.70" in output

    def test_risk_level_line_present(self):
        output = _render()
        assert "Risk level:" in output

    def test_policy_compliance_line_present(self):
        output = _render()
        assert "Policy compliance:" in output

    def test_occurrences_line_present(self):
        output = _render()
        assert "Occurrences:" in output

    def test_theme_line_present(self):
        output = _render()
        assert "Theme:" in output

    def test_resource_line_shows_type_and_status_when_datasource_context_exists(self):
        payload = build_analysis_payload(
            violation=_make_violation(resourceName=""),
            resource_records=_make_resource_records(),
        )
        output = render_analysis(payload)
        assert "Resource: demo-vm | type=cloudchef.nodes.Compute | status=RUNNING" in output


# ---------------------------------------------------------------------------
# Multi-recommendation rendering
# ---------------------------------------------------------------------------


class TestMultiRecommendationRendering:
    def test_p0_primary_action_line_present(self):
        output = _render()
        assert "[P0] Primary Action:" in output

    def test_p1_risk_assessment_line_present(self):
        output = _render()
        assert "[P1] Risk Assessment:" in output

    def test_p1_configuration_guide_when_fix_type_missing(self):
        """AC-32 acceptance #4: configuration_guide line appears when fixType empty."""
        output = _render(fixType="", status="ACTIVE")
        assert "[P1] Configuration Guide:" in output

    def test_configuration_guide_absent_when_fix_type_present(self):
        output = _render(fixType="DAY2")
        assert "[P1] Configuration Guide:" not in output

    def test_saving_priority_line_present_with_context(self):
        violation = _make_violation()
        saving_summary = {"optimizableAmount": 500.0}
        payload = build_analysis_payload(violation=violation, saving_summary=saving_summary)
        output = render_analysis(payload)
        assert "[P1] Saving Priority:" in output

    def test_policy_history_line_present_with_executions(self):
        violation = _make_violation()
        executions = [{"complianceRate": 75, "startTime": "2026-04-01T01:00:00Z"}]
        payload = build_analysis_payload(violation=violation, policy_executions=executions)
        output = render_analysis(payload)
        assert "[P2] Policy History:" in output


# ---------------------------------------------------------------------------
# Best Practice section
# ---------------------------------------------------------------------------


class TestBestPracticeSection:
    def test_best_practice_section_present(self):
        output = _render()
        assert "Best Practice:" in output

    def test_best_practice_content_non_empty(self):
        output = _render()
        lines = output.splitlines()
        bp_idx = next((i for i, l in enumerate(lines) if l.strip() == "Best Practice:"), None)
        assert bp_idx is not None
        # Next non-empty line should be the practice text
        practice_lines = [l for l in lines[bp_idx + 1:] if l.strip() and not l.startswith("##")]
        assert len(practice_lines) > 0


# ---------------------------------------------------------------------------
# English-only output (no Chinese in rendered text outside JSON block)
# ---------------------------------------------------------------------------


class TestEnglishOnlyOutput:
    def _get_non_json_output(self, output: str) -> str:
        """Return only the lines before the JSON marker."""
        if "##COST_ANALYSIS_START##" in output:
            return output[:output.index("##COST_ANALYSIS_START##")]
        return output

    def test_no_chinese_in_rendered_summary(self):
        """AC-32: rendered text outside JSON block must be English only."""
        output = _render()
        text = self._get_non_json_output(output)
        chinese_chars = [c for c in text if "\u4e00" <= c <= "\u9fff"]
        assert chinese_chars == [], f"Chinese characters found in rendered output: {chinese_chars!r}"

    def test_no_chinese_for_tear_down(self):
        output = _render(savingOperationType="TEAR_DOWN_IN_RESOURCE")
        text = self._get_non_json_output(output)
        chinese_chars = [c for c in text if "\u4e00" <= c <= "\u9fff"]
        assert chinese_chars == [], f"Chinese characters found: {chinese_chars!r}"

    def test_no_chinese_for_change_pay_type(self):
        output = _render(savingOperationType="CHANGE_PAY_TYPE")
        text = self._get_non_json_output(output)
        chinese_chars = [c for c in text if "\u4e00" <= c <= "\u9fff"]
        assert chinese_chars == []


# ---------------------------------------------------------------------------
# Contribution percentage in output
# ---------------------------------------------------------------------------


class TestContributionPercentage:
    def test_contribution_percentage_shown_in_saving_line(self):
        violation = _make_violation(monthlySaving=100.0)
        saving_summary = {"optimizableAmount": 500.0}
        payload = build_analysis_payload(violation=violation, saving_summary=saving_summary)
        output = render_analysis(payload)
        assert "20.0% of total optimizable" in output

    def test_no_contribution_when_no_summary(self):
        output = _render()
        assert "of total optimizable" not in output
