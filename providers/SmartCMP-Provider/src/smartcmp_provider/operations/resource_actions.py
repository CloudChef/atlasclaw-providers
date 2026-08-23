"""Confirmed, user-scoped SmartCMP resource action execution."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from smartcmp_provider.capabilities import capability_by_id
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
from smartcmp_provider.operations.resources import (
    resource_operation_rejection_reason,
)
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
    """Validate and submit an explicitly Agent-supported resource action once.

    Every target is checked through the current credential's authoritative
    operation endpoint immediately before submission. The POST is never retried; an
    indeterminate transport result is surfaced as an unknown outcome.

    Args:
        client: Client bound to the acting user or robot.
        action_input: Confirmed resource targets and operation ID.

    Returns:
        Sanitized submission facts.

    Raises:
        SmartCmpValidationError: If the action is absent, disabled, web-only,
            or outside the Agent's explicit supported resource-operation set.
        SmartCmpUnknownOutcomeError: If the write may have reached SmartCMP.
        SmartCmpError: If SmartCMP definitely rejects the request.
    """

    action = str(action_input.action or "").strip()
    if not action:
        raise SmartCmpValidationError(
            "action is required.",
            trace_id=client.request.context.trace_id,
        )
    if action == "permanently_delete_deployment":
        raise SmartCmpValidationError(
            "Permanent deletion is available only through the dedicated "
            "smartcmp_permanently_remove_recycled_resource, which resolves the "
            "owning recycled deployment and requires explicit confirmation.",
            trace_id=client.request.context.trace_id,
        )

    resource_ids: list[str] = []
    categories: set[str] = set()
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
                if str(item.get("id") or "").strip() == action
            ),
            None,
        )
        if operation is None:
            raise SmartCmpValidationError(
                f"Operation '{action}' is not available for resource "
                f"{resource_id} under category {category}.",
                trace_id=client.request.context.trace_id,
            )
        reason = resource_operation_rejection_reason(operation)
        if reason:
            raise SmartCmpValidationError(
                f"Operation '{action}' is not executable for resource "
                f"{resource_id}: {reason}",
                trace_id=client.request.context.trace_id,
            )
        categories.add(category.casefold())
        if resource_id not in resource_ids:
            resource_ids.append(resource_id)
            selected_operations.append(operation)

    if len(resource_ids) > 1 and any(
        operation.get("supportBatchAction") is not True
        for operation in selected_operations
    ):
        raise SmartCmpValidationError(
            f"Operation '{action}' does not support batch execution for every "
            "selected resource.",
            trace_id=client.request.context.trace_id,
        )

    if len(categories) != 1:
        raise SmartCmpValidationError(
            "A single operation cannot mix deployments and node resources.",
            trace_id=client.request.context.trace_id,
        )

    if categories == {"deployments"}:
        await submit_deployment_actions_once(
            client,
            operations=tuple(
                (resource_id, str(operation.get("id") or ""))
                for resource_id, operation in zip(
                    resource_ids, selected_operations, strict=True
                )
            ),
        )
    else:
        payload = {
            "operationId": action,
            "resourceIds": (
                resource_ids[0]
                if len(resource_ids) == 1
                else ",".join(resource_ids)
            ),
            "scheduledTaskMetadataRequest": _schedule_metadata(),
        }
        await _submit_resource_operation_once(
            client,
            path="/nodes/resource-operations",
            payload=payload,
        )
    return ResourceActionResult(
        action=action,
        resource_ids=tuple(resource_ids),
        message=f"SmartCMP {action} request submitted.",
        verification_hint=(
            "Refresh the resource list or resource detail to confirm the latest state."
        ),
    )


async def submit_deployment_actions_once(
    client: SmartCmpClient,
    *,
    operations: tuple[tuple[str, str], ...],
    recycled: bool = False,
) -> Any:
    """Submit already-authorized deployment operations in one non-retried write.

    Args:
        client: Client bound to the acting SmartCMP principal.
        operations: ``(deployment_id, operation_id)`` pairs authorized through
            the current-user action endpoint immediately before this call.
        recycled: Include SmartCMP's recycle-bin flags for permanent removal.

    Returns:
        The validated SmartCMP response payload. Callers that need stronger
        acceptance evidence must inspect the operation-specific response shape.

    Raises:
        SmartCmpUnknownOutcomeError: If the request may have reached SmartCMP.
        SmartCmpError: If SmartCMP definitely rejects the submission.
    """

    payload = {
        deployment_id: {
            "operationName": operation_id,
            "scheduledTaskMetadataRequest": _schedule_metadata(),
            "operationParamJson": json.dumps(
                {"systemForm": None}, separators=(",", ":")
            ),
            **({"recycle": True, "manual": True} if recycled else {}),
        }
        for deployment_id, operation_id in operations
    }
    response_payload = await _submit_resource_operation_once(
        client,
        path="/deployments/execute-action",
        payload=payload,
    )
    _validate_batch_execution_response(
        client,
        response_payload,
        deployment_ids=tuple(deployment_id for deployment_id, _ in operations),
    )
    return response_payload


def _schedule_metadata() -> dict[str, Any]:
    return {
        "cronExpression": "",
        "cycleDescription": "",
        "cycled": False,
        "scheduleEnabled": False,
        "scheduledTime": None,
    }


async def _submit_resource_operation_once(
    client: SmartCmpClient,
    *,
    path: str,
    payload: dict[str, Any],
) -> Any:
    try:
        response_payload = await client.request_json(
            "POST",
            path,
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
    return response_payload


async def _fetch_current_user_operations(
    client: SmartCmpClient,
    *,
    category: str,
    resource_id: str,
) -> list[dict[str, Any]]:
    if category.casefold() == "deployments":
        path = (
            f"/deployments/{quote(resource_id, safe='')}"
            "/deployment-actions"
        )
    else:
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
    explicit_error = str(
        payload.get("error")
        or payload.get("errMsg")
        or payload.get("errorMessage")
        or ""
    ).strip()
    if explicit_error:
        return explicit_error
    message = str(payload.get("message") or "").strip()
    success = payload.get("success")
    if success is False or str(success or "").casefold() == "false":
        return message or "SmartCMP reported operation failure."
    state = str(
        payload.get("status") or payload.get("state") or payload.get("outcome") or ""
    ).casefold()
    if state in _FAILED_STATES:
        return message or f"SmartCMP reported operation state: {state}."
    code = payload.get("code")
    if (
        code not in (None, "", 0, "0", 200, "200")
        and str(code).casefold() not in {"ok", "success"}
    ):
        return message or f"SmartCMP returned business code: {code}."
    return ""


def _validate_batch_execution_response(
    client: SmartCmpClient,
    payload: Any,
    *,
    deployment_ids: tuple[str, ...],
) -> None:
    """Require one non-failed acknowledgement for every submitted deployment."""

    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, dict):
        raise SmartCmpUnknownOutcomeError(
            "SmartCMP deployment operation outcome is unknown because the "
            "submission response has no BatchExecutionResponse.results; do not "
            "retry automatically.",
            trace_id=client.request.context.trace_id,
        )
    for deployment_id in deployment_ids:
        if (
            deployment_id not in results
            or not isinstance(results[deployment_id], dict)
            or not results[deployment_id]
        ):
            raise SmartCmpUnknownOutcomeError(
                "SmartCMP deployment operation outcome is unknown because the "
                f"submission response did not acknowledge deployment '{deployment_id}'; "
                "do not retry automatically.",
                trace_id=client.request.context.trace_id,
            )
        business_error = _resource_business_error(results[deployment_id])
        if business_error:
            raise SmartCmpUpstreamError(
                f"SmartCMP deployment '{deployment_id}' operation failed: "
                f"{business_error}",
                trace_id=client.request.context.trace_id,
            )
