# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    REPO_ROOT
    / "providers"
    / "SmartCMP-Provider"
    / "skills"
    / "resource-compliance"
    / "scripts"
    / "analyze_resource.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("test_analyze_resource_module", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def extract_payload(output: str) -> dict:
    match = re.search(
        r"##RESOURCE_COMPLIANCE_START##\s*(.*?)\s*##RESOURCE_COMPLIANCE_END##",
        output,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def make_directory_meta() -> list[dict]:
    return [
        {
            "index": 1,
            "id": "res-hidden-1",
            "name": "vm-01",
            "scope": "virtual_machines",
            "resourceType": "cloudchef.nodes.Compute",
            "componentType": "iaas.machine.virtual_machine",
            "status": "started",
        },
        {
            "index": 2,
            "id": "res-hidden-2",
            "name": "custom-resource-01",
            "scope": "resources",
            "resourceType": "cloudchef.nodes.Resource",
            "componentType": "resource.unknown.custom",
            "status": "unknown",
        },
    ]


def make_resource_record(
    resource_id: str,
    name: str,
    *,
    component_type: str = "iaas.machine.virtual_machine",
    status: str = "started",
    properties: dict | None = None,
) -> dict:
    normalized_properties = {
        "name": name,
        "componentType": component_type,
        "resourceType": "cloudchef.nodes.Resource",
        "status": status,
        "osDescription": "Ubuntu 22.04 LTS",
        "monitorEnabled": True,
    }
    normalized_properties.update(properties or {})
    resource = {
        "id": resource_id,
        "name": name,
        "resourceType": "cloudchef.nodes.Resource",
        "componentType": component_type,
        "status": status,
        "properties": dict(properties or {}),
    }
    return {
        "resourceId": resource_id,
        "summary": {},
        "data": resource,
        "resource": resource,
        "details": {},
        "normalized": {
            "type": component_type,
            "properties": normalized_properties,
        },
        "fetchStatus": "ok",
        "missingEvidence": [],
        "errors": [],
        "fallbackUsed": False,
    }


def run_main(module, args: list[str]) -> tuple[int, str, dict]:
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(args)
    output = stdout.getvalue()
    return exit_code, output, extract_payload(output) if exit_code == 0 else {}


def test_main_returns_clean_error_when_no_resource_target():
    module = load_module()

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main([])

    output = stdout.getvalue()
    assert exit_code == 1
    assert "Provide an exact resource name" in output
    assert "Traceback" not in output


def test_main_resolves_name_and_emits_generic_evidence(monkeypatch):
    module = load_module()
    captured = {}

    def fake_load_resources(ids):
        captured["ids"] = ids
        return [make_resource_record("res-hidden-2", "custom-resource-01", component_type="resource.unknown.custom")]

    monkeypatch.setattr(module, "load_resources", fake_load_resources)
    exit_code, output, payload = run_main(
        module,
        [
            "--resource-name",
            "custom-resource-01",
            "--resource-directory-json",
            json.dumps(make_directory_meta()),
        ],
    )

    assert exit_code == 0
    assert captured["ids"] == ["res-hidden-2"]
    assert payload["requestedResources"] == [
        {"name": "custom-resource-01", "index": None, "source": "resource_directory"}
    ]
    result = payload["results"][0]
    assert result["analysisTargets"] == ["llm:generic_cloud_resource"]
    assert result["analysisStatus"] == "evidence_collected"
    assert result["resourceProfile"]["identity"]["componentType"] == "resource.unknown.custom"
    assert result["object_id"] == "res-hidden-2"
    assert result["object_name"] == "custom-resource-01"
    assert "| # | Resource | Type | CMP Status | Evidence |" in output
    assert "No analyzer route matched" not in output


def test_main_resolves_resource_index_from_directory_metadata(monkeypatch):
    module = load_module()
    captured = {}

    def fake_load_resources(ids):
        captured["ids"] = ids
        return [make_resource_record("res-hidden-2", "custom-resource-01")]

    monkeypatch.setattr(module, "load_resources", fake_load_resources)
    exit_code, _output, payload = run_main(
        module,
        [
            "--resource-index",
            "2",
            "--resource-directory-json",
            json.dumps(make_directory_meta()),
        ],
    )

    assert exit_code == 0
    assert captured["ids"] == ["res-hidden-2"]
    assert payload["requestedResources"][0]["index"] == 2
    assert payload["resolvedResources"][0]["name"] == "custom-resource-01"


def test_main_rejects_index_name_mismatch_without_printing_resource_id():
    module = load_module()
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(
            [
                "--resource-index",
                "2",
                "--resource-name",
                "vm-01",
                "--resource-directory-json",
                json.dumps(make_directory_meta()),
            ]
        )

    output = stdout.getvalue()
    assert exit_code == 1
    assert "Index 2 is 'custom-resource-01'" in output
    assert "vm-01" in output
    assert "res-hidden-2" not in output


def test_main_direct_name_lookup_rejects_ambiguous_exact_matches(monkeypatch):
    module = load_module()
    monkeypatch.setattr(
        module,
        "require_config",
        lambda: ("https://cmp.example.com/platform-api", "", {"Auth": "token"}, {}),
    )
    monkeypatch.setattr(
        module,
        "search_resource_summaries",
        lambda **_kwargs: [
            {"id": "res-hidden-1", "name": "duplicate-vm", "status": "started"},
            {"id": "res-hidden-2", "name": "duplicate-vm", "status": "stopped"},
        ],
    )

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["--resource-name", "duplicate-vm"])

    output = stdout.getvalue()
    assert exit_code == 1
    assert "Multiple SmartCMP resources exactly matched name 'duplicate-vm'" in output
    assert "res-hidden" not in output


def test_internal_id_compatibility_is_structured_but_not_in_human_summary(monkeypatch):
    module = load_module()
    internal_id = "123e4567-e89b-42d3-a456-426614174000"
    monkeypatch.setattr(
        module,
        "load_resources",
        lambda _ids: [make_resource_record(internal_id, "vm-01")],
    )

    exit_code, output, payload = run_main(module, ["--resource-ids", internal_id])
    human_summary = output.split("##RESOURCE_COMPLIANCE_START##", 1)[0]

    assert exit_code == 0
    assert payload["requestedResourceIds"] == [internal_id]
    assert payload["results"][0]["object_id"] == internal_id
    assert internal_id not in human_summary
    assert internal_id not in json.dumps(payload["results"][0]["resourceProfile"])


def test_main_accepts_webhook_payload_and_keeps_same_generic_contract(monkeypatch):
    module = load_module()
    monkeypatch.setattr(
        module,
        "load_resources",
        lambda _ids: [make_resource_record("res-1", "hardware-01", component_type="resource.hardware.server")],
    )

    exit_code, _output, payload = run_main(
        module,
        [
            "--payload-json",
            json.dumps(
                {
                    "resourceIds": ["res-1"],
                    "triggerSource": "webhook",
                    "rawMetadata": {"event": "manual-validation"},
                }
            ),
        ],
    )

    assert exit_code == 0
    assert payload["triggerSource"] == "webhook"
    assert payload["results"][0]["analysisTargets"] == ["llm:generic_cloud_resource"]
    assert payload["results"][0]["type"] == "resource.hardware.server"


def test_fetch_failure_emits_partial_context_and_needs_llm_review(monkeypatch):
    module = load_module()
    monkeypatch.setattr(
        module,
        "load_resources",
        lambda _ids: [
            make_resource_record("res-1", "vm-01"),
            {
                "resourceId": "res-missing",
                "summary": {"componentType": "resource.software.db.mysql"},
                "data": {},
                "resource": {},
                "details": {},
                "normalized": {"type": "resource.software.db.mysql", "properties": {}},
                "fetchStatus": "error",
                "missingEvidence": ["resource.data"],
                "errors": ["Resource view data was not returned."],
            },
        ],
    )

    exit_code, _output, payload = run_main(module, ["res-1", "res-missing"])
    failed = payload["results"][1]

    assert exit_code == 0
    assert payload["analyzedCount"] == 1
    assert payload["failedCount"] == 1
    assert failed["analysisStatus"] == "fetch_failed"
    assert failed["analysisTargets"] == ["llm:generic_cloud_resource"]
    assert "resource.data" in failed["missingEvidence"]
    assert failed["errors"] == ["Resource view data was not returned."]


def test_legacy_record_keeps_runtime_facts_without_product_routing(monkeypatch):
    module = load_module()
    record = {
        "resourceId": "res-legacy",
        "summary": {},
        "resource": {
            "name": "mysql-legacy",
            "resourceType": "cloudchef.nodes.Compute",
            "componentType": "resource.software.rds.mysql_32",
            "status": "started",
            "extensibleProperties": {"RuntimeProperties": {"version1": "5.7"}},
        },
        "details": {"hostname": "mysql-legacy"},
        "fetchStatus": "ok",
        "missingEvidence": [],
        "errors": [],
        "fallbackUsed": True,
    }
    monkeypatch.setattr(module, "load_resources", lambda _ids: [record])

    exit_code, _output, payload = run_main(module, ["res-legacy"])
    result = payload["results"][0]

    assert exit_code == 0
    assert result["analysisTargets"] == ["llm:generic_cloud_resource"]
    assert result["resourceProfile"]["attributes"]["version1"] == "5.7"
    assert result["evidenceCoverage"]["fallbackUsed"] is True
    assert "patchAssessment" not in result


def test_entrypoint_has_no_external_or_product_specific_evidence_clients():
    module = load_module()

    assert not hasattr(module, "external_checker")
    assert not hasattr(module, "OfficialSourceClient")
    assert not hasattr(module, "analyze_aws_rds_mysql_patch")
