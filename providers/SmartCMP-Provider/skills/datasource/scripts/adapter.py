"""AtlasClaw Tool adapters for SmartCMP directory and datasource lookups."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


_SHARED_SCRIPTS = Path(__file__).resolve().parents[2] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from _atlasclaw_adapter import (  # noqa: E402
    RunContext,
    execute,
    tool_error,
    tool_result,
)
from smartcmp_provider.models.catalogs import (  # noqa: E402
    ImageQuery,
    LogicalTemplateQuery,
)
from smartcmp_provider.models.directory import (  # noqa: E402
    ApplicationListQuery,
    ComponentListQuery,
    DirectorySearchQuery,
)
from smartcmp_provider.operations.catalogs import (  # noqa: E402
    list_images as list_images_operation,
    list_logical_templates as list_logical_templates_operation,
)
from smartcmp_provider.operations.directory import (  # noqa: E402
    list_applications as list_applications_operation,
    list_business_group_directory,
    list_components as list_components_operation,
)


async def list_all_business_groups(
    ctx: RunContext[Any],
    query_value: str | None = None,
    page: int = 1,
    size: int = 65_535,
) -> dict[str, Any]:
    """List business groups visible to the selected SmartCMP principal."""

    try:
        result = await execute(
            ctx,
            list_business_group_directory,
            DirectorySearchQuery(
                query_value=query_value or "",
                page=page,
                size=size,
            ),
        )
        return tool_result(
            result,
            summary=f"Found {result.total or len(result.items)} business groups.",
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def list_applications(
    ctx: RunContext[Any],
    business_group_id: str,
) -> dict[str, Any]:
    """List applications for one explicit SmartCMP business group."""

    try:
        result = await execute(
            ctx,
            list_applications_operation,
            ApplicationListQuery(business_group_id=business_group_id),
        )
        return tool_result(
            result,
            summary=f"Found {result.total or len(result.items)} applications.",
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def list_components(
    ctx: RunContext[Any],
    source_key: str,
) -> dict[str, Any]:
    """List component metadata for one explicit SmartCMP resource type."""

    try:
        result = await execute(
            ctx,
            list_components_operation,
            ComponentListQuery(source_key=source_key),
        )
        return tool_result(
            result,
            summary=f"Found {result.total or len(result.items)} components.",
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def list_logical_templates(
    ctx: RunContext[Any],
    query: str | None = None,
    resource_bundle_id: str | None = None,
    catalog_id: str | None = None,
    node_template_name: str | None = None,
    os_type: str | None = None,
) -> dict[str, Any]:
    """List logical templates after normalizing omitted AtlasClaw fields."""

    try:
        result = await execute(
            ctx,
            list_logical_templates_operation,
            LogicalTemplateQuery(
                query_value=query or "",
                resource_bundle_id=resource_bundle_id or "",
                catalog_id=catalog_id or "",
                node_template_name=node_template_name or "",
                os_type=os_type or "",
            ),
        )
        return tool_result(
            result,
            summary=f"Found {len(result.items)} logical templates.",
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def list_images(
    ctx: RunContext[Any],
    resource_bundle_id: str,
    logic_template_id: str,
    cloud_entry_type: str,
) -> dict[str, Any]:
    """List images for one resource-pool and logical-template selection."""

    try:
        result = await execute(
            ctx,
            list_images_operation,
            ImageQuery(
                resource_bundle_id=resource_bundle_id,
                logic_template_id=logic_template_id,
                cloud_entry_type=cloud_entry_type,
            ),
        )
        return tool_result(
            result,
            summary=f"Found {len(result.items)} images.",
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)
