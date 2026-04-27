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


def test_main_reports_partial_success_when_one_fetch_failed(monkeypatch):
    module = load_module()

    monkeypatch.setattr(
        module,
        "load_resources",
        lambda ids: [
            make_resource_record("res-1", "ubuntu-01", os_description="Ubuntu 22.04.3 LTS"),
            {
                "resourceId": "res-missing",
                "summary": {"componentType": "resource.software.db.mysql"},
                "resource": {},
                "details": {},
                "fetchStatus": "not_found",
                "errors": ["Resource was not returned by /nodes/search."],
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
