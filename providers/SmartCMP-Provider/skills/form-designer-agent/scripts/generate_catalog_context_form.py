# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Generate SmartCMP form JSON composed from scanned catalog parameter keys."""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any


def _js_string(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


HIDE_SUBMIT_FIELD_TRUE_VALUES = {"1", "true", "yes", "y", "hide", "hidden", "hide_submit_field"}
HIDE_SUBMIT_FIELD_FALSE_VALUES = {"0", "false", "no", "n", "show", "visible", "show_submit_field"}


def _as_bool(value: str) -> bool:
    return value.strip().lower() in HIDE_SUBMIT_FIELD_TRUE_VALUES


def _resolve_hide_submit_field(
    value: str,
    hide_flag: bool = False,
    show_flag: bool = False,
    default: bool = True,
) -> bool:
    if hide_flag:
        return True
    if show_flag:
        return False
    token = value.strip().lower()
    if token in HIDE_SUBMIT_FIELD_TRUE_VALUES:
        return True
    if token in HIDE_SUBMIT_FIELD_FALSE_VALUES:
        return False
    return default


def _is_bool_literal(value: str) -> bool:
    return value.strip().lower() in HIDE_SUBMIT_FIELD_TRUE_VALUES | HIDE_SUBMIT_FIELD_FALSE_VALUES


def _parse_fields(value: str) -> list[tuple[str, str]]:
    fields: list[tuple[str, str]] = []
    for raw in re.split(r"[,，、]+", value.strip()):
        raw = raw.strip()
        if not raw:
            continue
        if "=" not in raw:
            raise SystemExit(
                "Catalog fields must be label=key pairs scanned from Request Parameter Instructions."
            )
        label, key = raw.split("=", 1)
        label = label.strip()
        key = key.strip()
        if not label or not key:
            raise SystemExit(f"Invalid catalog field mapping: {raw}")
        pair = (key, label)
        if pair not in fields:
            fields.append(pair)
    if not fields:
        raise SystemExit("At least one catalog field mapping is required.")
    return fields


def _js_runtime_preamble(
    key: str,
    field_array: str,
    hide_value: str,
    allow_backend_labels_value: str,
) -> str:
    return (
        "function(model,sourceParams,schema,unused,cfg){"
        f"var KEY={key},FIELDS={field_array},HIDE={hide_value},ALLOW_BACKEND_LABELS={allow_backend_labels_value},W=window,ID='__smartcmp_catalog_auto_sync_'+KEY;"
    )


def _js_text_helpers() -> str:
    return (
        "var text=function(v){if(v===null||v===undefined)return'';if(typeof v==='object')v=v.label||v.name||v.displayName||v.text||v.value||v.username||v.loginId||v.originName||v.id||'';return String(v).replace(/\\s+/g,' ').replace(/^\\s+|\\s+$/g,'');};var domText=function(v){var raw=(v===null||v===undefined)?'':String(v),parts=raw.split(/[\\r\\n]+/),out=[],p;for(var i=0;i<parts.length;i++){p=text(parts[i]);if(p)out.push(p);}return out.length?out[out.length-1]:text(raw);};"
        "var state=W[ID]||{};state.values=state.values||{};state.cache=state.cache||{bg:{},user:{}};var seen=[];"
        "var getJson=function(url,pick){try{var x=new XMLHttpRequest();x.open('GET',url,false);x.setRequestHeader('Content-Type','application/json');x.send();if(x.status>=200&&x.status<300){return pick(JSON.parse(x.responseText));}}catch(e){}return'';};"
    )


def _js_dom_helpers() -> str:
    return (
        "var findInput=function(){try{var els=document.querySelectorAll('input,textarea,select');for(var i=0;i<els.length;i++){var e=els[i],n=e.getAttribute('name')||'',id=e.getAttribute('id')||'',ng=e.getAttribute('ng-model')||'',dk='',box=e.closest&&e.closest('[data-key]');if(box)dk=box.getAttribute('data-key')||'';if(n===KEY||id.indexOf(KEY)>=0||ng.indexOf(KEY)>=0||dk===KEY)return e;}}catch(e){}return null;};"
        "var hideUi=function(e){try{if(!e)return;var box=(e.closest&&(e.closest('.form-group')||e.closest('.ant-form-item')||e.closest('[data-key]')))||e.parentElement||e;box.style.position='absolute';box.style.left='-10000px';box.style.top='auto';box.style.width='1px';box.style.height='1px';box.style.overflow='hidden';box.style.opacity='0';box.style.pointerEvents='none';box.setAttribute('aria-hidden','true');e.setAttribute('tabindex','-1');}catch(x){}};"
        "var selected=function(e){try{if(e&&e.tagName&&String(e.tagName).toLowerCase()==='select'){var opt=e.options&&e.selectedIndex>=0&&e.options[e.selectedIndex];return domText(opt&&(opt.text||opt.label||opt.value))||text(e.value);}}catch(x){}if(!e)return'';var val=('value'in e)?e.value:'';return text(val)||domText(e.textContent||e.innerText);};"
        "var byLabel=function(label,k){try{var words=Array.isArray(label)?label:[label,k];var labels=document.querySelectorAll('.form-group label,.field-label,.control-label,.ant-form-item-label,label');for(var i=0;i<labels.length;i++){var l=text(labels[i].textContent||labels[i].innerText);for(var j=0;j<words.length;j++){if(words[j]&&(l.indexOf(words[j])>=0||l.indexOf(k)>=0)){var p=labels[i].closest('.form-group')||labels[i].closest('.ant-form-item')||labels[i].parentElement;if(p){var e=p.querySelector('select,input,textarea,.selected-value,.tag-text,.select2-selection__rendered,.ui-select-match-text,.ant-select-selection-item');var v=selected(e);if(v)return v;}}}}}catch(e){}return'';};"
        "var byKey=function(k){try{var esc=(W.CSS&&CSS.escape)?CSS.escape(k):String(k).replace(/[^a-zA-Z0-9_-]/g,'\\\\$&');var e=document.querySelector('[name=\"'+esc+'\"],[id=\"'+esc+'\"],[data-key=\"'+esc+'\"] input,[data-key=\"'+esc+'\"] select,[data-key=\"'+esc+'\"] textarea,[ng-model*=\"'+k+'\"]');var v=selected(e);if(v)return v;}catch(e){}return'';};"
    )


def _js_catalog_value_helpers() -> str:
    return (
        "var direct=function(o,k){try{if(!o||typeof o!=='object')return'';var v=o[k];if(v!==undefined&&v!==null)return text(v);var lk=String(k).toLowerCase();for(var p in o){if(String(p).toLowerCase()===lk)return text(o[p]);}}catch(e){}return'';};"
        "var catalogValue=function(o,k){try{var v=direct(o,k)||direct(o&&o.params,k)||direct(o&&o.resourceBundleParams,k)||direct(o&&o.genericRequest&&o.genericRequest.processForm,k);if(v)return v;var specs=o&&o.resourceSpecs;if(Array.isArray(specs)){for(var i=0;i<specs.length;i++){v=direct(specs[i],k)||direct(specs[i].params,k)||direct(specs[i].resourceBundleParams,k);if(v)return v;}}}catch(e){}return'';};"
        "var deep=function(o,k,d){try{if(!o||typeof o!=='object'||d>5)return'';for(var s=0;s<seen.length;s++){if(seen[s]===o)return'';}seen.push(o);var v=direct(o,k);if(v)return v;if(Array.isArray(o)){for(var a=0;a<o.length;a++){v=deep(o[a],k,d+1);if(v)return v;}return'';}var skip={window:1,document:1,parent:1,top:1,$parent:1,$root:1};for(var p in o){if(skip[p])continue;v=deep(o[p],k,d+1);if(v)return v;}}catch(e){}return'';};"
        "var roots=function(){var out=[sourceParams,schema,cfg,model];try{if(W.angular){var input=findInput(),nodes=[];if(input&&input.closest){var near=input.closest('catalog-form');if(near)nodes.push(near);}var forms=document.querySelectorAll('catalog-form');for(var f=0;f<forms.length;f++)nodes.push(forms[f]);var ctrls=document.querySelectorAll('[ng-controller],form,body');for(var c=0;c<ctrls.length;c++)nodes.push(ctrls[c]);for(var i=0;i<nodes.length;i++){var el=nodes[i],ae=W.angular.element(el),ctrl=ae.controller&&ae.controller('catalogForm'),iso=ae.isolateScope&&ae.isolateScope(),sc=ae.scope&&ae.scope();out.push(ctrl,ctrl&&(ctrl.vm||ctrl.$ctrl),iso,iso&&(iso.vm||iso.$ctrl),sc,sc&&(sc.vm||sc.$ctrl));var node=el;while(node){var ne=W.angular.element(node),ns=(ne.scope&&ne.scope())||(ne.isolateScope&&ne.isolateScope());var guard=0;while(ns&&guard<8){out.push(ns,ns&&(ns.vm||ns.$ctrl));ns=ns.$parent;guard++;}node=node.parentElement;}}}}catch(e){}return out;};"
    )


def _js_request_context_helpers() -> str:
    return (
        "var mergeRequest=function(out,p){try{if(!p||typeof p!=='object')return;if(p.sourceConfigParamter)mergeRequest(out,p.sourceConfigParamter);if(p.options&&p.options.sourceConfigParamter)mergeRequest(out,p.options.sourceConfigParamter);if(p.businessGroupId)out.businessGroupId=p.businessGroupId;if(p.projectId)out.projectId=p.projectId;if(p.ownerId)out.ownerId=p.ownerId;if(p.userId&&!out.ownerId)out.ownerId=p.userId;if(p.businessGroupName||p.departmentName)out.businessGroupName=text(p.businessGroupName||p.departmentName);if(p.projectName)out.projectName=text(p.projectName);if(p.ownerName||p.ownerDisplayName||p.requestUserName)out.ownerName=text(p.ownerName||p.ownerDisplayName||p.requestUserName);if(p.deploymentObj){if(p.deploymentObj.name)out.requestName=text(p.deploymentObj.name);if(p.deploymentObj.businessGroupId)out.businessGroupId=p.deploymentObj.businessGroupId;}if(p.selectedUser){if(p.selectedUser.id)out.ownerId=p.selectedUser.id;if(p.selectedUser.name||p.selectedUser.displayName||p.selectedUser.originName||p.selectedUser.username)out.ownerName=text(p.selectedUser.name||p.selectedUser.displayName||p.selectedUser.originName||p.selectedUser.username);}if(p.selectedBusinessGroup&&(p.selectedBusinessGroup.name||p.selectedBusinessGroup.displayName))out.businessGroupName=text(p.selectedBusinessGroup.name||p.selectedBusinessGroup.displayName);if(p.selectedGroup){if(typeof p.selectedGroup==='object'){out.projectId=p.selectedGroup.id||out.projectId;if(p.selectedGroup.name||p.selectedGroup.displayName)out.projectName=text(p.selectedGroup.name||p.selectedGroup.displayName);}else{out.projectId=p.selectedGroup;}}}catch(e){}};"
        "var requestContext=function(){var out={},rs=roots();for(var i=0;i<rs.length;i++)mergeRequest(out,rs[i]);return out;};"
        "var bgName=function(id){if(!id)return'';if(state.cache.bg[id])return state.cache.bg[id];return state.cache.bg[id]=getJson('/platform-api/business-groups/'+encodeURIComponent(id),function(o){return text(o.name||o.displayName);});};"
        "var userName=function(id){if(!id)return'';if(state.cache.user[id])return state.cache.user[id];return state.cache.user[id]=getJson('/platform-api/users/simple?ids='+encodeURIComponent(id),function(o){var a=Array.isArray(o)?o:(o.content||o.data||[]);if(Array.isArray(a)&&a[0])return text(a[0].name||a[0].displayName||a[0].username||a[0].loginId);return text(o.name||o.displayName||o.username||o.loginId);});};"
        "var requestValue=function(k,label){var p=requestContext(),v='';if(k==='name')v=text(p.requestName)||byLabel([label,'名称','Name'],k);else if(k==='owner'){v=text(p.ownerName)||userName(p.ownerId||p.userId)||byLabel([label,'所有者','负责人','Owner'],k);}else if(k==='department')v=text(p.businessGroupName)||bgName(p.businessGroupId)||byLabel([label,'部门','业务组','Business Group'],k);else if(k==='project')v=text(p.projectName)||byLabel([label,'项目','Project'],k);if(v){state.values['@request:'+k]=v;return v;}return state.values['@request:'+k]||'';};"
        "var valueOf=function(k,label){seen=[];if(String(k).indexOf('@request:')===0)return requestValue(String(k).slice(9),label);var v=byKey(k);if(v){state.values[k]=v;return v;}var rs=roots();for(var i=0;i<rs.length;i++){v=catalogValue(rs[i],k)||deep(rs[i],k,0);if(v){state.values[k]=v;return v;}}v=byLabel(label,k);if(v){state.values[k]=v;return v;}return state.values[k]||'';};"
    )


def _js_model_sync_helpers() -> str:
    return (
        "var parsed=function(v){v=text(v);if(!v||v.indexOf('AUTO_SYNC_PENDING')>=0)return null;try{var o=JSON.parse(v);if(!o||typeof o!=='object'||Array.isArray(o))return null;for(var i=0;i<FIELDS.length;i++){if(!text(o[FIELDS[i][1]]))return null;}return o;}catch(e){return null;}};var valid=function(v){var o=parsed(v);return o?JSON.stringify(o):'';};"
        "var guard=function(){try{if(!model||state.model===model)return;var cur=valid(model[KEY]);state.raw=cur||state.lastGood||state.raw||'';Object.defineProperty(model,KEY,{configurable:true,enumerable:true,get:function(){return state.lastGood||state.raw||'';},set:function(v){v=valid(v);if(v){state.raw=v;state.lastGood=v;}}});state.model=model;}catch(e){}};guard();"
        "var existing=function(){try{var v=model&&model[KEY];if(!v){var e=findInput();v=e&&selected(e);}return valid(v);}catch(e){return'';}};"
        "var resolve=function(){var obj={},miss=0;state.restoreOnly=false;for(var i=0;i<FIELDS.length;i++){var val=valueOf(FIELDS[i][0],FIELDS[i][1]);if(!val)miss++;obj[FIELDS[i][1]]=val;}var v=JSON.stringify(obj);if(miss){state.restoreOnly=true;return state.lastGood||existing()||'';}state.lastGood=v;return v;};"
        "var write=function(v){if(!v)return state.lastGood||existing()||'';var emit=!state.restoreOnly&&state.dispatched!==v;if(model&&model[KEY]!==v)model[KEY]=v;try{var e=findInput();if(HIDE)hideUi(e);if(e&&emit){var old=selected(e);if(old!==v){if('value'in e)e.value=v;else e.textContent=v;}e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));state.dispatched=v;if(W.angular){var ng=W.angular.element(e).controller('ngModel');if(ng){ng.$setViewValue(v);if(ng.$render)ng.$render();}var sc=W.angular.element(e).scope();if(sc&&sc.$applyAsync)sc.$applyAsync();}}}catch(e){}return v;};"
        "if(HIDE)hideUi(findInput());if(state.timer)clearInterval(state.timer);state.timer=setInterval(function(){guard();write(resolve());},500);W[ID]=state;return write(resolve());}"
    )


def _build_expression(
    backend_key: str,
    fields: list[tuple[str, str]],
    hide_submit_field: bool = True,
    allow_backend_labels: bool = False,
) -> str:
    key = _js_string(backend_key)
    field_array = _js_string([[field_key, label] for field_key, label in fields])
    hide_value = "true" if hide_submit_field else "false"
    allow_backend_labels_value = "true" if allow_backend_labels else "false"
    return ''.join(
        (
            _js_runtime_preamble(key, field_array, hide_value, allow_backend_labels_value),
            _js_text_helpers(),
            _js_dom_helpers(),
            _js_catalog_value_helpers(),
            _js_request_context_helpers(),
            _js_model_sync_helpers(),
        )
    )


def _field_display(title: str, hide_submit_field: bool) -> dict[str, Any]:
    if not hide_submit_field:
        return {"title": title, "inputClass": "form-control"}
    return {
        "title": " ",
        "i18nTitle": {"zh": "", "en": ""},
        "inputClass": "form-control",
        "labelClass": "",
        "className": "",
        "hideTitle": True,
        "hideTitleText": True,
        "notitle": True,
    }


def build_form(
    backend_key: str,
    title: str,
    fields: list[tuple[str, str]],
    fieldset_title: str,
    hide_submit_field: bool = True,
    allow_backend_labels: bool = False,
) -> dict[str, Any]:
    display = _field_display(title, hide_submit_field)
    return {
        "type": "object",
        "properties": {
            backend_key: {
                "id": backend_key,
                "type": "string",
                **display,
                "index": 0,
                "default": "AUTO_SYNC_PENDING",
                "widget": {"id": "string"},
                "config": {
                    "visibility": {"allowInRequest": True},
                    "modification": {"allowInRequest": True},
                    "value": {
                        "source": "mock",
                        "method": "mock",
                        "expression": _build_expression(
                            backend_key,
                            fields,
                            hide_submit_field,
                            allow_backend_labels,
                        ),
                    },
                },
            },
            "schemaFormValid": {
                "hidden": True,
                "type": "boolean",
                "default": True,
                "condition": "1 === 2",
                "widget": {"id": "hidden"},
            },
        },
        "required": [],
        "fieldsets": [
            {
                "id": "fieldset-default",
                "title": fieldset_title,
                "description": "",
                "name": fieldset_title,
                "fields": [backend_key, "schemaFormValid"],
            }
        ],
        "widget": {"id": "object"},
    }


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backend_key")
    parser.add_argument("title")
    parser.add_argument("fields", help="Comma-separated label=key pairs scanned from catalog details.")
    parser.add_argument("fieldset_title", nargs="?", default="")
    parser.add_argument("hide_submit_field_pos", nargs="?", default="")
    parser.add_argument("--hide-submit-field", action="store_true")
    parser.add_argument("--show-submit-field", action="store_true")
    parser.add_argument("--allow-backend-labels", action="store_true")
    args = parser.parse_args(argv)
    fieldset_title = args.fieldset_title.strip()
    if not args.hide_submit_field_pos and _is_bool_literal(fieldset_title):
        hide_submit_field = _resolve_hide_submit_field(
            fieldset_title,
            args.hide_submit_field,
            args.show_submit_field,
        )
        fieldset_title = "表单字段"
    else:
        hide_submit_field = _resolve_hide_submit_field(
            args.hide_submit_field_pos,
            args.hide_submit_field,
            args.show_submit_field,
        )
        fieldset_title = fieldset_title or "表单字段"

    payload = build_form(
        args.backend_key,
        args.title,
        _parse_fields(args.fields),
        fieldset_title,
        hide_submit_field,
        args.allow_backend_labels,
    )
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=4)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
