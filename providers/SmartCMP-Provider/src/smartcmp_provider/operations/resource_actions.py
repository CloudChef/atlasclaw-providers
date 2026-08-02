"""Confirmed, user-scoped SmartCMP resource action execution."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from smartcmp_provider.capabilities import capability_by_id
from smartcmp_provider.domain.resource_actions import normalize_operation_id
from smartcmp_provider.errors import (
    SmartCmpError,
    SmartCmpUnknownOutcomeError,
    SmartCmpUpstreamError,
    SmartCmpValidationError,
)
from smartcmp_provider.models.operations import (
    ResourceActionInput,
    ResourceActionResult,
)
from smartcmp_provider.operations.resources import operation_rejection_reason
from smartcmp_provider.transport.client import SmartCmpClient
from smartcmp_provider.transport.mutations import write_result_is_unknown

_FAILED_STATES = {
    "failed",
    "failure",
    "error",
    "rejected",
    "canceled",
    "cancelled",
}

LIST_RESOURCE_OPERATIONS_CAPABILITY = capability_by_id(
    "smartcmp.resources.operations"
)
OPERATE_RESOURCE_CAPABILITY = capability_by_id("smartcmp.resources.operate")


async def execute_resource_action(
    client: SmartCmpClient,
    action_input: ResourceActionInput,
) -> ResourceActionResult:
    """Validate and submit a no-parameter resource action exactly once.

    Every target is checked through the current credential's resource-actions
    endpoint immediately before submission. The POST is never retried; an
    indeterminate transport result is surfaced as an unknown outcome.

    Args:
        client: Client bound to the acting user or robot.
        action_input: Confirmed resource targets and operation ID.

    Returns:
        Sanitized submission facts.

    Raises:
        SmartCmpValidationError: If the action is absent, disabled, web-only,
            or requires form/parameter input for any target.
        SmartCmpUnknownOutcomeError: If the write may have reached SmartCMP.
        SmartCmpError: If SmartCMP definitely rejects the request.
    """

    action = normalize_operation_id(action_input.action)
    if not action:
        raise SmartCmpValidationError(
            "action is required.",
            trace_id=client.request.context.trace_id,
        )

    resource_ids: list[str] = []
    selected_operations: list[dict[str, Any]] = []
    for target in action_input.targets:
        category = target.category.strip()
        resource_id = target.resource_id.strip()
        if not category or not resource_id:
            raise SmartCmpValidationError(
                "Resource category and resource ID are required.",
                trace_id=client.request.context.trace_id,
            )
        operations = await _fetch_current_user_operations(
            client,
            category=category,
            resource_id=resource_id,
        )
        operation = next(
            (
                item
                for item in operations
                if normalize_operation_id(str(item.get("id") or "")) == action
            ),
            None,
        )
        if operation is None:
            raise SmartCmpValidationError(
                f"Operation '{action}' is not available for resource "
                f"{resource_id} under category {category}.",
                trace_id=client.request.context.trace_id,
            )
        reason = operation_rejection_reason(operation)
        if reason:
            raise SmartCmpValidationError(
                f"Operation '{action}' is not executable for resource "
                f"{resource_id}: {reason}",
                trace_id=client.request.context.trace_id,
            )
        selected_operations.append(operation)
        if resource_id not in resource_ids:
            resource_ids.append(resource_id)

    if len(resource_ids) > 1 and any(
        operation.get("supportBatchAction") is not True
        for operation in selected_operations
    ):
        raise SmartCmpValidationError(
            f"Operation '{action}' does not support batch execution for every "
            "selected resource.",
            trace_id=client.request.context.trace_id,
        )

    payload = {
        "operationId": action,
        "resourceIds": (
            resource_ids[0]
            if len(resource_ids) == 1
            else ",".join(resource_ids)
        ),
        "scheduledTaskMetadataRequest": {
            "cronExpression": "",
            "cycleDescription": "",
            "cycled": False,
            "scheduleEnabled": False,
            "scheduledTime": None,
        },
    }
    try:
        response_payload = await client.request_json(
            "POST",
            "/nodes/resource-operations",
            json_body=payload,
        )
    except SmartCmpError as exc:
        if write_result_is_unknown(exc):
            raise SmartCmpUnknownOutcomeError(
                "SmartCMP resource operation outcome is unknown; do not retry "
                f"automatically. {exc}",
                trace_id=client.request.context.trace_id,
            ) from exc
        raise

    business_error = _resource_business_error(response_payload)
    if business_error:
        raise SmartCmpUpstreamError(
            "SmartCMP business error: " + business_error,
            trace_id=client.request.context.trace_id,
        )
    return ResourceActionResult(
        action=action,
        resource_ids=tuple(resource_ids),
        message=f"SmartCMP {action} request submitted.",
        verification_hint=(
            "Refresh the resource list or resource detail to confirm the latest state."
        ),
    )


async def _fetch_current_user_operations(
    client: SmartCmpClient,
    *,
    category: str,
    resource_id: str,
) -> list[dict[str, Any]]:
    path = (
        f"/nodes/{quote(category, safe='')}/{quote(resource_id, safe='')}"
        "/resource-actions"
    )
    payload = await client.request_json("GET", path)
    if not isinstance(payload, list):
        raise SmartCmpUpstreamError(
            "SmartCMP returned an unexpected operation list payload.",
            trace_id=client.request.context.trace_id,
        )
    return [item for item in payload if isinstance(item, dict)]


def _resource_business_error(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    message = str(
        payload.get("message")
        or payload.get("error")
        or payload.get("errMsg")
        or ""
    ).strip()
    success = payload.get("success")
    if success is False or str(success or "").casefold() == "false":
        return message or "SmartCMP reported operation failure."
    state = str(payload.get("status") or payload.get("state") or "").casefold()
    if state in _FAILED_STATES:
        return message or f"SmartCMP reported operation state: {state}."
    code = payload.get("code")
    if (
        code not in (None, "", 0, "0", 200, "200")
        and str(code).casefold() not in {"ok", "success"}
    ):
        return message or f"SmartCMP returned business code: {code}."
    return ""
