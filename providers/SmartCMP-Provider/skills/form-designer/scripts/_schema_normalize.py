#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Normalize SmartCMP Angular form schema JSON."""

from __future__ import annotations

import copy
import re
from typing import Any


class SchemaNormalizationError(ValueError):
    """Raised when a schema cannot be interpreted as a JSON object."""


_UNICODE_ESCAPE_RE = re.compile(r"(?<!\\)\\u([0-9a-fA-F]{4})")
_STRICT_DISPLAY_OUTPUT_KEYS = {
    "业务组": {"catalogServiceRequest.exts.businessGroup.name"},
    "所有者": {"catalogServiceRequest.exts.owner.name"},
    "应用系统": {"catalogServiceRequest.exts.project.name"},
    "名称": {"name"},
}


def normalize_schema(schema: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Return a normalized SmartCMP Angular form schema.

    The normalizer repairs deterministic structural issues only. It preserves
    unknown keys and reports changes through warnings so that the LLM and user
    can review the result before copying it into CMP.

    Args:
        schema: Draft or existing SmartCMP form schema.

    Returns:
        A tuple of `(normalized_schema, warnings)`.

    Raises:
        SchemaNormalizationError: If `schema` is not a JSON object.
    """
    if not isinstance(schema, dict):
        raise SchemaNormalizationError("Schema must be a JSON object.")

    warnings: list[str] = []
    normalized = copy.deepcopy(schema)

    if "properties" not in normalized and isinstance(normalized.get("schema"), dict):
        normalized = copy.deepcopy(normalized["schema"])
        warnings.append(
            "Unwrapped top-level schema container; return the SmartCMP schema object directly instead of {'schema': ...}."
        )

    if normalized.get("type") != "object":
        previous = normalized.get("type")
        normalized["type"] = "object"
        warnings.append(f"Set root type to object (was {previous!r}).")

    properties = normalized.get("properties")
    if not isinstance(properties, dict):
        normalized["properties"] = {}
        warnings.append("Created missing root properties object.")
        properties = normalized["properties"]

    widget = normalized.get("widget")
    if not isinstance(widget, dict):
        normalized["widget"] = {"id": "object"}
        warnings.append("Added root widget.id=object.")
    elif not widget.get("id"):
        widget["id"] = "object"
        warnings.append("Added root widget.id=object.")

    if "fieldsets" in normalized and not isinstance(normalized.get("fieldsets"), list):
        normalized["fieldsets"] = []
        warnings.append("Replaced invalid root fieldsets with an empty list.")

    for index, (field_key, field_value) in enumerate(properties.items()):
        properties[field_key] = _normalize_top_level_field(
            field_key,
            field_value,
            index,
            warnings,
        )

    _normalize_auto_sync_submission_shape(normalized, properties, warnings)

    return normalized, warnings


def _normalize_top_level_field(
    field_key: str,
    raw_field: Any,
    index: int,
    warnings: list[str],
) -> dict[str, Any]:
    if not isinstance(raw_field, dict):
        warnings.append(f"Replaced non-object field {field_key!r} with a string field.")
        raw_field = {"title": field_key}

    field = raw_field
    if not field.get("id"):
        field["id"] = field_key
        warnings.append(f"Added id for field {field_key!r}.")

    if not isinstance(field.get("index"), int):
        field["index"] = index
        warnings.append(f"Added numeric index for field {field_key!r}.")

    field_type = field.get("type")
    if not isinstance(field_type, str) or not field_type.strip():
        field["type"] = _infer_type(field)
        warnings.append(f"Added type={field['type']} for field {field_key!r}.")

    _normalize_widget(field, field_key, warnings)
    _normalize_visibility(field, field_key, warnings)

    if field.get("type") == "array":
        _normalize_array_field(field, field_key, warnings)

    return field


def _infer_type(field: dict[str, Any]) -> str:
    widget = field.get("widget") if isinstance(field.get("widget"), dict) else {}
    widget_id = str(widget.get("id") or "").strip()
    if widget_id == "number":
        return "number"
    if field.get("items") is not None or widget_id == "table-head":
        return "array"
    return "string"


def _normalize_widget(field: dict[str, Any], field_key: str, warnings: list[str]) -> None:
    widget = field.get("widget")
    if not isinstance(widget, dict):
        field["widget"] = {"id": _default_widget_for_field(field)}
        warnings.append(f"Added widget.id={field['widget']['id']} for field {field_key!r}.")
        return

    if not widget.get("id"):
        widget["id"] = _default_widget_for_field(field)
        warnings.append(f"Added widget.id={widget['id']} for field {field_key!r}.")
    else:
        # LLM drafts often use human-facing widget names. Normalize only aliases
        # with a deterministic SmartCMP equivalent, leaving unknown widgets intact.
        _normalize_widget_alias(field, field_key, warnings)

    _promote_select_keys_from_widget(field, field_key, warnings)


def _normalize_widget_alias(field: dict[str, Any], field_key: str, warnings: list[str]) -> None:
    widget = field.get("widget")
    if not isinstance(widget, dict):
        return

    widget_id = str(widget.get("id") or "").strip()
    if widget_id == "text":
        widget["id"] = "string"
        warnings.append(f"Changed widget.id=text to string for field {field_key!r}.")
    elif field.get("type") == "array" and widget_id in {"array", "table"}:
        widget["id"] = "table-head"
        warnings.append(
            f"Changed widget.id={widget_id} to table-head for array field {field_key!r}."
        )


def _promote_select_keys_from_widget(
    field: dict[str, Any],
    field_key: str,
    warnings: list[str],
) -> None:
    widget = field.get("widget")
    if not isinstance(widget, dict):
        return

    for key in ("selectDatas", "value"):
        if key in widget and key not in field:
            # SmartCMP schemas commonly keep select metadata at field level. Copy
            # it out for compatibility, but do not overwrite intentional fields.
            field[key] = copy.deepcopy(widget[key])
            warnings.append(
                f"Copied widget.{key} to field-level {key} for field {field_key!r}."
            )


def _default_widget_for_field(field: dict[str, Any]) -> str:
    field_type = field.get("type")
    if field_type == "array":
        return "table-head"
    if field_type == "number":
        return "number"
    return "string"


def _normalize_visibility(field: dict[str, Any], field_key: str, warnings: list[str]) -> None:
    config = field.get("config")
    if not isinstance(config, dict):
        config = {}
        field["config"] = config
        warnings.append(f"Added config object for field {field_key!r}.")

    visibility = config.get("visibility")
    if not isinstance(visibility, dict):
        visibility = {}
        config["visibility"] = visibility
        warnings.append(f"Added config.visibility for field {field_key!r}.")

    if "allowInRequest" not in visibility:
        visibility["allowInRequest"] = True
        warnings.append(f"Added allowInRequest=true for field {field_key!r}.")
    if "allowInApproval" not in visibility:
        visibility["allowInApproval"] = True
        warnings.append(f"Added allowInApproval=true for field {field_key!r}.")


def _normalize_auto_sync_submission_shape(
    schema: dict[str, Any],
    properties: dict[str, Any],
    warnings: list[str],
) -> None:
    """Normalize mock auto-sync fields so SmartCMP renders and submits them.

    Args:
        schema: Root SmartCMP schema object being normalized.
        properties: Root schema properties dictionary.
        warnings: Mutable warning list describing deterministic repairs.
    """
    auto_sync_keys = [
        field_key
        for field_key, field in properties.items()
        if _is_mock_auto_sync_field(field)
    ]
    if not auto_sync_keys:
        return

    for field_key in auto_sync_keys:
        field = properties[field_key]
        _normalize_mock_auto_sync_field(field_key, field, warnings)

    if "schemaFormValid" not in properties:
        properties["schemaFormValid"] = {
            "hidden": True,
            "type": "boolean",
            "default": True,
            "condition": "1 === 2",
            "widget": {"id": "hidden"},
        }
        warnings.append("Added schemaFormValid hidden companion field.")

    fieldsets = schema.get("fieldsets")
    if not isinstance(fieldsets, list) or not fieldsets:
        schema["fieldsets"] = [
            {
                "id": f"fieldset-{auto_sync_keys[0]}",
                "title": schema.get("title") or "",
                "description": "",
                "name": schema.get("title") or "",
                "fields": auto_sync_keys + ["schemaFormValid"],
            }
        ]
        warnings.append("Added fieldsets for mock auto-sync submission fields.")
        return

    present = set()
    for fieldset in fieldsets:
        if not isinstance(fieldset, dict):
            continue
        fields = fieldset.get("fields")
        if isinstance(fields, list):
            present.update(fields)
    missing = [field_key for field_key in auto_sync_keys if field_key not in present]
    if "schemaFormValid" not in present:
        missing.append("schemaFormValid")
    if missing:
        first_fieldset = next((item for item in fieldsets if isinstance(item, dict)), None)
        if first_fieldset is None:
            schema["fieldsets"] = [
                {
                    "id": f"fieldset-{auto_sync_keys[0]}",
                    "title": schema.get("title") or "",
                    "description": "",
                    "name": schema.get("title") or "",
                    "fields": auto_sync_keys + ["schemaFormValid"],
                }
            ]
        else:
            fields = first_fieldset.get("fields")
            if not isinstance(fields, list):
                fields = []
                first_fieldset["fields"] = fields
            fields.extend(missing)
        warnings.append("Registered mock auto-sync fields in fieldsets.")


def _is_mock_auto_sync_field(field: Any) -> bool:
    """Return whether a field uses a mock function value expression.

    Args:
        field: Candidate SmartCMP field definition.

    Returns:
        True when the field has a mock value expression function.
    """
    if not isinstance(field, dict):
        return False
    value = _field_value_config(field)
    if not isinstance(value, dict):
        return False
    expression = value.get("expression")
    return (
        value.get("source") == "mock"
        and value.get("method") == "mock"
        and isinstance(expression, str)
        and expression.strip().startswith("function")
        and (
            _has_hidden_auto_sync_shape(field)
            or _has_auto_sync_expression_intent(expression)
        )
    )


def _has_hidden_auto_sync_shape(field: dict[str, Any]) -> bool:
    """Return whether a field is shaped like a hidden submit sync field.

    Args:
        field: SmartCMP field definition.

    Returns:
        True when the field uses the hidden/condition pattern for submit sync.
    """
    widget = field.get("widget")
    return (
        field.get("hidden") is True
        or "condition" in field
        or (isinstance(widget, dict) and widget.get("id") == "hidden")
    )


def _has_auto_sync_expression_intent(expression: str) -> bool:
    """Return whether an expression is meant to build a submit value.

    Args:
        expression: JavaScript function string from `config.value.expression`.

    Returns:
        True when the expression has known submit-sync output markers.
    """
    return (
        "CATALOG_CONTEXT_SYNC_TEMPLATE_V1" in expression
        or "FIELD_SPECS" in expression
        or "AUTO_SYNC_PENDING" in expression
        or "JSON.stringify(out)" in expression
        or re.search(r"\bparts\.join\s*\(", expression) is not None
        or re.search(r"return\s*['\"]\{", expression) is not None
    )


def _field_value_config(field: dict[str, Any]) -> dict[str, Any] | None:
    """Find the dynamic value config for a SmartCMP field.

    Args:
        field: SmartCMP field definition.

    Returns:
        The `config.value` object, a legacy field-level value object, or None.
    """
    config = field.get("config")
    if isinstance(config, dict) and isinstance(config.get("value"), dict):
        return config["value"]
    value = field.get("value")
    if isinstance(value, dict) and value.get("source") == "mock":
        return value
    return None


def _normalize_mock_auto_sync_field(
    field_key: str,
    field: dict[str, Any],
    warnings: list[str],
) -> None:
    """Repair one mock auto-sync field for request-time submission.

    Args:
        field_key: Root schema property key for the field.
        field: Mutable SmartCMP field definition.
        warnings: Mutable warning list describing deterministic repairs.
    """
    config = field.setdefault("config", {})
    if not isinstance(config, dict):
        config = {}
        field["config"] = config

    value = _field_value_config(field)
    if isinstance(value, dict) and field.get("value") is value:
        config["value"] = value
        field.pop("value", None)
        warnings.append(f"Moved field-level value to config.value for field {field_key!r}.")

    if field.get("type") != "string":
        field["type"] = "string"
        warnings.append(f"Changed mock auto-sync field {field_key!r} type to string.")

    expression = value.get("expression") if isinstance(value, dict) else None
    if isinstance(expression, str):
        decoded_expression = _decode_printable_non_ascii_unicode_escapes(expression)
        if decoded_expression != expression:
            value["expression"] = decoded_expression
            warnings.append(
                f"Decoded printable non-ASCII Unicode escape sequences in mock auto-sync expression for field {field_key!r}."
            )
        expression = value.get("expression")
        if isinstance(expression, str):
            _warn_mock_auto_sync_expression_antipatterns(field_key, expression, warnings)

    widget = field.setdefault("widget", {})
    if not isinstance(widget, dict):
        widget = {}
        field["widget"] = widget
    if widget.get("id") == "hidden":
        widget["id"] = "string"
        warnings.append(f"Changed widget.id=hidden to string for mock auto-sync field {field_key!r}.")

    if not field.get("default") and not field.get("defaultValue"):
        field["default"] = "AUTO_SYNC_PENDING"
        warnings.append(f"Added AUTO_SYNC_PENDING default for field {field_key!r}.")

    field.setdefault("title", " ")
    field.setdefault("i18nTitle", {"zh": "", "en": ""})
    field.setdefault("inputClass", "form-control")
    field.setdefault("labelClass", "")
    field.setdefault("className", "")
    field["hideTitle"] = True
    field["hideTitleText"] = True
    field["notitle"] = True
    if "hidden" in field:
        field.pop("hidden", None)
        warnings.append(
            f"Removed hidden=true from mock auto-sync field {field_key!r} so the renderer creates its ngModel."
        )
    if "condition" in field:
        field.pop("condition", None)
        warnings.append(
            f"Removed condition from mock auto-sync field {field_key!r} so config.value.expression can execute."
        )

    visibility = config.setdefault("visibility", {})
    if isinstance(visibility, dict):
        visibility["allowInRequest"] = True
        visibility["allowInCatalog"] = False
        visibility["allowInApproval"] = False
    else:
        config["visibility"] = {
            "allowInRequest": True,
            "allowInCatalog": False,
            "allowInApproval": False,
        }

    config["modification"] = {
        "allowInRequest": True,
        "allowInCatalog": False,
        "allowInApproval": False,
    }


def _warn_mock_auto_sync_expression_antipatterns(
    field_key: str,
    expression: str,
    warnings: list[str],
) -> None:
    """Add warnings for fragile mock auto-sync JavaScript patterns.

    Args:
        field_key: Root schema property key for the field.
        expression: JavaScript function string from `config.value.expression`.
        warnings: Mutable warning list for reviewable issues.
    """
    compact = re.sub(r"\s+", " ", expression)

    if re.search(r"(^|[;,{=(\s])\.\.\.($|[;,) }\]\s])", expression):
        warnings.append(
            f"Mock auto-sync expression for field {field_key!r} contains a literal ellipsis placeholder; return the complete JavaScript function, not an abbreviated snippet."
        )

    if re.search(r"\bel\.value\s*\|\|.*selectedIndex", compact):
        warnings.append(
            f"Mock auto-sync expression for field {field_key!r} should read selected option text before el.value for DOM select controls."
        )

    if re.search(r"interval[_-]?set", expression, flags=re.IGNORECASE):
        warnings.append(
            f"Mock auto-sync expression for field {field_key!r} uses a one-time interval-set flag; clear and recreate the interval from the current invocation."
        )

    if "$parent" in expression and "catalog-form" not in expression and "[ng-controller]" not in expression:
        warnings.append(
            f"Mock auto-sync expression for field {field_key!r} has a narrow roots helper; start from sourceParams/schema/cfg/model and Angular catalog scopes."
        )

    if "[ng-model*" in expression and "[name=" not in expression:
        warnings.append(
            f"Mock auto-sync expression for field {field_key!r} should find the target input by name or id before ng-model substring selectors."
        )

    if re.search(
        r"roots\s*:\s*function[\s\S]*?querySelectorAll\(['\"]catalog-form[\s\S]*?if\s*\(\s*iso\s*\)[^;]*;\s*\}\}\s*catch\s*\(",
        expression,
    ):
        warnings.append(
            f"Mock auto-sync expression for field {field_key!r} has a malformed roots helper try/catch block; validate the one-line JavaScript function before returning it."
        )

    if (
        "valueOf:function" in expression
        and "rs[i]&&rs[i].params" not in expression
        and "rs[i].params" not in expression
        and ".genericRequest&&rs[i].genericRequest.processForm" not in expression
    ):
        warnings.append(
            f"Mock auto-sync expression for field {field_key!r} should scan params/resourceBundleParams/genericRequest.processForm for every root, not only top-level sourceParams."
        )

    if re.search(r"byLabel\s*:\s*function\s*\(\s*roots\s*,\s*labels\s*\)", expression):
        warnings.append(
            f"Mock auto-sync expression for field {field_key!r} byLabel helper should query rendered form blocks by label text, not just inspect root object keys."
        )

    if (
        "FIELD_SPECS" in expression
        and re.search(r"keys\s*:\s*\[[^\]]*['\"][^'\"]+\.[^'\"]+['\"]", expression)
        and "String(k).split('.')" not in expression
    ):
        warnings.append(
            f"Mock auto-sync expression for field {field_key!r} has Dot-path FIELD_SPECS keys but does not resolve dot paths by walking object properties."
        )

    if re.search(r"querySelector\s*\(\s*['\"]select,input,textarea", expression):
        warnings.append(
            f"Mock auto-sync expression for field {field_key!r} should read visible selected text before input or textarea values in DOM select widgets."
        )

    if (
        "FIELD_SPECS" in expression
        and any(token in expression for token in ("owners", "Owners"))
        and "Array.isArray(v)" not in expression
    ):
        warnings.append(
            f"Mock auto-sync expression for field {field_key!r} should handle array values such as owners/Owners before object cleanup."
        )

    non_fixed_field_spec_keys = _non_fixed_display_field_spec_keys(expression)
    if non_fixed_field_spec_keys:
        warnings.append(
            f"Mock auto-sync expression for field {field_key!r} uses non-fixed display keys ({', '.join(non_fixed_field_spec_keys)}); for service-catalog display outputs use the fixed catalog-context display paths only and rely on DOM label fallback for renderer variation."
        )

    if (
        "querySelectorAll" in expression
        and "angular.element(nodes[i])" in expression
        and "for(var i=0;i<nodes.length;i++){try{" not in expression
    ):
        warnings.append(
            f"Mock auto-sync expression for field {field_key!r} roots helper should catch DOM node errors per node so one failed scope lookup does not abort scanning."
        )

    if (
        "infoblox_ip_attr" in expression
        and "APP_OUTPUT_KEY" in expression
        and "OWNER_OUTPUT_KEY" in expression
        and "FIELD_SPECS" not in expression
    ):
        warnings.append(
            f"Mock auto-sync expression for field {field_key!r} appears to copy test-ip-form.json verbatim; adapt KEY/output labels and FIELD_SPECS for the target service-catalog fields."
        )

    if _has_catalog_template_placeholders(expression):
        warnings.append(
            f"Mock auto-sync expression for field {field_key!r} still contains placeholder FIELD_SPECS entries; replace 字段A/字段B with the requested service-catalog output labels and fixed display paths."
        )

    if re.search(r"valueOf\s*=\s*function\s*\(\s*name\s*,\s*rootsList\s*\)", expression):
        warnings.append(
            f"Mock auto-sync expression for field {field_key!r} has a valueOf helper that ignores the requested output name; use per-output key lists from test-ip-form.json."
        )

    if "JSON.stringify" not in expression and (
        re.search(r"\bparts\.join\s*\(", expression)
        or re.search(r"return\s*['\"]\{", compact)
    ):
        warnings.append(
            f"Mock auto-sync expression for field {field_key!r} should submit a valid JSON string with JSON.stringify(out), not a manually concatenated pseudo-JSON string."
        )

    if (
        re.search(r"\bisUuid\s*\(", expression)
        and "resolveById" not in expression
        and any(token in expression for token in ("businessGroup", "BusinessGroup", "projects", "Projects", "owners", "Owners"))
    ):
        warnings.append(
            f"Mock auto-sync expression for field {field_key!r} should attempt ID-to-name resolution before rejecting UUID control values."
        )

    if (
        re.search(r"0-9a-f.*\{12\}", expression, flags=re.IGNORECASE)
        and any(token in expression for token in ("businessGroup", "BusinessGroup", "projects", "Projects", "owners", "Owners"))
    ):
        warnings.append(
            f"Mock auto-sync expression for field {field_key!r} should not reject UUID-like SmartCMP control values before resolving their display text."
        )


def _decode_printable_non_ascii_unicode_escapes(value: str) -> str:
    """Decode printable non-ASCII Unicode escapes in generated JavaScript.

    Args:
        value: JavaScript expression string.

    Returns:
        Expression string with printable non-ASCII escapes decoded.
    """
    def replace(match: re.Match[str]) -> str:
        codepoint = int(match.group(1), 16)
        if codepoint >= 0x80 and not 0xD800 <= codepoint <= 0xDFFF:
            return chr(codepoint)
        return match.group(0)

    return _UNICODE_ESCAPE_RE.sub(replace, value)


def _non_fixed_display_field_spec_keys(expression: str) -> list[str]:
    """Find FIELD_SPECS display keys outside the fixed catalog allowlist.

    Args:
        expression: JavaScript function string from `config.value.expression`.

    Returns:
        Non-allowlisted keys used for fixed display-label outputs.
    """
    found: list[str] = []
    if "FIELD_SPECS" not in expression:
        return found

    for output_label, allowed_keys in _STRICT_DISPLAY_OUTPUT_KEYS.items():
        for field_spec_source in _field_spec_sources(expression):
            if not re.search(rf"output\s*:\s*['\"]{re.escape(output_label)}['\"]", field_spec_source):
                continue
            keys_match = re.search(r"keys\s*:\s*\[([^\]]*)\]", field_spec_source)
            if not keys_match:
                continue
            keys_source = keys_match.group(1)
            for key in re.findall(r"['\"]([^'\"]+)['\"]", keys_source):
                if key not in allowed_keys and key not in found:
                    found.append(key)

    return found


def _has_catalog_template_placeholders(expression: str) -> bool:
    """Return whether a catalog sync expression still has template placeholders.

    Args:
        expression: JavaScript function string from `config.value.expression`.

    Returns:
        True when placeholder FIELD_SPECS entries such as 字段A remain.
    """
    if "CATALOG_CONTEXT_SYNC_TEMPLATE_V1" not in expression or "FIELD_SPECS" not in expression:
        return False
    for field_spec_source in _field_spec_sources(expression):
        if re.search(r"output\s*:\s*['\"]字段[ABC]['\"]", field_spec_source):
            return True
        if re.search(r"state\s*:\s*['\"]field[ABC]['\"]", field_spec_source):
            return True
    return False


def _field_spec_sources(expression: str) -> list[str]:
    """Extract object literal bodies from the top-level FIELD_SPECS array.

    Args:
        expression: JavaScript function string from `config.value.expression`.

    Returns:
        Object literal body strings for FIELD_SPECS entries.
    """
    marker = expression.find("FIELD_SPECS")
    if marker < 0:
        return []
    start = expression.find("[", marker)
    if start < 0:
        return []

    sources: list[str] = []
    array_depth = 0
    object_depth = 0
    object_start: int | None = None
    quote = ""
    escape = False

    for index in range(start, len(expression)):
        char = expression[index]
        if quote:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                quote = ""
            continue
        if char in ("'", '"'):
            quote = char
            continue
        if char == "[":
            array_depth += 1
            continue
        if char == "]":
            array_depth -= 1
            if array_depth <= 0:
                break
            continue
        if array_depth == 1 and char == "{":
            if object_depth == 0:
                object_start = index + 1
            object_depth += 1
            continue
        if array_depth == 1 and char == "}":
            object_depth -= 1
            if object_depth == 0 and object_start is not None:
                sources.append(expression[object_start:index])
                object_start = None

    return sources


def _normalize_array_field(field: dict[str, Any], field_key: str, warnings: list[str]) -> None:
    items = field.get("items")
    if not isinstance(items, dict):
        items = {"type": "object", "properties": {}, "widget": {"id": "table-body"}}
        field["items"] = items
        warnings.append(f"Added object items for array field {field_key!r}.")

    if items.get("type") != "object":
        items["type"] = "object"
        warnings.append(f"Set array field {field_key!r} items.type=object.")

    item_properties = items.get("properties")
    if not isinstance(item_properties, dict):
        items["properties"] = {}
        item_properties = items["properties"]
        warnings.append(f"Added items.properties for array field {field_key!r}.")

    item_widget = items.get("widget")
    if not isinstance(item_widget, dict):
        items["widget"] = {"id": "table-body"}
        warnings.append(f"Added items.widget.id=table-body for array field {field_key!r}.")
    elif not item_widget.get("id"):
        item_widget["id"] = "table-body"
        warnings.append(f"Added items.widget.id=table-body for array field {field_key!r}.")

    for nested_key, nested_value in item_properties.items():
        if not isinstance(nested_value, dict):
            # A table column must still be an object schema; use the smallest
            # visible string column rather than inventing domain-specific fields.
            item_properties[nested_key] = {
                "type": "string",
                "title": nested_key,
                "hideTitle": True,
                "widget": {"id": "string"},
            }
            warnings.append(
                f"Replaced non-object nested field {field_key}.{nested_key} with a string field."
            )
            continue
        if not nested_value.get("type"):
            nested_value["type"] = _infer_type(nested_value)
            warnings.append(f"Added type for nested field {field_key}.{nested_key}.")
        if not isinstance(nested_value.get("widget"), dict):
            nested_value["widget"] = {"id": _default_widget_for_field(nested_value)}
            warnings.append(f"Added widget.id for nested field {field_key}.{nested_key}.")
        elif not nested_value["widget"].get("id"):
            nested_value["widget"]["id"] = _default_widget_for_field(nested_value)
            warnings.append(f"Added widget.id for nested field {field_key}.{nested_key}.")
        else:
            _normalize_widget_alias(nested_value, f"{field_key}.{nested_key}", warnings)
        _promote_select_keys_from_widget(nested_value, f"{field_key}.{nested_key}", warnings)

    if "fieldsets" not in items:
        items["fieldsets"] = [
            {
                "id": f"{field_key}-fieldset-default",
                "title": field.get("title") or field_key,
                "description": "",
                "name": "",
                "fields": list(item_properties.keys()),
            }
        ]
        warnings.append(f"Added fieldsets for array field {field_key!r}.")
    elif not isinstance(items.get("fieldsets"), list):
        items["fieldsets"] = []
        warnings.append(f"Replaced invalid items.fieldsets for array field {field_key!r}.")
