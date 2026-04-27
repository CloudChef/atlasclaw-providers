# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

import json
import sys
from pathlib import Path

import requests


SCRIPT_DIR = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "cost-optimization"
    / "scripts"
)
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import execute_optimization as executor  # noqa: E402


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


def test_build_execution_result_uses_submission_semantics():
    result = executor.build_execution_result(
        violation_id="vio-1",
        submitted=True,
        message="submitted",
        response_body={"taskInstanceId": "task-1"},
    )

    assert result["violationId"] == "vio-1"
    assert result["requested"] is True
    assert result["executionSubmitted"] is True
    assert result["executionMode"] == "smartcmp_day2_fix"
    assert result["followUpRequired"] is True
    assert result["response"] == {"taskInstanceId": "task-1"}


def test_render_execution_result_outputs_structured_block():
    result = executor.build_execution_result(
        violation_id="vio-1",
        submitted=True,
        message="submitted",
        response_body={"taskInstanceId": "task-1"},
    )

    output = executor.render_execution_result(result)

    assert "Violation vio-1: submitted" in output
    assert "##COST_EXECUTION_START##" in output
    assert "##COST_EXECUTION_END##" in output
    payload = output.split("##COST_EXECUTION_START##\n", 1)[1].split(
        "\n##COST_EXECUTION_END##",
        1,
    )[0]
    assert json.loads(payload) == result


def test_main_posts_to_day2_fix_endpoint(monkeypatch, capsys):
    calls = {}

    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {"Content-Type": "application/json; charset=utf-8", "CloudChef-Authenticate": "token"}, {}

    def fake_post(url, headers, json, verify, timeout):
        calls["url"] = url
        calls["headers"] = headers
        calls["json"] = json
        calls["verify"] = verify
        calls["timeout"] = timeout
        return DummyResponse(body={"taskInstanceId": "task-1"})

    monkeypatch.setattr(executor, "require_config", fake_require_config)
    monkeypatch.setattr(executor.requests, "post", fake_post)
    monkeypatch.setattr(sys, "argv", ["execute_optimization.py", "--id", "vio-1"])

    assert executor.main() == 0
    output = capsys.readouterr().out

    assert calls["url"].endswith("/compliance-policies/violations/day2/fix/vio-1")
    assert calls["json"] == {}
    assert calls["headers"]["CloudChef-Authenticate"] == "token"
    assert "executionSubmitted" in output


def test_main_rejects_blank_id(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["execute_optimization.py", "--id", "   "])

    assert executor.main() == 1
    assert "[ERROR] --id must not be empty." in capsys.readouterr().out


def test_main_handles_request_exception(monkeypatch, capsys):
    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {}, {}

    def fake_post(*_args, **_kwargs):
        raise requests.RequestException("connection timed out")

    monkeypatch.setattr(executor, "require_config", fake_require_config)
    monkeypatch.setattr(executor.requests, "post", fake_post)
    monkeypatch.setattr(sys, "argv", ["execute_optimization.py", "--id", "vio-1"])

    assert executor.main() == 1
    output = capsys.readouterr().out
    assert "[ERROR] SmartCMP day2 fix request failed: connection timed out" in output
    assert "##COST_EXECUTION_START##" not in output


def test_main_handles_invalid_json_response(monkeypatch, capsys):
    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {}, {}

    def fake_post(url, headers, json, verify, timeout):
        return InvalidJsonResponse()

    monkeypatch.setattr(executor, "require_config", fake_require_config)
    monkeypatch.setattr(executor.requests, "post", fake_post)
    monkeypatch.setattr(sys, "argv", ["execute_optimization.py", "--id", "vio-1"])

    assert executor.main() == 1
    output = capsys.readouterr().out
    assert "[ERROR] SmartCMP returned an invalid JSON response:" in output
    assert "##COST_EXECUTION_START##" not in output


def test_main_surfaces_missing_repair_action_guidance(monkeypatch, capsys):
    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {}, {}

    def fake_post(url, headers, json, verify, timeout):
        return DummyResponse(
            status_code=400,
            text='{"message":"The policy has no repair action configured"}',
            body={"message": "The policy has no repair action configured"},
        )

    monkeypatch.setattr(executor, "require_config", fake_require_config)
    monkeypatch.setattr(executor.requests, "post", fake_post)
    monkeypatch.setattr(sys, "argv", ["execute_optimization.py", "--id", "vio-1"])

    assert executor.main() == 1
    output = capsys.readouterr().out
    assert "policy has no repair action configured" in output
    assert "##COST_EXECUTION_START##" not in output
