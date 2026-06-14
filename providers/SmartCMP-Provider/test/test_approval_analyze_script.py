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
    / "analyze_request.py"
)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class _InvalidJsonResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self):
        raise ValueError("invalid catalog json")


def localized(default: str, zh_cn: str) -> dict[str, object]:
    return {
        "default": default,
        "translations": {
            "en-US": default,
            "zh-CN": zh_cn,
        },
    }


def _load_module(monkeypatch):
    monkeypatch.setenv("CMP_URL", "https://cmp.example.com")
    monkeypatch.setenv("CMP_COOKIE", "CloudChef-Authenticate=token")
    scripts_dir = str(SCRIPT_PATH.parent)
    inserted = False
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
        inserted = True
    try:
        spec = importlib.util.spec_from_file_location("smartcmp_analyze_approval_script", SCRIPT_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if inserted:
            sys.path.remove(scripts_dir)


def _forbid_mutating_requests(module, monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise AssertionError("analysis tool must not use mutating HTTP methods")

    monkeypatch.setattr(module.requests, "post", fail, raising=False)
    monkeypatch.setattr(module.requests, "put", fail, raising=False)
    monkeypatch.setattr(module.requests, "patch", fail, raising=False)
    monkeypatch.setattr(module.requests, "delete", fail, raising=False)


def _analysis_meta(stderr: str) -> dict[str, object]:
    payload = stderr.split("##APPROVAL_ANALYSIS_META_START##\n", 1)[1].split(
        "\n##APPROVAL_ANALYSIS_META_END##",
        1,
    )[0]
    return json.loads(payload)


def test_analyze_request_is_read_only_and_returns_object_actions(monkeypatch) -> None:
    module = _load_module(monkeypatch)
    _forbid_mutating_requests(module, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["analyze_request.py", "RES20260427000004"])
    called_urls: list[str] = []

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        called_urls.append(url)
        if url.endswith("/catalogs/catalog-linux"):
            return _FakeResponse(
                {
                    "id": "catalog-linux",
                    "name": "Linux VM",
                    "instructions": (
                        "# Pre Approval Instructions\n"
                        "- Approve only when the business purpose is concrete.\n"
                        "- Reject oversized requests without workload evidence.\n"
                    ),
                }
            )
        assert url.endswith("/generic-request/current-activity-approval")
        assert params["stage"] == "pending"
        return _FakeResponse(
            {
                "content": [
                    {
                        "workflowId": "RES20260427000004",
                        "name": "linux-prod-api",
                        "catalogId": "catalog-linux",
                        "catalogName": "Linux VM",
                        "applicant": "Admin User",
                        "email": "admin@cmp.com",
                        "description": "Run the production API workload for finance reporting.",
                        "createdDate": 1_772_000_000_000,
                        "updatedDate": 1_772_000_060_000,
                        "chargePredictResult": {"totalCost": 20},
                        "currentActivity": {
                            "id": "approval-uuid",
                            "processStep": {"name": "Level 1 Approval"},
                            "requestParams": {
                                "resourceSpecs": {
                                    "node_1": {
                                        "cpu": {"value": 2},
                                        "memory": {"value": 4096},
                                    }
                                }
                            },
                        },
                        "exts": {
                            "approval_state": "PENDING",
                            "approval_type": "PROVISION_BP",
                            "approval_id": "approval-uuid",
                        },
                    }
                ],
            }
        )

    monkeypatch.setattr(module.requests, "get", fake_get)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        assert module.main() == 0

    rendered = stdout.getvalue()
    assert "Approval Analysis: RES20260427000004" in rendered
    assert "Decision Guidance: manual_review_required" in rendered
    assert "Catalog Pre-Approval Instructions:" in rendered
    assert "approve.py" not in rendered
    assert "reject.py" not in rendered
    assert not any("/approve" in url or "/reject" in url for url in called_urls)

    meta = _analysis_meta(stderr.getvalue())
    assert meta["readOnly"] is True
    assert meta["object_type"] == "approval_request"
    assert meta["object_id"] == "RES20260427000004"
    assert meta["catalogPolicy"]["hasPreApprovalInstructions"] is True
    assert meta["analysis"]["decision_guidance"] == "manual_review_required"
    assert meta["analysis"]["confidence"] == "low"
    assert any("Catalog policy exists" in concern for concern in meta["analysis"]["concerns"])
    assert [action["display_label"] for action in meta["object_actions"]] == [
        localized("Open", "打开"),
        localized("Analyze", "分析"),
        localized("Approve", "同意"),
        localized("Reject", "拒绝"),
    ]
    assert meta["object_actions"][1]["agent_prompt"] == localized(
        "Run read-only approval analysis for RES20260427000004",
        "只读分析审批请求 RES20260427000004",
    )


def test_analyze_request_flags_vague_business_purpose(monkeypatch) -> None:
    module = _load_module(monkeypatch)
    _forbid_mutating_requests(module, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["analyze_request.py", "TIC20260427000005"])

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        assert url.endswith("/generic-request/current-activity-approval")
        return _FakeResponse(
            {
                "content": [
                    {
                        "workflowId": "TIC20260427000005",
                        "name": "general-ticket",
                        "catalogName": "General Request",
                        "description": "test",
                        "createdDate": 1_772_000_000_000,
                        "updatedDate": 1_772_000_060_000,
                        "currentActivity": {"requestParams": {}},
                    }
                ],
            }
        )

    monkeypatch.setattr(module.requests, "get", fake_get)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(stdout), redirect_stderr(stderr):
        assert module.main() == 0

    rendered = stdout.getvalue()
    assert "Decision Guidance: manual_review_required" in rendered
    assert "Business purpose is missing or too vague" in rendered

    meta = _analysis_meta(stderr.getvalue())
    assert meta["analysis"]["decision_guidance"] == "manual_review_required"
    assert "Business purpose is missing or too vague" in meta["analysis"]["concerns"][0]
    assert [action["display_label"] for action in meta["object_actions"]] == [
        localized("Analyze", "分析"),
        localized("Approve", "同意"),
        localized("Reject", "拒绝"),
    ]


def test_analyze_request_fails_closed_when_catalog_json_is_invalid(monkeypatch) -> None:
    module = _load_module(monkeypatch)
    _forbid_mutating_requests(module, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["analyze_request.py", "RES20260427000006"])

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        if url.endswith("/catalogs/catalog-invalid"):
            return _InvalidJsonResponse()
        assert url.endswith("/generic-request/current-activity-approval")
        return _FakeResponse(
            {
                "content": [
                    {
                        "workflowId": "RES20260427000006",
                        "name": "linux-prod-api",
                        "catalogId": "catalog-invalid",
                        "catalogName": "Linux VM",
                        "applicant": "Admin User",
                        "description": "Run the production API workload for finance reporting.",
                        "createdDate": 1_772_000_000_000,
                        "updatedDate": 1_772_000_060_000,
                        "chargePredictResult": {"totalCost": 20},
                        "currentActivity": {
                            "id": "approval-uuid",
                            "processStep": {"name": "Level 1 Approval"},
                            "requestParams": {
                                "resourceSpecs": {
                                    "node_1": {
                                        "cpu": {"value": 2},
                                        "memory": {"value": 4096},
                                    }
                                }
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
        assert module.main() == 0

    rendered = stdout.getvalue()
    assert "Decision Guidance: manual_review_required" in rendered
    assert "Catalog policy could not be fetched from SmartCMP." in rendered

    meta = _analysis_meta(stderr.getvalue())
    assert meta["catalogPolicy"]["status"] == "unavailable"
    assert meta["analysis"]["decision_guidance"] == "manual_review_required"


def test_analyze_request_fails_closed_when_catalog_payload_is_not_an_object(monkeypatch) -> None:
    module = _load_module(monkeypatch)
    _forbid_mutating_requests(module, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["analyze_request.py", "RES20260427000007"])

    def fake_get(url, headers=None, params=None, verify=None, timeout=None):
        if url.endswith("/catalogs/catalog-list"):
            return _FakeResponse([{"id": "catalog-list"}])
        assert url.endswith("/generic-request/current-activity-approval")
        return _FakeResponse(
            {
                "content": [
                    {
                        "workflowId": "RES20260427000007",
                        "name": "linux-prod-api",
                        "catalogId": "catalog-list",
                        "catalogName": "Linux VM",
                        "applicant": "Admin User",
                        "description": "Run the production API workload for finance reporting.",
                        "createdDate": 1_772_000_000_000,
                        "updatedDate": 1_772_000_060_000,
                        "chargePredictResult": {"totalCost": 20},
                        "currentActivity": {
                            "id": "approval-uuid",
                            "processStep": {"name": "Level 1 Approval"},
                            "requestParams": {
                                "resourceSpecs": {
                                    "node_1": {
                                        "cpu": {"value": 2},
                                        "memory": {"value": 4096},
                                    }
                                }
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
        assert module.main() == 0

    rendered = stdout.getvalue()
    assert "Decision Guidance: manual_review_required" in rendered
    assert "Catalog policy could not be fetched from SmartCMP." in rendered

    meta = _analysis_meta(stderr.getvalue())
    assert meta["catalogPolicy"]["status"] == "unavailable"
    assert meta["catalogPolicy"]["error"] == "catalog response is not a JSON object"
    assert meta["analysis"]["decision_guidance"] == "manual_review_required"
