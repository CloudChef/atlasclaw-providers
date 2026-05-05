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
    / "list_pending.py"
)


def _load_module():
    scripts_dir = str(SCRIPT_PATH.parent)
    inserted = False
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
        inserted = True
    try:
        spec = importlib.util.spec_from_file_location("smartcmp_list_pending_script", SCRIPT_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if inserted:
            sys.path.remove(scripts_dir)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


def test_build_pending_query_params_defaults_to_all_pending() -> None:
    module = _load_module()

    params = module.build_pending_query_params(now_ms=1_700_000_000_000, days=None)

    assert params["page"] == 1
    assert params["size"] == 50
    assert params["stage"] == "pending"
    assert "startAtMin" not in params
    assert "startAtMax" not in params
    assert "rangeField" not in params


def test_build_pending_query_params_adds_time_window_when_days_specified() -> None:
    module = _load_module()

    now_ms = 1_700_000_000_000
    params = module.build_pending_query_params(now_ms=now_ms, days=7)

    assert params["stage"] == "pending"
    assert params["startAtMax"] == now_ms
    assert params["rangeField"] == "updatedDate"
    assert params["startAtMin"] < now_ms


def test_parse_days_from_argv_accepts_positive_integer_only() -> None:
    module = _load_module()

    assert module.parse_days_from_argv([]) is None
    assert module.parse_days_from_argv(["--days", "7"]) == 7
    assert module.parse_days_from_argv(["--days", "0"]) is None
    assert module.parse_days_from_argv(["--days", "-3"]) is None
    assert module.parse_days_from_argv(["--days", "abc"]) is None


def test_build_meta_exposes_only_canonical_request_id() -> None:
    module = _load_module()
    item = {
        "id": "internal-request-uuid",
        "workflowId": "RES20260427000004",
        "name": "Linux-test-agent",
        "createdDate": 1_772_000_000_000,
        "updatedDate": 1_772_000_060_000,
        "currentActivity": {
            "id": "approval-activity-uuid",
            "taskId": "task-uuid",
            "processInstanceId": "process-uuid",
        },
    }
    item["_priority"] = module.calculate_priority(item, now_ms=1_772_000_120_000)

    meta = module.build_meta([item], now_ms=1_772_000_120_000)

    assert meta[0]["requestId"] == "RES20260427000004"
    for internal_field in ("id", "workflowId", "internalRequestId", "taskId", "processInstanceId"):
        assert internal_field not in meta[0]


def test_build_meta_accepts_request_id_alias_fields() -> None:
    module = _load_module()
    items = [
        {"requestId": "RES20260427000004"},
        {"customizedId": "TIC20260427000005"},
        {"currentActivity": {"workflowId": "CHG20260427000006"}},
    ]
    for item in items:
        item["_priority"] = module.calculate_priority(item, now_ms=1_772_000_120_000)

    meta = module.build_meta(items, now_ms=1_772_000_120_000)

    assert [item["requestId"] for item in meta] == [
        "RES20260427000004",
        "TIC20260427000005",
        "CHG20260427000006",
    ]


def test_main_renders_newest_first_table_and_hides_internal_meta(monkeypatch) -> None:
    module = _load_module()
    monkeypatch.setattr(
        module,
        "require_config",
        lambda: ("https://cmp.example.com/platform-api", "token", {"Cookie": "token"}, None),
    )
    monkeypatch.setattr(module.time, "time", lambda: 1_772_000_120)

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        assert url == "https://cmp.example.com/platform-api/generic-request/current-activity-approval"
        assert params["sort"] == "updatedDate,desc"
        return _FakeResponse(
            {
                "content": [
                    {
                        "id": "old-internal-request-uuid",
                        "workflowId": "RES20260426000003",
                        "name": "older urgent production request",
                        "catalogName": "General Ticket",
                        "applicant": "Admin User",
                        "createdDate": 1_771_900_000_000,
                        "updatedDate": 1_771_900_060_000,
                        "currentActivity": {
                            "id": "old-approval-uuid",
                            "taskId": "old-task-uuid",
                            "processInstanceId": "old-process-uuid",
                        },
                    },
                    {
                        "id": "new-internal-request-uuid",
                        "workflowId": "RES20260427000004",
                        "name": "Linux-test-agent",
                        "catalogName": "Linux VM",
                        "applicant": "Admin User",
                        "createdDate": 1_772_000_000_000,
                        "updatedDate": 1_772_000_060_000,
                        "currentActivity": {
                            "id": "new-approval-uuid",
                            "taskId": "new-task-uuid",
                            "processInstanceId": "new-process-uuid",
                        },
                    },
                ],
                "totalElements": 2,
            }
        )

    monkeypatch.setattr(module.requests, "get", fake_get)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        assert module.main([]) == 0

    rendered = stdout.getvalue()
    internal = stderr.getvalue()
    assert "| # | Request ID | Name |" in rendered
    assert rendered.index("RES20260427000004") < rendered.index("RES20260426000003")
    assert "new-internal-request-uuid" not in rendered
    assert "new-approval-uuid" not in rendered
    assert "new-task-uuid" not in rendered
    assert "new-process-uuid" not in rendered
    assert "##APPROVAL_META_START##" not in rendered

    payload = internal.split("##APPROVAL_META_START##\n", 1)[1].split(
        "\n##APPROVAL_META_END##",
        1,
    )[0]
    meta = json.loads(payload)
    assert [item["requestId"] for item in meta] == ["RES20260427000004", "RES20260426000003"]
    for internal_field in ("id", "workflowId", "internalRequestId", "taskId", "processInstanceId"):
        assert internal_field not in meta[0]
