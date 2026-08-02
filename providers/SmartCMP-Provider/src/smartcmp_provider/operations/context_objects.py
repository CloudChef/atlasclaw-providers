"""Identity-scoped reads used by Agent adapters to describe SmartCMP objects."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from smartcmp_provider.errors import SmartCmpUpstreamError
from smartcmp_provider.models.objects import ObjectReadQuery
from smartcmp_provider.operations.objects import get_object_by_id
from smartcmp_provider.transport.client import SmartCmpClient


CATALOG_ENTITY_CLASS = "io.cloudchef.yacmp.core.catalog.Catalog"
RESOURCE_ENTITY_CLASS = "io.cloudchef.yacmp.core.resource.Resource"


async def read_form_definition(
    client: SmartCmpClient,
    object_id: str,
) -> dict[str, Any]:
    """Read one exact SmartCMP form definition for an adapter projection."""

    return await _read_designer_object(client, "form_definition", object_id)


async def read_script_definition(
    client: SmartCmpClient,
    object_id: str,
) -> dict[str, Any]:
    """Read one exact SmartCMP script definition for an adapter projection."""

    return await _read_designer_object(client, "script_definition", object_id)


async def read_optimization_policy(
    client: SmartCmpClient,
    object_id: str,
) -> dict[str, Any]:
    """Read one exact SmartCMP optimization policy for an adapter projection."""

    return await _read_designer_object(client, "optimization_policy", object_id)


async def read_component_definition(
    client: SmartCmpClient,
    object_id: str,
) -> dict[str, Any]:
    """Read one exact SmartCMP component definition for an adapter projection."""

    return await _read_designer_object(client, "component_definition", object_id)


async def read_alert(
    client: SmartCmpClient,
    alert_id: str,
) -> dict[str, Any]:
    """Read one SmartCMP alert selected by an immutable identifier."""

    return await _read_record(client, f"/alarm-alert/{_encoded(alert_id)}")


async def read_cost_recommendation(
    client: SmartCmpClient,
    recommendation_id: str,
) -> dict[str, Any]:
    """Read one SmartCMP cost recommendation selected by identifier."""

    return await _read_record(
        client,
        "/compliance-policies/violations/"
        f"{_encoded(recommendation_id)}",
    )


async def read_approval(
    client: SmartCmpClient,
    approval_id: str,
) -> dict[str, Any]:
    """Read one SmartCMP approval selected by its internal identifier."""

    return await _read_record(client, f"/approval/{_encoded(approval_id)}")


async def list_current_pending_approvals(
    client: SmartCmpClient,
    workflow_id: str,
) -> tuple[dict[str, Any], ...]:
    """List the current principal's pending rows for one visible Request ID."""

    payload = await client.request_json(
        "GET",
        "/generic-request/current-activity-approval",
        params={
            "page": 1,
            "size": 100,
            "stage": "pending",
            "states": "APPROVAL_PENDING",
            "sort": "updatedDate,desc",
            "searchValues": workflow_id,
        },
    )
    content = payload.get("content") if isinstance(payload, dict) else None
    if not isinstance(content, list):
        return ()
    return tuple(item for item in content if isinstance(item, dict))


async def read_catalog(
    client: SmartCmpClient,
    catalog_id: str,
) -> dict[str, Any]:
    """Read one SmartCMP catalog selected by its exact identifier."""

    return await _read_record(client, f"/catalogs/{_encoded(catalog_id)}")


async def read_request(
    client: SmartCmpClient,
    request_id: str,
) -> dict[str, Any]:
    """Read one SmartCMP generic request selected by internal identifier."""

    return await _read_record(client, f"/generic-request/{_encoded(request_id)}")


async def read_resource(
    client: SmartCmpClient,
    resource_id: str,
) -> dict[str, Any]:
    """Read one SmartCMP resource node selected by immutable identifier."""

    return await _read_record(client, f"/nodes/{_encoded(resource_id)}")


async def has_instance_permission(
    client: SmartCmpClient,
    entity_class: str,
    entity_id: str,
    permission: str,
) -> bool:
    """Check one effective instance or class permission for the current principal."""

    payload = await client.request_json(
        "GET",
        "/acl/queryCurrentUserPermissions",
        params={
            "entityClassNames": entity_class,
            "entityInstanceIds": entity_id,
        },
    )
    if not isinstance(payload, list):
        return False

    exact_entries: list[dict[str, Any]] = []
    class_entries: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        entity = item.get("entityClass")
        if (
            not isinstance(entity, dict)
            or _text(entity.get("className")) != entity_class
        ):
            continue
        instance_id = _text(entity.get("instanceId"))
        if instance_id == entity_id:
            exact_entries.append(item)
        elif instance_id in {"", "-1"}:
            class_entries.append(item)

    for item in exact_entries + class_entries:
        permissions = item.get("permissions")
        if not isinstance(permissions, list):
            continue
        permission_ids = {
            _text(value.get("id")) if isinstance(value, dict) else _text(value)
            for value in permissions
        }
        if permission in permission_ids:
            return True
    return False


async def _read_designer_object(
    client: SmartCmpClient,
    object_type: str,
    object_id: str,
) -> dict[str, Any]:
    result = await get_object_by_id(
        client,
        ObjectReadQuery(
            object_type=object_type,
            object_id=object_id,
        ),
    )
    return result.payload


async def _read_record(
    client: SmartCmpClient,
    path: str,
) -> dict[str, Any]:
    payload = await client.request_json("GET", path)
    if not isinstance(payload, dict):
        raise SmartCmpUpstreamError(
            "SmartCMP object response must be a JSON object.",
            trace_id=client.request.context.trace_id,
        )
    return payload


def _encoded(value: str) -> str:
    return quote(str(value or "").strip(), safe="")


def _text(value: Any) -> str:
    return str(value).strip() if isinstance(value, (str, int, float)) else ""
