# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

import json

import pytest

from form_designer_test_utils import (
    FakeResponse,
    SCRIPTS_DIR,
    SKILL_ROOT,
    extract_meta,
    load_module,
    run_main,
)

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
