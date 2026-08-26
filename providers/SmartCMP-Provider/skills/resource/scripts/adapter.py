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
    list_workflow_internal,
    split_values,
    tool_error,
    tool_result,
    validate_list_page_size,
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
    PermanentResourceRemovalInput,
    RecycledResourceQuery,
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
from smartcmp_provider.operations.recycle_bin import (  # noqa: E402
    list_recycled_resources as list_recycled_resources_operation,
    permanently_remove_recycled_resource as permanently_remove_recycled_resource_operation,
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
        size = validate_list_page_size(size)
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
                        compact_prompts=True,
                    )
                    for item in result.items
                )
            }
        )
        return tool_result(
            result,
            summary=f"Found {result.total or len(result.items)} resources.",
            internal=list_workflow_internal(
                result.items,
                fields=("id", "name"),
                total=result.total,
                extra={
                    "category": category,
                    "pagination": {
                        "page": page,
                        "size": size,
                        "scope": scope,
                        "query_value": query_value,
                    },
                },
            ),
            request=request,
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
            request=request,
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def list_recycled_resources(
    ctx: RunContext[Any],
    resource_id: str = "",
    resource_name: str = "",
    deployment_id: str = "",
    deployment_name: str = "",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """List recycle-bin resources using an optional resource or deployment locator.

    Names remain exact-match data. The Provider returns every candidate rather
    than selecting an ambiguous resource or deployment for a later write.
    """

    try:
        size = validate_list_page_size(size, maximum=20)
        result, request = await execute_with_request(
            ctx,
            list_recycled_resources_operation,
            RecycledResourceQuery(
                resource_id=resource_id or "",
                resource_name=resource_name or "",
                deployment_id=deployment_id or "",
                deployment_name=deployment_name or "",
                page=page,
                size=size,
            ),
        )
        projection = _recycled_resource_agent_projection(result)
        return tool_result(
            projection,
            summary=f"Found {len(result.items)} recycled resource rows.",
            internal=_recycled_resource_workflow_projection(
                projection,
                query={
                    "resource_id": resource_id or "",
                    "resource_name": resource_name or "",
                    "deployment_id": deployment_id or "",
                    "deployment_name": deployment_name or "",
                    "page": page,
                    "size": size,
                },
            ),
            request=request,
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


def _recycled_resource_agent_projection(result: Any) -> dict[str, Any]:
    """Expose only the dedicated recycle-bin operation in Agent result shape."""

    source = result.model_dump(mode="json")
    projection = {
        "items": [],
        "total": source.get("total", 0),
        "page": source.get("page", 1),
        "size": source.get("size", 20),
    }
    for source_item in source.get("items", []):
        item = {
            key: source_item[key]
            for key in (
                "resource_id",
                "resource_name",
                "resource_type",
                "component_type",
                "status",
                "deployment_id",
                "deployment_name",
                "owning_deployment",
                "affected_scope",
            )
            if key in source_item
        }
        operations: list[dict[str, Any]] = []
        for operation in source_item.get("available_operations", []):
            operation_id = str(operation.get("operation_id") or "").strip()
            if operation_id != "permanently_delete_deployment":
                continue
            operations.append(
                {
                    "index": 1,
                    "id": operation_id,
                    "name": "Permanently Delete Deployment",
                    "name_zh": "从回收站删除",
                    "display_name": "从回收站删除",
                }
            )
        item["operations"] = operations
        projection["items"].append(item)
    return projection


def _recycled_resource_workflow_projection(
    projection: dict[str, Any],
    *,
    query: dict[str, Any],
) -> dict[str, Any]:
    """Retain exact permanent-removal scope without replaying full resource payloads.

    Recycle-bin rows can contain large cloud properties that exceed Core's
    trace-bound workflow-context budget.  The follow-up write only needs the
    deployment identity, complete resource identity set, current state, and
    authoritative permanent-removal operation shown to the user.
    """

    workflow_items: list[dict[str, Any]] = []
    deployment_scopes: dict[str, dict[str, Any]] = {}
    deployment_refs: dict[str, str] = {}
    for item in projection.get("items", []) or []:
        if not isinstance(item, dict):
            continue
        deployment_id = str(item.get("deployment_id") or "").strip()
        scope_ref = deployment_refs.setdefault(
            deployment_id,
            str(len(deployment_refs) + 1),
        )
        workflow_items.append(
            {
                "id": item.get("resource_id"),
                "name": item.get("resource_name"),
                "scope_ref": scope_ref,
            }
        )
        if not deployment_id or scope_ref in deployment_scopes:
            continue
        affected_scope = item.get("affected_scope")
        resource_ids = (
            affected_scope.get("resource_ids")
            if isinstance(affected_scope, dict)
            else ()
        )
        deployment_scopes[scope_ref] = {
            "deployment_id": deployment_id,
            "resource_ids": list(resource_ids or ()),
            "action_id": next(
                (
                    operation.get("id")
                    for operation in item.get("operations", [])
                    if isinstance(operation, dict) and operation.get("id")
                ),
                "",
            ),
        }

    return list_workflow_internal(
        workflow_items,
        fields=("id", "name", "scope_ref"),
        total=projection.get("total", 0),
        extra={
            "pagination": dict(query),
            "deployment_scopes": deployment_scopes,
        },
    )


async def permanently_remove_recycled_resource(
    ctx: RunContext[Any],
    expected_deployment_id: str,
    expected_resource_ids: list[str],
    resource_id: str = "",
    resource_name: str = "",
    deployment_id: str = "",
    deployment_name: str = "",
    confirmed: bool = False,
) -> dict[str, Any]:
    """Submit one irreversible recycle-bin removal after explicit confirmation.

    Exactly one resource or deployment locator is accepted. The Provider
    resolves the deployment and affected resources again, requires an exact
    match with the confirmed expected scope, rechecks the current user's
    recycle-bin action, and submits at most once.
    """

    try:
        result, request = await execute_with_request(
            ctx,
            permanently_remove_recycled_resource_operation,
            PermanentResourceRemovalInput(
                expected_deployment_id=expected_deployment_id,
                expected_resource_ids=tuple(expected_resource_ids),
                resource_id=resource_id or "",
                resource_name=resource_name or "",
                deployment_id=deployment_id or "",
                deployment_name=deployment_name or "",
                confirmed=confirmed,
            ),
        )
        return tool_result(result, summary=result.message, request=request)
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
        result, request = await execute_with_request(
            ctx,
            security_service.analyze_resource_security,
            ResourceSecurityAnalysisQuery(resource_id=selected_resource_id),
        )
        return tool_result(
            result,
            summary="Collected resource Security posture and violation evidence.",
            request=request,
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
        result, request = await execute_with_request(
            ctx,
            security_service.list_resource_security_violations,
            ResourceSecurityViolationQuery(
                resource_id=selected_resource_id,
                max_pages=max_pages,
            ),
        )
        payload = result.model_dump(mode="json")
        provider_instance_name = str(
            getattr(
                getattr(getattr(request, "context", None), "instance", None),
                "name",
                "",
            )
            or ""
        ).strip()
        payload["items"] = [
            attach_security_violation_object_metadata(
                item,
                provider_instance_name=provider_instance_name,
            )
            for item in payload.get("items", [])
        ]
        return tool_result(
            payload,
            summary=_resource_security_summary(payload),
            internal=list_workflow_internal(
                _security_violation_workflow_items(payload.get("items", [])),
                fields=("id", "name"),
                total=payload.get("matched_total"),
                extra={
                    "resource_id": selected_resource_id,
                    "scan_context": {
                        key: payload.get(key)
                        for key in (
                            "total",
                            "matched_total",
                            "scanned_pages",
                            "has_more",
                            "next_page",
                            "coverage",
                            "truncated",
                            "errors",
                        )
                    },
                    "max_pages": max_pages,
                },
            ),
            request=request,
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


def _security_violation_workflow_items(
    items: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Keep exact violation identities for resource-scoped analysis."""

    return [
        {
            "id": str(item.get("id") or item.get("violationId") or "").strip(),
            "name": str(item.get("policyName") or "").strip(),
        }
        for item in items
    ]


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
            request=request,
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
        result, request = await execute_with_request(
            ctx,
            execute_resource_action,
            ResourceActionInput(targets=targets, action=action),
        )
        return tool_result(result, summary=result.message, request=request)
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
