# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

import importlib.util
import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

import requests


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    REPO_ROOT
    / "providers"
    / "SmartCMP-Provider"
    / "skills"
    / "resource"
    / "scripts"
    / "operate_resource.py"
)


class DummyResponse:
    def __init__(self, status_code=200, text="{}", body=None):
        self.status_code = status_code
        self.text = text
        self._body = {} if body is None else body

    def json(self):
        return self._body


class InvalidJsonResponse:
    def __init__(self, text="not-json"):
        self.status_code = 200
        self.text = text

    def json(self):
        raise ValueError("No JSON object could be decoded")


def load_module():
    spec = importlib.util.spec_from_file_location("test_resource_power_module", MODULE_PATH)
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
        r"##RESOURCE_POWER_OPERATION_START##\s*(.*?)\s*##RESOURCE_POWER_OPERATION_END##",
        output,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def test_normalize_action_supports_english_and_chinese_aliases():
    module = load_module()

    assert module.normalize_action("start") == "start"
    assert module.normalize_action("power-on") == "start"
    assert module.normalize_action("开机") == "start"
    assert module.normalize_action("stop") == "stop"
    assert module.normalize_action("shutdown") == "stop"
    assert module.normalize_action("关机") == "stop"
    assert module.normalize_action("CREATE-SNAPSHOT") == "create_snapshot"


def test_build_request_payload_serializes_resource_ids_and_schedule_defaults():
    module = load_module()

    payload = module.build_request_payload(["res-1", "res-2"], "create_snapshot")

    assert payload == {
        "operationId": "create_snapshot",
        "resourceIds": "res-1,res-2",
        "scheduledTaskMetadataRequest": {
            "cronExpression": "",
            "cycleDescription": "",
            "cycled": False,
            "scheduleEnabled": False,
            "scheduledTime": None,
        },
    }


def test_render_operation_result_outputs_structured_block():
    module = load_module()
    result = module.build_operation_result(
        resource_ids=["res-1"],
        action="start",
    )

    output = module.render_operation_result(result)

    assert "Submitted start request for 1 resource(s)." in output
    assert "task-1" not in output
    payload = extract_payload(output)
    assert payload == result
    assert "request" not in payload
    assert "response" not in payload


def test_main_posts_to_resource_operations_endpoint(monkeypatch):
    module = load_module()
    calls = {}
    validation = {}

    def fake_require_config():
        return (
            "https://cmp.example.com/platform-api",
            "token",
            {"Content-Type": "application/json; charset=utf-8", "CloudChef-Authenticate": "token"},
            {},
        )

    def fake_validate_operation_for_targets(*, base_url, headers, targets, action):
        validation["base_url"] = base_url
        validation["headers"] = headers
        validation["targets"] = targets
        validation["action"] = action

    def fake_post(url, headers, json, verify, timeout):
        calls["url"] = url
        calls["headers"] = headers
        calls["json"] = json
        calls["verify"] = verify
        calls["timeout"] = timeout
        return DummyResponse(body={"taskId": "task-1"})

    monkeypatch.setattr(module, "require_config", fake_require_config)
    monkeypatch.setattr(module, "validate_operation_for_targets", fake_validate_operation_for_targets)
    monkeypatch.setattr(module.requests, "post", fake_post)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["res-1", "--action", "create_snapshot"])

    output = stdout.getvalue()
    payload = extract_payload(output)

    assert exit_code == 0
    assert validation["base_url"] == "https://cmp.example.com/platform-api"
    assert validation["targets"] == [{"category": "virtual-machines", "resourceId": "res-1"}]
    assert validation["action"] == "create_snapshot"
    assert calls["url"].endswith("/nodes/resource-operations")
    assert calls["json"]["operationId"] == "create_snapshot"
    assert calls["json"]["resourceIds"] == "res-1"
    assert calls["headers"]["CloudChef-Authenticate"] == "token"
    assert payload["action"] == "create_snapshot"
    assert payload["resourceIds"] == ["res-1"]
    assert payload["submitted"] is True
    assert "request" not in payload
    assert "response" not in payload
    assert "task-1" not in output


def test_main_rejects_http_200_business_failure_without_raw_response(monkeypatch):
    module = load_module()

    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {}, {}

    def fake_post(url, headers, json, verify, timeout):
        return DummyResponse(
            text='{"success":false,"message":"resource is already stopped","taskId":"task-1"}',
            body={"success": False, "message": "resource is already stopped", "taskId": "task-1"},
        )

    monkeypatch.setattr(module, "require_config", fake_require_config)
    monkeypatch.setattr(module, "validate_operation_for_targets", lambda **_kwargs: None)
    monkeypatch.setattr(module.requests, "post", fake_post)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["res-1", "--action", "stop"])

    output = stdout.getvalue()
    assert exit_code == 1
    assert "[ERROR] SmartCMP resource operation was not submitted: resource is already stopped" in output
    assert "##RESOURCE_POWER_OPERATION_START##" not in output
    assert "task-1" not in output


def test_main_rejects_empty_action():
    module = load_module()

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["res-1", "--action", ""])

    output = stdout.getvalue()
    assert exit_code == 1
    assert "[ERROR]" in output
    assert "action is required" in output


def test_validate_operation_for_targets_rejects_unavailable_or_non_executable_actions(monkeypatch):
    module = load_module()

    def fake_fetch_resource_operations(base_url, headers, category, resource_id):
        return [
            {"id": "refresh", "enabled": True, "parameters": "{}"},
            {"id": "stop", "enabled": False, "disabledMsgZh": "请先启动实例"},
        ]

    monkeypatch.setattr(module, "fetch_resource_operations", fake_fetch_resource_operations)

    module.validate_operation_for_targets(
        base_url="https://cmp.example.com/platform-api",
        headers={},
        targets=[{"category": "virtual-machines", "resourceId": "res-1"}],
        action="refresh",
    )

    try:
        module.validate_operation_for_targets(
            base_url="https://cmp.example.com/platform-api",
            headers={},
            targets=[{"category": "virtual-machines", "resourceId": "res-1"}],
            action="stop",
        )
    except ValueError as exc:
        assert "not executable" in str(exc)
        assert "请先启动实例" in str(exc)
    else:
        raise AssertionError("disabled operation should be rejected")

    try:
        module.validate_operation_for_targets(
            base_url="https://cmp.example.com/platform-api",
            headers={},
            targets=[{"category": "virtual-machines", "resourceId": "res-1"}],
            action="missing",
        )
    except ValueError as exc:
        assert "not available" in str(exc)
    else:
        raise AssertionError("missing operation should be rejected")


def test_main_rejects_action_when_current_user_cannot_execute_it(monkeypatch):
    module = load_module()

    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {}, {}

    def fake_validate_operation_for_targets(**_kwargs):
        raise ValueError("Operation 'stop' is not executable for resource res-1: 请先启动实例")

    def fake_post(*_args, **_kwargs):
        raise AssertionError("operation must not be posted after validation failure")

    monkeypatch.setattr(module, "require_config", fake_require_config)
    monkeypatch.setattr(module, "validate_operation_for_targets", fake_validate_operation_for_targets)
    monkeypatch.setattr(module.requests, "post", fake_post)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["res-1", "--action", "stop"])

    output = stdout.getvalue()
    assert exit_code == 1
    assert "not executable" in output


def test_main_handles_request_exception(monkeypatch):
    module = load_module()

    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {}, {}

    def fake_post(*_args, **_kwargs):
        raise requests.RequestException("connection timed out")

    monkeypatch.setattr(module, "require_config", fake_require_config)
    monkeypatch.setattr(module, "validate_operation_for_targets", lambda **_kwargs: None)
    monkeypatch.setattr(module.requests, "post", fake_post)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["res-1", "--action", "start"])

    output = stdout.getvalue()
    assert exit_code == 1
    assert "[ERROR] SmartCMP resource power request failed: connection timed out" in output


def test_main_handles_invalid_json_response(monkeypatch):
    module = load_module()

    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {}, {}

    def fake_post(url, headers, json, verify, timeout):
        return InvalidJsonResponse()

    monkeypatch.setattr(module, "require_config", fake_require_config)
    monkeypatch.setattr(module, "validate_operation_for_targets", lambda **_kwargs: None)
    monkeypatch.setattr(module.requests, "post", fake_post)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["res-1", "--action", "start"])

    output = stdout.getvalue()
    assert exit_code == 1
    assert "[ERROR] SmartCMP returned an invalid JSON response:" in output


def test_main_surfaces_http_error_message(monkeypatch):
    module = load_module()

    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {}, {}

    def fake_post(url, headers, json, verify, timeout):
        return DummyResponse(
            status_code=400,
            text='{"message":"resource is already stopped"}',
            body={"message": "resource is already stopped"},
        )

    monkeypatch.setattr(module, "require_config", fake_require_config)
    monkeypatch.setattr(module, "validate_operation_for_targets", lambda **_kwargs: None)
    monkeypatch.setattr(module.requests, "post", fake_post)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["res-1", "--action", "stop"])

    output = stdout.getvalue()
    assert exit_code == 1
    assert "[ERROR] HTTP 400: resource is already stopped" in output
