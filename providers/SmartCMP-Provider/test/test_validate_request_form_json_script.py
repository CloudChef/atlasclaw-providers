# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

import importlib.util
import json
import sys
import unicodedata
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "form-designer-agent"
    / "scripts"
    / "validate_request_form_json.py"
)


def _load_module():
    module_name = "test_validate_request_form_json_script_module"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


def test_validate_request_form_json_detects_named_fullwidth_display_separator() -> None:
    module = _load_module()
    separator = unicodedata.lookup("FULLWIDTH COLON")
    script = (
        "function(model,sourceParams,schema){"
        "var parts=[];"
        f"parts.push('billing{separator}'+sourceParams.billing);"
        "var v='{'+parts.join(',')+'}';"
        "model.mixture=v;"
        "return v;"
        "}"
    )
    payload = {
        "type": "object",
        "properties": {
            "mixture": {
                "id": "mixture",
                "type": "string",
                "title": "mixture",
                "index": 0,
                "inputClass": "form-control",
                "widget": {"id": "string"},
                "config": {
                    "visibility": {"allowInRequest": True},
                    "modification": {"allowInRequest": True},
                    "value": {
                        "source": "mock",
                        "method": "mock",
                        "expression": script,
                    },
                },
            }
        },
        "fieldsets": [{"fields": ["mixture"], "title": "Form Fields", "name": "Form Fields"}],
    }

    result = module.validate_form_json(json.dumps(payload, ensure_ascii=False))

    assert result["valid"] is False
    assert any(issue["code"] == "composed_value_not_json_string" for issue in result["issues"])
