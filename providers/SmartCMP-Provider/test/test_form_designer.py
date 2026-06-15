# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest
import requests


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = PROVIDER_ROOT / "skills" / "form-designer"
SCRIPTS_DIR = SKILL_ROOT / "scripts"


class FakeResponse:
    """Minimal requests response double used by form designer tests."""

    def __init__(self, payload, *, status_code: int = 200, text: str = ""):
        self._payload = payload
        self.status_code = status_code
        self.text = text or json.dumps(payload, ensure_ascii=False)
        self.headers = {"content-type": "application/json"}

    def json(self):
        """Return the configured JSON payload."""
        return self._payload

    def raise_for_status(self):
        """Raise an HTTPError for error status codes."""
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def load_module(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


def run_main(module_path: Path, argv: list[str], monkeypatch, *, fake_get=None):
    module_name = f"test_{module_path.stem}_module"
    monkeypatch.setenv("CMP_URL", "https://cmp.example.com")
    monkeypatch.setenv("CMP_COOKIE", "CloudChef-Authenticate=test-token")
    if fake_get is not None:
        monkeypatch.setattr(requests, "get", fake_get)

    stdout = io.StringIO()
    stderr = io.StringIO()
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            spec.loader.exec_module(module)
            exit_code = module.main(argv)
    finally:
        sys.modules.pop(module_name, None)

    return exit_code, stdout.getvalue(), stderr.getvalue()


def extract_meta(stderr: str, block_name: str):
    match = re.search(rf"##{block_name}_START##\s*(.*?)\s*##{block_name}_END##", stderr, re.DOTALL)
    assert match is not None
    return json.loads(match.group(1))


def test_form_designer_skill_layout_and_metadata():
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert (SKILL_ROOT / "references" / "WORKFLOW.md").is_file()
    assert (SCRIPTS_DIR / "read_form.py").is_file()
    assert (SCRIPTS_DIR / "design_form.py").is_file()
    assert (SCRIPTS_DIR / "_form_fetch.py").is_file()
    assert (SCRIPTS_DIR / "_schema_normalize.py").is_file()

    assert 'name: "form-designer"' in skill_text
    assert "smartcmp_read_form_schema" in skill_text
    assert "smartcmp_design_form_schema" in skill_text
    assert "form-designer" in skill_text
    assert "workflow_role" not in skill_text
    assert "request_parent" not in skill_text
    assert "smartcmp_submit_request" not in skill_text
    assert "submit.py" not in skill_text
    assert "does not save" in skill_text


def test_form_fetch_accepts_current_instance_edit_url():
    module = load_module("test_form_fetch_valid", SCRIPTS_DIR / "_form_fetch.py")

    source = module.parse_form_edit_url(
        "https://cmp.example.com/#/main/service-model/forms/edit/42607f38-2c63-4649-a8de-efa031db4544",
        "https://cmp.example.com/platform-api",
    )

    assert source.form_id == "42607f38-2c63-4649-a8de-efa031db4544"


def test_form_fetch_ignores_hash_query_without_widening_route():
    module = load_module("test_form_fetch_hash_query", SCRIPTS_DIR / "_form_fetch.py")

    source = module.parse_form_edit_url(
        "https://cmp.example.com/#/main/service-model/forms/edit/"
        "42607f38-2c63-4649-a8de-efa031db4544?tab=json",
        "https://cmp.example.com/platform-api",
    )

    assert source.form_id == "42607f38-2c63-4649-a8de-efa031db4544"


@pytest.mark.parametrize(
    "form_url",
    [
        "https://other.example.com/#/main/service-model/forms/edit/42607f38-2c63-4649-a8de-efa031db4544",
        "https://cmp.example.com/#/main/service-model/forms/view/42607f38-2c63-4649-a8de-efa031db4544",
        "https://cmp.example.com/#/main/service-model/forms/edit/not-a-uuid",
    ],
)
def test_form_fetch_rejects_external_or_non_edit_urls(form_url: str):
    module = load_module("test_form_fetch_invalid", SCRIPTS_DIR / "_form_fetch.py")

    with pytest.raises(ValueError):
        module.parse_form_edit_url(form_url, "https://cmp.example.com/platform-api")


def test_fetch_form_definition_reads_content_schema_with_get_only():
    module = load_module("test_form_fetch_definition", SCRIPTS_DIR / "_form_fetch.py")
    captured = {}

    def fake_get(url, headers=None, verify=None, timeout=None):
        captured["url"] = url
        return FakeResponse(
            {
                "name": "infoblox",
                "description": "IPAM form",
                "content": {
                    "designMode": "JSON",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "ip": {"type": "string", "widget": {"id": "string"}},
                        },
                    },
                },
            }
        )

    form = module.fetch_form_definition(
        "https://cmp.example.com/#/main/service-model/forms/edit/42607f38-2c63-4649-a8de-efa031db4544",
        "https://cmp.example.com/platform-api",
        {"CloudChef-Authenticate": "token"},
        get=fake_get,
    )

    assert captured["url"] == (
        "https://cmp.example.com/platform-api/forms/42607f38-2c63-4649-a8de-efa031db4544"
    )
    assert form.name == "infoblox"
    assert form.schema["properties"]["ip"]["type"] == "string"


def test_extract_schema_from_payload_accepts_string_schema_and_rejects_invalid_shapes():
    module = load_module("test_form_fetch_extract_schema", SCRIPTS_DIR / "_form_fetch.py")

    schema = module.extract_schema_from_payload(
        {"content": {"schema": json.dumps({"type": "object", "properties": {}})}}
    )

    assert schema == {"type": "object", "properties": {}}
    with pytest.raises(ValueError):
        module.extract_schema_from_payload({"content": {"schema": "[not-json]"}})
    with pytest.raises(ValueError):
        module.extract_schema_from_payload({"content": {"schema": []}})
    with pytest.raises(ValueError):
        module.extract_schema_from_payload({"content": None})


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
