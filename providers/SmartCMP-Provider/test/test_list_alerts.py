# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

import importlib.util
import io
import json
import re
import sys
from contextlib import redirect_stdout
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
    / "list_alerts.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("test_list_alerts_module", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def extract_meta(output: str):
    match = re.search(
        r"##ALARM_META_START##\s*(.*?)\s*##ALARM_META_END##",
        output,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def test_main_prints_numbered_summary_and_meta_block(monkeypatch):
    module = load_module()
    captured = {}
    payload = {
        "content": [
            {
                "id": "alert-1",
                "alarmPolicyId": "policy-1",
                "alarmPolicyName": "CPU High",
                "status": "ALERT_FIRING",
                "level": 3,
                "triggerAt": "2026-03-28T01:02:03Z",
                "lastTriggerAt": "2026-03-28T04:05:06Z",
                "triggerCount": 4,
                "deploymentId": "deployment-1",
                "deploymentName": "prod-app",
                "entityInstanceId": ["entity-1"],
                "entityInstanceName": "vm-01",
                "nodeInstanceId": "node-1",
                "resourceExternalId": "i-abc",
                "resourceExternalName": "worker-01",
            },
            {
                "id": "alert-2",
                "alarmPolicyId": "policy-2",
                "alarmPolicyName": "Memory High",
                "status": "ALERT_MUTED",
                "level": 2,
                "triggerAt": "2026-03-28T02:00:00Z",
                "lastTriggerAt": "2026-03-28T03:00:00Z",
                "triggerCount": 1,
                "deploymentId": "deployment-2",
                "deploymentName": "qa-app",
                "entityInstanceId": ["entity-2"],
                "entityInstanceName": "vm-02",
                "nodeInstanceId": "node-2",
                "resourceExternalId": "i-def",
                "resourceExternalName": "worker-02",
            },
        ],
        "totalElements": 2,
    }

    def fake_get_json(path, *, params=None, timeout=30):
        captured["path"] = path
        captured["params"] = params
        return payload

    monkeypatch.setattr(module, "get_json", fake_get_json)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["--status", "ALERT_FIRING", "--days", "3", "--size", "10"])

    output = stdout.getvalue()
    assert exit_code == 0
    assert "Found 2 alert(s)." in output
    assert "[1] CPU High" in output
    assert "worker-01" in output
    assert captured["path"] == "/alarm-alert"
    assert captured["params"]["status"] == ["ALERT_FIRING"]
    assert captured["params"]["size"] == 10

    meta = extract_meta(output)
    assert len(meta) == 2
    assert meta[0]["index"] == 1
    assert meta[0]["alertId"] == "alert-1"
    assert meta[0]["alarmPolicyId"] == "policy-1"
    assert meta[0]["status"] == "ALERT_FIRING"
    assert meta[0]["level"] == 3
    assert meta[0]["deploymentId"] == "deployment-1"
    assert meta[0]["nodeInstanceId"] == "node-1"
    assert meta[0]["resourceExternalId"] == "i-abc"
    assert meta[0]["resourceExternalName"] == "worker-01"
    assert meta[1]["index"] == 2
    assert meta[1]["alertId"] == "alert-2"
    assert meta[1]["alarmPolicyId"] == "policy-2"
    assert meta[1]["status"] == "ALERT_MUTED"
    assert meta[1]["level"] == 2


def test_main_prints_empty_state(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "get_json", lambda *args, **kwargs: {"content": [], "totalElements": 0})

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["--status", "ALERT_RESOLVED"])

    output = stdout.getvalue()
    assert exit_code == 0
    assert "No alerts found." in output
    assert extract_meta(output) == []


def test_main_prints_error_and_returns_non_zero(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "get_json", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["--status", "ALERT_FIRING"])

    output = stdout.getvalue()
    assert exit_code == 1
    assert "[ERROR] boom" in output


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--days", "0"),
        ("--days", "-1"),
        ("--page", "0"),
        ("--size", "0"),
    ],
)
def test_parse_args_rejects_non_positive_integers(flag, value):
    module = load_module()

    with pytest.raises(SystemExit):
        module.parse_args([flag, value])
