"""AtlasClaw Tool adapters for SmartCMP resource reads and day-2 actions."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Literal


_SHARED_SCRIPTS = Path(__file__).resolve().parents[2] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

_SECURITY_SCRIPTS = (
    Path(__file__).resolve().parents[2] / "security-compliance" / "scripts"
)
if str(_SECURITY_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SECURITY_SCRIPTS))

from _atlasclaw_adapter import (  # noqa: E402
    RunContext,
    execute,
    execute_with_request,
    split_values,
    tool_error,
    tool_result,
)
from _resource_object_actions import attach_resource_object_metadata  # noqa: E402
from _security_object_actions import (  # noqa: E402
    attach_security_violation_object_metadata,
)
from smartcmp_provider.domain.resource_resolution import (  # noqa: E402
    parse_resource_directory,
    parse_resource_reference,
    resolve_single_resource,
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
from smartcmp_provider.models.security_compliance import (  # noqa: E402
    ResourceSecurityAnalysisQuery,
    ResourceSecurityViolationQuery,
)
from smartcmp_provider.operations.resource_actions import (  # noqa: E402
    execute_resource_action,
)
from smartcmp_provider.operations.resources import list_resources  # noqa: E402
from smartcmp_provider.services.resources import (  # noqa: E402
    get_resource_detail_view,
    get_resource_operations_view,
)
from smartcmp_provider.services import security_compliance as security_service  # noqa: E402


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


async def analyze_resource_security(
    ctx: RunContext[Any],
    resource_name: str = "",
    resource_index: int | None = None,
    resource_directory_json: str = "",
    resource_id: str = "",
) -> dict[str, Any]:
    """Collect resource facts and associated Security violations for LLM analysis.

    Args:
        ctx: AtlasClaw request context for the selected SmartCMP instance.
        resource_name: Exact visible resource name for interactive resolution.
        resource_index: Visible row number from recent resource metadata.
        resource_directory_json: Hidden directory metadata used to resolve an
            index or validate a listed name without exposing its UUID.
        resource_id: Trusted internal Resource ID from object context.

    Returns:
        Resource facts, CMP-confirmed Security violations, LLM posture evidence,
        missing evidence, and manual remediation guidance.
    """

    try:
        selected_resource_id = await _resolve_security_resource_id(
            ctx,
            resource_name=resource_name,
            resource_index=resource_index,
            resource_directory_json=resource_directory_json,
            resource_id=resource_id,
        )
        result = await execute(
            ctx,
            security_service.analyze_resource_security,
            ResourceSecurityAnalysisQuery(resource_id=selected_resource_id),
        )
        return tool_result(
            result,
            summary="Collected resource Security posture and violation evidence.",
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def list_resource_security_violations(
    ctx: RunContext[Any],
    resource_name: str = "",
    resource_index: int | None = None,
    resource_directory_json: str = "",
    resource_id: str = "",
    max_pages: int = 50,
) -> dict[str, Any]:
    """List Security violations associated with one exact SmartCMP resource.

    Args:
        ctx: AtlasClaw request context for the selected SmartCMP instance.
        resource_name: Exact visible resource name for interactive resolution.
        resource_index: Visible row number from recent resource metadata.
        resource_directory_json: Hidden directory metadata used to resolve an
            index or validate a listed name without exposing its UUID.
        resource_id: Trusted internal Resource ID from object context.
        max_pages: Maximum root-SECURITY pages to scan, from 1 through 50.

    Returns:
        Exact resource-ID matches plus complete, partial, or failed scan
        coverage. Each item retains its real violation ID in object metadata.
    """

    try:
        selected_resource_id = await _resolve_security_resource_id(
            ctx,
            resource_name=resource_name,
            resource_index=resource_index,
            resource_directory_json=resource_directory_json,
            resource_id=resource_id,
        )
        result = await execute(
            ctx,
            security_service.list_resource_security_violations,
            ResourceSecurityViolationQuery(
                resource_id=selected_resource_id,
                max_pages=max_pages,
            ),
        )
        payload = result.model_dump(mode="json")
        payload["items"] = [
            attach_security_violation_object_metadata(item)
            for item in payload.get("items", [])
        ]
        return tool_result(
            payload,
            summary=_resource_security_summary(payload),
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


def _resource_security_summary(payload: dict[str, Any]) -> str:
    """Describe exact matches without overstating incomplete scan coverage."""

    item_count = len(payload.get("items") or [])
    coverage = str(payload.get("coverage") or "unknown").strip().lower()
    if item_count:
        return (
            f"Found {item_count} associated Security violations; "
            f"scan coverage is {coverage}."
        )
    if coverage == "partial":
        return (
            "No associated Security violations were found in the scanned pages; "
            "the inventory is incomplete."
        )
    if coverage == "failed":
        return (
            "Security violation collection failed; no conclusion can be made about "
            "whether this resource has associated violations."
        )
    return (
        "Found 0 associated Security violations; "
        f"scan coverage is {coverage}."
    )


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


async def _resolve_security_resource_id(
    ctx: RunContext[Any],
    *,
    resource_name: str,
    resource_index: int | None,
    resource_directory_json: str,
    resource_id: str,
) -> str:
    """Resolve exactly one resource for Security analysis and correlation."""

    normalized_id = str(resource_id or "").strip()
    if normalized_id:
        return normalized_id
    resolved_id, _resolved_name = await _resolve_resource_for_security(
        ctx,
        resource_name=resource_name,
        resource_index=resource_index,
        resource_directory_json=resource_directory_json,
    )
    return resolved_id


async def _resolve_resource_for_security(
    ctx: RunContext[Any],
    *,
    resource_name: str,
    resource_index: int | None,
    resource_directory_json: str,
) -> tuple[str, str]:
    """Resolve an interactive name or recent visible index to one resource ID."""

    directory = parse_resource_directory(resource_directory_json)
    if resource_index is not None or directory:
        return resolve_single_resource(
            resource_id_value="",
            resource_name=resource_name,
            resource_index=resource_index,
            directory_items=directory,
        )
    detail = await execute(
        ctx,
        get_resource_detail_view,
        ResourceDetailQuery(resource_name=resource_name),
    )
    return detail.resource_id, detail.name or resource_name
