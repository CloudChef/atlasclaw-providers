"""Exact deployment scope and lifecycle facts for non-interactive callers."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from smartcmp_provider.errors import SmartCmpUpstreamError, SmartCmpValidationError
from smartcmp_provider.operations.tasks import get_task
from smartcmp_provider.transport.client import SmartCmpClient


async def get_deployment(client: SmartCmpClient, deployment_id: str) -> dict[str, Any]:
    """Read current scope and task evidence without interpreting absence as deletion.

    Args:
        client: Credential-scoped client.
        deployment_id: Exact deployment selected by the caller.
    Returns:
        Scope, current lifecycle state, final task and verified permanent-delete evidence.
    Raises:
        SmartCmpError: For missing access, absent objects or malformed scope data.
    """
    if not deployment_id:
        raise SmartCmpValidationError("deployment_id is required.")
    path = f"/deployments/{quote(deployment_id, safe='')}"
    resources = await client.request_json("GET", "/nodes/findByDepId",
        params={"deploymentId": deployment_id, "includeDeleted": True})
    if not isinstance(resources, list) or any(not isinstance(item, dict) or not item.get("id") for item in resources):
        raise SmartCmpUpstreamError("Deployment resource scope is incomplete.")
    if any(item.get("deploymentId") not in (None, "", deployment_id) for item in resources):
        raise SmartCmpUpstreamError("Deployment resource scope contains another deployment.")
    if resources and all(item.get("deleted") is True for item in resources):
        # The ordinary detail endpoint excludes deleted deployments. The deleted
        # endpoint requires both ID and name, so obtain the name from scoped records.
        names = {item.get("deploymentName") for item in resources}
        if len(names) != 1 or not next(iter(names)):
            raise SmartCmpUpstreamError("Deleted resource records do not identify one deployment name.")
        rows = await client.request_json("GET", "/deployments/deleted", params={
            "expand": "", "deploymentId": deployment_id, "deploymentName": next(iter(names))})
        if not isinstance(rows, list) or len(rows) != 1:
            raise SmartCmpUpstreamError("The deleted deployment cannot be reliably confirmed.")
        detail = rows[0]
    else:
        detail = await client.request_json("GET", path)
    if not isinstance(detail, dict) or detail.get("id") != deployment_id:
        raise SmartCmpUpstreamError("Deployment lookup did not return the requested deployment.")
    last_task_id = detail.get("lastTaskId")
    # The list projection omits exts, including the permanent-removal marker.
    tasks = [await get_task(client, last_task_id)] if last_task_id else []
    proof = [item for item in tasks if item["deployment_id"] == deployment_id
             and item["succeeded"] and item["permanent_removal"]]
    permanently_deleted = bool(proof and detail.get("deleted") is True
        and detail.get("state") in {"TORN_DOWN", "DELETED"}
        and all(item.get("deleted") is True for item in resources))
    safe_resources = [{key: item[key] for key in ("id", "name", "externalId", "deploymentId", "deleted", "recycled", "status") if key in item} for item in resources]
    return {
        "deployment_id": deployment_id, "name": detail.get("name", ""), "state": detail.get("state", ""),
        "recycled": detail.get("recycled") is True, "deleted": detail.get("deleted") is True,
        "resource_ids": sorted(item["id"] for item in resources), "resources": safe_resources,
        "last_task_id": last_task_id, "tasks": tasks, "permanently_deleted": permanently_deleted,
    }
