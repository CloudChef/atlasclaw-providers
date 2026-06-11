# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

import importlib.util
import io
import json
import sys
import types
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "shared"
    / "scripts"
    / "get_catalog_detail.py"
)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


def _unexpected_http_call(*args, **kwargs):
    raise AssertionError("Unexpected HTTP call in test.")


class _FakeRequests(types.SimpleNamespace):
    class exceptions:
        class RequestException(Exception):
            pass

        class HTTPError(RequestException):
            pass

    RequestException = exceptions.RequestException
    HTTPError = exceptions.HTTPError

    def __init__(self):
        super().__init__(
            get=_unexpected_http_call,
            post=_unexpected_http_call,
            exceptions=self.exceptions,
        )


class _FakeUrllib3(types.SimpleNamespace):
    class exceptions:
        class InsecureRequestWarning(Warning):
            pass

    def __init__(self):
        super().__init__(
            disable_warnings=lambda *args, **kwargs: None,
            exceptions=self.exceptions,
        )


def _load_module(monkeypatch):
    monkeypatch.setenv("CMP_URL", "https://cmp.example.com")
    monkeypatch.setenv("CMP_COOKIE", "CloudChef-Authenticate=token")
    monkeypatch.setitem(sys.modules, "requests", _FakeRequests())
    monkeypatch.setitem(sys.modules, "urllib3", _FakeUrllib3())
    monkeypatch.setitem(sys.modules, "yaml", None)
    sys.modules.pop("_common", None)
    spec = importlib.util.spec_from_file_location("smartcmp_get_catalog_detail_script", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def _extract_meta(stderr: str) -> dict:
    payload = stderr.split("##CATALOG_DETAIL_META_START##\n", 1)[1].split(
        "\n##CATALOG_DETAIL_META_END##",
        1,
    )[0]
    return json.loads(payload)


def _cjk(*codepoints: str) -> str:
    return "".join(chr(int(codepoint, 16)) for codepoint in codepoints)


def test_catalog_detail_fetches_by_id_and_extracts_preapproval_section(monkeypatch) -> None:
    module = _load_module(monkeypatch)
    instructions = """
# Request Parameter Instructions

catalog:
  id: "catalog-1"

# Pre Approval Instructions

Approve only when the requester selects the dev environment.

# Request Instructions

Use the request parameter contract.
""".strip()

    def fake_get(url, headers=None, verify=None, timeout=None):
        if url == "https://cmp.example.com/platform-api/catalogs/catalog-1":
            assert timeout == 30
            return _FakeResponse(
                {
                    "id": "catalog-1",
                    "name": "Linux VM",
                    "sourceKey": "resource.iaas.machine.instance.abstract",
                    "serviceCategory": "CLOUD_COMPONENT_SERVICE",
                    "type": "CLOUD_COMPONENT",
                    "instructions": instructions,
                }
            )
        raise module.requests.exceptions.HTTPError(f"not found: {url}")

    monkeypatch.setattr(module.requests, "get", fake_get)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = module.main(["catalog-1"])

    assert exit_code == 0
    assert "Catalog Detail: Linux VM" in stdout.getvalue()
    meta = _extract_meta(stderr.getvalue())
    assert meta["id"] == "catalog-1"
    assert meta["hasPreApprovalInstructions"] is True
    assert meta["preApprovalInstructionHeading"] == "# Pre Approval Instructions"
    assert meta["preApprovalInstructions"] == "Approve only when the requester selects the dev environment."
    assert "Request Instructions" not in meta["preApprovalInstructions"]


def test_catalog_detail_reports_missing_preapproval_section(monkeypatch) -> None:
    module = _load_module(monkeypatch)

    def fake_get(url, headers=None, verify=None, timeout=None):
        if url == "https://cmp.example.com/platform-api/catalogs/catalog-2":
            return _FakeResponse({"id": "catalog-2", "name": "VPC", "instructions": "# Request Instructions\n\nBuild it."})
        raise module.requests.exceptions.HTTPError(f"not found: {url}")

    monkeypatch.setattr(module.requests, "get", fake_get)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = module.main(["catalog-2"])

    assert exit_code == 0
    assert "Has Pre Approval Instructions: false" in stdout.getvalue()
    meta = _extract_meta(stderr.getvalue())
    assert meta["hasInstructions"] is True
    assert meta["hasPreApprovalInstructions"] is False
    assert "preApprovalInstructions" not in meta


def test_catalog_detail_extracts_request_parameter_instruction_fields(monkeypatch) -> None:
    module = _load_module(monkeypatch)
    instructions = """
# Request Parameter Instructions

catalog:
  componentType: "resource.example"
topLevelRequired:
  - catalogId
  - businessGroupName
  - name
topLevelFields:
  name:
    type: string
    required: true
    ask: true
params:
  rootCostCenter:
    type: string
    required: false
genericRequest:
  processForm:
    ticketField:
      type: string
      required: true
resourceSpecs:
  - node: EIP
    type: resource.example.eip
    resourceBundleParams:
      zoneId:
        type: string
        defaultValue: zone-a
    params:
      Bandwidth:
        type: string
        required: true
        defaultValue: "5"
    AllocateEIP:
      type: boolean
      required: false
      defaultValue: false

# Request Instructions

Use the request parameter contract.
""".strip()

    def fake_get(url, headers=None, verify=None, timeout=None):
        if url == "https://cmp.example.com/platform-api/catalogs/catalog-fields":
            return _FakeResponse(
                {
                    "id": "catalog-fields",
                    "name": "EIP",
                    "sourceKey": "resource.example.eip",
                    "serviceCategory": "CLOUD_COMPONENT_SERVICE",
                    "type": "APPLICATION",
                    "instructions": instructions,
                }
            )
        raise module.requests.exceptions.HTTPError(f"not found: {url}")

    monkeypatch.setattr(module.requests, "get", fake_get)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = module.main(["catalog-fields"])

    assert exit_code == 0
    assert "Has Request Parameter Instructions: true" in stdout.getvalue()
    meta = _extract_meta(stderr.getvalue())
    assert meta["hasRequestParameterInstructions"] is True
    assert meta["instructions"]["componentType"] == "resource.example"
    assert meta["instructions"]["topLevelRequired"] == ["catalogId", "businessGroupName", "name"]
    assert meta["instructions"]["topLevelFields"]["name"]["location"] == "topLevel"
    assert meta["instructions"]["params"]["rootCostCenter"]["location"] == "rootParams"
    assert meta["instructions"]["genericRequest"]["processForm"]["ticketField"]["location"] == "genericRequest.processForm"
    spec = meta["instructions"]["resourceSpecs"][0]
    assert spec["node"] == "EIP"
    assert spec["type"] == "resource.example.eip"
    assert spec["params"]["Bandwidth"]["location"] == "params"
    assert spec["resourceBundleParams"]["zoneId"]["location"] == "resourceBundleParams"
    assert spec["AllocateEIP"]["location"] == "resourceSpecFields"
    assert meta["catalogFieldKeys"]["topLevelFields"] == ["name"]
    assert meta["catalogFieldKeys"]["params"] == ["rootCostCenter"]
    assert meta["catalogFieldKeys"]["genericRequest.processForm"] == ["ticketField"]
    assert meta["catalogFieldKeys"]["resourceSpecs"][0]["params"] == ["Bandwidth"]
    assert meta["catalogFieldKeys"]["resourceSpecs"][0]["resourceBundleParams"] == ["zoneId"]
    assert meta["catalogFieldKeys"]["resourceSpecs"][0]["resourceSpecFields"] == ["AllocateEIP"]


def test_catalog_detail_extracts_payload_form_fields_without_request_parameter_instructions(monkeypatch) -> None:
    module = _load_module(monkeypatch)

    def fake_get(url, headers=None, verify=None, timeout=None):
        assert url == "https://cmp.example.com/platform-api/catalogs/catalog-ip"
        return _FakeResponse(
            {
                "id": "catalog-ip",
                "nameZh": "IP申请",
                "sourceKey": "resource.example.ip",
                "instructions": "",
                "content": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "appSystem": {
                                "type": "string",
                                "title": "应用系统",
                                "widget": {"id": "select"},
                            },
                            "ownerName": {
                                "type": "string",
                                "title": "所有者",
                            },
                        },
                    }
                },
            }
        )

    monkeypatch.setattr(module.requests, "get", fake_get)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = module.main(["catalog-ip"])

    assert exit_code == 0
    assert "Has Request Parameter Instructions: false" in stdout.getvalue()
    assert "Has Catalog Payload Fields: true" in stdout.getvalue()
    meta = _extract_meta(stderr.getvalue())
    assert meta["hasRequestParameterInstructions"] is False
    assert meta["hasCatalogPayloadFields"] is True
    assert meta["catalogPayloadFields"] == {
        "appSystem": {
            "key": "appSystem",
            "label": "应用系统",
            "required": False,
            "defaultValue": None,
            "type": "string",
            "location": "catalog.content.schema.properties",
        },
        "ownerName": {
            "key": "ownerName",
            "label": "所有者",
            "required": False,
            "defaultValue": None,
            "type": "string",
            "location": "catalog.content.schema.properties",
        },
    }
    assert meta["catalogFieldKeys"]["payloadFields"] == ["appSystem", "ownerName"]


def test_catalog_detail_extracts_payload_fields_from_related_form_id(monkeypatch) -> None:
    module = _load_module(monkeypatch)
    calls: list[str] = []

    def fake_get(url, headers=None, verify=None, timeout=None):
        calls.append(url)
        if url == "https://cmp.example.com/platform-api/catalogs/catalog-ip":
            return _FakeResponse(
                {
                    "id": "catalog-ip",
                    "nameZh": "IP申请",
                    "instructions": "",
                    "requestFormId": "form-ip",
                }
            )
        if url == "https://cmp.example.com/platform-api/forms/form-ip":
            return _FakeResponse(
                {
                    "content": {
                        "schema": {
                            "properties": {
                                "applicationSystem": {"type": "string", "title": "应用系统"},
                                "ownerName": {"type": "string", "title": "所有者"},
                            }
                        }
                    }
                }
            )
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(module.requests, "get", fake_get)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = module.main(["catalog-ip"])

    assert exit_code == 0
    assert "Has Catalog Payload Fields: true" in stdout.getvalue()
    meta = _extract_meta(stderr.getvalue())
    assert "https://cmp.example.com/platform-api/forms/form-ip" in calls
    assert meta["hasCatalogPayloadFields"] is True
    assert meta["catalogPayloadFieldSource"] == "/forms/form-ip"
    assert meta["catalogPayloadFields"]["applicationSystem"]["label"] == "应用系统"
    assert meta["catalogPayloadFields"]["applicationSystem"]["location"] == "form:form-ip.content.schema.properties"
    assert meta["catalogFieldKeys"]["payloadFields"] == ["applicationSystem", "ownerName"]


def test_catalog_detail_fetches_related_form_fields_even_with_instructions(monkeypatch) -> None:
    module = _load_module(monkeypatch)
    owner = _cjk("6240", "6709", "8005")
    compute_specification = _cjk("8BA1", "7B97", "89C4", "683C")
    instructions = """
# Request Parameter Instructions

topLevelRequired:
  - catalogId
  - businessGroupName
resourceSpecs:
  - node: VM
    params:
      computeProfileId:
        type: string
        label: compute profile id
      flavorId:
        type: string
        label: flavor id
""".strip()
    calls: list[str] = []

    def fake_get(url, headers=None, verify=None, timeout=None):
        calls.append(url)
        if url == "https://cmp.example.com/platform-api/catalogs/catalog-linux":
            return _FakeResponse(
                {
                    "id": "catalog-linux",
                    "name": "Linux VM",
                    "instructions": instructions,
                    "requestFormId": "form-linux",
                }
            )
        if url == "https://cmp.example.com/platform-api/forms/form-linux":
            return _FakeResponse(
                {
                    "content": {
                        "schema": {
                            "properties": {
                                "ownerName": {"type": "string", "title": owner},
                                "computeProfileId": {
                                    "type": "string",
                                    "i18nTitle": {"zh": compute_specification, "en": "Compute specification"},
                                },
                            }
                        }
                    }
                }
            )
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(module.requests, "get", fake_get)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = module.main(["catalog-linux"])

    meta = _extract_meta(stderr.getvalue())
    assert exit_code == 0
    assert "https://cmp.example.com/platform-api/forms/form-linux" in calls
    assert meta["hasRequestParameterInstructions"] is True
    assert meta["hasCatalogPayloadFields"] is True
    assert meta["catalogPayloadFields"]["ownerName"]["label"] == owner
    assert meta["catalogPayloadFields"]["computeProfileId"]["label"] == compute_specification


def test_catalog_detail_probes_catalog_form_endpoints_when_detail_has_no_fields(monkeypatch) -> None:
    module = _load_module(monkeypatch)
    calls: list[str] = []

    def fake_get(url, headers=None, verify=None, timeout=None):
        calls.append(url)
        if url == "https://cmp.example.com/platform-api/catalogs/catalog-ip":
            return _FakeResponse({"id": "catalog-ip", "nameZh": "IP申请", "instructions": ""})
        if url == "https://cmp.example.com/platform-api/catalogs/catalog-ip/request-form":
            return _FakeResponse(
                {
                    "schema": {
                        "properties": {
                            "applicationSystem": {"type": "string", "title": "应用系统"},
                            "ownerName": {"type": "string", "title": "所有者"},
                        }
                    }
                }
            )
        raise module.requests.exceptions.HTTPError(f"not found: {url}")

    monkeypatch.setattr(module.requests, "get", fake_get)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = module.main(["catalog-ip"])

    assert exit_code == 0
    assert "Has Catalog Payload Fields: true" in stdout.getvalue()
    meta = _extract_meta(stderr.getvalue())
    assert "https://cmp.example.com/platform-api/catalogs/catalog-ip/request-form" in calls
    assert meta["hasCatalogPayloadFields"] is True
    assert meta["catalogPayloadFieldSource"] == "/catalogs/catalog-ip/request-form"
    assert meta["catalogPayloadFields"]["applicationSystem"]["key"] == "applicationSystem"
    assert meta["catalogPayloadFields"]["ownerName"]["label"] == "所有者"
