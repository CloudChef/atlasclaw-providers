"""Pending-approval reads and non-retried approval decisions."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from smartcmp_provider.capabilities import capability_by_id
from smartcmp_provider.domain.approval_validation import (
    is_request_id,
    request_ids_from_item,
)
from smartcmp_provider.errors import (
    SmartCmpAuthenticationError,
    SmartCmpError,
    SmartCmpPermissionError,
    SmartCmpRateLimitError,
    SmartCmpTargetResolutionError,
    SmartCmpTimeoutError,
    SmartCmpUnknownOutcomeError,
    SmartCmpUpstreamError,
    SmartCmpValidationError,
)
from smartcmp_provider.models.approvals import (
    ApprovalDecisionInput,
    ApprovalDecisionItem,
    ApprovalDecisionResult,
    ApprovalDetailQuery,
    ApprovalDetailResult,
    ApprovalListQuery,
    ApprovalListResult,
)
from smartcmp_provider.models.catalogs import CatalogItemsResult
from smartcmp_provider.transport.client import SmartCmpClient
from smartcmp_provider.transport.mutations import write_result_is_unknown

_FAILED_STATES = {
    "failed",
    "failure",
    "error",
    "canceled",
    "cancelled",
}
_SAFE_SUCCESS_STATES = {
    "approve",
    "approved",
    "complete",
    "completed",
    "reject",
    "rejected",
    "success",
    "succeeded",
}

LIST_PENDING_APPROVALS_CAPABILITY = capability_by_id(
    "smartcmp.approvals.list"
)
GET_APPROVAL_DETAIL_CAPABILITY = capability_by_id(
    "smartcmp.approvals.detail"
)
APPROVE_CAPABILITY = capability_by_id("smartcmp.approvals.approve")
REJECT_CAPABILITY = capability_by_id("smartcmp.approvals.reject")


async def list_pending_approvals(
    client: SmartCmpClient,
    query: ApprovalListQuery,
) -> ApprovalListResult:
    """List pending approvals using the current credential and bounded paging.

    Args:
        client: Request-scoped SmartCMP client.
        query: Optional lookback and page bounds.

    Returns:
        Raw pending rows and the upstream total when available.
    """

    now_ms = int(time.time() * 1000)
    items: list[dict[str, Any]] = []
    total: int | None = None
    for page in range(1, query.max_pages + 1):
        params = build_pending_query_params(
            page=page,
            page_size=query.page_size,
            days=query.days,
            now_ms=now_ms,
        )
        payload = await client.request_json(
            "GET",
            "/generic-request/current-activity-approval",
            params=params,
        )
        page_items = extract_pending_items(payload)
        items.extend(page_items)
        if total is None:
            total = _extract_total(payload)
        if len(page_items) < query.page_size:
            break
    return ApprovalListResult(
        items=tuple(items),
        total=total if total is not None else len(items),
    )


async def list_approval_flavors(
    client: SmartCmpClient,
) -> CatalogItemsResult:
    """List the legacy flavor catalog used for approval display enrichment."""

    payload = await client.request_json(
        "GET",
        "/flavors",
        params={
            "page": 1,
            "size": 500,
            "query": "",
            "queryValue": "",
            "sort": "createdDate,desc",
        },
    )
    rows = extract_pending_items(payload)
    if not isinstance(payload, (dict, list)):
        raise SmartCmpUpstreamError(
            "SmartCMP returned an unexpected flavor list payload.",
            trace_id=client.request.context.trace_id,
        )
    return CatalogItemsResult(items=tuple(rows))


async def get_pending_approval_detail(
    client: SmartCmpClient,
    query: ApprovalDetailQuery,
) -> ApprovalDetailResult:
    """Resolve one pending approval with bounded read-only polling.

    Authentication, permission, validation, and target-conflict failures are
    never retried. Transient read failures and a not-yet-visible pending row may
    be retried within the caller-provided bound.

    Args:
        client: Request-scoped SmartCMP client.
        query: Visible Request ID and polling policy.

    Returns:
        The exact pending row.

    Raises:
        SmartCmpValidationError: If the Request ID format is invalid.
        SmartCmpTargetResolutionError: If the row stays absent or is ambiguous.
        SmartCmpError: If a non-retryable upstream read fails.
    """

    request_id = _validated_request_id(query.request_id)
    last_retryable_error: SmartCmpError | None = None
    for attempt in range(query.max_attempts):
        try:
            result = await list_pending_approvals(
                client,
                ApprovalListQuery(days=query.days, max_pages=5),
            )
            last_retryable_error = None
            item = _resolve_pending_item(result.items, request_id)
            if item is not None:
                return ApprovalDetailResult(request_id=request_id, item=item)
        except (SmartCmpAuthenticationError, SmartCmpPermissionError):
            raise
        except SmartCmpTargetResolutionError:
            raise
        except (SmartCmpRateLimitError, SmartCmpTimeoutError, SmartCmpUpstreamError) as exc:
            last_retryable_error = exc
        if attempt < query.max_attempts - 1:
            await asyncio.sleep(query.retry_interval_seconds)

    if last_retryable_error is not None:
        error_type = type(last_retryable_error)
        raise error_type(
            "SmartCMP pending approval lookup failed after "
            f"{query.max_attempts} attempts.",
            trace_id=client.request.context.trace_id,
        ) from last_retryable_error
    raise SmartCmpTargetResolutionError(
        "No pending SmartCMP approval matched identifier: "
        f"{request_id} (after {query.max_attempts} attempts)",
        trace_id=client.request.context.trace_id,
    )


async def execute_approval_decision(
    client: SmartCmpClient,
    decision_input: ApprovalDecisionInput,
) -> ApprovalDecisionResult:
    """Execute one confirmed approval/rejection batch exactly once.

    The user-visible Request IDs are first resolved to the current internal
    activity IDs. The subsequent POST is never retried. A transport timeout or
    indeterminate response becomes ``SmartCmpUnknownOutcomeError`` so callers
    cannot automatically duplicate a decision.

    Args:
        client: Client bound to the acting user or robot credential.
        decision_input: Confirmed decision, visible Request IDs, and reason.

    Returns:
        One sanitized outcome per visible Request ID.

    Raises:
        SmartCmpTargetResolutionError: If a visible ID cannot be resolved
            uniquely to a current approval activity.
        SmartCmpUnknownOutcomeError: If the write may have reached SmartCMP.
        SmartCmpError: If SmartCMP definitely rejects the operation.
    """

    request_ids = _normalize_distinct_request_ids(decision_input.request_ids)
    pending = await list_pending_approvals(
        client,
        ApprovalListQuery(max_pages=decision_input.max_pages),
    )
    activity_ids = _resolve_activity_ids(pending.items, request_ids)
    path = f"/approval-activity/{decision_input.decision}/batch"
    body = {"reason": decision_input.reason} if decision_input.reason else {}
    try:
        payload = await client.request_json(
            "POST",
            path,
            params={"ids": ",".join(activity_ids)},
            json_body=body,
        )
    except SmartCmpError as exc:
        if write_result_is_unknown(exc):
            raise SmartCmpUnknownOutcomeError(
                "SmartCMP approval decision outcome is unknown; do not retry "
                f"automatically. {exc}",
                trace_id=client.request.context.trace_id,
            ) from exc
        raise

    items = _decision_items(
        decision_input.decision,
        request_ids,
        activity_ids,
        payload,
    )
    return ApprovalDecisionResult(
        decision=decision_input.decision,
        reason=decision_input.reason,
        items=tuple(items),
        overall_success=all(item.outcome == "succeeded" for item in items),
    )


def build_pending_query_params(
    *,
    page: int = 1,
    page_size: int = 50,
    days: int | None = None,
    now_ms: int,
) -> dict[str, Any]:
    """Build the SmartCMP pending-approval pagination and date filters."""

    params: dict[str, Any] = {
        "page": page,
        "size": page_size,
        "stage": "pending",
        "sort": "updatedDate,desc",
        "states": "",
    }
    if days is not None:
        start_of_today = now_ms - (now_ms % 86400000)
        params.update(
            {
                "startAtMin": start_of_today - (days * 86400000),
                "startAtMax": now_ms,
                "rangeField": "updatedDate",
            }
        )
    return params


def extract_pending_items(payload: Any) -> list[dict[str, Any]]:
    """Extract pending rows from supported SmartCMP response envelopes."""

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("content", "data", "items", "result"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _extract_total(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    for key in ("totalElements", "total", "totalCount", "count"):
        try:
            return int(payload.get(key))
        except (TypeError, ValueError):
            pass
    return None


def _validated_request_id(value: Any) -> str:
    request_id = str(value or "").strip()
    if not is_request_id(request_id):
        raise SmartCmpValidationError("Invalid SmartCMP Request ID.")
    return request_id


def _normalize_distinct_request_ids(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        request_id = _validated_request_id(value)
        key = request_id.casefold()
        if key in seen:
            raise SmartCmpValidationError(
                f"Duplicate SmartCMP Request ID: {request_id}"
            )
        seen.add(key)
        normalized.append(request_id)
    return tuple(normalized)


def _resolve_pending_item(
    items: tuple[dict[str, Any], ...],
    request_id: str,
) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []
    for item in items:
        ids = request_ids_from_item(item)
        if any(value.casefold() == request_id.casefold() for value in ids):
            if any(value.casefold() != request_id.casefold() for value in ids):
                raise SmartCmpTargetResolutionError(
                    f"Pending approval {request_id} returned conflicting Request IDs."
                )
            matches.append(item)
    if len(matches) > 1:
        activity_ids = {
            _activity_id(item)
            for item in matches
            if _activity_id(item)
        }
        if len(activity_ids) != 1:
            raise SmartCmpTargetResolutionError(
                f"Pending approval {request_id} matched multiple current activities."
            )
    return matches[0] if matches else None


def _resolve_activity_ids(
    items: tuple[dict[str, Any], ...],
    request_ids: tuple[str, ...],
) -> tuple[str, ...]:
    resolved: list[str] = []
    missing: list[str] = []
    missing_activity: list[str] = []
    for request_id in request_ids:
        item = _resolve_pending_item(items, request_id)
        if item is None:
            missing.append(request_id)
            continue
        activity_id = _activity_id(item)
        if not activity_id:
            missing_activity.append(request_id)
            continue
        resolved.append(activity_id)
    if missing:
        raise SmartCmpTargetResolutionError(
            "No pending SmartCMP approval matched Request ID(s): "
            + ", ".join(missing)
        )
    if missing_activity:
        raise SmartCmpTargetResolutionError(
            "Pending approval item(s) have no current activity ID: "
            + ", ".join(missing_activity)
        )
    activity_keys = [activity_id.casefold() for activity_id in resolved]
    if len(set(activity_keys)) != len(activity_keys):
        raise SmartCmpTargetResolutionError(
            "Multiple SmartCMP Request IDs resolved to the same current "
            "approval activity."
        )
    return tuple(resolved)


def _activity_id(item: dict[str, Any]) -> str:
    activity = item.get("currentActivity")
    if not isinstance(activity, dict):
        return ""
    return str(activity.get("id") or "").strip()


def _decision_items(
    decision: str,
    request_ids: tuple[str, ...],
    activity_ids: tuple[str, ...],
    payload: Any,
) -> list[ApprovalDecisionItem]:
    if isinstance(payload, dict):
        failed = _record_failed(payload, decision)
        succeeded = _record_succeeded(payload, decision)
        return [
            ApprovalDecisionItem(
                request_id=request_id,
                outcome=(
                    "failed"
                    if failed
                    else "succeeded"
                    if succeeded
                    else "unknown"
                ),
                status=(
                    _safe_record_status(payload, failed=failed)
                    if failed or succeeded
                    else "unknown"
                ),
                message=(
                    _record_message(payload, failed=failed)
                    if failed or succeeded
                    else "SmartCMP did not return verifiable aggregate results."
                ),
            )
            for request_id in request_ids
        ]
    if not isinstance(payload, list):
        return [
            ApprovalDecisionItem(
                request_id=request_id,
                outcome="unknown",
                status="unknown",
                message="SmartCMP did not return verifiable decision results.",
            )
            for request_id in request_ids
        ]

    # SmartCMP's batch endpoint returns one ordered response per submitted
    # activity and uses ``pass`` as the item-level execution result. Detect this
    # contract before the legacy activity-ID response shapes below; approvalId
    # identifies the parent Approval, not the submitted ApprovalActivity.
    if any(isinstance(record, dict) and "pass" in record for record in payload):
        return _ordered_batch_decision_items(decision, request_ids, payload)

    pending_records = [
        record if isinstance(record, dict) else None for record in payload
    ]
    by_activity_id = {
        activity_id.casefold(): request_id
        for request_id, activity_id in zip(
            request_ids,
            activity_ids,
            strict=True,
        )
    }
    assigned: dict[str, dict[str, Any]] = {}
    for record in pending_records:
        if record is None:
            continue
        record_activity_id = _record_activity_id(record)
        mapped_request_id = by_activity_id.get(record_activity_id.casefold())
        if mapped_request_id and mapped_request_id not in assigned:
            assigned[mapped_request_id] = record

    results: list[ApprovalDecisionItem] = []
    for request_id in request_ids:
        record = assigned.get(request_id)
        if record is None:
            results.append(
                ApprovalDecisionItem(
                    request_id=request_id,
                    outcome="unknown",
                    status="unknown",
                    message="SmartCMP did not return an item-level result.",
                )
            )
            continue
        failed = _record_failed(record, decision)
        succeeded = _record_succeeded(record, decision)
        if not failed and not succeeded:
            results.append(
                ApprovalDecisionItem(
                    request_id=request_id,
                    outcome="unknown",
                    status="unknown",
                    message="SmartCMP returned an unverified item-level result.",
                )
            )
            continue
        results.append(
            ApprovalDecisionItem(
                request_id=request_id,
                outcome="failed" if failed else "succeeded",
                status=_safe_record_status(record, failed=failed),
                message=_record_message(record, failed=failed),
            )
        )
    return results


def _ordered_batch_decision_items(
    decision: str,
    request_ids: tuple[str, ...],
    payload: list[Any],
) -> list[ApprovalDecisionItem]:
    """Map SmartCMP's ordered batch response without exposing internal IDs."""

    if len(payload) != len(request_ids) or not all(
        isinstance(record, dict) and type(record.get("pass")) is bool
        for record in payload
    ):
        return [
            ApprovalDecisionItem(
                request_id=request_id,
                outcome="unknown",
                status="unknown",
                message="SmartCMP returned an unverifiable batch decision result.",
            )
            for request_id in request_ids
        ]

    succeeded_status = "approved" if decision == "approve" else "rejected"
    return [
        ApprovalDecisionItem(
            request_id=request_id,
            outcome="succeeded" if record["pass"] else "failed",
            status=succeeded_status if record["pass"] else "failed",
            message=(
                ""
                if record["pass"]
                else _record_message(record, failed=True)
            ),
        )
        for request_id, record in zip(request_ids, payload, strict=True)
    ]


def _record_activity_id(record: dict[str, Any]) -> str:
    for field in ("activityId", "approvalActivityId", "id", "approvalId"):
        value = str(record.get(field) or "").strip()
        if value:
            return value
    return ""


def _record_state(record: dict[str, Any]) -> str:
    return str(record.get("status") or record.get("state") or "").strip()


def _record_failed(record: dict[str, Any], decision: str) -> bool:
    state = _record_state(record).casefold()
    code = record.get("code")
    return (
        record.get("success") is False
        or str(record.get("success") or "").casefold() == "false"
        or state in _FAILED_STATES
        or (decision == "approve" and state in {"denied", "rejected"})
        or (decision == "reject" and state in {"approve", "approved"})
        or (
            code not in (None, "", 0, "0", 200, "200")
            and str(code).casefold() not in {"ok", "success"}
        )
    )


def _record_succeeded(record: dict[str, Any], decision: str) -> bool:
    """Return whether one correlated response explicitly proves the decision."""

    state = _record_state(record).casefold()
    success = record.get("success")
    code = record.get("code")
    explicit_success = (
        success is True
        or str(success or "").casefold() == "true"
        or state in _SAFE_SUCCESS_STATES
        or code in (0, "0", 200, "200")
        or str(code or "").casefold() in {"ok", "success"}
    )
    if not explicit_success:
        return False
    if decision == "approve" and state in {"denied", "reject", "rejected"}:
        return False
    if decision == "reject" and state in {"approve", "approved"}:
        return False
    return True


def _safe_record_status(record: dict[str, Any], *, failed: bool) -> str:
    state = _record_state(record).casefold()
    if failed:
        return state if state in _FAILED_STATES | {"denied", "rejected"} else "failed"
    return state if state in _SAFE_SUCCESS_STATES else "completed"


def _record_message(record: dict[str, Any], *, failed: bool) -> str:
    if failed:
        return str(record.get("reason") or "").strip() or (
            "SmartCMP reported an item-level decision failure."
        )
    return ""
