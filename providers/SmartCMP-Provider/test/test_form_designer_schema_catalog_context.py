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
