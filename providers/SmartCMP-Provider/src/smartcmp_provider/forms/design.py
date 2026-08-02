"""Orchestrate reusable SmartCMP form schema design."""

from __future__ import annotations

import json
from typing import Any

from smartcmp_provider.forms.catalog_insertions import apply_catalog_fields
from smartcmp_provider.forms.definitions import (
    FormDefinition,
    parse_form_edit_url,
)
from smartcmp_provider.forms.requested_fields import (
    constrain_schema_to_requested_fields,
    load_requested_fields,
)
from smartcmp_provider.forms.schema_layout import (
    ensure_schema_form_valid_control,
)
from smartcmp_provider.forms.schema_normalize import (
    SchemaNormalizationError,
    normalize_schema,
)
from smartcmp_provider.forms.value_expressions import apply_value_expressions

_ROUTINE_VISIBLE_WARNING_PREFIXES = (
    "Added root widget.id=object.",
    "Changed widget.id=text to string for field ",
    "Added config.visibility for field ",
    "Added allowInRequest=true for field ",
    "Added allowInApproval=true for field ",
    "Set root fieldset id=fieldset-default for catalog request compatibility.",
    "Removed root fieldset index for catalog request compatibility.",
    "Canonicalized root fieldset field order for catalog request compatibility.",
    "Set catalog request field index=",
    "Removed schemaFormValid index for catalog request compatibility.",
)


def load_schema(schema_json: str) -> dict[str, Any]:
    """Parse a complete draft schema JSON object."""

    try:
        parsed = json.loads(schema_json)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"schema_json is not valid JSON: {error}"
        ) from error
    if not isinstance(parsed, dict):
        raise ValueError("schema_json must be a JSON object.")
    return parsed


def source_metadata(form: FormDefinition) -> dict[str, Any]:
    """Project reusable source form metadata."""

    return {
        "formId": form.form_id,
        "name": form.name,
        "route": form.source_route,
        "designMode": form.design_mode,
        "modelKeys": sorted(form.model),
        "componentCount": form.component_count,
    }


def source_schema(
    form: FormDefinition,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Return a source schema plus visual-designer compatibility warnings."""

    warnings: list[str] = []
    if form.component_count:
        warnings.append(
            "Source form contains visual designer components; schema-only "
            "replacement can be overwritten by SmartCMP visual designer "
            "component state. Review component/designMode state before saving "
            "the form."
        )
    if form.model:
        warnings.append(
            "Source form content.model has existing keys "
            f"({', '.join(sorted(form.model))}); value expressions must "
            "overwrite target model values at runtime."
        )
    return form.schema, source_metadata(form), warnings


def raise_for_fatal_warnings(
    warnings: list[str],
    *,
    form_url: str = "",
    value_expressions_json: str = "",
) -> None:
    """Reject generated JavaScript that can silently produce invalid forms."""

    fatal_warnings = [
        warning
        for warning in warnings
        if "literal ellipsis placeholder" in warning
        or "JavaScript syntax" in warning
    ]
    if fatal_warnings:
        raise ValueError(
            "Generated schema contains abbreviated JavaScript. Use "
            "value_expressions_json or provide a complete function string. "
            + " ".join(fatal_warnings)
        )
    unresolved = [
        warning
        for warning in warnings
        if (
            "which is not a schema property" in warning
            or "uses an unverified sourceParams context container" in warning
            or "uses an unverified runtime context container" in warning
            or (
                warning.startswith("Value expression for field ")
                and not form_url.strip()
            )
        )
    ]
    if unresolved:
        raise ValueError(
            "Generated schema contains JavaScript that can submit empty values "
            "because it reads unresolved service-catalog context. "
            + " ".join(unresolved)
        )
    if form_url.strip() and not value_expressions_json.strip():
        legacy = [
            warning
            for warning in warnings
            if (
                "is not a function(model, sourceParams, schema, unused, cfg)"
                in warning
                or "does not assign model[" in warning
                or warning.startswith("Value expression for field ")
            )
        ]
        if legacy:
            raise ValueError(
                "URL-based form changes cannot use legacy JavaScript "
                "expressions. Use value_expressions_json for deterministic "
                "updates, or provide a complete "
                "function(model, sourceParams, schema, unused, cfg) "
                "expression that writes model[fieldKey]. "
                + " ".join(legacy)
            )


def visible_warnings(warnings: list[str]) -> list[str]:
    """Hide routine canonicalization notes from user-facing output."""

    return [
        warning
        for warning in warnings
        if not any(
            warning.startswith(prefix)
            for prefix in _ROUTINE_VISIBLE_WARNING_PREFIXES
        )
    ]


def prepare_design(
    *,
    mode: str,
    schema_json: str,
    form_url: str,
    change_summary: str,
    catalog_fields_json: str,
    value_expressions_json: str,
    requested_fields_json: str,
    base_url: str,
    source_form: FormDefinition | None,
) -> dict[str, Any]:
    """Build a complete normalized form schema without persisting it."""

    if mode not in {"new", "modify", "regenerate"}:
        raise ValueError("mode must be new, modify, or regenerate.")
    if mode == "modify" and not schema_json and source_form is None:
        raise ValueError(
            "schema_json or an existing source form is required for modify mode."
        )
    if mode in {"new", "regenerate"} and not schema_json:
        raise ValueError(f"schema_json is required for {mode} mode.")

    warnings: list[str] = []
    source: dict[str, Any] = {}
    requested_fields = load_requested_fields(requested_fields_json)
    if schema_json:
        schema = load_schema(schema_json)
        if source_form is not None:
            source = source_metadata(source_form)
        elif form_url:
            parsed = parse_form_edit_url(form_url, base_url)
            source = {"formId": parsed.form_id, "route": parsed.route}
    elif source_form is not None:
        schema, source, source_warnings = source_schema(source_form)
        warnings.extend(source_warnings)
    else:
        raise ValueError("The source form could not be loaded.")

    if not schema_json:
        if value_expressions_json.strip():
            warnings.append(
                "No schema_json was provided; loaded the source form before "
                "deterministic value expression update."
            )
        elif catalog_fields_json.strip():
            warnings.append(
                "No schema_json was provided; loaded the source form before "
                "deterministic catalog field insertion."
            )
        else:
            warnings.append(
                "No schema_json was provided; normalized the source form "
                "without changes."
            )

    warnings.extend(
        constrain_schema_to_requested_fields(schema, requested_fields)
    )
    warnings.extend(apply_catalog_fields(schema, catalog_fields_json))
    warnings.extend(
        apply_value_expressions(schema, value_expressions_json)
    )
    warnings.extend(
        constrain_schema_to_requested_fields(
            schema,
            requested_fields,
            require_all=True,
        )
    )
    schema, normalization_warnings = normalize_schema(schema)
    warnings.extend(normalization_warnings)
    ensure_schema_form_valid_control(schema, warnings)
    raise_for_fatal_warnings(
        warnings,
        form_url=form_url,
        value_expressions_json=value_expressions_json,
    )
    summary = change_summary.strip() or {
        "new": "Generated a new SmartCMP form schema.",
        "modify": "Prepared a normalized SmartCMP form schema.",
        "regenerate": "Regenerated a replacement SmartCMP form schema.",
    }[mode]
    return {
        "mode": mode,
        "source": source,
        "warnings": warnings,
        "changeSummary": summary,
        "schema": schema,
    }


__all__ = [
    "SchemaNormalizationError",
    "apply_catalog_fields",
    "apply_value_expressions",
    "constrain_schema_to_requested_fields",
    "ensure_schema_form_valid_control",
    "load_requested_fields",
    "load_schema",
    "normalize_schema",
    "prepare_design",
    "raise_for_fatal_warnings",
    "source_metadata",
    "source_schema",
    "visible_warnings",
]
