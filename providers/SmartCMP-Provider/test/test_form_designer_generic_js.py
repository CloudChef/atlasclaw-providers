# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

import importlib.util
import io
import json
import re
import shutil
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest
import requests


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = PROVIDER_ROOT / "skills" / "form-designer"
SCRIPTS_DIR = SKILL_ROOT / "scripts"


class FakeResponse:
    def __init__(self, payload, *, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload, ensure_ascii=False)
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._payload

    def raise_for_status(self):
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


def run_node_expression(expression: str, setup_js: str) -> dict:
    if shutil.which("node") is None:
        raise AssertionError("node is required for JavaScript expression regression tests")
    result = subprocess.run(
        ["node", "-e", f"const fn = ({expression});\n{setup_js}"],
        text=True,
        capture_output=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_form_fetch_accepts_edit_and_design_urls_and_rejects_external_routes():
    module = load_module("form_fetch_url_contract", SCRIPTS_DIR / "_form_fetch.py")

    edit_source = module.parse_form_edit_url(
        "https://cmp.example.com/#/main/service-model/forms/edit/"
        "123e4567-e89b-12d3-a456-426614174000?tab=json",
        "https://cmp.example.com/platform-api",
    )
    design_source = module.parse_form_edit_url(
        "https://cmp.example.com/#/main/service-model/forms/design/"
        "123e4567-e89b-12d3-a456-426614174000?currentAction=edit",
        "https://cmp.example.com/platform-api",
    )

    assert edit_source.form_id == "123e4567-e89b-12d3-a456-426614174000"
    assert edit_source.route == "edit"
    assert design_source.route == "design"

    for bad_url in (
        "https://other.example.com/#/main/service-model/forms/edit/123e4567-e89b-12d3-a456-426614174000",
        "https://cmp.example.com/#/main/service-model/forms/view/123e4567-e89b-12d3-a456-426614174000",
        "https://cmp.example.com/#/main/service-model/forms/edit/not-a-uuid",
    ):
        with pytest.raises(ValueError):
            module.parse_form_edit_url(bad_url, "https://cmp.example.com/platform-api")


def test_fetch_form_definition_extracts_schema_model_and_visual_context():
    module = load_module("form_fetch_definition_contract", SCRIPTS_DIR / "_form_fetch.py")
    calls = []

    def fake_get(url, headers=None, verify=None, timeout=None):
        calls.append({"url": url, "headers": headers, "verify": verify, "timeout": timeout})
        return FakeResponse(
            {
                "name": "Existing",
                "description": "Service form",
                "content": {
                    "designMode": "visual",
                    "components": [{"key": "payload"}, {"key": "owner"}],
                    "model": json.dumps({"payload": "old", "owner": "u1"}, ensure_ascii=False),
                    "schema": json.dumps(
                        {
                            "type": "object",
                            "properties": {
                                "payload": {"type": "string", "widget": {"id": "string"}}
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
            }
        )

    form = module.fetch_form_definition(
        "https://cmp.example.com/#/main/service-model/forms/design/123e4567-e89b-12d3-a456-426614174000",
        "https://cmp.example.com/platform-api",
        {"CloudChef-Authenticate": "token"},
        get=fake_get,
    )

    assert calls == [
        {
            "url": "https://cmp.example.com/platform-api/forms/123e4567-e89b-12d3-a456-426614174000",
            "headers": {"CloudChef-Authenticate": "token"},
            "verify": False,
            "timeout": 60,
        }
    ]
    assert form.name == "Existing"
    assert form.description == "Service form"
    assert form.schema["properties"]["payload"]["type"] == "string"
    assert form.model == {"payload": "old", "owner": "u1"}
    assert form.design_mode == "visual"
    assert form.component_count == 2
    assert form.source_route == "design"
    assert form.raw_content_keys == ["components", "designMode", "model", "schema"]


def test_read_form_outputs_context_meta_and_rejects_bad_url(monkeypatch):
    def fake_get(url, headers=None, timeout=None, **kwargs):
        return FakeResponse(
            {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "name": "Existing",
                "description": "Service form",
                "content": {
                    "designMode": "visual",
                    "components": [{"key": "payload"}],
                    "model": {"payload": "old"},
                    "schema": {
                        "type": "object",
                        "properties": {
                            "payload": {"id": "payload", "type": "string", "widget": {"id": "string"}}
                        },
                    },
                },
            }
        )

    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "read_form.py",
        [
            "https://cmp.example.com/#/main/service-model/forms/design/"
            "123e4567-e89b-12d3-a456-426614174000"
        ],
        monkeypatch,
        fake_get=fake_get,
    )

    assert exit_code == 0, stdout
    assert "SmartCMP Form: Existing" in stdout
    assert "Design Mode: visual" in stdout
    assert "Model Keys: payload" in stdout
    assert "Component Count: 1" in stdout
    meta = extract_meta(stderr, "FORM_SCHEMA_META")
    assert meta["source"] == {
        "formId": "123e4567-e89b-12d3-a456-426614174000",
        "route": "design",
    }
    assert meta["model"] == {"payload": "old"}
    assert meta["componentCount"] == 1

    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "read_form.py",
        ["https://other.example.com/#/main/service-model/forms/design/123e4567-e89b-12d3-a456-426614174000"],
        monkeypatch,
        fake_get=fake_get,
    )
    assert exit_code == 1
    assert "selected SmartCMP provider instance" in stdout
    assert "FORM_SCHEMA_META" not in stderr


def test_skill_contract_stays_generic_and_reviewable():
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    workflow_text = (SKILL_ROOT / "references" / "WORKFLOW.md").read_text(encoding="utf-8")
    combined = "\n".join((skill_text, workflow_text))

    for marker in (
        "value_expressions_json is an optional compatibility helper",
        "Do not use value_expressions_json as the default path",
        "Do not rely on catalog_fields_json to satisfy catalog context needs",
        "Service-catalog context derived fields are not general custom JavaScript",
        "User-enumerated fields are visible by default",
        "requested_fields_json",
    ):
        assert marker in skill_text
    assert "empty string until at least one source value resolves" in workflow_text
    assert "Do not guess unverified runtime containers" in workflow_text
    assert "treat display labels as current-form model keys" in workflow_text
    assert "sourceParams.serviceParams" not in combined
    assert "model['业务组']" not in combined

    for incident_marker in (
        "161b8b0a",
        "57ec090a",
        "project-1",
        "Passw0rd",
        "catalog_context_sync_json",
        "AUTO_SYNC_PENDING",
    ):
        assert incident_marker not in combined


def test_value_expression_target_keeps_requested_field_set_and_runtime_value_type(monkeypatch):
    schema = {
        "type": "object",
        "properties": {
            "sourceProject": {"id": "sourceProject", "type": "string", "widget": {"id": "string"}},
            "payload": {
                "id": "payload",
                "type": "object",
                "format": "table-like",
                "widget": {"id": "object"},
                "properties": {"staleChild": {"type": "string"}},
                "items": {"type": "object", "properties": {"staleRow": {"type": "string"}}},
                "fieldsets": [{"fields": ["staleChild"]}],
                "columnsets": [{"columns": [{"fields": ["staleChild"]}]}],
            },
        },
        "fieldsets": [{"id": "base", "fields": ["sourceProject", "payload"]}],
        "widget": {"id": "object"},
    }

    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "new",
            "--schema-json",
            json.dumps(schema, ensure_ascii=False),
            "--requested-fields-json",
            json.dumps(["payload"], ensure_ascii=False),
            "--value-expressions-json",
            json.dumps(
                [
                    {
                        "fieldKey": "payload",
                        "valueType": "object",
                        "compose": {"应用系统": {"$field": "应用系统"}},
                    }
                ],
                ensure_ascii=False,
            ),
        ],
        monkeypatch,
    )

    assert exit_code == 0, stdout
    meta = extract_meta(stderr, "FORM_DESIGN_META")
    assert list(meta["schema"]["properties"]) == ["payload", "schemaFormValid"]
    assert meta["schema"]["fieldsets"][0]["fields"] == ["payload", "schemaFormValid"]

    field = meta["schema"]["properties"]["payload"]
    assert meta["schema"]["properties"]["schemaFormValid"]["hidden"] is True
    assert field["type"] == "string"
    assert field["widget"] == {"id": "string"}
    for stale_key in ("properties", "items", "fieldsets", "columnsets", "format"):
        assert stale_key not in field

    result = run_node_expression(
        field["config"]["value"]["expression"],
        """
const model = {};
const sourceParams = {catalogServiceRequest: {exts: {project: {name: 'project-1'}}}};
const out = fn(model, sourceParams, {}, null, {});
console.log(JSON.stringify({out: out, model: model, outType: typeof out}));
""",
    )
    assert result["outType"] == "object"
    assert result["out"] == {"应用系统": "project-1"}
    assert result["model"]["payload"] == {"应用系统": "project-1"}


def test_url_modify_loads_source_but_replaces_legacy_value_expression(monkeypatch):
    calls = []

    def fake_get(url, headers=None, timeout=None, **kwargs):
        calls.append({"url": url, "timeout": timeout})
        return FakeResponse(
            {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "name": "Existing",
                "content": {
                    "designMode": "visual",
                    "components": [{"key": "payload"}],
                    "model": {"payload": "{\"应用系统\":\"project-1\",\"业务组\":\"1组\"}"},
                    "schema": {
                        "type": "object",
                        "properties": {
                            "payload": {
                                "id": "payload",
                                "type": "string",
                                "widget": {"id": "string"},
                                "config": {
                                    "value": {
                                        "source": "mock",
                                        "method": "mock",
                                        "expression": "function(model){return model.payload || '';}",
                                    }
                                },
                            }
                        },
                        "widget": {"id": "object"},
                    },
                },
            }
        )

    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "modify",
            "--form-url",
            "https://cmp.example.com/#/main/service-model/forms/design/123e4567-e89b-12d3-a456-426614174000?currentAction=edit#update",
            "--value-expressions-json",
            json.dumps(
                [{"fieldKey": "payload", "compose": {"应用系统": {"$field": "应用系统"}}}],
                ensure_ascii=False,
            ),
        ],
        monkeypatch,
        fake_get=fake_get,
    )

    assert exit_code == 0, stdout
    assert calls[0]["url"] == "https://cmp.example.com/platform-api/forms/123e4567-e89b-12d3-a456-426614174000"
    assert calls[0]["timeout"] is not None
    assert "does not save changes to CMP" in stdout
    assert "contains visual designer components" in stdout

    expression = extract_meta(stderr, "FORM_DESIGN_META")["schema"]["properties"]["payload"]["config"]["value"]["expression"]
    assert "业务组" not in expression
    result = run_node_expression(
        expression,
        """
const model = {payload: '{"应用系统":"old","业务组":"old"}'};
const sourceParams = {projects: {name: 'project-1'}};
const out = fn(model, sourceParams, {}, null, {});
console.log(JSON.stringify({out: out, model: model}));
""",
    )
    assert result["out"] == "{\"应用系统\":\"project-1\"}"
    assert result["model"]["payload"] == "{\"应用系统\":\"project-1\"}"


def test_design_form_rejects_placeholder_and_legacy_url_javascript(monkeypatch):
    placeholder_schema = {
        "type": "object",
        "properties": {
            "payload": {
                "type": "string",
                "widget": {"id": "string"},
                "config": {
                    "value": {
                        "source": "mock",
                        "method": "mock",
                        "expression": "function(model, sourceParams, schema, unused, cfg) { ... }",
                    }
                },
            }
        },
    }

    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        ["--mode", "new", "--schema-json", json.dumps(placeholder_schema)],
        monkeypatch,
    )
    assert exit_code == 1
    assert "literal ellipsis placeholder" in stdout
    assert "FORM_DESIGN_META" not in stderr

    legacy_schema = {
        "type": "object",
        "properties": {
            "payload": {
                "type": "string",
                "widget": {"id": "string"},
                "config": {
                    "value": {
                        "source": "mock",
                        "method": "mock",
                        "expression": "function(formInRet, schemas, widget, injection) { return formInRet.payload; }",
                    }
                },
            }
        },
    }
    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "regenerate",
            "--form-url",
            "https://cmp.example.com/#/main/service-model/forms/edit/123e4567-e89b-12d3-a456-426614174000",
            "--schema-json",
            json.dumps(legacy_schema),
        ],
        monkeypatch,
    )
    assert exit_code == 1
    assert "URL-based form changes cannot use legacy JavaScript expressions" in stdout
    assert "FORM_DESIGN_META" not in stderr


def test_design_form_rejects_new_value_expressions_without_a_safe_submit_contract(monkeypatch):
    def run_new_schema(expression: str):
        schema = {
            "type": "object",
            "properties": {
                "computed": {
                    "type": "string",
                    "widget": {"id": "string"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": expression,
                        }
                    },
                }
            },
        }
        return run_main(
            SCRIPTS_DIR / "design_form.py",
            ["--mode", "new", "--schema-json", json.dumps(schema)],
            monkeypatch,
        )

    exit_code, stdout, stderr = run_new_schema(
        "function(formInRet, schemas, widget, injection) { return 'computed'; }"
    )
    assert exit_code == 1
    assert "must use function(model, sourceParams, schema, unused, cfg)" in stdout
    assert "FORM_DESIGN_META" not in stderr

    exit_code, stdout, stderr = run_new_schema(
        "function(model, sourceParams, schema, unused, cfg) { return 'computed'; }"
    )
    assert exit_code == 1
    assert "must assign model" in stdout
    assert "FORM_DESIGN_META" not in stderr


def test_design_form_rejects_javascript_syntax_errors(monkeypatch):
    schema = {
        "type": "object",
        "properties": {
            "computed": {
                "type": "string",
                "widget": {"id": "string"},
                "config": {
                    "value": {
                        "source": "mock",
                        "method": "mock",
                        "expression": (
                            "function(model, sourceParams, schema, unused, cfg) { "
                            "model.computed = ; return 'computed'; }"
                        ),
                    }
                },
            }
        },
    }

    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        ["--mode", "new", "--schema-json", json.dumps(schema)],
        monkeypatch,
    )

    assert exit_code == 1
    assert "invalid JavaScript syntax" in stdout
    assert "FORM_DESIGN_META" not in stderr


def test_design_form_rejects_custom_js_missing_model_context_fields(monkeypatch):
    schema = {
        "type": "object",
        "properties": {
            "expansion": {
                "type": "string",
                "widget": {"id": "string"},
                "config": {
                    "value": {
                        "source": "mock",
                        "method": "mock",
                        "expression": (
                            "function(model, sourceParams, schema, unused, cfg) { "
                            "var bg = model['业务组'] || ''; "
                            "var app = model['应用系统'] || ''; "
                            "return JSON.stringify({v1:{业务组:bg},v2:{应用系统:app}}); "
                            "}"
                        ),
                    }
                },
            }
        },
        "fieldsets": [{"fields": ["expansion"]}],
    }

    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "new",
            "--schema-json",
            json.dumps(schema, ensure_ascii=False),
            "--requested-fields-json",
            json.dumps(["expansion"], ensure_ascii=False),
        ],
        monkeypatch,
    )

    assert exit_code == 1
    assert "reads model field '业务组' which is not a schema property" in stdout
    assert "value_expressions_json" in stdout
    assert "FORM_DESIGN_META" not in stderr


def test_design_form_rejects_unverified_service_params_catalog_context(monkeypatch):
    schema = {
        "type": "object",
        "properties": {
            "mixture": {
                "type": "string",
                "widget": {"id": "string"},
                "config": {
                    "value": {
                        "source": "mock",
                        "method": "mock",
                        "expression": (
                            "function(model, sourceParams, schema, unused, cfg) { "
                            "var params = sourceParams && sourceParams.serviceParams; "
                            "var name = params && (params['名称'] || params.name) || ''; "
                            "return JSON.stringify({名称:name}); "
                            "}"
                        ),
                    }
                },
            }
        },
        "fieldsets": [{"fields": ["mixture"]}],
    }

    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        ["--mode", "new", "--schema-json", json.dumps(schema, ensure_ascii=False)],
        monkeypatch,
    )

    assert exit_code == 1
    assert "unverified sourceParams context container" in stdout
    assert "verified catalog context paths" in stdout
    assert "FORM_DESIGN_META" not in stderr


def test_design_form_rejects_direct_source_params_catalog_context(monkeypatch):
    schema = {
        "type": "object",
        "properties": {
            "attr": {
                "type": "string",
                "widget": {"id": "string"},
                "config": {
                    "value": {
                        "source": "mock",
                        "method": "mock",
                        "expression": (
                            "function(model, sourceParams, schema, unused, cfg) { "
                            "var bizGroup = (sourceParams && sourceParams['businessGroup']) || "
                            "(sourceParams && sourceParams['业务组']) || ''; "
                            "var owner = (sourceParams && sourceParams.owners) || "
                            "(sourceParams && sourceParams['所有者']) || ''; "
                            "model['attr'] = '{业务组：' + bizGroup + '，所有者：' + owner + '}'; "
                            "return model['attr']; "
                            "}"
                        ),
                    }
                },
            }
        },
        "fieldsets": [{"fields": ["attr"]}],
    }

    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "new",
            "--schema-json",
            json.dumps(schema, ensure_ascii=False),
            "--requested-fields-json",
            json.dumps(["attr"], ensure_ascii=False),
        ],
        monkeypatch,
    )

    assert exit_code == 1
    assert "unverified sourceParams context container" in stdout
    assert "businessGroup" in stdout
    assert "owners" in stdout
    assert "value_expressions_json" in stdout
    assert "FORM_DESIGN_META" not in stderr


def test_design_form_rejects_any_direct_source_params_key(monkeypatch):
    schema = {
        "type": "object",
        "properties": {
            "computed": {
                "type": "string",
                "widget": {"id": "string"},
                "config": {
                    "value": {
                        "source": "mock",
                        "method": "mock",
                        "expression": (
                            "function(model, sourceParams, schema, unused, cfg) { "
                            "var first = sourceParams && sourceParams['futureCatalogField']; "
                            "var second = sourceParams && sourceParams.someOtherRuntimeKey; "
                            "model['computed'] = String(first || '') + String(second || ''); "
                            "return model['computed']; "
                            "}"
                        ),
                    }
                },
            }
        },
        "fieldsets": [{"fields": ["computed"]}],
    }

    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "new",
            "--schema-json",
            json.dumps(schema, ensure_ascii=False),
            "--requested-fields-json",
            json.dumps(["computed"], ensure_ascii=False),
        ],
        monkeypatch,
    )

    assert exit_code == 1
    assert "unverified sourceParams context container" in stdout
    assert "futureCatalogField" in stdout
    assert "someOtherRuntimeKey" in stdout
    assert "value_expressions_json" in stdout
    assert "FORM_DESIGN_META" not in stderr


def test_design_form_rejects_source_params_optional_alias_and_destructure_reads(monkeypatch):
    schema = {
        "type": "object",
        "properties": {
            "computed": {
                "type": "string",
                "widget": {"id": "string"},
                "config": {
                    "value": {
                        "source": "mock",
                        "method": "mock",
                        "expression": (
                            "function(model, sourceParams, schema, unused, cfg) { "
                            "var sp = sourceParams; "
                            "var bg = sourceParams?.businessGroup || sourceParams?.['owner']; "
                            "var project = (sourceParams || {}).project; "
                            "var bracket = (sourceParams || {})['futureBracket']; "
                            "var alias = sourceParams; "
                            "var {directField} = sourceParams || {}; "
                            "var {destructuredField, nestedOwner: ownerAlias, nestedObject: {leaf}} = alias || {}; "
                            "model['computed'] = (sp.futureKey || '') + bg + project + bracket + "
                            "directField + destructuredField + ownerAlias + leaf; "
                            "return model['computed']; "
                            "}"
                        ),
                    }
                },
            }
        },
        "fieldsets": [{"fields": ["computed"]}],
    }

    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "new",
            "--schema-json",
            json.dumps(schema, ensure_ascii=False),
            "--requested-fields-json",
            json.dumps(["computed"], ensure_ascii=False),
        ],
        monkeypatch,
    )

    assert exit_code == 1
    assert "unverified sourceParams context container" in stdout
    assert "businessGroup" in stdout
    assert "owner" in stdout
    assert "project" in stdout
    assert "futureKey" in stdout
    assert "futureBracket" in stdout
    assert "directField" in stdout
    assert "destructuredField" in stdout
    assert "nestedOwner" in stdout
    assert "nestedObject" in stdout
    assert "FORM_DESIGN_META" not in stderr


def test_value_expression_preserves_legacy_root_fieldset_properties(monkeypatch):
    schema = {
        "type": "object",
        "properties": {
            "sourceProject": {
                "id": "sourceProject",
                "title": "Source Project",
                "type": "string",
                "widget": {"id": "string"},
            }
        },
        "fieldsets": [{"id": "legacy", "properties": ["sourceProject"]}],
        "widget": {"id": "object"},
    }

    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "new",
            "--schema-json",
            json.dumps(schema, ensure_ascii=False),
            "--value-expressions-json",
            json.dumps(
                [
                    {
                        "fieldKey": "payload",
                        "compose": {
                            "$concat": ["{名称：", {"$field": "名称"}, "}"],
                        },
                    }
                ],
                ensure_ascii=False,
            ),
        ],
        monkeypatch,
    )

    assert exit_code == 0, stdout
    meta = extract_meta(stderr, "FORM_DESIGN_META")
    assert list(meta["schema"]["properties"]) == ["sourceProject", "payload", "schemaFormValid"]
    assert meta["schema"]["fieldsets"][0]["fields"] == [
        "sourceProject",
        "payload",
        "schemaFormValid",
    ]
    assert "properties" not in meta["schema"]["fieldsets"][0]


def test_design_form_rejects_unverified_context_in_non_value_js_fields(monkeypatch):
    schema = {
        "type": "object",
        "properties": {
            "computed": {
                "type": "string",
                "widget": {"id": "string"},
                "changeEvent": (
                    "function(model, sourceParams, schema, unused, cfg) { "
                    "model['computed'] = sourceParams?.businessGroup || cfg.catalogServiceRequest; "
                    "}"
                ),
            }
        },
        "fieldsets": [{"fields": ["computed"]}],
    }

    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "new",
            "--schema-json",
            json.dumps(schema, ensure_ascii=False),
            "--requested-fields-json",
            json.dumps(["computed"], ensure_ascii=False),
        ],
        monkeypatch,
    )

    assert exit_code == 1
    assert "computed.changeEvent" in stdout
    assert "unverified sourceParams context container" in stdout
    assert "unverified runtime context container" in stdout
    assert "FORM_DESIGN_META" not in stderr


def test_design_form_rejects_unknown_model_optional_and_dynamic_reads(monkeypatch):
    schema = {
        "type": "object",
        "properties": {
            "computed": {
                "type": "string",
                "widget": {"id": "string"},
                "config": {
                    "value": {
                        "source": "mock",
                        "method": "mock",
                        "expression": (
                            "function(model, sourceParams, schema, unused, cfg) { "
                            "var key = '业务组'; "
                            "return (model?.futureField || '') + (model[key] || ''); "
                            "}"
                        ),
                    }
                },
            }
        },
        "fieldsets": [{"fields": ["computed"]}],
    }

    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "new",
            "--schema-json",
            json.dumps(schema, ensure_ascii=False),
            "--requested-fields-json",
            json.dumps(["computed"], ensure_ascii=False),
        ],
        monkeypatch,
    )

    assert exit_code == 1
    assert "futureField" in stdout
    assert "业务组" in stdout
    assert "which is not a schema property" in stdout
    assert "FORM_DESIGN_META" not in stderr


def test_catalog_context_value_expression_matches_visible_requested_fields(monkeypatch):
    schema = {
        "type": "object",
        "properties": {
            "mixture": {"id": "mixture", "type": "string", "widget": {"id": "string"}},
            "expansion": {"id": "expansion", "type": "string", "widget": {"id": "string"}},
        },
        "fieldsets": [
            {
                "id": "fieldset1",
                "index": 0,
                "title": "基本信息",
                "i18nTitle": "基本信息",
                "fields": [{"id": "mixture", "index": 0}, {"id": "expansion", "index": 1}],
            }
        ],
    }

    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "new",
            "--schema-json",
            json.dumps(schema, ensure_ascii=False),
            "--requested-fields-json",
            json.dumps(["mixture", "expansion"], ensure_ascii=False),
            "--value-expressions-json",
            json.dumps(
                [
                    {
                        "fieldKey": "mixture",
                        "valueType": "string",
                        "compose": {
                            "$concat": [
                                "{名称：",
                                {"$field": "名称"},
                                "，所有者：",
                                {"$field": "所有者"},
                                "}",
                            ]
                        },
                    },
                    {
                        "fieldKey": "expansion",
                        "valueType": "string",
                        "compose": {
                            "$concat": [
                                "{应用系统：",
                                {"$field": "应用系统"},
                                "，业务组：",
                                {"$field": "业务组"},
                                "}",
                            ]
                        },
                    },
                ],
                ensure_ascii=False,
            ),
        ],
        monkeypatch,
    )

    assert exit_code == 0, stdout
    meta = extract_meta(stderr, "FORM_DESIGN_META")
    assert list(meta["schema"]["properties"]) == ["mixture", "expansion", "schemaFormValid"]
    assert meta["schema"]["fieldsets"][0]["id"] == "fieldset-default"
    assert "index" not in meta["schema"]["fieldsets"][0]
    assert meta["schema"]["fieldsets"][0]["title"] == "基本信息"
    assert meta["schema"]["fieldsets"][0]["fields"] == ["mixture", "expansion", "schemaFormValid"]
    assert meta["schema"]["properties"]["mixture"]["index"] == 1
    assert meta["schema"]["properties"]["expansion"]["index"] == 2
    assert "index" not in meta["schema"]["properties"]["schemaFormValid"]
    assert meta["schema"]["properties"]["mixture"].get("hidden") is not True
    assert meta["schema"]["properties"]["expansion"].get("hidden") is not True
    assert meta["schema"]["properties"]["schemaFormValid"] == {
        "hidden": True,
        "type": "boolean",
        "default": True,
        "condition": "1 === 2",
        "widget": {"id": "hidden"},
    }
    for field_key in ("mixture", "expansion"):
        expression = meta["schema"]["properties"][field_key]["config"]["value"]["expression"]
        assert "setInterval" not in expression
        assert "dispatchEvent" not in expression
        assert "function findInput" not in expression

    source_params = """
const sourceParams = {
  name: 'req-1',
  catalogServiceRequest: {
    exts: {
      owner: {name: 'owner-1'},
      project: {name: 'app-1'},
      businessGroup: {name: 'bg-1'}
    }
  }
};
"""
    mixture_result = run_node_expression(
        meta["schema"]["properties"]["mixture"]["config"]["value"]["expression"],
        f"""
const model = {{}};
{source_params}
const out = fn(model, sourceParams, {{}}, null, {{}});
console.log(JSON.stringify({{out: out, model: model}}));
""",
    )
    expansion_result = run_node_expression(
        meta["schema"]["properties"]["expansion"]["config"]["value"]["expression"],
        f"""
const model = {{}};
{source_params}
const out = fn(model, sourceParams, {{}}, null, {{}});
console.log(JSON.stringify({{out: out, model: model}}));
""",
    )

    assert mixture_result["out"] == "{名称：req-1，所有者：owner-1}"
    assert mixture_result["model"]["mixture"] == "{名称：req-1，所有者：owner-1}"
    assert expansion_result["out"] == "{应用系统：app-1，业务组：bg-1}"
    assert expansion_result["model"]["expansion"] == "{应用系统：app-1，业务组：bg-1}"


def test_catalog_fields_and_table_normalization_still_work():
    catalog = load_module("catalog_fields_smoke", SCRIPTS_DIR / "_catalog_fields.py")
    projects = catalog.resolve_catalog_field_alias("应用系统")
    assert projects is not None
    assert projects.default_field_key == "projects"

    normalizer = load_module("schema_normalize_table_smoke", SCRIPTS_DIR / "_schema_normalize.py")
    schema = {
        "type": "object",
        "properties": {
            "servers": {
                "id": "servers",
                "type": "array",
                "widget": {"id": "array"},
                "items": {"properties": {"name": {"widget": {"id": "text"}}}},
            }
        },
        "widget": {"id": "object"},
    }
    normalized, warnings = normalizer.normalize_schema(schema)
    field = normalized["properties"]["servers"]
    assert field["widget"]["id"] == "table-head"
    assert field["items"]["widget"]["id"] == "table-body"
    assert field["items"]["properties"]["name"]["widget"]["id"] == "string"
    assert any("table-head" in warning for warning in warnings)


def test_catalog_field_insertion_preserves_existing_behavior_and_reports_bad_requests():
    inserter = load_module("catalog_insertion_contract", SCRIPTS_DIR / "_catalog_insertions.py")
    schema = {
        "type": "object",
        "properties": {
            "businessGroup": {
                "id": "businessGroup",
                "title": "Custom",
                "type": "string",
                "widget": {"id": "string"},
                "hidden": True,
                "condition": "model.enabled",
                "selectDatas": [{"label": "Old", "value": "old"}],
                "config": {
                    "value": {"source": "static", "value": [{"label": "Old", "value": "old"}]},
                    "visibility": {"allowInRequest": False},
                },
                "x-extra": {"keep": True},
            }
        },
        "fieldsets": [{"id": "base", "fields": []}],
    }

    warnings = inserter.apply_catalog_fields(
        schema,
        json.dumps(
            [
                {"field": "业务组"},
                {"field": "应用系统", "fieldKey": "application_context"},
                {"field": "unknown-field"},
                "bad-request",
            ],
            ensure_ascii=False,
        ),
    )

    business_group = schema["properties"]["businessGroup"]
    assert business_group["title"] == "业务组"
    assert business_group["hidden"] is True
    assert business_group["condition"] == "model.enabled"
    assert business_group["selectDatas"] == [{"label": "Old", "value": "old"}]
    assert business_group["config"]["value"]["source"] == "static"
    assert business_group["config"]["visibility"]["allowInRequest"] is False
    assert business_group["x-extra"] == {"keep": True}

    application_context = schema["properties"]["application_context"]
    assert application_context["id"] == "application_context"
    assert application_context["x-smartcmp"]["builtinCatalogField"] == "projects"
    assert schema["fieldsets"][0]["fields"] == ["businessGroup", "application_context"]
    assert any("Custom fieldKey 'application_context'" in warning for warning in warnings)
    assert any("Unknown SmartCMP catalog field" in warning for warning in warnings)
    assert any("Ignored non-object catalog field request" in warning for warning in warnings)

    with pytest.raises(ValueError, match="catalog_fields_json is not valid JSON"):
        inserter.apply_catalog_fields(schema, "[")
    with pytest.raises(ValueError, match="catalog_fields_json must be a JSON array"):
        inserter.apply_catalog_fields(schema, json.dumps({"field": "业务组"}, ensure_ascii=False))
    with pytest.raises(ValueError, match="schema.properties must be an object"):
        inserter.apply_catalog_fields({"type": "object"}, json.dumps([{"field": "业务组"}], ensure_ascii=False))


def test_catalog_field_insertion_explicitly_unhides_an_existing_field():
    inserter = load_module("catalog_insertion_unhide", SCRIPTS_DIR / "_catalog_insertions.py")
    schema = {
        "type": "object",
        "properties": {
            "businessGroup": {
                "id": "businessGroup",
                "type": "string",
                "hidden": True,
                "widget": {"id": "hidden"},
            }
        },
        "fieldsets": [{"fields": ["businessGroup"]}],
    }

    inserter.apply_catalog_fields(
        schema,
        json.dumps([{"field": "businessGroup", "hidden": False}]),
    )

    field = schema["properties"]["businessGroup"]
    assert "hidden" not in field
    assert field["widget"] == {"id": "string"}


def test_requested_fields_contract_reorders_filters_and_rejects_missing_fields():
    requested = load_module("requested_fields_contract", SCRIPTS_DIR / "_requested_fields.py")

    assert requested.load_requested_fields(json.dumps([" payload ", "owner", "payload"])) == [
        "payload",
        "owner",
    ]
    with pytest.raises(ValueError, match="requested_fields_json must be a JSON array"):
        requested.load_requested_fields(json.dumps({"field": "payload"}))
    with pytest.raises(ValueError, match="invalid item indexes: 1, 2"):
        requested.load_requested_fields(json.dumps(["payload", "", 3]))

    schema = {
        "type": "object",
        "properties": {
            "owner": {"type": "string"},
            "payload": {"type": "string"},
            "extra": {"type": "string"},
        },
        "fieldsets": [{"fields": ["extra", "owner"]}],
    }
    warnings = requested.constrain_schema_to_requested_fields(schema, ["payload", "owner"], require_all=True)

    assert list(schema["properties"]) == ["payload", "owner"]
    assert schema["fieldsets"][0]["fields"] == ["owner", "payload"]
    assert any("Removed unrequested schema properties" in warning for warning in warnings)
    assert any("Added missing requested fieldset references" in warning for warning in warnings)

    with pytest.raises(ValueError, match="schema.properties is missing requested fields"):
        requested.constrain_schema_to_requested_fields(
            {"type": "object", "properties": {}, "fieldsets": []},
            ["payload"],
            require_all=True,
        )


def test_requested_fields_preserve_smartcmp_hidden_technical_fieldset_entry():
    requested = load_module("requested_fields_smartcmp_fieldsets", SCRIPTS_DIR / "_requested_fields.py")
    schema = {
        "type": "object",
        "properties": {
            "mixture": {"type": "string"},
            "expansion": {"type": "string"},
            "schemaFormValid": {"type": "boolean", "widget": {"id": "hidden"}, "hidden": True},
        },
        "fieldsets": [
            {
                "id": "fieldset-default",
                "title": "",
                "description": "",
                "name": "",
                "fields": ["mixture", {"id": "expansion", "index": 1}, "schemaFormValid"],
            }
        ],
    }

    warnings = requested.constrain_schema_to_requested_fields(
        schema,
        ["mixture", "expansion"],
        require_all=True,
    )

    assert list(schema["properties"]) == ["mixture", "expansion", "schemaFormValid"]
    assert schema["fieldsets"][0]["id"] == "fieldset-default"
    assert schema["fieldsets"][0]["fields"] == ["mixture", "expansion", "schemaFormValid"]
    assert not any("Rebuilt root fieldsets" in warning for warning in warnings)


def test_value_expressions_repair_fullwidth_json_and_reject_ambiguous_markers():
    value_expressions = load_module("value_expression_contract", SCRIPTS_DIR / "_value_expressions.py")
    schema = {"type": "object", "properties": {}, "fieldsets": []}
    warnings = value_expressions.apply_value_expressions(
        schema,
        '[{"fieldKey":"payload"，"compose":{"$concat":["{名称：",{"$field":"名称"},"}"]}}]',
    )

    assert any("Repaired full-width JSON punctuation" in warning for warning in warnings)
    assert "payload" in schema["properties"]
    assert schema["fieldsets"][0]["fields"] == ["payload"]

    result = run_node_expression(
        schema["properties"]["payload"]["config"]["value"]["expression"],
        """
const model = {};
const sourceParams = {name: 'req-1'};
const out = fn(model, sourceParams, {}, null, {});
console.log(JSON.stringify({out: out, model: model}));
""",
    )
    assert result["out"] == "{名称：req-1}"
    assert result["model"]["payload"] == "{名称：req-1}"

    with pytest.raises(ValueError, match="value_expressions_json must be a JSON array"):
        value_expressions.apply_value_expressions(schema, json.dumps({"fieldKey": "payload"}))
    with pytest.raises(ValueError, match="must include exactly one of fields or compose"):
        value_expressions.apply_value_expressions(
            schema,
            json.dumps([{"fieldKey": "payload", "fields": [], "compose": {}}]),
        )
    with pytest.raises(ValueError, match="source marker objects cannot include sibling output keys"):
        value_expressions.apply_value_expressions(
            schema,
            json.dumps([{"fieldKey": "payload", "compose": {"$field": "名称", "extra": "bad"}}], ensure_ascii=False),
        )
    with pytest.raises(ValueError, match="Unverified value expression path"):
        value_expressions.apply_value_expressions(
            schema,
            json.dumps([{"fieldKey": "payload", "fields": [{"label": "BG", "path": "businessGroup"}]}]),
        )
    with pytest.raises(ValueError, match="Unverified value expression path"):
        value_expressions.apply_value_expressions(
            schema,
            json.dumps([{"fieldKey": "payload", "compose": {"$path": "futureCatalogField"}}]),
        )
    with pytest.raises(ValueError, match="Unverified value expression path"):
        value_expressions.apply_value_expressions(
            schema,
            json.dumps([{"fieldKey": "payload", "compose": {"$field": "futureCatalogField"}}]),
        )
    with pytest.raises(ValueError, match="schema.properties must be an object"):
        value_expressions.apply_value_expressions(
            {"type": "object"},
            json.dumps([{"fieldKey": "payload", "compose": {"$literal": "x"}}]),
        )


def test_form_designer_scripts_remain_read_only_and_reviewable():
    oversized = {}
    for script_path in SCRIPTS_DIR.glob("*.py"):
        text = script_path.read_text(encoding="utf-8")
        assert "requests.post" not in text
        assert "requests.put" not in text
        assert "requests.patch" not in text
        assert "requests.delete" not in text
        line_count = len(text.splitlines())
        if line_count > 400:
            oversized[script_path.name] = line_count

    assert oversized == {}
