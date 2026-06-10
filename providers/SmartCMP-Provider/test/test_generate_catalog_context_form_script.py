# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = PROVIDER_ROOT / "skills" / "form-designer-agent"
SCRIPT_PATH = SKILL_ROOT / "scripts" / "generate_catalog_context_form.py"
VALIDATE_SCRIPT = SKILL_ROOT / "scripts" / "validate_request_form_json.py"


def _load_validator():
    module_name = "test_generate_catalog_context_form_validate_module"
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


def test_generate_catalog_context_form_outputs_eip_mixture_json() -> None:
    payload = run_generator(
        "mixture",
        "mixture",
        "计费类型=InternetChargeType,带宽=Bandwidth",
        "test-eip",
    )
    prop = payload["properties"]["mixture"]
    expression = prop["config"]["value"]["expression"]

    assert payload["type"] == "object"
    assert payload["fieldsets"][0]["title"] == "test-eip"
    assert payload["fieldsets"][0]["fields"] == ["mixture", "schemaFormValid"]
    assert prop["title"] == " "
    assert prop["hideTitle"] is True
    assert prop["default"] == "AUTO_SYNC_PENDING"
    assert "HIDE=true" in expression
    assert '"InternetChargeType","计费类型"' in expression
    assert '"Bandwidth","带宽"' in expression
    assert "sourceParams" in expression
    assert "resourceSpecs" in expression
    assert "Object.defineProperty" in expression
    assert "state.dispatched" in expression
    assert "\n" not in expression

    code = f"""
const fn = new Function('return (' + {json.dumps(expression)} + ')')();
let tick = null;
global.window = global;
global.Event = function(){{}};
global.setInterval = function(cb){{ tick = cb; return 1; }};
global.clearInterval = function(){{}};
let inputValue = '';
let mixtureInput = {{ get value(){{ return inputValue; }}, set value(v){{ inputValue = v; }}, getAttribute: function(name){{ return name === 'name' ? 'mixture' : ''; }}, closest: function(){{ return null; }}, dispatchEvent: function(){{}} }};
global.document = {{
  querySelectorAll: function(sel) {{ return sel === 'input,textarea,select' ? [mixtureInput] : []; }},
  querySelector: function() {{ return null; }}
}};
let model = {{}};
let first = fn(model, {{ params: {{ InternetChargeType: '按流量', Bandwidth: 5 }} }}, {{}});
tick();
model.mixture = '';
let second = fn(model, {{ params: {{}} }}, {{}});
console.log(JSON.stringify({{ first, second, modelValue: model.mixture, inputValue }}));
"""
    result = subprocess.run(
        ["node", "-e", code],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert json.loads(output["first"]) == {"计费类型": "按流量", "带宽": "5"}
    assert json.loads(output["second"]) == {"计费类型": "按流量", "带宽": "5"}
    assert output["modelValue"] == output["first"]
    assert output["inputValue"] == output["first"]

    validator = _load_validator()
    result = validator.validate_form_json(json.dumps(payload, ensure_ascii=False))
    assert result == {"valid": True, "issues": []}


def test_generate_catalog_context_form_can_show_composed_field_when_explicit() -> None:
    payload = run_generator(
        "mixture",
        "mixture",
        "计费类型=InternetChargeType,带宽=Bandwidth",
        "test-eip",
        "--show-submit-field",
    )
    prop = payload["properties"]["mixture"]
    expression = prop["config"]["value"]["expression"]

    assert prop["title"] == "mixture"
    assert "hideTitle" not in prop
    assert "HIDE=false" in expression


def test_generate_catalog_context_form_can_allow_explicit_backend_key_labels() -> None:
    payload = run_generator(
        "mixture",
        "mixture",
        "InternetChargeType=InternetChargeType,Bandwidth=Bandwidth",
        "test-eip",
        "--allow-backend-labels",
    )
    expression = payload["properties"]["mixture"]["config"]["value"]["expression"]

    assert "ALLOW_BACKEND_LABELS=true" in expression
    validator = _load_validator()
    assert validator.validate_form_json(json.dumps(payload, ensure_ascii=False)) == {"valid": True, "issues": []}


def test_generate_catalog_context_form_keeps_custom_field_visible_next_to_hidden_composed() -> None:
    payload = run_generator(
        "mixture",
        "mixture",
        "计费类型=InternetChargeType,带宽=Bandwidth",
        "test-eip",
    )
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
    payload["fieldsets"][0]["fields"] = ["mixture", "priority", "schemaFormValid"]

    assert payload["properties"]["mixture"]["title"] == " "
    assert payload["properties"]["mixture"]["hideTitle"] is True
    assert payload["properties"]["priority"]["title"] == "优先级"
    assert "hideTitle" not in payload["properties"]["priority"]

    validator = _load_validator()
    result = validator.validate_form_json(json.dumps(payload, ensure_ascii=False))
    assert result == {"valid": True, "issues": []}


def test_generate_catalog_context_form_cleans_select_placeholder_dom_text() -> None:
    payload = run_generator(
        "mixture",
        "mixture",
        "计费类型=InternetChargeType,带宽=Bandwidth",
        "test-eip",
    )
    expression = payload["properties"]["mixture"]["config"]["value"]["expression"]
    assert "请选择" not in expression
    assert "please select" not in expression.lower()

    code = f"""
const fn = new Function('return (' + {json.dumps(expression)} + ')')();
global.window = global;
global.Event = function(){{}};
global.setInterval = function(){{ return 1; }};
global.clearInterval = function(){{}};
let inputValue = '';
let mixtureInput = {{ get value(){{ return inputValue; }}, set value(v){{ inputValue = v; }}, getAttribute: function(name){{ return name === 'name' ? 'mixture' : ''; }}, closest: function(){{ return null; }}, dispatchEvent: function(){{}} }};
let billingValue = {{ textContent: '请选择\\n                \\n                                                        \\n                                                        按使用流量计费' }};
let billingBox = {{ querySelector: function(sel){{ return sel.indexOf('ant-select') >= 0 ? billingValue : null; }} }};
let billingLabel = {{ textContent: '计费类型', innerText: '计费类型', closest: function(){{ return billingBox; }} }};
global.document = {{
  querySelectorAll: function(sel) {{
    if (sel === 'input,textarea,select') return [mixtureInput];
    if (sel.indexOf('label') >= 0) return [billingLabel];
    return [];
  }},
  querySelector: function() {{ return null; }}
}};
let model = {{}};
let result = fn(model, {{ params: {{ Bandwidth: 1 }} }}, {{}});
console.log(JSON.stringify({{ result, modelValue: model.mixture }}));
"""
    result = subprocess.run(
        ["node", "-e", code],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert json.loads(output["result"]) == {
        "计费类型": "按使用流量计费",
        "带宽": "1",
    }
    assert output["modelValue"] == output["result"]


def test_generate_catalog_context_form_supports_mixed_request_and_catalog_fields() -> None:
    payload = run_generator(
        "expansion",
        "expansion",
        "业务组=@request:department,所有者=@request:owner,资源组=resource_group_id",
        "test-oss",
    )
    expression = payload["properties"]["expansion"]["config"]["value"]["expression"]

    assert '"@request:department","业务组"' in expression
    assert '"@request:owner","所有者"' in expression
    assert '"resource_group_id","资源组"' in expression

    code = f"""
const fn = new Function('return (' + {json.dumps(expression)} + ')')();
global.window = global;
global.Event = function(){{}};
global.setInterval = function(){{ return 1; }};
global.clearInterval = function(){{}};
let inputValue = '';
let targetInput = {{ get value(){{ return inputValue; }}, set value(v){{ inputValue = v; }}, getAttribute: function(name){{ return name === 'name' ? 'expansion' : ''; }}, closest: function(){{ return null; }}, dispatchEvent: function(){{}} }};
global.document = {{
  querySelectorAll: function(sel) {{ return sel === 'input,textarea,select' ? [targetInput] : []; }},
  querySelector: function() {{ return null; }}
}};
let model = {{}};
let result = fn(model, {{
  businessGroupName: '研发部',
  ownerName: '平台管理员',
  resourceBundleParams: {{ resource_group_id: 'rg-default' }}
}}, {{}});
console.log(JSON.stringify({{ result, modelValue: model.expansion, inputValue }}));
"""
    result = subprocess.run(
        ["node", "-e", code],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert json.loads(output["result"]) == {
        "业务组": "研发部",
        "所有者": "平台管理员",
        "资源组": "rg-default",
    }
    assert output["modelValue"] == output["result"]
    assert output["inputValue"] == output["result"]

    validator = _load_validator()
    result = validator.validate_form_json(json.dumps(payload, ensure_ascii=False))
    assert result == {"valid": True, "issues": []}


def test_generate_catalog_context_form_supports_hidden_submit_field() -> None:
    payload = run_generator(
        "hidden_attr",
        "hidden_attr",
        "App=applicationSystem,Owner=ownerName",
        "test-ip",
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
let inputValue = '';
let wrapper = {{ style: {{}}, attrs: {{}}, setAttribute: function(k,v){{ this.attrs[k] = v; }} }};
let targetInput = {{ get value(){{ return inputValue; }}, set value(v){{ inputValue = v; }}, attrs: {{}}, setAttribute: function(k,v){{ this.attrs[k] = v; }}, getAttribute: function(name){{ return name === 'name' ? 'hidden_attr' : ''; }}, closest: function(sel){{ return sel === '.form-group' ? wrapper : null; }}, dispatchEvent: function(){{}} }};
global.document = {{
  querySelectorAll: function(sel) {{ return sel === 'input,textarea,select' ? [targetInput] : []; }},
  querySelector: function() {{ return null; }}
}};
let model = {{}};
fn(model, {{ params: {{ applicationSystem: 'IPAM', ownerName: 'admin' }} }}, {{}});
console.log(JSON.stringify({{ modelValue: model.hidden_attr, inputValue, wrapperStyle: wrapper.style, ariaHidden: wrapper.attrs['aria-hidden'], tabindex: targetInput.attrs.tabindex }}));
"""
    result = subprocess.run(
        ["node", "-e", code],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["modelValue"]
    assert output["modelValue"] == output["inputValue"]
    assert json.loads(output["modelValue"]) == {"App": "IPAM", "Owner": "admin"}
    assert output["wrapperStyle"]["left"] == "-10000px"
    assert output["wrapperStyle"]["opacity"] == "0"
    assert output["ariaHidden"] == "true"
    assert output["tabindex"] == "-1"

    validator = _load_validator()
    result = validator.validate_form_json(json.dumps(payload, ensure_ascii=False))
    assert result == {"valid": True, "issues": []}


def test_generate_catalog_context_form_treats_positional_bool_as_hide_flag_when_fieldset_omitted() -> None:
    payload = run_generator(
        "expansion",
        "expansion",
        "业务组=@request:department,所有者=@request:owner,计算规格=flavorId",
        "true",
    )
    prop = payload["properties"]["expansion"]
    expression = prop["config"]["value"]["expression"]

    assert payload["fieldsets"][0]["title"] == "表单字段"
    assert payload["fieldsets"][0]["name"] == "表单字段"
    assert prop["title"] == " "
    assert prop["hideTitle"] is True
    assert "HIDE=true" in expression
    assert "HIDE=false" not in expression


def test_generate_catalog_context_form_reads_catalog_field_from_parent_angular_scope() -> None:
    payload = run_generator(
        "expansion",
        "expansion",
        "业务组=@request:department,所有者=@request:owner,计算规格=flavorId",
        "test-linux",
        "--hide-submit-field",
    )
    expression = payload["properties"]["expansion"]["config"]["value"]["expression"]

    code = f"""
const fn = new Function('return (' + {json.dumps(expression)} + ')')();
global.window = global;
global.Event = function(){{}};
global.setInterval = function(){{ return 1; }};
global.clearInterval = function(){{}};
let inputValue = '';
let catalogEl = {{ parentElement: null }};
let targetInput = {{
  get value(){{ return inputValue; }},
  set value(v){{ inputValue = v; }},
  getAttribute: function(name){{ return name === 'name' ? 'expansion' : ''; }},
  setAttribute: function(){{}},
  closest: function(sel){{ return sel === 'catalog-form' ? catalogEl : null; }},
  dispatchEvent: function(){{}}
}};
let parentScope = {{
  vm: {{
    resourceSpecs: [
      {{ node: 'Compute', flavorId: {{ label: '2C4G', value: 'flavor-small' }} }}
    ]
  }}
}};
let childScope = {{ $parent: parentScope }};
global.angular = {{
  element: function(el) {{
    return {{
      controller: function(){{ return null; }},
      isolateScope: function(){{ return null; }},
      scope: function(){{ return el === catalogEl ? childScope : null; }}
    }};
  }}
}};
global.document = {{
  querySelectorAll: function(sel) {{
    if (sel === 'input,textarea,select') return [targetInput];
    if (sel === 'catalog-form') return [catalogEl];
    return [];
  }},
  querySelector: function() {{ return null; }}
}};
let model = {{}};
let result = fn(model, {{
  businessGroupName: '研发部',
  ownerName: '平台管理员'
}}, {{}});
console.log(JSON.stringify({{ result, modelValue: model.expansion, inputValue }}));
"""
    result = subprocess.run(
        ["node", "-e", code],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert json.loads(output["result"]) == {
        "业务组": "研发部",
        "所有者": "平台管理员",
        "计算规格": "2C4G",
    }
    assert output["modelValue"] == output["result"]
    assert output["inputValue"] == output["result"]


def test_generate_catalog_context_form_prefers_scanned_key_over_ambiguous_label_dom() -> None:
    payload = run_generator(
        "infoblox_ip_attr",
        "infoblox_ip_attr",
        "应用系统=applicationSystem,所有者=ownerName",
        "test-ip",
    )
    expression = payload["properties"]["infoblox_ip_attr"]["config"]["value"]["expression"]

    code = f"""
const fn = new Function('return (' + {json.dumps(expression)} + ')')();
global.window = global;
global.Event = function(){{}};
global.setInterval = function(){{ return 1; }};
global.clearInterval = function(){{}};
let inputValue = '';
let targetInput = {{ get value(){{ return inputValue; }}, set value(v){{ inputValue = v; }}, getAttribute: function(name){{ return name === 'name' ? 'infoblox_ip_attr' : ''; }}, closest: function(){{ return null; }}, dispatchEvent: function(){{}} }};
let badLabel = {{ textContent: '应用系统', innerText: '应用系统', closest: function(){{ return {{ querySelector: function(){{ return {{ value: '我的业务组' }}; }} }}; }} }};
global.document = {{
  querySelectorAll: function(sel) {{
    if (sel === 'input,textarea,select') return [targetInput];
    if (sel.indexOf('label') >= 0) return [badLabel];
    return [];
  }},
  querySelector: function() {{ return null; }}
}};
let model = {{}};
let result = fn(model, {{ params: {{ applicationSystem: 'IPAM系统', ownerName: '平台管理员' }} }}, {{}});
console.log(JSON.stringify({{ result, modelValue: model.infoblox_ip_attr }}));
"""
    result = subprocess.run(
        ["node", "-e", code],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert json.loads(output["result"]) == {
        "应用系统": "IPAM系统",
        "所有者": "平台管理员",
    }
    assert output["modelValue"] == output["result"]
