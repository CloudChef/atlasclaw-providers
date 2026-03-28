from __future__ import annotations

import json
import sys
from pathlib import Path


SCRIPT_DIR = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "cost-optimization"
    / "scripts"
)
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import analyze_recommendation as analyzer  # noqa: E402


def test_build_analysis_payload_contains_required_sections():
    payload = analyzer.build_analysis_payload(
        violation={
            "id": "vio-1",
            "policyId": "pol-1",
            "policyName": "Idle VM",
            "resourceName": "vm-prod-01",
            "status": "OPEN",
            "monthlySaving": "80.25",
            "monthlyCost": "120.50",
            "savingOperationType": "STOP_IDLE",
            "fixType": "DAY2",
            "taskDefinition": {"name": "Stop VM"},
        },
        policy={
            "id": "pol-1",
            "name": "Idle VM",
            "description": "Stop low-utilization VM",
            "remedie": "Stop the instance",
        },
        saving_summary={"optimizableAmount": 1000},
        operation_summary={"STOP_IDLE": 12},
    )

    assert payload["violationId"] == "vio-1"
    assert set(payload) == {"violationId", "facts", "assessment", "recommendations", "suggestedNextStep"}
    assert payload["facts"]["policyName"] == "Idle VM"
    assert payload["facts"]["monthlySaving"] == 80.25
    assert payload["assessment"]["optimizationTheme"] == "idle_shutdown"
    assert payload["assessment"]["executionReadiness"] == "ready"
    assert payload["assessment"]["savingSummaryAvailable"] is True
    assert payload["assessment"]["operationSummaryAvailable"] is True
    assert payload["suggestedNextStep"] == "execute_fix"


def test_render_analysis_outputs_human_summary_and_structured_block():
    payload = {
        "violationId": "vio-1",
        "facts": {
            "resourceName": "vm-prod-01",
            "monthlySaving": 80.25,
        },
        "assessment": {
            "optimizationTheme": "idle_shutdown",
            "executionReadiness": "ready",
        },
        "recommendations": [],
        "suggestedNextStep": "manual_review",
    }

    output = analyzer.render_analysis(payload)

    assert "Violation vio-1: ready" in output
    assert "Theme: idle_shutdown" in output
    assert "Resource: vm-prod-01" in output
    assert "Estimated monthly saving: 80.25" in output
    assert "##COST_ANALYSIS_START##" in output
    assert "##COST_ANALYSIS_END##" in output

    meta_text = output.split("##COST_ANALYSIS_START##\n", 1)[1].split(
        "\n##COST_ANALYSIS_END##",
        1,
    )[0]
    assert json.loads(meta_text) == payload
