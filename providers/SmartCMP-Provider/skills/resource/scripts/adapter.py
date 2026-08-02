"""AtlasClaw Tool adapters for SmartCMP resource reads and day-2 actions."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Literal


_SHARED_SCRIPTS = Path(__file__).resolve().parents[2] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from _atlasclaw_adapter import (  # noqa: E402
    RunContext,
    execute,
    execute_with_request,
    split_values,
    tool_error,
    tool_result,
)
from _resource_object_actions import attach_resource_object_metadata  # noqa: E402
from smartcmp_provider.domain.resource_resolution import (  # noqa: E402
    parse_resource_reference,
)
from smartcmp_provider.models.operations import (  # noqa: E402
    ResourceActionInput,
    ResourceActionTarget,
)
from smartcmp_provider.models.resources import (  # noqa: E402
    ResourceDetailQuery,
    ResourceListQuery,
    ResourceOperationsQuery,
)
from smartcmp_provider.operations.resource_actions import (  # noqa: E402
    execute_resource_action,
)
from smartcmp_provider.operations.resources import list_resources  # noqa: E402
from smartcmp_provider.services.resources import (  # noqa: E402
    get_resource_detail_view,
    get_resource_operations_view,
)


async def list_all_resource(
    ctx: RunContext[Any],
    scope: Literal["all_resources", "virtual_machines"] = "all_resources",
    query_value: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """List SmartCMP resources in the requested standalone browsing scope."""

    try:
        result, request = await execute_with_request(
            ctx,
            list_resources,
            ResourceListQuery(
                scope=scope,
                query_value=query_value,
                page=page,
                size=size,
            ),
        )
        category = (
            "virtual-machines"
            if scope == "virtual_machines"
            else "cloud-resource"
        )
        result = result.model_copy(
            update={
                "items": tuple(
                    attach_resource_object_metadata(
                        item,
                        ui_base_url=request.context.instance.ui_base_url,
                        category=category,
                        include_detail_action=True,
                        include_operations_action=True,
                    )
                    for item in result.items
                )
            }
        )
        return tool_result(
            result,
            summary=f"Found {result.total or len(result.items)} resources.",
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def resource_detail(
    ctx: RunContext[Any],
    resource_id: str | None = None,
    resource_name: str | None = None,
    category: str = "virtual-machines",
) -> dict[str, Any]:
    """Return one normalized SmartCMP resource detail view."""

    try:
        result, request = await execute_with_request(
            ctx,
            get_resource_detail_view,
            ResourceDetailQuery(
                resource_id=resource_id or "",
                resource_name=resource_name or "",
                category=category,
            ),
        )
        projected = attach_resource_object_metadata(
            result.model_dump(mode="json"),
            ui_base_url=request.context.instance.ui_base_url,
            category=category,
            include_detail_action=False,
            include_operations_action=True,
        )
        return tool_result(
            projected,
            summary=(
                f"Resource {result.name or result.resource_id}: "
                f"{result.status or 'status unavailable'}."
            ),
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def list_resource_operations(
    ctx: RunContext[Any],
    resource_ref: str,
    category: str = "virtual-machines",
) -> dict[str, Any]:
    """List current-user operations for one resource ID or SmartCMP URL."""

    try:
        resolved_category, resource_id = parse_resource_reference(
            resource_ref,
            default_category=category,
        )
        result, request = await execute_with_request(
            ctx,
            get_resource_operations_view,
            ResourceOperationsQuery(
                category=resolved_category,
                resource_id=resource_id,
            ),
        )
        projected = attach_resource_object_metadata(
            result.model_dump(mode="json"),
            ui_base_url=request.context.instance.ui_base_url,
            category=resolved_category,
            include_detail_action=True,
            include_operations_action=False,
        )
        return tool_result(
            projected,
            summary=f"Found {len(result.operations)} available operations.",
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def operate_resource(
    ctx: RunContext[Any],
    resource_ids: str | list[str],
    action: str,
    category: str = "virtual-machines",
) -> dict[str, Any]:
    """Execute one user-confirmed operation for explicit resource targets."""

    try:
        targets = tuple(
            ResourceActionTarget(
                category=resolved_category,
                resource_id=resource_id,
            )
            for resolved_category, resource_id in (
                parse_resource_reference(
                    resource_ref,
                    default_category=category,
                )
                for resource_ref in split_values(resource_ids)
            )
        )
        result = await execute(
            ctx,
            execute_resource_action,
            ResourceActionInput(targets=targets, action=action),
        )
        return tool_result(result, summary=result.message)
    except (ValueError, RuntimeError) as error:
        return tool_error(error)
