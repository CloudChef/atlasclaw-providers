#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Inspect SmartCMP form schema JavaScript expressions without executing them."""

from __future__ import annotations

import json
import re
from typing import Any


_EXPECTED_FUNCTION_PATTERN = re.compile(
    r"^\s*function\s*\(\s*model\s*,\s*sourceParams\s*,\s*schema\s*,\s*unused\s*,\s*cfg\s*\)",
    re.DOTALL,
)

_RISK_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\beval\s*\(", "eval(...)"),
    (
        r"(?<![\w$])(?:new\s+)?(?:Function|(?:[A-Za-z_$][\w$]*\s*\.\s*)+Function)\s*\(",
        "Function constructor",
    ),
    (r"\bfetch\s*\(", "fetch(...)"),
    (r"\bXMLHttpRequest\b", "XMLHttpRequest"),
    (r"\bdocument\s*\.\s*cookie\b", "document.cookie"),
    (r"https?://", "external URL"),
)


def _javascript_without_literals(expression: str) -> str:
    """Return JavaScript with string literals and comments blanked out."""
    output: list[str] = []
    index = 0
    length = len(expression)
    quote: str | None = None

    while index < length:
        char = expression[index]
        next_char = expression[index + 1] if index + 1 < length else ""

        if quote is not None:
            if char == "\\":
                output.append(" ")
                if index + 1 < length:
                    output.append(" ")
                    index += 2
                    continue
            elif char == quote:
                quote = None
            output.append(" ")
            index += 1
            continue

        if char in ("'", '"', "`"):
            quote = char
            output.append(" ")
            index += 1
            continue

        if char == "/" and next_char == "/":
            output.extend((" ", " "))
            index += 2
            while index < length and expression[index] not in "\r\n":
                output.append(" ")
                index += 1
            continue

        if char == "/" and next_char == "*":
            output.extend((" ", " "))
            index += 2
            while index < length:
                if expression[index] == "*" and index + 1 < length and expression[index + 1] == "/":
                    output.extend((" ", " "))
                    index += 2
                    break
                output.append(" ")
                index += 1
            continue

        output.append(char)
        index += 1

    return "".join(output)


def expression_from_field(field: dict[str, Any]) -> str:
    """Return a field-level value expression when it is stored as a string.

    SmartCMP keeps dynamic field expressions at
    `field.config.value.expression`. The normalizer must preserve that raw
    value, so this helper only reads the nested value and never coerces or
    rewrites non-string shapes.

    Args:
        field: A SmartCMP schema field object.

    Returns:
        The exact expression string, or an empty string when no string
        expression is present.
    """
    config = field.get("config")
    if not isinstance(config, dict):
        return ""

    value = config.get("value")
    if not isinstance(value, dict):
        return ""

    expression = value.get("expression")
    if not isinstance(expression, str):
        return ""
    return expression


def validate_javascript_expression(expression: str, *, field_key: str) -> list[str]:
    """Return warnings for risky or unexpected JavaScript expression text.

    The check is intentionally conservative: it does not parse or execute
    JavaScript, and it never rejects or mutates schema content. Warnings call
    out patterns that deserve manual review before a generated schema is copied
    into SmartCMP.

    Args:
        expression: Raw JavaScript expression text from a schema field.
        field_key: Field key used to identify the warning source.

    Returns:
        Human-readable warnings for the caller to surface alongside normalized
        schema output.
    """
    if not expression:
        return []

    warnings: list[str] = []
    executable_text = _javascript_without_literals(expression)
    if "..." in executable_text or "…" in executable_text:
        warnings.append(
            f"JavaScript expression for field {field_key!r} contains a literal ellipsis placeholder; "
            "provide the complete function text or generate it through value_expressions_json."
        )

    if not _EXPECTED_FUNCTION_PATTERN.search(expression):
        warnings.append(
            "JavaScript expression for field "
            f"{field_key!r} is not a function(model, sourceParams, schema, unused, cfg) "
            "expression; verify the SmartCMP runtime contract before use."
        )

    for pattern, label in _RISK_PATTERNS:
        if re.search(pattern, expression):
            warnings.append(
                f"JavaScript expression for field {field_key!r} contains {label}; "
                "review the trust boundary before use."
            )

    return warnings


def build_model_projection_expression(
    fields: list[dict[str, Any]],
    *,
    target_field_key: str | None = None,
    output_type: str = "string",
) -> str:
    """Build a one-line SmartCMP mock expression that projects model values.

    This is intentionally generic: callers decide which model paths are read
    and which output labels are emitted. The generated JavaScript handles common
    SmartCMP value shapes, including strings, objects, and arrays.

    Args:
        fields: Ordered flat output specs with unique `label` values and
            `path` string values.

    Returns:
        A single-line JavaScript `function(model, sourceParams, schema, unused, cfg)`.

    Raises:
        ValueError: If no usable field specs are provided.
    """
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
    """Build a one-line SmartCMP mock expression from a JSON composition spec.

    The composition spec is data, not JavaScript. Objects and arrays describe
    the returned JSON structure. Reserved source references are resolved at
    runtime:

    - `{"$path": "owners"}` reads and text-normalizes a model path.
    - `{"$concat": [...]}` concatenates composed child values as a string.

    Args:
        compose_spec: JSON-serializable structure describing the output value.

    Returns:
        A single-line JavaScript `function(model, sourceParams, schema, unused, cfg)`.
    """
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
        "var composed = compose(spec); "
        "var result = hasValue(composed) ? resultValue(composed) : emptyValue(); "
        f"var targetKey = {target_literal}; "
        "if (model && typeof model === 'object') model[targetKey] = result; "
        "function findInput() { try { if (typeof document === 'undefined') return null; function ngMatch(v) { return v === targetKey || String(v).split('.').pop() === targetKey || String(v).indexOf('[\\'' + targetKey + '\\']') >= 0 || String(v).indexOf('[\"' + targetKey + '\"]') >= 0; } var els = document.querySelectorAll('input,textarea,select'); for (var i = 0; i < els.length; i++) { var el = els[i], n = el.getAttribute('name') || '', id = el.getAttribute('id') || '', ng = el.getAttribute('ng-model') || '', fc = el.getAttribute('formcontrolname') || '', dk = '', box = el.closest && el.closest('[data-key]'); if (box) dk = box.getAttribute('data-key') || ''; if (n === targetKey || id === targetKey || fc === targetKey || dk === targetKey || ngMatch(ng)) return el; } } catch (e) {} return null; } "
        "function write(v) { if (model && typeof model === 'object') model[targetKey] = v; try { var el = findInput(); if (el) { var view = displayText(v); if ('value' in el) { if (el.value !== view) el.value = view; } else if (el.textContent !== view) el.textContent = view; el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); if (typeof window !== 'undefined' && window.angular) { var ng = window.angular.element(el).controller('ngModel'); if (ng) { ng.$setViewValue(v); if (ng.$render) ng.$render(); } var sc = window.angular.element(el).scope(); if (sc && sc.$applyAsync) sc.$applyAsync(); } } } catch (e) {} return v; } "
        "try { if (typeof window !== 'undefined') { var timerKey = '__smartcmp_value_expr_' + targetKey; if (window[timerKey]) clearInterval(window[timerKey]); window[timerKey] = setInterval(function() { var next = compose(spec); write(hasValue(next) ? resultValue(next) : emptyValue()); }, 500); } } catch (e) {} "
        "return write(result); }"
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
        "function displayText(v) { if (v == null) return ''; return typeof v === 'string' ? v : JSON.stringify(v); } "
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
