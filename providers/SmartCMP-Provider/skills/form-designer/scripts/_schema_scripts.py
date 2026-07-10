#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Build SmartCMP form schema JavaScript expressions."""

from __future__ import annotations

import json
from typing import Any

def build_model_projection_expression(
    fields: list[dict[str, Any]],
    *,
    target_field_key: str | None = None,
    output_type: str = "string",
) -> str:
    """Build a one-line SmartCMP mock expression that projects model values."""
    pairs: list[tuple[str, str | list[str], list[str]]] = []
    seen_labels: set[str] = set()
    for field in fields:
        if not isinstance(field, dict):
            continue
        label = field.get("label")
        path = field.get("path")
        if not isinstance(label, str) or not label.strip():
            continue
        label = label.strip()
        if label in seen_labels:
            raise ValueError(
                f"value expression fields contain duplicate output label {label!r}; "
                "use compose for nested or grouped output structures."
            )
        seen_labels.add(label)
        if isinstance(path, list):
            cleaned_paths = [item.strip() for item in path if isinstance(item, str) and item.strip()]
            if not cleaned_paths:
                continue
            pairs.append((label, cleaned_paths, _clean_string_list(field.get("labels"))))
            continue
        if not isinstance(path, str) or not path.strip():
            continue
        pairs.append((label, path.strip(), _clean_string_list(field.get("labels"))))

    if not pairs:
        raise ValueError("value expression fields must include at least one label/path pair.")

    compose_spec: dict[str, dict[str, str | list[str]]] = {}
    for label, path, labels in pairs:
        reference: dict[str, str | list[str]] = (
            {"$paths": path}
            if isinstance(path, list)
            else {"$path": path}
        )
        reference["$label"] = label
        if labels:
            reference["$labels"] = labels
        compose_spec[label] = reference

    return build_model_composition_expression(
        compose_spec,
        target_field_key=target_field_key,
        output_type=output_type,
    )


def build_model_composition_expression(
    compose_spec: Any,
    *,
    target_field_key: str | None = None,
    output_type: str = "string",
) -> str:
    """Build a one-line SmartCMP mock expression from a JSON composition spec."""
    spec_literal = json.dumps(compose_spec, ensure_ascii=False, separators=(",", ":"))
    output_type_literal = json.dumps(
        _normalize_expression_output_type(output_type),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    target_literal = (
        json.dumps(target_field_key, ensure_ascii=False, separators=(",", ":"))
        if isinstance(target_field_key, str) and target_field_key
        else ""
    )

    result_statement = (
        f"var targetKey = {target_literal}; var composed = compose(spec); var result = hasValue(composed) ? resultValue(composed) : emptyValue(); if (model && typeof model === 'object') model[targetKey] = result; return result; }}"
        if target_literal
        else "var composed = compose(spec); return hasValue(composed) ? resultValue(composed) : emptyValue(); }"
    )
    return (
        "function(model, sourceParams, schema, unused, cfg) { "
        "function get(obj, path) { return String(path).split('.').reduce(function(o, k) { return o && o[k]; }, obj); } "
        "function getAny(obj, path) { var parts = String(path).split('.'); for (var i = parts.length; i > 0; i--) { var v = get(obj, parts.slice(0, i).join('.')); if (v != null && v !== '') return v; } return ''; } "
        "function clean(v) { v = String(v).replace(/^[\\s　]+|[\\s　]+$/g, '').replace(/[\\r\\n\\t]+/g, ' ').replace(/\\s{2,}/g, ' '); return (!v || v === '请选择' || v === '加载' || v === '正在加载...' || v === '暂无数据') ? '' : v; } "
        "function text(v) { if (v == null) return ''; if (Array.isArray(v)) return v.map(text).filter(Boolean).join(','); "
        "if (typeof v === 'object') return clean(v.name || v.originName || v.displayName || v.businessGroupName || v.label || v.text || v.projectName || v.applicationName || v.userName || v.userLoginId || v.username || v.loginId || v.value || v.id || ''); "
        "return clean(v); } "
        "function roots() { var out = []; function addRoot(v, depth) { if (!v || (typeof v !== 'object' && typeof v !== 'function') || depth > 4) return; for (var s = 0; s < out.length; s++) { if (out[s] === v) return; } out.push(v); var keys = ['params','resourceBundleParams','sourceConfigParamter','externalParams','catalogServiceRequest','genericRequest','processFormParams','processForm']; for (var i = 0; i < keys.length; i++) { try { var child = v[keys[i]]; if (child && child !== v) addRoot(child, depth + 1); } catch (e) {} } } addRoot(sourceParams, 0); addRoot(schema, 0); addRoot(cfg, 0); addRoot(model, 0); try { if (typeof window !== 'undefined' && window.angular && typeof document !== 'undefined') { var nodes = document.querySelectorAll('[ng-controller],[formcontrolname],[data-key]'); for (var i = 0; i < nodes.length; i++) { try { var ae = window.angular.element(nodes[i]), iso = ae.isolateScope && ae.isolateScope(), sc = ae.scope && ae.scope(); addRoot(iso, 0); addRoot(iso && (iso.vm || iso.$ctrl), 0); addRoot(sc, 0); addRoot(sc && (sc.vm || sc.$ctrl), 0); } catch (e) {} } } } catch (e) {} return out; } "
        "function selected(root) { try { if (!root) return ''; var selText = root.querySelector('.selected-value,.tag-text,.treeview-select-text,.treeview-select-text-color,.select2-selection__rendered,.ui-select-match-text,.ant-select-selection-item,.ant-select-selection-selected-value,.ant-select-selection__rendered,.ant-select-selection__choice__content'); var sv = text(selText && (selText.textContent || selText.innerText)); if (sv) return sv; sv = text(selText && selText.getAttribute && selText.getAttribute('title')); if (sv) return sv; var sel = root.querySelector('select'); if (sel) { var opt = sel.options && sel.selectedIndex >= 0 && sel.options[sel.selectedIndex]; return text(opt && (opt.text || opt.label || opt.value)) || text(sel.value); } var input = root.querySelector('textarea,input'); if (input) return text(input.value || input.textContent); var lines = String(root.textContent || root.innerText || '').split(/\\n+/); for (var i = 1; i < lines.length; i++) { var v = clean(lines[i]); if (v) return v; } } catch (e) {} return ''; } "
        "function labelList(label) { if (Array.isArray(label)) return label; return [label]; } "
        "function labelMatch(actual, want) { actual = clean(actual).replace(/^[*＊\\s]+|[*＊\\s]+$/g, ''); want = clean(want); return actual === want || actual.indexOf(want + '：') === 0 || actual.indexOf(want + ':') === 0; } "
        "function byLabel(label) { try { var labels = labelList(label).map(clean).filter(Boolean); if (!labels.length || typeof document === 'undefined') return ''; var blocks = document.querySelectorAll('.form-group,.ant-form-item,.schema-form-default-item,.schema-form-ui-select,[data-key],[formcontrolname]'); for (var i = 0; i < blocks.length; i++) { var labelNode = blocks[i].querySelector && blocks[i].querySelector('label,.ant-form-item-label,.control-label'); var lt = text(labelNode && (labelNode.textContent || labelNode.innerText)); var t = text(blocks[i].textContent || blocks[i].innerText); for (var j = 0; j < labels.length; j++) { var l = labels[j]; if (labelMatch(lt, l) || t.indexOf(l) === 0 || t.indexOf(l + '\\n') >= 0 || t.indexOf(l + '：') >= 0 || t.indexOf(l + ':') >= 0) { var v = selected(blocks[i]); if (v) return v; } } } } catch (e) {} return ''; } "
        "function readExact(path) { var rs = roots(); for (var i = 0; i < rs.length; i++) { var r = rs[i], v = text(get(r, path)) || text(get(r && r.params, path)) || text(get(r && r.resourceBundleParams, path)) || text(get(r && r.sourceConfigParamter, path)) || text(get(r && r.externalParams, path)) || text(get(r && r.genericRequest && r.genericRequest.processFormParams, path)) || text(get(r && r.genericRequest && r.genericRequest.processForm, path)) || text(get(r && r.catalogServiceRequest, path)); if (v) return v; } return ''; } "
        "function read(path, label) { var rs = roots(); for (var i = 0; i < rs.length; i++) { var r = rs[i], v = text(getAny(r, path)) || text(getAny(r && r.params, path)) || text(getAny(r && r.resourceBundleParams, path)) || text(getAny(r && r.sourceConfigParamter, path)) || text(getAny(r && r.externalParams, path)) || text(getAny(r && r.genericRequest && r.genericRequest.processFormParams, path)) || text(getAny(r && r.genericRequest && r.genericRequest.processForm, path)) || text(getAny(r && r.catalogServiceRequest, path)); if (v) return v; } return byLabel(label); } "
        "function firstText(paths, label) { for (var i = 0; i < paths.length; i++) { var v = read(paths[i], label); if (v) return v; } return byLabel(label); } "
        "function compose(spec, label) { if (spec == null) return spec; if (Array.isArray(spec)) return spec.map(function(item) { return compose(item, label); }); "
        "if (typeof spec === 'object') { if (Object.prototype.hasOwnProperty.call(spec, '$path')) return readExact(spec.$path); "
        "if (Object.prototype.hasOwnProperty.call(spec, '$paths') && Array.isArray(spec.$paths)) return firstText(spec.$paths, spec.$labels || spec.$label || label); "
        "if (Object.prototype.hasOwnProperty.call(spec, '$literal')) return spec.$literal; "
        "if (Object.prototype.hasOwnProperty.call(spec, '$concat')) return spec.$concat.map(function(item) { return compose(item, label); }).join(''); "
        "var out = {}; Object.keys(spec).forEach(function(k) { out[k] = compose(spec[k], k); }); return out; } "
        "return spec; } "
        "function hasValue(v) { if (v == null) return false; if (Array.isArray(v)) { for (var i = 0; i < v.length; i++) { if (hasValue(v[i])) return true; } return false; } if (typeof v === 'object') { for (var k in v) { if (Object.prototype.hasOwnProperty.call(v, k) && hasValue(v[k])) return true; } return false; } return clean(v) !== ''; } "
        "function resultValue(v) { if (outputType === 'object') return v; if (outputType === 'array') return Array.isArray(v) ? v : [v]; if (outputType === 'jsonString') return JSON.stringify(v); return typeof v === 'string' ? v : JSON.stringify(v); } "
        "function emptyValue() { if (outputType === 'object') return null; if (outputType === 'array') return []; return ''; } "
        f"var spec = {spec_literal}; var outputType = {output_type_literal}; {result_statement}"
    )


def _normalize_expression_output_type(value: str) -> str:
    normalized = str(value or "").strip().replace("-", "").replace("_", "").lower()
    if normalized in {"object", "jsonobject", "rawobject"}:
        return "object"
    if normalized in {"array", "jsonarray", "rawarray"}:
        return "array"
    if normalized in {"jsonstring", "json"}:
        return "jsonString"
    return "string"


def _clean_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    labels: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            continue
        label = item.strip()
        if label in seen:
            continue
        labels.append(label)
        seen.add(label)
    return labels
