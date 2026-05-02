# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import requests


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "request"
    / "scripts"
    / "status.py"
)


class FakeResponse:
    def __init__(self, payload, *, status_code: int = 200, text: str = ""):
        self._payload = payload
        self.status_code = status_code
        self.text = text or json.dumps(payload, ensure_ascii=False)

    def json(self):
        return self._payload


def _unexpected_http_call(*args, **kwargs):
    raise AssertionError("Unexpected HTTP call in test.")


def load_module():
    module_name = "test_request_status_script_module"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(module_name, None)


def run_script(monkeypatch, argv: list[str], *, fake_get=None):
    module = load_module()
    monkeypatch.setenv("CMP_URL", "https://cmp.example.com")
    monkeypatch.setenv("CMP_COOKIE", "CloudChef-Authenticate=test-token")
    monkeypatch.setattr(module.requests, "get", fake_get or _unexpected_http_call)

    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = module.main(argv)
    return exit_code, stdout.getvalue(), stderr.getvalue()


def extract_meta(stderr: str):
    start = "##REQUEST_STATUS_META_START##"
    end = "##REQUEST_STATUS_META_END##"
    assert start in stderr and end in stderr, stderr
    payload = stderr.split(start, 1)[1].split(end, 1)[0].strip()
    return json.loads(payload)


def test_status_script_has_no_hardcoded_chinese_output() -> None:
    script_text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert re.search(r"[\u4e00-\u9fff]", script_text) is None
    assert "approvalMessage" not in script_text
    assert "Approval has " not in script_text


def test_status_resolves_visible_request_id_via_search_then_detail(monkeypatch):
    request_id = "RES20260501000095"
    calls: list[str] = []

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        calls.append(url)
        if url == "https://cmp.example.com/platform-api/generic-request/search":
            assert params["queryValue"] == request_id
            return FakeResponse({"content": [{"id": "req-internal-95", "workflowId": request_id}]})
        if url == "https://cmp.example.com/platform-api/generic-request/req-internal-95":
            return FakeResponse(
                {
                    "id": "req-internal-95",
                    "workflowId": request_id,
                    "name": "Linux-test-agent",
                    "catalogName": "Linux VM",
                    "state": "APPROVAL_PENDING",
                    "provisionState": "",
                    "createdDate": 1_774_000_000_000,
                    "updatedDate": 1_774_000_060_000,
                    "currentActivity": {
                        "processStep": {"name": "Level 1 Approval"},
                        "assignments": [{"approver": {"name": "admin"}}],
                    },
                }
            )
        raise AssertionError(f"Unexpected GET url: {url}")

    exit_code, stdout, stderr = run_script(monkeypatch, [request_id], fake_get=fake_get)

    assert exit_code == 0
    assert calls == [
        "https://cmp.example.com/platform-api/generic-request/search",
        "https://cmp.example.com/platform-api/generic-request/req-internal-95",
    ]
    assert f"Request ID: {request_id}" in stdout
    assert "State: APPROVAL_PENDING" in stdout
    assert "Status Category: approval_pending" in stdout
    assert "Approval Passed: false" in stdout
    assert "Current Step: Level 1 Approval" in stdout
    assert "Current Assignee: admin" in stdout

    meta = extract_meta(stderr)
    assert meta["requestId"] == request_id
    assert meta["internalRequestId"] == "req-internal-95"
    assert meta["statusCategory"] == "approval_pending"
    assert meta["approvalPassed"] is False
    assert "approvalMessage" not in meta


def test_status_accepts_internal_request_id_when_search_has_no_exact_match(monkeypatch):
    internal_id = "req-internal-100"

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        if url == "https://cmp.example.com/platform-api/generic-request/search":
            return FakeResponse({"content": []})
        if url == f"https://cmp.example.com/platform-api/generic-request/{internal_id}":
            return FakeResponse(
                {
                    "id": internal_id,
                    "workflowId": "TIC20260501000100",
                    "name": "ticket-100",
                    "catalogName": "Ticket",
                    "state": "FINISHED",
                    "updatedDate": "2026-05-01T12:00:00",
                }
            )
        raise AssertionError(f"Unexpected GET url: {url}")

    exit_code, stdout, stderr = run_script(monkeypatch, [internal_id], fake_get=fake_get)

    assert exit_code == 0
    assert "Request ID: TIC20260501000100" in stdout
    assert "State: FINISHED" in stdout
    assert "Status Category: approval_passed" in stdout
    assert "Approval Passed: true" in stdout
    meta = extract_meta(stderr)
    assert meta["internalRequestId"] == internal_id
    assert meta["approvalPassed"] is True


def test_status_does_not_treat_success_message_as_error(monkeypatch):
    request_id = "RES20260501000101"

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        if url == "https://cmp.example.com/platform-api/generic-request/search":
            return FakeResponse({"content": [{"id": "req-internal-101", "workflowId": request_id}]})
        if url == "https://cmp.example.com/platform-api/generic-request/req-internal-101":
            return FakeResponse(
                {
                    "id": "req-internal-101",
                    "workflowId": request_id,
                    "name": "Linux-finished",
                    "catalogName": "Linux VM",
                    "state": "FINISHED",
                    "message": "Request completed successfully",
                    "updatedDate": "2026-05-01T12:00:00",
                }
            )
        raise AssertionError(f"Unexpected GET url: {url}")

    exit_code, stdout, stderr = run_script(monkeypatch, [request_id], fake_get=fake_get)

    assert exit_code == 0
    assert "State: FINISHED" in stdout
    assert "Error:" not in stdout
    meta = extract_meta(stderr)
    assert meta["statusCategory"] == "approval_passed"
    assert meta["error"] == ""


def test_status_semantics_for_common_states():
    module = load_module()

    cases = {
        "APPROVAL_PENDING": ("approval_pending", False),
        "APPROVAL_REJECTED": ("approval_rejected", False),
        "APPROVAL_RETREATED": ("approval_rejected", False),
        "STARTED": ("approval_passed", True),
        "TASK_RUNNING": ("approval_passed", True),
        "WAIT_EXECUTE": ("approval_passed", True),
        "FINISHED": ("approval_passed", True),
        "INITIALING": ("initial_or_failed", None),
        "INITIALING_FAILED": ("initial_or_failed", None),
        "FAILED": ("initial_or_failed", None),
        "CANCELED": ("initial_or_failed", None),
    }

    for state, expected in cases.items():
        category, approval_passed = module.classify_status(state)
        assert (category, approval_passed) == expected


def test_status_returns_clear_error_when_no_request_matches(monkeypatch):
    request_id = "RES20260501999999"

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        if url == "https://cmp.example.com/platform-api/generic-request/search":
            return FakeResponse({"content": []})
        if url == f"https://cmp.example.com/platform-api/generic-request/{request_id}":
            return FakeResponse({"message": "Not found"}, status_code=404, text="Not found")
        raise AssertionError(f"Unexpected GET url: {url}")

    exit_code, stdout, stderr = run_script(monkeypatch, [request_id], fake_get=fake_get)

    assert exit_code == 1
    assert "[ERROR] No SmartCMP request matched Request ID: RES20260501999999" in stdout
    assert "direct detail failed: HTTP 404" in stdout
    assert "REQUEST_STATUS_META" not in stderr


def test_status_does_not_fallback_to_partial_search_row_when_detail_fails(monkeypatch):
    request_id = "RES20260501000095"

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        if url == "https://cmp.example.com/platform-api/generic-request/search":
            return FakeResponse({"content": [{"id": "req-internal-95", "workflowId": request_id}]})
        if url == "https://cmp.example.com/platform-api/generic-request/req-internal-95":
            return FakeResponse({"message": "Forbidden"}, status_code=403, text="Forbidden")
        raise AssertionError(f"Unexpected GET url: {url}")

    exit_code, stdout, stderr = run_script(monkeypatch, [request_id], fake_get=fake_get)

    assert exit_code == 1
    assert "Matched Request ID RES20260501000095, but detail lookup failed" in stdout
    assert "HTTP 403" in stdout
    assert "REQUEST_STATUS_META" not in stderr


def test_status_does_not_match_approval_task_or_process_ids_from_search(monkeypatch):
    task_id = "task-123"

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        if url == "https://cmp.example.com/platform-api/generic-request/search":
            return FakeResponse(
                {
                    "content": [
                        {
                            "id": "req-internal-95",
                            "workflowId": "RES20260501000095",
                            "currentActivity": {
                                "taskId": task_id,
                                "processInstanceId": "process-123",
                            },
                        }
                    ]
                }
            )
        if url == f"https://cmp.example.com/platform-api/generic-request/{task_id}":
            return FakeResponse({"message": "Not found"}, status_code=404, text="Not found")
        raise AssertionError(f"Unexpected GET url: {url}")

    exit_code, stdout, stderr = run_script(monkeypatch, [task_id], fake_get=fake_get)

    assert exit_code == 1
    assert "[ERROR] No SmartCMP request matched Request ID: task-123" in stdout
    assert "REQUEST_STATUS_META" not in stderr
