# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Validate SmartCMP Schema Form JSON for common form-designer failure modes.

This is a focused safety linter for renderer-breaking form output,
not a full JSON Schema validator.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unicodedata
from typing import Any


META_START = "##REQUEST_FORM_VALIDATION_META_START##"
META_END = "##REQUEST_FORM_VALIDATION_META_END##"
FULLWIDTH_COLON_NAMES = {"FULLWIDTH COLON"}
DISPLAY_JOIN_SEPARATOR_NAMES = {"FULLWIDTH COMMA", "IDEOGRAPHIC COMMA"}


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    # Build one structured validation issue.
    return {"code": code, "path": path, "message": message}


def _widget_id(field: dict[str, Any]) -> str:
    # Read widget.id defensively from a field definition.
    widget = field.get("widget")
    return str(widget.get("id", "") if isinstance(widget, dict) else "").strip()


def _has_non_rendering_css_class(field: dict[str, Any]) -> bool:
    # Treat common CSS hiding classes as non-rendering form fields.
    hidden_classes = {"hidden", "d-none"}
    for key in ("inputClass", "labelClass", "className"):
        raw = field.get(key)
        if not isinstance(raw, str):
            continue
        classes = {item.strip() for item in re.split(r"\s+", raw) if item.strip()}
        if hidden_classes.intersection(classes):
            return True
    return False


def _field_config(field: dict[str, Any]) -> dict[str, Any]:
    # Return config only when it is object-shaped.
    config = field.get("config")
    return config if isinstance(config, dict) else {}


def _nested_bool(container: dict[str, Any], outer_key: str, inner_key: str) -> Any:
    # Read a nested boolean-like setting without assuming the parent exists.
    outer = container.get(outer_key)
    if not isinstance(outer, dict):
        return None
    return outer.get(inner_key)


def _is_boolean_string(value: Any) -> bool:
    # Detect accidental string booleans in labels or section names.
    return isinstance(value, str) and value.strip().lower() in {"true", "false"}


def _function_strings(field: dict[str, Any]) -> list[tuple[str, str]]:
    # Only JavaScript hook locations are linted; API URLs and model paths are left alone.
    config = _field_config(field)
    values: list[tuple[str, str]] = []
    change_event = config.get("changeEvent")
    if isinstance(change_event, str) and change_event.strip():
        values.append(("config.changeEvent", change_event))
    value_config = config.get("value")
    if isinstance(value_config, dict):
        custom_function = value_config.get("customFunction")
        if isinstance(custom_function, str) and custom_function.strip():
            values.append(("config.value.customFunction", custom_function))
        mock_expression = value_config.get("expression")
        source = str(value_config.get("source", "")).lower()
        method = str(value_config.get("method", "")).lower()
        expression_is_function = (
            isinstance(mock_expression, str)
            and mock_expression.strip().startswith("function")
        )
        if isinstance(mock_expression, str) and mock_expression.strip() and (
            (source == "mock" and method == "mock") or expression_is_function
        ):
            values.append(("config.value.expression", mock_expression))
    return values


def _has_non_newline_control_character(script: str) -> bool:
    # Reject hidden control characters while allowing line endings to be reported separately.
    return any(ord(ch) < 32 and ch not in "\n\r" for ch in script)


def _has_malformed_try_block(script: str) -> bool:
    # Catch try blocks that cannot run because catch/finally is missing.
    return bool(re.search(r"\btry\s*\{", script)) and not bool(
        re.search(r"\b(?:catch|finally)\b", script)
    )


def _has_named_character(script: str, names: set[str]) -> bool:
    # Detect non-ASCII runtime punctuation without keeping it in this source file.
    return any(unicodedata.name(ch, "") in names for ch in script)


def _has_display_join_separator(script: str) -> bool:
    return "," in script or _has_named_character(script, DISPLAY_JOIN_SEPARATOR_NAMES)


def _has_display_pair_separator(script: str) -> bool:
    return ":" in script or _has_named_character(script, FULLWIDTH_COLON_NAMES)


def _compile_function_syntax_error(script: str) -> str:
    # Use Node as a cheap parser check for the same function strings the browser evaluates.
    code = (
        "let src='';"
        "process.stdin.setEncoding('utf8');"
        "process.stdin.on('data',c=>src+=c);"
        "process.stdin.on('end',()=>{try{"
        "const fn=new Function('return ('+src+')')();"
        "if(typeof fn!=='function')throw new Error('not a function');"
        "}catch(e){console.error(e&&e.message?e.message:String(e));process.exit(1);}});"
    )
    try:
        result = subprocess.run(
            ["node", "-e", code],
            input=script,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"JavaScript function compilation could not run: {type(exc).__name__}."
    if result.returncode == 0:
        return ""
    return (result.stderr or result.stdout or "JavaScript function syntax is invalid.").strip()


def _function_params(script: str) -> list[str]:
    # Extract top-level function parameter names for signature checks.
    match = re.search(r"\bfunction(?:\s+\w+)?\s*\(([^)]*)\)", script)
    if not match:
        return []
    return [part.strip() for part in match.group(1).split(",")]


def _has_value_expression_change_event_signature(script: str) -> bool:
    # Detect changeEvent-style parameters used in a mock value expression.
    params = [part.lower() for part in _function_params(script)]
    return (
        len(params) >= 4
        and params[0] in {"itemid", "item", "id"}
        and params[1] == "schema"
        and params[2] in {"model", "m"}
        and params[3] in {"sourceparams", "sourceconfigparamter", "p"}
    )


def _uses_fixed_name_sourceparams(script: str) -> bool:
    # Fixed request-context fields are no longer inferred by the form designer.
    return False


def _looks_like_fixed_context_template(script: str) -> bool:
    # Fixed request-context templates are no longer generated.
    return False


def _missing_last_non_empty_context_cache(script: str) -> bool:
    # Ensure auto-sync hooks remember the last non-empty context value.
    if not _looks_like_fixed_context_template(script) or "setInterval" not in script:
        return False
    cache_markers = (
        "state.values",
        "lastNonEmpty",
        "last_non_empty",
        "nonEmptyCache",
        "contextValues",
    )
    return not any(marker in script for marker in cache_markers)


def _missing_empty_context_write_guard(script: str) -> bool:
    # Ensure auto-sync hooks avoid writing unresolved empty context values.
    if not _looks_like_fixed_context_template(script) or "setInterval" not in script:
        return False
    guard_markers = (
        "lastGood",
        "existing()",
        "if(!v)return",
        "if (!v) return",
    )
    return not any(marker in script for marker in guard_markers)


def _has_catalog_display_object_string(script: str) -> bool:
    # Detect catalog composed values built as display text instead of JSON.
    return bool(
        "__smartcmp_catalog_auto_sync_" in script
        and "JSON.stringify" not in script
        and "FIELDS" in script
        and re.search(r"parts\s*\.\s*join\s*\(", script)
        and _has_display_join_separator(script)
        and _has_display_pair_separator(script)
    )


def _looks_like_catalog_auto_sync_expression(script: str) -> bool:
    # Identify generated catalog context auto-sync expressions.
    return "__smartcmp_catalog_auto_sync_" in script and "FIELDS" in script


def _normalize_key_like(value: str) -> str:
    # Normalize labels and keys before comparing them.
    return "".join(ch for ch in value.lower() if ch.isalnum() or ch in "_-")


def _looks_like_backend_key(value: str) -> bool:
    # Heuristically identify technical backend keys.
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_@:\-]*", value):
        return False
    if re.search(r"[A-Z]", value):
        return True
    if "_" in value or value.endswith("Id") or value.endswith("_id"):
        return True
    return bool(re.search(r"[a-z][A-Z]", value))


def _catalog_output_labels_using_backend_keys(script: str) -> list[str]:
    # FIELDS entries are [backendKey, displayLabel]; submitted JSON should keep the label.
    if "ALLOW_BACKEND_LABELS=true" in script:
        return []
    if "__smartcmp_catalog_auto_sync_" not in script or "FIELDS" not in script:
        return []
    leaked: list[str] = []
    for key, label in re.findall(
        r"\[\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\]",
        script,
    ):
        if _normalize_key_like(label) != _normalize_key_like(key):
            continue
        if _looks_like_backend_key(key):
            leaked.append(label)
    return sorted(set(leaked))


def _has_request_context_display_object_string(script: str) -> bool:
    # Detect request-context composed values built as display text.
    return bool(
        "__smartcmp_auto_sync_" in script
        and "JSON.stringify" not in script
        and "FIELDS" in script
        and re.search(r"parts\s*\.\s*join\s*\(", script)
        and _has_display_join_separator(script)
        and _has_display_pair_separator(script)
    )


def _has_display_formatted_composed_string(script: str) -> bool:
    # Display-style "{label:value}" strings submit as plain text, not JSON strings.
    if "JSON.stringify" in script or not _has_display_pair_separator(script):
        return False
    return bool(
        re.search(r"['\"]\s*\{[^'\"]*:", script)
        or re.search(r"['\"][^'\"]*:['\"]\s*\+", script)
        or re.search(r"\+\s*['\"]\s*,[^'\"]*:", script)
        or re.search(r"parts\s*\.\s*push\s*\(", script)
        or _has_named_character(script, FULLWIDTH_COLON_NAMES)
    )


def _referenced_model_keys(script: str) -> set[str]:
    # Collect model keys read or written by a hook string.
    keys = set(re.findall(r"\b(?:model|m)\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)\b", script))
    keys.update(
        re.findall(
            r"\b(?:model|m)\s*\[\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\]",
            script,
        )
    )
    return keys


def _assigns_model_key(script: str, key: str) -> bool:
    # Check whether a hook assigns the submitted backend key.
    escaped = re.escape(key)
    patterns = [
        rf"\bmodel\s*\[\s*['\"]{escaped}['\"]\s*\]\s*=",
        rf"\bm\s*\[\s*['\"]{escaped}['\"]\s*\]\s*=",
        rf"\bmodel\.{escaped}\s*=",
        rf"\bm\.{escaped}\s*=",
    ]
    if any(re.search(pattern, script) for pattern in patterns):
        return True
    key_var_patterns = [
        rf"\bvar\s+KEY\s*=\s*['\"]{escaped}['\"]",
        rf"\bKEY\s*=\s*['\"]{escaped}['\"]",
    ]
    return bool(
        any(re.search(pattern, script) for pattern in key_var_patterns)
        and re.search(r"\b(?:model|m)\s*\[\s*KEY\s*\]\s*=", script)
    )


def _reads_model_common_context(script: str) -> bool:
    # Names such as name or owner may be real catalog fields after resolution.
    return False


def _has_direct_only_common_sourceparams(script: str) -> bool:
    # The designer no longer treats name or owner as fixed request-context keys.
    return False


def _has_raw_display_id_fallback(script: str) -> bool:
    # Catalog-resolved keys may include ids; do not apply request-context rules.
    return False


def _has_empty_common_context_template(script: str) -> bool:
    # Detect common context templates that can fall back to empty strings.
    common_template_markers = ("name", "owner", "department")
    if not any(marker in script for marker in common_template_markers):
        return False

    empty_fallback = bool(
        re.search(r"return\s*['\"]{2}", script)
        or re.search(r"String\s*\(\s*[^)]*\|\|\s*['\"]{2}\s*\)", script)
        or re.search(r"\|\|\s*['\"]{2}", script)
    )
    if not empty_fallback:
        return False

    safe_markers = (
        "unresolved",
        "not found",
        "missing",
        "N/A",
        "n/a",
        "UNRESOLVED",
        "unknown",
        "Unknown",
        "document.querySelector",
        "XMLHttpRequest",
        "fetch(",
        "/platform-api/",
        "current-user-details",
    )
    return not any(marker in script for marker in safe_markers)


def _validate_schema_form(root: dict[str, Any]) -> list[dict[str, str]]:
    # Validate the schema shape and dynamic hook safety rules.
    issues: list[dict[str, str]] = []
    # Later checks assume a schema-first SmartCMP form with properties and fieldsets.
    if root.get("type") != "object":
        issues.append(_issue("invalid_root_type", "$.type", "Root type must be object."))

    properties = root.get("properties")
    if not isinstance(properties, dict) or not properties:
        return issues + [
            _issue("missing_properties", "$.properties", "Schema-only JSON must define properties.")
        ]

    fieldsets = root.get("fieldsets")
    if not isinstance(fieldsets, list):
        issues.append(_issue("missing_fieldsets", "$.fieldsets", "Schema-only JSON must define fieldsets."))
        fieldsets = []

    referenced_fields: set[str] = set()
    # Fieldsets are render contracts; unreferenced properties may never mount.
    for index, fieldset in enumerate(fieldsets):
        path = f"$.fieldsets[{index}]"
        if not isinstance(fieldset, dict):
            issues.append(_issue("invalid_fieldset", path, "Each fieldset must be an object."))
            continue
        for label_key in ("title", "name"):
            if _is_boolean_string(fieldset.get(label_key)):
                issues.append(
                    _issue(
                        "boolean_string_fieldset_title",
                        f"{path}.{label_key}",
                        "Fieldset title/name looks like a boolean argument; pass a real section title or omit it.",
                    )
                )
        fields = fieldset.get("fields")
        if not isinstance(fields, list) or not fields:
            issues.append(
                _issue(
                    "invalid_fieldset_fields",
                    path,
                    "Each fieldset must define a non-empty fields array for renderable inputs.",
                )
            )
            continue
        for field_name in fields:
            if not isinstance(field_name, str) or not field_name.strip():
                issues.append(
                    _issue(
                        "invalid_fieldset_field_ref",
                        path,
                        "Fieldset fields entries must be non-empty property keys.",
                    )
                )
                continue
            referenced_fields.add(field_name)
            if field_name not in properties:
                issues.append(
                    _issue(
                        "unknown_fieldset_field_ref",
                        path,
                        f"Fieldset references unknown property `{field_name}`.",
                    )
                )

    for key, field in properties.items():
        if not isinstance(field, dict):
            continue
        widget_id = _widget_id(field)
        is_hidden = bool(field.get("hidden")) or widget_id == "hidden" or _has_non_rendering_css_class(field)
        functions = _function_strings(field)
        field_config = _field_config(field)
        modification = field_config.get("modification")
        allow_in_request = (
            modification.get("allowInRequest")
            if isinstance(modification, dict) and "allowInRequest" in modification
            else None
        )
        if key != "schemaFormValid" and not is_hidden:
            # Visible fields need designer-style metadata to mount predictably.
            required_render_keys = {
                "id": field.get("id"),
                "type": field.get("type"),
                "widget.id": widget_id,
                "inputClass": field.get("inputClass"),
                "index": field.get("index"),
                "title": field.get("title"),
            }
            for render_key, render_value in required_render_keys.items():
                if render_value in (None, ""):
                    issues.append(
                        _issue(
                            "missing_visible_field_render_key",
                            f"$.properties.{key}",
                            f"Visible business fields must define `{render_key}` to render reliably.",
                        )
                    )
            if _nested_bool(field_config, "visibility", "allowInRequest") is None:
                issues.append(
                    _issue(
                        "missing_request_visibility_flag",
                        f"$.properties.{key}.config.visibility",
                        "Visible business fields must set config.visibility.allowInRequest explicitly.",
                    )
                )
            if _nested_bool(field_config, "modification", "allowInRequest") is None:
                issues.append(
                    _issue(
                        "missing_request_modification_flag",
                        f"$.properties.{key}.config.modification",
                        "Visible business fields must set config.modification.allowInRequest explicitly.",
                    )
                )
        if key != "schemaFormValid" and is_hidden and functions:
            # Hidden dynamic hooks are unreliable because no input may be mounted.
            issue_code = "hidden_refresh_trigger" if any(name.endswith("changeEvent") for name, _ in functions) else "hidden_dynamic_field"
            issues.append(
                _issue(
                    issue_code,
                    f"$.properties.{key}",
                    "Dynamic fields must be visible; hidden fields do not provide a reliable render or refresh path.",
                )
            )
        if functions and (allow_in_request is False or field.get("readOnly") is True or field.get("readonly") is True):
            issues.append(
                _issue(
                    "nonmodifiable_dynamic_field",
                    f"$.properties.{key}",
                    "Fields that own dynamic hooks must allow request modification so changeEvent can fire.",
                )
            )

        for location, script in functions:
            path = f"$.properties.{key}.{location}"
            value_config = field_config.get("value") if isinstance(field_config.get("value"), dict) else {}
            value_source = str(value_config.get("source", "")).lower()
            value_method = str(value_config.get("method", "")).lower()
            # Keep function strings single-line for the SmartCMP/Angular renderer.
            if "\n" in script or "\r" in script:
                issues.append(_issue("multiline_function", path, "Function strings must stay on one physical line."))
            if _has_non_newline_control_character(script):
                issues.append(
                    _issue(
                        "control_character_function",
                        path,
                        "Function strings must not contain tabs or other control characters.",
                    )
                )
            if _has_malformed_try_block(script):
                issues.append(
                    _issue(
                        "invalid_function_syntax",
                        path,
                        "JavaScript try blocks must include catch or finally.",
                    )
                )
            compile_error = _compile_function_syntax_error(script)
            if compile_error:
                issues.append(
                    _issue(
                        "invalid_function_syntax",
                        path,
                        f"JavaScript function string failed to compile: {compile_error}",
                    )
                )
            if location == "config.value.expression" and _has_value_expression_change_event_signature(script):
                issues.append(
                    _issue(
                        "wrong_value_expression_signature",
                        path,
                        "Mock value expressions must use function(model, sourceParams, schema, ...), not the changeEvent signature.",
                    )
                )
            if location == "config.value.expression" and (value_source != "mock" or value_method != "mock"):
                issues.append(
                    _issue(
                        "value_expression_missing_mock_source",
                        path,
                        "Function config.value.expression must set config.value.source and method to mock so the renderer executes it.",
                    )
                )
            materialized_catalog_source_keys = []
            if location == "config.value.expression" and _looks_like_catalog_auto_sync_expression(script):
                # Catalog source keys should be read from payload, not duplicated as visible fields.
                materialized_catalog_source_keys = sorted(
                    ref
                    for ref in (_referenced_model_keys(script) - {key})
                    if ref in properties
                    and _looks_like_backend_key(ref)
                    and not _assigns_model_key(script, ref)
                )
            if materialized_catalog_source_keys:
                issues.append(
                    _issue(
                        "catalog_source_field_materialized",
                        f"$.properties.{key}",
                        "Catalog lookup labels are source keys for the composed backend field; do not create visible source fields: "
                        + ", ".join(materialized_catalog_source_keys),
                    )
                )
            if _uses_fixed_name_sourceparams(script):
                issues.append(
                    _issue(
                        "fixed_name_sourceparams",
                        path,
                        "Request name is vm.deploymentObj.name or DOM/model fallback; sourceParams.name is not a fixed request field.",
                    )
                )
            if location == "config.value.expression" and _missing_last_non_empty_context_cache(script):
                issues.append(
                    _issue(
                        "missing_last_non_empty_context_cache",
                        path,
                        "Auto-sync expressions for fixed request context must retain the last non-empty value so temporary empty reads cannot overwrite correct values.",
                    )
                )
            if location == "config.value.expression" and _missing_empty_context_write_guard(script):
                issues.append(
                    _issue(
                        "missing_empty_context_write_guard",
                        path,
                        "Auto-sync expressions must not write unresolved fixed-context templates; keep the previous good value when the current read is empty.",
                    )
                )
            if location == "config.value.expression" and _has_catalog_display_object_string(script):
                issues.append(
                    _issue(
                        "catalog_composed_value_not_json_string",
                        path,
                        "Catalog composed backend values must be JSON.stringify object strings, not display-formatted `{label:value}` strings.",
                    )
                )
            catalog_backend_labels = _catalog_output_labels_using_backend_keys(script)
            if location == "config.value.expression" and catalog_backend_labels:
                issues.append(
                    _issue(
                        "catalog_output_label_uses_backend_key",
                        path,
                        "Catalog composed output labels must preserve the user's display labels; do not use backend keys as JSON object labels: "
                        + ", ".join(catalog_backend_labels),
                    )
                )
            if location == "config.value.expression" and _has_request_context_display_object_string(script):
                issues.append(
                    _issue(
                        "request_context_composed_value_not_json_string",
                        path,
                        "Request-context composed backend values must be JSON.stringify object strings, not display-formatted `{label:value}` strings.",
                    )
                )
            if (
                not _has_catalog_display_object_string(script)
                and not _has_request_context_display_object_string(script)
                and _has_display_formatted_composed_string(script)
            ):
                issues.append(
                    _issue(
                        "composed_value_not_json_string",
                        path,
                        "Composed backend values must be JSON.stringify object strings, not display-formatted `{label:value}` strings.",
                    )
                )
            if "return" not in script:
                issues.append(_issue("missing_return", path, "Dynamic functions must return the computed value."))
            if not _assigns_model_key(script, key):
                assigned_other = bool(re.search(r"\b(?:model|m)(?:\.|\s*\[)", script))
                if location in ("config.value.customFunction", "config.value.expression") or not assigned_other:
                    issues.append(
                        _issue(
                            "missing_model_assignment",
                            path,
                            "Dynamic functions must assign the submitted backend key in the model.",
                        )
                    )
            if _reads_model_common_context(script):
                issues.append(
                    _issue(
                        "model_common_context_read",
                        path,
                        "Do not read common request context from model.name or model.owner in new forms.",
                    )
                )
            if _has_direct_only_common_sourceparams(script):
                issues.append(
                    _issue(
                        "direct_only_common_sourceparams",
                        path,
                        "Do not rely only on sourceParams.name/sourceParams.owner; use layered context resolution.",
                    )
                )
            if _has_raw_display_id_fallback(script):
                issues.append(
                    _issue(
                        "raw_display_id_fallback",
                        path,
                        "Display strings must not concatenate raw owner/project/business-group ids without resolving them to text.",
                    )
                )
            if _has_empty_common_context_template(script):
                issues.append(
                    _issue(
                        "empty_common_context_template",
                        path,
                        "Common request context templates must not fall back to empty values; add verified DOM/API resolution or an explicit non-empty unresolved marker.",
                    )
                )
        if key != "schemaFormValid" and fieldsets and key not in referenced_fields:
            issues.append(
                _issue(
                    "unrendered_property",
                    f"$.properties.{key}",
                    "Visible business properties must be referenced by a fieldset fields array to render inputs.",
                )
            )
    return issues


def validate_form_json(value: str) -> dict[str, Any]:
    # Parse JSON text and run SmartCMP-specific validation rules.
    try:
        root = json.loads(value)
    except json.JSONDecodeError as exc:
        return {
            "valid": False,
            "issues": [
                _issue("invalid_json", "$", f"JSON.parse failed at line {exc.lineno}, column {exc.colno}.")
            ],
        }
    if not isinstance(root, dict):
        return {
            "valid": False,
            "issues": [_issue("invalid_root", "$", "Root JSON value must be an object.")],
        }
    issues = _validate_schema_form(root)
    return {"valid": not issues, "issues": issues}


def main(argv: list[str] | None = None) -> int:
    # CLI entry point used by the form-designer-agent validation tool.
    argv = argv if argv is not None else sys.argv[1:]
    source = argv[0] if argv else sys.stdin.read()
    result = validate_form_json(source)
    if result["valid"]:
        print("[SUCCESS] Schema form JSON validated")
    else:
        print("[ERROR] Schema form JSON validation failed")
        for issue in result.get("issues", []):
            print(f"- {issue['code']} @ {issue['path']}: {issue['message']}")
    print(META_START, file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
    print(META_END, file=sys.stderr)
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    sys.exit(main())
