"""Identity-verified reads for SmartCMP designer objects."""

from __future__ import annotations

import uuid
from urllib.parse import quote

from smartcmp_provider.errors import (
    SmartCmpTargetResolutionError,
    SmartCmpUpstreamError,
    SmartCmpValidationError,
)
from smartcmp_provider.models.objects import ObjectReadQuery, ObjectReadResult
from smartcmp_provider.transport.client import SmartCmpClient

_OBJECT_COLLECTIONS = {
    "component_definition": "components",
    "form_definition": "forms",
    "optimization_policy": "compliance-policies",
    "script_definition": "scripts",
}


async def get_object_by_id(
    client: SmartCmpClient,
    query: ObjectReadQuery,
) -> ObjectReadResult:
    """Read one supported object and verify that SmartCMP returned the requested ID.

    Args:
        client: Request-scoped SmartCMP client.
        query: Supported object type and exact UUID selected by an adapter.

    Returns:
        The identity-verified raw object used by form and designer services.

    Raises:
        SmartCmpValidationError: If the object ID is not a canonical UUID.
        SmartCmpUpstreamError: If SmartCMP returns a non-object response.
        SmartCmpTargetResolutionError: If the response belongs to another object.
    """

    object_id = _canonical_uuid(query.object_id)
    collection = _OBJECT_COLLECTIONS[query.object_type]
    payload = await client.request_json(
        "GET",
        f"/{collection}/{quote(object_id, safe='')}",
    )
    if not isinstance(payload, dict):
        raise SmartCmpUpstreamError(
            "SmartCMP object response must be a JSON object.",
            trace_id=client.request.context.trace_id,
        )
    response_id = _canonical_uuid(payload.get("id"), allow_empty=True)
    if response_id != object_id:
        raise SmartCmpTargetResolutionError(
            "SmartCMP object response does not match the requested object ID.",
            trace_id=client.request.context.trace_id,
        )
    return ObjectReadResult(
        object_type=query.object_type,
        object_id=object_id,
        payload=payload,
    )


def _canonical_uuid(value: object, *, allow_empty: bool = False) -> str:
    """Return a canonical UUID or fail at the Provider boundary."""

    normalized = str(value or "").strip().lower()
    try:
        parsed = uuid.UUID(normalized)
    except (ValueError, AttributeError) as exc:
        if allow_empty:
            return ""
        raise SmartCmpValidationError(
            "SmartCMP object_id must be a canonical UUID."
        ) from exc
    canonical = str(parsed)
    if normalized != canonical:
        if allow_empty:
            return ""
        raise SmartCmpValidationError(
            "SmartCMP object_id must be a canonical UUID."
        )
    return canonical
