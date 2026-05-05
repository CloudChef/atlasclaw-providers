# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

import importlib.util
import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import requests


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "skills" / "approval" / "scripts"
VALID_REQUEST_ID = "RES20260505000010"
VALID_APPROVAL_ACTIVITY_ID = "20fef12e-5015-4df5-822b-e1e87c4f64fd"
RAW_RESPONSE_APPROVAL_ID = "bf1f6e71-9a5a-4c36-98e5-af9a68df2056"


class _FakeResponse:
    def __init__(self, payload=None, *, status_code: int = 200, url: str = ""):
        self._payload = {"success": True} if payload is None else payload
        self.text = json.dumps(self._payload)
        self.status_code = status_code
        self.url = url

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(
                f"{self.status_code} error for url: {self.url}",
                response=self,
            )
        return None

    def json(self):
        return self._payload


def _run_decision_script(
    monkeypatch,
    script_name: str,
    ids: str = VALID_REQUEST_ID,
    pending_payload=None,
    action_payload=None,
    action_status_code: int = 200,
):
    script_path = SCRIPT_DIR / script_name
    module_name = f"smartcmp_{script_path.stem}_robot_test"
    captured = {}
    if pending_payload is None:
        pending_payload = {
            "content": [
                {
                    "workflowId": VALID_REQUEST_ID,
                    "currentActivity": {"id": VALID_APPROVAL_ACTIVITY_ID},
                }
            ]
        }
    if action_payload is None:
        action_payload = {
            "success": True,
            "approvalId": RAW_RESPONSE_APPROVAL_ID,
            "id": VALID_APPROVAL_ACTIVITY_ID,
        }

    monkeypatch.setenv("ATLASCLAW_COOKIES", "{}")
    monkeypatch.setenv("ATLASCLAW_PROVIDER_INSTANCE", "robot-admin")
    monkeypatch.setenv(
        "ATLASCLAW_PROVIDER_CONFIG",
        json.dumps(
            {
                "smartcmp": {
                    "robot-admin": {
                        "base_url": "https://cmp.example.com",
                        "auth_type": "provider_token",
                        "provider_token": "cmp_tk_test_robot",
                    }
                }
            }
        ),
    )
    monkeypatch.setenv("IDS", ids)
    monkeypatch.setenv("REASON", "agent decision")
    monkeypatch.delenv("CMP_URL", raising=False)
    monkeypatch.delenv("CMP_COOKIE", raising=False)

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        captured["get"] = {
            "url": url,
            "headers": dict(headers or {}),
            "params": dict(params or {}),
            "verify": verify,
            "timeout": timeout,
        }
        return _FakeResponse(pending_payload)

    def fake_post(url, headers=None, params=None, json=None, verify=None, timeout=None):
        captured["post"] = {
            "url": url,
            "headers": dict(headers or {}),
            "params": dict(params or {}),
            "json": dict(json or {}),
            "verify": verify,
            "timeout": timeout,
        }
        return _FakeResponse(
            action_payload,
            status_code=action_status_code,
            url=f"{url}?ids={params.get('ids', '')}",
        )

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(sys, "argv", [script_path.name])

    stdout = io.StringIO()
    stderr = io.StringIO()
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    exit_code = None
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            spec.loader.exec_module(module)
    except SystemExit as exc:
        exit_code = exc.code
    finally:
        sys.modules.pop(module_name, None)

    return captured, stdout.getvalue(), stderr.getvalue(), exit_code


def test_approve_uses_robot_provider_token_from_require_config(monkeypatch):
    captured, stdout, _stderr, exit_code = _run_decision_script(monkeypatch, "approve.py")

    assert exit_code is None
    assert captured["get"]["url"] == "https://cmp.example.com/platform-api/generic-request/current-activity-approval"
    assert captured["post"]["url"] == "https://cmp.example.com/platform-api/approval-activity/approve/batch"
    assert captured["post"]["headers"]["Authorization"] == "Bearer cmp_tk_test_robot"
    assert "CloudChef-Authenticate" not in captured["post"]["headers"]
    assert captured["post"]["params"] == {"ids": VALID_APPROVAL_ACTIVITY_ID}
    assert captured["post"]["json"] == {"reason": "agent decision"}
    assert "[SUCCESS] Approval completed." in stdout
    assert VALID_APPROVAL_ACTIVITY_ID not in stdout
    assert RAW_RESPONSE_APPROVAL_ID not in stdout
    assert '"status": "approved"' in stdout
    assert '"response"' not in stdout


def test_reject_uses_robot_provider_token_from_require_config(monkeypatch):
    captured, stdout, _stderr, exit_code = _run_decision_script(monkeypatch, "reject.py")

    assert exit_code is None
    assert captured["get"]["url"] == "https://cmp.example.com/platform-api/generic-request/current-activity-approval"
    assert captured["post"]["url"] == "https://cmp.example.com/platform-api/approval-activity/reject/batch"
    assert captured["post"]["headers"]["Authorization"] == "Bearer cmp_tk_test_robot"
    assert "CloudChef-Authenticate" not in captured["post"]["headers"]
    assert captured["post"]["params"] == {"ids": VALID_APPROVAL_ACTIVITY_ID}
    assert captured["post"]["json"] == {"reason": "agent decision"}
    assert "[SUCCESS] Rejection completed." in stdout
    assert VALID_APPROVAL_ACTIVITY_ID not in stdout
    assert RAW_RESPONSE_APPROVAL_ID not in stdout
    assert '"status": "rejected"' in stdout
    assert '"response"' not in stdout


def test_approve_failure_does_not_expose_resolved_activity_uuid(monkeypatch):
    captured, stdout, _stderr, exit_code = _run_decision_script(
        monkeypatch,
        "approve.py",
        action_payload={
            "error": f"bad activity {VALID_APPROVAL_ACTIVITY_ID}",
            "approvalId": RAW_RESPONSE_APPROVAL_ID,
        },
        action_status_code=400,
    )

    assert exit_code == 1
    assert captured["post"]["params"] == {"ids": VALID_APPROVAL_ACTIVITY_ID}
    assert "[ERROR] Approval request failed with HTTP 400." in stdout
    assert VALID_APPROVAL_ACTIVITY_ID not in stdout
    assert RAW_RESPONSE_APPROVAL_ID not in stdout
    assert "Response:" not in stdout


def test_reject_failure_does_not_expose_resolved_activity_uuid(monkeypatch):
    captured, stdout, _stderr, exit_code = _run_decision_script(
        monkeypatch,
        "reject.py",
        action_payload={
            "error": f"bad activity {VALID_APPROVAL_ACTIVITY_ID}",
            "approvalId": RAW_RESPONSE_APPROVAL_ID,
        },
        action_status_code=400,
    )

    assert exit_code == 1
    assert captured["post"]["params"] == {"ids": VALID_APPROVAL_ACTIVITY_ID}
    assert "[ERROR] Rejection request failed with HTTP 400." in stdout
    assert VALID_APPROVAL_ACTIVITY_ID not in stdout
    assert RAW_RESPONSE_APPROVAL_ID not in stdout
    assert "Response:" not in stdout


def test_approve_rejects_placeholder_id_before_http(monkeypatch):
    captured, stdout, _stderr, exit_code = _run_decision_script(
        monkeypatch,
        "approve.py",
        ids="dummy-id-placeholder",
    )

    assert exit_code == 1
    assert captured == {}
    assert "[ERROR] Invalid SmartCMP Request ID(s)." in stdout
    assert "placeholder values are not valid approval identifiers" in stdout
    assert "RES20260505000010" in stdout


def test_reject_rejects_display_index_before_http(monkeypatch):
    captured, stdout, _stderr, exit_code = _run_decision_script(
        monkeypatch,
        "reject.py",
        ids="1",
    )

    assert exit_code == 1
    assert captured == {}
    assert "display row numbers must be resolved to a SmartCMP Request ID" in stdout


def test_approve_rejects_unknown_request_id_before_approval_http(monkeypatch):
    captured, stdout, _stderr, exit_code = _run_decision_script(
        monkeypatch,
        "approve.py",
        ids="TIC20260502000003",
        pending_payload={"content": []},
    )

    assert exit_code == 1
    assert "get" in captured
    assert "post" not in captured
    assert "No pending SmartCMP approval matched Request ID(s): TIC20260502000003" in stdout


def test_approve_resolves_top_level_request_id_field(monkeypatch):
    captured, stdout, _stderr, exit_code = _run_decision_script(
        monkeypatch,
        "approve.py",
        ids="TIC20260502000003",
        pending_payload={
            "content": [
                {
                    "requestId": "TIC20260502000003",
                    "currentActivity": {"id": VALID_APPROVAL_ACTIVITY_ID},
                }
            ]
        },
    )

    assert exit_code is None
    assert captured["post"]["params"] == {"ids": VALID_APPROVAL_ACTIVITY_ID}
    assert "[SUCCESS] Approval completed." in stdout


def test_approve_resolves_nested_current_activity_request_id(monkeypatch):
    captured, stdout, _stderr, exit_code = _run_decision_script(
        monkeypatch,
        "approve.py",
        ids="RES20260505000029",
        pending_payload={
            "content": [
                {
                    "currentActivity": {
                        "id": VALID_APPROVAL_ACTIVITY_ID,
                        "approvalRequests": [{"workflowId": "RES20260505000029"}],
                    },
                }
            ]
        },
    )

    assert exit_code is None
    assert captured["post"]["params"] == {"ids": VALID_APPROVAL_ACTIVITY_ID}
    assert "[SUCCESS] Approval completed." in stdout


def test_reject_accepts_change_request_id_prefix(monkeypatch):
    captured, stdout, _stderr, exit_code = _run_decision_script(
        monkeypatch,
        "reject.py",
        ids="CHG20260413000011",
        pending_payload={
            "content": [
                {
                    "customizedId": "CHG20260413000011",
                    "currentActivity": {"id": VALID_APPROVAL_ACTIVITY_ID},
                }
            ]
        },
    )

    assert exit_code is None
    assert captured["post"]["params"] == {"ids": VALID_APPROVAL_ACTIVITY_ID}
    assert "[SUCCESS] Rejection completed." in stdout


def test_approve_rejects_activity_uuid_before_loading_config(monkeypatch):
    captured, stdout, _stderr, exit_code = _run_decision_script(
        monkeypatch,
        "approve.py",
        ids=VALID_APPROVAL_ACTIVITY_ID,
    )

    assert exit_code == 1
    assert captured == {}
    assert "expected a SmartCMP Request ID" in stdout
