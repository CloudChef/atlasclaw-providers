"""AtlasClaw Tool adapters for SmartCMP request catalog and lifecycle actions."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


_SHARED_SCRIPTS = Path(__file__).resolve().parents[2] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from _atlasclaw_adapter import (  # noqa: E402
    RunContext,
    execute,
    execute_with_request,
    tool_error,
    tool_result,
    workflow_identity,
)
from _request_object_actions import (  # noqa: E402
    attach_catalog_object_metadata,
    attach_request_object_metadata,
)
from smartcmp_provider.domain.views import project_request_status  # noqa: E402
from smartcmp_provider.models.catalogs import (  # noqa: E402
    BusinessGroupQuery,
    CatalogDetailQuery,
    CatalogListQuery,
    FacetQuery,
    FlavorQuery,
    PhysicalTemplateQuery,
    ResourceBundleQuery,
)
from smartcmp_provider.models.requests import (  # noqa: E402
    RequestStatusQuery,
    RequestSubmissionInput,
    redact_request_secrets as _redact_request_secrets,
)
from smartcmp_provider.operations.catalogs import (  # noqa: E402
    get_catalog_detail as get_catalog_detail_operation,
    list_available_business_groups,
    list_catalogs,
    list_facets as list_facets_operation,
    list_flavors as list_flavors_operation,
    list_physical_templates as list_physical_templates_operation,
    list_resource_bundles as list_resource_bundles_operation,
)
from smartcmp_provider.operations.requests import (  # noqa: E402
    get_request_status as get_request_status_operation,
    submit_request as submit_request_operation,
)


def _resource_bundle_field_summary(result: Any) -> str:
    """Describe dynamic request fields without presenting a validation gate."""

    item = result.items[0]
    pending_keys = {
        str(key).strip()
        for key in (
            list(item.get("missingRequiredFields") or [])
            + list(item.get("missingSelectionFields") or [])
        )
        if str(key).strip()
    }
    pending_fields = []
    for field in item.get("requestFields") or []:
        if not isinstance(field, dict) or str(field.get("key") or "").strip() not in pending_keys:
            continue
        pending_fields.append(
            {
                key: value
                for key, value in {
                    "key": field.get("key"),
                    "target": field.get("target"),
                    "type": field.get("type"),
                    "required": field.get("required"),
                    "dependsOn": field.get("dependsOn") or [],
                }.items()
                if value not in (None, "")
            }
        )
    summary = {
        "resourceBundle": {
            "id": item.get("id"),
            "name": item.get("name"),
        },
        "pendingFields": pending_fields,
        "selectionField": dict(result.selection_field or {}),
        "selectionCandidates": list(result.selection_candidates or ()),
        "configurationErrors": _redact_request_secrets(
            list(item.get("configurationErrors") or [])
        ),
    }
    return json.dumps(summary, ensure_ascii=False, separators=(",", ":"))


def _compact_request_fields(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Project request fields into bounded workflow continuation metadata."""

    fields: list[dict[str, Any]] = []
    for field in item.get("requestFields") or []:
        if not isinstance(field, dict):
            continue
        projected = {
            key: value
            for key, value in {
                "key": field.get("key"),
                "name": field.get("name"),
                "target": field.get("target"),
                "type": field.get("type"),
                "required": field.get("required"),
                "ask": field.get("ask"),
                "dependsOn": field.get("dependsOn") or [],
                "value": field.get("value"),
                "options": [
                    {"id": option.get("id"), "name": option.get("name")}
                    for option in (field.get("options") or [])
                    if isinstance(option, dict)
                ],
            }.items()
            if value not in (None, "")
        }
        fields.append(projected)
    return fields


async def list_services(
    ctx: RunContext[Any],
    keyword: str | None = None,
) -> dict[str, Any]:
    """List catalogs after normalizing an omitted AtlasClaw keyword."""

    try:
        result, request = await execute_with_request(
            ctx,
            list_catalogs,
            CatalogListQuery(keyword=keyword or ""),
        )
        return tool_result(
            result,
            summary=f"Found {result.total} request catalogs.",
            internal={
                **workflow_identity(request),
                "catalogs": [
                    {
                        key: item.get(key)
                        for key in ("index", "id", "name", "status")
                        if item.get(key) not in (None, "")
                    }
                    for item in result.catalogs
                ],
            },
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def get_request_catalog(
    ctx: RunContext[Any],
    catalog_id: str,
) -> dict[str, Any]:
    """Load one selected catalog and its normalized request instructions."""

    try:
        result, request = await execute_with_request(
            ctx,
            get_catalog_detail_operation,
            CatalogDetailQuery(catalog_id=catalog_id),
        )
        result = result.model_copy(
            update={
                "metadata": attach_catalog_object_metadata(
                    result.metadata,
                    ui_base_url=request.context.instance.ui_base_url,
                )
            }
        )
        return tool_result(
            result,
            summary="Loaded the selected SmartCMP request catalog.",
            internal=_redact_request_secrets(
                {
                    **workflow_identity(request),
                    "metadata": result.metadata,
                }
            ),
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def submit(
    ctx: RunContext[Any],
    json_body: str,
    resource_bundle_selections: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Submit a confirmed request using its previously resolved pool IDs."""

    try:
        body = json.loads(json_body)
        if not isinstance(body, dict):
            raise ValueError("json_body must contain one JSON object.")
        result = await execute(
            ctx,
            submit_request_operation,
            RequestSubmissionInput(
                body=body,
                resource_bundle_selections=resource_bundle_selections or {},
            ),
        )
        request_ids = [
            item.request_id for item in result.items if item.request_id
        ]
        if result.overall_failed:
            failure_stage = (
                "initialization"
                if any(
                    item.outcome == "initialization_failed"
                    for item in result.items
                )
                else "submission"
            )
            summary = (
                f"SmartCMP request {failure_stage} failed: {', '.join(request_ids)}"
                if request_ids
                else f"SmartCMP request {failure_stage} failed."
            )
        elif request_ids:
            summary = f"Submitted SmartCMP request: {', '.join(request_ids)}"
        else:
            summary = "SmartCMP request submission did not return a confirmed Request ID."
        projected = tool_result(result, summary=summary)
        if result.overall_failed:
            projected["success"] = False
            projected["error"] = summary
        elif request_ids:
            # The Skill success contract intentionally accepts only the
            # canonical user-facing Request ID, not internal record UUIDs.
            projected["requestId"] = request_ids[0]
        return projected
    except (json.JSONDecodeError, ValueError, RuntimeError) as error:
        return tool_error(error)


async def status(
    ctx: RunContext[Any],
    request_id: str,
) -> dict[str, Any]:
    """Return the normalized lifecycle status for one visible Request ID."""

    try:
        raw_result, request = await execute_with_request(
            ctx,
            get_request_status_operation,
            RequestStatusQuery(request_id=request_id),
        )
        result = project_request_status(raw_result)
        summary = (
            f"Request {result.request_id}: state={result.state or 'unknown'}, "
            f"provision={result.provision_state or 'unknown'}."
        )
        projected = attach_request_object_metadata(
            result.model_dump(mode="json"),
            request=raw_result.detail,
            ui_base_url=request.context.instance.ui_base_url,
        )
        return tool_result(projected, summary=summary)
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def list_facets(
    ctx: RunContext[Any],
    business_group_id: str,
    node_type: str = "cloudchef.nodes.Compute",
) -> dict[str, Any]:
    """List request facets for one business group and node type."""

    try:
        result = await execute(
            ctx,
            list_facets_operation,
            FacetQuery(
                business_group_id=business_group_id,
                node_type=node_type,
            ),
        )
        return tool_result(
            result,
            summary=f"Found {len(result.items)} request facets.",
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def list_resource_bundles(
    ctx: RunContext[Any],
    business_group_id: str,
    component_type: str,
    node_type: str,
    catalog_id: str,
    node_template_name: str,
    cloud_entry_type_id: str | None = None,
    resource_bundle_id: str | None = None,
    resource_bundle_tags: list[str] | None = None,
    placement_fields: list[str] | None = None,
    placement_values: dict[str, str] | None = None,
) -> dict[str, Any]:
    """List tag-filtered resource pools and Provider-resolved placement choices."""

    try:
        normalized_resource_bundle_id = (resource_bundle_id or "").strip()
        normalized_resource_bundle_tags = (
            None
            if resource_bundle_tags is None
            else tuple(resource_bundle_tags)
        )
        result, request = await execute_with_request(
            ctx,
            list_resource_bundles_operation,
            ResourceBundleQuery(
                business_group_id=business_group_id,
                component_type=component_type,
                node_type=node_type,
                catalog_id=catalog_id,
                node_template_name=node_template_name,
                cloud_entry_type_id=cloud_entry_type_id or "",
                resource_bundle_id=normalized_resource_bundle_id,
                resource_bundle_tags=normalized_resource_bundle_tags,
                placement_fields=tuple(placement_fields or ()),
                placement_values=placement_values or {},
            ),
        )
        internal: dict[str, Any] = {
            "catalogId": catalog_id,
            "node": node_template_name,
            "businessGroupId": business_group_id,
            "items": [
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                }
                for item in result.items
            ],
        }
        if normalized_resource_bundle_id:
            exact_item = result.items[0]
            internal.update(
                {
                    "resourceBundleId": normalized_resource_bundle_id,
                    "placementValues": placement_values or {},
                    "items": [
                        {
                            "id": exact_item.get("id"),
                            "name": exact_item.get("name"),
                            "requestFields": _compact_request_fields(exact_item),
                            "missingRequiredFields": list(
                                exact_item.get("missingRequiredFields") or []
                            ),
                            "missingSelectionFields": list(
                                exact_item.get("missingSelectionFields") or []
                            ),
                            "configurationErrors": list(
                                exact_item.get("configurationErrors") or []
                            ),
                        }
                    ],
                    "selectionField": dict(result.selection_field or {}),
                    "selectionCandidates": list(result.selection_candidates or ()),
                }
            )
        public_result = _redact_request_secrets(
            result.model_dump(mode="json", by_alias=True)
        )
        return tool_result(
            public_result,
            summary=(
                _resource_bundle_field_summary(result)
                if normalized_resource_bundle_id
                else f"Found {len(result.items)} resource pools."
            ),
            internal=_redact_request_secrets(internal),
            request=request,
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def list_available_bgs(
    ctx: RunContext[Any],
    catalog_id: str,
) -> dict[str, Any]:
    """List business groups available to one selected request catalog."""

    try:
        result = await execute(
            ctx,
            list_available_business_groups,
            BusinessGroupQuery(catalog_id=catalog_id),
        )
        return tool_result(
            result,
            summary=f"Found {len(result.items)} available business groups.",
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def list_flavors(
    ctx: RunContext[Any],
    query: str | None = None,
    resource_bundle_id: str | None = None,
    compute_profile_id: str | None = None,
    catalog_id: str | None = None,
    node_template_name: str | None = None,
) -> dict[str, Any]:
    """List compute flavors after normalizing omitted AtlasClaw fields."""

    try:
        result, request = await execute_with_request(
            ctx,
            list_flavors_operation,
            FlavorQuery(
                query_value=query or "",
                resource_bundle_id=resource_bundle_id or "",
                compute_profile_id=compute_profile_id or "",
                catalog_id=catalog_id or "",
                node_template_name=node_template_name or "",
            ),
        )
        return tool_result(
            result,
            summary=f"Found {len(result.items)} compute flavors.",
            request=request,
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def list_physical_templates(
    ctx: RunContext[Any],
    resource_bundle_id: str,
    logic_template_id: str,
) -> dict[str, Any]:
    """List physical templates compatible with one logical template."""

    try:
        result = await execute(
            ctx,
            list_physical_templates_operation,
            PhysicalTemplateQuery(
                resource_bundle_id=resource_bundle_id,
                logic_template_id=logic_template_id,
            ),
        )
        return tool_result(
            result,
            summary=f"Found {len(result.items)} physical templates.",
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)
