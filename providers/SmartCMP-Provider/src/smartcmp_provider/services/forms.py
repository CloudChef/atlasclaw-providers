"""Shared read-only SmartCMP form operations."""

from __future__ import annotations

import uuid

from smartcmp_provider.forms.definitions import (
    FormDefinition,
    FormSource,
    form_definition_from_payload,
    get_form_definition,
    parse_form_edit_url,
)
from smartcmp_provider.forms.design import prepare_design
from smartcmp_provider.forms.schema_normalize import normalize_schema
from smartcmp_provider.models.forms import (
    FormDesignInput,
    FormDesignResult,
    FormReadQuery,
    FormReadResult,
)
from smartcmp_provider.transport.client import SmartCmpClient
from smartcmp_provider.errors import SmartCmpValidationError


async def read_form(
    client: SmartCmpClient,
    query: FormReadQuery,
) -> FormReadResult:
    """Read and parse one form through the Provider-owned HTTP boundary."""

    form = await _load_form(
        client,
        form_id=query.form_id,
        form_url=query.form_url,
    )
    return project_form_definition(
        {
            "id": form.form_id,
            "name": form.name,
            "description": form.description,
            "content": {
                "schema": form.schema,
                "model": form.model,
                "designMode": form.design_mode,
                "components": [None] * form.component_count,
            },
        },
        source_route=form.source_route,
        raw_content_keys=tuple(form.raw_content_keys),
    )


def project_form_definition(
    payload: dict[str, object],
    *,
    source_route: str = "edit",
    raw_content_keys: tuple[str, ...] | None = None,
) -> FormReadResult:
    """Project one raw form payload into the shared normalized form view."""

    form_id = str(payload.get("id") or "").strip()
    source = FormSource(
        form_id=form_id,
        form_url="",
        route=source_route,
    )
    form = form_definition_from_payload(payload, source)
    schema, warnings = normalize_schema(form.schema)
    return FormReadResult(
        form_id=form.form_id,
        name=form.name,
        description=form.description,
        form_schema=schema,
        model=form.model,
        design_mode=form.design_mode,
        component_count=form.component_count,
        source_route=form.source_route,
        raw_content_keys=(
            raw_content_keys
            if raw_content_keys is not None
            else tuple(form.raw_content_keys)
        ),
        warnings=tuple(warnings),
    )


async def design_form(
    client: SmartCmpClient,
    design_input: FormDesignInput,
) -> FormDesignResult:
    """Build one complete replacement schema without persisting a change."""

    form_url = design_input.form_url.strip()
    source_form = (
        await _load_form(
            client,
            form_id=design_input.form_id,
            form_url=form_url,
        )
        if design_input.form_id or form_url
        else None
    )
    result = prepare_design(
        mode=design_input.mode,
        schema_json=design_input.schema_json_value,
        form_url=form_url,
        change_summary=design_input.change_summary,
        catalog_fields_json=design_input.catalog_fields_json,
        value_expressions_json=design_input.value_expressions_json,
        requested_fields_json=design_input.requested_fields_json,
        base_url=client.request.context.instance.base_url,
        source_form=source_form,
    )
    return FormDesignResult(
        mode=result["mode"],
        source=result["source"],
        warnings=tuple(result["warnings"]),
        changeSummary=result["changeSummary"],
        form_schema=result["schema"],
    )


async def _load_form(
    client: SmartCmpClient,
    *,
    form_id: str = "",
    form_url: str = "",
) -> FormDefinition:
    """Resolve and read one form while preserving its validated editor route."""

    normalized_id = str(form_id or "").strip().lower()
    if form_url.strip():
        source = parse_form_edit_url(
            form_url,
            client.request.context.instance.base_url,
        )
        if normalized_id and source.form_id != normalized_id:
            raise SmartCmpValidationError(
                "SmartCMP form_url does not match form_id.",
                trace_id=client.request.context.trace_id,
            )
        return await get_form_definition(client, source)
    try:
        canonical_id = str(uuid.UUID(normalized_id))
    except (ValueError, AttributeError) as exc:
        raise SmartCmpValidationError(
            "SmartCMP form_id must be a canonical UUID.",
            trace_id=client.request.context.trace_id,
        ) from exc
    if canonical_id != normalized_id:
        raise SmartCmpValidationError(
            "SmartCMP form_id must be a canonical UUID.",
            trace_id=client.request.context.trace_id,
        )
    source = FormSource(
        form_id=canonical_id,
        form_url="",
        route="edit",
    )
    return await get_form_definition(client, source)
