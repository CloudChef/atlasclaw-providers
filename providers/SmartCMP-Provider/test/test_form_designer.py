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
    assert "JavaScript" in skill_text
    assert "config.value.expression" in skill_text
    assert "businessGroup.code" in skill_text
    assert "application.code" in skill_text
    assert "owners.userLoginId" in skill_text
    assert "cloudResourceTag" in skill_text
    assert "attachments" in skill_text
    assert "keyValueTag" in skill_text
    assert 'tool_design_result_mode: "llm"' in skill_text
    assert 'catalog_fields_json: "--catalog-fields-json"' in skill_text
    parameters_block = re.search(
        r"tool_design_parameters:\s*\|\s*(\{.*?\n  \})",
        skill_text,
        re.DOTALL,
    )
    assert parameters_block is not None
    assert '"catalog_fields_json"' in parameters_block.group(1)
    assert '"source": "mock"' in skill_text
    assert '"method": "mock"' in skill_text
    assert "do not also hand-write duplicate catalog fields" in skill_text
    assert "omit `schema_json`" in skill_text
    assert "Never pass truncated" in skill_text
    assert "preserves existing JavaScript" in skill_text
    assert "model.businessGroup" in skill_text
    assert "model.projects" in skill_text
    assert "complete normalized schema as a" in skill_text
    assert "fenced JSON block" in skill_text
    assert "tool output as authoritative" in skill_text
    assert "New-form design is a" in skill_text
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


def test_normalize_schema_repairs_bool_index_as_numeric_index():
    module = load_module("test_schema_normalize_bool_index", SCRIPTS_DIR / "_schema_normalize.py")

    schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "environment": {
                    "id": "environment",
                    "index": True,
                    "type": "string",
                    "widget": {"id": "string"},
                }
            },
        }
    )

    assert schema["properties"]["environment"]["index"] == 0
    assert any("Added numeric index" in warning for warning in warnings)


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


def test_normalize_schema_preserves_field_level_javascript_expression():
    module = load_module("test_schema_normalize_js", SCRIPTS_DIR / "_schema_normalize.py")
    expression = "function(model, sourceParams, schema, unused, cfg) { return model.name || ''; }"

    schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "computed_name": {
                    "type": "string",
                    "widget": {"id": "string"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": expression,
                        }
                    },
                },
            },
        }
    )

    field = schema["properties"]["computed_name"]
    assert field["config"]["value"]["expression"] == expression
    assert not [warning for warning in warnings if "JavaScript" in warning]


def test_normalize_schema_warns_for_risky_javascript_expression():
    module = load_module("test_schema_normalize_js_warning", SCRIPTS_DIR / "_schema_normalize.py")

    schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "remote_lookup": {
                    "type": "string",
                    "widget": {"id": "string"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": "function(model){ return fetch('https://example.com'); }",
                        }
                    },
                },
            },
        }
    )

    assert "fetch" in schema["properties"]["remote_lookup"]["config"]["value"]["expression"]
    assert any("fetch" in warning for warning in warnings)


def test_normalize_schema_accepts_known_builtin_catalog_field_metadata():
    module = load_module("test_schema_normalize_builtin_field", SCRIPTS_DIR / "_schema_normalize.py")

    schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "businessGroup": {
                    "type": "string",
                    "widget": {"id": "string"},
                    "x-smartcmp": {"builtinCatalogField": "businessGroup.code"},
                },
            },
        }
    )

    assert (
        schema["properties"]["businessGroup"]["x-smartcmp"]["builtinCatalogField"]
        == "businessGroup.code"
    )
    assert not [warning for warning in warnings if "Unknown SmartCMP catalog field" in warning]


@pytest.mark.parametrize(
    "field_content",
    [
        {
            "id": "context_field",
            "index": 0,
            "type": "string",
            "widget": {"id": "string"},
            "config": {"visibility": {"allowInRequest": True, "allowInApproval": True}},
        },
        {
            "id": "context_field",
            "index": 0,
            "type": "string",
            "widget": {"id": "string"},
            "config": {"visibility": {"allowInRequest": True, "allowInApproval": True}},
            "x-smartcmp": "businessGroup.code",
        },
        {
            "id": "context_field",
            "index": 0,
            "type": "string",
            "widget": {"id": "string"},
            "config": {"visibility": {"allowInRequest": True, "allowInApproval": True}},
            "x-smartcmp": {"builtinCatalogField": "   "},
        },
        {
            "id": "context_field",
            "index": 0,
            "type": "string",
            "widget": {"id": "string"},
            "config": {"visibility": {"allowInRequest": True, "allowInApproval": True}},
            "x-smartcmp": {"builtinCatalogField": 123},
        },
    ],
)
def test_normalize_schema_ignores_malformed_builtin_catalog_field_metadata(field_content):
    module = load_module(
        "test_schema_normalize_ignored_builtin_field",
        SCRIPTS_DIR / "_schema_normalize.py",
    )

    schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "widget": {"id": "object"},
            "properties": {"context_field": field_content},
        }
    )

    assert schema["properties"]["context_field"] == field_content
    assert not [warning for warning in warnings if "Unknown SmartCMP catalog field" in warning]


def test_normalize_schema_warns_for_unknown_builtin_catalog_field_metadata():
    module = load_module(
        "test_schema_normalize_unknown_builtin_field",
        SCRIPTS_DIR / "_schema_normalize.py",
    )

    schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "unknown_context": {
                    "type": "string",
                    "widget": {"id": "string"},
                    "x-smartcmp": {"builtinCatalogField": "businessGroup.costCenter"},
                },
            },
        }
    )

    assert (
        schema["properties"]["unknown_context"]["x-smartcmp"]["builtinCatalogField"]
        == "businessGroup.costCenter"
    )
    assert any("businessGroup.costCenter" in warning for warning in warnings)


@pytest.mark.parametrize(
    ("expression", "expected_label"),
    [
        (
            "function(model, sourceParams, schema, unused, cfg) { return eval(model.name); }",
            "eval(...)",
        ),
        (
            "function(model, sourceParams, schema, unused, cfg) { return Function('return 1')(); }",
            "Function constructor",
        ),
        (
            "function(model, sourceParams, schema, unused, cfg) { "
            "return window.Function('return 1')(); }",
            "Function constructor",
        ),
        (
            "function(model, sourceParams, schema, unused, cfg) { "
            "return globalThis.Function('return 1')(); }",
            "Function constructor",
        ),
        (
            "function(model, sourceParams, schema, unused, cfg) { return fetch('/api'); }",
            "fetch(...)",
        ),
        (
            "function(model, sourceParams, schema, unused, cfg) { "
            "return new XMLHttpRequest(); }",
            "XMLHttpRequest",
        ),
        (
            "function(model, sourceParams, schema, unused, cfg) { return document.cookie; }",
            "document.cookie",
        ),
        (
            "function(model, sourceParams, schema, unused, cfg) { "
            "return 'https://example.com/api'; }",
            "external URL",
        ),
    ],
)
def test_schema_scripts_warn_for_required_javascript_risk_patterns(
    expression: str,
    expected_label: str,
):
    module = load_module("test_schema_scripts_risk_patterns", SCRIPTS_DIR / "_schema_scripts.py")

    warnings = module.validate_javascript_expression(expression, field_key="computed_name")

    assert any(expected_label in warning for warning in warnings)


def test_schema_scripts_warn_for_non_smartcmp_function_contract():
    module = load_module("test_schema_scripts_function_contract", SCRIPTS_DIR / "_schema_scripts.py")

    warnings = module.validate_javascript_expression("model.name", field_key="computed_name")

    assert any("function(model, sourceParams, schema, unused, cfg)" in warning for warning in warnings)


def test_schema_scripts_allows_safe_smartcmp_function_contract_without_javascript_warnings():
    module = load_module("test_schema_scripts_safe_contract", SCRIPTS_DIR / "_schema_scripts.py")

    warnings = module.validate_javascript_expression(
        "function(model, sourceParams, schema, unused, cfg) { return model.name || ''; }",
        field_key="computed_name",
    )

    assert not [warning for warning in warnings if "JavaScript expression" in warning]


def test_schema_scripts_does_not_treat_regular_identifier_as_function_constructor():
    module = load_module("test_schema_scripts_identifier", SCRIPTS_DIR / "_schema_scripts.py")

    warnings = module.validate_javascript_expression(
        "function(model, sourceParams, schema, unused, cfg) { return myFunction(model.name); }",
        field_key="computed_name",
    )

    assert not any("Function constructor" in warning for warning in warnings)


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


def test_normalize_schema_warns_for_risky_nested_table_javascript_expression():
    module = load_module("test_schema_normalize_nested_js", SCRIPTS_DIR / "_schema_normalize.py")

    _schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "servers": {
                    "type": "array",
                    "items": {
                        "properties": {
                            "hostname": {
                                "type": "string",
                                "widget": {"id": "string"},
                                "config": {
                                    "value": {
                                        "source": "mock",
                                        "method": "mock",
                                        "expression": (
                                            "function(model, sourceParams, schema, unused, cfg) { "
                                            "return fetch('/api'); }"
                                        ),
                                    }
                                },
                            }
                        }
                    },
                }
            },
        }
    )

    assert any("servers.hostname" in warning and "fetch" in warning for warning in warnings)


def test_catalog_field_aliases_resolve_standard_context_fields():
    module = load_module("test_catalog_fields_aliases", SCRIPTS_DIR / "_catalog_fields.py")

    assert module.resolve_catalog_field_alias("businessGroup").canonical_key == "businessGroup"
    assert module.resolve_catalog_field_alias("应用").canonical_key == "projects"
    assert module.resolve_catalog_field_alias("业务组 code").canonical_key == "businessGroup.code"
    assert module.resolve_catalog_field_alias("应用code").canonical_key == "application.code"
    assert module.resolve_catalog_field_alias("projects.code").canonical_key == "application.code"
    assert module.resolve_catalog_field_alias("Owner Login ID").canonical_key == "owners.userLoginId"
    assert module.resolve_catalog_field_alias("执行时间").canonical_key == "executeTime"
    assert module.resolve_catalog_field_alias("附件").canonical_key == "attachments"
    assert module.resolve_catalog_field_alias("云资源标签").canonical_key == "cloudResourceTag"
    assert module.resolve_catalog_field_alias("Key-Value Tags").canonical_key == "keyValueTag"
    assert module.resolve_catalog_field_alias("not a known catalog field") is None


def test_catalog_field_definitions_include_required_standard_fields():
    module = load_module("test_catalog_fields_definitions", SCRIPTS_DIR / "_catalog_fields.py")

    definitions = module.iter_catalog_field_definitions()
    field_keys = {
        definition.canonical_key: definition.default_field_key for definition in definitions
    }

    assert field_keys == {
        "businessGroup": "businessGroup",
        "businessGroup.id": "businessGroup",
        "businessGroup.name": "businessGroup",
        "businessGroup.code": "businessGroup",
        "projects": "projects",
        "application.id": "projects",
        "application.name": "projects",
        "application.code": "projects",
        "owners": "owners",
        "owners.id": "owners",
        "owners.name": "owners",
        "owners.userName": "owners",
        "owners.userLoginId": "owners",
        "name": "name",
        "description": "description",
        "number": "number",
        "executeTime": "executeTime",
        "attachments": "attachments",
        "keyValueTag": "keyValueTag",
        "cloudResourceTag": "cloudResourceTag",
    }


def test_catalog_field_template_builds_read_only_schema_field():
    module = load_module("test_catalog_fields_template", SCRIPTS_DIR / "_catalog_fields.py")

    field = module.build_catalog_field_schema(
        "businessGroup.code",
        language="zh",
    )

    assert field["id"] == "businessGroup"
    assert field["title"] == "业务组 Code"
    assert field["type"] == "string"
    assert field["widget"]["id"] == "string"
    assert field["config"]["visibility"]["allowInRequest"] is True
    assert field["config"]["visibility"]["allowInApproval"] is True
    assert field["config"]["modification"]["allowInRequest"] is False
    assert field["config"]["modification"]["allowInApproval"] is False
    assert field["x-smartcmp"]["builtinCatalogField"] == "businessGroup.code"
    assert field["x-smartcmp"]["uiFieldKey"] == "businessGroup"


def test_catalog_field_template_uses_default_field_key_and_english_title():
    module = load_module("test_catalog_fields_defaults", SCRIPTS_DIR / "_catalog_fields.py")

    field = module.build_catalog_field_schema("application.name", language="en")

    assert field["id"] == "projects"
    assert field["title"] == "Application Name"
    assert field["x-smartcmp"]["builtinCatalogField"] == "application.name"
    assert field["x-smartcmp"]["uiFieldKey"] == "projects"


def test_catalog_field_template_builds_key_value_tag_table_schema():
    module = load_module("test_catalog_fields_key_value_tag", SCRIPTS_DIR / "_catalog_fields.py")

    field = module.build_catalog_field_schema("keyValueTag")

    assert field["id"] == "keyValueTag"
    assert field["type"] == "array"
    assert field["widget"]["id"] == "table-head"
    assert field["items"]["type"] == "object"
    assert field["items"]["widget"]["id"] == "table-body"
    assert field["items"]["properties"]["key"]["type"] == "string"
    assert field["items"]["properties"]["key"]["widget"]["id"] == "string"
    assert field["items"]["properties"]["value"]["type"] == "string"
    assert field["items"]["properties"]["value"]["widget"]["id"] == "string"
    assert field["items"]["fieldsets"][0]["fields"] == ["key", "value"]
    assert field["config"]["modification"]["allowInApproval"] is False
    assert field["x-smartcmp"]["builtinCatalogField"] == "keyValueTag"


def test_catalog_field_template_builds_owner_and_attachment_table_fields():
    module = load_module("test_catalog_fields_standard_tables", SCRIPTS_DIR / "_catalog_fields.py")

    owners = module.build_catalog_field_schema("owners", language="en")
    attachments = module.build_catalog_field_schema("attachments")

    assert owners["items"]["fieldsets"][0]["fields"] == [
        "id",
        "name",
        "userName",
        "userLoginId",
    ]
    assert owners["x-smartcmp"]["builtinCatalogField"] == "owners"
    assert attachments["type"] == "array"
    assert attachments["items"]["fieldsets"][0]["fields"] == ["name", "url"]
    assert attachments["x-smartcmp"]["builtinCatalogField"] == "attachments"


def test_catalog_field_template_builds_scalar_number_and_textarea_fields():
    module = load_module("test_catalog_fields_scalar_types", SCRIPTS_DIR / "_catalog_fields.py")

    number = module.build_catalog_field_schema("number")
    description = module.build_catalog_field_schema("description")

    assert number["type"] == "number"
    assert number["title"] == "数量"
    assert number["widget"]["id"] == "number"
    assert description["type"] == "string"
    assert description["widget"]["id"] == "textarea"


def test_catalog_field_template_can_build_hidden_schema_field():
    module = load_module("test_catalog_fields_hidden", SCRIPTS_DIR / "_catalog_fields.py")

    field = module.build_catalog_field_schema("businessGroup.id", hidden=True)

    assert field["id"] == "businessGroup"
    assert field["hidden"] is True
    assert field["widget"]["id"] == "hidden"
    assert field["config"]["modification"]["allowInApproval"] is False


def test_catalog_field_template_rejects_unknown_canonical_key():
    module = load_module("test_catalog_fields_unknown", SCRIPTS_DIR / "_catalog_fields.py")

    with pytest.raises(ValueError, match="Unknown SmartCMP catalog field"):
        module.build_catalog_field_schema("unknown.catalogField")


def test_catalog_field_template_allows_custom_field_key_with_ui_key_metadata():
    module = load_module("test_catalog_fields_custom_field_key", SCRIPTS_DIR / "_catalog_fields.py")

    field = module.build_catalog_field_schema(
        "businessGroup.code",
        field_key="business_group_code",
    )

    assert field["id"] == "business_group_code"
    assert field["x-smartcmp"]["builtinCatalogField"] == "businessGroup.code"
    assert field["x-smartcmp"]["uiFieldKey"] == "businessGroup"


def test_catalog_field_alias_registration_rejects_collisions():
    module = load_module("test_catalog_fields_alias_collision", SCRIPTS_DIR / "_catalog_fields.py")

    first = module.CatalogFieldDefinition(
        canonical_key="first.field",
        default_field_key="first_field",
        title_zh="First",
        title_en="First",
        description="First test field.",
        aliases=("shared alias",),
    )
    second = module.CatalogFieldDefinition(
        canonical_key="second.field",
        default_field_key="second_field",
        title_zh="Second",
        title_en="Second",
        description="Second test field.",
        aliases=("shared-alias",),
    )
    original_definitions = module._CATALOG_FIELD_DEFINITIONS
    module._CATALOG_FIELD_DEFINITIONS = (first, second)
    try:
        with pytest.raises(ValueError, match="Catalog field alias collision"):
            module._register_aliases()
    finally:
        module._CATALOG_FIELD_DEFINITIONS = original_definitions


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


def test_design_form_script_can_insert_catalog_standard_fields(monkeypatch):
    schema_json = json.dumps({"type": "object", "properties": {}}, ensure_ascii=False)
    catalog_fields_json = json.dumps(
        [{"field": "businessGroup.code"}, {"field": "application.code", "fieldKey": "app_code"}],
        ensure_ascii=False,
    )

    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "new",
            "--schema-json",
            schema_json,
            "--catalog-fields-json",
            catalog_fields_json,
            "--change-summary",
            "添加业务组 Code 和应用 Code 字段。",
        ],
        monkeypatch,
    )
    meta = extract_meta(stderr, "FORM_DESIGN_META")

    assert exit_code == 0
    assert "Custom fieldKey 'app_code'" in stdout
    assert (
        meta["schema"]["properties"]["businessGroup"]["x-smartcmp"][
            "builtinCatalogField"
        ]
        == "businessGroup.code"
    )
    assert (
        meta["schema"]["properties"]["app_code"]["x-smartcmp"]["builtinCatalogField"]
        == "application.code"
    )
    assert meta["schema"]["properties"]["app_code"]["x-smartcmp"]["uiFieldKey"] == "projects"


def test_design_form_script_deduplicates_indexes_after_catalog_field_insertion(monkeypatch):
    schema_json = json.dumps(
        {
            "type": "object",
            "properties": {
                "catalog_context": {
                    "id": "catalog_context",
                    "index": 2,
                    "type": "string",
                    "widget": {"id": "string"},
                }
            },
        },
        ensure_ascii=False,
    )
    catalog_fields_json = json.dumps(
        [{"field": "businessGroup.code"}, {"field": "application.code"}],
        ensure_ascii=False,
    )

    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "new",
            "--schema-json",
            schema_json,
            "--catalog-fields-json",
            catalog_fields_json,
        ],
        monkeypatch,
    )
    meta = extract_meta(stderr, "FORM_DESIGN_META")
    indexes = [
        field["index"]
        for field in meta["schema"]["properties"].values()
        if isinstance(field, dict)
    ]

    assert exit_code == 0
    assert indexes == [0, 1, 2]
    assert "duplicate top-level indexes" in stdout


def test_design_form_script_replaces_existing_field_by_catalog_template_id_and_preserves_unknowns(
    monkeypatch,
):
    schema_json = json.dumps(
        {
            "type": "object",
            "properties": {
                "businessGroup": {
                    "id": "businessGroup",
                    "title": "Old Business Group",
                    "type": "number",
                    "widget": {"id": "number"},
                    "condition": "model.enable_business_group",
                    "selectDatas": [{"id": "old", "name": "Old"}],
                    "value": {"label": "name", "value": "id"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": "function(model){ return model.existing; }",
                        },
                        "visibility": {"allowInRequest": False},
                    },
                    "x-local-test-marker": "old-field",
                }
            },
        },
        ensure_ascii=False,
    )
    catalog_fields_json = json.dumps([{"field": "businessGroup.code"}], ensure_ascii=False)

    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "new",
            "--schema-json",
            schema_json,
            "--catalog-fields-json",
            catalog_fields_json,
        ],
        monkeypatch,
    )
    meta = extract_meta(stderr, "FORM_DESIGN_META")
    field = meta["schema"]["properties"]["businessGroup"]

    assert exit_code == 0
    assert field["x-smartcmp"]["builtinCatalogField"] == "businessGroup.code"
    assert field["title"] == "业务组 Code"
    assert field["type"] == "string"
    assert field["widget"]["id"] == "string"
    assert field["condition"] == "model.enable_business_group"
    assert field["selectDatas"] == [{"id": "old", "name": "Old"}]
    assert field["value"] == {"label": "name", "value": "id"}
    assert field["config"]["value"]["expression"] == "function(model){ return model.existing; }"
    assert field["config"]["visibility"]["allowInRequest"] is False
    assert field["x-local-test-marker"] == "old-field"
    assert "Preserved unknown keys" in stdout
    assert "Preserved existing behavior" in stdout
    assert "Replaced existing structural keys" in stdout


def test_design_form_script_warns_when_catalog_aliases_share_ui_key(monkeypatch):
    schema_json = json.dumps({"type": "object", "properties": {}}, ensure_ascii=False)
    catalog_fields_json = json.dumps(
        [{"field": "businessGroup.name"}, {"field": "businessGroup.code"}],
        ensure_ascii=False,
    )

    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "new",
            "--schema-json",
            schema_json,
            "--catalog-fields-json",
            catalog_fields_json,
        ],
        monkeypatch,
    )
    meta = extract_meta(stderr, "FORM_DESIGN_META")
    business_group = meta["schema"]["properties"]["businessGroup"]

    assert exit_code == 0
    assert "Multiple catalog field requests" in stdout
    assert business_group["x-smartcmp"]["builtinCatalogField"] == "businessGroup"
    assert list(meta["schema"]["properties"]) == ["businessGroup"]


def test_design_form_script_uses_default_id_for_blank_catalog_field_key(monkeypatch):
    schema_json = json.dumps({"type": "object", "properties": {}}, ensure_ascii=False)
    catalog_fields_json = json.dumps(
        [{"field": "application.name", "fieldKey": "   "}],
        ensure_ascii=False,
    )

    exit_code, _stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "new",
            "--schema-json",
            schema_json,
            "--catalog-fields-json",
            catalog_fields_json,
        ],
        monkeypatch,
    )
    meta = extract_meta(stderr, "FORM_DESIGN_META")

    assert exit_code == 0
    assert "projects" in meta["schema"]["properties"]
    assert meta["schema"]["properties"]["projects"]["id"] == "projects"


def test_design_form_script_warns_for_ignored_catalog_field_requests(monkeypatch):
    schema_json = json.dumps({"type": "object", "properties": {}}, ensure_ascii=False)
    catalog_fields_json = json.dumps(
        ["not an object", {"field": "businessGroup.costCenter"}, {"field": "应用code"}],
        ensure_ascii=False,
    )

    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "new",
            "--schema-json",
            schema_json,
            "--catalog-fields-json",
            catalog_fields_json,
            "--change-summary",
            "添加应用 Code 字段，忽略不支持的字段请求。",
        ],
        monkeypatch,
    )
    meta = extract_meta(stderr, "FORM_DESIGN_META")

    assert exit_code == 0
    assert "Ignored non-object catalog field request." in stdout
    assert "Unknown SmartCMP catalog field: businessGroup.costCenter" in stdout
    assert "Ignored non-object catalog field request." in meta["warnings"]
    assert "Unknown SmartCMP catalog field: businessGroup.costCenter" in meta["warnings"]
    assert (
        meta["schema"]["properties"]["projects"]["x-smartcmp"][
            "builtinCatalogField"
        ]
        == "application.code"
    )


def test_design_form_script_rejects_invalid_schema_json(monkeypatch):
    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        ["--mode", "new", "--schema-json", "[not-json]"],
        monkeypatch,
    )

    assert exit_code == 1
    assert "schema_json is not valid JSON" in stdout
    assert "FORM_DESIGN_META" not in stderr


@pytest.mark.parametrize(
    ("schema", "catalog_fields_json", "expected_message"),
    [
        (
            {"type": "object", "properties": {}},
            "[not-json]",
            "catalog_fields_json is not valid JSON",
        ),
        (
            {"type": "object", "properties": {}},
            '{"field": "businessGroup.code"}',
            "catalog_fields_json must be a JSON array.",
        ),
        (
            {"type": "object", "properties": "not an object"},
            '[{"field": "businessGroup.code"}]',
            "schema.properties must be an object",
        ),
    ],
)
def test_design_form_script_rejects_catalog_field_hard_failures(
    schema: dict,
    catalog_fields_json: str,
    expected_message: str,
    monkeypatch,
):
    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "new",
            "--schema-json",
            json.dumps(schema, ensure_ascii=False),
            "--catalog-fields-json",
            catalog_fields_json,
        ],
        monkeypatch,
    )

    assert exit_code == 1
    assert "[ERROR]" in stdout
    assert expected_message in stdout
    assert "FORM_DESIGN_META_START" not in stderr


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


def test_design_form_modify_mode_can_insert_catalog_fields_without_schema_json(monkeypatch):
    captured = {}
    expression = "function(model, sourceParams, schema, unused, cfg) { return model.mixture; }"

    def fake_get(url, headers=None, verify=None, timeout=None):
        captured["url"] = url
        return FakeResponse(
            {
                "name": "test-vm",
                "content": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "expansion": {
                                "id": "expansion",
                                "type": "string",
                                "widget": {"id": "string"},
                                "config": {
                                    "value": {
                                        "source": "mock",
                                        "method": "mock",
                                        "expression": expression,
                                    }
                                },
                            },
                        },
                    }
                },
            }
        )

    catalog_fields_json = json.dumps([{"field": "application.code"}], ensure_ascii=False)
    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "modify",
            "--form-url",
            "https://cmp.example.com/#/main/service-model/forms/edit/"
            "42607f38-2c63-4649-a8de-efa031db4544",
            "--catalog-fields-json",
            catalog_fields_json,
            "--change-summary",
            "保留已有 JavaScript 并添加应用 Code 字段。",
        ],
        monkeypatch,
        fake_get=fake_get,
    )
    meta = extract_meta(stderr, "FORM_DESIGN_META")
    properties = meta["schema"]["properties"]

    assert exit_code == 0
    assert captured["url"].endswith("/forms/42607f38-2c63-4649-a8de-efa031db4544")
    assert "deterministic catalog field insertion" in stdout
    assert properties["expansion"]["config"]["value"]["expression"] == expression
    assert (
        properties["projects"]["x-smartcmp"]["builtinCatalogField"]
        == "application.code"
    )


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
