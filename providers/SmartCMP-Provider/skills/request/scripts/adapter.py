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
        result = result.model_copy(
            update={
                "catalogs": tuple(
                    attach_catalog_object_metadata(
                        catalog,
                        ui_base_url=request.context.instance.ui_base_url,
                    )
                    for catalog in result.catalogs
                )
            }
        )
        return tool_result(
            result,
            summary=f"Found {result.total} request catalogs.",
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
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def submit(
    ctx: RunContext[Any],
    json_body: str,
) -> dict[str, Any]:
    """Submit one user-confirmed SmartCMP request body exactly once."""

    try:
        body = json.loads(json_body)
        if not isinstance(body, dict):
            raise ValueError("json_body must contain one JSON object.")
        result = await execute(
            ctx,
            submit_request_operation,
            RequestSubmissionInput(body=body),
        )
        request_ids = [
            item.request_id for item in result.items if item.request_id
        ]
        summary = (
            f"Submitted SmartCMP request: {', '.join(request_ids)}"
            if request_ids and not result.overall_failed
            else "SmartCMP request submission did not return a confirmed Request ID."
        )
        return tool_result(result, summary=summary)
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
    cloud_entry_type_id: str | None = None,
) -> dict[str, Any]:
    """List requestable resource pools for one catalog field context."""

    try:
        result = await execute(
            ctx,
            list_resource_bundles_operation,
            ResourceBundleQuery(
                business_group_id=business_group_id,
                component_type=component_type,
                node_type=node_type,
                cloud_entry_type_id=cloud_entry_type_id or "",
            ),
        )
        return tool_result(
            result,
            summary=f"Found {len(result.items)} resource pools.",
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
    catalog_id: str | None = None,
    node_template_name: str | None = None,
) -> dict[str, Any]:
    """List compute flavors after normalizing omitted AtlasClaw fields."""

    try:
        result = await execute(
            ctx,
            list_flavors_operation,
            FlavorQuery(
                query_value=query or "",
                resource_bundle_id=resource_bundle_id or "",
                catalog_id=catalog_id or "",
                node_template_name=node_template_name or "",
            ),
        )
        return tool_result(
            result,
            summary=f"Found {len(result.items)} compute flavors.",
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
