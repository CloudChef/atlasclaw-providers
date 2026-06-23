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


def run_catalog_expression(
    expression: str,
    source_params: dict,
    *,
    initial_model: dict | None = None,
    initial_state: dict | None = None,
):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required to execute catalog context expressions")

    script = f"""
const expression = {json.dumps(expression, ensure_ascii=False)};
global.window = global;
global.document = {{
  querySelector: function() {{ return null; }},
  querySelectorAll: function() {{ return []; }}
}};
global.Event = function Event() {{}};
const fn = eval('(' + expression + ')');
const model = {json.dumps(initial_model or {}, ensure_ascii=False)};
const sourceParams = {json.dumps(source_params, ensure_ascii=False)};
const initialState = {json.dumps(initial_state, ensure_ascii=False)};
if (initialState) {{
  global['__smartcmp_catalog_context_' + (initialState.key || 'expansion')] = initialState.state || {{}};
}}
const cfg = {{}};
const result = fn(model, sourceParams, {{}}, null, cfg);
for (const key of Object.keys(global)) {{
  if (key.indexOf('__smartcmp_catalog_context_') === 0 && global[key] && global[key].timer) {{
    clearInterval(global[key].timer);
  }}
}}
console.log(JSON.stringify({{result: result, modelExpansion: model.expansion || null, model: model}}));
"""
    completed = subprocess.run(
        [node, "-e", script],
        check=True,
        capture_output=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def test_form_designer_skill_layout_and_metadata():
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert (SKILL_ROOT / "references" / "WORKFLOW.md").is_file()
    assert (SKILL_ROOT / "references" / "catalog-context-expression.js").is_file()
    assert (SCRIPTS_DIR / "read_form.py").is_file()
    assert (SCRIPTS_DIR / "design_form.py").is_file()
    assert (SCRIPTS_DIR / "_catalog_context_sync.py").is_file()
    assert (SCRIPTS_DIR / "_form_fetch.py").is_file()
    assert (SCRIPTS_DIR / "_schema_normalize.py").is_file()

    assert 'name: "form-designer"' in skill_text
    assert "smartcmp_read_form_schema" in skill_text
    assert "smartcmp_design_form_schema" in skill_text
    assert "catalog_context_sync_json" in skill_text
    assert "form-designer" in skill_text
    assert "workflow_role" not in skill_text
    assert "request_parent" not in skill_text
    assert "smartcmp_submit_request" not in skill_text
    assert "submit.py" not in skill_text
    assert "does not save" in skill_text
    assert "Service catalog context display values" in skill_text
    assert "`businessGroup`" in skill_text
    assert "`BusinessGroup`" in skill_text
    assert "`catalogServiceRequest.exts.businessGroup.name`" in skill_text
    assert "`exts.businessGroup.name`" not in skill_text
    assert "`businessGroupId`" in skill_text
    assert "`projects`" in skill_text
    assert "`owners`" in skill_text
    assert "`Owners`" in skill_text
    assert "`catalogServiceRequest.exts.owner.name`" in skill_text
    assert "`exts.owner.name`" not in skill_text
    assert "`name`" in skill_text
    assert "`exts.field[].id`" in skill_text
    assert "`exts.field[].name`" in skill_text
    assert "prefer human-readable display names" in skill_text
    assert "keep that ID as a fallback" not in skill_text
    assert "For the Linux VM catalog" not in skill_text
    assert "f3a4149b-cfbf-446a-a340-512a304014f2" not in skill_text
    assert "one observed catalog" in skill_text
    assert "Do not drop UUID-like values in `clean`" not in skill_text
    assert "ID fallback is better" not in skill_text
    assert "Dot-path keys such as `a.b.c` must be resolved by walking object properties" in skill_text
    assert "visible selected text before `input` or `textarea` values" in skill_text
    assert "catch errors per DOM node" in skill_text
    assert "Dynamic JavaScript context sync pattern" in skill_text
    assert '`source: "mock"`' in skill_text
    assert '`method: "mock"`' in skill_text
    assert "`function(model, sourceParams, schema, unused, cfg)`" in skill_text
    assert "`setInterval`" in skill_text
    assert "`model[KEY]`" in skill_text
    assert "`$setViewValue`" in skill_text
    assert "each `valueOf` candidate list must" in skill_text
    assert "contain the fixed display path" in skill_text
    assert "Do not cache or return incomplete values" in skill_text
    assert "`lastGood`" in skill_text
    assert "Use a rendered string field" in skill_text
    assert "Do not set `hidden: true` or `condition: \"1 === 2\"` on the auto-sync field" in skill_text
    assert "`JSON.stringify(out)`" in skill_text
    assert "Do not build pseudo-JSON strings with manual braces" in skill_text
    assert "parts.join" not in skill_text
    assert "`angular.element(e).controller('ngModel')`" in skill_text
    assert "Do not use `scope.$$childHead[KEY]`" in skill_text
    assert "Do not generate a shallow one-shot expression" in skill_text
    assert "Validate the final one-line JavaScript function for syntax" in skill_text
    assert "`deep`" in skill_text
    assert "`byLabel`" in skill_text
    assert "`roots`" in skill_text
    assert "`byLabel` must query rendered form blocks by label text" in skill_text
    assert "The `roots` helper must start with `[sourceParams, schema, cfg, model]`" in skill_text
    assert "`catalog-form`, `.catalog-form`, and `[ng-controller]`" in skill_text
    assert "Do not" in skill_text
    assert "implement `roots` as only a `$parent` walk from `cfg.$scope`" in skill_text
    assert "Keep the template's DOM `selected` helper behavior" in skill_text
    assert "read the selected option text before using `el.value`" in skill_text
    assert "Use the maintained fixed template" in skill_text
    assert "`references/catalog-context-expression.js`" in skill_text
    assert "CATALOG_CONTEXT_SYNC_TEMPLATE_V1" in skill_text
    assert "Do not hand-write" in skill_text
    assert "JavaScript lookup function" in skill_text
    assert "`FIELD_SPECS`" in skill_text
    assert "`FIELD_SPECS` may contain one entry or many entries" in skill_text
    assert "Single-field example" in skill_text
    assert "Multi-field example" in skill_text
    assert "Do not invent a new runtime lookup algorithm" in skill_text
    assert "Change only `KEY` and the `FIELD_SPECS` entries" in skill_text
    assert "use one" in skill_text
    assert "display source path per output" in skill_text
    assert "map `业务组` to `catalogServiceRequest.exts.businessGroup.name`" in skill_text
    assert "map `所有者` to `catalogServiceRequest.exts.owner.name`" in skill_text
    assert "do not add" in skill_text
    assert "`businessGroupId`, `businessGroup`, `BusinessGroup`, `ownerId`, `owner`" in skill_text
    assert "use this exact fixed spec" not in skill_text
    assert "FIELD_SPECS=[{state:'businessGroupName'" not in skill_text
    assert "`所有者`, `应用系统`, or `名称`" in skill_text
    assert "`业务组`, `所有者`, `应用系统`, or `名称`" in skill_text
    assert "or `项目`" not in skill_text
    assert "`keys:['businessGroup']`" in skill_text
    assert "`keys:['owners']`" in skill_text
    assert "`keys:['projects']`" in skill_text
    assert "`keys:['Name']`" in skill_text
    assert "is wrong" in skill_text
    assert "test-ip-form.json" not in skill_text
    assert "`KEY='infoblox_ip_attr'`" not in skill_text
    assert "`APP_OUTPUT_KEY='应用服务器'`" not in skill_text
    assert "`OWNER_OUTPUT_KEY='责任人'`" not in skill_text
    assert "Backend-facing field values must be valid JSON strings" in skill_text
    assert "Do not add UUID rejection or `resolveById` logic" not in skill_text
    assert "Do not drop UUID-like values in `clean`" not in skill_text
    assert "ID fallback is better" not in skill_text
    assert "clear any previous interval before starting a new one" in skill_text
    assert 'Find the target input with `[name="\'+KEY+\'"],#\'+KEY` first' in skill_text
    assert "Do not rely only on `[ng-model*=\"...KEY...\"]` substring selectors" in skill_text
    assert "The submitted auto-sync value must remain a string" in skill_text
    assert "Do not return a JavaScript object or array from the expression" in skill_text
    assert "Do not manually convert Chinese labels or values to Unicode escape sequences" in skill_text
    assert "Keep Chinese labels and Chinese punctuation as literal UTF-8 text" in skill_text
    assert "Final response must include the normalized schema JSON text" in skill_text
    assert "Do not replace the JSON with a summary, table, or usage notes" in skill_text
    assert "Return the root schema object directly" in skill_text
    assert "Do not wrap it in `{ \"schema\": ... }`" in skill_text
    assert "Do not call `session_status`" in skill_text
    assert "Fixed service catalog context labels are sufficient" in skill_text
    assert "Do not ask the user for existing form schema" in skill_text
    assert "Do not ask for field IDs, field keys, or schema versions" in skill_text
    assert "Tool or catalog lookup failure must not block JSON generation" in skill_text
    assert "Do not call `smartcmp_read_form_schema` for new forms" in skill_text
    assert "The `字段A` and `字段B` entries in `references/catalog-context-expression.js` are placeholders" in skill_text
    assert "test-eip" not in skill_text
    assert "`KEY='mixture'`" not in skill_text
    assert "The four-field variant adds `业务组`" not in skill_text
    assert "The fixed-label subset can contain one, two, three, or four `FIELD_SPECS` entries" in skill_text
    assert "Do not answer that `CATALOG_CONTEXT_SYNC_TEMPLATE_V1` only supports `字段A` and `字段B`" in skill_text
    assert "`FIELD_SPECS=[{state:'fieldA'" not in skill_text


def test_form_designer_skill_documents_regenerate_mode():
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert '"regenerate"' in skill_text
    assert "mode=regenerate" in skill_text
    assert "replacement schema" in skill_text
    assert "For ordinary user requests to change a form from" in skill_text
    assert "a URL, prefer `mode=regenerate`" in skill_text


def test_form_designer_skill_treats_bare_form_url_as_read_only_inspection():
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert "A bare form edit URL without an explicit change request" in skill_text
    assert "is an inspect/read request only" in skill_text
    assert "call `smartcmp_read_form_schema`" in skill_text
    assert "do not call `smartcmp_design_form_schema`" in skill_text
    assert "`mode=modify`" in skill_text
    assert "`mode=regenerate`" in skill_text
    assert "`catalog_context_sync_json`" in skill_text


def test_form_designer_skill_routes_url_expansion_context_sync_to_deterministic_tool():
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert "If a URL request only changes one existing field into fixed service-catalog" in skill_text
    assert "context JSON" in skill_text
    assert "`mode=modify`" in skill_text
    assert "Set `catalog_context_sync_json.fieldKey` to" in skill_text
    assert "the field named by the user" in skill_text
    assert "set `catalog_context_sync_json.outputs` to the" in skill_text
    assert "requested fixed context labels or aliases" in skill_text
    assert "Do not hand-write a replacement" in skill_text
    assert "`config.value.expression`" in skill_text
    assert "修改这个表单的expansion字段" not in skill_text


def test_form_designer_skill_preserves_catalog_fields_json_contract():
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    parameters_block = re.search(
        r"tool_design_parameters:\s*\|\s*(\{.*?\n  \})",
        skill_text,
        re.DOTALL,
    )

    assert 'catalog_fields_json: "--catalog-fields-json"' in skill_text
    assert parameters_block is not None
    assert '"catalog_fields_json"' in parameters_block.group(1)
    assert "do not also hand-write duplicate catalog fields" in skill_text.lower()
    assert "preserves existing" in skill_text
    assert "JavaScript and unknown keys" in skill_text


def test_catalog_context_expression_template_uses_generic_field_specs():
    template = (SKILL_ROOT / "references" / "catalog-context-expression.js").read_text(encoding="utf-8")
    compact = "".join(line.strip() for line in template.splitlines())

    assert "CATALOG_CONTEXT_SYNC_TEMPLATE_V1" in template
    assert "function(model,sourceParams,schema,unused,cfg)" in template
    assert "FIELD_SPECS" in template
    assert "JSON.stringify(out)" in template
    assert "valueOf(spec.state,spec.keys,spec.labels)" in template
    assert "for(var i=0;i<FIELD_SPECS.length;i++)" in template
    assert "Array.isArray(v)" in template
    assert "arr.join(',')" in template
    assert "out[spec.output]={value:v}" in template
    assert "String(k).split('.')" in template
    assert "var selectedText=root.querySelector" in template
    assert "PREFIX=ROOT+KEY+'_'" in compact
    assert "ck.indexOf(PREFIX)===0" in compact
    assert "for(var i=0;i<nodes.length;i++){try{" in compact
    assert "fieldAName" in template
    assert "FieldA.name" in template
    assert "字段A" in template
    assert "业务组" not in template
    assert "所有者" not in template
    assert "0-9a-f]{8}" not in template
    assert "setInterval" in template
    assert "lastGood" in template


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


def test_normalize_schema_preserves_catalog_metadata_and_warns_for_unknown_builtin():
    module = load_module("test_schema_normalize_catalog_metadata", SCRIPTS_DIR / "_schema_normalize.py")

    known_schema, known_warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "businessGroup": {
                    "type": "string",
                    "widget": {"id": "string"},
                    "x-smartcmp": {"builtinCatalogField": "businessGroup.code"},
                }
            },
        }
    )
    unknown_schema, unknown_warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "unknown_context": {
                    "type": "string",
                    "widget": {"id": "string"},
                    "x-smartcmp": {"builtinCatalogField": "businessGroup.costCenter"},
                }
            },
        }
    )

    assert (
        known_schema["properties"]["businessGroup"]["x-smartcmp"]["builtinCatalogField"]
        == "businessGroup.code"
    )
    assert not [warning for warning in known_warnings if "Unknown SmartCMP catalog field" in warning]
    assert (
        unknown_schema["properties"]["unknown_context"]["x-smartcmp"]["builtinCatalogField"]
        == "businessGroup.costCenter"
    )
    assert any("Unknown SmartCMP catalog field" in warning for warning in unknown_warnings)


def test_normalize_schema_warns_for_risky_javascript_expression():
    module = load_module("test_schema_normalize_risky_js", SCRIPTS_DIR / "_schema_normalize.py")

    _schema, warnings = module.normalize_schema(
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
                            "expression": "function(model){ return eval(model.name); }",
                        }
                    },
                }
            },
        }
    )

    assert any("eval" in warning for warning in warnings)


def test_normalize_schema_repairs_hidden_mock_autosync_field_for_submission():
    module = load_module("test_schema_normalize_autosync", SCRIPTS_DIR / "_schema_normalize.py")

    schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "title": "test-linux",
            "properties": {
                "expansion": {
                    "type": "string",
                    "id": "expansion",
                    "index": 0,
                    "title": "expansion",
                    "widget": {"id": "hidden"},
                    "hidden": True,
                    "condition": "1 === 2",
                    "config": {
                        "visibility": {
                            "allowInRequest": True,
                            "allowInApproval": False,
                        },
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": "function(model, sourceParams, schema, unused, cfg) { return ''; }",
                        },
                    },
                }
            },
        }
    )

    field = schema["properties"]["expansion"]
    assert field["widget"]["id"] == "string"
    assert field["default"] == "AUTO_SYNC_PENDING"
    assert "hidden" not in field
    assert "condition" not in field
    assert field["hideTitle"] is True
    assert field["config"]["value"]["source"] == "mock"
    assert field["config"]["visibility"] == {
        "allowInRequest": True,
        "allowInApproval": False,
        "allowInCatalog": False,
    }
    assert field["config"]["modification"] == {
        "allowInRequest": True,
        "allowInApproval": False,
        "allowInCatalog": False,
    }
    assert schema["properties"]["schemaFormValid"]["type"] == "boolean"
    assert schema["fieldsets"][0]["fields"] == ["expansion", "schemaFormValid"]
    assert warnings


def test_normalize_schema_normalizes_added_schema_form_valid_field():
    module = load_module(
        "test_schema_normalize_schema_form_valid",
        SCRIPTS_DIR / "_schema_normalize.py",
    )

    schema, _warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "expansion": {
                    "type": "string",
                    "widget": {"id": "hidden"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": (
                                "function(model,sourceParams,schema,unused,cfg){"
                                "var out={};out['context']={value:'ready'};"
                                "return JSON.stringify(out);}"
                            ),
                        }
                    },
                }
            },
        }
    )

    field = schema["properties"]["schemaFormValid"]
    assert field["id"] == "schemaFormValid"
    assert isinstance(field["index"], int)
    assert field["config"]["visibility"]["allowInRequest"] is True
    assert field["config"]["visibility"]["allowInApproval"] is True


def test_normalize_schema_does_not_repair_visible_mock_value_field_as_autosync():
    module = load_module(
        "test_schema_normalize_visible_mock_value",
        SCRIPTS_DIR / "_schema_normalize.py",
    )

    schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "displayName": {
                    "type": "string",
                    "title": "Display name",
                    "widget": {"id": "string"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": "function(model){ return model.name || ''; }",
                        }
                    },
                }
            },
        }
    )

    field = schema["properties"]["displayName"]
    assert field["title"] == "Display name"
    assert field["widget"]["id"] == "string"
    assert "default" not in field
    assert "hideTitle" not in field
    assert "schemaFormValid" not in schema["properties"]
    assert "fieldsets" not in schema
    assert "modification" not in field["config"]
    assert "allowInCatalog" not in field["config"]["visibility"]
    assert not any("mock auto-sync" in warning for warning in warnings)


def test_normalize_schema_does_not_repair_visible_json_stringify_field_as_autosync():
    module = load_module(
        "test_schema_normalize_visible_json_stringify_value",
        SCRIPTS_DIR / "_schema_normalize.py",
    )

    schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "tagsJson": {
                    "type": "string",
                    "title": "Tags JSON",
                    "widget": {"id": "string"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": "function(model){ return JSON.stringify(model.tags || []); }",
                        }
                    },
                }
            },
        }
    )

    field = schema["properties"]["tagsJson"]
    assert field["title"] == "Tags JSON"
    assert field["widget"]["id"] == "string"
    assert "default" not in field
    assert "hideTitle" not in field
    assert "schemaFormValid" not in schema["properties"]
    assert "fieldsets" not in schema
    assert "modification" not in field["config"]
    assert "allowInCatalog" not in field["config"]["visibility"]
    assert not any("mock auto-sync" in warning for warning in warnings)


def test_normalize_schema_unwraps_schema_container_before_repairing_autosync_field():
    module = load_module("test_schema_normalize_autosync_unwrap", SCRIPTS_DIR / "_schema_normalize.py")

    schema, warnings = module.normalize_schema(
        {
            "schema": {
                "type": "object",
                "properties": {
                    "expansion": {
                        "id": "expansion",
                        "type": "string",
                        "widget": {"id": "hidden"},
                        "hidden": True,
                        "condition": "1 === 2",
                        "config": {
                            "value": {
                                "source": "mock",
                                "method": "mock",
                                "expression": "function(model, sourceParams, schema, unused, cfg) { return ''; }",
                            }
                        },
                    }
                },
            }
        }
    )

    assert "schema" not in schema
    assert schema["properties"]["expansion"]["widget"]["id"] == "string"
    assert "hidden" not in schema["properties"]["expansion"]
    assert schema["fieldsets"][0]["fields"] == ["expansion", "schemaFormValid"]
    assert any("Unwrapped top-level schema container" in warning for warning in warnings)


def test_normalize_schema_repairs_invalid_fieldset_fields_for_autosync_field():
    module = load_module(
        "test_schema_normalize_autosync_invalid_fieldsets",
        SCRIPTS_DIR / "_schema_normalize.py",
    )

    schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "expansion": {
                    "type": "string",
                    "id": "expansion",
                    "widget": {"id": "string"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": "function(model, sourceParams, schema, unused, cfg) { return 'AUTO_SYNC_PENDING'; }",
                        }
                    },
                }
            },
            "fieldsets": [{"id": "fieldset-expansion", "fields": None}],
        }
    )

    assert schema["fieldsets"][0]["fields"] == ["expansion", "schemaFormValid"]
    assert any("Registered mock auto-sync fields in fieldsets" in warning for warning in warnings)


def test_normalize_schema_keeps_mock_autosync_value_as_utf8_string():
    module = load_module("test_schema_normalize_autosync_utf8", SCRIPTS_DIR / "_schema_normalize.py")
    escaped_department = "\\u" + "90e8" + "\\u" + "95e8"

    schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "expansion": {
                    "type": "object",
                    "id": "expansion",
                    "widget": {"id": "hidden"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": (
                                'function(model, sourceParams, schema, unused, cfg) { '
                                f'var KEY="expansion"; var label="{escaped_department}"; '
                                'var out={}; out[label]={value:(sourceParams.name||"")}; '
                                'out["所有者"]={value:"admin"}; var v=JSON.stringify(out); '
                                "model[KEY]=v; return v; }"
                            ),
                        },
                    },
                }
            },
        }
    )

    field = schema["properties"]["expansion"]
    expression = field["config"]["value"]["expression"]
    assert field["type"] == "string"
    assert "部门" in expression
    assert "JSON.stringify(out)" in expression
    assert not re.search(r"\\u(?:90e8|95e8)", expression)
    assert "model[KEY]=v" in expression
    assert warnings


def test_normalize_schema_warns_about_mock_autosync_runtime_antipatterns():
    module = load_module("test_schema_normalize_autosync_antipatterns", SCRIPTS_DIR / "_schema_normalize.py")

    _schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "expansion": {
                    "type": "string",
                    "id": "expansion",
                    "widget": {"id": "string"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": (
                                "function(model, sourceParams, schema, unused, cfg) { "
                                "function isUuid(v) { return /^[0-9a-f-]{36}$/i.test(v); } "
                                "function roots(scope) { var result = []; var s = cfg.$scope; "
                                "while (s) { result.push(s); s = s.$parent; } return result; } "
                                "var val = el.value || (el.tagName === 'SELECT' && el.options[el.selectedIndex] ? "
                                "el.options[el.selectedIndex].text : ''); "
                                "document.querySelector('[ng-model*=\"' + FIELD_KEY + '\"]'); "
                                "if (!window['__expansion_interval_set']) { window['__expansion_interval_set'] = true; "
                                "setInterval(function() {}, 2000); } "
                                "if (isUuid(model.businessGroup)) return 'AUTO_SYNC_PENDING'; "
                                "return model.expansion || 'AUTO_SYNC_PENDING'; }"
                            ),
                        },
                    },
                }
            },
        }
    )

    assert any("selected option text before el.value" in warning for warning in warnings)
    assert any("one-time interval-set flag" in warning for warning in warnings)
    assert any("start from sourceParams/schema/cfg/model and Angular catalog scopes" in warning for warning in warnings)
    assert any("attempt ID-to-name resolution before rejecting UUID control values" in warning for warning in warnings)
    assert any("target input by name or id before ng-model substring selectors" in warning for warning in warnings)


def test_normalize_schema_warns_when_autosync_builds_pseudo_json_string():
    module = load_module("test_schema_normalize_autosync_pseudo_json", SCRIPTS_DIR / "_schema_normalize.py")

    _schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "expansion": {
                    "type": "string",
                    "id": "expansion",
                    "widget": {"id": "string"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": (
                                "function(model, sourceParams, schema, unused, cfg) { "
                                "var FIELDS=[['businessGroupName','业务组'],['userName','所有者']]; "
                                "var parts=[]; for(var i=0;i<FIELDS.length;i++){parts.push(FIELDS[i][1]+'：'+model[FIELDS[i][0]]);} "
                                "return '{'+parts.join('，')+'}'; }"
                            ),
                        },
                    },
                }
            },
        }
    )

    assert any("valid JSON string with JSON.stringify(out)" in warning for warning in warnings)


def test_normalize_schema_warns_when_autosync_rejects_uuid_control_values_inline():
    module = load_module("test_schema_normalize_autosync_inline_uuid_reject", SCRIPTS_DIR / "_schema_normalize.py")

    _schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "expansion": {
                    "type": "string",
                    "id": "expansion",
                    "widget": {"id": "string"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": (
                                "function(model, sourceParams, schema, unused, cfg) { "
                                "var keys=['businessGroup','BusinessGroup','owners','Owners']; "
                                "var v=model.businessGroup; "
                                "if(v && typeof v==='string' && "
                                "!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v) "
                                "&& !/^\\d+$/.test(v)) return JSON.stringify({'业务组':{value:v}}); "
                                "return 'AUTO_SYNC_PENDING'; }"
                            ),
                        },
                    },
                }
            },
        }
    )

    assert any("should not reject UUID-like SmartCMP control values" in warning for warning in warnings)


def test_normalize_schema_warns_about_malformed_autosync_roots_try_catch():
    module = load_module("test_schema_normalize_autosync_malformed_roots", SCRIPTS_DIR / "_schema_normalize.py")

    _schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "expansion": {
                    "type": "string",
                    "id": "expansion",
                    "widget": {"id": "string"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": (
                                "function(model, sourceParams, schema, unused, cfg){"
                                "var helpers={roots:function(sp,sc,cfg,m){var arr=[sp,sc,cfg,m];"
                                "try{var body=document.body;if(body){var forms=body.querySelectorAll('catalog-form,.catalog-form,[ng-controller]');"
                                "for(var f=0;f<forms.length;f++){var iso=angular.element(forms[f]).isolateScope();"
                                "if(iso)arr.push(iso);}}catch(e){}return arr;}};"
                                "return 'AUTO_SYNC_PENDING';}"
                            ),
                        },
                    },
                }
            },
        }
    )

    assert any("malformed roots helper try/catch" in warning for warning in warnings)


def test_normalize_schema_warns_when_autosync_omits_per_root_params_and_dom_label_fallback():
    module = load_module("test_schema_normalize_autosync_missing_paths", SCRIPTS_DIR / "_schema_normalize.py")

    _schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "expansion": {
                    "type": "string",
                    "id": "expansion",
                    "widget": {"id": "string"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": (
                                "function(model, sourceParams, schema, unused, cfg){"
                                "var helpers={byLabel:function(roots,labels){return undefined;},"
                                "valueOf:function(roots,keys,labelKeys){return helpers.byLabel(roots,labelKeys);}};"
                                "var pm=sourceParams||{};var pf=pm.genericRequest&&pm.genericRequest.processForm||{};"
                                "return model.expansion||'AUTO_SYNC_PENDING';}"
                            ),
                        },
                    },
                }
            },
        }
    )

    assert any("scan params/resourceBundleParams/genericRequest.processForm for every root" in warning for warning in warnings)
    assert any("byLabel helper should query rendered form blocks by label text" in warning for warning in warnings)


def test_normalize_schema_warns_when_value_of_ignores_requested_output_name():
    module = load_module("test_schema_normalize_autosync_ignores_output_name", SCRIPTS_DIR / "_schema_normalize.py")

    _schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "expansion": {
                    "type": "string",
                    "id": "expansion",
                    "widget": {"id": "string"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": (
                                "function(model, sourceParams, schema, unused, cfg){"
                                "var valueOf=function(name,rootsList){for(var i=0;i<rootsList.length;i++){"
                                "var r=rootsList[i];if(r.fieldAName)return r.fieldAName;"
                                "if(r.fieldBName)return r.fieldBName;}return'';};"
                                "var out={};out['字段A']={value:valueOf('字段A',[sourceParams])};"
                                "out['字段B']={value:valueOf('字段B',[sourceParams])};"
                                "return JSON.stringify(out);}"
                            ),
                        },
                    },
                }
            },
        }
    )

    assert any("valueOf helper that ignores the requested output name" in warning for warning in warnings)


def test_normalize_schema_warns_about_catalog_template_regressions():
    module = load_module("test_schema_normalize_autosync_template_regressions", SCRIPTS_DIR / "_schema_normalize.py")

    _schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "expansion": {
                    "type": "string",
                    "id": "expansion",
                    "widget": {"id": "string"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": (
                                "function(model,sourceParams,schema,unused,cfg){"
                                "var TEMPLATE='CATALOG_CONTEXT_SYNC_TEMPLATE_V1';"
                                "var FIELD_SPECS=[{keys:['selectedThing.name'],labels:['Thing']}];"
                                "var direct=function(o,k){return o&&o[k];};"
                                "var selected=function(root){var e=root.querySelector('select,input,textarea,.selected-value');return e&&e.value;};"
                                "var roots=function(){var nodes=document.querySelectorAll('[ng-controller]');"
                                "for(var i=0;i<nodes.length;i++){var ae=angular.element(nodes[i]);out.push(ae.scope());}};"
                                "return model.expansion||'AUTO_SYNC_PENDING';}"
                            ),
                        },
                    },
                }
            },
        }
    )

    assert any("Dot-path FIELD_SPECS keys" in warning for warning in warnings)
    assert any("visible selected text before input" in warning for warning in warnings)
    assert any("catch DOM node errors per node" in warning for warning in warnings)


def test_normalize_schema_warns_when_owner_arrays_are_not_handled():
    module = load_module("test_schema_normalize_autosync_owner_arrays", SCRIPTS_DIR / "_schema_normalize.py")

    _schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "expansion": {
                    "type": "string",
                    "id": "expansion",
                    "widget": {"id": "string"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": (
                                "function(model,sourceParams,schema,unused,cfg){"
                                "var TEMPLATE='CATALOG_CONTEXT_SYNC_TEMPLATE_V1';"
                                "var FIELD_SPECS=[{state:'owner',output:'所有者',keys:['owners','Owners'],labels:['所有者']}];"
                                "var text=function(v){if(v===null||v===undefined)return'';"
                                "if(typeof v==='object')v=v.name||v.username||v.id||'';return String(v);};"
                                "return model.expansion||'AUTO_SYNC_PENDING';}"
                            ),
                        },
                    },
                }
            },
        }
    )

    assert any("handle array values such as owners/Owners" in warning for warning in warnings)


def test_normalize_schema_warns_when_display_outputs_fall_back_to_ids():
    module = load_module("test_schema_normalize_autosync_display_output_ids", SCRIPTS_DIR / "_schema_normalize.py")

    _schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "expansion": {
                    "type": "string",
                    "id": "expansion",
                    "widget": {"id": "string"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": (
                                "function(model,sourceParams,schema,unused,cfg){"
                                "var TEMPLATE='CATALOG_CONTEXT_SYNC_TEMPLATE_V1';"
                                "var FIELD_SPECS=[{state:'businessGroup',output:'业务组',"
                                "keys:['catalogServiceRequest.exts.businessGroup.name','businessGroupId','BusinessGroup'],"
                                "labels:['业务组']},{state:'owner',output:'所有者',"
                                "keys:['catalogServiceRequest.exts.owner.name','ownerId','owners','Owners'],"
                                "labels:['所有者']}];"
                                "return model.expansion||'AUTO_SYNC_PENDING';}"
                            ),
                        },
                    },
                }
            },
        }
    )

    assert any("uses non-fixed display keys" in warning for warning in warnings)


def test_normalize_schema_warns_when_display_outputs_use_control_ids_directly():
    module = load_module(
        "test_schema_normalize_autosync_direct_control_ids",
        SCRIPTS_DIR / "_schema_normalize.py",
    )

    _schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "expansion": {
                    "type": "string",
                    "id": "expansion",
                    "widget": {"id": "string"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": (
                                "function(model,sourceParams,schema,unused,cfg){"
                                "var TEMPLATE='CATALOG_CONTEXT_SYNC_TEMPLATE_V1';"
                                "var FIELD_SPECS=[{state:'businessGroup',output:'业务组',"
                                "keys:['businessGroup'],labels:['业务组']},"
                                "{state:'owner',output:'所有者',keys:['owner'],labels:['所有者']}];"
                                "return model.expansion||'AUTO_SYNC_PENDING';}"
                            ),
                        },
                    },
                }
            },
        }
    )

    assert any("uses non-fixed display keys" in warning for warning in warnings)


def test_normalize_schema_warns_when_field_spec_keys_precede_display_output():
    module = load_module(
        "test_schema_normalize_autosync_field_spec_key_order",
        SCRIPTS_DIR / "_schema_normalize.py",
    )

    _schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "expansion": {
                    "type": "string",
                    "id": "expansion",
                    "widget": {"id": "string"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": (
                                "function(model,sourceParams,schema,unused,cfg){"
                                "var TEMPLATE='CATALOG_CONTEXT_SYNC_TEMPLATE_V1';"
                                "var FIELD_SPECS=[{state:'owner',keys:['owner','owners'],"
                                "output:'所有者',labels:['所有者']}];"
                                "return model.expansion||'AUTO_SYNC_PENDING';}"
                            ),
                        },
                    },
                }
            },
        }
    )

    assert any("uses non-fixed display keys" in warning for warning in warnings)


def test_normalize_schema_uses_strict_display_output_allowlist():
    module_text = (SCRIPTS_DIR / "_schema_normalize.py").read_text(encoding="utf-8")

    assert "_STRICT_DISPLAY_OUTPUT_KEYS" in module_text
    assert "_ID_BEARING_CONTEXT_KEYS" not in module_text
    assert '"业务组": {"catalogServiceRequest.exts.businessGroup.name"}' in module_text
    assert '"所有者": {"catalogServiceRequest.exts.owner.name"}' in module_text
    assert '"应用系统": {"catalogServiceRequest.exts.project.name"}' in module_text
    assert '"名称": {"name"}' in module_text


def test_normalize_schema_replaces_handwritten_catalog_context_expression_with_template():
    module = load_module(
        "test_schema_normalize_replaces_handwritten_catalog_context",
        SCRIPTS_DIR / "_schema_normalize.py",
    )

    schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "expansion": {
                    "type": "string",
                    "id": "expansion",
                    "widget": {"id": "string"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": (
                                "function(model, sourceParams, schema, unused, cfg) { "
                                "var KEY = 'expansion'; "
                                "var FIELD_SPECS = [{ state: 'projectName', output: '应用系统', "
                                "keys: ['catalogServiceRequest.exts.project.name'], labels: ['应用系统', 'Projects'] }]; "
                                "var stateKey = '_expansionState'; "
                                "return model[KEY] || 'AUTO_SYNC_PENDING'; "
                                "}"
                            ),
                        },
                    },
                }
            },
        }
    )
    expression = schema["properties"]["expansion"]["config"]["value"]["expression"]

    assert "CATALOG_CONTEXT_SYNC_TEMPLATE_V1" in expression
    assert "stateKey" not in expression
    assert "output:'应用系统'" in expression
    assert "catalogServiceRequest.exts.project.name" in expression
    assert any("Replaced hand-written catalog context expression" in warning for warning in warnings)

    result = run_catalog_expression(
        expression,
        {"catalogServiceRequest": {"exts": {"project": {"name": "研发门户"}}}},
    )

    assert json.loads(result["result"]) == {"应用系统": {"value": "研发门户"}}
    assert result["modelExpansion"] == result["result"]


def test_normalize_schema_warns_when_display_outputs_use_extra_fallback_keys():
    module = load_module(
        "test_schema_normalize_autosync_extra_fallback_keys",
        SCRIPTS_DIR / "_schema_normalize.py",
    )

    _schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "expansion": {
                    "type": "string",
                    "id": "expansion",
                    "widget": {"id": "string"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": (
                                "function(model,sourceParams,schema,unused,cfg){"
                                "var TEMPLATE='CATALOG_CONTEXT_SYNC_TEMPLATE_V1';"
                                "var FIELD_SPECS=[{state:'businessGroupName',output:'业务组',"
                                "keys:['catalogServiceRequest.exts.businessGroup.name','exts.businessGroup.name','businessGroupName'],"
                                "labels:['业务组','BusinessGroup']},{state:'ownerName',output:'所有者',"
                                "keys:['catalogServiceRequest.exts.owner.name','ownerName','ownerDisplayName'],"
                                "labels:['所有者','Owner','Owners']}];"
                                "return model.expansion||'AUTO_SYNC_PENDING';}"
                            ),
                        },
                    },
                }
            },
        }
    )

    assert any("uses non-fixed display keys" in warning for warning in warnings)


def test_normalize_schema_warns_when_project_and_name_outputs_use_extra_keys():
    module = load_module(
        "test_schema_normalize_autosync_project_name_extra_keys",
        SCRIPTS_DIR / "_schema_normalize.py",
    )

    _schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "expansion": {
                    "type": "string",
                    "id": "expansion",
                    "widget": {"id": "string"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": (
                                "function(model,sourceParams,schema,unused,cfg){"
                                "var TEMPLATE='CATALOG_CONTEXT_SYNC_TEMPLATE_V1';"
                                "var FIELD_SPECS=[{state:'projectName',output:'应用系统',"
                                "keys:['catalogServiceRequest.exts.project.name','projects','Projects','projectName'],"
                                "labels:['应用系统','Projects']},{state:'requestName',output:'名称',"
                                "keys:['name','Name','requestName'],labels:['名称','Name']}];"
                                "return model.expansion||'AUTO_SYNC_PENDING';}"
                            ),
                        },
                    },
                }
            },
        }
    )

    assert any("uses non-fixed display keys" in warning for warning in warnings)


def test_normalize_schema_warns_when_autosync_expression_is_abbreviated():
    module = load_module("test_schema_normalize_autosync_ellipsis", SCRIPTS_DIR / "_schema_normalize.py")

    _schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "expansion": {
                    "type": "string",
                    "id": "expansion",
                    "widget": {"id": "string"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": (
                                "function(model,sourceParams,schema,unused,cfg){"
                                "var TEMPLATE='CATALOG_CONTEXT_SYNC_TEMPLATE_V1';..."
                            ),
                        },
                    },
                }
            },
        }
    )

    assert any("literal ellipsis placeholder" in warning for warning in warnings)


def test_normalize_schema_warns_when_test_ip_form_expression_is_copied_verbatim():
    module = load_module("test_schema_normalize_autosync_copied_test_ip", SCRIPTS_DIR / "_schema_normalize.py")

    _schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "infoblox_ip_attr": {
                    "type": "string",
                    "id": "infoblox_ip_attr",
                    "widget": {"id": "string"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": (
                                "function(model,sourceParams,schema,unused,cfg){"
                                "var KEY='infoblox_ip_attr',APP_OUTPUT_KEY='应用服务器',OWNER_OUTPUT_KEY='责任人';"
                                "var valueOf=function(name,keys,labels){return model&&model[name]||'';};"
                                "var out={};out[APP_OUTPUT_KEY]={value:valueOf('app',[],[])};"
                                "out[OWNER_OUTPUT_KEY]={value:valueOf('owner',[],[])};"
                                "return JSON.stringify(out);}"
                            ),
                        },
                    },
                }
            },
        }
    )

    assert any("copy a historical IP-form expression verbatim" in warning for warning in warnings)


def test_normalize_schema_warns_when_catalog_template_placeholders_remain():
    module = load_module(
        "test_schema_normalize_autosync_placeholder_specs",
        SCRIPTS_DIR / "_schema_normalize.py",
    )

    _schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "mixture": {
                    "type": "string",
                    "id": "mixture",
                    "widget": {"id": "string"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": (
                                "function(model,sourceParams,schema,unused,cfg){"
                                "var TEMPLATE='CATALOG_CONTEXT_SYNC_TEMPLATE_V1';"
                                "var KEY='mixture',FIELD_SPECS=[{state:'fieldA',output:'字段A',"
                                "keys:['fieldAName'],labels:['字段A']},{state:'fieldB',output:'字段B',"
                                "keys:['fieldBName'],labels:['字段B']}];"
                                "return model.mixture||'AUTO_SYNC_PENDING';}"
                            ),
                        },
                    },
                }
            },
        }
    )

    assert any("still contains placeholder FIELD_SPECS entries" in warning for warning in warnings)


def test_normalize_schema_does_not_replace_autosync_lookup_algorithm():
    module = load_module("test_schema_normalize_autosync_preserve", SCRIPTS_DIR / "_schema_normalize.py")

    expression = (
        "function(model,sourceParams,schema,unused,cfg){var KEY='expansion',APP_OUTPUT_KEY='业务组',"
        "OWNER_OUTPUT_KEY='所有者',W=window,ID='__smartcmp_ip_attr_'+KEY,state=W[ID]||{};"
        "state.values=state.values||{};var text=function(v){if(v===null||v===undefined)return'';"
        "if(typeof v==='object')v=v.label||v.name||v.displayName||v.text||v.value||v.id||'';"
        "return String(v).replace(/^\\s+|\\s+$/g,'');};var clean=function(v){v=text(v);return v;};"
        "var direct=function(o,k){try{if(!o||typeof o!=='object')return'';var v=o[k];"
        "if(v!==undefined&&v!==null)return clean(v);}catch(e){}return'';};"
        "var pick=function(o,keys){for(var i=0;i<keys.length;i++){var v=direct(o,keys[i]);if(v)return v;}return'';};"
        "var roots=function(){var out=[sourceParams,schema,cfg,model];return out;};"
        "var valueOf=function(name,keys,labels){var rs=roots(),v='';for(var i=0;i<rs.length;i++){v=pick(rs[i],keys);if(v){state.values[name]=v;return v;}}return state.values[name]||'';};"
        "var resolve=function(){var bg=valueOf('businessGroupName',['businessGroupName','businessGroup'],['业务组']);"
        "var owner=valueOf('ownerName',['ownerName','owner'],['所有者']);if(!bg||!owner)return state.lastGood||'';"
        "var out={};out[APP_OUTPUT_KEY]={value:bg};out[OWNER_OUTPUT_KEY]={value:owner};"
        "var v=JSON.stringify(out);state.lastGood=v;return v;};"
        "var write=function(v){if(model)model[KEY]=v;return v;};if(state.timer)clearInterval(state.timer);"
        "state.timer=setInterval(function(){write(resolve());},500);W[ID]=state;return write(resolve());}"
    )

    schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "expansion": {
                    "type": "string",
                    "id": "expansion",
                    "widget": {"id": "string"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": expression,
                        },
                    },
                }
            },
        }
    )

    normalized_expression = schema["properties"]["expansion"]["config"]["value"]["expression"]
    assert normalized_expression == expression
    assert "JSON.stringify(out)" in normalized_expression
    assert "state.timer=setInterval" in normalized_expression
    assert not any("Replaced fragile mock auto-sync expression" in warning for warning in warnings)


def test_normalize_schema_warns_without_replacing_fragile_business_group_owner_expression():
    module = load_module("test_schema_normalize_autosync_warn_only", SCRIPTS_DIR / "_schema_normalize.py")
    expression = (
        "function(model, sourceParams, schema, unused, cfg) { "
        "var FIELD_KEY='expansion'; var KEY='expansion'; "
        "var APP_OUTPUT_KEY='业务组'; var OWNER_OUTPUT_KEY='所有者'; "
        "function isUuid(v) { return /^[0-9a-f-]{36}$/i.test(v); } "
        "function roots(scope) { var result = []; var s = cfg.$scope; "
        "while (s) { result.push(s); s = s.$parent; } return result; } "
        "var val = el.value || (el.tagName === 'SELECT' && el.options[el.selectedIndex] ? "
        "el.options[el.selectedIndex].text : ''); "
        "document.querySelector('[ng-model*=\"' + KEY + '\"]'); "
        "if (!window['__expansion_interval_set']) { window['__expansion_interval_set'] = true; "
        "setInterval(function() {}, 2000); } "
        "if (isUuid(model.businessGroup)) return 'AUTO_SYNC_PENDING'; "
        "return model.expansion || 'AUTO_SYNC_PENDING'; }"
    )

    schema, warnings = module.normalize_schema(
        {
            "type": "object",
            "properties": {
                "expansion": {
                    "type": "string",
                    "id": "expansion",
                    "widget": {"id": "string"},
                    "config": {
                        "value": {
                            "source": "mock",
                            "method": "mock",
                            "expression": expression,
                        },
                    },
                }
            },
        }
    )

    normalized_expression = schema["properties"]["expansion"]["config"]["value"]["expression"]
    assert normalized_expression == expression
    assert any("selected option text before el.value" in warning for warning in warnings)
    assert any("one-time interval-set flag" in warning for warning in warnings)
    assert any("start from sourceParams/schema/cfg/model and Angular catalog scopes" in warning for warning in warnings)
    assert any("attempt ID-to-name resolution before rejecting UUID control values" in warning for warning in warnings)
    assert any("target input by name or id before ng-model substring selectors" in warning for warning in warnings)
    assert not any("Replaced fragile mock auto-sync expression" in warning for warning in warnings)


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


def test_design_form_script_can_insert_catalog_standard_fields(monkeypatch):
    schema_json = json.dumps({"type": "object", "properties": {}}, ensure_ascii=False)
    catalog_fields_json = json.dumps(
        [{"field": "businessGroup.code"}, {"field": "application.name"}],
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
    assert (
        meta["schema"]["properties"]["businessGroup"]["x-smartcmp"]["builtinCatalogField"]
        == "businessGroup.code"
    )
    assert (
        meta["schema"]["properties"]["projects"]["x-smartcmp"]["builtinCatalogField"]
        == "application.name"
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


def test_design_form_regenerate_mode_normalizes_replacement_schema_with_source_url(monkeypatch):
    schema_json = json.dumps(
        {
            "properties": {
                "hostname": {
                    "title": "Hostname",
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
            "regenerate",
            "--schema-json",
            schema_json,
            "--form-url",
            "https://cmp.example.com/#/main/service-model/forms/edit/"
            "42607f38-2c63-4649-a8de-efa031db4544",
            "--change-summary",
            "Regenerated the form from user requirements.",
        ],
        monkeypatch,
    )
    meta = extract_meta(stderr, "FORM_DESIGN_META")

    assert exit_code == 0
    assert "Regenerated the form from user requirements." in stdout
    assert meta["mode"] == "regenerate"
    assert meta["source"]["formId"] == "42607f38-2c63-4649-a8de-efa031db4544"
    assert meta["schema"]["properties"]["hostname"]["id"] == "hostname"


def test_design_form_regenerate_mode_requires_complete_schema_json(monkeypatch):
    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "regenerate",
            "--form-url",
            "https://cmp.example.com/#/main/service-model/forms/edit/"
            "42607f38-2c63-4649-a8de-efa031db4544",
        ],
        monkeypatch,
    )

    assert exit_code == 1
    assert "schema_json is required for regenerate mode" in stdout
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


def test_design_form_modify_mode_applies_catalog_context_sync_from_template(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, verify=None, timeout=None):
        captured["url"] = url
        return FakeResponse(
            {
                "name": "test-linux",
                "content": {
                    "schema": {
                        "type": "object",
                        "title": "test-linux",
                        "properties": {
                            "expansion": {
                                "type": "string",
                                "title": "expansion",
                                "widget": {"id": "string"},
                            },
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
            "--catalog-context-sync-json",
            json.dumps(
                {"fieldKey": "expansion", "outputs": ["projects", "owner"]},
                ensure_ascii=False,
            ),
        ],
        monkeypatch,
        fake_get=fake_get,
    )
    meta = extract_meta(stderr, "FORM_DESIGN_META")
    expression = meta["schema"]["properties"]["expansion"]["config"]["value"]["expression"]

    assert exit_code == 0
    assert captured["url"].endswith("/forms/42607f38-2c63-4649-a8de-efa031db4544")
    assert "Applied catalog context sync field 'expansion' with outputs: 应用系统, 所有者." in stdout
    assert "literal ellipsis placeholder" not in stdout
    assert "CATALOG_CONTEXT_SYNC_TEMPLATE_V1" in expression
    assert "KEY='expansion'" in expression
    assert "output:'应用系统'" in expression
    assert "output:'所有者'" in expression
    assert "catalogServiceRequest.exts.project.name" in expression
    assert "catalogServiceRequest.exts.owner.name" in expression
    assert "projectId" not in expression
    assert "keys:['projects']" not in expression
    assert "JSON.stringify(out)" in expression
    assert "write(keep||JSON.stringify(out))" not in expression


def test_catalog_context_sync_expression_does_not_publish_empty_json_when_unresolved(monkeypatch):
    exit_code, _stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "new",
            "--catalog-context-sync-json",
            json.dumps(
                {"fieldKey": "expansion", "outputs": ["projects", "owner"]},
                ensure_ascii=False,
            ),
        ],
        monkeypatch,
    )
    meta = extract_meta(stderr, "FORM_DESIGN_META")
    expression = meta["schema"]["properties"]["expansion"]["config"]["value"]["expression"]

    assert exit_code == 0
    result = run_catalog_expression(expression, {})

    assert result["result"] == ""
    assert result["modelExpansion"] is None
    assert '"value":""' not in json.dumps(result, ensure_ascii=False)


def test_catalog_context_sync_expression_publishes_complete_display_values(monkeypatch):
    exit_code, _stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "new",
            "--catalog-context-sync-json",
            json.dumps(
                {"fieldKey": "expansion", "outputs": ["projects", "owner"]},
                ensure_ascii=False,
            ),
        ],
        monkeypatch,
    )
    meta = extract_meta(stderr, "FORM_DESIGN_META")
    expression = meta["schema"]["properties"]["expansion"]["config"]["value"]["expression"]

    assert exit_code == 0
    result = run_catalog_expression(
        expression,
        {
            "catalogServiceRequest": {
                "exts": {
                    "project": {"name": "研发门户"},
                    "owner": {"name": "平台管理员"},
                }
            }
        },
    )

    assert json.loads(result["result"]) == {
        "应用系统": {"value": "研发门户"},
        "所有者": {"value": "平台管理员"},
    }
    assert result["modelExpansion"] == result["result"]


def test_catalog_context_sync_supports_arbitrary_target_field_and_label_outputs(monkeypatch):
    exit_code, _stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "new",
            "--catalog-context-sync-json",
            json.dumps(
                {"fieldKey": "contextPayload", "outputs": ["业务组", "名称"]},
                ensure_ascii=False,
            ),
        ],
        monkeypatch,
    )
    meta = extract_meta(stderr, "FORM_DESIGN_META")
    field = meta["schema"]["properties"]["contextPayload"]
    expression = field["config"]["value"]["expression"]

    assert exit_code == 0
    assert "expansion" not in meta["schema"]["properties"]
    assert "KEY='contextPayload'" in expression
    assert "output:'业务组'" in expression
    assert "output:'名称'" in expression
    assert "catalogServiceRequest.exts.businessGroup.name" in expression
    assert "keys:['name']" in expression

    result = run_catalog_expression(
        expression,
        {
            "catalogServiceRequest": {
                "exts": {"businessGroup": {"name": "默认业务组"}},
            },
            "name": "test-linux",
        },
    )

    assert json.loads(result["result"]) == {
        "业务组": {"value": "默认业务组"},
        "名称": {"value": "test-linux"},
    }
    assert result["modelExpansion"] is None
    assert result["model"]["contextPayload"] == result["result"]


def test_catalog_context_sync_rejects_application_alias(monkeypatch):
    exit_code, stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "new",
            "--catalog-context-sync-json",
            json.dumps(
                {"fieldKey": "contextPayload", "outputs": ["application"]},
                ensure_ascii=False,
            ),
        ],
        monkeypatch,
    )

    assert exit_code == 1
    assert "Unsupported catalog_context_sync_json output 'application'" in stdout
    assert "FORM_DESIGN_META" not in stderr


def test_catalog_context_sync_clears_stale_invalid_value_when_unresolved(monkeypatch):
    exit_code, _stdout, stderr = run_main(
        SCRIPTS_DIR / "design_form.py",
        [
            "--mode",
            "new",
            "--catalog-context-sync-json",
            json.dumps(
                {"fieldKey": "expansion", "outputs": ["业务组"]},
                ensure_ascii=False,
            ),
        ],
        monkeypatch,
    )
    meta = extract_meta(stderr, "FORM_DESIGN_META")
    expression = meta["schema"]["properties"]["expansion"]["config"]["value"]["expression"]
    stale_value = json.dumps({"应用系统": {"value": ""}}, ensure_ascii=False)

    assert exit_code == 0
    result = run_catalog_expression(
        expression,
        {},
        initial_model={"expansion": stale_value},
        initial_state={
            "key": "expansion",
            "state": {"lastGood": stale_value, "values": {"projectName": ""}},
        },
    )

    assert result["result"] == ""
    assert result["model"]["expansion"] == ""


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
