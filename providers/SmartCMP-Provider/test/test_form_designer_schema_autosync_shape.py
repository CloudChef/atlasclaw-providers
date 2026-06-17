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
