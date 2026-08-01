"""AtlasClaw Tool adapters for SmartCMP cost-optimization workflows."""

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
from _cost_object_actions import attach_cost_object_metadata  # noqa: E402
from smartcmp_provider.domain.resource_resolution import (  # noqa: E402
    parse_resource_directory,
    resolve_single_resource,
)
from smartcmp_provider.models.cost import (  # noqa: E402
    CostExecutionInput,
    CostExecutionStatusQuery,
    CostRecommendationFactsQuery,
    CostRecommendationListQuery,
    ResourceCostAnalysisQuery,
)
from smartcmp_provider.models.resources import ResourceDetailQuery  # noqa: E402
from smartcmp_provider.operations.cost import (  # noqa: E402
    execute_cost_optimization as execute_cost_optimization_operation,
)
from smartcmp_provider.services.cost_analysis import (  # noqa: E402
    analyze_cost_recommendation as analyze_cost_recommendation_operation,
    analyze_resource_cost as analyze_resource_cost_operation,
    list_cost_recommendations as list_cost_recommendations_operation,
)
from smartcmp_provider.services.cost_execution import (  # noqa: E402
    get_cost_execution_status,
)
from smartcmp_provider.services.resources import (  # noqa: E402
    get_resource_detail_view,
)


async def list_recommendations(
    ctx: RunContext[Any],
    status: str = "ACTIVED",
    severity: list[str] | None = None,
    category: str = "COST-OPTIMIZATION",
    query: str = "",
    page: int = 0,
    size: int = 20,
    with_related_policies: bool = False,
) -> dict[str, Any]:
    """List normalized SmartCMP cost recommendations."""

    filters: dict[str, Any] = {
        "queryValue": query,
        "sort": "lastExecuteDate,desc",
    }
    if status:
        filters["status"] = status
    if severity:
        filters["severity"] = severity
    if category:
        filters["category"] = category
    try:
        result = await execute(
            ctx,
            list_cost_recommendations_operation,
            CostRecommendationListQuery(
                filters=filters,
                page=page,
                size=size,
                include_related_policy_count=with_related_policies,
            ),
        )
        projected = result.model_copy(
            update={
                "items": tuple(
                    attach_cost_object_metadata(
                        item,
                        recommendation=item,
                        analyze_action_id="view_detail",
                    )
                    for item in result.items
                )
            }
        )
        return tool_result(
            projected,
            summary=(
                f"Found {result.total or len(result.items)} "
                "cost recommendations."
            ),
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def analyze_recommendation(
    ctx: RunContext[Any],
    violation_id: str,
) -> dict[str, Any]:
    """Analyze one SmartCMP cost recommendation and its resource evidence."""

    try:
        result = await execute(
            ctx,
            analyze_cost_recommendation_operation,
            CostRecommendationFactsQuery(violation_id=violation_id),
        )
        projected = attach_cost_object_metadata(
            result.model_dump(mode="json"),
            recommendation=result.facts,
            include_analysis_action=False,
        )
        return tool_result(
            projected,
            summary=f"Analyzed cost recommendation {result.violationId}.",
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def analyze_resource_cost(
    ctx: RunContext[Any],
    resource_name: str = "",
    resource_index: int | None = None,
    resource_directory_json: str = "",
    resource_id: str = "",
) -> dict[str, Any]:
    """Collect SmartCMP-confirmed cost evidence for one exact resource."""

    try:
        resolved_id, resolved_name = await _resolve_resource(
            ctx,
            resource_id=resource_id,
            resource_name=resource_name,
            resource_index=resource_index,
            resource_directory_json=resource_directory_json,
        )
        result = await execute(
            ctx,
            analyze_resource_cost_operation,
            ResourceCostAnalysisQuery(resource_id=resolved_id),
        )
        return tool_result(
            result,
            summary=f"Collected cost evidence for {resolved_name}.",
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def execute_optimization(
    ctx: RunContext[Any],
    violation_id: str,
) -> dict[str, Any]:
    """Submit one user-confirmed native SmartCMP cost remediation."""

    try:
        result = await execute(
            ctx,
            execute_cost_optimization_operation,
            CostExecutionInput(violation_id=violation_id),
        )
        return tool_result(result, summary=result.message)
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def track_execution(
    ctx: RunContext[Any],
    violation_id: str,
) -> dict[str, Any]:
    """Return aggregate execution status for one cost recommendation."""

    try:
        result = await execute(
            ctx,
            get_cost_execution_status,
            CostExecutionStatusQuery(violation_id=violation_id),
        )
        return tool_result(
            result,
            summary=(
                f"Violation {result.violationId}: "
                f"{result.overallStatus}."
            ),
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def _resolve_resource(
    ctx: Any,
    *,
    resource_id: str,
    resource_name: str,
    resource_index: int | None,
    resource_directory_json: str,
) -> tuple[str, str]:
    """Resolve a cost-analysis resource without exposing internal IDs."""

    directory = parse_resource_directory(resource_directory_json)
    if resource_id or resource_index is not None or directory:
        return resolve_single_resource(
            resource_id_value=resource_id,
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
