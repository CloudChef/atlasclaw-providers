# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    REPO_ROOT
    / "providers"
    / "SmartCMP-Provider"
    / "skills"
    / "alarm"
    / "scripts"
    / "_analysis.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("test_alarm_analysis_module", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def make_alert(**overrides):
    alert = {
        "id": "alert-1",
        "alarmPolicyId": "policy-1",
        "alarmPolicyName": "CPU High",
        "status": "ALERT_FIRING",
        "level": 3,
        "triggerAt": "2026-03-27T00:00:00Z",
        "lastTriggerAt": "2026-03-28T00:00:00Z",
        "triggerCount": 5,
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
    alert.update(overrides)
    return alert


def make_policy(**overrides):
    policy = {
        "id": "policy-1",
        "name": "CPU High",
        "description": "CPU usage over threshold",
        "category": "ALARM_CATEGORY_RESOURCE",
        "type": "ALARM_TYPE_METRIC",
        "metric": "node_cpu_seconds_total",
        "expression": "cpu_usage > 90",
        "resourceType": "VirtualMachine",
    }
    policy.update(overrides)
    return policy


def test_normalize_alert_fact_merges_alert_and_rule_fields():
    module = load_module()
    fact = module.normalize_alert_fact(make_alert(), make_policy())

    assert fact["alert_id"] == "alert-1"
    assert fact["status"] == "ALERT_FIRING"
    assert fact["level"] == 3
    assert fact["trigger_count"] == 5
    assert fact["trigger_at"] == "2026-03-27T00:00:00Z"
    assert fact["last_trigger_at"] == "2026-03-28T00:00:00Z"
    assert fact["resource"]["deployment_id"] == "deployment-1"
    assert fact["resource"]["resource_external_name"] == "worker-01"
    assert fact["resource"]["entity_instance_id"] == ["entity-1"]
    assert fact["resource"]["resource_context_available"] is False
    assert fact["resource"]["resolved_resources"] == []
    assert fact["rule"]["policy_id"] == "policy-1"
    assert fact["rule"]["name"] == "CPU High"
    assert fact["rule"]["metric"] == "node_cpu_seconds_total"
    assert fact["rule"]["expression"] == "cpu_usage > 90"
    assert fact["rule"]["resource_type"] == "VirtualMachine"


def test_normalize_alert_fact_merges_datasource_resource_context():
    module = load_module()
    fact = module.normalize_alert_fact(
        make_alert(),
        make_policy(),
        resource_records=[
            {
                "resourceId": "entity-1",
                "summary": {
                    "name": "vm-01",
                    "resourceType": "VirtualMachine",
                    "componentType": "cloudchef.nodes.Compute",
                    "status": "RUNNING",
                    "osType": "Linux",
                    "osDescription": "Ubuntu 22.04",
                },
                "resource": {"name": "vm-01"},
                "normalized": {
                    "type": "cloudchef.nodes.Compute",
                    "properties": {"instanceType": "c6.large"},
                },
                "fetchStatus": "ok",
                "errors": [],
            }
        ],
    )

    assert fact["resource"]["resource_context_available"] is True
    assert fact["resource"]["resolved_resource_count"] == 1
    assert fact["resource"]["resolved_name"] == "vm-01"
    assert fact["resource"]["resolved_type"] == "cloudchef.nodes.Compute"
    assert fact["resource"]["resolved_status"] == "RUNNING"
    assert fact["resource"]["resolved_resources"][0]["normalized"]["type"] == "cloudchef.nodes.Compute"


def test_classify_alert_pattern_distinguishes_persistent_and_noisy():
    module = load_module()

    persistent = module.normalize_alert_fact(
        make_alert(triggerCount=6, triggerAt="2026-03-27T00:00:00Z", lastTriggerAt="2026-03-28T00:00:00Z"),
        make_policy(),
    )
    noisy = module.normalize_alert_fact(
        make_alert(triggerCount=8, triggerAt="2026-03-28T00:00:00Z", lastTriggerAt="2026-03-28T00:30:00Z", level=1),
        make_policy(),
    )

    assert module.classify_alert_pattern(persistent) == "persistent"
    assert module.classify_alert_pattern(noisy) == "noisy"


def test_build_recommendations_include_required_fields():
    module = load_module()
    fact = module.normalize_alert_fact(make_alert(), make_policy())
    assessment = module.build_assessment(fact)
    recommendations = module.build_recommendations(fact, assessment)

    assert recommendations
    for item in recommendations:
        assert set(item) == {"action", "confidence", "reason", "evidence"}
        assert isinstance(item["evidence"], list)
        assert item["evidence"]
