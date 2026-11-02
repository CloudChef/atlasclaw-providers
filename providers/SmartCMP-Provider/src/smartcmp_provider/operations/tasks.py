"""Read task execution facts without treating asynchronous submission as success."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from smartcmp_provider.errors import SmartCmpUpstreamError, SmartCmpValidationError
from smartcmp_provider.transport.client import SmartCmpClient


def task_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    """Project a GenericTask into safe status and correlation facts.

    Args:
        payload: A GenericTask object from CMP.
    Returns:
        Status, success and target facts; SUBMITTED remains incomplete.
    """
    state = str(payload.get("state") or "").upper()
    failed = state in {"FAILED", "CANCELLED", "APPROVAL_REJECTED"}
    return {
        "task_id": str(payload.get("id") or ""), "state": state,
        "completed": state == "FINISHED" or failed, "succeeded": state == "FINISHED",
        "outcome": "failed" if failed else "succeeded" if state == "FINISHED" else "approval_pending" if state == "PRE_EXTERNAL_STEP" else "running",
        "error": SmartCmpClient.sanitize_error_text(str(payload.get("resultMsg") or "")) if failed else "",
        "deployment_id": str(payload.get("deploymentId") or ""),
        "request_id": str(payload.get("genericRequestId") or ""),
        "resource_ids": payload.get("resourceIds") or [],
        "operation_name": str(payload.get("operationName") or ""),
        "execution_id": str(payload.get("executionId") or ""),
        "permanent_removal": bool(payload.get("deploymentId"))
            and (payload.get("exts") or {}).get("permanently_delete_deployment") == payload.get("deploymentId"),
    }


async def get_task(client: SmartCmpClient, task_id: str) -> dict[str, Any]:
    """Read an exact task with the current caller's permissions.

    Args:
        client: Credential-scoped client.
        task_id: Internal task ID.
    Returns:
        Safe normalized task facts.
    Raises:
        SmartCmpError: For invalid IDs, failed reads or malformed responses.
    """
    if not task_id:
        raise SmartCmpValidationError("task_id is required.")
    payload = await client.request_json("GET", f"/tasks/{quote(task_id, safe='')}")
    if not isinstance(payload, dict) or payload.get("id") != task_id:
        raise SmartCmpUpstreamError("Task lookup did not return the requested task.")
    return task_snapshot(payload)
