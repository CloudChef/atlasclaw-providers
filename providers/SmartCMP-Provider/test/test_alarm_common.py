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
    / "src"
    / "smartcmp_provider"
    / "domain"
    / "alarms.py"
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
        target_entity_id="target-1",
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
        "targetEntityId": "target-1",
    }
