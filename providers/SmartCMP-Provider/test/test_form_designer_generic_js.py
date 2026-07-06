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


def test_skill_contract_stays_generic_and_reviewable():
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    workflow_text = (SKILL_ROOT / "references" / "WORKFLOW.md").read_text(encoding="utf-8")
    combined = "\n".join((skill_text, workflow_text))

    for marker in (
        "value_expressions_json is an optional compatibility helper",
        "Do not use value_expressions_json as the default path",
        "Do not rely on catalog_fields_json to satisfy catalog context needs",
        "requested_fields_json",
    ):
        assert marker in skill_text
    assert "empty string until at least one source value resolves" in workflow_text

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
    assert list(meta["schema"]["properties"]) == ["payload"]
    assert meta["schema"]["fieldsets"][0]["fields"] == ["payload"]

    field = meta["schema"]["properties"]["payload"]
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
