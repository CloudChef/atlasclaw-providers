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

    assert any("copy test-ip-form.json verbatim" in warning for warning in warnings)

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
