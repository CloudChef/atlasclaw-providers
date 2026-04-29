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


class _FakeResponse:
    text = '{"success": true}'

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return {"success": True}


def _run_decision_script(monkeypatch, script_name: str):
    script_path = SCRIPT_DIR / script_name
    module_name = f"smartcmp_{script_path.stem}_robot_test"
    captured = {}

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
    monkeypatch.setenv("IDS", "approval-1")
    monkeypatch.setenv("REASON", "agent decision")
    monkeypatch.delenv("CMP_URL", raising=False)
    monkeypatch.delenv("CMP_COOKIE", raising=False)

    def fake_post(url, headers=None, params=None, json=None, verify=None, timeout=None):
        captured.update(
            {
                "url": url,
                "headers": dict(headers or {}),
                "params": dict(params or {}),
                "json": dict(json or {}),
                "verify": verify,
                "timeout": timeout,
            }
        )
        return _FakeResponse()

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(sys, "argv", [script_path.name])

    stdout = io.StringIO()
    stderr = io.StringIO()
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)

    return captured, stdout.getvalue(), stderr.getvalue()


def test_approve_uses_robot_provider_token_from_require_config(monkeypatch):
    captured, stdout, _stderr = _run_decision_script(monkeypatch, "approve.py")

    assert captured["url"] == "https://cmp.example.com/platform-api/approval-activity/approve/batch"
    assert captured["headers"]["Authorization"] == "Bearer cmp_tk_test_robot"
    assert "CloudChef-Authenticate" not in captured["headers"]
    assert captured["params"] == {"ids": "approval-1"}
    assert captured["json"] == {"reason": "agent decision"}
    assert "[SUCCESS] Approval completed." in stdout


def test_reject_uses_robot_provider_token_from_require_config(monkeypatch):
    captured, stdout, _stderr = _run_decision_script(monkeypatch, "reject.py")

    assert captured["url"] == "https://cmp.example.com/platform-api/approval-activity/reject/batch"
    assert captured["headers"]["Authorization"] == "Bearer cmp_tk_test_robot"
    assert "CloudChef-Authenticate" not in captured["headers"]
    assert captured["params"] == {"ids": "approval-1"}
    assert captured["json"] == {"reason": "agent decision"}
    assert "[SUCCESS] Rejection completed." in stdout
