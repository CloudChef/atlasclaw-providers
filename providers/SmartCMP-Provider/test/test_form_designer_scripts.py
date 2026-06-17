# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

import json
import re

import pytest

from form_designer_test_utils import (
    FakeResponse,
    SCRIPTS_DIR,
    SKILL_ROOT,
    extract_meta,
    load_module,
    run_main,
)

def test_design_form_script_outputs_parseable_schema_and_metadata(monkeypatch):
    schema_json = json.dumps(
        {
            "properties": {
                "hostname": {
                    "title": "主机名",
                    "type": "string",
                    "widget": {"id": "string"},
                }
            }
        },
        ensure_ascii=False,
    )

    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "new",
            "--schema-json",
            schema_json,
            "--change-summary",
            "生成一个包含主机名字段的表单。",
        ],
        monkeypatch,
    )
    meta = extract_meta(stderr, "FORM_DESIGN_META")

    assert exit_code == 0
    assert "生成一个包含主机名字段的表单。" in stdout
    assert "```json" in stdout
    assert meta["mode"] == "new"
    assert meta["schema"]["properties"]["hostname"]["id"] == "hostname"

def test_design_form_script_rejects_invalid_schema_json(monkeypatch):
    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        ["--mode", "new", "--schema-json", "[not-json]"],
        monkeypatch,
    )

    assert exit_code == 1
    assert "schema_json is not valid JSON" in stdout
    assert "FORM_DESIGN_META" not in stderr

def test_design_form_modify_mode_can_read_and_normalize_source_when_schema_omitted(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, verify=None, timeout=None):
        captured["url"] = url
        return FakeResponse(
            {
                "name": "infoblox",
                "content": {
                    "schema": {
                        "properties": {
                            "infoblox_ip": {"title": "IP", "widget": {"id": "string"}},
                        },
                    }
                },
            }
        )

    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "modify",
            "--form-url",
            "https://cmp.example.com/#/main/service-model/forms/edit/"
            "42607f38-2c63-4649-a8de-efa031db4544",
        ],
        monkeypatch,
        fake_get=fake_get,
    )
    meta = extract_meta(stderr, "FORM_DESIGN_META")

    assert exit_code == 0
    assert captured["url"].endswith("/forms/42607f38-2c63-4649-a8de-efa031db4544")
    assert "normalized the source form without changes" in stdout
    assert meta["source"]["formId"] == "42607f38-2c63-4649-a8de-efa031db4544"
    assert meta["schema"]["properties"]["infoblox_ip"]["id"] == "infoblox_ip"

def test_read_form_script_reads_and_normalizes_existing_form(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, verify=None, timeout=None):
        captured["url"] = url
        return FakeResponse(
            {
                "name": "infoblox",
                "description": None,
                "content": {
                    "schema": {
                        "properties": {
                            "infoblox_ip": {"title": "IP", "widget": {"id": "string"}},
                        },
                    },
                    "designMode": "JSON",
                },
            }
        )

    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "read_form.py",
        [
            "https://cmp.example.com/#/main/service-model/forms/edit/42607f38-2c63-4649-a8de-efa031db4544"
        ],
        monkeypatch,
        fake_get=fake_get,
    )
    meta = extract_meta(stderr, "FORM_SCHEMA_META")

    assert exit_code == 0
    assert captured["url"].endswith("/forms/42607f38-2c63-4649-a8de-efa031db4544")
    assert "SmartCMP Form: infoblox" in stdout
    assert meta["formId"] == "42607f38-2c63-4649-a8de-efa031db4544"
    assert meta["schema"]["properties"]["infoblox_ip"]["id"] == "infoblox_ip"

def test_read_form_script_rejects_invalid_url_before_http_get(monkeypatch):
    calls = []

    def fake_get(url, headers=None, verify=None, timeout=None):
        calls.append(url)
        return FakeResponse({})

    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "read_form.py",
        ["https://other.example.com/#/main/service-model/forms/edit/not-a-uuid"],
        monkeypatch,
        fake_get=fake_get,
    )

    assert exit_code == 1
    assert calls == []
    assert "form_url must belong to the selected SmartCMP provider instance" in stdout
    assert "FORM_SCHEMA_META" not in stderr

def test_form_designer_scripts_do_not_use_cmp_write_methods():
    script_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in SCRIPTS_DIR.glob("*.py")
        if path.name != "__init__.py"
    )

    assert "requests.post" not in script_text
    assert "requests.put" not in script_text
    assert "requests.patch" not in script_text
    assert "requests.delete" not in script_text
    assert "submit.py" not in script_text

def test_normalize_schema_repairs_basic_top_level_field_and_preserves_unknowns():
    module = load_module("test_schema_normalize_basic", SCRIPTS_DIR / "_schema_normalize.py")

    schema, warnings = module.normalize_schema(
        {
            "properties": {
                "password": {
                    "title": "密码",
                    "widget": {"id": "password"},
                    "hidden": True,
                    "condition": "1 === 2",
                    "x-custom": {"keep": True},
                }
            }
        }
    )

    field = schema["properties"]["password"]
    assert schema["type"] == "object"
    assert schema["widget"]["id"] == "object"
    assert field["id"] == "password"
    assert field["index"] == 0
    assert field["type"] == "string"
    assert field["config"]["visibility"] == {
        "allowInRequest": True,
        "allowInApproval": True,
    }
    assert field["hidden"] is True
    assert field["condition"] == "1 === 2"
    assert field["x-custom"] == {"keep": True}
    assert warnings

def test_normalize_schema_preserves_visibility_and_select_data():
    module = load_module("test_schema_normalize_select", SCRIPTS_DIR / "_schema_normalize.py")

    schema, _warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "environment": {
                    "id": "environment",
                    "index": 3,
                    "type": "string",
                    "widget": {"id": "select"},
                    "config": {"visibility": {"allowInRequest": False}},
                    "selectDatas": [{"id": "prod", "name": "生产"}],
                    "value": {"label": "name", "value": "id"},
                }
            },
        }
    )

    field = schema["properties"]["environment"]
    assert field["index"] == 3
    assert field["config"]["visibility"]["allowInRequest"] is False
    assert field["config"]["visibility"]["allowInApproval"] is True
    assert field["selectDatas"] == [{"id": "prod", "name": "生产"}]
    assert field["value"] == {"label": "name", "value": "id"}

def test_normalize_schema_repairs_common_llm_widget_shapes():
    module = load_module("test_schema_normalize_widget_aliases", SCRIPTS_DIR / "_schema_normalize.py")

    schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "widget": {"id": "text"},
                },
                "environment": {
                    "type": "string",
                    "widget": {
                        "id": "select",
                        "selectDatas": [
                            {"label": "Dev", "value": "dev"},
                            {"label": "Prod", "value": "prod"},
                        ],
                        "value": {"label": "label", "value": "value"},
                    },
                },
                "servers": {
                    "type": "array",
                    "widget": {"id": "table"},
                    "items": {"properties": {"hostname": {"widget": {"id": "text"}}}},
                },
            },
        }
    )

    assert schema["properties"]["service_name"]["widget"]["id"] == "string"
    assert schema["properties"]["environment"]["selectDatas"] == [
        {"label": "Dev", "value": "dev"},
        {"label": "Prod", "value": "prod"},
    ]
    assert schema["properties"]["environment"]["value"] == {"label": "label", "value": "value"}
    assert schema["properties"]["servers"]["widget"]["id"] == "table-head"
    assert (
        schema["properties"]["servers"]["items"]["properties"]["hostname"]["widget"]["id"]
        == "string"
    )
    assert warnings

def test_normalize_schema_keeps_field_level_select_values_when_widget_also_has_values():
    module = load_module("test_schema_normalize_select_precedence", SCRIPTS_DIR / "_schema_normalize.py")

    schema, _warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "environment": {
                    "type": "string",
                    "widget": {
                        "id": "select",
                        "selectDatas": [{"label": "Widget", "value": "widget"}],
                        "value": {"label": "widgetLabel", "value": "widgetValue"},
                    },
                    "selectDatas": [{"label": "Field", "value": "field"}],
                    "value": {"label": "fieldLabel", "value": "fieldValue"},
                },
            },
        }
    )

    field = schema["properties"]["environment"]
    assert field["selectDatas"] == [{"label": "Field", "value": "field"}]
    assert field["value"] == {"label": "fieldLabel", "value": "fieldValue"}
    assert field["widget"]["selectDatas"] == [{"label": "Widget", "value": "widget"}]
    assert field["widget"]["value"] == {"label": "widgetLabel", "value": "widgetValue"}

def test_normalize_schema_supports_array_table_fields():
    module = load_module("test_schema_normalize_array", SCRIPTS_DIR / "_schema_normalize.py")

    schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "database": {
                    "type": "array",
                    "title": "数据库",
                    "items": {
                        "properties": {
                            "name": {"title": "名称"},
                            "description": {"type": "string", "widget": {"id": "textarea"}},
                        }
                    },
                }
            },
        }
    )

    field = schema["properties"]["database"]
    assert field["widget"]["id"] == "table-head"
    assert field["items"]["type"] == "object"
    assert field["items"]["widget"]["id"] == "table-body"
    assert field["items"]["properties"]["name"]["type"] == "string"
    assert field["items"]["properties"]["name"]["widget"]["id"] == "string"
    assert field["items"]["fieldsets"][0]["fields"] == ["name", "description"]
    assert warnings
