# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

import importlib.util
import io
import json
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    REPO_ROOT
    / "providers"
    / "SmartCMP-Provider"
    / "skills"
    / "resource"
    / "scripts"
    / "list_resource_operations.py"
)


class DummyResponse:
    def __init__(self, status_code=200, text="{}", body=None):
        self.status_code = status_code
        self.text = text
        self._body = [] if body is None else body

    def json(self):
        return self._body


def load_module():
    spec = importlib.util.spec_from_file_location("test_resource_operations_module", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def extract_meta(stderr: str):
    match = re.search(
        r"##RESOURCE_OPERATIONS_META_START##\s*(.*?)\s*##RESOURCE_OPERATIONS_META_END##",
        stderr,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def test_parse_resource_reference_extracts_category_and_resource_id_from_detail_url():
    module = load_module()

    category, resource_id = module.parse_resource_reference(
        "https://192.168.176.29/#/main/virtual-machines/"
        "0b0c89dc-3188-4783-82ff-b83a3e4a56d7/details"
    )

    assert category == "virtual-machines"
    assert resource_id == "0b0c89dc-3188-4783-82ff-b83a3e4a56d7"


def test_parse_resource_reference_uses_default_category_for_raw_id():
    module = load_module()

    assert module.parse_resource_reference("res-1") == ("virtual-machines", "res-1")
    assert module.parse_resource_reference("res-1", "databases") == ("databases", "res-1")


def test_operation_filter_keeps_only_current_user_executable_no_parameter_actions():
    module = load_module()
    operations = [
        {"id": "refresh", "name": "REFRESH_RESOURCE", "enabled": True, "parameters": "{}"},
        {"id": "stop", "name": "STOP", "enabled": False, "disabledMsgZh": "请先启动实例"},
        {"id": "web_ssh", "name": "Web SSH", "enabled": True, "webOperation": True},
        {"id": "update_connection_info", "enabled": True, "inputsForm": "{}"},
        {"id": "resize", "enabled": True, "parameters": '{"cpu": 2}'},
    ]

    executable = [item for item in operations if module.operation_is_executable(item)]

    assert [item["id"] for item in executable] == ["refresh"]
    assert module.operation_rejection_reason(operations[1]) == "请先启动实例"
    assert "web UI" in module.operation_rejection_reason(operations[2])
    assert "form input" in module.operation_rejection_reason(operations[3])
    assert "requires parameters" in module.operation_rejection_reason(operations[4])


def test_main_queries_resource_scoped_user_operations_and_emits_metadata(monkeypatch):
    module = load_module()
    calls = {}

    def fake_require_config():
        return "https://cmp.example.com/platform-api", "token", {"CloudChef-Authenticate": "token"}, {}

    def fake_get(url, headers, verify, timeout):
        calls["url"] = url
        calls["headers"] = headers
        calls["verify"] = verify
        calls["timeout"] = timeout
        return DummyResponse(
            body=[
                {
                    "id": "refresh",
                    "name": "REFRESH_RESOURCE",
                    "enabled": True,
                    "parameters": "{}",
                    "actionCategory": {"name": "MACHINE_TOP_ACTION"},
                    "supportBatchAction": True,
                },
                {
                    "id": "stop",
                    "name": "STOP",
                    "enabled": False,
                    "disabledMsgZh": "请先启动实例",
                },
            ]
        )

    monkeypatch.setattr(module, "require_config", fake_require_config)
    monkeypatch.setattr(module.requests, "get", fake_get)

    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = module.main(
            [
                "https://cmp.example/#/main/virtual-machines/res-1/details",
            ]
        )

    output = stdout.getvalue()
    meta = extract_meta(stderr.getvalue())

    assert exit_code == 0
    assert calls["url"] == (
        "https://cmp.example.com/platform-api/nodes/virtual-machines/res-1/resource-actions"
    )
    assert calls["headers"]["CloudChef-Authenticate"] == "token"
    assert calls["verify"] is False
    assert calls["timeout"] == 30
    assert "REFRESH_RESOURCE (refresh)" in output
    assert "STOP" not in output
    assert meta[0]["id"] == "refresh"
    assert meta[0]["supportBatchAction"] is True
