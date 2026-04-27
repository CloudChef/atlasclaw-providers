# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    REPO_ROOT
    / "providers"
    / "SmartCMP-Provider"
    / "skills"
    / "alarm"
    / "scripts"
    / "_alarm_common.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("test_alarm_common_module", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def test_action_status_map():
    module = load_module()

    assert module.ACTION_STATUS_MAP["mute"] == "ALERT_MUTED"
    assert module.ACTION_STATUS_MAP["resolve"] == "ALERT_RESOLVED"
    assert module.ACTION_STATUS_MAP["reopen"] == "ALERT_FIRING"


def test_normalize_timestamp_supports_multiple_inputs():
    module = load_module()

    assert module.normalize_timestamp(1704164645000) == "2024-01-02T03:04:05Z"
    assert module.normalize_timestamp(1704164645) == "2024-01-02T03:04:05Z"
    assert module.normalize_timestamp("2024-01-02T11:04:05+08:00") == "2024-01-02T03:04:05Z"
    assert module.normalize_timestamp("2024-01-02T03:04:05Z") == "2024-01-02T03:04:05Z"
    assert module.normalize_timestamp("") == ""
    assert module.normalize_timestamp(None) == ""


def test_extract_items_tolerates_multiple_payload_shapes():
    module = load_module()
    raw_items = [{"id": "a1"}, {"id": "a2"}]

    assert module.extract_items(raw_items) == raw_items
    assert module.extract_items({"content": raw_items}) == raw_items
    assert module.extract_items({"data": raw_items}) == raw_items
    assert module.extract_items({"result": raw_items}) == raw_items
    assert module.extract_items({"data": {"items": raw_items}}) == raw_items


def test_extract_policy_tolerates_direct_and_wrapped_payloads():
    module = load_module()
    policy = {
        "id": "policy-1",
        "name": "CPU High",
        "nameZh": "CPU High Zh",
        "metric": "cpu_usage",
        "expression": "avg(cpu_usage) > 80",
        "resourceType": "VirtualMachine",
    }
    alert_like_payload = {"id": "alert-1", "name": "Alert row", "status": "ALERT_FIRING", "level": 3}

    assert module.extract_policy(policy) == policy
    assert module.extract_policy({"policy": policy}) == policy
    assert module.extract_policy({"data": {"policy": policy}}) == policy
    assert module.extract_policy({"content": policy}) == policy
    assert module.extract_policy(alert_like_payload) == {}


def test_build_list_params_omits_blank_values():
    module = load_module()

    params = module.build_list_params(page=2, size=25, status="ALERT_FIRING", keyword="", policy_id=None)

    assert params == {
        "page": 2,
        "size": 25,
        "status": "ALERT_FIRING",
    }


def test_build_list_params_supports_time_window_and_list_filters():
    module = load_module()

    params = module.build_list_params(
        statuses="ALERT_FIRING, ALERT_MUTED",
        days=2,
        level=3,
        deployment_id="deployment-1",
        entity_instance_id="entity-1",
        node_instance_id="node-1",
        sort="triggerAt,desc",
        now_ms=1704067200000,
    )

    assert params == {
        "page": 1,
        "size": 20,
        "sort": "triggerAt,desc",
        "triggerAtMin": 1703894400000,
        "triggerAtMax": 1704067200000,
        "status": ["ALERT_FIRING", "ALERT_MUTED"],
        "level": 3,
        "deploymentId": "deployment-1",
        "entityInstanceId": "entity-1",
        "nodeInstanceId": "node-1",
    }


def test_request_json_uses_expected_request_shape(monkeypatch):
    module = load_module()
    captured = {}

    class FakeResponse:
        status_code = 200
        text = '{"ok": true}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    def fake_request(**kwargs):
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(
        module,
        "get_connection",
        lambda content_type="application/json; charset=utf-8": (
            "https://cmp.example.com/platform-api",
            {"CloudChef-Authenticate": "token"},
            {},
        ),
    )
    monkeypatch.setattr(module.requests, "request", fake_request)

    result = module.request_json("GET", "/alarm-alert", params={"page": 1})

    assert result == {"ok": True}
    assert captured["method"] == "GET"
    assert captured["url"] == "https://cmp.example.com/platform-api/alarm-alert"
    assert captured["params"] == {"page": 1}
    assert "json" not in captured


def test_request_json_wraps_request_errors(monkeypatch):
    module = load_module()

    def fake_request(**_kwargs):
        raise module.requests.RequestException("network down")

    monkeypatch.setattr(
        module,
        "get_connection",
        lambda content_type="application/json; charset=utf-8": (
            "https://cmp.example.com/platform-api",
            {"CloudChef-Authenticate": "token"},
            {},
        ),
    )
    monkeypatch.setattr(module.requests, "request", fake_request)

    with pytest.raises(RuntimeError, match="SmartCMP request failed"):
        module.request_json("GET", "/alarm-alert")
