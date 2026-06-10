# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = PROVIDER_ROOT / "skills" / "form-designer-agent"
SCRIPT_PATH = SKILL_ROOT / "scripts" / "generate_request_context_form.py"
VALIDATE_SCRIPT = SKILL_ROOT / "scripts" / "validate_request_form_json.py"


def _load_validator():
    module_name = "test_generate_request_context_form_validate_module"
    spec = importlib.util.spec_from_file_location(module_name, VALIDATE_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


def run_generator(*args: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def run_node(code: str) -> dict:
    result = subprocess.run(
        ["node", "-e", code],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_generate_request_context_form_outputs_canonical_name_owner_json() -> None:
    payload = run_generator("backend_test", "后端测试", "名称,所有者", "--fieldset-title", "test4")
    expression = payload["properties"]["backend_test"]["config"]["value"]["expression"]

    assert payload["type"] == "object"
    assert payload["fieldsets"][0]["fields"] == ["backend_test", "schemaFormValid"]
    assert payload["properties"]["backend_test"]["config"]["value"]["source"] == "mock"
    assert payload["properties"]["backend_test"]["config"]["value"]["method"] == "mock"
    assert "\n" not in expression
    assert "vm.deploymentObj.name" in expression
    assert "catalog-form" in expression
    assert "/platform-api/users/simple" in expression
    assert "state.timer=setInterval" in expression
    assert "Object.defineProperty" in expression
    assert "state.dispatched" in expression
    assert "return write(resolve())" in expression
    assert "JSON.stringify" in expression
    assert "sourceParams.name" not in expression
    assert "window.vm" not in expression
    assert "window.sourceConfigParamter" not in expression
    assert "$(" not in expression
    assert "var interval = null" not in expression
    assert "return 'AUTO_SYNC_PENDING'" not in expression

    validator = _load_validator()
    result = validator.validate_form_json(json.dumps(payload, ensure_ascii=False))
    assert result == {"valid": True, "issues": []}


def test_generate_request_context_form_hides_composed_field_by_default() -> None:
    payload = run_generator("backend_test", "后端测试", "名称,所有者", "--fieldset-title", "test4")
    prop = payload["properties"]["backend_test"]
    expression = prop["config"]["value"]["expression"]

    assert prop["title"] == " "
    assert prop["i18nTitle"] == {"zh": "", "en": ""}
    assert prop["hideTitle"] is True
    assert prop["hideTitleText"] is True
    assert prop["notitle"] is True
    assert "HIDE=true" in expression
    assert "HIDE=false" not in expression


def test_generate_request_context_form_can_show_composed_field_when_explicit() -> None:
    payload = run_generator(
        "backend_test",
        "后端测试",
        "名称,所有者",
        "--fieldset-title",
        "test4",
        "--show-submit-field",
    )
    prop = payload["properties"]["backend_test"]
    expression = prop["config"]["value"]["expression"]

    assert prop["title"] == "后端测试"
    assert "hideTitle" not in prop
    assert "HIDE=false" in expression


def test_generate_request_context_form_keeps_custom_field_visible_next_to_hidden_composed() -> None:
    payload = run_generator("backend_test", "后端测试", "名称,所有者", "--fieldset-title", "test4")
    payload["properties"]["priority"] = {
        "id": "priority",
        "type": "string",
        "title": "优先级",
        "inputClass": "form-control",
        "index": 1,
        "widget": {"id": "string"},
        "config": {
            "visibility": {"allowInRequest": True},
            "modification": {"allowInRequest": True},
        },
    }
    payload["fieldsets"][0]["fields"] = ["backend_test", "priority", "schemaFormValid"]

    assert payload["properties"]["backend_test"]["title"] == " "
    assert payload["properties"]["backend_test"]["hideTitle"] is True
    assert payload["properties"]["priority"]["title"] == "优先级"
    assert "hideTitle" not in payload["properties"]["priority"]

    validator = _load_validator()
    result = validator.validate_form_json(json.dumps(payload, ensure_ascii=False))
    assert result == {"valid": True, "issues": []}


def test_generate_request_context_form_keeps_last_non_empty_context_values() -> None:
    payload = run_generator("backend_test", "后端测试", "名称,所有者", "--fieldset-title", "test4")
    expression = payload["properties"]["backend_test"]["config"]["value"]["expression"]
    code = f"""
const fn = new Function('return (' + {json.dumps(expression)} + ')')();
let currentName = '服务A';
global.window = global;
global.Event = function(){{}};
global.setInterval = function(){{ return 1; }};
global.clearInterval = function(){{}};
global.XMLHttpRequest = function(){{}};
global.document = {{
  querySelectorAll: function(){{ return []; }},
  querySelector: function(sel) {{
    if (sel.indexOf('deploymentObj.name') >= 0 && currentName) {{
      return {{ value: currentName, dispatchEvent: function(){{}} }};
    }}
    return null;
  }}
}};
let model = {{}};
let first = fn(model, {{ ownerName: '平台管理员' }}, {{}});
currentName = '';
let second = fn(model, {{}}, {{}});
console.log(JSON.stringify({{ first, second, modelValue: model.backend_test }}));
"""
    output = run_node(code)
    assert json.loads(output["first"]) == {"名称": "服务A", "所有者": "平台管理员"}
    assert json.loads(output["second"]) == {"名称": "服务A", "所有者": "平台管理员"}
    assert json.loads(output["modelValue"]) == {"名称": "服务A", "所有者": "平台管理员"}


def test_generate_request_context_form_does_not_overwrite_existing_value_when_context_is_empty() -> None:
    payload = run_generator("backend_test", "后端测试", "名称,所有者", "--fieldset-title", "test4")
    expression = payload["properties"]["backend_test"]["config"]["value"]["expression"]
    code = f"""
const fn = new Function('return (' + {json.dumps(expression)} + ')')();
global.window = global;
global.Event = function(){{}};
global.setInterval = function(cb){{ cb(); return 1; }};
global.clearInterval = function(){{}};
global.XMLHttpRequest = function(){{}};
let inputValue = JSON.stringify({{'名称':'服务A','所有者':'平台管理员'}});
let writeCount = 0;
global.document = {{
  querySelectorAll: function(sel) {{
    if (sel === 'input,textarea') {{
      return [{{ value: inputValue, getAttribute: function(name){{ return name === 'name' ? 'backend_test' : ''; }}, closest: function(){{ return null; }}, dispatchEvent: function(){{ writeCount++; }} }}];
    }}
    return [];
  }},
  querySelector: function() {{ return null; }}
}};
let model = {{ backend_test: inputValue }};
let result = fn(model, {{}}, {{}});
console.log(JSON.stringify({{ result, modelValue: model.backend_test, inputValue, writeCount }}));
"""
    output = run_node(code)
    assert json.loads(output["result"]) == {"名称": "服务A", "所有者": "平台管理员"}
    assert json.loads(output["modelValue"]) == {"名称": "服务A", "所有者": "平台管理员"}
    assert json.loads(output["inputValue"]) == {"名称": "服务A", "所有者": "平台管理员"}
    assert output["writeCount"] == 0


def test_generate_request_context_form_protects_model_after_external_empty_write() -> None:
    payload = run_generator("backend_test", "后端测试", "名称,所有者", "--fieldset-title", "test4")
    expression = payload["properties"]["backend_test"]["config"]["value"]["expression"]
    code = f"""
const fn = new Function('return (' + {json.dumps(expression)} + ')')();
let tick = null;
global.window = global;
global.Event = function(){{}};
global.setInterval = function(cb){{ tick = cb; return 1; }};
global.clearInterval = function(){{}};
global.XMLHttpRequest = function(){{}};
let inputValue = '';
let currentName = '服务A';
let writes = 0;
let backendInput = {{ get value(){{ return inputValue; }}, set value(v){{ inputValue = v; }}, getAttribute: function(name){{ return name === 'name' ? 'backend_test' : ''; }}, closest: function(){{ return null; }}, dispatchEvent: function(){{ writes++; }} }};
global.document = {{
  querySelectorAll: function(sel) {{
    if (sel === 'input,textarea') {{
      return [backendInput];
    }}
    return [];
  }},
  querySelector: function(sel) {{
    if (sel.indexOf('deploymentObj.name') >= 0 && currentName) {{
      return {{ value: currentName, dispatchEvent: function(){{}} }};
    }}
    return null;
  }}
}};
let model = {{}};
let first = fn(model, {{ ownerName: '平台管理员' }}, {{}});
tick();
model.backend_test = '';
inputValue = '';
currentName = '';
tick();
console.log(JSON.stringify({{ first, modelValue: model.backend_test, inputValue, writes }}));
"""
    output = run_node(code)
    assert json.loads(output["first"]) == {"名称": "服务A", "所有者": "平台管理员"}
    assert json.loads(output["modelValue"]) == {"名称": "服务A", "所有者": "平台管理员"}
    assert output["inputValue"] == ""
    assert output["writes"] == 2


def test_generate_request_context_form_dispatches_only_when_computed_value_changes() -> None:
    payload = run_generator("backend_test", "后端测试", "名称,所有者", "--fieldset-title", "test4")
    expression = payload["properties"]["backend_test"]["config"]["value"]["expression"]
    code = f"""
const fn = new Function('return (' + {json.dumps(expression)} + ')')();
let tick = null;
global.window = global;
global.Event = function(){{}};
global.setInterval = function(cb){{ tick = cb; return 1; }};
global.clearInterval = function(){{}};
global.XMLHttpRequest = function(){{}};
let inputValue = '';
let currentName = '服务A';
let writes = 0;
let backendInput = {{ get value(){{ return inputValue; }}, set value(v){{ inputValue = v; }}, getAttribute: function(name){{ return name === 'name' ? 'backend_test' : ''; }}, closest: function(){{ return null; }}, dispatchEvent: function(){{ writes++; }} }};
global.document = {{
  querySelectorAll: function(sel) {{ return sel === 'input,textarea' ? [backendInput] : []; }},
  querySelector: function(sel) {{ return sel.indexOf('deploymentObj.name') >= 0 && currentName ? {{ value: currentName, dispatchEvent: function(){{}} }} : null; }}
}};
let model = {{}};
fn(model, {{ ownerName: '平台管理员' }}, {{}});
tick();
currentName = '服务B';
tick();
console.log(JSON.stringify({{ modelValue: model.backend_test, inputValue, writes }}));
"""
    output = run_node(code)
    assert json.loads(output["modelValue"]) == {"名称": "服务B", "所有者": "平台管理员"}
    assert json.loads(output["inputValue"]) == {"名称": "服务B", "所有者": "平台管理员"}
    assert output["writes"] == 4


def test_generate_request_context_form_supports_department_owner_json() -> None:
    payload = run_generator("backend_test", "后端测试", "部门,所有者")
    expression = payload["properties"]["backend_test"]["config"]["value"]["expression"]

    assert "businessGroupId" in expression
    assert "/platform-api/business-groups/" in expression
    assert '"department","部门"' in expression
    assert '"owner","所有者"' in expression

    code = f"""
const fn = new Function('return (' + {json.dumps(expression)} + ')')();
global.window = global;
global.Event = function(){{}};
global.setInterval = function(){{ return 1; }};
global.clearInterval = function(){{}};
global.XMLHttpRequest = function(){{}};
global.document = {{
  querySelectorAll: function(){{ return []; }},
  querySelector: function(){{ return null; }}
}};
let model = {{}};
let value = fn(model, {{ businessGroupName: '开发部', ownerName: '平台管理员' }}, {{}});
console.log(JSON.stringify({{ value, modelValue: model.backend_test }}));
"""
    output = run_node(code)
    assert json.loads(output["value"]) == {"部门": "开发部", "所有者": "平台管理员"}
    assert json.loads(output["modelValue"]) == {"部门": "开发部", "所有者": "平台管理员"}

    validator = _load_validator()
    result = validator.validate_form_json(json.dumps(payload, ensure_ascii=False))
    assert result == {"valid": True, "issues": []}


def test_generate_request_context_form_rejects_noncommon_request_fields() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "request_summary",
            "申请摘要",
            "description,quantity,execution_time",
            "基本信息",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 1
    assert "Unsupported fixed request field: description" in result.stderr


def test_generate_request_context_form_rejects_application_system_context() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "catalog_attr",
            "catalog_attr",
            "application_system,owner",
            "test-catalog",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 1
    assert "Unsupported fixed request field: application_system" in result.stderr


def test_generate_request_context_form_accepts_business_group_name_alias() -> None:
    payload = run_generator("mixture", "mixture", "owner,businessGroupName", "test-vm")
    expression = payload["properties"]["mixture"]["config"]["value"]["expression"]

    assert '"owner","所有者"' in expression
    assert '"department","业务组"' in expression

    code = f"""
const fn = new Function('return (' + {json.dumps(expression)} + ')')();
global.window = global;
global.Event = function(){{}};
global.setInterval = function(){{ return 1; }};
global.clearInterval = function(){{}};
global.XMLHttpRequest = function(){{}};
global.document = {{
  querySelectorAll: function(){{ return []; }},
  querySelector: function(){{ return null; }}
}};
let model = {{}};
let value = fn(model, {{ ownerName: '平台管理员', businessGroupName: '研发部' }}, {{}});
console.log(JSON.stringify({{ value, modelValue: model.mixture }}));
"""
    output = run_node(code)
    assert json.loads(output["value"]) == {"所有者": "平台管理员", "业务组": "研发部"}
    assert json.loads(output["modelValue"]) == {"所有者": "平台管理员", "业务组": "研发部"}


def test_generate_request_context_form_supports_hidden_submit_field() -> None:
    payload = run_generator(
        "hidden_attr",
        "hidden_attr",
        "owner,businessGroupName",
        "test-vm",
        "--hide-submit-field",
    )
    prop = payload["properties"]["hidden_attr"]
    expression = prop["config"]["value"]["expression"]

    assert prop["title"] == " "
    assert prop["i18nTitle"] == {"zh": "", "en": ""}
    assert prop["hideTitle"] is True
    assert prop["hideTitleText"] is True
    assert prop["notitle"] is True
    assert "hidden" not in prop["inputClass"].split()
    assert "d-none" not in prop["inputClass"].split()
    assert "var hideUi=function" in expression

    code = f"""
const fn = new Function('return (' + {json.dumps(expression)} + ')')();
global.window = global;
global.Event = function(name){{ this.name = name; }};
global.setInterval = function(){{ return 1; }};
global.clearInterval = function(){{}};
global.XMLHttpRequest = function(){{}};
let inputValue = '';
let wrapper = {{ style: {{}}, attrs: {{}}, setAttribute: function(k,v){{ this.attrs[k] = v; }} }};
let targetInput = {{ get value(){{ return inputValue; }}, set value(v){{ inputValue = v; }}, attrs: {{}}, setAttribute: function(k,v){{ this.attrs[k] = v; }}, getAttribute: function(name){{ return name === 'name' ? 'hidden_attr' : ''; }}, closest: function(sel){{ return sel === '.form-group' ? wrapper : null; }}, dispatchEvent: function(){{}} }};
global.document = {{
  querySelectorAll: function(sel) {{ return sel === 'input,textarea' ? [targetInput] : []; }},
  querySelector: function() {{ return null; }}
}};
let model = {{}};
fn(model, {{ ownerName: 'admin', businessGroupName: 'dev' }}, {{}});
console.log(JSON.stringify({{ modelValue: model.hidden_attr, inputValue, wrapperStyle: wrapper.style, ariaHidden: wrapper.attrs['aria-hidden'], tabindex: targetInput.attrs.tabindex }}));
"""
    output = run_node(code)
    assert output["modelValue"]
    assert output["modelValue"] == output["inputValue"]
    assert json.loads(output["modelValue"]) == {"所有者": "admin", "业务组": "dev"}
    assert output["wrapperStyle"]["left"] == "-10000px"
    assert output["wrapperStyle"]["opacity"] == "0"
    assert output["ariaHidden"] == "true"
    assert output["tabindex"] == "-1"

    validator = _load_validator()
    result = validator.validate_form_json(json.dumps(payload, ensure_ascii=False))
    assert result == {"valid": True, "issues": []}


def test_generate_request_context_form_supports_source_fields_and_composed_mix_json() -> None:
    payload = run_generator("mix", "mix", "名称,业务组", "test4", "--include-source-fields")
    payload_from_positional_flag = run_generator("mix", "mix", "名称,业务组", "test4", "true")
    assert list(payload_from_positional_flag["properties"].keys()) == [
        "name",
        "business_group",
        "mix",
        "schemaFormValid",
    ]

    properties = payload["properties"]

    assert list(properties.keys()) == ["name", "business_group", "mix", "schemaFormValid"]
    assert properties["name"]["title"] == "名称"
    assert properties["business_group"]["title"] == "业务组"
    assert properties["mix"]["title"] == " "
    assert properties["mix"]["hideTitle"] is True
    assert payload["fieldsets"][0]["fields"] == [
        "name",
        "business_group",
        "mix",
        "schemaFormValid",
    ]

    name_expr = properties["name"]["config"]["value"]["expression"]
    bg_expr = properties["business_group"]["config"]["value"]["expression"]
    mix_expr = properties["mix"]["config"]["value"]["expression"]
    assert '"raw"' in name_expr
    assert '"raw"' in bg_expr
    assert '"template"' in mix_expr
    assert '"department","业务组"' in mix_expr
    assert "Object.defineProperty" in name_expr
    assert "Object.defineProperty" in bg_expr
    assert "Object.defineProperty" in mix_expr

    code = f"""
const nameFn = new Function('return (' + {json.dumps(name_expr)} + ')')();
const bgFn = new Function('return (' + {json.dumps(bg_expr)} + ')')();
const mixFn = new Function('return (' + {json.dumps(mix_expr)} + ')')();
global.window = global;
global.Event = function(){{}};
global.setInterval = function(){{ return 1; }};
global.clearInterval = function(){{}};
global.XMLHttpRequest = function(){{}};
let currentName = '服务A';
global.document = {{
  querySelectorAll: function(){{ return []; }},
  querySelector: function(sel) {{
    if (sel.indexOf('deploymentObj.name') >= 0 && currentName) {{
      return {{ value: currentName, dispatchEvent: function(){{}} }};
    }}
    return null;
  }}
}};
let model = {{}};
let sourceParams = {{ businessGroupName: '开发部' }};
let nameValue = nameFn(model, sourceParams, {{}});
let bgValue = bgFn(model, sourceParams, {{}});
let mixValue = mixFn(model, sourceParams, {{}});
console.log(JSON.stringify({{ nameValue, bgValue, mixValue, model }}));
"""
    output = run_node(code)
    assert output["nameValue"] == "服务A"
    assert output["bgValue"] == "开发部"
    assert json.loads(output["mixValue"]) == {"名称": "服务A", "业务组": "开发部"}
    assert output["model"]["name"] == "服务A"
    assert output["model"]["business_group"] == "开发部"
    assert json.loads(output["model"]["mix"]) == {"名称": "服务A", "业务组": "开发部"}

    validator = _load_validator()
    result = validator.validate_form_json(json.dumps(payload, ensure_ascii=False))
    assert result == {"valid": True, "issues": []}
