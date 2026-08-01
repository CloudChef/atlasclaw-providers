"""VM request payload, submission, verification, and status operations."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote

from smartcmp_provider.errors import (
    SmartCmpError,
    SmartCmpTargetResolutionError,
    SmartCmpUnknownOutcomeError,
    SmartCmpUpstreamError,
    SmartCmpValidationError,
)
from smartcmp_provider.models.requests import (
    RequestActorIdentity,
    RequestStatusQuery,
    RequestStatusResult,
    RequestSubmissionInput,
    RequestSubmissionItem,
    RequestSubmissionResult,
)
from smartcmp_provider.transport.client import SmartCmpClient
from smartcmp_provider.transport.mutations import write_result_is_unknown

_REQUEST_ID_PATTERN = re.compile(r"^[A-Z]{3}\d{14}$", re.IGNORECASE)
_UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_FALLBACK_QUANTITY_FIELD = "quantity"
_MATCH_FIELDS = (
    "requestId",
    "workflowId",
    "requestNo",
    "requestNumber",
    "customizedId",
)
_APPROVAL_PENDING_STATES = {"APPROVAL_PENDING"}
_APPROVAL_REJECTED_STATES = {"APPROVAL_REJECTED", "APPROVAL_RETREATED"}
_APPROVAL_PASSED_STATES = {
    "STARTED",
    "TASK_RUNNING",
    "WAIT_EXECUTE",
    "FINISHED",
}
_INITIAL_OR_FAILED_STATES = {
    "INITIALING",
    "INITIALING_FAILED",
    "FAILED",
    "CANCELED",
    "CANCELLED",
    "TIMEOUT_CLOSED",
}


async def submit_request(
    client: SmartCmpClient,
    request_input: RequestSubmissionInput,
) -> RequestSubmissionResult:
    """Submit a confirmed request exactly once and verify created records.

    The operation never retries the submit call. A timeout or transport failure
    is raised as ``SmartCmpUnknownOutcomeError`` because SmartCMP may already
    have accepted the request and repeating it could create duplicate resources.

    Args:
        client: Client bound to one principal, instance, and credential.
        request_input: Confirmed payload, actor hints, and verification policy.

    Returns:
        Normalized submitted body and one outcome per SmartCMP request record.

    Raises:
        SmartCmpValidationError: If the request payload contract is invalid.
        SmartCmpUnknownOutcomeError: If the submit result cannot be determined.
        SmartCmpError: If SmartCMP definitely rejects the submission.
    """

    normalized_body = normalize_request_contract(request_input.body)
    normalized_body = await _enrich_request_body(
        client,
        normalized_body,
        request_input.actor,
    )
    # Submission is intentionally single-attempt. Only read-only verification
    # may repeat after SmartCMP returns a correlatable request record.
    try:
        payload = await client.request_json(
            "POST",
            "/generic-request/submit",
            json_body=normalized_body,
        )
    except SmartCmpError as exc:
        if write_result_is_unknown(exc):
            raise SmartCmpUnknownOutcomeError(
                "SmartCMP request submission outcome is unknown; do not "
                f"resubmit automatically. {exc}",
                trace_id=client.request.context.trace_id,
            ) from exc
        raise

    records = _extract_request_records(payload)
    if not records:
        # HTTP success is insufficient when no stable request can be correlated.
        # Reporting an unknown outcome prevents an adapter from submitting again.
        raise SmartCmpUnknownOutcomeError(
            "SmartCMP accepted the request submission but returned no "
            "correlatable request record; do not resubmit automatically.",
            trace_id=client.request.context.trace_id,
        )

    outcomes: list[RequestSubmissionItem] = []
    overall_failed = False
    for record in records:
        outcome = await _build_submission_outcome(
            client,
            record,
            verification_attempts=request_input.verification_attempts,
            verification_interval_seconds=(
                request_input.verification_interval_seconds
            ),
        )
        outcomes.append(outcome)
        if outcome.outcome == "failed":
            overall_failed = True
    return RequestSubmissionResult(
        normalized_body=normalized_body,
        items=tuple(outcomes),
        overall_failed=overall_failed,
    )


def normalize_request_contract(body: dict[str, Any]) -> dict[str, Any]:
    """Normalize legacy VM request cardinality without changing catalog fields.

    Args:
        body: Confirmed request JSON.

    Returns:
        A shallow copy with ``quantity`` normalized and object-form
        ``resourceSpecs`` converted to a one-item list.

    Raises:
        SmartCmpValidationError: If quantity or resourceSpecs violates the
            established Skill contract.
    """

    normalized = dict(body)
    if _FALLBACK_QUANTITY_FIELD in normalized:
        raw_value = normalized.get(_FALLBACK_QUANTITY_FIELD)
        if raw_value in (None, "", [], {}):
            normalized.pop(_FALLBACK_QUANTITY_FIELD, None)
        else:
            parsed_value = _coerce_positive_int(raw_value)
            if parsed_value is None:
                raise SmartCmpValidationError(
                    "Invalid `quantity` value. Fallback quantity requires one "
                    "positive integer."
                )
            normalized[_FALLBACK_QUANTITY_FIELD] = parsed_value

    specs = normalized.get("resourceSpecs")
    if isinstance(specs, dict):
        normalized["resourceSpecs"] = [specs]
        specs = normalized["resourceSpecs"]
    if "resourceSpecs" in normalized and not isinstance(specs, list):
        raise SmartCmpValidationError(
            "`resourceSpecs` must be an object or an array."
        )
    return normalized


async def get_request_status(
    client: SmartCmpClient,
    query: RequestStatusQuery,
) -> RequestStatusResult:
    """Resolve a user-facing Request ID through search and detail endpoints.

    Args:
        client: Request-scoped SmartCMP client.
        query: User-visible REQ/RES/TIC/CHG-style Request ID.

    Returns:
        Full SmartCMP request detail and normalized status facts.

    Raises:
        SmartCmpValidationError: If the Request ID format is invalid.
        SmartCmpTargetResolutionError: If no exact visible request is resolved
            or the matched detail cannot be loaded.
    """

    request_id = _normalize_value(query.request_id)
    if not is_user_facing_request_id(request_id):
        raise SmartCmpValidationError(
            "Invalid SmartCMP Request ID.",
            trace_id=client.request.context.trace_id,
        )
    params = {
        "page": 1,
        "size": 20,
        "sort": "updatedDate,desc",
        "queryValue": request_id,
        "states": "",
    }
    try:
        payload = await client.request_json(
            "GET",
            "/generic-request/search",
            params=params,
        )
        items = _extract_items(payload)
    except SmartCmpError as exc:
        error_type = type(exc)
        raise error_type(
            "SmartCMP Request ID search failed: "
            f"{_safe_message(exc, '')}",
            trace_id=client.request.context.trace_id,
        ) from exc

    matched = next(
        (item for item in items if _matches_request_id(item, request_id)),
        None,
    )
    if matched is None:
        raise SmartCmpTargetResolutionError(
            f"No SmartCMP request matched Request ID: {request_id}",
            trace_id=client.request.context.trace_id,
        )
    detail_id = _normalize_value(matched.get("id"))
    if not detail_id:
        raise SmartCmpTargetResolutionError(
            f"Matched Request ID {request_id}, but SmartCMP did not return a "
            "detail lookup ID.",
            trace_id=client.request.context.trace_id,
        )
    try:
        detail_payload = await client.request_json(
            "GET",
            f"/generic-request/{quote(detail_id, safe='')}",
        )
    except SmartCmpError as exc:
        error_type = type(exc)
        raise error_type(
            f"Matched Request ID {request_id}, but detail lookup failed: "
            f"{_safe_message(exc, detail_id)}",
            trace_id=client.request.context.trace_id,
        ) from exc
    if not isinstance(detail_payload, dict):
        raise SmartCmpTargetResolutionError(
            f"Matched Request ID {request_id}, but detail lookup returned an "
            "unexpected payload.",
            trace_id=client.request.context.trace_id,
        )
    detail_request_ids = [
        _normalize_value(detail_payload.get(field))
        for field in _MATCH_FIELDS
        if _normalize_value(detail_payload.get(field))
    ]
    if not detail_request_ids:
        raise SmartCmpTargetResolutionError(
            f"Matched Request ID {request_id}, but detail lookup did not return "
            "a user-facing Request ID.",
            trace_id=client.request.context.trace_id,
        )
    if any(
        candidate.casefold() != request_id.casefold()
        for candidate in detail_request_ids
    ):
        raise SmartCmpTargetResolutionError(
            f"Matched Request ID {request_id}, but detail lookup returned a "
            "different Request ID.",
            trace_id=client.request.context.trace_id,
        )
    return RequestStatusResult(
        detail=detail_payload,
        metadata=build_request_status_metadata(detail_payload, request_id),
    )


def is_user_facing_request_id(value: Any) -> bool:
    """Return whether a value matches the established visible Request ID form."""

    return bool(_REQUEST_ID_PATTERN.fullmatch(_normalize_value(value)))


def classify_request_status(state: Any) -> tuple[str, bool | None]:
    """Map one SmartCMP state to the stable Skill status semantics."""

    normalized = _canonical_state(state)
    if normalized in _APPROVAL_PENDING_STATES:
        return "approval_pending", False
    if normalized in _APPROVAL_REJECTED_STATES:
        return "approval_rejected", False
    if normalized in _APPROVAL_PASSED_STATES:
        return "approval_passed", True
    if normalized in _INITIAL_OR_FAILED_STATES:
        return "initial_or_failed", None
    if normalized == "ON_HOLD":
        return "on_hold", None
    if normalized == "ARCHIVED":
        return "archived", None
    if normalized == "RE_APPLY":
        return "re_apply", False
    return "unknown", None


def build_request_status_metadata(
    item: dict[str, Any],
    requested_id: str,
) -> dict[str, Any]:
    """Build stable status metadata from a SmartCMP request detail object."""

    state = _canonical_state(item.get("state"))
    category, approval_passed = classify_request_status(state)
    created_date = (
        item.get("createdDate")
        or item.get("actualStartDate")
        or item.get("plannedStartDate")
    )
    updated_date = (
        item.get("updatedDate")
        or item.get("completedDate")
        or item.get("actualEndDate")
    )
    return {
        "requestId": _display_request_id(item, requested_id),
        "name": _normalize_value(item.get("name") or item.get("requestName")),
        "catalogName": _normalize_value(
            item.get("catalogName")
            or item.get("currentCatalogName")
            or item.get("currentCatalogNameZh")
        ),
        "state": state,
        "provisionState": _normalize_value(item.get("provisionState")),
        "statusCategory": category,
        "approvalPassed": approval_passed,
        "currentStep": _current_step_name(item),
        "currentApprover": _current_approver(item),
        "error": _status_error_message(item, category),
        "resourceIds": _configuration_item_ids(item),
        "createdDate": created_date,
        "createdAt": _format_timestamp(created_date),
        "updatedDate": updated_date,
        "updatedAt": _format_timestamp(updated_date),
    }


def _configuration_item_ids(item: dict[str, Any]) -> list[str]:
    """Return resource identifiers linked to a completed SmartCMP request.

    SmartCMP records provisioned resources in ``configurationItems``. Entries
    vary by deployment between plain IDs and small objects, so the Provider
    normalizes both forms while preserving their source order.
    """

    raw_items = item.get("configurationItems")
    if not isinstance(raw_items, list):
        return []

    resource_ids: list[str] = []
    for raw_item in raw_items:
        if isinstance(raw_item, dict):
            candidate = next(
                (
                    _normalize_value(raw_item.get(field))
                    for field in ("resourceId", "configurationItemId", "id")
                    if _normalize_value(raw_item.get(field))
                ),
                "",
            )
        else:
            candidate = _normalize_value(raw_item)
        if candidate and candidate not in resource_ids:
            resource_ids.append(candidate)
    return resource_ids


async def _build_submission_outcome(
    client: SmartCmpClient,
    record: dict[str, Any],
    *,
    verification_attempts: int,
    verification_interval_seconds: float,
) -> RequestSubmissionItem:
    detail_lookup_id = _normalize_value(record.get("id"))
    display_request_id = _extract_request_id(record)
    submit_state = _normalize_value(record.get("state"))
    submit_error = _safe_message(
        record.get("errorMessage") or record.get("errMsg"),
        detail_lookup_id,
    )
    if submit_error:
        return RequestSubmissionItem(
            outcome="failed",
            request_id=display_request_id,
            submit_state=submit_state,
            state=submit_state,
            error=submit_error,
        )
    if not display_request_id:
        raise SmartCmpUnknownOutcomeError(
            "SmartCMP accepted the request submission but returned no "
            "user-facing Request ID; do not resubmit automatically.",
            trace_id=client.request.context.trace_id,
        )
    if not detail_lookup_id or detail_lookup_id.lower() in {
        "n/a",
        "none",
        "null",
    }:
        detail_lookup_id = display_request_id

    snapshot = await _verify_submitted_request(
        client,
        detail_lookup_id,
        attempts=verification_attempts,
        interval_seconds=verification_interval_seconds,
    )
    verified_request_id = _normalize_value(
        snapshot.get("request_id") or snapshot.get("workflow_id")
    )
    if is_user_facing_request_id(verified_request_id):
        display_request_id = verified_request_id
    verified_state = (
        _normalize_value(snapshot.get("state")) or submit_state or "N/A"
    )
    provision_state = _normalize_value(snapshot.get("provision_state"))
    verified_error = _safe_message(snapshot.get("error"), detail_lookup_id)
    if not snapshot.get("ok"):
        return RequestSubmissionItem(
            outcome="pending_verification",
            request_id=display_request_id,
            submit_state=submit_state,
            state=verified_state,
            provision_state=provision_state,
            message=_normalize_value(snapshot.get("message")),
            verification_status_code=_coerce_status_code(
                snapshot.get("status_code")
            ),
        )
    if snapshot.get("failed"):
        diagnostics = await _build_failure_diagnostics(client, snapshot)
        return RequestSubmissionItem(
            outcome="initialization_failed",
            request_id=display_request_id,
            submit_state=submit_state,
            state=verified_state,
            provision_state=provision_state,
            error=verified_error,
            diagnostics=tuple(diagnostics),
        )
    if not _is_submission_confirmed(snapshot):
        return RequestSubmissionItem(
            outcome="pending_workflow",
            request_id=display_request_id,
            submit_state=submit_state,
            state=verified_state,
            provision_state=provision_state,
        )
    return RequestSubmissionItem(
        outcome="success",
        request_id=display_request_id,
        submit_state=submit_state,
        state=verified_state,
        provision_state=provision_state,
    )


async def _enrich_request_body(
    client: SmartCmpClient,
    body: dict[str, Any],
    actor: RequestActorIdentity | None,
) -> dict[str, Any]:
    enriched = dict(body)
    enriched.pop("userId", None)
    enriched.pop("userLoginId", None)

    if client.request.context.principal.actor_type == "robot":
        current_user = await _fetch_current_user(client, required=True)
        _apply_current_user(enriched, current_user)
        return enriched

    if actor is not None and actor.user_id and actor.login_id:
        enriched["userId"] = actor.user_id
        enriched["userLoginId"] = actor.login_id
        return enriched

    current_user = await _fetch_current_user(client, required=True)
    _apply_current_user(enriched, current_user)
    return enriched


async def _fetch_current_user(
    client: SmartCmpClient,
    *,
    required: bool = False,
) -> dict[str, str]:
    try:
        payload = await client.request_json("GET", "/users/current-user-details")
    except SmartCmpError:
        if required:
            raise
        return {}
    if not isinstance(payload, dict):
        if required:
            raise SmartCmpUpstreamError(
                "SmartCMP current-user lookup returned an unexpected payload.",
                trace_id=client.request.context.trace_id,
            )
        return {}
    current_user = {
        "userId": _normalize_value(payload.get("id")),
        "userLoginId": _normalize_value(
            payload.get("loginId")
            or payload.get("userLoginId")
            or payload.get("username")
        ),
    }
    if required and (
        not current_user["userId"] or not current_user["userLoginId"]
    ):
        raise SmartCmpUpstreamError(
            "SmartCMP current-user lookup did not return a complete robot actor.",
            trace_id=client.request.context.trace_id,
        )
    return current_user


def _apply_current_user(
    body: dict[str, Any],
    current_user: dict[str, str],
) -> None:
    if current_user.get("userId") and not body.get("userId"):
        body["userId"] = current_user["userId"]
    if current_user.get("userLoginId") and not body.get("userLoginId"):
        body["userLoginId"] = current_user["userLoginId"]


async def _verify_submitted_request(
    client: SmartCmpClient,
    lookup_id: str,
    *,
    attempts: int,
    interval_seconds: float,
) -> dict[str, Any]:
    last_snapshot: dict[str, Any] = {
        "ok": False,
        "lookup_id": lookup_id,
        "message": "Verification did not return any response.",
    }
    for attempt in range(attempts):
        snapshot = await _fetch_request_snapshot(client, lookup_id)
        last_snapshot = snapshot
        if snapshot.get("ok") and (
            _looks_failed_state(snapshot.get("state"))
            or _looks_failed_provision_state(snapshot.get("provision_state"))
        ):
            snapshot["failed"] = True
            return snapshot
        if _is_submission_confirmed(snapshot):
            snapshot["failed"] = False
            return snapshot
        if attempt < attempts - 1:
            await asyncio.sleep(interval_seconds * (attempt + 1))
    last_snapshot["failed"] = bool(
        last_snapshot.get("ok")
        and (
            _looks_failed_state(last_snapshot.get("state"))
            or _looks_failed_provision_state(
                last_snapshot.get("provision_state")
            )
        )
    )
    return last_snapshot


async def _fetch_request_snapshot(
    client: SmartCmpClient,
    lookup_id: str,
) -> dict[str, Any]:
    try:
        payload = await client.request_json(
            "GET",
            f"/generic-request/{quote(lookup_id, safe='')}",
        )
    except SmartCmpError as exc:
        status_code, message = _error_status_and_message(exc, lookup_id)
        snapshot: dict[str, Any] = {
            "ok": False,
            "lookup_id": lookup_id,
            "message": message,
        }
        if status_code is not None:
            snapshot["status_code"] = status_code
        return snapshot
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "lookup_id": lookup_id,
            "message": "Unexpected verification payload.",
        }
    display_request_id = _extract_request_id(payload)
    return {
        "ok": True,
        "request_id": display_request_id,
        "workflow_id": display_request_id,
        "state": _normalize_value(payload.get("state")),
        "provision_state": _normalize_value(payload.get("provisionState")),
        "error": _normalize_value(
            payload.get("errMsg") or payload.get("errorMessage")
        ),
        "process_instance_id": _normalize_value(
            payload.get("processInstanceId")
        ),
        "catalog_id": _normalize_value(payload.get("catalogId")),
        "catalog_name": _normalize_value(payload.get("catalogName")),
        "request_name": _normalize_value(payload.get("name")),
        "business_group_id": _normalize_value(payload.get("businessGroupId")),
        "compute_context": _extract_compute_context(payload),
    }


async def _build_failure_diagnostics(
    client: SmartCmpClient,
    verified: dict[str, Any],
) -> list[str]:
    diagnostics: list[str] = []
    catalog_name = _normalize_value(verified.get("catalog_name"))
    request_name = _normalize_value(verified.get("request_name"))
    if catalog_name:
        diagnostics.append(f"Catalog: {catalog_name}")
    if request_name:
        diagnostics.append(f"Request Name: {request_name}")

    business_group_id = _normalize_value(verified.get("business_group_id"))
    business_group = await _fetch_optional_object(
        client,
        f"/business-groups/{quote(business_group_id, safe='')}",
    )
    business_group_name = _normalize_value(
        business_group.get("name") or business_group.get("nameZh")
    )
    if business_group_name or business_group_id:
        bg_display = business_group_name or business_group_id
        if business_group_name and business_group_id:
            bg_display = f"{business_group_name} ({business_group_id})"
        diagnostics.append(f"Business Group: {bg_display}")

    compute_context = verified.get("compute_context")
    if not isinstance(compute_context, dict):
        compute_context = {}
    requested_facets = _normalize_list(compute_context.get("requested_facets"))
    if requested_facets:
        diagnostics.append(f"Requested Facets: {', '.join(requested_facets)}")

    resource_bundle_id = _normalize_value(
        compute_context.get("resource_bundle_id")
    )
    resource_bundle = await _fetch_optional_object(
        client,
        f"/resource-bundles/{quote(resource_bundle_id, safe='')}",
    )
    resource_bundle_name = _normalize_value(resource_bundle.get("name"))
    if resource_bundle_name or resource_bundle_id:
        rb_display = resource_bundle_name or resource_bundle_id
        if resource_bundle_name and resource_bundle_id:
            rb_display = f"{resource_bundle_name} ({resource_bundle_id})"
        diagnostics.append(f"Selected Resource Bundle: {rb_display}")
    resource_bundle_facets = _normalize_list(resource_bundle.get("facets"))
    if resource_bundle_facets:
        diagnostics.append(
            f"Resource Bundle Facets: {', '.join(resource_bundle_facets)}"
        )

    resource_bundle_policy = _normalize_value(
        compute_context.get("resource_bundle_policy")
    )
    if resource_bundle_policy:
        diagnostics.append(f"Resource Bundle Policy: {resource_bundle_policy}")
    for label, key in (
        ("Compute Profile ID", "compute_profile_id"),
        ("Flavor ID", "flavor_id"),
        ("Template ID", "template_id"),
        ("Logic Template ID", "logic_template_id"),
        ("Network ID", "network_id"),
    ):
        value = _normalize_value(compute_context.get(key))
        if value:
            diagnostics.append(f"{label}: {value}")
    cpu_value = _normalize_value(compute_context.get("cpu"))
    memory_value = _normalize_value(compute_context.get("memory"))
    if cpu_value or memory_value:
        shape = []
        if cpu_value:
            shape.append(f"CPU={cpu_value}")
        if memory_value:
            shape.append(f"Memory={memory_value}")
        diagnostics.append(f"Requested Shape: {', '.join(shape)}")
    system_disk_size = _normalize_value(
        compute_context.get("system_disk_size")
    )
    if system_disk_size:
        diagnostics.append(f"System Disk Size: {system_disk_size}")
    credential_user = _normalize_value(compute_context.get("credential_user"))
    if credential_user:
        diagnostics.append(f"Credential User: {credential_user}")
    return diagnostics


async def _fetch_optional_object(
    client: SmartCmpClient,
    path: str,
) -> dict[str, Any]:
    if path.endswith("/"):
        return {}
    try:
        payload = await client.request_json("GET", path)
    except SmartCmpError:
        return {}
    return payload if isinstance(payload, dict) else {}
def _error_status_and_message(
    exc: SmartCmpError,
    lookup_id: str,
) -> tuple[int | None, str]:
    return exc.http_status, _safe_message(str(exc), lookup_id)


def _extract_request_records(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    if isinstance(result, dict):
        return [result]
    return []


def _extract_request_id(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    fields = (
        "workflowId",
        "workflow_id",
        "requestId",
        "request_id",
        "requestNo",
        "requestNumber",
        "customizedId",
        "ticketId",
        "ticket_id",
    )
    for key in fields:
        candidate = _normalize_value(payload.get(key))
        if is_user_facing_request_id(candidate):
            return candidate
    current_activity = payload.get("currentActivity")
    if isinstance(current_activity, dict):
        for key in fields:
            candidate = _normalize_value(current_activity.get(key))
            if is_user_facing_request_id(candidate):
                return candidate
    return ""


def _extract_compute_context(payload: dict[str, Any]) -> dict[str, Any]:
    request_payload = payload.get("catalogServiceRequest")
    if not isinstance(request_payload, dict):
        request_payload = {}
    request_parameters = request_payload.get("requestParameters")
    if not isinstance(request_parameters, dict):
        request_parameters = {}
    compute: dict[str, Any] = {}
    ext_params = request_parameters.get("extensibleParameters")
    if isinstance(ext_params, list):
        for item in ext_params:
            if isinstance(item, dict) and isinstance(item.get("Compute"), dict):
                compute = item["Compute"]
                break
    resource_bundle_config = compute.get("resource_bundle_config")
    if not isinstance(resource_bundle_config, dict):
        resource_bundle_config = {}
    system_disk_config = _unwrap_value(compute.get("system_disk_config"))
    if not isinstance(system_disk_config, dict):
        system_disk_config = {}
    requested_facets = _extract_requested_facets(request_parameters)
    requested_facets.extend(_normalize_list(_unwrap_value(compute.get("tags"))))
    requested_facets.extend(
        _normalize_list(_unwrap_value(compute.get("tags_copy")))
    )
    return {
        "requested_facets": _normalize_list(requested_facets),
        "resource_bundle_id": _normalize_value(
            _unwrap_value(resource_bundle_config.get("policy_resource"))
        ),
        "resource_bundle_policy": _normalize_value(
            _unwrap_value(resource_bundle_config.get("policy_type"))
        ),
        "compute_profile_id": _normalize_value(
            _unwrap_value(compute.get("compute_profile_id"))
        ),
        "flavor_id": _normalize_value(
            _unwrap_value(compute.get("flavor_id"))
        ),
        "logic_template_id": _normalize_value(
            _unwrap_value(compute.get("logic_template_id"))
        ),
        "template_id": _normalize_value(
            _unwrap_value(compute.get("template_id"))
        ),
        "network_id": _normalize_value(
            _unwrap_value(compute.get("network_id") or compute.get("networkId"))
        ),
        "cpu": _normalize_value(
            _unwrap_value(compute.get("cpus") or compute.get("cpu"))
        ),
        "memory": _normalize_value(_unwrap_value(compute.get("memory"))),
        "system_disk_size": _normalize_value(system_disk_config.get("size")),
        "credential_user": _normalize_value(
            (compute.get("credential") or {}).get("user")
        ),
    }


def _extract_requested_facets(
    request_parameters: dict[str, Any],
) -> list[str]:
    facets: list[str] = []
    raw_facets = request_parameters.get("cloud_resource_facets")
    if not isinstance(raw_facets, dict):
        return facets
    for key, raw_values in raw_facets.items():
        facet_key = _normalize_value(key)
        if not facet_key:
            continue
        values = raw_values if isinstance(raw_values, list) else [raw_values]
        for raw_value in values:
            facet_value = _normalize_value(raw_value)
            if facet_value:
                facets.append(f"{facet_key}:{facet_value}")
    return _normalize_list(facets)


def _normalize_list(values: Any) -> list[str]:
    if isinstance(values, list):
        items = values
    elif values in (None, "", {}, ()):
        items = []
    else:
        items = [values]
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, (list, tuple, set)):
            for nested in _normalize_list(list(item)):
                if nested not in seen:
                    seen.add(nested)
                    normalized.append(nested)
            continue
        candidate = _normalize_value(_unwrap_value(item))
        if candidate and candidate not in seen:
            seen.add(candidate)
            normalized.append(candidate)
    return normalized


def _unwrap_value(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def _looks_failed_state(state: Any) -> bool:
    normalized = _canonical_state(state)
    if not normalized:
        return False
    if normalized in {
        "FAILED",
        "INITIALING_FAILED",
        "CANCELLED",
        "CANCELED",
        "REJECTED",
    }:
        return True
    return "FAIL" in normalized or "ERROR" in normalized


def _looks_failed_provision_state(state: Any) -> bool:
    normalized = _normalize_value(state).lower()
    return bool(normalized and ("fail" in normalized or "error" in normalized))


def _is_submission_confirmed(snapshot: dict[str, Any]) -> bool:
    if not snapshot.get("ok"):
        return False
    state = _canonical_state(snapshot.get("state"))
    if not state:
        return False
    if _looks_failed_state(state) or _looks_failed_provision_state(
        snapshot.get("provision_state")
    ):
        return False
    if _normalize_value(snapshot.get("process_instance_id")):
        return True
    return state not in {"INITIALING", "INITIALIZING"}


def _coerce_positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        return int(value) if value.is_integer() and value > 0 else None
    if isinstance(value, str):
        candidate = value.strip()
        if candidate and re.fullmatch(r"\d+", candidate):
            parsed = int(candidate)
            return parsed if parsed > 0 else None
    return None


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("content", "data", "items", "result"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("content", "items", "result"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _matches_request_id(item: dict[str, Any], request_id: str) -> bool:
    normalized = request_id.lower()
    return any(
        _normalize_value(item.get(field)).lower() == normalized
        for field in _MATCH_FIELDS
    )


def _display_request_id(item: dict[str, Any], fallback: str) -> str:
    for field in _MATCH_FIELDS:
        candidate = _normalize_value(item.get(field))
        if is_user_facing_request_id(candidate):
            return candidate
    return _normalize_value(fallback)


def _current_step_name(item: dict[str, Any]) -> str:
    activity = item.get("currentActivity")
    if isinstance(activity, dict):
        process_step = activity.get("processStep")
        if isinstance(process_step, dict):
            candidate = _normalize_value(process_step.get("name"))
            if candidate:
                return candidate
        for field in ("name", "activityName", "taskName"):
            candidate = _normalize_value(activity.get(field))
            if candidate:
                return candidate
    task_node = item.get("taskNode")
    if isinstance(task_node, dict):
        return _normalize_value(task_node.get("name"))
    return ""


def _current_approver(item: dict[str, Any]) -> str:
    activity = item.get("currentActivity")
    if isinstance(activity, dict):
        assignments = activity.get("assignments")
        if isinstance(assignments, list):
            names: list[str] = []
            for assignment in assignments[:3]:
                if not isinstance(assignment, dict):
                    continue
                approver = assignment.get("approver")
                if isinstance(approver, dict):
                    name = _normalize_value(
                        approver.get("name") or approver.get("loginId")
                    )
                    if name:
                        names.append(name)
                        continue
                name = _normalize_value(
                    assignment.get("name")
                    or assignment.get("loginId")
                    or assignment.get("assigneeName")
                )
                if name:
                    names.append(name)
            if names:
                return ", ".join(names)
    current = item.get("currentAssignee")
    if isinstance(current, dict):
        return _normalize_value(current.get("name") or current.get("loginId"))
    return _normalize_value(
        item.get("currentAssignee")
        or item.get("assigneeName")
        or item.get("assigneeId")
    )


def _status_error_message(item: dict[str, Any], category: str) -> str:
    explicit_error = _normalize_value(
        item.get("errMsg")
        or item.get("errorMessage")
        or item.get("closeNotes")
        or item.get("resolutionNotes")
    )
    if explicit_error:
        return _safe_message(explicit_error, "")
    if category in {"approval_rejected", "initial_or_failed"}:
        return _safe_message(item.get("message"), "")
    return ""


def _format_timestamp(value: Any) -> str:
    if isinstance(value, (int, float)) and value > 0:
        try:
            return datetime.fromtimestamp(value / 1000).strftime(
                "%Y-%m-%d %H:%M"
            )
        except (OSError, OverflowError, ValueError):
            return str(value)
    return _normalize_value(value)


def _canonical_state(value: Any) -> str:
    return _normalize_value(value).upper().replace("-", "_")


def _normalize_value(value: Any) -> str:
    return str(value or "").strip()


def _safe_message(value: Any, lookup_id: str) -> str:
    message = SmartCmpClient.sanitize_error_text(_normalize_value(value))
    if lookup_id:
        message = message.replace(lookup_id, "[internal-id]")
    return _UUID_PATTERN.sub("[uuid]", message)


def _coerce_status_code(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
