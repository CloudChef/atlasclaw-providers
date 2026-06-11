# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

import json
import subprocess
import sys
import unicodedata
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "form-designer-agent"
    / "scripts"
    / "generate_catalog_context_form.py"
)


def run_generator(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_generate_catalog_context_form_outputs_hidden_catalog_mixture_json() -> None:
    result = run_generator(
        "mixture",
        "mixture",
        "billing type=InternetChargeType,bandwidth=Bandwidth",
        "test-eip",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    prop = payload["properties"]["mixture"]
    expression = prop["config"]["value"]["expression"]

    assert payload["type"] == "object"
    assert payload["fieldsets"][0]["fields"] == ["mixture", "schemaFormValid"]
    assert prop["title"] == " "
    assert prop["hideTitle"] is True
    assert prop["default"] == "AUTO_SYNC_PENDING"
    assert '"InternetChargeType","billing type"' in expression
    assert '"Bandwidth","bandwidth"' in expression
    assert "@request:" not in expression
    assert "Object.defineProperty" in expression
    assert "setInterval" in expression
    assert "\n" not in expression


def test_generate_catalog_context_form_resolves_values_from_catalog_source_params() -> None:
    result = run_generator(
        "mixture",
        "mixture",
        "billing type=InternetChargeType,bandwidth=Bandwidth",
        "test-eip",
    )
    payload = json.loads(result.stdout)
    expression = payload["properties"]["mixture"]["config"]["value"]["expression"]

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
let first = fn(model, {{ params: {{ InternetChargeType: 'PayByTraffic', Bandwidth: 5 }} }}, {{}});
tick();
model.mixture = '';
let second = fn(model, {{ params: {{}} }}, {{}});
console.log(JSON.stringify({{ first, second, modelValue: model.mixture, inputValue }}));
"""
    node_result = subprocess.run(
        ["node", "-e", code],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert node_result.returncode == 0, node_result.stderr
    output = json.loads(node_result.stdout)
    assert json.loads(output["first"]) == {"billing type": "PayByTraffic", "bandwidth": "5"}
    assert output["second"] == output["first"]
    assert output["modelValue"] == output["first"]
    assert output["inputValue"] == output["first"]


def test_generate_catalog_context_form_rejects_request_context_aliases() -> None:
    result = run_generator(
        "mixture",
        "mixture",
        "owner=@request:owner,bandwidth=Bandwidth",
        "test-eip",
    )

    assert result.returncode != 0
    assert "fixed request-context aliases are not supported" in result.stderr


def test_generate_catalog_context_form_can_show_composed_field_when_explicit() -> None:
    result = run_generator(
        "mixture",
        "mixture",
        "billing type=InternetChargeType,bandwidth=Bandwidth",
        "test-eip",
        "--show-submit-field",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    prop = payload["properties"]["mixture"]
    assert prop["title"] == "mixture"
    assert "hideTitle" not in prop
    assert "HIDE=false" in prop["config"]["value"]["expression"]


def test_generate_catalog_context_form_accepts_named_non_ascii_separators() -> None:
    separator = unicodedata.lookup("IDEOGRAPHIC COMMA")

    result = run_generator(
        "mixture",
        "mixture",
        f"billing type=InternetChargeType{separator}bandwidth=Bandwidth",
        "test-eip",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    expression = payload["properties"]["mixture"]["config"]["value"]["expression"]
    assert '"InternetChargeType","billing type"' in expression
    assert '"Bandwidth","bandwidth"' in expression
