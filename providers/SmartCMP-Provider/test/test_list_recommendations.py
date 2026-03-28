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

import list_recommendations as listing  # noqa: E402


def test_render_output_formats_summary_and_meta_block():
    items = [
        {
            "id": "vio-1",
            "policyId": "pol-1",
            "policyName": "Idle VM",
            "resourceId": "res-1",
            "resourceName": "vm-prod-01",
            "status": "OPEN",
            "severity": "HIGH",
            "category": "COST",
            "monthlyCost": "120.5",
            "monthlySaving": "80.25",
            "savingOperationType": "STOP_IDLE",
            "fixType": "DAY2",
            "taskInstanceId": "task-1",
            "lastExecuteDate": 1_710_000_000_000,
        }
    ]

    output = listing.render_output(items)

    assert "Found 1 cost optimization recommendation(s):" in output
    assert "[1] | vm-prod-01 | Idle VM | OPEN | STOP_IDLE | saving=80.25" in output
    assert "##COST_RECOMMENDATION_META_START##" in output
    assert "##COST_RECOMMENDATION_META_END##" in output

    meta_text = output.split("##COST_RECOMMENDATION_META_START##\n", 1)[1].split(
        "\n##COST_RECOMMENDATION_META_END##",
        1,
    )[0]
    meta = json.loads(meta_text)
    assert meta == [
        {
            "index": 1,
            "violationId": "vio-1",
            "policyId": "pol-1",
            "policyName": "Idle VM",
            "resourceId": "res-1",
            "resourceName": "vm-prod-01",
            "status": "OPEN",
            "severity": "HIGH",
            "category": "COST",
            "monthlyCost": 120.5,
            "monthlySaving": 80.25,
            "savingOperationType": "STOP_IDLE",
            "fixType": "DAY2",
            "taskInstanceId": "task-1",
            "lastExecuteDate": "2024-03-09T16:00:00Z",
            "taskDefinitionId": "",
            "taskDefinitionName": "",
        }
    ]


def test_render_output_handles_empty_list():
    output = listing.render_output([])

    assert "No cost optimization recommendations found." in output
    meta_text = output.split("##COST_RECOMMENDATION_META_START##\n", 1)[1].split(
        "\n##COST_RECOMMENDATION_META_END##",
        1,
    )[0]
    assert json.loads(meta_text) == []
