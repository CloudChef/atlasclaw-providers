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
    / "analyze_alert.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("test_analyze_alert_module", MODULE_PATH)
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
        r"##ALARM_ANALYSIS_START##\s*(.*?)\s*##ALARM_ANALYSIS_END##",
        output,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def make_alert():
    return {
        "id": "alert-1",
        "alarmPolicyId": "policy-1",
        "alarmPolicyName": "CPU High",
        "status": "ALERT_FIRING",
        "level": 3,
        "triggerCount": 5,
        "triggerAt": "2026-03-27T00:00:00Z",
        "lastTriggerAt": "2026-03-28T00:00:00Z",
        "deploymentId": "deployment-1",
        "deploymentName": "prod-app",
        "nodeInstanceId": "node-1",
        "resourceExternalId": "i-abc",
        "resourceExternalName": "worker-01",
        "entityInstanceId": ["entity-1"],
        "entityInstanceName": "vm-01",
        "metricName": "node_cpu_seconds_total",
        "queryExpression": "avg(rate(node_cpu_seconds_total[5m]))",
        "ruleExpression": "cpu_usage > 90",
    }


def make_policy():
    return {
        "id": "policy-1",
        "name": "CPU High",
        "description": "CPU usage over threshold",
        "category": "ALARM_CATEGORY_RESOURCE",
        "type": "ALARM_TYPE_METRIC",
        "metric": "node_cpu_seconds_total",
        "expression": "cpu_usage > 90",
        "resourceType": "VirtualMachine",
    }


def test_main_emits_human_summary_and_analysis_block(monkeypatch):
    module = load_module()
    captured = {}

    def fake_get_json(path, *, params=None, timeout=30):
        captured[path] = params
        if path == "/alarm-alert/alert-1":
            return make_alert()
        if path == "/alarm-policies/policy-1":
            return make_policy()
        if path == "/alarm-overview/recent":
            return [{"alarmPolicyId": "policy-1", "status": "ALERT_FIRING"}]
        if path == "/alarm-overview/alarm-trend":
            return [{"date": "2026-03-28", "count": 5}]
        if path == "/stats/alarm-alert/detail":
            return [{"alarmPolicyId": "policy-1", "deploymentId": "deployment-1"}]
        raise AssertionError(f"Unexpected path: {path}")

    monkeypatch.setattr(module, "get_json", fake_get_json)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["alert-1", "--days", "7"])

    output = stdout.getvalue()
    assert exit_code == 0
    assert "Analyzed 1 alert(s)." in output
    assert "persistent" in output
    payload = extract_payload(output)
    assert set(payload) == {
        "alert_ids",
        "facts",
        "assessment",
        "recommendations",
        "suggested_status_operation",
    }
    assert payload["alert_ids"] == ["alert-1"]
    assert payload["facts"][0]["alert_id"] == "alert-1"
    assert payload["facts"][0]["rule"]["policy_id"] == "policy-1"
    assert payload["assessment"]["pattern"] == "persistent"
    assert payload["assessment"]["risk"] == "high"
    assert payload["recommendations"]
    assert "suggested_status_operation" in payload
    assert captured["/alarm-overview/alarm-trend"] == {"days": 7}
    assert captured["/stats/alarm-alert/detail"] == {"alertId": "alert-1"}


def test_main_degrades_when_optional_context_calls_fail(monkeypatch):
    module = load_module()

    def fake_get_json(path, *, params=None, timeout=30):
        if path == "/alarm-alert/alert-1":
            return make_alert()
        if path == "/alarm-policies/policy-1":
            return make_policy()
        raise RuntimeError("optional context unavailable")

    monkeypatch.setattr(module, "get_json", fake_get_json)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["alert-1"])

    output = stdout.getvalue()
    payload = extract_payload(output)
    assert exit_code == 0
    assert "Analyzed 1 alert(s)." in output
    assert payload["facts"][0]["alert_id"] == "alert-1"
    assert payload["assessment"]["pattern"] == "persistent"
    assert payload["recommendations"]
    assert payload["suggested_status_operation"]["should_operate"] is False


def test_main_returns_error_when_policy_reference_is_missing(monkeypatch):
    module = load_module()
    alert = make_alert()
    alert.pop("alarmPolicyId")

    def fake_get_json(path, *, params=None, timeout=30):
        if path == "/alarm-alert/alert-1":
            return alert
        raise AssertionError(f"Unexpected path: {path}")

    monkeypatch.setattr(module, "get_json", fake_get_json)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["alert-1"])

    output = stdout.getvalue()
    assert exit_code == 1
    assert "does not reference an alarm policy" in output


def test_parse_args_rejects_non_positive_days():
    module = load_module()

    with pytest.raises(SystemExit):
        module.parse_args(["alert-1", "--days", "0"])
