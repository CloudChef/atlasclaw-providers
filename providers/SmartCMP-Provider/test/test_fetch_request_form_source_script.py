# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

import importlib.util
import io
import json
import re
import sys
import types
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    PROVIDER_ROOT
    / "skills"
    / "form-designer-agent"
    / "scripts"
    / "fetch_request_form_source.py"
)
REQUEST_ID = "RES20260603000001"
DETAIL_ID = "20fef12e-5015-4df5-822b-e1e87c4f64fd"
CATALOG_ID = "943f38c1-1fc0-4df8-9710-d13f34f49f07"
FORM_ID = "BUILD-IN-INIT-FORM-TASK-SUBMIT"
UUID_FORM_ID = "943f38c1-1fc0-4df8-9710-d13f34f49f07"


class FakeResponse:
    def __init__(self, payload=None, *, status_code: int = 200, text: str = ""):
        self._payload = payload
        self.status_code = status_code
        self.text = text or json.dumps(payload, ensure_ascii=False)

    def json(self):
        if self._payload is None:
            raise ValueError("No JSON payload")
        return self._payload


class FakeRequests(types.SimpleNamespace):
    class exceptions:
        class RequestException(Exception):
            pass

    RequestException = exceptions.RequestException

    def __init__(self, fake_get):
        super().__init__(get=fake_get, exceptions=self.exceptions)


class FakeUrllib3(types.SimpleNamespace):
    class exceptions:
        class InsecureRequestWarning(Warning):
            pass

    def __init__(self):
        super().__init__(
            disable_warnings=lambda *args, **kwargs: None,
            exceptions=self.exceptions,
        )


def _unexpected_http_call(*args, **kwargs):
    raise AssertionError("Unexpected HTTP call in test.")


def run_script(monkeypatch, argv: list[str], *, fake_get=None):
    module_name = "test_fetch_request_form_source_script_module"
    fake_requests = FakeRequests(fake_get or _unexpected_http_call)

    monkeypatch.setenv("CMP_URL", "https://cmp.example.com")
    monkeypatch.setenv("CMP_COOKIE", "CloudChef-Authenticate=test-token")
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    monkeypatch.setitem(sys.modules, "urllib3", FakeUrllib3())
    sys.modules.pop("_common", None)

    stdout = io.StringIO()
    stderr = io.StringIO()
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            spec.loader.exec_module(module)
            exit_code = int(module.main(argv) or 0)
    finally:
        sys.modules.pop(module_name, None)
        sys.modules.pop("_common", None)

    return exit_code, stdout.getvalue(), stderr.getvalue()


def extract_meta(stderr: str) -> dict:
    match = re.search(
        r"##REQUEST_FORM_SOURCE_META_START##\s*(\{.*?\})\s*##REQUEST_FORM_SOURCE_META_END##",
        stderr,
        re.S,
    )
    assert match, stderr
    return json.loads(match.group(1))


def test_fetch_request_form_source_accepts_service_model_form_url(monkeypatch):
    source_url = (
        "https://cmp.example.com/#/main/service-model/forms"
        "?page=1&size=20&queryValue=&sort=updatedDate,desc&isList=true&strict=true"
    )

    exit_code, stdout, stderr = run_script(monkeypatch, [source_url])
    meta = extract_meta(stderr)
    assert exit_code == 0
    assert "[SUCCESS] Schema form source recognized" in stdout
    assert meta["decision"] == "schema_form_source_ready"
    assert meta["mode"] == "create"
    assert meta["sourceType"] == "smartcmp_service_model_form_list"
    assert meta["sourceUrl"] == source_url
    assert meta["requestParams"] == {}
    assert meta["backendParameterContract"]["shape"] == "kv_json_object"
    assert meta["backendParameterContract"]["sourcePolicy"] == "shape_dependent"
    assert meta["backendParameterContract"]["source"] == "shape_dependent"
    assert meta["backendParameterContract"]["sourcesByShape"]["smartcmp_content"] == "content.model"
    assert meta["backendParameterContract"]["sourcesByShape"]["schema_only"] == "properties"
    assert meta["backendParameterContract"]["sourcesByShape"]["formio_components"] == "components[].key"
    assert meta["backendParameterContract"]["catalogRequestLocation"] == "params_when_service_catalog_model_form"
    assert meta["backendParameterContract"]["genericRequestLocation"] == "genericRequest.processForm_when_process_form"
    assert meta["backendParameterKeys"] == []
    assert meta["backendParameterPayloadPreview"] == {}
    assert meta["designerOutputContract"]["primaryJson"] == "chat_fenced_json_value"
    assert meta["designerOutputContract"]["sourceContextKey"] == "designerPasteJson"
    assert meta["designerOutputContract"]["shapePolicy"] == "preserve_target_module_shape"
    assert meta["designerOutputContract"]["forceModelSchemaOptions"] is False
    assert meta["designerOutputContract"]["expertModePreviewDefault"] == "schema_only"
    assert meta["designerOutputContract"]["previewPasteTargets"]["visual_designer_expert_mode"] == "schema_only"
    assert meta["artifactAllowed"] is False
    assert meta["outputDeliveryContract"]["delivery"] == "chat_json_text_only"
    assert meta["outputDeliveryContract"]["fileOutputAllowed"] is False
    assert meta["outputDeliveryContract"]["artifactOutputAllowed"] is False
    assert meta["outputDeliveryContract"]["downloadOutputAllowed"] is False
    assert meta["outputDeliveryContract"]["localFileOutputAllowed"] is False
    assert meta["outputDeliveryContract"]["workspaceWriteAllowedForGeneratedJson"] is False
    assert meta["outputDeliveryContract"]["mustInlineCompleteJsonTextInChat"] is True
    assert "local_file_path" in meta["outputDeliveryContract"]["forbiddenDeliveryMethods"]
    assert meta["outputDeliveryContract"]["requiredFormat"] == "single_fenced_json_block"
    assert meta["retention"] == "schema_form_json"
    assert meta["interactionSurface"] == "smartcmp_platform_service_model_form"
    assert "handoffSkill" not in meta
    assert meta["finalAction"] == "return_schema_form_json_only"
    assert meta["cmpWriteAllowed"] is False
    assert meta["cmpWriteRequiresSecondConfirmation"] is False
    assert "Schema Form JSON" in meta["nextStep"]
    assert "backend parameters" in meta["nextStep"]
    assert "Return the generated or updated JSON as chat text in one fenced json code block" in meta["nextStep"]
    assert "Do not create, write, attach, or mention a JSON file" in meta["nextStep"]
    assert "save, mount, publish, or submit" in meta["nextStep"]
    assert "conversation draft" not in meta["nextStep"]
    assert "CMP form save tool" not in meta["nextStep"]
    assert "smartcmp_submit_request" not in stderr
    assert "Submitted:" not in stdout
    assert "submitted" not in meta
    assert "writeAllowed" not in meta


def test_fetch_request_form_source_reads_edit_form_url(monkeypatch):
    source_url = f"https://cmp.example.com/#/main/service-model/forms/edit/{FORM_ID}"
    calls = []

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        calls.append((url, params))
        assert url == f"https://cmp.example.com/platform-api/forms/{FORM_ID}"
        return FakeResponse(
            {
                "_id": FORM_ID,
                "title": "Task Submit",
                "name": "taskSubmit",
                "path": FORM_ID,
                "display": "form",
                "components": [{"key": "reason", "type": "textarea", "label": "Reason"}],
            }
        )

    exit_code, stdout, stderr = run_script(monkeypatch, [source_url], fake_get=fake_get)

    meta = extract_meta(stderr)
    assert exit_code == 0
    assert calls == [(f"https://cmp.example.com/platform-api/forms/{FORM_ID}", None)]
    assert "[SUCCESS] Schema form source fetched" in stdout
    assert meta["decision"] == "schema_form_source_ready"
    assert meta["mode"] == "update"
    assert meta["sourceType"] == "smartcmp_service_model_form_edit"
    assert meta["formId"] == FORM_ID
    assert meta["formDefinition"]["title"] == "Task Submit"
    assert meta["formDefinition"]["components"][0]["key"] == "reason"
    assert meta["backendParameterKeys"] == ["reason"]
    assert meta["backendParameterPayloadPreview"] == {"reason": None}
    assert meta["backendParameterContract"]["sourcePolicy"] == "shape_dependent"
    assert meta["backendParameterContract"]["source"] == "components[].key"
    assert meta["backendParameterContract"]["runtimeValue"] == "final_rendered_form_values"
    assert meta["designerPasteShape"] == "formio_components"
    assert meta["designerPasteJson"] == {"components": [{"key": "reason", "type": "textarea", "label": "Reason"}]}
    assert meta["previewCompatible"] is False
    assert any("Form.io components may not preview in SmartCMP schema expert mode" in warning for warning in meta["warnings"])
    assert "model" not in meta["designerPasteJson"]
    assert "schema" not in meta["designerPasteJson"]
    assert meta["cmpWriteAllowed"] is False
    assert meta["cmpWriteRequiresSecondConfirmation"] is False


def test_fetch_request_form_source_extracts_schema_form_kv_payload(monkeypatch):
    source_url = f"https://cmp.example.com/#/main/service-model/forms/edit/{FORM_ID}"

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        assert url == f"https://cmp.example.com/platform-api/forms/{FORM_ID}"
        return FakeResponse(
            {
                "_id": FORM_ID,
                "title": "VM Apply",
                "name": "vmApply",
                "content": {
                    "model": {"cpu": 2, "imageId": None},
                    "schema": {
                        "type": "object",
                        "properties": {
                            "cpu": {"id": "cpu", "type": "number", "default": 2},
                            "memory": {"id": "memory", "type": "number", "defaultValue": 4},
                            "imageId": {"id": "imageId", "type": "string"},
                        },
                        "required": ["cpu", "memory", "imageId"],
                    },
                    "options": {"sourceConfigParamter": {"resourceBundleId": "rb-1"}},
                },
            }
        )

    exit_code, stdout, stderr = run_script(monkeypatch, [source_url], fake_get=fake_get)

    meta = extract_meta(stderr)
    assert exit_code == 0
    assert "[SUCCESS] Schema form source fetched" in stdout
    assert meta["backendParameterContract"]["shape"] == "kv_json_object"
    assert meta["backendParameterContract"]["source"] == "properties"
    assert meta["backendParameterContract"]["sourcePolicy"] == "shape_dependent"
    assert meta["backendParameterKeys"] == ["cpu", "imageId", "memory"]
    assert meta["backendParameterPayloadPreview"] == {"cpu": 2, "imageId": None, "memory": 4}
    assert meta["designerPasteShape"] == "schema_only"
    assert set(meta["designerPasteJson"]["properties"]) == {"cpu", "memory", "imageId"}
    assert "model" not in meta["designerPasteJson"]
    assert "schema" not in meta["designerPasteJson"]
    assert "options" not in meta["designerPasteJson"]
    assert "title" not in meta["designerPasteJson"]
    assert "content" not in meta["designerPasteJson"]
    assert meta["extractedFormContent"]["model"] == {"cpu": 2, "imageId": None}
    assert set(meta["extractedFormContent"]["schema"]["properties"]) == {"cpu", "memory", "imageId"}


def test_fetch_request_form_source_reports_schema_only_parameter_source(monkeypatch):
    source_url = f"https://cmp.example.com/#/main/service-model/forms/edit/{FORM_ID}"

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        assert url == f"https://cmp.example.com/platform-api/forms/{FORM_ID}"
        return FakeResponse(
            {
                "_id": FORM_ID,
                "title": "Object Attribute",
                "name": "Object Attribute",
                "schema": {
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string", "default": "ops"},
                        "costCenter": {"type": "string"},
                    },
                },
            }
        )

    exit_code, stdout, stderr = run_script(monkeypatch, [source_url], fake_get=fake_get)

    meta = extract_meta(stderr)
    assert exit_code == 0
    assert "[SUCCESS] Schema form source fetched" in stdout
    assert meta["designerPasteShape"] == "schema_only"
    assert meta["designerPasteJson"]["properties"]["owner"]["default"] == "ops"
    assert meta["previewCompatible"] is True
    assert meta["warnings"] == []
    assert meta["backendParameterContract"]["sourcePolicy"] == "shape_dependent"
    assert meta["backendParameterContract"]["source"] == "properties"
    assert meta["backendParameterKeys"] == ["owner", "costCenter"]
    assert meta["backendParameterPayloadPreview"] == {"owner": "ops", "costCenter": None}


def test_fetch_request_form_source_masks_uuid_form_id_in_stdout(monkeypatch):
    source_url = f"https://cmp.example.com/#/main/service-model/forms/edit/{UUID_FORM_ID}"

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        assert url == f"https://cmp.example.com/platform-api/forms/{UUID_FORM_ID}"
        return FakeResponse(
            {
                "_id": UUID_FORM_ID,
                "title": "Task Submit",
                "name": "Task Submit",
                "content": {"schema": {"type": "object", "properties": {}}, "model": {}},
            }
        )

    exit_code, stdout, stderr = run_script(monkeypatch, [source_url], fake_get=fake_get)

    meta = extract_meta(stderr)
    assert exit_code == 0
    assert f"Form ID: {UUID_FORM_ID}" not in stdout
    assert "Form ID: [uuid]" in stdout
    assert meta["formId"] == UUID_FORM_ID


def test_fetch_request_form_source_reads_design_edit_form_url(monkeypatch):
    source_url = f"https://cmp.example.com/#/main/service-model/forms/design/{FORM_ID}?currentAction=edit#update"
    calls = []

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        calls.append((url, params))
        assert url == f"https://cmp.example.com/platform-api/forms/{FORM_ID}"
        return FakeResponse(
            {
                "_id": FORM_ID,
                "title": "Task Submit",
                "name": "Task Submit",
                "content": {"schema": {"type": "object", "properties": {}}, "model": {}},
            }
        )

    exit_code, stdout, stderr = run_script(monkeypatch, [source_url], fake_get=fake_get)

    meta = extract_meta(stderr)
    assert exit_code == 0
    assert calls == [(f"https://cmp.example.com/platform-api/forms/{FORM_ID}", None)]
    assert "[SUCCESS] Schema form source fetched" in stdout
    assert meta["mode"] == "update"
    assert meta["sourceType"] == "smartcmp_service_model_form_edit"
    assert meta["formId"] == FORM_ID
    assert meta["routePath"] == f"main/service-model/forms/design/{FORM_ID}"


def test_fetch_request_form_source_rejects_pending_request_detail_url(monkeypatch):
    source_url = f"https://cmp.example.com/#/main/requests/{DETAIL_ID}/detail"

    exit_code, stdout, stderr = run_script(monkeypatch, [source_url])

    assert exit_code == 1
    assert "[ERROR]" in stdout
    assert "service-model form URL" in stdout
    assert "REQUEST_FORM_SOURCE_META" not in stderr


def test_fetch_request_form_source_rejects_external_url_before_http(monkeypatch):
    exit_code, stdout, stderr = run_script(
        monkeypatch,
        [f"https://evil.example.com/#/approval/pending?requestId={REQUEST_ID}"],
    )

    assert exit_code == 1
    assert "[ERROR]" in stdout
    assert "outside configured SmartCMP host" in stdout
    assert "REQUEST_FORM_SOURCE_META" not in stderr
