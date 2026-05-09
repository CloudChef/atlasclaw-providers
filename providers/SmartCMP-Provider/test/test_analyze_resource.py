# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

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


def extract_payload(output: str):
    match = re.search(
        r"##RESOURCE_COMPLIANCE_START##\s*(.*?)\s*##RESOURCE_COMPLIANCE_END##",
        output,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def make_directory_meta():
    return [
        {
            "index": 1,
            "id": "res-hidden-1",
            "name": "test-linux-vm-20260506",
            "scope": "virtual_machines",
            "resourceType": "cloudchef.nodes.Compute",
            "componentType": "iaas.machine.virtual_machine",
            "status": "started",
            "os": "Linux",
        },
        {
            "index": 2,
            "id": "res-hidden-2",
            "name": "e2e-newrole-linux3-0501",
            "scope": "virtual_machines",
            "resourceType": "cloudchef.nodes.Compute",
            "componentType": "iaas.machine.virtual_machine",
            "status": "started",
            "os": "Linux",
        },
    ]


def make_resource_record(resource_id: str, name: str, *, os_description: str, softwares: str = ""):
    is_linux = "Ubuntu" in os_description
    return {
        "resourceId": resource_id,
        "summary": {
            "id": resource_id,
            "name": name,
            "resourceType": "cloudchef.nodes.Compute",
            "componentType": "resource.software.app.tomcat" if softwares else ("resource.os.linux" if is_linux else "resource.os.windows"),
            "status": "started",
            "osType": "LINUX" if is_linux else "WINDOWS",
            "osDescription": os_description,
        },
        "resource": {
            "id": resource_id,
            "name": name,
            "resourceType": "cloudchef.nodes.Compute",
            "componentType": "resource.software.app.tomcat" if softwares else ("resource.os.linux" if is_linux else "resource.os.windows"),
            "status": "started",
            "osType": "LINUX" if is_linux else "WINDOWS",
            "osDescription": os_description,
            "softwares": softwares,
        },
        "details": {},
        "normalized": {
            "type": "resource.software.app.tomcat" if softwares else ("resource.os.linux" if is_linux else "resource.os.windows"),
            "properties": {
                "osType": "LINUX" if is_linux else "WINDOWS",
                "osDescription": os_description,
                "softwareVersion": "9.0.0.M10" if softwares else "",
                "softwares": softwares,
            },
        },
        "fetchStatus": "ok",
        "errors": [],
    }


def test_main_resolves_resource_name_from_directory_metadata(monkeypatch):
    module = load_module()
    captured = {}

    def fake_load_resources(ids):
        captured["ids"] = ids
        return [
            make_resource_record(
                "res-hidden-2",
                "e2e-newrole-linux3-0501",
                os_description="Ubuntu 22.04.3 LTS",
            )
        ]

    monkeypatch.setattr(module, "load_resources", fake_load_resources)
    monkeypatch.setattr(
        module,
        "external_checker",
        lambda product, version: {
            "status": "supported",
            "summary": f"{product} {version} is supported.",
            "links": [],
            "checkedAt": "2026-04-03T00:00:00Z",
        },
    )

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(
            [
                "--resource-name",
                "e2e-newrole-linux3-0501",
                "--resource-directory-json",
                json.dumps(make_directory_meta()),
            ]
        )

    output = stdout.getvalue()
    payload = extract_payload(output)

    assert exit_code == 0
    assert captured["ids"] == ["res-hidden-2"]
    assert "[1] e2e-newrole-linux3-0501 | compliant | confidence=high" in output
    assert payload["requestedResources"] == [
        {
            "name": "e2e-newrole-linux3-0501",
            "index": None,
            "source": "resource_directory",
        }
    ]
    assert payload["resolvedResources"][0]["name"] == "e2e-newrole-linux3-0501"
    assert payload["requestedResourceIds"] == ["res-hidden-2"]


def test_main_resolves_resource_index_from_directory_metadata(monkeypatch):
    module = load_module()
    captured = {}

    def fake_load_resources(ids):
        captured["ids"] = ids
        return [
            make_resource_record(
                "res-hidden-2",
                "e2e-newrole-linux3-0501",
                os_description="Ubuntu 22.04.3 LTS",
            )
        ]

    monkeypatch.setattr(module, "load_resources", fake_load_resources)
    monkeypatch.setattr(
        module,
        "external_checker",
        lambda product, version: {
            "status": "supported",
            "summary": "supported",
            "links": [],
            "checkedAt": "2026-04-03T00:00:00Z",
        },
    )

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(
            [
                "--resource-index",
                "2",
                "--resource-directory-json",
                json.dumps(make_directory_meta()),
            ]
        )

    payload = extract_payload(stdout.getvalue())

    assert exit_code == 0
    assert captured["ids"] == ["res-hidden-2"]
    assert payload["requestedResources"][0]["index"] == 2
    assert payload["resolvedResources"][0]["name"] == "e2e-newrole-linux3-0501"


def test_main_rejects_index_name_mismatch_without_printing_resource_id(monkeypatch):
    module = load_module()

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(
            [
                "--resource-index",
                "2",
                "--resource-name",
                "test-linux-vm-20260506",
                "--resource-directory-json",
                json.dumps(make_directory_meta()),
            ]
        )

    output = stdout.getvalue()

    assert exit_code == 1
    assert "Index 2 is 'e2e-newrole-linux3-0501'" in output
    assert "test-linux-vm-20260506" in output
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
    assert "[1] duplicate-vm | status: started" in output
    assert "[2] duplicate-vm | status: stopped" in output
    assert "res-hidden" not in output


def test_main_accepts_resource_ids_flag_for_compatibility(monkeypatch):
    module = load_module()
    captured = {}

    def fake_load_resources(ids):
        captured["ids"] = ids
        return [make_resource_record("res-1", "ubuntu-01", os_description="Ubuntu 22.04.3 LTS")]

    monkeypatch.setattr(module, "load_resources", fake_load_resources)
    monkeypatch.setattr(
        module,
        "external_checker",
        lambda product, version: {
            "status": "supported",
            "summary": "supported",
            "links": [],
            "checkedAt": "2026-04-03T00:00:00Z",
        },
    )

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["--resource-ids", "res-1"])

    payload = extract_payload(stdout.getvalue())

    assert exit_code == 0
    assert captured["ids"] == ["res-1"]
    assert payload["requestedResourceIds"] == ["res-1"]


def test_rendered_summary_does_not_fallback_to_resource_id_when_name_missing():
    module = load_module()
    output = module.render_output(
        {
            "analyzedCount": 1,
            "failedCount": 0,
            "results": [
                {
                    "resourceId": "res-hidden-1",
                    "resourceName": "",
                    "summary": {
                        "overallCompliance": "needs_review",
                        "confidence": "low",
                    },
                }
            ],
        }
    )
    visible_summary = output.split("##RESOURCE_COMPLIANCE_START##", 1)[0]

    assert "[1] unknown resource | needs_review | confidence=low" in visible_summary
    assert "res-hidden-1" not in visible_summary


def test_main_emits_summary_and_analysis_block(monkeypatch):
    module = load_module()

    monkeypatch.setattr(
        module,
        "load_resources",
        lambda ids: [make_resource_record("res-1", "ubuntu-01", os_description="Ubuntu 22.04.3 LTS")],
    )
    monkeypatch.setattr(
        module,
        "external_checker",
        lambda product, version: {
            "status": "supported",
            "summary": f"{product} {version} is supported.",
            "links": ["https://example.invalid/support"],
            "checkedAt": "2026-04-03T00:00:00Z",
        },
    )

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["res-1"])

    output = stdout.getvalue()
    payload = extract_payload(output)

    assert exit_code == 0
    assert "Analyzed 1 resource(s)." in output
    assert payload["requestedResourceIds"] == ["res-1"]
    assert payload["triggerSource"] == "user"
    assert payload["analyzedCount"] == 1
    assert payload["failedCount"] == 0
    assert payload["results"][0]["type"] == "resource.os.linux"
    assert payload["results"][0]["analysisTargets"] == ["os:linux"]
    assert payload["results"][0]["summary"]["overallCompliance"] == "compliant"


def test_main_accepts_webhook_payload_json(monkeypatch):
    module = load_module()

    monkeypatch.setattr(
        module,
        "load_resources",
        lambda ids: [make_resource_record("res-1", "win-01", os_description="Windows Server 2016 Datacenter")],
    )
    monkeypatch.setattr(
        module,
        "external_checker",
        lambda product, version: {
            "status": "warning",
            "summary": f"{product} {version} needs review.",
            "links": ["https://example.invalid/windows"],
            "checkedAt": "2026-04-03T00:00:00Z",
        },
    )

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(
            [
                "--payload-json",
                json.dumps(
                    {
                        "resourceIds": ["res-1"],
                        "triggerSource": "webhook",
                        "rawMetadata": {"event": "manual-validation"},
                    }
                ),
            ]
        )

    output = stdout.getvalue()
    payload = extract_payload(output)

    assert exit_code == 0
    assert payload["triggerSource"] == "webhook"
    assert payload["requestedResourceIds"] == ["res-1"]
    assert payload["results"][0]["resourceId"] == "res-1"
    assert payload["results"][0]["type"] == "resource.os.windows"


def test_main_reports_fetch_failure_when_one_resource_has_no_data(monkeypatch):
    module = load_module()

    monkeypatch.setattr(
        module,
        "load_resources",
        lambda ids: [
            make_resource_record("res-1", "ubuntu-01", os_description="Ubuntu 22.04.3 LTS"),
            {
                "resourceId": "res-missing",
                "summary": {"componentType": "resource.software.db.mysql"},
                "data": {},
                "resource": {},
                "details": {},
                "fetchStatus": "error",
                "missingEvidence": ["resource.data"],
                "errors": ["Resource view data was not returned."],
            },
        ],
    )
    monkeypatch.setattr(
        module,
        "external_checker",
        lambda product, version: {
            "status": "supported",
            "summary": "supported",
            "links": [],
            "checkedAt": "2026-04-03T00:00:00Z",
        },
    )

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["res-1", "res-missing"])

    payload = extract_payload(stdout.getvalue())

    assert exit_code == 0
    assert payload["analyzedCount"] == 1
    assert payload["failedCount"] == 1
    assert payload["results"][1]["analysisStatus"] == "fetch_failed"
    assert payload["results"][1]["type"] == "resource.software.db.mysql"


def test_main_preserves_degraded_external_validation_result(monkeypatch):
    module = load_module()

    monkeypatch.setattr(
        module,
        "load_resources",
        lambda ids: [make_resource_record("res-1", "win-01", os_description="Windows Server 2016 Datacenter")],
    )

    def failing_checker(product, version):
        raise RuntimeError(f"external validation unavailable for {product} {version}")

    monkeypatch.setattr(module, "external_checker", failing_checker)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["res-1"])

    payload = extract_payload(stdout.getvalue())

    assert exit_code == 0
    assert payload["results"][0]["summary"]["overallCompliance"] == "needs_review"
    assert payload["results"][0]["analysisTargets"] == ["os:windows"]
    assert any(
        "external validation unavailable" in item
        for item in payload["results"][0]["uncertainties"]
    )


def test_main_builds_normalized_fallback_from_legacy_record_shape(monkeypatch):
    module = load_module()

    monkeypatch.setattr(
        module,
        "load_resources",
        lambda ids: [
            {
                "resourceId": "res-legacy-mysql",
                "summary": {
                    "id": "res-legacy-mysql",
                    "name": "mysql-legacy",
                    "resourceType": "cloudchef.nodes.Compute",
                    "componentType": "resource.software.rds.mysql_32",
                    "osType": "LINUX",
                },
                "resource": {
                    "id": "res-legacy-mysql",
                    "name": "mysql-legacy",
                    "resourceType": "cloudchef.nodes.Compute",
                    "componentType": "resource.software.rds.mysql_32",
                    "osType": "LINUX",
                    "properties": {"softwareVersion": "1.0"},
                    "extensibleProperties": {"RuntimeProperties": {"version1": "5.7"}},
                },
                "details": {"hostname": "mysql-legacy"},
                "fetchStatus": "ok",
                "errors": [],
            }
        ],
    )
    monkeypatch.setattr(
        module,
        "external_checker",
        lambda product, version: {
            "status": "supported",
            "summary": f"{product} {version} is supported.",
            "links": ["https://example.invalid/support"],
            "checkedAt": "2026-04-03T00:00:00Z",
        },
    )

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["res-legacy-mysql"])

    payload = extract_payload(stdout.getvalue())

    assert exit_code == 0
    assert payload["results"][0]["type"] == "resource.software.rds.mysql_32"
    assert payload["results"][0]["analysisTargets"] == ["software:mysql"]
    assert payload["results"][0]["properties"]["version1"] == "5.7"
    assert payload["results"][0]["findings"][0]["evidence"] == ["version1=5.7"]
