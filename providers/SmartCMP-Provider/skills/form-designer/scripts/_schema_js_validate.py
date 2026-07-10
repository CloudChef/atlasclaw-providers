#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Validate SmartCMP schema JavaScript strings without executing them."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile


_EXPECTED_FUNCTION_PATTERN = re.compile(
    r"^\s*function\s*\(\s*model\s*,\s*sourceParams\s*,\s*schema\s*,\s*unused\s*,\s*cfg\s*\)",
    re.DOTALL,
)
_MODEL_ASSIGNMENT_PATTERN = re.compile(
    r"\bmodel\s*(?:(?:\?\s*)?\.\s*[A-Za-z_$][\w$]*|(?:\?\s*\.)?\[[^\]]+\])\s*=(?!=|>)"
)
_RISK_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\beval\s*\(", "eval(...)"),
    (r"(?<![\w$])(?:new\s+)?(?:Function|(?:[A-Za-z_$][\w$]*\s*\.\s*)+Function)\s*\(", "Function constructor"),
    (r"\bfetch\s*\(", "fetch(...)"),
    (r"\bXMLHttpRequest\b", "XMLHttpRequest"),
    (r"\bdocument\s*\.\s*cookie\b", "document.cookie"),
    (r"https?://", "external URL"),
)
_MODEL_BRACKET_READ_PATTERN = re.compile(r"\bmodel\s*(?:\?\s*\.)?\[\s*(['\"])(?P<key>[^'\"]+)\1\s*\]")
_MODEL_DOT_READ_PATTERN = re.compile(r"\bmodel\s*(?:\?\s*)?\.\s*(?P<key>[A-Za-z_$][\w$]*)")
_MODEL_DYNAMIC_BRACKET_READ_PATTERN = re.compile(r"\bmodel\s*(?:\?\s*\.)?\[\s*(?P<name>[A-Za-z_$][\w$]*)\s*\]")
_STRING_ALIAS_PATTERN = re.compile(r"\b(?:var|let|const)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*(['\"])(?P<value>[^'\"]+)\2")
_SOURCE_PARAMS_ALIAS_PATTERN = re.compile(
    r"\b(?:var|let|const)\s+(?P<alias>[A-Za-z_$][\w$]*)\s*=\s*sourceParams(?=\s*(?:;|,|\|\||$))"
)
_SOURCE_PARAMS_BRACKET_READ_PATTERN = re.compile(r"\bsourceParams\s*(?:\?\s*\.)?\[\s*(['\"])(?P<key>[^'\"]+)\1\s*\]")
_SOURCE_PARAMS_DOT_READ_PATTERN = re.compile(r"\bsourceParams\s*(?:\?\s*)?\.\s*(?P<key>[A-Za-z_$][\w$]*)")
_SOURCE_PARAMS_FALLBACK_DOT_READ_PATTERN = re.compile(r"\(\s*sourceParams\s*\|\|\s*\{\s*\}\s*\)\s*(?:\?\s*)?\.\s*(?P<key>[A-Za-z_$][\w$]*)")
_SOURCE_PARAMS_FALLBACK_BRACKET_READ_PATTERN = re.compile(
    r"\(\s*sourceParams\s*\|\|\s*\{\s*\}\s*\)\s*(?:\?\s*\.)?\[\s*(['\"])(?P<key>[^'\"]+)\1\s*\]"
)
_IDENTIFIER = r"[A-Za-z_$][\w$]*"
_SCHEMA_SAFE_READ_KEYS = frozenset(("properties", "required", "fieldsets", "columnsets", "config", "type"))


def validate_javascript_expression(
    expression: str,
    *,
    field_key: str,
    schema_property_keys: set[str] | None = None,
) -> list[str]:
    if not expression:
        return []
    warnings: list[str] = []
    executable_text = _javascript_without_literals(expression)
    warnings.extend(_validate_javascript_syntax(expression, field_key=field_key))
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
    warnings.extend(_validate_source_params_direct_reads(expression, field_key=field_key))
    warnings.extend(_validate_runtime_context_direct_reads(expression, field_key=field_key))
    if schema_property_keys is not None:
        warnings.extend(
            _validate_model_literal_reads(
                expression,
                field_key=field_key,
                schema_property_keys=schema_property_keys,
            )
        )
    return warnings


def _validate_javascript_syntax(expression: str, *, field_key: str) -> list[str]:
    node = shutil.which("node")
    if node is None:
        return [
            f"JavaScript expression for field {field_key!r} cannot validate JavaScript syntax "
            "because Node.js is unavailable."
        ]

    source_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".js",
            delete=False,
        ) as source:
            source.write(f"const __smartcmp_expression__ = ({expression});\n")
            source_path = source.name
        result = subprocess.run(
            [node, "--check", source_path],
            text=True,
            capture_output=True,
            encoding="utf-8",
            check=False,
        )
    except OSError as error:
        return [
            f"JavaScript expression for field {field_key!r} cannot validate JavaScript syntax: {error}."
        ]
    finally:
        if source_path:
            try:
                os.unlink(source_path)
            except OSError:
                pass

    if result.returncode:
        return [f"JavaScript expression for field {field_key!r} has invalid JavaScript syntax."]
    return []


def validate_value_expression_contract(expression: str, *, field_key: str) -> list[str]:
    """Validate the submit contract for ``config.value.expression`` only."""
    if not expression:
        return []

    if not _EXPECTED_FUNCTION_PATTERN.search(expression):
        return [
            "Value expression for field "
            f"{field_key!r} must use function(model, sourceParams, schema, unused, cfg)."
        ]

    executable_text = _javascript_without_literals(expression)
    if not _MODEL_ASSIGNMENT_PATTERN.search(executable_text):
        return [
            f"Value expression for field {field_key!r} must assign model[fieldKey] before returning."
        ]
    return []


def _javascript_without_literals(expression: str) -> str:
    output: list[str] = []
    index = 0
    quote: str | None = None
    while index < len(expression):
        char = expression[index]
        next_char = expression[index + 1] if index + 1 < len(expression) else ""
        if quote is not None:
            if char == "\\":
                output.append(" ")
                if index + 1 < len(expression):
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
        elif char == "/" and next_char == "/":
            output.extend((" ", " "))
            index += 2
            while index < len(expression) and expression[index] not in "\r\n":
                output.append(" ")
                index += 1
            continue
        elif char == "/" and next_char == "*":
            output.extend((" ", " "))
            index += 2
            while index < len(expression):
                if expression[index:index + 2] == "*/":
                    output.extend((" ", " "))
                    index += 2
                    break
                output.append(" ")
                index += 1
            continue
        else:
            output.append(char)
        index += 1
    return "".join(output)


def _validate_source_params_direct_reads(expression: str, *, field_key: str) -> list[str]:
    warnings: list[str] = []
    seen: set[str] = set()
    executable_text = _javascript_without_literals(expression)
    for match in list(_SOURCE_PARAMS_DOT_READ_PATTERN.finditer(executable_text)) + list(
        _SOURCE_PARAMS_FALLBACK_DOT_READ_PATTERN.finditer(executable_text)
    ):
        _append_source_warning(warnings, seen, field_key, match.group("key"))
    for match in _SOURCE_PARAMS_BRACKET_READ_PATTERN.finditer(expression):
        if "sourceParams" in executable_text[match.start() : match.end()]:
            _append_source_warning(warnings, seen, field_key, match.group("key"))
    for match in _SOURCE_PARAMS_FALLBACK_BRACKET_READ_PATTERN.finditer(expression):
        if "sourceParams" in executable_text[match.start() : match.end()]:
            _append_source_warning(warnings, seen, field_key, match.group("key"))
    aliases = {match.group("alias") for match in _SOURCE_PARAMS_ALIAS_PATTERN.finditer(executable_text)}
    for key, _end in _root_destructure_reads(expression, executable_text, "sourceParams"):
        _append_source_warning(warnings, seen, field_key, key)
    for alias in aliases:
        for key, _end in _root_literal_reads(expression, executable_text, alias):
            _append_source_warning(warnings, seen, field_key, key)
        for key, _end in _root_destructure_reads(expression, executable_text, alias):
            _append_source_warning(warnings, seen, field_key, key)
    return warnings


def _append_source_warning(warnings: list[str], seen: set[str], field_key: str, key: str) -> None:
    if key in seen:
        return
    seen.add(key)
    warnings.append(
        f"JavaScript expression for field {field_key!r} uses an unverified "
        f"sourceParams context container {key!r}, which is not a verified "
        "SmartCMP service-catalog context path; use value_expressions_json or "
        "verified catalog context paths."
    )


def _root_literal_reads(expression: str, executable_text: str, root: str) -> list[tuple[str, int]]:
    dot = re.compile(rf"\b{re.escape(root)}\s*(?:\?\s*)?\.\s*(?P<key>{_IDENTIFIER})")
    bracket = re.compile(rf"\b{re.escape(root)}\s*(?:\?\s*\.)?\[\s*(['\"])(?P<key>[^'\"]+)\1\s*\]")
    reads = [(match.group("key"), match.end()) for match in dot.finditer(executable_text)]
    for match in bracket.finditer(expression):
        if root in executable_text[match.start() : match.end()]:
            reads.append((match.group("key"), match.end()))
    return reads


def _root_destructure_reads(expression: str, executable_text: str, root: str) -> list[tuple[str, int]]:
    pattern = re.compile(
        rf"\b(?:var|let|const)\s*\{{(?P<body>[^;]*?)\}}\s*=\s*{re.escape(root)}(?:\s*\|\|\s*\{{\s*\}})?",
        re.DOTALL,
    )
    reads: list[tuple[str, int]] = []
    for match in pattern.finditer(expression):
        if root not in executable_text[match.start() : match.end()]:
            continue
        reads.extend((key, match.end()) for key in _destructured_object_keys(match.group("body")))
    return reads


def _destructured_object_keys(body: str) -> list[str]:
    keys: list[str] = []
    for part in body.split(","):
        item = part.strip()
        if not item or item.startswith("..."):
            continue
        key = item.split(":", 1)[0].split("=", 1)[0].strip()
        if len(key) >= 2 and key[0] in {"'", '"'} and key[-1] == key[0]:
            key = key[1:-1]
        if key:
            keys.append(key)
    return keys


def _validate_runtime_context_direct_reads(expression: str, *, field_key: str) -> list[str]:
    warnings: list[str] = []
    executable_text = _javascript_without_literals(expression)
    for root in ("cfg", "schema"):
        for key, _end in _root_literal_reads(expression, executable_text, root):
            if root == "schema" and key in _SCHEMA_SAFE_READ_KEYS:
                continue
            warnings.append(
                f"JavaScript expression for field {field_key!r} uses an unverified "
                f"runtime context container {root}.{key}; use value_expressions_json "
                "or verified catalog context paths."
            )
    return warnings


def _validate_model_literal_reads(
    expression: str,
    *,
    field_key: str,
    schema_property_keys: set[str],
) -> list[str]:
    warnings: list[str] = []
    seen: set[str] = set()
    string_aliases = {match.group("name"): match.group("value") for match in _STRING_ALIAS_PATTERN.finditer(expression)}
    literal_matches = list(_MODEL_BRACKET_READ_PATTERN.finditer(expression)) + list(_MODEL_DOT_READ_PATTERN.finditer(expression))
    for match in literal_matches:
        _append_model_warning(warnings, seen, expression, match.end(), field_key, match.group("key"), schema_property_keys)
    for match in _MODEL_DYNAMIC_BRACKET_READ_PATTERN.finditer(expression):
        key = string_aliases.get(match.group("name"), f"<dynamic:{match.group('name')}>")
        _append_model_warning(warnings, seen, expression, match.end(), field_key, key, schema_property_keys)
    return warnings


def _append_model_warning(
    warnings: list[str],
    seen: set[str],
    expression: str,
    end: int,
    field_key: str,
    key: str,
    schema_property_keys: set[str],
) -> None:
    if key in seen or key in schema_property_keys or _is_literal_model_assignment(expression, end):
        return
    seen.add(key)
    warnings.append(
        f"JavaScript expression for field {field_key!r} reads model field {key!r} "
        "which is not a schema property; add the field to schema.properties or "
        "use value_expressions_json with verified catalog context paths for "
        "service-catalog source values."
    )


def _is_literal_model_assignment(expression: str, position: int) -> bool:
    index = position
    while index < len(expression) and expression[index].isspace():
        index += 1
    if index >= len(expression) or expression[index] != "=":
        return False
    next_char = expression[index + 1] if index + 1 < len(expression) else ""
    return next_char not in {"=", ">"}
