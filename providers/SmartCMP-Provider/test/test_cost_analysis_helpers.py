from __future__ import annotations

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

import _analysis as analysis  # noqa: E402


def test_normalize_analysis_facts_combines_violation_and_policy_fields():
    facts = analysis.normalize_analysis_facts(
        {
            "id": "vio-1",
            "policyId": "pol-1",
            "policyName": "Idle VM",
            "resourceId": "res-1",
            "resourceName": "vm-prod-01",
            "status": "OPEN",
            "severity": "HIGH",
            "category": "COST",
            "monthlyCost": 120.0,
            "monthlySaving": 80.0,
            "savingOperationType": "STOP_IDLE",
            "fixType": "DAY2",
            "taskDefinition": {"name": "Stop VM"},
        },
        {
            "id": "pol-1",
            "name": "Idle VM",
            "description": "Stop low-utilization VM",
            "remedie": "Stop the instance",
        },
    )

    assert facts["violationId"] == "vio-1"
    assert facts["policyId"] == "pol-1"
    assert facts["resourceName"] == "vm-prod-01"
    assert facts["taskDefinitionPresent"] is True
    assert facts["policyDescription"] == "Stop low-utilization VM"
    assert facts["remedie"] == "Stop the instance"


def test_classify_optimization_theme_maps_stable_values():
    assert analysis.classify_optimization_theme("RIGHTSIZE") == "rightsizing"
    assert analysis.classify_optimization_theme("STOP_IDLE") == "idle_shutdown"
    assert analysis.classify_optimization_theme("DELETE_UNUSED") == "orphan_cleanup"
    assert analysis.classify_optimization_theme("STORAGE_TIER") == "storage_optimization"


def test_determine_execution_readiness_distinguishes_ready_manual_and_skip():
    assert analysis.determine_execution_readiness({"monthlySaving": 0, "status": "OPEN"}) == "skip"
    assert (
        analysis.determine_execution_readiness(
            {"monthlySaving": 10, "status": "OPEN", "fixType": "DAY2"}
        )
        == "ready"
    )
    assert (
        analysis.determine_execution_readiness({"monthlySaving": 10, "status": "OPEN"})
        == "manual_review"
    )


def test_build_recommendations_always_returns_required_fields():
    recommendations = analysis.build_recommendations(
        {
            "policyName": "Idle VM",
            "monthlySaving": 80.0,
            "savingOperationType": "STOP_IDLE",
            "fixType": "DAY2",
            "taskDefinitionPresent": True,
            "remedie": "Stop the instance",
            "status": "OPEN",
        }
    )

    assert len(recommendations) == 1
    recommendation = recommendations[0]
    assert recommendation["action"] == "execute_fix"
    assert recommendation["confidence"] == "high"
    assert recommendation["platformExecutable"] is True
    assert recommendation["reason"]
    assert recommendation["evidence"]
    assert recommendation["bestPractice"]
