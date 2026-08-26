"""SmartCMP resource-center recycle-bin reads and permanent removal."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from smartcmp_provider.domain.object_operations import (
    available_operation,
    serialize_available_operations,
)
from smartcmp_provider.errors import (
    SmartCmpTargetResolutionError,
    SmartCmpUpstreamError,
    SmartCmpValidationError,
)
from smartcmp_provider.models.resources import (
    PermanentResourceRemovalInput,
    PermanentResourceRemovalResult,
    RecycledResourceListResult,
    RecycledResourceQuery,
)
from smartcmp_provider.operations.resource_actions import (
    submit_deployment_actions_once,
)
from smartcmp_provider.operations.resources import (
    extract_items,
    extract_total_count,
    operation_rejection_reason,
)
from smartcmp_provider.transport.client import SmartCmpClient

PERMANENT_DELETE_ACTION = "permanently_delete_deployment"
_RECYCLED_DEPLOYMENT_PAGE_SIZE = 100
_RECYCLED_DEPLOYMENT_MAX_PAGES = 20
_LOCATOR_FIELDS = (
    "resource_id",
    "resource_name",
    "deployment_id",
    "deployment_name",
)
_DELETED_RESOURCE_ENVELOPE_KEYS = ("content", "data", "items", "result")


async def list_recycled_resources(
    client: SmartCmpClient,
    query: RecycledResourceQuery,
) -> RecycledResourceListResult:
    """List current-user recycled resources with their owning deployment.

    With no locator, ``page`` and ``size`` page the recycled deployment source
    and every returned deployment is expanded to its affected resources. With
    one locator, bounded paging resolves one exact deployment and returns its
    complete affected scope. Each row advertises only the dedicated permanent
    removal capability; execution still rechecks current-user recycled actions.

    Args:
        client: Client bound to the current SmartCMP credential.
        query: Optional exact locator plus deployment paging controls.

    Returns:
        Resource rows carrying owning-deployment and affected-scope metadata.

    Raises:
        SmartCmpValidationError: If more than one locator is supplied.
        SmartCmpTargetResolutionError: If a supplied locator has no unique match.
        SmartCmpUpstreamError: If SmartCMP violates the recycle-bin contract.
    """

    locator = _selected_locator(client, query, require_one=False)
    if locator is None:
        payload = await _fetch_recycled_deployment_page(
            client,
            page=query.page,
            size=query.size,
        )
        deployments = _validated_deployments(client, extract_items(payload))
        rows = await _expand_deployments(client, deployments)
        total = extract_total_count(payload)
        return RecycledResourceListResult(
            items=tuple(rows),
            total=total if total is not None else len(deployments),
            page=query.page,
            size=query.size,
        )

    field, value = locator
    rows = await _resolve_locator_rows(
        client,
        field=field,
        value=value,
        include_actions=True,
    )
    return RecycledResourceListResult(
        items=tuple(rows),
        total=1,
        page=query.page,
        size=query.size,
    )


async def permanently_remove_recycled_resource(
    client: SmartCmpClient,
    action_input: PermanentResourceRemovalInput,
) -> PermanentResourceRemovalResult:
    """Submit permanent removal of one uniquely resolved recycled deployment.

    A resource locator is promoted to its owning deployment because SmartCMP's
    permanent action removes the entire deployment scope. Confirmation and
    target uniqueness are checked before any write. The current credential's
    ``recycled=true`` actions are then reloaded and exactly one POST is issued.

    Args:
        client: Client bound to the acting SmartCMP principal.
        action_input: Exactly one locator and an explicit confirmation flag.

    Returns:
        Submission facts and the full affected resource scope. The result does
        not represent completion of asynchronous removal.

    Raises:
        SmartCmpValidationError: If confirmation/action eligibility is absent.
        SmartCmpTargetResolutionError: If the target or ownership is ambiguous.
        SmartCmpUnknownOutcomeError: If the single POST outcome is unknown.
        SmartCmpError: If SmartCMP definitely rejects the submission.
    """

    if action_input.confirmed is not True:
        raise SmartCmpValidationError(
            "confirmed must be true before permanent removal; this deletes the "
            "entire owning deployment and cannot be undone.",
            trace_id=client.request.context.trace_id,
        )
    field, value = _selected_locator(client, action_input, require_one=True)
    rows = await _resolve_locator_rows(
        client,
        field=field,
        value=value,
        include_actions=False,
    )
    deployment_ids = {
        str(item.get("deployment_id") or "").strip()
        for item in rows
        if str(item.get("deployment_id") or "").strip()
    }
    if len(deployment_ids) != 1:
        raise SmartCmpTargetResolutionError(
            "The recycled target did not resolve to exactly one owning "
            "deployment; refresh the recycle bin and retry with deployment_id.",
            trace_id=client.request.context.trace_id,
        )
    deployment_id = next(iter(deployment_ids))
    owning_deployment = next(
        (
            item.get("owning_deployment")
            for item in rows
            if isinstance(item.get("owning_deployment"), dict)
        ),
        {},
    )
    if owning_deployment.get("deleted") is True:
        raise SmartCmpValidationError(
            "The recycled deployment is a deleted tombstone and has no "
            "executable permanent-removal action; refresh the recycle bin "
            "instead of resubmitting deletion.",
            trace_id=client.request.context.trace_id,
        )
    deployment_name = next(
        (
            str(item.get("deployment_name") or "").strip()
            for item in rows
            if str(item.get("deployment_name") or "").strip()
        ),
        "",
    )
    row_snapshot = tuple(rows)
    actual_resource_ids = _resource_id_snapshot(row_snapshot)
    _validate_expected_scope(
        client,
        action_input,
        deployment_id=deployment_id,
        resource_ids=actual_resource_ids,
    )
    action_path = (
        f"/deployments/{quote(deployment_id, safe='')}"
        "/deployment-actions"
    )
    action_payload = await client.request_json(
        "GET",
        action_path,
        params={"recycled": True},
    )
    operations = extract_items(action_payload)
    operation = next(
        (
            item
            for item in operations
            if str(item.get("id") or "").strip() == PERMANENT_DELETE_ACTION
        ),
        None,
    )
    if operation is None:
        raise SmartCmpValidationError(
            "Permanent removal is not available for recycled deployment "
            f"'{deployment_name or deployment_id}' under the current user. "
            "Refresh the recycle bin or ask an authorized operator.",
            trace_id=client.request.context.trace_id,
        )
    rejection = operation_rejection_reason(operation)
    if rejection:
        raise SmartCmpValidationError(
            "Permanent removal is not executable for recycled deployment "
            f"'{deployment_name or deployment_id}': {rejection}",
            trace_id=client.request.context.trace_id,
        )
    await submit_deployment_actions_once(
        client,
        operations=((deployment_id, str(operation.get("id") or "")),),
        recycled=True,
    )
    return PermanentResourceRemovalResult(
        deployment_id=deployment_id,
        deployment_name=deployment_name,
        affected_resources=_stable_resource_snapshot(row_snapshot),
        message=(
            "SmartCMP permanently_delete_deployment request submitted for "
            f"deployment '{deployment_name or deployment_id}'."
        ),
        verification_hint=(
            "Refresh the recycle bin to verify that SmartCMP completed removal; "
            "a submitted request does not mean deletion is complete."
        ),
    )


def _validate_expected_scope(
    client: SmartCmpClient,
    action_input: PermanentResourceRemovalInput,
    *,
    deployment_id: str,
    resource_ids: tuple[str, ...],
) -> None:
    expected_deployment_id = action_input.expected_deployment_id.strip()
    expected_values = tuple(
        str(resource_id or "").strip()
        for resource_id in action_input.expected_resource_ids
    )
    if not expected_deployment_id or any(not item for item in expected_values):
        raise SmartCmpValidationError(
            "expected_deployment_id and every expected_resource_ids value must "
            "come from the selected recycle-bin row. Refresh the recycle bin "
            "and confirm the current affected scope.",
            trace_id=client.request.context.trace_id,
        )
    expected_resource_ids = tuple(sorted(set(expected_values)))
    if (
        expected_deployment_id != deployment_id
        or expected_resource_ids != resource_ids
    ):
        raise SmartCmpValidationError(
            "The recycled deployment or affected resource set changed after "
            "confirmation. Refresh the recycle bin, review the complete owning "
            "deployment scope, and confirm permanent removal again.",
            trace_id=client.request.context.trace_id,
        )


def _resource_id_snapshot(
    rows: tuple[dict[str, Any], ...],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                str(item.get("resource_id") or "").strip()
                for item in rows
                if str(item.get("resource_id") or "").strip()
            }
        )
    )


def _stable_resource_snapshot(
    rows: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    resources = [
        {
            "resource_id": str(item.get("resource_id") or "").strip(),
            "resource_name": str(item.get("resource_name") or "").strip(),
            "status": str(item.get("status") or "").strip(),
        }
        for item in rows
        if str(item.get("resource_id") or "").strip()
    ]
    return tuple(sorted(resources, key=lambda item: item["resource_id"]))


def _selected_locator(
    client: SmartCmpClient,
    value: RecycledResourceQuery | PermanentResourceRemovalInput,
    *,
    require_one: bool,
) -> tuple[str, str] | None:
    selected = [
        (field, str(getattr(value, field) or "").strip())
        for field in _LOCATOR_FIELDS
        if str(getattr(value, field) or "").strip()
    ]
    expected = "exactly one" if require_one else "at most one"
    if len(selected) > 1 or (require_one and not selected):
        raise SmartCmpValidationError(
            f"Provide {expected} of resource_id, resource_name, deployment_id, "
            "or deployment_name.",
            trace_id=client.request.context.trace_id,
        )
    return selected[0] if selected else None


async def _resolve_locator_rows(
    client: SmartCmpClient,
    *,
    field: str,
    value: str,
    include_actions: bool,
) -> list[dict[str, Any]]:
    deployments = await _load_all_recycled_deployments(client)
    if field.startswith("deployment_"):
        selected = _resolve_deployment(client, deployments, field, value)
    else:
        all_rows = await _expand_deployments(
            client,
            deployments,
            include_actions=False,
        )
        selected = _resolve_resource_owner(
            client,
            deployments,
            all_rows,
            field,
            value,
        )
    return await _expand_deployments(
        client,
        [selected],
        include_actions=include_actions,
    )


async def _fetch_recycled_deployment_page(
    client: SmartCmpClient,
    *,
    page: int,
    size: int,
) -> Any:
    return await client.request_json(
        "GET",
        "/deployments",
        params={
            # Spring selects the recycle-bin controller by query-parameter
            # presence; an empty value matches the SmartCMP UI request.
            "recycled": "",
            "page": page,
            "size": size,
            "catalogGroupIds": "",
            "sort": "recycleDeleteTime,desc",
            "queryValue": "",
            "searchValue": "",
            "isList": True,
        },
    )


async def _load_all_recycled_deployments(
    client: SmartCmpClient,
) -> list[dict[str, Any]]:
    deployments: list[dict[str, Any]] = []
    for page in range(1, _RECYCLED_DEPLOYMENT_MAX_PAGES + 1):
        payload = await _fetch_recycled_deployment_page(
            client,
            page=page,
            size=_RECYCLED_DEPLOYMENT_PAGE_SIZE,
        )
        items = _validated_deployments(client, extract_items(payload))
        deployments.extend(items)
        total_pages = _extract_total_pages(payload)
        if total_pages is not None:
            if page >= total_pages:
                return _deduplicate_deployments(deployments)
            continue
        last = payload.get("last") if isinstance(payload, dict) else None
        if last is True:
            return _deduplicate_deployments(deployments)
        if last is False:
            continue
        if len(items) < _RECYCLED_DEPLOYMENT_PAGE_SIZE:
            return _deduplicate_deployments(deployments)
    scan_limit = (
        _RECYCLED_DEPLOYMENT_PAGE_SIZE * _RECYCLED_DEPLOYMENT_MAX_PAGES
    )
    raise SmartCmpTargetResolutionError(
        "Automatic recycle-bin target resolution is limited to the first "
        f"{scan_limit} deployments. Manage the target directly in SmartCMP or "
        "add server-side exact filtering before retrying through this Provider.",
        trace_id=client.request.context.trace_id,
    )


def _validated_deployments(
    client: SmartCmpClient,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    for item in items:
        if not str(item.get("id") or "").strip():
            raise SmartCmpUpstreamError(
                "SmartCMP returned a recycled deployment without an ID.",
                trace_id=client.request.context.trace_id,
            )
    return items


def _deduplicate_deployments(
    deployments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for item in deployments:
        by_id.setdefault(str(item.get("id") or "").strip(), item)
    return list(by_id.values())


def _resolve_deployment(
    client: SmartCmpClient,
    deployments: list[dict[str, Any]],
    field: str,
    value: str,
) -> dict[str, Any]:
    key = "id" if field == "deployment_id" else "name"
    matches = [
        item
        for item in deployments
        if _matches(str(item.get(key) or ""), value, name=key == "name")
    ]
    if not matches:
        raise SmartCmpTargetResolutionError(
            f"No current-user recycled deployment matches {field}='{value}'.",
            trace_id=client.request.context.trace_id,
        )
    if len(matches) > 1:
        candidates = ", ".join(
            f"{item.get('name') or '<unnamed>'} ({item.get('id')})"
            for item in matches
        )
        raise SmartCmpTargetResolutionError(
            f"{field}='{value}' is ambiguous. Use deployment_id from: "
            f"{candidates}.",
            trace_id=client.request.context.trace_id,
        )
    return matches[0]


def _resolve_resource_owner(
    client: SmartCmpClient,
    deployments: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    field: str,
    value: str,
) -> dict[str, Any]:
    key = "resource_id" if field == "resource_id" else "resource_name"
    matches = [
        item
        for item in rows
        if _matches(str(item.get(key) or ""), value, name=key == "resource_name")
    ]
    identities = {
        (
            str(item.get("deployment_id") or ""),
            str(item.get("resource_id") or ""),
        )
        for item in matches
    }
    if not matches:
        raise SmartCmpTargetResolutionError(
            f"No current-user recycled resource matches {field}='{value}'.",
            trace_id=client.request.context.trace_id,
        )
    if len(identities) > 1:
        candidates = ", ".join(
            f"{item.get('resource_name') or '<unnamed>'} "
            f"({item.get('resource_id')}) in "
            f"{item.get('deployment_name') or item.get('deployment_id')}"
            for item in matches
        )
        raise SmartCmpTargetResolutionError(
            f"{field}='{value}' has ambiguous recycled ownership. Use one "
            f"deployment_id from: {candidates}.",
            trace_id=client.request.context.trace_id,
        )
    deployment_id = str(matches[0].get("deployment_id") or "")
    return next(
        item
        for item in deployments
        if str(item.get("id") or "") == deployment_id
    )


async def _expand_deployments(
    client: SmartCmpClient,
    deployments: list[dict[str, Any]],
    *,
    include_actions: bool = True,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for deployment in deployments:
        deployment_id = str(deployment.get("id") or "").strip()
        path = (
            "/nodes/deleted?expand&deploymentId="
            f"{quote(deployment_id, safe='')}&includeRecycle=true"
        )
        payload = await client.request_json("GET", path)
        resources = _extract_deleted_resources(
            client,
            payload,
            deployment_id=deployment_id,
        )
        operations = []
        if include_actions and deployment.get("deleted") is not True:
            operations = await _fetch_recycled_deployment_actions(
                client,
                deployment_id,
            )
        rows.extend(
            _project_deployment_rows(
                client,
                deployment,
                resources,
                operations,
            )
        )
    return rows


def _extract_deleted_resources(
    client: SmartCmpClient,
    payload: Any,
    *,
    deployment_id: str,
) -> list[dict[str, Any]]:
    rows = _known_deleted_resource_rows(payload)
    if rows is None:
        raise SmartCmpUpstreamError(
            "SmartCMP returned an unexpected deleted-resource payload for "
            f"deployment '{deployment_id}'; expected a list or known list envelope.",
            trace_id=client.request.context.trace_id,
        )
    resources: list[dict[str, Any]] = []
    for index, item in enumerate(rows):
        if not isinstance(item, dict):
            raise SmartCmpUpstreamError(
                "SmartCMP returned a non-object deleted resource at index "
                f"{index} for deployment '{deployment_id}'.",
                trace_id=client.request.context.trace_id,
            )
        if not str(item.get("id") or "").strip():
            raise SmartCmpUpstreamError(
                "SmartCMP returned a deleted resource without an ID at index "
                f"{index} for deployment '{deployment_id}'.",
                trace_id=client.request.context.trace_id,
            )
        resources.append(item)
    return resources


def _known_deleted_resource_rows(payload: Any) -> list[Any] | None:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return None
    for key in _DELETED_RESOURCE_ENVELOPE_KEYS:
        if key not in payload:
            continue
        value = payload[key]
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = _known_deleted_resource_rows(value)
            if nested is not None:
                return nested
    return None


async def _fetch_recycled_deployment_actions(
    client: SmartCmpClient,
    deployment_id: str,
) -> list[dict[str, Any]]:
    path = (
        f"/deployments/{quote(deployment_id, safe='')}"
        "/deployment-actions"
    )
    payload = await client.request_json(
        "GET",
        path,
        params={"recycled": True},
    )
    if not isinstance(payload, (list, dict)):
        raise SmartCmpUpstreamError(
            "SmartCMP returned an unexpected recycled action payload for "
            f"deployment '{deployment_id}'.",
            trace_id=client.request.context.trace_id,
        )
    return extract_items(payload)


def _project_deployment_rows(
    client: SmartCmpClient,
    deployment: dict[str, Any],
    resources: list[dict[str, Any]],
    operations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    deployment_id = str(deployment.get("id") or "").strip()
    deployment_name = str(deployment.get("name") or "").strip()
    resource_ids = tuple(
        sorted({str(item.get("id") or "").strip() for item in resources})
    )
    source_rows = resources or [{}]
    permanent_operation = next(
        (
            item
            for item in operations
            if str(item.get("id") or "").strip() == PERMANENT_DELETE_ACTION
            and not operation_rejection_reason(item)
        ),
        None,
    )
    deployment_state = str(
        deployment.get("state") or deployment.get("status") or ""
    ).strip()
    deployment_deleted = deployment.get("deleted")
    deployment_recycled = deployment.get("recycled")
    rows: list[dict[str, Any]] = []
    for resource in source_rows:
        upstream_deployment_id = str(
            resource.get("deploymentId") or deployment_id
        ).strip()
        if upstream_deployment_id != deployment_id:
            raise SmartCmpUpstreamError(
                "SmartCMP returned recycled resource "
                f"'{resource.get('id') or resource.get('name')}' for deployment "
                f"'{deployment_id}' but assigned it to '{upstream_deployment_id}'.",
                trace_id=client.request.context.trace_id,
            )
        resource_id = str(resource.get("id") or "").strip()
        locator_arguments = (
            {"resource_id": resource_id}
            if resource_id
            else {"deployment_id": deployment_id}
        )
        locator_arguments.update(
            {
                "expected_deployment_id": deployment_id,
                "expected_resource_ids": resource_ids,
            }
        )
        row = {
            "resource_id": resource_id,
            "resource_name": str(resource.get("name") or "").strip(),
            "resource_type": str(
                resource.get("resourceType")
                or resource.get("resource_type")
                or ""
            ).strip(),
            "component_type": str(
                resource.get("componentType")
                or resource.get("component_type")
                or ""
            ).strip(),
            "status": str(
                resource.get("status") or resource.get("state") or ""
            ).strip(),
            "deployment_id": deployment_id,
            "deployment_name": deployment_name,
            "owning_deployment": {
                "id": deployment_id,
                "name": deployment_name,
                "state": deployment_state,
                "deleted": deployment_deleted,
                "recycled": deployment_recycled,
                "recycle_delete_time": deployment.get("recycleDeleteTime"),
            },
            "affected_scope": {
                "deployment_id": deployment_id,
                "resource_ids": resource_ids,
            },
            "available_operations": (
                serialize_available_operations(
                    (
                        available_operation(
                            PERMANENT_DELETE_ACTION,
                            "smartcmp.resources.recycle_bin.permanently_remove",
                            arguments=locator_arguments,
                            required_inputs=("confirmed",),
                        ),
                    )
                )
                if permanent_operation is not None
                else []
            ),
        }
        rows.append(row)
    return rows


def _matches(actual: str, expected: str, *, name: bool) -> bool:
    if name:
        return actual.strip().casefold() == expected.strip().casefold()
    return actual.strip() == expected.strip()


def _extract_total_pages(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    for key in ("totalPages", "pages"):
        try:
            return int(payload.get(key))
        except (TypeError, ValueError):
            pass
    for key in ("data", "result"):
        nested = _extract_total_pages(payload.get(key))
        if nested is not None:
            return nested
    return None
