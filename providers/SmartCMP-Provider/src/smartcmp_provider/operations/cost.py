"""SmartCMP cost evidence reads and confirmed native remediation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from smartcmp_provider.capabilities import capability_by_id
from smartcmp_provider.errors import (
    SmartCmpAuthenticationError,
    SmartCmpError,
    SmartCmpPermissionError,
    SmartCmpRateLimitError,
    SmartCmpTargetResolutionError,
    SmartCmpUnknownOutcomeError,
    SmartCmpUpstreamError,
    SmartCmpValidationError,
)
from smartcmp_provider.models.cost import (
    CostExecutionInput,
    CostExecutionResult,
    CostItemsResult,
    CostListQuery,
    CostRecommendationFactsQuery,
    CostRecommendationFactsResult,
    CurrencyEvidenceResult,
)
from smartcmp_provider.transport.client import SmartCmpClient
from smartcmp_provider.transport.mutations import write_result_is_unknown

EXECUTE_COST_OPTIMIZATION_CAPABILITY = capability_by_id(
    "smartcmp.cost.execute"
)


async def list_cost_violations(
    client: SmartCmpClient,
    query: CostListQuery,
) -> CostItemsResult:
    """List cost optimization violation facts."""

    return await _list_paged(
        client,
        "/compliance-policies/violations/search",
        query,
    )


async def list_cost_policies(
    client: SmartCmpClient,
    query: CostListQuery,
) -> CostItemsResult:
    """List cost optimization policy facts."""

    return await _list_paged(
        client,
        "/compliance-policies/search",
        query,
    )


async def list_policy_executions(
    client: SmartCmpClient,
    query: CostListQuery,
) -> CostItemsResult:
    """List policy evaluation execution facts."""

    return await _list_paged(
        client,
        "/compliance-policies/policy-executions/search",
        query,
    )


async def list_violation_instances(
    client: SmartCmpClient,
    query: CostListQuery,
) -> CostItemsResult:
    """List remediation violation-instance facts."""

    return await _list_paged(
        client,
        "/compliance-policies/violation-instances/search",
        query,
    )


async def list_resource_executions(
    client: SmartCmpClient,
    query: CostListQuery,
) -> CostItemsResult:
    """List resource-level remediation execution facts."""

    return await _list_paged(
        client,
        "/compliance-policies/resource-executions/search",
        query,
    )


async def get_cost_recommendation_facts(
    client: SmartCmpClient,
    query: CostRecommendationFactsQuery,
) -> CostRecommendationFactsResult:
    """Load one recommendation and bounded optional analysis evidence."""

    violation_id = query.violation_id.strip()
    violation = await client.request_json(
        "GET",
        f"/compliance-policies/violations/{quote(violation_id, safe='')}",
    )
    if not isinstance(violation, dict) or not violation:
        raise SmartCmpTargetResolutionError(
            f"Cost recommendation '{violation_id}' was not found.",
            trace_id=client.request.context.trace_id,
        )

    policy_id = str(violation.get("policyId") or "").strip()
    policy = (
        await _optional_record(
            client,
            f"/compliance-policies/{quote(policy_id, safe='')}",
        )
        if policy_id
        else None
    )
    policy_executions: tuple[dict[str, Any], ...] = ()
    if policy_id:
        execution_result = await _optional_list(
            client,
            list_policy_executions,
            CostListQuery(
                filters={"policyId": policy_id},
                page=0,
                size=5,
            ),
        )
        policy_executions = execution_result.items if execution_result else ()

    related_policy_count = 0
    category = str(violation.get("category") or "").strip()
    if category:
        policies = await _optional_list(
            client,
            list_cost_policies,
            CostListQuery(
                filters={"category": category},
                page=0,
                size=100,
            ),
        )
        if policies is not None:
            related_policy_count = max(0, len(policies.items) - 1)

    return CostRecommendationFactsResult(
        violation=violation,
        policy=policy,
        saving_summary=await _optional_payload(
            client,
            "/compliance-policies/overview/saving-summary",
        ),
        operation_summary=await _optional_payload(
            client,
            "/compliance-policies/overview/saving-operation-type-summary",
        ),
        saving_trend=await _optional_payload(
            client,
            "/compliance-policies/overview/saving-trend",
        ),
        resource_top=await _optional_payload(
            client,
            "/compliance-policies/overview/saving-resource-top",
        ),
        policy_executions=policy_executions,
        related_policy_count=related_policy_count,
    )


async def get_currency_evidence(
    client: SmartCmpClient,
) -> CurrencyEvidenceResult:
    """Load verified tenant currency code and symbol without guessing."""

    setting = await client.request_json("GET", "/tenants/current/setting")
    code = (
        str(setting.get("currencyUnitType") or "").strip()
        if isinstance(setting, dict)
        else ""
    )
    if not code:
        return CurrencyEvidenceResult()
    units = await client.request_json("GET", "/tenants/currencyUnits")
    if not isinstance(units, list):
        raise SmartCmpUpstreamError(
            "SmartCMP returned an unexpected currency unit payload.",
            trace_id=client.request.context.trace_id,
        )
    for unit in units:
        if not isinstance(unit, dict) or str(unit.get("code") or "") != code:
            continue
        symbol = str(unit.get("symbol") or "").strip()
        if symbol:
            return CurrencyEvidenceResult(
                symbol=symbol,
                code=code,
                source="smartcmp_tenant_settings",
            )
    return CurrencyEvidenceResult()


async def execute_cost_optimization(
    client: SmartCmpClient,
    execution_input: CostExecutionInput,
) -> CostExecutionResult:
    """Submit one confirmed SmartCMP day-two cost fix exactly once.

    Args:
        client: Client bound to the acting user or robot credential.
        execution_input: Cost violation selected for remediation.

    Returns:
        Submission facts and the upstream response.

    Raises:
        SmartCmpValidationError: If the violation ID is blank.
        SmartCmpUnknownOutcomeError: If the write may have reached SmartCMP.
        SmartCmpError: If SmartCMP definitely rejects the operation.
    """

    violation_id = execution_input.violation_id.strip()
    if not violation_id:
        raise SmartCmpValidationError(
            "Violation ID must not be empty.",
            trace_id=client.request.context.trace_id,
        )
    try:
        payload = await client.request_json(
            "POST",
            "/compliance-policies/violations/day2/fix/"
            f"{quote(violation_id, safe='')}",
            json_body={},
            allow_empty=True,
        )
    except SmartCmpError as exc:
        if write_result_is_unknown(exc):
            raise SmartCmpUnknownOutcomeError(
                "SmartCMP cost optimization outcome is unknown; do not retry "
                f"automatically. {exc}",
                trace_id=client.request.context.trace_id,
            ) from exc
        raise
    return CostExecutionResult(
        violation_id=violation_id,
        message="SmartCMP day2 fix request submitted.",
        response=payload,
    )


async def _list_paged(
    client: SmartCmpClient,
    path: str,
    query: CostListQuery,
) -> CostItemsResult:
    items: list[dict[str, Any]] = []
    total: int | None = None
    for offset in range(query.max_pages):
        page = query.page + offset
        params = dict(query.filters)
        params.update({"page": page, "size": query.size})
        payload = await client.request_json("GET", path, params=params)
        page_items = _extract_items(payload)
        items.extend(page_items)
        if total is None:
            total = _extract_total(payload)
        if query.max_pages == 1:
            break
        total_pages = _extract_total_pages(payload)
        if isinstance(payload, dict) and payload.get("last") is True:
            break
        if total_pages is not None and page + 1 >= total_pages:
            break
        if total_pages is None and len(page_items) < query.size:
            break
    else:
        raise SmartCmpUpstreamError(
            f"SmartCMP pagination exceeded {query.max_pages} pages for {path}.",
            trace_id=client.request.context.trace_id,
        )
    return CostItemsResult(items=tuple(items), total=total)


async def _optional_payload(
    client: SmartCmpClient,
    path: str,
) -> Any:
    try:
        return await client.request_json("GET", path)
    except (
        SmartCmpAuthenticationError,
        SmartCmpPermissionError,
        SmartCmpRateLimitError,
    ):
        raise
    except SmartCmpError:
        return None


async def _optional_record(
    client: SmartCmpClient,
    path: str,
) -> dict[str, Any] | None:
    payload = await _optional_payload(client, path)
    return payload if isinstance(payload, dict) else None


async def _optional_list(
    client: SmartCmpClient,
    operation: Callable[
        [SmartCmpClient, CostListQuery],
        Any,
    ],
    query: CostListQuery,
) -> CostItemsResult | None:
    try:
        result = await operation(client, query)
    except (
        SmartCmpAuthenticationError,
        SmartCmpPermissionError,
        SmartCmpRateLimitError,
    ):
        raise
    except SmartCmpError:
        return None
    return result if isinstance(result, CostItemsResult) else None


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        raise SmartCmpUpstreamError(
            "SmartCMP returned an unexpected cost list payload."
        )
    for key in ("content", "items", "result", "data"):
        if key not in payload:
            continue
        value = payload[key]
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            return _extract_items(value)
        raise SmartCmpUpstreamError(
            "SmartCMP returned an unexpected cost list payload."
        )
    raise SmartCmpUpstreamError(
        "SmartCMP returned an unexpected cost list payload."
    )


def _extract_total(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    for key in ("totalElements", "total", "totalCount", "count"):
        try:
            return int(payload.get(key))
        except (TypeError, ValueError):
            pass
    for key in ("data", "result"):
        nested = _extract_total(payload.get(key))
        if nested is not None:
            return nested
    return None


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
