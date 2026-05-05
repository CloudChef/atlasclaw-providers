# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

import importlib.util
import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "approval"
    / "scripts"
    / "get_request_detail.py"
)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


def _load_module(monkeypatch):
    monkeypatch.setenv("CMP_URL", "https://cmp.example.com")
    monkeypatch.setenv("CMP_COOKIE", "CloudChef-Authenticate=token")
    scripts_dir = str(SCRIPT_PATH.parent)
    inserted = False
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
        inserted = True
    try:
        spec = importlib.util.spec_from_file_location("smartcmp_get_request_detail_script", SCRIPT_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if inserted:
            sys.path.remove(scripts_dir)


def test_detail_uses_chinese_number_label_and_extensible_resource_specs(monkeypatch) -> None:
    module = _load_module(monkeypatch)
    monkeypatch.setattr(module.time, "time", lambda: 1_772_000_120)
    monkeypatch.setattr(sys, "argv", ["get_request_detail.py", "RES20260427000004"])

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        assert url.endswith("/generic-request/current-activity-approval")
        assert params["sort"] == "updatedDate,desc"
        return _FakeResponse(
            {
                "content": [
                    {
                        "id": "internal-request-uuid",
                        "workflowId": "RES20260427000004",
                        "name": "Linux-test-agent",
                        "catalogName": "Linux VM",
                        "applicant": "Admin User",
                        "email": "admin@cmp.com",
                        "createdDate": 1_772_000_000_000,
                        "updatedDate": 1_772_000_060_000,
                        "currentActivity": {
                            "id": "approval-uuid",
                            "taskId": "task-uuid",
                            "processInstanceId": "process-uuid",
                            "processStep": {"name": "Level 1 Approval"},
                            "requestParams": {
                                "_ra_Compute_compute_profile_id": "profile-1",
                                "extensibleParameters": {
                                    "node_1": {
                                        "memory": {"value": 1024},
                                        "cloudEntryType": {"value": "aliyun"},
                                    }
                                },
                            },
                        },
                    }
                ],
            }
        )

    monkeypatch.setattr(module.requests, "get", fake_get)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        module.main()

    rendered = stdout.getvalue()
    assert "编号: RES20260427000004" in rendered
    assert "Request ID:" not in rendered
    assert "内存: 1.0GB" in rendered
    assert "类型: aliyun" in rendered
    assert "无详细规格" not in rendered
    assert "process-uuid" not in rendered
    assert "task-uuid" not in rendered
    assert "internal-request-uuid" not in rendered

    payload = stderr.getvalue().split("##APPROVAL_DETAIL_META_START##\n", 1)[1].split(
        "\n##APPROVAL_DETAIL_META_END##",
        1,
    )[0]
    meta = json.loads(payload)
    assert meta["requestId"] == "RES20260427000004"
    assert meta["resourceSpecs"][:2] == ["内存: 1.0GB", "类型: aliyun"]
    for internal_field in ("approvalId", "internalRequestId", "workflowId", "taskId", "processInstanceId"):
        assert internal_field not in meta


def test_detail_rejects_internal_uuid_before_http(monkeypatch) -> None:
    module = _load_module(monkeypatch)
    internal_id = "15919c7d-67c4-45a6-8603-91c6f6b9e644"
    monkeypatch.setattr(sys, "argv", ["get_request_detail.py", internal_id])

    def unexpected_http_call(*args, **kwargs):
        raise AssertionError("Unexpected HTTP call.")

    monkeypatch.setattr(module.requests, "get", unexpected_http_call)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            module.main()
        except SystemExit as exc:
            assert exc.code == 1

    rendered = stdout.getvalue()
    assert "[ERROR] Invalid SmartCMP Request ID." in rendered
    assert "RES20260505000010" in rendered
    assert internal_id not in rendered
    assert "APPROVAL_DETAIL_META" not in stderr.getvalue()
