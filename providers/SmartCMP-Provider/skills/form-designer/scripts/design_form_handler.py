# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Context-aware final-output handler for SmartCMP form schema design."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from typing import Any

import requests

try:
    from pydantic_ai import RunContext
except ImportError:  # Provider-only unit tests do not install the Core runtime.
    RunContext = Any

from design_form import (
    SchemaNormalizationError,
    _load_schema,
    _raise_for_fatal_warnings,
    _visible_warnings,
    apply_catalog_fields,
    apply_value_expressions,
    constrain_schema_to_requested_fields,
    ensure_schema_form_valid_control,
    load_requested_fields,
    normalize_schema,
)
from _form_fetch import (
    FormDefinition,
    FormSource,
    fetch_form_definition,
    form_definition_from_payload,
    parse_form_edit_url,
)

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "shared", "scripts")
    ),
)

from _current_page_object import (  # noqa: E402
    CurrentPageObjectError,
    embedded_object_id,
    fetch_current_page_object,
    selected_provider_read_config,
)


def _source_metadata(form: FormDefinition) -> dict[str, Any]:
    return {
        "formId": form.form_id,
        "name": form.name,
        "route": form.source_route,
        "designMode": form.design_mode,
        "modelKeys": sorted(form.model),
        "componentCount": form.component_count,
    }


def _source_schema(
    form: FormDefinition,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    warnings: list[str] = []
    if form.component_count:
        warnings.append(
            "Source form contains visual designer components; schema-only replacement "
            "can be overwritten by SmartCMP visual designer component state. "
            "Review component/designMode state before saving the form."
        )
    if form.model:
        warnings.append(
            "Source form content.model has existing keys "
            f"({', '.join(sorted(form.model))}); value expressions must overwrite "
            "target model values at runtime."
        )
    return form.schema, _source_metadata(form), warnings


def _summary(mode: str, change_summary: str) -> str:
    if change_summary.strip():
        return change_summary.strip()
    return {
        "new": "Generated a new SmartCMP form schema.",
        "regenerate": "Regenerated a replacement SmartCMP form schema.",
        "modify": "Prepared a normalized SmartCMP form schema.",
    }[mode]


def _prepare_design(
    *,
    mode: str,
    schema_json: str,
    form_url: str,
    change_summary: str,
    catalog_fields_json: str,
    value_expressions_json: str,
    requested_fields_json: str,
    base_url: str,
    headers: dict[str, str] | None,
    timeout: int | None,
    source_form: FormDefinition | None,
) -> dict[str, Any]:
    if mode not in {"new", "modify", "regenerate"}:
        raise ValueError("mode must be new, modify, or regenerate.")
    if mode == "modify" and not schema_json and not form_url:
        raise ValueError("schema_json or form_url is required for modify mode.")
    if mode in {"new", "regenerate"} and not schema_json:
        raise ValueError(f"schema_json is required for {mode} mode.")

    warnings: list[str] = []
    source: dict[str, Any] = {}
    requested_fields = load_requested_fields(requested_fields_json)
    if schema_json:
        schema = _load_schema(schema_json)
        if source_form is not None:
            source = _source_metadata(source_form)
        elif form_url:
            parsed = parse_form_edit_url(form_url, base_url)
            source = {"formId": parsed.form_id, "route": parsed.route}
    elif source_form is not None:
        schema, source, source_warnings = _source_schema(source_form)
        warnings.extend(source_warnings)
    else:
        form = fetch_form_definition(
            form_url,
            base_url,
            headers or {},
            timeout=timeout,
        )
        schema, source, source_warnings = _source_schema(form)
        warnings.extend(source_warnings)

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
                "No schema_json was provided; normalized the source form without changes."
            )

    warnings.extend(constrain_schema_to_requested_fields(schema, requested_fields))
    warnings.extend(apply_catalog_fields(schema, catalog_fields_json))
    warnings.extend(apply_value_expressions(schema, value_expressions_json))
    warnings.extend(
        constrain_schema_to_requested_fields(schema, requested_fields, require_all=True)
    )
    schema, normalization_warnings = normalize_schema(schema)
    warnings.extend(normalization_warnings)
    ensure_schema_form_valid_control(schema, warnings)
    _raise_for_fatal_warnings(
        warnings,
        form_url=form_url,
        value_expressions_json=value_expressions_json,
    )
    return {
        "mode": mode,
        "source": source,
        "warnings": warnings,
        "changeSummary": _summary(mode, change_summary),
        "schema": schema,
    }


def _json_fence(schema: dict[str, Any]) -> str:
    content = json.dumps(schema, ensure_ascii=False, indent=2)
    longest = max(
        (len(match.group(0)) for match in re.finditer(r"`+", content)),
        default=0,
    )
    marker = "`" * max(3, longest + 1)
    return f"{marker}json\n{content}\n{marker}"


def _final_user_output(
    result: dict[str, Any],
    *,
    object_name: str,
    object_id: str,
) -> str:
    warnings = _visible_warnings(result["warnings"])
    validation = ["- Schema normalization and structural validation completed."]
    validation.extend(
        [f"- Risk: {warning}" for warning in warnings]
        or ["- Risks: No additional schema warnings were reported."]
    )
    return "\n".join(
        [
            "## 1. Current Object",
            f"- Name: {object_name}",
            f"- ID: {object_id}",
            "",
            "## 2. Copy Target",
            "- Copy the JSON below into the form definition's `content.schema` field.",
            "",
            "## 3. Change Summary",
            result["changeSummary"],
            "",
            "## 4. Complete Replacement JSON",
            _json_fence(result["schema"]),
            "",
            "## 5. Validation and Risks",
            *validation,
            "",
            "## 6. Save Status",
            "- Not saved. This Tool did not write, publish, or update anything in CMP.",
            "- Review the complete JSON and copy it back to the SmartCMP form editor manually.",
        ]
    )


async def design_form(
    ctx: RunContext[Any],
    mode: str,
    schema_json: str = "",
    form_url: str = "",
    change_summary: str = "",
    catalog_fields_json: str = "",
    value_expressions_json: str = "",
    requested_fields_json: str = "",
) -> dict[str, Any]:
    """Return a complete replacement schema bound to the active form Context.

    Args:
        ctx: Server-owned AtlasClaw request and embedded page Context.
        mode: ``new``, ``modify``, or ``regenerate``.
        schema_json: Complete caller-provided replacement schema.
        form_url: Optional current-instance source form URL.
        change_summary: User-facing description of the requested change.
        catalog_fields_json: Optional deterministic catalog-field insertions.
        value_expressions_json: Optional deterministic value-expression updates.
        requested_fields_json: Optional exact requested business-field list.

    Returns:
        Structured result containing both compatibility ``output`` and trusted
        ``final_user_output`` fields. No CMP write is performed.
    """
    values = {
        "mode": str(mode or ""),
        "schema_json": str(schema_json or ""),
        "form_url": str(form_url or ""),
        "change_summary": str(change_summary or ""),
        "catalog_fields_json": str(catalog_fields_json or ""),
        "value_expressions_json": str(value_expressions_json or ""),
        "requested_fields_json": str(requested_fields_json or ""),
    }
    try:
        context_form_id = embedded_object_id(
            ctx,
            expected_object_type="form_definition",
        )
        base_url = ""
        headers: dict[str, str] | None = None
        timeout: int | None = None
        url_source = None
        if values["form_url"] or context_form_id is not None:
            base_url, headers, timeout = await asyncio.to_thread(
                selected_provider_read_config,
                ctx,
                request_cookie_only=context_form_id is not None,
            )
        if values["form_url"]:
            url_source = parse_form_edit_url(values["form_url"], base_url)
            if context_form_id is not None and url_source.form_id != context_form_id:
                raise CurrentPageObjectError(
                    "form_url does not match the current SmartCMP form page Context."
                )

        source_form = None
        if context_form_id is not None:
            payload = await fetch_current_page_object(
                ctx,
                expected_object_type="form_definition",
                api_collection="forms",
            )
            form_source = url_source or FormSource(
                form_id=context_form_id,
                form_url="",
                route="edit",
            )
            source_form = form_definition_from_payload(payload, form_source)
        elif url_source is not None:
            source_form = await asyncio.to_thread(
                fetch_form_definition,
                values["form_url"],
                base_url,
                headers or {},
                timeout=timeout,
            )

        result = await asyncio.to_thread(
            _prepare_design,
            **values,
            base_url=base_url,
            headers=headers,
            timeout=timeout,
            source_form=source_form,
        )
    except (
        CurrentPageObjectError,
        ValueError,
        SchemaNormalizationError,
        requests.RequestException,
    ) as error:
        return {"success": False, "error": str(error)}

    source = result["source"]
    object_id = str(source.get("formId") or "").strip()
    object_name = str(source.get("name") or "").strip()
    if not object_name:
        object_name = "New SmartCMP form draft" if not object_id else "SmartCMP form"
    if not object_id:
        object_id = "N/A (new unsaved draft)"
    final_output = _final_user_output(
        result,
        object_name=object_name,
        object_id=object_id,
    )
    return {
        "success": True,
        "output": final_output,
        "final_user_output": final_output,
        **result,
    }
