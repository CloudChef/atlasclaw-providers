"""SmartCMP Security compliance reads and the manual status update primitive."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from smartcmp_provider.errors import (
    SmartCmpAuthenticationError,
    SmartCmpError,
    SmartCmpPermissionError,
    SmartCmpRateLimitError,
    SmartCmpTargetResolutionError,
    SmartCmpUpstreamError,
    SmartCmpValidationError,
)
from smartcmp_provider.models.security_compliance import (
    ResourceSecurityViolationQuery,
    ResourceSecurityViolationResult,
    SecurityRecordCollection,
    SecurityViolationListQuery,
    SecurityViolationListResult,
)
from smartcmp_provider.transport.client import SmartCmpClient


SECURITY_CATEGORY = "SECURITY"
RESOURCE_VIOLATION_PAGE_SIZE = 100
SECURITY_VIOLATION_FIELDS = (
    "id",
    "policyId",
    "policyName",
    "remedie",
    "resourceId",
    "resourceName",
    "resourceExternalName",
    "resourceExternalId",
    "resourceType",
    "componentType",
    "nodeInstanceId",
    "category",
    "severity",
    "status",
    "lastExecuteDate",
    "lastOperator",
    "times",
    "fixTime",
    "serialNumber",
    "updatedDate",
)
SECURITY_POLICY_FIELDS = (
    "id",
    "name",
    "nameZh",
    "description",
    "descriptionZh",
    "category",
    "severity",
    "type",
    "buildIn",
    "enabled",
    "status",
    "resourceType",
    "resourceTypes",
    "cloudEntryType",
    "cloudEntryTypes",
    "scope",
    "lastExecuteDate",
    "lastExecuteStatus",
    "remedie",
    "remedieZh",
    "ruleContent",
    "createdBy",
    "createdDate",
    "updatedDate",
)
SECURITY_POLICY_CONFIG_FIELDS = (
    "id",
    "policyId",
    "policyType",
    "name",
    "description",
    "category",
    "severity",
    "type",
    "enabled",
    "status",
    "resourceType",
    "resourceTypes",
    "cloudEntryType",
    "cloudEntryTypes",
    "scope",
    "scopeType",
    "scopeIds",
    "rule",
    "rules",
    "condition",
    "conditions",
    "expression",
    "property",
    "operator",
    "value",
    "values",
    "lastExecuteDate",
    "lastExecuteStatus",
    "remedie",
    "createdDate",
    "updatedDate",
)


@dataclass(frozen=True, slots=True)
class _PageCollection:
    items: tuple[dict[str, Any], ...]
    total: int | None
    scanned_pages: int
    has_more: bool
    next_page: int | None
    coverage: str
    truncated: bool
    errors: tuple[str, ...]


async def query_security_violations(
    client: SmartCmpClient,
    query: SecurityViolationListQuery,
) -> SecurityViolationListResult:
    """Query Security violations with one-based request pagination.

    Args:
        client: Client bound to the acting SmartCMP principal.
        query: Status, severity, search, and bounded pagination inputs.

    Returns:
        Security violation rows and explicit collection coverage.

    Raises:
        SmartCmpValidationError: If the requested status is unsupported.
        SmartCmpError: If SmartCMP cannot serve any requested page.
    """

    status = _normalize_status(query.status, trace_id=client.request.context.trace_id)
    params: dict[str, Any] = {
        "category": SECURITY_CATEGORY,
        "sort": "lastExecuteDate,desc",
    }
    if status:
        params["status"] = status
    severities = tuple(
        value
        for value in (str(item or "").strip().upper() for item in query.severities)
        if value
    )
    if severities:
        params["severity"] = list(severities)
    query_value = query.query_value.strip()
    if query_value:
        params["queryValue"] = query_value

    collected = await _collect_pages(
        client,
        "/compliance-policies/violations/search",
        params=params,
        page=query.page,
        size=query.size,
        max_pages=query.max_pages,
        tolerate_page_errors=False,
    )
    if any(
        not is_security_category(item.get("category"))
        for item in collected.items
    ):
        raise SmartCmpUpstreamError(
            "SmartCMP returned a non-Security row for a Security violation search.",
            trace_id=client.request.context.trace_id,
        )
    return SecurityViolationListResult(
        items=tuple(_normalize_violation_rows(collected.items, query.page, query.size)),
        page=query.page,
        size=query.size,
        total=collected.total,
        scanned_pages=collected.scanned_pages,
        has_more=collected.has_more,
        next_page=collected.next_page,
        coverage=collected.coverage,
        truncated=collected.truncated,
        errors=collected.errors,
    )


async def query_resource_security_violations(
    client: SmartCmpClient,
    query: ResourceSecurityViolationQuery,
) -> ResourceSecurityViolationResult:
    """Scan Security violations in every lifecycle state for one resource.

    SmartCMP currently ignores its documented ``resourceId`` filter for this
    endpoint. This operation therefore scans the root Security category with a
    fixed page size and performs an exact local ``resourceId`` comparison.

    Args:
        client: Client bound to the acting SmartCMP principal.
        query: Explicit resource ID and scan bound.

    Returns:
        Matching violations together with complete, partial, or failed coverage.

    Raises:
        SmartCmpValidationError: If the resource ID contains only whitespace.
        SmartCmpAuthenticationError: If SmartCMP rejects the credential.
        SmartCmpPermissionError: If the principal cannot read violations.
        SmartCmpRateLimitError: If SmartCMP throttles the scan.
    """

    resource_id = query.resource_id.strip()
    if not resource_id:
        raise SmartCmpValidationError(
            "Resource ID must not be empty.",
            trace_id=client.request.context.trace_id,
        )
    collected = await _collect_pages(
        client,
        "/compliance-policies/violations/search",
        params={
            "category": SECURITY_CATEGORY,
            "sort": "lastExecuteDate,desc",
        },
        page=1,
        size=RESOURCE_VIOLATION_PAGE_SIZE,
        max_pages=query.max_pages,
        tolerate_page_errors=True,
    )
    matches = [
        item
        for item in collected.items
        if str(item.get("resourceId") or "") == resource_id
        and is_security_category(item.get("category"))
    ]
    normalized = tuple(_normalize_violation_rows(tuple(matches), 1, len(matches) or 1))
    return ResourceSecurityViolationResult(
        resource_id=resource_id,
        items=normalized,
        total=collected.total,
        matched_total=len(normalized),
        scanned_pages=collected.scanned_pages,
        has_more=collected.has_more,
        next_page=collected.next_page,
        coverage=collected.coverage,
        truncated=collected.truncated,
        errors=collected.errors,
    )


async def get_security_violation_facts(
    client: SmartCmpClient,
    violation_id: str,
) -> dict[str, Any]:
    """Load one current violation and prove that it belongs to Security.

    Args:
        client: Client bound to the acting SmartCMP principal.
        violation_id: Exact SmartCMP policy violation ID.

    Returns:
        The current upstream violation record.

    Raises:
        SmartCmpTargetResolutionError: If no record is returned.
        SmartCmpValidationError: If the record is not a Security violation.
        SmartCmpError: If the required detail read fails.
    """

    normalized_id = str(violation_id or "").strip()
    if not normalized_id:
        raise SmartCmpValidationError(
            "Violation ID must not be empty.",
            trace_id=client.request.context.trace_id,
        )
    payload = await client.request_json(
        "GET",
        f"/compliance-policies/violations/{quote(normalized_id, safe='')}",
    )
    violation = _extract_record(payload)
    if not violation:
        raise SmartCmpTargetResolutionError(
            f"Security violation '{normalized_id}' was not found.",
            trace_id=client.request.context.trace_id,
        )
    returned_id = str(
        violation.get("id") or violation.get("violationId") or ""
    ).strip()
    if returned_id != normalized_id:
        raise SmartCmpTargetResolutionError(
            f"Security violation '{normalized_id}' returned mismatched identity.",
            trace_id=client.request.context.trace_id,
        )
    if not is_security_category(violation.get("category")):
        category = str(violation.get("category") or "unknown")
        raise SmartCmpValidationError(
            f"Violation '{normalized_id}' belongs to category '{category}', not Security.",
            trace_id=client.request.context.trace_id,
        )
    return violation


async def get_security_policy_facts(
    client: SmartCmpClient,
    policy_id: str,
) -> dict[str, Any]:
    """Load one Security violation's policy for best-effort enrichment.

    Args:
        client: Client bound to the acting SmartCMP principal.
        policy_id: Exact SmartCMP compliance policy ID.

    Returns:
        The current policy record.

    Raises:
        SmartCmpTargetResolutionError: If no policy record is returned.
        SmartCmpError: If the policy read fails.
    """

    normalized_id = str(policy_id or "").strip()
    if not normalized_id:
        raise SmartCmpValidationError(
            "Policy ID must not be empty.",
            trace_id=client.request.context.trace_id,
        )
    payload = await client.request_json(
        "GET",
        f"/compliance-policies/{quote(normalized_id, safe='')}",
    )
    policy = _extract_record(payload)
    if not policy:
        raise SmartCmpTargetResolutionError(
            f"Security policy '{normalized_id}' was not found.",
            trace_id=client.request.context.trace_id,
        )
    returned_id = str(policy.get("id") or policy.get("policyId") or "").strip()
    if returned_id != normalized_id:
        raise SmartCmpTargetResolutionError(
            f"Security policy '{normalized_id}' returned mismatched identity.",
            trace_id=client.request.context.trace_id,
        )
    category = str(policy.get("category") or "").strip()
    if category and not is_security_category(category):
        raise SmartCmpValidationError(
            f"Policy '{normalized_id}' belongs to category '{category}', not Security.",
            trace_id=client.request.context.trace_id,
        )
    return _project_security_policy(policy)


async def query_security_policies(
    client: SmartCmpClient,
) -> SecurityRecordCollection:
    """Collect bounded Security policy inventory for the overview.

    Args:
        client: Client bound to the acting SmartCMP principal.

    Returns:
        Up to 50 pages of root Security policy records and coverage.
    """

    collected = await _collect_pages(
        client,
        "/compliance-policies/search",
        params={"category": SECURITY_CATEGORY},
        page=1,
        size=100,
        max_pages=50,
        tolerate_page_errors=False,
    )
    return _as_record_collection(collected)


async def query_security_policy_executions(
    client: SmartCmpClient,
) -> SecurityRecordCollection:
    """Collect bounded Security policy execution inventory for the overview.

    Args:
        client: Client bound to the acting SmartCMP principal.

    Returns:
        Up to 50 pages of root Security execution records and coverage.
    """

    collected = await _collect_pages(
        client,
        "/compliance-policies/policy-executions/search",
        params={"category": SECURITY_CATEGORY, "lastExecution": True},
        page=1,
        size=100,
        max_pages=50,
        tolerate_page_errors=False,
    )
    return _as_record_collection(collected)


async def get_security_compliance_overview_payload(client: SmartCmpClient) -> Any:
    """Read the root Security compliance summary chart payload.

    Args:
        client: Client bound to the acting SmartCMP principal.

    Returns:
        Raw chart facts returned by SmartCMP.
    """

    return await client.request_json(
        "GET",
        "/compliance-policies/overview/compliance",
        params={"category": SECURITY_CATEGORY},
    )


async def get_security_violation_overview_payload(client: SmartCmpClient) -> Any:
    """Read the root Security severity summary chart payload.

    Args:
        client: Client bound to the acting SmartCMP principal.

    Returns:
        Raw chart facts returned by SmartCMP.
    """

    return await client.request_json(
        "GET",
        "/compliance-policies/overview/violation",
        params={"category": SECURITY_CATEGORY},
    )


async def get_security_compliance_trend_payload(
    client: SmartCmpClient,
    *,
    start_time: int,
    end_time: int,
) -> Any:
    """Read Security compliance trend facts for one epoch-millisecond range.

    Args:
        client: Client bound to the acting SmartCMP principal.
        start_time: Inclusive range start in epoch milliseconds.
        end_time: Inclusive range end in epoch milliseconds.

    Returns:
        Raw chart facts returned by SmartCMP.
    """

    return await client.request_json(
        "GET",
        "/compliance-policies/overview/compliance-trend",
        params={
            "category": SECURITY_CATEGORY,
            "startTime": start_time,
            "endTime": end_time,
        },
    )


async def get_security_violation_trend_payload(
    client: SmartCmpClient,
    *,
    start_time: int,
    end_time: int,
) -> Any:
    """Read Security violation trend facts for one epoch-millisecond range.

    Args:
        client: Client bound to the acting SmartCMP principal.
        start_time: Inclusive range start in epoch milliseconds.
        end_time: Inclusive range end in epoch milliseconds.

    Returns:
        Raw chart facts returned by SmartCMP.
    """

    return await client.request_json(
        "GET",
        "/compliance-policies/overview/violation-trend",
        params={
            "category": SECURITY_CATEGORY,
            "startTime": start_time,
            "endTime": end_time,
        },
    )


async def mark_security_violation_fixed_once(
    client: SmartCmpClient,
    violation_id: str,
) -> Any:
    """Send the status-changing GET exactly once.

    The endpoint is a semantic write despite its HTTP method. This primitive
    intentionally contains no retry; the service maps ambiguous failures to an
    unknown-outcome error and performs the required post-read verification.

    Args:
        client: Client bound to the acting SmartCMP principal.
        violation_id: Exact Security violation ID already revalidated by service.

    Returns:
        Decoded response or an empty object for a successful blank response.

    Raises:
        SmartCmpError: If SmartCMP rejects or cannot complete the status update.
    """

    return await client.request_json(
        "GET",
        f"/compliance-policies/{quote(violation_id, safe='')}/violation/FIXED",
        allow_empty=True,
    )


def is_security_category(value: Any) -> bool:
    """Return whether a category is the Security root or one of its children.

    Args:
        value: Raw SmartCMP category value.

    Returns:
        ``True`` for ``SECURITY`` and ``SECURITY.*`` only.
    """

    category = str(value or "").strip().upper()
    return category == SECURITY_CATEGORY or category.startswith(f"{SECURITY_CATEGORY}.")


async def _collect_pages(
    client: SmartCmpClient,
    path: str,
    *,
    params: dict[str, Any],
    page: int,
    size: int,
    max_pages: int,
    tolerate_page_errors: bool,
) -> _PageCollection:
    items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    total: int | None = None
    scanned_pages = 0
    has_more = True
    next_page: int | None = page
    errors: list[str] = []

    for offset in range(max_pages):
        request_page = page + offset
        request_params = dict(params)
        request_params.update({"page": request_page, "size": size})
        try:
            payload = await client.request_json("GET", path, params=request_params)
            page_items = _extract_items(
                payload,
                trace_id=client.request.context.trace_id,
            )
        except (
            SmartCmpAuthenticationError,
            SmartCmpPermissionError,
            SmartCmpRateLimitError,
        ):
            raise
        except SmartCmpError as exc:
            if not tolerate_page_errors:
                raise
            errors.append(SmartCmpClient.sanitize_error_text(str(exc)))
            next_page = request_page
            break

        for item in page_items:
            record_id = str(item.get("id") or "").strip()
            if record_id and record_id in seen_ids:
                continue
            if record_id:
                seen_ids.add(record_id)
            items.append(item)
        scanned_pages += 1
        if total is None:
            total = _extract_int(payload, ("totalElements", "total", "totalCount", "count"))
        has_more = _page_has_more(
            payload,
            requested_page=request_page,
            page_size=size,
            page_item_count=len(page_items),
            total=total,
        )
        next_page = request_page + 1 if has_more else None
        if not has_more:
            break

    coverage = "complete"
    if errors and scanned_pages == 0:
        coverage = "failed"
    elif errors or has_more:
        coverage = "partial"
    return _PageCollection(
        items=tuple(items),
        total=total,
        scanned_pages=scanned_pages,
        has_more=has_more,
        next_page=next_page,
        coverage=coverage,
        truncated=coverage != "complete",
        errors=tuple(errors),
    )


def _normalize_status(value: str, *, trace_id: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized in {"", "ALL"}:
        return ""
    if normalized not in {"ACTIVED", "FIXED"}:
        raise SmartCmpValidationError(
            "Security violation status must be ACTIVED, FIXED, or ALL.",
            trace_id=trace_id,
        )
    return normalized


def _extract_record(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    for key in ("data", "result", "item"):
        value = payload.get(key)
        if isinstance(value, dict):
            return dict(value)
    return dict(payload)


def _extract_items(payload: Any, *, trace_id: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("content", "items", "data", "result"):
            if key not in payload:
                continue
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                return _extract_items(value, trace_id=trace_id)
    raise SmartCmpUpstreamError(
        "SmartCMP returned an unexpected Security compliance list payload.",
        trace_id=trace_id,
    )


def _extract_int(payload: Any, keys: tuple[str, ...]) -> int | None:
    if not isinstance(payload, dict):
        return None
    for key in keys:
        try:
            return int(payload.get(key))
        except (TypeError, ValueError):
            pass
    for key in ("data", "result"):
        nested = _extract_int(payload.get(key), keys)
        if nested is not None:
            return nested
    return None


def _page_has_more(
    payload: Any,
    *,
    requested_page: int,
    page_size: int,
    page_item_count: int,
    total: int | None,
) -> bool:
    if isinstance(payload, dict):
        if payload.get("last") is True:
            return False
        if payload.get("last") is False:
            return True
        for key in ("data", "result"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                return _page_has_more(
                    nested,
                    requested_page=requested_page,
                    page_size=page_size,
                    page_item_count=page_item_count,
                    total=total,
                )
    total_pages = _extract_int(payload, ("totalPages", "pages"))
    response_number = _extract_int(payload, ("number",))
    if total_pages is not None:
        current_index = response_number if response_number is not None else requested_page - 1
        return current_index + 1 < total_pages
    if total is not None:
        current_index = response_number if response_number is not None else requested_page - 1
        return (current_index + 1) * page_size < total
    return page_item_count >= page_size


def _normalize_violation_rows(
    items: tuple[dict[str, Any], ...],
    page: int,
    size: int,
) -> list[dict[str, Any]]:
    start_index = (page - 1) * size + 1
    normalized: list[dict[str, Any]] = []
    for offset, item in enumerate(items):
        row = {
            field: item.get(field)
            for field in SECURITY_VIOLATION_FIELDS
            if field in item
        }
        row["violationId"] = str(item.get("id") or item.get("violationId") or "")
        row["index"] = start_index + offset
        normalized.append(row)
    return normalized


def _project_security_policy(policy: dict[str, Any]) -> dict[str, Any]:
    """Project policy evidence without exposing executable repair contracts.

    Args:
        policy: Raw Security policy detail returned by SmartCMP.

    Returns:
        Security identity, rule, scope, remediation text, and evaluation facts.
        Cost-saving fields and executable Day-2/task fields are omitted.
    """

    projected = {
        field: policy.get(field)
        for field in SECURITY_POLICY_FIELDS
        if field in policy
    }
    configs = policy.get("policyConfigs")
    if isinstance(configs, list):
        projected["policyConfigs"] = [
            {
                field: config.get(field)
                for field in SECURITY_POLICY_CONFIG_FIELDS
                if field in config
            }
            for config in configs
            if isinstance(config, dict)
        ]
    return projected


def _as_record_collection(collected: _PageCollection) -> SecurityRecordCollection:
    return SecurityRecordCollection(
        items=collected.items,
        total=collected.total,
        scanned_pages=collected.scanned_pages,
        coverage=collected.coverage,
        truncated=collected.truncated,
    )
