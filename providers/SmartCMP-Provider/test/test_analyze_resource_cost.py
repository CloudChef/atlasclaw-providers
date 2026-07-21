# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Tests for read-only resource-first cost optimization evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "skills" / "cost-optimization" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import analyze_resource_cost as analyzer  # noqa: E402
from _resource_cost_analysis import (  # noqa: E402
    build_analysis_payload,
    build_financial_evidence,
    build_platform_assessment,
    build_policy_coverages,
    build_resource_projection,
    match_policy_scope,
    match_resource_type,
    project_execution_extra,
    project_violation,
    render_output,
)


RESOURCE_ID = "6c6eb87b-b763-45b7-a193-f0c12d8cae88"


def _resource_record(**resource_overrides):
    resource = {
        "id": RESOURCE_ID,
        "name": "rds-prod-01",
        "resourceType": "resource.paas.rds.aws",
        "componentType": "resource.paas.rds.aws",
        "status": "lost",
        "cloudEntryId": "entry-1",
        "regionId": "cn-north-1",
        "zoneId": "cn-north-1b",
        "monitorEnabled": True,
        "monitorSourceType": "hypervisor",
        "monitorResourceType": "resource.agent.monitoring_agent.prometheus_exporter.aws_exporter",
        "payType": "PayAsYouGo",
        "exts": {
            "customProperty": {
                "status": "available",
                "cloud_entry_type": "yacmp:cloudentry:type:aws",
                "engine": "mysql",
                "engine_version": "8.0.42",
                "instance_type": "db.t3.micro",
                "storage_type": "gp2",
                "size": 100,
                "backup_retention": 0,
                "password": "must-not-leak",
            }
        },
        "secretAccessKey": "must-not-leak",
    }
    resource.update(resource_overrides)
    return {
        "resourceId": RESOURCE_ID,
        "data": resource,
        "resource": resource,
        "summary": {},
        "normalized": {
            "type": "resource.paas.rds.aws",
            "properties": {
                "currentBilling": "88.50",
                "credential_user": "must-not-leak",
            },
        },
        "fetchStatus": "ok",
        "errors": [],
    }


def _coverage(*, status=None, extra=None, applicable=True, last_execution_id="exec-1"):
    execution = None
    if status is not None:
        execution = {"status": status, "extra": extra or {}}
    return {
        "policyId": "policy-1",
        "policyName": "Idle RDS",
        "scopeStatus": "matched" if applicable else "excluded",
        "applicable": applicable,
        "lastExecutionId": last_execution_id,
        "lastExecuteStatus": "FINISHED",
        "resourceExecution": execution,
    }


def test_resource_projection_keeps_cost_fields_and_excludes_credentials():
    projected = build_resource_projection(_resource_record())

    assert projected["name"] == "rds-prod-01"
    assert projected["componentType"] == "resource.paas.rds.aws"
    assert projected["status"] == "lost"
    assert projected["providerStatus"] == "available"
    assert projected["cloudEntryType"] == "yacmp:cloudentry:type:aws"
    assert projected["costAttributes"] == {
        "payType": "PayAsYouGo",
        "currentBilling": "88.50",
        "instance_type": "db.t3.micro",
        "size": 100,
        "storage_type": "gp2",
        "engine": "mysql",
        "engine_version": "8.0.42",
        "backup_retention": 0,
    }
    rendered = json.dumps(projected)
    assert "must-not-leak" not in rendered
    assert "password" not in rendered
    assert "credential_user" not in rendered


@pytest.mark.parametrize(
    ("resource_types", "policy_types", "expected"),
    [
        (["resource.paas.rds.aws"], ["resource.paas.rds.aws"], "exact"),
        (["resource.iaas.machine.instance.vsphere"], ["resource.iaas.machine"], "ancestor"),
        (["resource.paas.rds.aws"], ["resource.iaas.machine"], ""),
        (["resource.paas.rdsx"], ["resource.paas.rds"], ""),
    ],
)
def test_resource_type_matching_observes_dot_boundaries(resource_types, policy_types, expected):
    assert match_resource_type(resource_types, policy_types) == expected


def test_policy_scope_supports_all_cloud_entries_and_resource_ids():
    assert match_policy_scope(
        {"cloudEntryTypes": ["-1"], "resourceIds": [RESOURCE_ID]},
        resource_id=RESOURCE_ID,
        cloud_entry_type="yacmp:cloudentry:type:aws",
    )[0] == "matched"
    assert match_policy_scope(
        {"resourceIds": ["another-resource"]},
        resource_id=RESOURCE_ID,
        cloud_entry_type="yacmp:cloudentry:type:aws",
    )[0] == "excluded"
    assert match_policy_scope(
        {"businessGroupIds": ["bg-1"]},
        resource_id=RESOURCE_ID,
        cloud_entry_type="yacmp:cloudentry:type:aws",
    )[0] == "scope_unknown"


def test_policy_coverage_uses_only_enabled_type_matches_and_preserves_scope_state():
    resource = build_resource_projection(_resource_record())
    policies = [
        {
            "id": "policy-exact",
            "name": "Idle AWS RDS",
            "resourceType": ["resource.paas.rds.aws"],
            "ruleContent": "return true;",
            "policyConfigs": [
                {"id": "cfg-1", "enabled": True, "scope": {"cloudEntryTypes": ["-1"]}},
                {"id": "cfg-2", "enabled": False, "scope": {"cloudEntryTypes": ["-1"]}},
            ],
        },
        {
            "id": "policy-parent",
            "name": "Generic RDS",
            "resourceType": ["resource.paas.rds"],
            "policyConfigs": [
                {"id": "cfg-3", "enabled": True, "scope": {"resourceIds": ["other"]}},
            ],
        },
        {
            "id": "policy-vm",
            "name": "VM",
            "resourceType": ["resource.iaas.machine"],
            "policyConfigs": [{"id": "cfg-4", "enabled": True, "scope": {}}],
        },
    ]

    coverage = build_policy_coverages(policies, resource=resource, resource_id=RESOURCE_ID)

    assert [(item["policyId"], item["typeMatch"], item["scopeStatus"]) for item in coverage] == [
        ("policy-exact", "exact", "matched"),
        ("policy-parent", "ancestor", "excluded"),
    ]


def test_platform_assessment_prioritizes_active_violation():
    violation = project_violation(
        {
            "id": "violation-1",
            "policyId": "policy-1",
            "status": "ACTIVED",
            "monthlySaving": "20.50",
        }
    )

    assessment = build_platform_assessment([_coverage()], [violation])

    assert assessment["platformStatus"] == "platform_detected"
    assert assessment["evidenceCompleteness"] == "platform_confirmed"


@pytest.mark.parametrize(
    ("coverages", "expected"),
    [
        ([], "not_covered"),
        ([_coverage(status=None)], "covered_not_evaluated"),
        ([_coverage(status="FAILED")], "execution_failed"),
        ([_coverage(status="COMPLIANCE")], "insufficient_evidence"),
        (
            [_coverage(status="COMPLIANCE", extra={"evidenceComplete": True})],
            "evaluated_clear",
        ),
    ],
)
def test_platform_assessment_distinguishes_execution_evidence(coverages, expected):
    assert build_platform_assessment(coverages, [])["platformStatus"] == expected


def test_financial_evidence_keeps_platform_amounts_without_summing():
    resource = build_resource_projection(_resource_record())
    violations = [
        project_violation(
            {
                "id": "violation-1",
                "policyId": "policy-1",
                "monthlyCost": "100",
                "monthlySaving": "25.25",
            }
        ),
        project_violation(
            {
                "id": "violation-2",
                "policyId": "policy-2",
                "monthlySaving": None,
            }
        ),
    ]

    evidence = build_financial_evidence(resource, violations, currency="¥")

    assert evidence["resourceCurrentBilling"] == 88.5
    assert evidence["violationEstimates"] == [
        {
            "violationId": "violation-1",
            "policyId": "policy-1",
            "monthlyCost": 100.0,
            "monthlySaving": 25.25,
            "source": "smartcmp_violation",
        }
    ]
    assert "total" not in evidence


def test_financial_evidence_does_not_invent_missing_amounts():
    resource = build_resource_projection(_resource_record(currentBilling=None))
    resource["costAttributes"].pop("currentBilling", None)

    evidence = build_financial_evidence(resource, [], currency="¥")

    assert evidence["resourceCurrentBilling"] is None
    assert evidence["violationEstimates"] == []
    assert evidence["hasExactSavingEvidence"] is False


def test_resource_resolution_supports_index_name_and_internal_id():
    directory = [{"index": 7, "id": RESOURCE_ID, "name": "rds-prod-01"}]

    assert analyzer.resolve_resource_target(
        resource_id="",
        resource_name="rds-prod-01",
        resource_index=7,
        directory_items=directory,
        base_url="https://cmp.example/platform-api",
        headers={},
    ) == (RESOURCE_ID, "rds-prod-01")
    assert analyzer.resolve_resource_target(
        resource_id=RESOURCE_ID,
        resource_name="",
        resource_index=None,
        directory_items=[],
        base_url="https://cmp.example/platform-api",
        headers={},
    ) == (RESOURCE_ID, "")


def test_resource_resolution_rejects_duplicate_directory_names():
    directory = [
        {"index": 1, "id": "resource-1", "name": "duplicate"},
        {"index": 2, "id": "resource-2", "name": "duplicate"},
    ]

    with pytest.raises(analyzer.ResourceResolutionError, match="Multiple listed resources"):
        analyzer.resolve_resource_target(
            resource_id="",
            resource_name="duplicate",
            resource_index=None,
            directory_items=directory,
            base_url="https://cmp.example/platform-api",
            headers={},
        )


def test_resource_resolution_reports_no_api_name_match(monkeypatch):
    class Response:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"content": [], "last": True, "totalPages": 1}

    monkeypatch.setattr(analyzer.requests, "get", lambda *args, **kwargs: Response())

    with pytest.raises(analyzer.ResourceResolutionError, match="No SmartCMP resource exactly matched"):
        analyzer.resolve_resource_target(
            resource_id="",
            resource_name="missing-resource",
            resource_index=None,
            directory_items=[],
            base_url="https://cmp.example/platform-api",
            headers={},
        )


def test_resource_resolution_uses_case_insensitive_unique_api_match(monkeypatch):
    class Response:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {
                "content": [{"id": RESOURCE_ID, "name": "RDS-Prod-01"}],
                "last": True,
                "totalPages": 1,
            }

    monkeypatch.setattr(analyzer.requests, "get", lambda *args, **kwargs: Response())

    assert analyzer.resolve_resource_target(
        resource_id="",
        resource_name="rds-prod-01",
        resource_index=None,
        directory_items=[],
        base_url="https://cmp.example/platform-api",
        headers={},
    ) == (RESOURCE_ID, "RDS-Prod-01")


def test_resource_resolution_rejects_conflicting_visible_name_and_internal_id(monkeypatch):
    class Response:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {
                "content": [{"id": "different-resource", "name": "rds-prod-01"}],
                "last": True,
                "totalPages": 1,
            }

    monkeypatch.setattr(analyzer.requests, "get", lambda *args, **kwargs: Response())

    with pytest.raises(analyzer.ResourceResolutionError, match="does not match"):
        analyzer.resolve_resource_target(
            resource_id=RESOURCE_ID,
            resource_name="rds-prod-01",
            resource_index=None,
            directory_items=[],
            base_url="https://cmp.example/platform-api",
            headers={},
        )


def test_execution_enrichment_requires_exact_execution_id_and_stable_filters(monkeypatch):
    calls = []

    def fake_fetch(url, *, headers, params=None):
        calls.append({"url": url, "params": params})
        return [
            {
                "executionId": "stale-execution",
                "resourceId": RESOURCE_ID,
                "policyId": "policy-1",
                "status": "COMPLIANCE",
                "extra": {"evidenceComplete": True},
            },
            {
                "executionId": "exec-1",
                "resourceId": RESOURCE_ID,
                "policyId": "policy-1",
                "status": "FAILED",
                "extra": {},
            },
        ]

    monkeypatch.setattr(analyzer, "_fetch_paginated", fake_fetch)
    coverages = [_coverage(status=None)]

    errors = analyzer.enrich_resource_executions(
        coverages,
        base_url="https://cmp.example/platform-api",
        headers={},
        resource_id=RESOURCE_ID,
    )

    assert errors == []
    assert coverages[0]["resourceExecution"]["executionId"] == "exec-1"
    assert coverages[0]["resourceExecution"]["status"] == "FAILED"
    assert calls[0]["params"] == {"executionId": "exec-1"}


def test_active_violation_lookup_uses_stable_resource_id_without_name_filter(monkeypatch):
    captured = {}

    def fake_fetch(url, *, headers, params=None):
        captured.update(params or {})
        return [{"resourceId": RESOURCE_ID}, {"resourceId": "different-resource"}]

    monkeypatch.setattr(analyzer, "_fetch_paginated", fake_fetch)

    violations = analyzer.fetch_active_violations(
        base_url="https://cmp.example/platform-api",
        headers={},
        resource_id=RESOURCE_ID,
    )

    assert violations == [{"resourceId": RESOURCE_ID}]
    assert captured["resourceId"] == RESOURCE_ID
    assert "queryValue" not in captured


def test_execution_evidence_is_bounded_and_redacts_sensitive_keys():
    projected = project_execution_extra(
        {
            "evidenceComplete": True,
            "metrics": {
                "password": "must-not-leak",
                "nested": {"access_token": "must-not-leak"},
                "samples": ["x" * 2_000 for _ in range(100)],
            },
        }
    )

    rendered = json.dumps(projected)
    assert projected["evidenceComplete"] is True
    assert projected["redactionApplied"] is True
    assert projected["evidenceTruncated"] is True
    assert "must-not-leak" not in rendered
    assert len(rendered) < 9_000


def test_currency_lookup_failure_returns_no_guessed_currency(monkeypatch):
    class Response:
        @staticmethod
        def raise_for_status():
            raise analyzer.requests.HTTPError("unavailable")

    monkeypatch.setattr(analyzer.requests, "get", lambda *args, **kwargs: Response())

    currency, code, source, error = analyzer.fetch_currency_evidence(
        "https://cmp.example/platform-api",
        {},
    )

    assert currency is None
    assert code == ""
    assert source == ""
    assert error == "SmartCMP tenant currency evidence is unavailable."


def test_missing_currency_is_reported_as_evidence_gap():
    resource = build_resource_projection(_resource_record())

    payload = build_analysis_payload(
        resource_id=RESOURCE_ID,
        resource=resource,
        policy_coverages=[],
        active_violations=[],
        currency=None,
    )

    assert payload["financialEvidence"]["currency"] is None
    assert "financial.currency" in payload["missingEvidence"]


def test_vm_open_action_uses_virtual_machine_route():
    actions = analyzer._build_resource_actions(
        "https://cmp.example/platform-api",
        RESOURCE_ID,
        {"componentType": "resource.iaas.machine.instance.vsphere"},
    )

    assert len(actions) == 1
    assert "/virtual-machines/" in actions[0]["href"]

    alias_actions = analyzer._build_resource_actions(
        "https://cmp.example/platform-api",
        RESOURCE_ID,
        {"resourceType": "virtualMachine"},
    )
    assert "/virtual-machines/" in alias_actions[0]["href"]


def test_render_output_hides_internal_id_from_human_summary_and_exposes_contract():
    resource = build_resource_projection(_resource_record())
    payload = build_analysis_payload(
        resource_id=RESOURCE_ID,
        resource=resource,
        policy_coverages=[_coverage(status="COMPLIANCE")],
        active_violations=[],
        currency="¥",
    )

    output = render_output(payload)
    human_text = output.split("##RESOURCE_COST_ANALYSIS_START##", 1)[0]
    context_text = output.split("##RESOURCE_COST_ANALYSIS_START##\n", 1)[1].split(
        "\n##RESOURCE_COST_ANALYSIS_END##",
        1,
    )[0]
    context = json.loads(context_text)

    assert RESOURCE_ID not in human_text
    assert context["object_id"] == RESOURCE_ID
    assert context["platformAssessment"]["platformStatus"] == "insufficient_evidence"
    assert "potentialOpportunities" in context["analysisContract"]["requiredOutput"]
    assert "resource.inventoryStateConsistency" in context["missingEvidence"]
    contract_rules = " ".join(context["analysisContract"]["rules"])
    assert "violationEstimates[].monthlySaving" in contract_rules
    assert "read-only validation only" in contract_rules
