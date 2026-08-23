"""Resource listing, detail, and executable-operation queries."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from smartcmp_provider.domain.object_operations import serialize_available_operations
from smartcmp_provider.domain.resource_actions import (
    available_resource_operations,
)
from smartcmp_provider.domain.resource_normalization import (
    build_flat_resource_properties,
    build_normalized_resource,
    determine_component_type,
)
from smartcmp_provider.errors import (
    SmartCmpTargetResolutionError,
    SmartCmpUpstreamError,
    SmartCmpValidationError,
)
from smartcmp_provider.models.resources import (
    ResourceDetailQuery,
    ResourceDetailResult,
    ResourceEvidenceQuery,
    ResourceEvidenceResult,
    ResourceListQuery,
    ResourceListResult,
    ResourceOperationsQuery,
    ResourceOperationsResult,
    ResourceSummarySearchQuery,
)
from smartcmp_provider.transport.client import SmartCmpClient

RESOURCE_NAME_SEARCH_SIZE = 100
RESOURCE_NAME_SEARCH_MAX_PAGES = 20
SUPPORTED_RESOURCE_OPERATION_IDS = frozenset(
    {
        "refresh",
        "restart",
        "start",
        "stop",
        "suspend",
        "tear_down_in_resource",
    }
)


def build_resource_search_path(query: ResourceListQuery) -> str:
    """Build the legacy SmartCMP resource directory path exactly.

    Args:
        query: Typed list scope, filter, and pagination values.

    Returns:
        Provider-owned path including the existing ordered query string.
    """

    encoded_query = quote(query.query_value or "", safe="")
    if query.scope == "virtual_machines":
        return (
            "/nodes/search"
            f"?query&page={query.page}&size={query.size}&catalogGroupIds=&sort=createdDate%2Cdesc"
            f"&queryValue={encoded_query}&category=iaas.machine.virtual_machine"
            "&componentType=&monitorEnabled=&cloudEntryType=&isAgentInstalled=&os="
            "&groupIds=&isImported=&relation=AND&fullMatch=false"
        )
    return (
        "/nodes/search"
        f"?page={query.page}&size={query.size}&queryValue={encoded_query}"
        "&sort=createdDate%2Cdesc&relation=AND&fullMatch=false&category=-1"
    )


def build_resource_name_search_path(resource_name: str, page: int) -> str:
    """Build the exact-name VM search path used by the detail adapter.

    Args:
        resource_name: Visible resource name supplied by the user.
        page: One-based page number.

    Returns:
        Provider-owned VM search path with legacy query semantics.
    """

    encoded_query = quote(resource_name or "", safe="")
    return (
        "/nodes/search"
        f"?query&page={page}&size={RESOURCE_NAME_SEARCH_SIZE}&catalogGroupIds=&sort=createdDate%2Cdesc"
        f"&queryValue={encoded_query}&category=iaas.machine.virtual_machine"
        "&componentType=&monitorEnabled=&cloudEntryType=&isAgentInstalled=&os="
        "&groupIds=&isImported=&relation=AND&fullMatch=true"
    )


def extract_items(payload: Any) -> list[dict[str, Any]]:
    """Extract resource rows from known SmartCMP list envelope variants."""

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("content", "data", "items", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            nested = extract_items(value)
            if nested:
                return nested
    return []


def extract_total_count(payload: Any) -> int | None:
    """Extract pagination total from known SmartCMP envelope fields."""

    if not isinstance(payload, dict):
        return None
    for key in ("totalElements", "total", "totalCount", "count"):
        try:
            return int(payload.get(key))
        except (TypeError, ValueError):
            pass
    for key in ("data", "result"):
        nested_total = extract_total_count(payload.get(key))
        if nested_total is not None:
            return nested_total
    return None


def normalize_resource_summary(item: dict[str, Any]) -> dict[str, Any]:
    """Project one SmartCMP resource row into the shared summary contract."""

    return {
        "id": item.get("id", ""),
        "name": item.get("name", ""),
        "resourceType": item.get("resourceType", ""),
        "componentType": item.get("componentType", ""),
        "status": item.get("status", ""),
        "osType": item.get("osType", ""),
        "osDescription": item.get("osDescription", ""),
        "isAgentInstalled": item.get("isAgentInstalled"),
        "monitorEnabled": item.get("monitorEnabled"),
        "externalId": item.get("externalId", ""),
        "nodeInstanceId": item.get("nodeInstanceId", ""),
    }


async def list_resources(
    client: SmartCmpClient,
    query: ResourceListQuery,
) -> ResourceListResult:
    """List SmartCMP resources within one request-scoped client.

    Args:
        client: Client bound to one Principal, Instance, and Credential.
        query: Typed resource directory query.

    Returns:
        Resource rows and optional upstream total count.
    """

    payload = await client.request_json("GET", build_resource_search_path(query))
    category = (
        "virtual-machines"
        if query.scope == "virtual_machines"
        else "cloud-resource"
    )
    return ResourceListResult(
        items=tuple(
            _attach_resource_available_operations(
                normalize_resource_summary(item),
                category=category,
            )
            for item in extract_items(payload)
        ),
        total=extract_total_count(payload),
    )


def _attach_resource_available_operations(
    item: dict[str, Any],
    *,
    category: str,
) -> dict[str, Any]:
    """Attach adapter-neutral operations to one exact resource row."""

    enriched = dict(item)
    resource_id = str(item.get("id") or "").strip()
    enriched["available_operations"] = serialize_available_operations(
        available_resource_operations(resource_id, category=category)
    )
    return enriched


async def search_resource_summaries(
    client: SmartCmpClient,
    query: ResourceSummarySearchQuery,
) -> ResourceListResult:
    """Search the shared SmartCMP resource datasource endpoint.

    Args:
        client: Client bound to one Principal, Instance, and Credential.
        query: Bounded parameters and filters for ``/nodes/search``.

    Returns:
        Raw resource summary rows and optional pagination total.
    """

    payload = await client.request_json(
        "POST",
        "/nodes/search",
        params=dict(query.params),
        json_body=(
            dict(query.payload)
            if query.payload is not None
            else None
        ),
    )
    return ResourceListResult(
        items=tuple(extract_items(payload)),
        total=extract_total_count(payload),
    )


async def load_resource_evidence(
    client: SmartCmpClient,
    query: ResourceEvidenceQuery,
) -> ResourceEvidenceResult:
    """Load analyzer-compatible evidence packs for explicit resource IDs.

    SmartCMP ``PATCH /nodes/{id}/view`` is the sole authoritative evidence
    endpoint. Every upstream failure propagates to the caller so analysis cannot
    substitute a different resource representation.

    Args:
        client: Client bound to the current request credential.
        query: Internal SmartCMP resource IDs already resolved by an adapter.

    Returns:
        One evidence record per requested ID, preserving input order.
    """

    records: list[dict[str, Any]] = []
    for raw_resource_id in query.resource_ids:
        resource_id = str(raw_resource_id or "").strip()
        if not resource_id:
            records.append(_missing_resource_record(""))
            continue
        records.append(await _load_one_resource_evidence(client, resource_id))
    return ResourceEvidenceResult(records=tuple(records))


async def get_resource_detail(
    client: SmartCmpClient,
    query: ResourceDetailQuery,
) -> ResourceDetailResult:
    """Resolve and fetch one SmartCMP resource view.

    Args:
        client: Client bound to one Principal, Instance, and Credential.
        query: Internal resource ID or exact visible resource name.

    Returns:
        Resolved resource ID and raw view payload.

    Raises:
        SmartCmpValidationError: If the target is missing, absent, or ambiguous.
        SmartCmpUpstreamError: If SmartCMP returns an unexpected detail payload.
    """

    resource_id = str(query.resource_id or "").strip()
    if not resource_id and query.resource_name.strip():
        resource_id = await resolve_unique_resource_id_by_name(
            client,
            query.resource_name.strip(),
        )
    if not resource_id:
        raise SmartCmpTargetResolutionError(
            "Provide either resource_id or resource_name.",
            trace_id=client.request.context.trace_id,
        )

    encoded_id = quote(resource_id, safe="")
    # SmartCMP currently exposes this read-only view through PATCH. The endpoint
    # is expected to become GET after the upstream CMP API bug is fixed.
    payload = await client.request_json("PATCH", f"/nodes/{encoded_id}/view")
    resource = _unwrap_payload(payload)
    if not resource:
        raise SmartCmpUpstreamError(
            "SmartCMP returned an empty resource detail payload.",
            trace_id=client.request.context.trace_id,
        )
    resolved_id = str(resource.get("id") or resource_id).strip()
    return ResourceDetailResult(resource_id=resolved_id, payload=resource)


async def list_resource_operations(
    client: SmartCmpClient,
    query: ResourceOperationsQuery,
) -> ResourceOperationsResult:
    """List enabled operations from the Agent's explicit supported set.

    Args:
        client: Client bound to the current request credential.
        query: Resource category and internal ID.

    Returns:
        Operations supported by the Agent and enabled for the current user.

    Raises:
        SmartCmpValidationError: If category or resource ID is empty.
        SmartCmpUpstreamError: If SmartCMP does not return a list.
    """

    category = str(query.category or "").strip()
    resource_id = str(query.resource_id or "").strip()
    if not category or not resource_id:
        raise SmartCmpValidationError(
            "Resource category and resource ID are required.",
            trace_id=client.request.context.trace_id,
        )
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
    operations = tuple(
        item
        for item in payload
        if isinstance(item, dict) and operation_is_executable(item)
    )
    return ResourceOperationsResult(operations=operations)


def operation_rejection_reason(operation: dict[str, Any]) -> str:
    """Explain why SmartCMP does not expose an operation in the current state."""

    if not str(operation.get("id") or "").strip():
        return "Operation has no ID."
    if operation.get("enabled") is not True:
        return str(
            operation.get("disabledMsgZh")
            or operation.get("disabledMsg")
            or "Operation is not enabled for the current user or resource state."
        )
    if operation.get("webOperation") is True:
        return "Operation must be executed in the SmartCMP web UI."
    return ""


def resource_operation_rejection_reason(operation: dict[str, Any]) -> str:
    """Explain why an operation is outside the Agent-supported resource scope."""

    operation_id = str(operation.get("id") or "").strip()
    if not operation_id:
        return "Operation has no ID."
    if operation_id not in SUPPORTED_RESOURCE_OPERATION_IDS:
        return f"Operation '{operation_id}' is not supported by the Agent."
    return operation_rejection_reason(operation)


def operation_is_executable(operation: dict[str, Any]) -> bool:
    """Return whether the operation is in the Agent's explicit supported set."""

    return not resource_operation_rejection_reason(operation)


async def _load_one_resource_evidence(
    client: SmartCmpClient,
    resource_id: str,
) -> dict[str, Any]:
    encoded_id = quote(resource_id, safe="")
    source_endpoint = f"/nodes/{encoded_id}/view"
    payload = await client.request_json("PATCH", source_endpoint)
    resource = _unwrap_payload(payload)

    if not resource:
        raise SmartCmpUpstreamError(
            f"Primary PATCH {source_endpoint} did not return resource data.",
            trace_id=client.request.context.trace_id,
        )
    record = {
        "resourceId": resource_id,
        "sourceEndpoint": source_endpoint,
        "data": resource,
        "summary": {},
        "resource": resource,
        "details": {},
        "normalized": {},
        "fetchStatus": "ok",
        "missingEvidence": [],
        "errors": [],
    }
    record["normalized"] = build_normalized_resource(record)
    return record


def _missing_resource_record(resource_id: str) -> dict[str, Any]:
    encoded_id = quote(resource_id, safe="")
    return {
        "resourceId": resource_id,
        "sourceEndpoint": f"/nodes/{encoded_id}/view",
        "data": {},
        "summary": {},
        "resource": {},
        "details": {},
        "normalized": {"type": "", "properties": {}},
        "fetchStatus": "error",
        "missingEvidence": ["resource.data"],
        "errors": ["Resource view data was not returned."],
    }


async def resolve_unique_resource_id_by_name(
    client: SmartCmpClient,
    resource_name: str,
) -> str:
    """Resolve one exact visible VM name through bounded SmartCMP paging."""

    items: list[dict[str, Any]] = []
    total_count: int | None = None
    for page in range(1, RESOURCE_NAME_SEARCH_MAX_PAGES + 1):
        payload = await client.request_json(
            "GET",
            build_resource_name_search_path(resource_name, page),
        )
        page_items = extract_items(payload)
        items.extend(page_items)
        if total_count is None:
            total_count = extract_total_count(payload)
        if total_count is not None:
            if len(items) >= total_count or not page_items:
                break
            continue
        if len(page_items) < RESOURCE_NAME_SEARCH_SIZE:
            break
    else:
        raise SmartCmpTargetResolutionError(
            f"Too many virtual machines matched name '{resource_name}'. "
            "Refine the resource name.",
            trace_id=client.request.context.trace_id,
        )

    name_key = resource_name.casefold()
    exact_matches = [
        item
        for item in items
        if _display_name(item).casefold() == name_key
        and str(item.get("id") or "").strip()
    ]
    if not exact_matches:
        choices = _format_resource_choices(items)
        suffix = f" Closest visible matches:\n{choices}" if choices else ""
        raise SmartCmpTargetResolutionError(
            f"No virtual machine exactly matched name '{resource_name}'.{suffix}",
            trace_id=client.request.context.trace_id,
        )
    if len(exact_matches) > 1:
        raise SmartCmpTargetResolutionError(
            f"Multiple virtual machines exactly matched name '{resource_name}'. "
            f"Choose one by table #:\n{_format_resource_choices(exact_matches)}",
            trace_id=client.request.context.trace_id,
        )
    return str(exact_matches[0].get("id") or "").strip()


def _unwrap_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        for key in ("data", "result", "content", "item"):
            value = payload.get(key)
            if isinstance(value, dict):
                return value
        return payload
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    return {}


def _display_name(item: dict[str, Any]) -> str:
    return str(
        item.get("name")
        or item.get("nameZh")
        or item.get("displayName")
        or item.get("label")
        or item.get("instanceName")
        or "unknown resource"
    ).strip()


def _display_status(item: dict[str, Any]) -> str:
    return str(
        item.get("status")
        or item.get("powerState")
        or item.get("state")
        or item.get("phase")
        or "unknown"
    ).strip()


def _format_resource_choices(items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    lines = ["| # | Name | Status |", "| --- | --- | --- |"]
    for index, item in enumerate(items, start=1):
        values = (index, _display_name(item), _display_status(item))
        rendered = [
            " ".join(str(value or "").replace("|", "\\|").split())
            for value in values
        ]
        lines.append("| " + " | ".join(rendered) + " |")
    return "\n".join(lines)
