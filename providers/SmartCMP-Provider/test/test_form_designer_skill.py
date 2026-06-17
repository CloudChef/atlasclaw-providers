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

def test_form_designer_skill_layout_and_metadata():
    entry_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    catalog_context_text = (
        SKILL_ROOT / "references" / "CATALOG_CONTEXT_SYNC.md"
    ).read_text(encoding="utf-8")
    skill_text = entry_text + "\n" + catalog_context_text

    assert (SKILL_ROOT / "references" / "WORKFLOW.md").is_file()
    assert (SKILL_ROOT / "references" / "CATALOG_CONTEXT_SYNC.md").is_file()
    assert (SKILL_ROOT / "references" / "catalog-context-expression.js").is_file()
    assert (SCRIPTS_DIR / "read_form.py").is_file()
    assert (SCRIPTS_DIR / "design_form.py").is_file()
    assert (SCRIPTS_DIR / "_form_fetch.py").is_file()
    assert (SCRIPTS_DIR / "_schema_normalize.py").is_file()

    assert 'name: "form-designer"' in entry_text
    assert "smartcmp_read_form_schema" in entry_text
    assert "smartcmp_design_form_schema" in entry_text
    assert "form-designer" in entry_text
    assert "workflow_role" not in entry_text
    assert "request_parent" not in entry_text
    assert "smartcmp_submit_request" not in skill_text
    assert "submit.py" not in skill_text
    assert "does not save" in entry_text
    assert len(entry_text.splitlines()) <= 300
    assert "references/CATALOG_CONTEXT_SYNC.md" in entry_text
    assert "read `references/CATALOG_CONTEXT_SYNC.md` before generating" in entry_text
    assert "## Schema Rules" in entry_text
    assert "Root schema should be `type: object` with a `properties` object" in entry_text
    assert "Top-level fields should include stable `id`, numeric `index`, `type`" in entry_text
    assert "Use warnings for ambiguous or unsupported structures" in entry_text
    assert "Service catalog context display values" in skill_text
    assert "`businessGroup`" in skill_text
    assert "`BusinessGroup`" in skill_text
    assert "`businessGroupName`" in skill_text
    assert "`catalogServiceRequest.exts.businessGroup.name`" in skill_text
    assert "`exts.businessGroup.name`" not in skill_text
    assert "`businessGroupId`" in skill_text
    assert "`projects`" in skill_text
    assert "`owners`" in skill_text
    assert "`Owners`" in skill_text
    assert "`ownerName`" in skill_text
    assert "`catalogServiceRequest.exts.owner.name`" in skill_text
    assert "`exts.owner.name`" not in skill_text
    assert "`name`" in skill_text
    assert "`exts.field[].id`" in skill_text
    assert "`exts.field[].name`" in skill_text
    assert "prefer human-readable display names" in skill_text
    assert "keep that ID as a fallback" not in skill_text
    assert "For the Linux VM catalog" in skill_text
    assert "`owners/Owners`, and `name/Name`" in skill_text
    assert "fix the business group key to" in skill_text
    assert "and the owner key to" in skill_text
    assert "Fix the application-system key to" in skill_text
    assert "Fix the name key to `name`" in skill_text
    assert "add secondary scope keys unless" in skill_text
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
    assert "Keep `test-ip-form.json`'s DOM `selected` helper behavior" in skill_text
    assert "read the selected option text before using `el.value`" in skill_text
    assert "Use the `test-ip-form.json` expression skeleton as the source of truth" in skill_text
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
    assert "`FIELD_SPECS=[{state:'businessGroupName',output:'业务组',keys:['catalogServiceRequest.exts.businessGroup.name'],labels:['业务组','BusinessGroup']},{state:'ownerName',output:'所有者',keys:['catalogServiceRequest.exts.owner.name'],labels:['所有者','Owner','Owners']},{state:'projectName',output:'应用系统',keys:['catalogServiceRequest.exts.project.name'],labels:['应用系统','Projects']},{state:'requestName',output:'名称',keys:['name'],labels:['名称','Name']}]`" in skill_text
    assert "`所有者`, `应用系统`, or `名称`" in skill_text
    assert "`业务组`, `所有者`, `应用系统`, or `名称`" in skill_text
    assert "or `项目`" not in skill_text
    assert "`keys:['businessGroup']`" in skill_text
    assert "`keys:['owners']`" in skill_text
    assert "`keys:['projects']`" in skill_text
    assert "`keys:['Name']`" in skill_text
    assert "wrong for" in skill_text
    assert "Do not copy `test-ip-form.json` verbatim" in skill_text
    assert "`KEY='infoblox_ip_attr'`" in skill_text
    assert "`APP_OUTPUT_KEY='应用服务器'`" in skill_text
    assert "`OWNER_OUTPUT_KEY='责任人'`" in skill_text
    assert "The only required behavior change from `test-ip-form.json` is the final submit format" in skill_text
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
    assert "Do not try to read `test-ip-form.json` from disk" in skill_text
    assert "contains the four universal service-catalog header fields" in skill_text
    assert "The `字段A` and `字段B` entries" not in skill_text
    assert "For an EIP `test-eip` request with field `mixture` combining `应用系统`, `名称`, and `所有者`" in skill_text
    assert "`KEY='mixture'`" in skill_text
    assert "`FIELD_SPECS=[{state:'projectName',output:'应用系统',keys:['catalogServiceRequest.exts.project.name'],labels:['应用系统','Projects']},{state:'requestName',output:'名称',keys:['name'],labels:['名称','Name']},{state:'ownerName',output:'所有者',keys:['catalogServiceRequest.exts.owner.name'],labels:['所有者','Owner','Owners']}]`" in skill_text
    assert "If the user asks for a smaller subset" in skill_text
    assert "The fixed-label subset can contain one, two, three, or four `FIELD_SPECS` entries" in skill_text
    assert "the maintained template supports the four universal" in skill_text
    assert "initially contains only generic placeholder fields" not in skill_text
    assert "`FIELD_SPECS=[{state:'fieldA'" not in skill_text

def test_catalog_context_expression_template_uses_generic_field_specs():
    template = (SKILL_ROOT / "references" / "catalog-context-expression.js").read_text(encoding="utf-8")

    assert not template.startswith("\ufeff")
    assert "\n" not in template
    assert '"' not in template
    assert "\\" not in template
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
    assert "for(var i=0;i<nodes.length;i++){try{" in template
    assert "businessGroupName" in template
    assert "catalogServiceRequest.exts.businessGroup.name" in template
    assert "catalogServiceRequest.exts.project.name" in template
    assert "catalogServiceRequest.exts.owner.name" in template
    assert "业务组" in template
    assert "应用系统" in template
    assert "所有者" in template
    assert "名称" in template
    assert "fieldAName" not in template
    assert "字段A" not in template
    assert "getElementsByName" in template
    assert "/catalog-ui/request/" in template
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
