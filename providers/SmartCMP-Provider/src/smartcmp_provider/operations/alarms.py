"""SmartCMP alarm evidence reads and confirmed alert-state updates."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlencode

from smartcmp_provider.capabilities import capability_by_id
from smartcmp_provider.domain.alarms import (
    available_alert_operations,
    map_action_to_status,
)
from smartcmp_provider.domain.object_operations import serialize_available_operations
from smartcmp_provider.errors import (
    SmartCmpAuthenticationError,
    SmartCmpError,
    SmartCmpPermissionError,
    SmartCmpRateLimitError,
    SmartCmpTargetResolutionError,
    SmartCmpUnknownOutcomeError,
    SmartCmpUpstreamError,
    SmartCmpValidationError,
)
from smartcmp_provider.models.alarms import (
    AlarmAnalysisFactsQuery,
    AlarmAnalysisFactsResult,
    AlarmListQuery,
    AlarmListResult,
    AlarmMetricGroupsQuery,
    AlarmOperationInput,
    AlarmOperationResult,
    AlarmPayloadResult,
    AlarmResourceMonitorQuery,
)
from smartcmp_provider.transport.client import SmartCmpClient
from smartcmp_provider.transport.mutations import write_result_is_unknown

OPERATE_ALERT_CAPABILITY = capability_by_id("smartcmp.alarms.operate")


async def list_alarms(
    client: SmartCmpClient,
    query: AlarmListQuery,
) -> AlarmListResult:
    """List raw SmartCMP alert facts using existing filter semantics."""

    encoded_filters = urlencode(dict(query.filters), doseq=True)
    path = (
        f"/alarm-alert?query&{encoded_filters}"
        if encoded_filters
        else "/alarm-alert?query"
    )
    payload = await client.request_json("GET", path)
    items = tuple(_attach_available_operations(item) for item in _extract_items(payload))
    return AlarmListResult(
        items=items,
        total=_extract_total(payload),
    )


def _attach_available_operations(item: dict[str, Any]) -> dict[str, Any]:
    """Attach neutral state-valid operations to one raw alert result."""

    enriched = dict(item)
    enriched["available_operations"] = serialize_available_operations(
        available_alert_operations(enriched)
    )
    return enriched


async def get_alarm_analysis_facts(
    client: SmartCmpClient,
    query: AlarmAnalysisFactsQuery,
) -> AlarmAnalysisFactsResult:
    """Load one alert, its policy, and bounded optional analysis context."""

    alert_id = query.alert_id.strip()
    alert_payload = await client.request_json(
        "GET",
        f"/alarm-alert/{quote(alert_id, safe='')}",
    )
    if not isinstance(alert_payload, dict) or not alert_payload:
        raise SmartCmpTargetResolutionError(
            f"Alert '{alert_id}' was not found.",
            trace_id=client.request.context.trace_id,
        )

    policy_id = str(alert_payload.get("alarmPolicyId") or "").strip()
    if not policy_id:
        raise SmartCmpTargetResolutionError(
            f"Alert '{alert_id}' does not reference an alarm policy.",
            trace_id=client.request.context.trace_id,
        )
    policy_payload = await client.request_json(
        "GET",
        f"/alarm-policies/{quote(policy_id, safe='')}",
    )
    if not isinstance(policy_payload, dict) or not policy_payload:
        raise SmartCmpTargetResolutionError(
            f"Alarm policy '{policy_id}' was not found for alert '{alert_id}'.",
            trace_id=client.request.context.trace_id,
        )

    detail = {
        "recent_overview": await _optional_read(
            client,
            "/alarm-overview/recent",
        ),
        "alarm_trend": await _optional_read(
            client,
            "/alarm-overview/alarm-trend",
            params={"days": query.days},
        ),
        "alert_detail_stats": await _optional_read(
            client,
            "/stats/alarm-alert/detail",
            params={"alertId": alert_id},
        ),
    }
    return AlarmAnalysisFactsResult(
        alert=alert_payload,
        policy=policy_payload,
        detail=detail,
    )


async def get_alarm_metric_groups(
    client: SmartCmpClient,
    query: AlarmMetricGroupsQuery,
) -> AlarmPayloadResult:
    """Load component monitoring-model metric groups."""

    component_type = query.component_type.strip()
    payload = await client.request_json(
        "GET",
        "/alarm-policies/alarm-metric-groups",
        params={"resourceType": component_type},
    )
    return AlarmPayloadResult(payload=payload)


async def get_resource_monitor_binding(
    client: SmartCmpClient,
    query: AlarmResourceMonitorQuery,
) -> AlarmPayloadResult:
    """Load the monitor binding for one explicit SmartCMP resource."""

    resource_id = query.resource_id.strip()
    payload = await client.request_json(
        "GET",
        f"/nodes/{quote(resource_id, safe='')}/monitor",
    )
    return AlarmPayloadResult(payload=payload)


async def get_monitor_api_url(client: SmartCmpClient) -> AlarmPayloadResult:
    """Load the CMP-managed monitoring API URL as JSON or plain text."""

    payload = await client.request_json_or_text("GET", "/monitor/api_url")
    return AlarmPayloadResult(payload=payload)


async def execute_alarm_operation(
    client: SmartCmpClient,
    operation_input: AlarmOperationInput,
) -> AlarmOperationResult:
    """Submit one confirmed alert-state update exactly once.

    Args:
        client: Client bound to the acting user or robot credential.
        operation_input: Alert IDs and validated state-transition action.

    Returns:
        Submitted action facts and the upstream response.

    Raises:
        SmartCmpValidationError: If an alert ID is blank.
        SmartCmpUnknownOutcomeError: If the write may have reached SmartCMP.
        SmartCmpError: If SmartCMP definitely rejects the operation.
    """

    alert_ids = tuple(str(item).strip() for item in operation_input.alert_ids)
    if any(not item for item in alert_ids):
        raise SmartCmpValidationError(
            "Alert IDs must not be empty.",
            trace_id=client.request.context.trace_id,
        )
    status = map_action_to_status(operation_input.action)
    try:
        payload = await client.request_json(
            "PUT",
            "/alarm-alert/operation",
            json_body={"ids": list(alert_ids), "status": status},
            allow_empty=True,
        )
    except SmartCmpError as exc:
        if write_result_is_unknown(exc):
            raise SmartCmpUnknownOutcomeError(
                "SmartCMP alert operation outcome is unknown; do not retry "
                f"automatically. {exc}",
                trace_id=client.request.context.trace_id,
            ) from exc
        raise
    return AlarmOperationResult(
        alert_ids=alert_ids,
        action=operation_input.action,
        status=status,
        response=payload,
    )


async def _optional_read(
    client: SmartCmpClient,
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> Any:
    try:
        return await client.request_json("GET", path, params=params)
    except (
        SmartCmpAuthenticationError,
        SmartCmpPermissionError,
        SmartCmpRateLimitError,
    ):
        raise
    except SmartCmpError:
        return None


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        raise SmartCmpUpstreamError(
            "SmartCMP returned an unexpected alert list payload."
        )
    for key in ("content", "data", "items", "result"):
        if key not in payload:
            continue
        value = payload[key]
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            return _extract_items(value)
        raise SmartCmpUpstreamError(
            "SmartCMP returned an unexpected alert list payload."
        )
    raise SmartCmpUpstreamError(
        "SmartCMP returned an unexpected alert list payload."
    )


def _extract_total(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    for key in ("totalElements", "total", "totalCount", "count"):
        try:
            return int(payload.get(key))
        except (TypeError, ValueError):
            pass
    for key in ("data", "result"):
        nested = _extract_total(payload.get(key))
        if nested is not None:
            return nested
    return None
