# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Generate canonical SmartCMP request-context auto-sync Schema Form JSON."""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any


FIELD_DEFINITIONS = {
    "name": {
        "label": "名称",
        "aliases": ("name", "名称", "service_name"),
        "domLabels": ("名称", "Name"),
    },
    "owner": {
        "label": "所有者",
        "aliases": ("owner", "所有者", "负责人"),
        "domLabels": ("所有者", "负责人", "Owner", "owners"),
    },
    "department": {
        "label": "部门",
        "aliases": ("department", "dept", "部门"),
        "domLabels": ("部门", "业务组", "业务群组", "Business Group"),
    },
    "business_group": {
        "canonical": "department",
        "label": "业务组",
        "aliases": ("business_group", "business_group_name", "businessgroupname", "business_group_id", "businessgroupid", "业务组"),
    },
    "project": {
        "label": "项目",
        "aliases": ("project", "项目"),
        "domLabels": ("项目", "Project"),
    },
}


def _build_field_aliases() -> dict[str, tuple[str, str]]:
    aliases: dict[str, tuple[str, str]] = {}
    for key, definition in FIELD_DEFINITIONS.items():
        canonical = str(definition.get("canonical") or key)
        label = str(definition["label"])
        for alias in definition["aliases"]:
            aliases[str(alias)] = (canonical, label)
    return aliases


FIELD_ALIASES = _build_field_aliases()
RUNTIME_DOM_LABELS = {
    key: list(definition["domLabels"])
    for key, definition in FIELD_DEFINITIONS.items()
    if "domLabels" in definition
}


def _normalize_key(value: str) -> str:
    return re.sub(r"\s+", "", value.strip())


def _parse_fields(value: str) -> list[tuple[str, str]]:
    fields: list[tuple[str, str]] = []
    for raw in re.split(r"[,，、\s]+", value.strip()):
        if not raw:
            continue
        item = FIELD_ALIASES.get(_normalize_key(raw).lower()) or FIELD_ALIASES.get(_normalize_key(raw))
        if not item:
            raise SystemExit(f"Unsupported fixed request field: {raw}")
        if item not in fields:
            fields.append(item)
    if not fields:
        raise SystemExit("At least one fixed request field is required.")
    return fields


def _js_string(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _as_include_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "include", "include_source_fields"}


HIDE_SUBMIT_FIELD_TRUE_VALUES = {"1", "true", "yes", "y", "hide", "hidden", "hide_submit_field"}
HIDE_SUBMIT_FIELD_FALSE_VALUES = {"0", "false", "no", "n", "show", "visible", "show_submit_field"}


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


def _source_backend_key(field: tuple[str, str]) -> str:
    key, label = field
    if key == "department" and label == "业务组":
        return "business_group"
    return key


def _build_expression(
    backend_key: str,
    fields: list[tuple[str, str]],
    mode: str = "template",
    hide_submit_field: bool = True,
) -> str:
    field_array = _js_string([[key, label] for key, label in fields])
    key = _js_string(backend_key)
    mode_value = _js_string(mode)
    label_config = _js_string(RUNTIME_DOM_LABELS)
    hide_value = "true" if hide_submit_field else "false"
    script = (
        "function(model,sourceParams,schema,unused,cfg){"
        f"var KEY={key},FIELDS={field_array},MODE={mode_value},LABELS={label_config},HIDE={hide_value},W=window,ID='__smartcmp_auto_sync_'+KEY;"
        "var text=function(v){if(v===null||v===undefined)return'';if(typeof v==='object')v=v.name||v.displayName||v.label||v.username||v.loginId||v.originName||v.id||'';return String(v).replace(/^\\s+|\\s+$/g,'');};"
        "var state=W[ID]||{};state.cache=state.cache||{bg:{},user:{}};state.values=state.values||{};var stop=function(n){try{if(W[n]){clearInterval(W[n]);W[n]=null;}}catch(e){}};stop('_backendTestInterval');stop('__smartcmp_backend_test_sync');"
        "var getJson=function(url,pick){try{var x=new XMLHttpRequest();x.open('GET',url,false);x.setRequestHeader('Content-Type','application/json');x.send();if(x.status>=200&&x.status<300){return pick(JSON.parse(x.responseText));}}catch(e){}return'';};"
        "var findInput=function(){try{var els=document.querySelectorAll('input,textarea');for(var i=0;i<els.length;i++){var e=els[i],n=e.getAttribute('name')||'',id=e.getAttribute('id')||'',ng=e.getAttribute('ng-model')||'',dk='',box=e.closest&&e.closest('[data-key]');if(box)dk=box.getAttribute('data-key')||'';if(n===KEY||id.indexOf(KEY)>=0||ng.indexOf(KEY)>=0||dk===KEY)return e;}}catch(e){}return null;};"
        "var hideUi=function(e){try{if(!e)return;var box=(e.closest&&(e.closest('.form-group')||e.closest('.ant-form-item')||e.closest('[data-key]')))||e.parentElement||e;box.style.position='absolute';box.style.left='-10000px';box.style.top='auto';box.style.width='1px';box.style.height='1px';box.style.overflow='hidden';box.style.opacity='0';box.style.pointerEvents='none';box.setAttribute('aria-hidden','true');e.setAttribute('tabindex','-1');}catch(x){}};"
        "var mergeSource=function(out,p){try{if(!p)return;if(p.businessGroupId)out.businessGroupId=p.businessGroupId;if(p.projectId)out.projectId=p.projectId;if(p.ownerId)out.ownerId=p.ownerId;if(p.userId&&!out.ownerId)out.ownerId=p.userId;if(p.businessGroupName||p.departmentName)out.businessGroupName=text(p.businessGroupName||p.departmentName);if(p.projectName)out.projectName=text(p.projectName);if(p.ownerName||p.ownerDisplayName||p.requestUserName)out.ownerName=text(p.ownerName||p.ownerDisplayName||p.requestUserName);}catch(e){}};"
        "var mergeScope=function(out,vm){try{if(!vm)return;mergeSource(out,vm.sourceConfigParamter);mergeSource(out,vm.options&&vm.options.sourceConfigParamter);if(vm.businessGroupId)out.businessGroupId=vm.businessGroupId;if(vm.projectId)out.projectId=vm.projectId;if(vm.ownerId)out.ownerId=vm.ownerId;if(vm.userId&&!out.ownerId)out.ownerId=vm.userId;if(vm.deploymentObj&&vm.deploymentObj.name)out.requestName=text(vm.deploymentObj.name);if(vm.deploymentObj&&vm.deploymentObj.businessGroupId)out.businessGroupId=vm.deploymentObj.businessGroupId;if(vm.selectedUser){if(vm.selectedUser.id)out.ownerId=vm.selectedUser.id;if(vm.selectedUser.name||vm.selectedUser.displayName||vm.selectedUser.originName||vm.selectedUser.username)out.ownerName=text(vm.selectedUser.name||vm.selectedUser.displayName||vm.selectedUser.originName||vm.selectedUser.username);}if(vm.selectedBusinessGroup&&(vm.selectedBusinessGroup.name||vm.selectedBusinessGroup.displayName))out.businessGroupName=text(vm.selectedBusinessGroup.name||vm.selectedBusinessGroup.displayName);if(vm.selectedGroup){if(typeof vm.selectedGroup==='object'){out.projectId=vm.selectedGroup.id||out.projectId;if(vm.selectedGroup.name||vm.selectedGroup.displayName)out.projectName=text(vm.selectedGroup.name||vm.selectedGroup.displayName);}else{out.projectId=vm.selectedGroup;}}}catch(e){}};"
        "var latest=function(){var out={};mergeSource(out,sourceParams);try{if(W.angular){var input=findInput(),nodes=[];if(input&&input.closest){var near=input.closest('catalog-form');if(near)nodes.push(near);}var forms=document.querySelectorAll('catalog-form');for(var a=0;a<forms.length;a++)nodes.push(forms[a]);var ctrls=document.querySelectorAll('[ng-controller],form,body');for(var c=0;c<ctrls.length;c++)nodes.push(ctrls[c]);for(var i=0;i<nodes.length;i++){var el=nodes[i],ae=W.angular.element(el),ctrl=ae.controller&&ae.controller('catalogForm'),iso=ae.isolateScope&&ae.isolateScope(),sc=ae.scope&&ae.scope();mergeScope(out,ctrl);mergeScope(out,iso&&(iso.vm||iso.$ctrl));mergeScope(out,sc&&(sc.vm||sc.$ctrl));var node=el;while(node){var ne=W.angular.element(node),ns=(ne.scope&&ne.scope())||(ne.isolateScope&&ne.isolateScope());mergeScope(out,ns&&(ns.vm||ns.$ctrl));node=node.parentElement;}}}}catch(e){}return out;};"
        "var byLabel=function(words){try{var labels=document.querySelectorAll('.form-group label,.field-label,.control-label,.ant-form-item-label,label');for(var i=0;i<labels.length;i++){var l=text(labels[i].textContent||labels[i].innerText);for(var j=0;j<words.length;j++){if(l.indexOf(words[j])>=0){var p=labels[i].closest('.form-group')||labels[i].closest('.ant-form-item')||labels[i].parentElement;if(p){var e=p.querySelector('input,textarea,.selected-value,.tag-text,.select2-selection__rendered,.ui-select-match-text');var v=e&&text(e.value||e.textContent||e.innerText);if(v)return v;}}}}}catch(e){}return'';};"
        "var domValue=function(sel){try{var e=document.querySelector(sel);return e?text(e.value||e.textContent||e.innerText):'';}catch(e){return'';}};"
        "var bgName=function(id){if(!id)return'';if(state.cache.bg[id])return state.cache.bg[id];return state.cache.bg[id]=getJson('/platform-api/business-groups/'+encodeURIComponent(id),function(o){return text(o.name||o.displayName);});};"
        "var userName=function(id){if(!id)return'';if(state.cache.user[id])return state.cache.user[id];return state.cache.user[id]=getJson('/platform-api/users/simple?ids='+encodeURIComponent(id),function(o){var a=Array.isArray(o)?o:(o.content||o.data||[]);if(Array.isArray(a)&&a[0])return text(a[0].name||a[0].displayName||a[0].username||a[0].loginId);return text(o.name||o.displayName||o.username||o.loginId);});};"
        "var valueOf=function(k,p){var v='';if(k==='name'){v=text(p.requestName)||domValue('input[ng-model*=\"deploymentObj.name\"],textarea[ng-model*=\"deploymentObj.name\"],input[name=\"name\"],textarea[name=\"name\"]')||byLabel(LABELS.name||[]);}else if(k==='owner'){v=text(p.ownerName)||userName(p.ownerId||p.userId);if(!v&&!p.ownerId&&!p.userId)v=getJson('/platform-api/users/current-user-details',function(o){return text(o.name||o.displayName||o.username||o.loginId);});if(!v)v=byLabel(LABELS.owner||[]);}else if(k==='department'){v=text(p.businessGroupName)||bgName(p.businessGroupId)||byLabel(LABELS.department||[]);}else if(k==='project'){v=text(p.projectName)||byLabel(LABELS.project||[]);}if(v){state.values[k]=v;return v;}return state.values[k]||'';};"
        "var valid=function(v){v=text(v);if(!v||v.indexOf('AUTO_SYNC_PENDING')>=0||v.indexOf('未获取')>=0)return'';if(MODE==='raw')return v;try{var o=JSON.parse(v);if(!o||typeof o!=='object'||Array.isArray(o))return'';for(var i=0;i<FIELDS.length;i++){if(!text(o[FIELDS[i][1]]))return'';}return JSON.stringify(o);}catch(e){return'';}};"
        "var guard=function(){try{if(!model||state.model===model)return;var cur=valid(model[KEY]);state.raw=cur||state.lastGood||state.raw||'';Object.defineProperty(model,KEY,{configurable:true,enumerable:true,get:function(){return state.lastGood||state.raw||'';},set:function(v){v=valid(v);if(v){state.raw=v;state.lastGood=v;}}});state.model=model;}catch(e){}};guard();"
        "var existing=function(){try{var v=model&&model[KEY];if(!v){var e=findInput();v=e&&('value'in e?e.value:e.textContent);}return valid(v);}catch(e){return'';}};"
        "var resolve=function(){var p=latest(),miss=0;state.restoreOnly=false;if(MODE==='raw'){var single=valueOf(FIELDS[0][0],p);if(!single){state.restoreOnly=true;return state.lastGood||existing()||'';}state.lastGood=single;return single;}var obj={};for(var i=0;i<FIELDS.length;i++){var val=valueOf(FIELDS[i][0],p);if(!val)miss++;obj[FIELDS[i][1]]=val;}var v=JSON.stringify(obj);if(miss){state.restoreOnly=true;return state.lastGood||existing()||'';}state.lastGood=v;return v;};"
        "var write=function(v){if(!v)return state.lastGood||existing()||'';var emit=!state.restoreOnly&&state.dispatched!==v;if(model&&model[KEY]!==v){model[KEY]=v;}try{var e=findInput();if(HIDE)hideUi(e);if(e&&emit){var old=('value'in e)?e.value:e.textContent;if(old!==v){if('value'in e)e.value=v;else e.textContent=v;}e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));state.dispatched=v;if(W.angular){var ng=W.angular.element(e).controller('ngModel');if(ng){ng.$setViewValue(v);if(ng.$render)ng.$render();}var sc=W.angular.element(e).scope();if(sc&&sc.$applyAsync)sc.$applyAsync();}}}catch(e){}return v;};"
        "if(HIDE)hideUi(findInput());if(state.timer)clearInterval(state.timer);state.last=null;state.timer=setInterval(function(){guard();var v=resolve();if(v)state.last=write(v);},500);W[ID]=state;return write(resolve());}"
    )
    return script


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


def _build_field(
    backend_key: str,
    title: str,
    fields: list[tuple[str, str]],
    index: int,
    mode: str,
    hide_submit_field: bool = True,
) -> dict[str, Any]:
    display = _field_display(title, hide_submit_field)
    return {
        "id": backend_key,
        "type": "string",
        **display,
        "index": index,
        "default": "AUTO_SYNC_PENDING",
        "widget": {"id": "string"},
        "config": {
            "visibility": {"allowInRequest": True},
            "modification": {"allowInRequest": True},
            "value": {
                "source": "mock",
                "method": "mock",
                "expression": _build_expression(backend_key, fields, mode, hide_submit_field),
            },
        },
    }


def build_form(
    backend_key: str,
    title: str,
    fields: list[tuple[str, str]],
    fieldset_title: str,
    index: int,
    include_source_fields: bool = False,
    hide_submit_field: bool = True,
) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    fieldset_fields: list[str] = []
    next_index = index
    if include_source_fields:
        for field in fields:
            source_key = _source_backend_key(field)
            if source_key in properties or source_key == backend_key:
                continue
            properties[source_key] = _build_field(
                source_key,
                field[1],
                [field],
                next_index,
                "raw",
                hide_submit_field=False,
            )
            fieldset_fields.append(source_key)
            next_index += 1

    properties[backend_key] = _build_field(
        backend_key,
        title,
        fields,
        next_index,
        "template",
        hide_submit_field,
    )
    fieldset_fields.append(backend_key)
    properties["schemaFormValid"] = {
        "hidden": True,
        "type": "boolean",
        "default": True,
        "condition": "1 === 2",
        "widget": {"id": "hidden"},
    }
    fieldset_fields.append("schemaFormValid")

    return {
        "type": "object",
        "properties": properties,
        "required": [],
        "fieldsets": [
            {
                "id": "fieldset-default",
                "title": fieldset_title,
                "description": "",
                "name": fieldset_title,
                "fields": fieldset_fields,
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
    parser.add_argument("fields", help="Comma-separated fixed fields, e.g. 名称,所有者")
    parser.add_argument("fieldset_title_pos", nargs="?", default="")
    parser.add_argument("include_source_fields_pos", nargs="?", default="")
    parser.add_argument("hide_submit_field_pos", nargs="?", default="")
    parser.add_argument("--fieldset-title", default="")
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--include-source-fields", action="store_true")
    parser.add_argument("--hide-submit-field", action="store_true")
    parser.add_argument("--show-submit-field", action="store_true")
    args = parser.parse_args(argv)

    fields = _parse_fields(args.fields)
    fieldset_title = args.fieldset_title or args.fieldset_title_pos
    include_source_fields = args.include_source_fields or _as_include_bool(args.include_source_fields_pos)
    hide_submit_field = _resolve_hide_submit_field(
        args.hide_submit_field_pos,
        args.hide_submit_field,
        args.show_submit_field,
    )
    payload = build_form(
        args.backend_key,
        args.title,
        fields,
        fieldset_title,
        args.index,
        include_source_fields,
        hide_submit_field,
    )
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=4)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
