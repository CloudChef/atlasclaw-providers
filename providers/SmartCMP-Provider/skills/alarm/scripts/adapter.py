"""AtlasClaw Tool adapters for SmartCMP alarms and resource health evidence."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Literal


_SHARED_SCRIPTS = Path(__file__).resolve().parents[2] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from _atlasclaw_adapter import (  # noqa: E402
    RunContext,
    execute,
    resolve_selected_provider_request,
    split_values,
    tool_error,
    tool_result,
)
from _alarm_object_actions import attach_alert_object_metadata  # noqa: E402
from smartcmp_provider.domain.alarms import build_list_params  # noqa: E402
from smartcmp_provider.domain.resource_resolution import (  # noqa: E402
    parse_resource_directory,
    resolve_single_resource,
)
from smartcmp_provider.models.alarms import (  # noqa: E402
    AlarmAnalysisFactsQuery,
    AlarmListQuery,
    AlarmOperationInput,
    ResourceAlertListQuery,
)
from smartcmp_provider.models.resources import ResourceDetailQuery  # noqa: E402
from smartcmp_provider.operations.alarms import (  # noqa: E402
    execute_alarm_operation,
    list_alarms as list_alarms_operation,
)
from smartcmp_provider.services.alarm_analysis import analyze_alarm  # noqa: E402
from smartcmp_provider.services.alarm_listing import (  # noqa: E402
    collect_resource_alerts,
)
from smartcmp_provider.services.resource_health import (  # noqa: E402
    collect_resource_health_context,
)
from smartcmp_provider.services.resources import (  # noqa: E402
    get_resource_detail_view,
)


async def list_alerts(
    ctx: RunContext[Any],
    status: str = "",
    days: int = 7,
    level: int | None = None,
    deployment_id: str = "",
    entity_instance_id: str = "",
    node_instance_id: str = "",
    alarm_type: str = "",
    alarm_category: str = "",
    query: str = "",
    target_entity_id: str = "",
    resource_name: str = "",
    resource_index: int | None = None,
    resource_directory_json: str = "",
    resource_id: str = "",
    resource_alert_scope: Literal[
        "current", "current_and_recent"
    ] = "current_and_recent",
    page: int = 1,
    size: int = 20,
) -> dict[str, Any]:
    """List general alerts or exact-resource lifecycle evidence."""

    try:
        resource_mode = bool(
            resource_id or resource_name or resource_index is not None
        )
        if resource_mode:
            resolved_id, resolved_name = await _resolve_resource(
                ctx,
                resource_id=resource_id,
                resource_name=resource_name,
                resource_index=resource_index,
                resource_directory_json=resource_directory_json,
            )
            result = await execute(
                ctx,
                collect_resource_alerts,
                ResourceAlertListQuery(
                    resource_id=resolved_id,
                    resource_name=resolved_name,
                    scope=resource_alert_scope,
                    days=days,
                    size=size,
                    level=level,
                    alarm_type=alarm_type,
                    alarm_categories=split_values(alarm_category),
                ),
            )
            projected = result.model_copy(
                update={
                    "items": tuple(
                        attach_alert_object_metadata(
                            item,
                            alert=item,
                            operations=(),
                            analyze_action_id="view_detail",
                        )
                        for item in result.items
                    )
                }
            )
            return tool_result(
                projected,
                summary=(
                    f"Found {len(result.items)} alerts for {resolved_name}; "
                    f"association coverage is "
                    f"{result.coverage.association_status}."
                ),
            )
        filters = build_list_params(
            page=page,
            size=size,
            statuses=status,
            days=days,
            level=level,
            deployment_id=deployment_id,
            entity_instance_id=entity_instance_id,
            node_instance_id=node_instance_id,
            target_entity_id=target_entity_id,
            alarm_type=alarm_type,
            alarm_categories=alarm_category,
            query=query,
        )
        result = await execute(
            ctx,
            list_alarms_operation,
            AlarmListQuery(filters=filters),
        )
        projected = result.model_copy(
            update={
                "items": tuple(
                    attach_alert_object_metadata(
                        item,
                        alert=item,
                        operations=(),
                        analyze_action_id="view_detail",
                    )
                    for item in result.items
                )
            }
        )
        return tool_result(
            projected,
            summary=f"Found {result.total or len(result.items)} alerts.",
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def analyze_alert(
    ctx: RunContext[Any],
    alert_id: str,
    days: int = 7,
) -> dict[str, Any]:
    """Analyze one SmartCMP alert through shared deterministic evidence rules."""

    try:
        result = await execute(
            ctx,
            analyze_alarm,
            AlarmAnalysisFactsQuery(alert_id=alert_id, days=days),
        )
        suggested_operation = str(
            result.suggested_status_operation.get("operation") or ""
        ).strip()
        facts = result.facts[0] if result.facts else {"id": alert_id}
        projected = attach_alert_object_metadata(
            result.model_dump(mode="json"),
            alert={**facts, "id": alert_id},
            operations=(suggested_operation,) if suggested_operation else (),
            include_analysis_action=False,
        )
        return tool_result(
            projected,
            summary=f"Analyzed SmartCMP alert {alert_id}.",
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def analyze_resource_health(
    ctx: RunContext[Any],
    resource_name: str = "",
    resource_index: int | None = None,
    resource_directory_json: str = "",
    resource_id: str = "",
    window_hours: int = 24,
) -> dict[str, Any]:
    """Collect component-model and Prometheus evidence for one resource."""

    try:
        resolved_id, resolved_name = await _resolve_resource(
            ctx,
            resource_id=resource_id,
            resource_name=resource_name,
            resource_index=resource_index,
            resource_directory_json=resource_directory_json,
        )
        request = await resolve_selected_provider_request(ctx)
        payload = await asyncio.to_thread(
            collect_resource_health_context,
            resource_id=resolved_id,
            resource_name=resolved_name,
            window_hours=window_hours,
            provider_request=request,
        )
        return tool_result(
            payload,
            summary=(
                f"Collected resource health evidence for {resolved_name}; "
                f"monitoring state is "
                f"{payload.get('monitoring_state', 'unknown')}."
            ),
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def operate_alert(
    ctx: RunContext[Any],
    alert_ids: str | list[str],
    action: Literal["mute", "resolve", "reopen"],
) -> dict[str, Any]:
    """Execute one user-confirmed status operation for explicit alert IDs."""

    try:
        result = await execute(
            ctx,
            execute_alarm_operation,
            AlarmOperationInput(
                alert_ids=split_values(alert_ids),
                action=action,
            ),
        )
        return tool_result(
            result,
            summary=(
                f"Applied {result.action} to "
                f"{len(result.alert_ids)} SmartCMP alerts."
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
    """Resolve a resource from trusted ID, recent directory, or exact name."""

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
