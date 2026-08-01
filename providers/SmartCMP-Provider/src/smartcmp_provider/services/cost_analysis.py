"""Shared SmartCMP cost recommendation and resource analysis services."""

from __future__ import annotations

from typing import Any

from smartcmp_provider.analysis.cost.recommendation import (
    build_recommendation_analysis_payload,
)
from smartcmp_provider.analysis.cost.resource_cost import (
    build_analysis_payload as build_resource_cost_payload,
    build_policy_coverages,
    build_resource_projection,
    project_violation,
    project_execution_extra,
)
from smartcmp_provider.domain.resource_resolution import (
    collect_resource_ids_from_summaries,
)
from smartcmp_provider.domain.resource_normalization import (
    build_normalized_resource,
)
from smartcmp_provider.domain.cost import normalize_money, normalize_timestamp
from smartcmp_provider.domain.cost import available_cost_operations
from smartcmp_provider.domain.object_operations import serialize_available_operations
from smartcmp_provider.errors import (
    SmartCmpAuthenticationError,
    SmartCmpError,
    SmartCmpPermissionError,
    SmartCmpRateLimitError,
    SmartCmpTargetResolutionError,
)
from smartcmp_provider.models.cost import (
    CostListQuery,
    CostRecommendationAnalysisResult,
    CostRecommendationFactsQuery,
    CostRecommendationListQuery,
    CostRecommendationListResult,
    ResourceCostAnalysisQuery,
    ResourceCostAnalysisResult,
)
from smartcmp_provider.models.resources import (
    ResourceEvidenceQuery,
    ResourceSummarySearchQuery,
)
from smartcmp_provider.operations.cost import (
    get_cost_recommendation_facts,
    get_currency_evidence,
    list_cost_policies,
    list_cost_violations,
    list_resource_executions,
)
from smartcmp_provider.operations.resources import (
    load_resource_evidence,
    search_resource_summaries,
)
from smartcmp_provider.transport.client import SmartCmpClient


async def list_cost_recommendations(
    client: SmartCmpClient,
    query: CostRecommendationListQuery,
) -> CostRecommendationListResult:
    """List normalized violations with optional related-policy counts."""

    result = await list_cost_violations(
        client,
        CostListQuery(
            filters=query.filters,
            page=query.page,
            size=query.size,
            max_pages=query.max_pages,
        ),
    )
    rows = [dict(item) for item in result.items]
    category_counts: dict[str, int] = {}
    if query.include_related_policy_count:
        for category in {
            str(item.get("category") or "").strip()
            for item in rows
            if str(item.get("category") or "").strip()
        }:
            policies = await list_cost_policies(
                client,
                CostListQuery(
                    filters={"category": category},
                    page=0,
                    size=100,
                ),
            )
            category_counts[category] = len(policies.items)
    normalized = tuple(
        normalize_cost_recommendation(
            item,
            index=index,
            related_policy_count=(
                max(
                    0,
                    category_counts.get(
                        str(item.get("category") or "").strip(),
                        0,
                    )
                    - 1,
                )
                if query.include_related_policy_count
                else None
            ),
        )
        for index, item in enumerate(rows, start=1)
    )
    currency = await get_currency_evidence(client)
    return CostRecommendationListResult(
        items=normalized,
        total=result.total,
        currency_symbol=currency.symbol or "",
        currency_code=currency.code,
    )


async def analyze_cost_recommendation(
    client: SmartCmpClient,
    query: CostRecommendationFactsQuery,
) -> CostRecommendationAnalysisResult:
    """Build one complete recommendation assessment from shared Provider evidence."""

    result = await get_cost_recommendation_facts(client, query)
    violation = dict(result.violation)
    resource_records = await _load_violation_resource_records(
        client,
        violation,
    )
    currency = await get_currency_evidence(client)
    payload = build_recommendation_analysis_payload(
        violation,
        result.policy,
        saving_summary=result.saving_summary,
        operation_summary=result.operation_summary,
        saving_trend=result.saving_trend,
        resource_top=result.resource_top,
        policy_executions=list(result.policy_executions),
        resource_records=resource_records,
        related_policy_count=result.related_policy_count,
        currency=currency.symbol or "",
    )
    result = CostRecommendationAnalysisResult.model_validate(payload)
    return result.model_copy(
        update={"available_operations": available_cost_operations(result.facts)}
    )


async def analyze_resource_cost(
    client: SmartCmpClient,
    query: ResourceCostAnalysisQuery,
) -> ResourceCostAnalysisResult:
    """Collect resource, policy, violation, and currency evidence in the Provider."""

    evidence = await load_resource_evidence(
        client,
        ResourceEvidenceQuery(resource_ids=(query.resource_id,)),
    )
    records = [dict(record) for record in evidence.records]
    if not records or records[0].get("fetchStatus") != "ok":
        raise SmartCmpTargetResolutionError(
            f"Resource '{query.resource_id}' could not be loaded.",
            trace_id=client.request.context.trace_id,
        )
    record = records[0]
    record["normalized"] = build_normalized_resource(record)
    resource = build_resource_projection(record)
    policies = await list_cost_policies(
        client,
        CostListQuery(
            filters={"category": "COST-OPTIMIZATION"},
            page=0,
            size=100,
            max_pages=100,
        ),
    )
    coverages = build_policy_coverages(
        [dict(item) for item in policies.items],
        resource=resource,
        resource_id=query.resource_id,
    )
    violations = await list_cost_violations(
        client,
        CostListQuery(
            filters={
                "status": "ACTIVED",
                "category": "COST-OPTIMIZATION",
                "resourceId": query.resource_id,
                "sort": "lastExecuteDate,desc",
            },
            page=0,
            size=100,
            max_pages=100,
        ),
    )
    active = [
        project_violation(item)
        for item in violations.items
        if str(item.get("resourceId") or "") == query.resource_id
    ]
    for coverage in coverages:
        coverage["activeViolationIds"] = [
            violation["violationId"]
            for violation in active
            if violation.get("policyId") == coverage.get("policyId")
        ]
    errors = list(record.get("errors") or [])
    errors.extend(
        await _enrich_resource_executions(
            client,
            coverages,
            resource_id=query.resource_id,
        )
    )
    try:
        currency = await get_currency_evidence(client)
    except (
        SmartCmpAuthenticationError,
        SmartCmpPermissionError,
        SmartCmpRateLimitError,
    ):
        raise
    except SmartCmpError:
        currency = None
        errors.append("SmartCMP tenant currency evidence is unavailable.")
    payload = build_resource_cost_payload(
        resource_id=query.resource_id,
        resource=resource,
        policy_coverages=coverages,
        active_violations=active,
        currency=currency.symbol if currency else None,
        currency_code=currency.code if currency else "",
        currency_source=currency.source if currency else "",
        errors=errors,
    )
    return ResourceCostAnalysisResult.model_validate(payload)


def normalize_cost_recommendation(
    item: dict[str, Any],
    *,
    index: int,
    related_policy_count: int | None = None,
) -> dict[str, Any]:
    """Normalize one SmartCMP policy violation for any output adapter."""

    task_definition = item.get("taskDefinition") or {}
    normalized = {
        "index": index,
        "violationId": item.get("id", ""),
        "policyId": item.get("policyId", ""),
        "policyName": item.get("policyName", ""),
        "resourceId": item.get("resourceId", ""),
        "resourceName": item.get("resourceName", ""),
        "resourceType": item.get("resourceType", ""),
        "componentType": item.get("componentType", ""),
        "status": item.get("status", ""),
        "severity": item.get("severity", ""),
        "category": item.get("category", ""),
        "monthlyCost": normalize_money(item.get("monthlyCost")),
        "monthlySaving": normalize_money(item.get("monthlySaving")),
        "savingOperationType": item.get("savingOperationType", ""),
        "fixType": item.get("fixType", ""),
        "taskInstanceId": item.get("taskInstanceId", ""),
        "lastExecuteDate": normalize_timestamp(item.get("lastExecuteDate")),
        "taskDefinitionId": task_definition.get("id", ""),
        "taskDefinitionName": task_definition.get("name", ""),
    }
    normalized["available_operations"] = serialize_available_operations(
        available_cost_operations(normalized)
    )
    if related_policy_count is not None:
        normalized["relatedPolicyCount"] = related_policy_count
    return normalized


async def _optional_resource_records(
    client: SmartCmpClient,
    resource_ids: list[str],
) -> list[dict[str, Any]]:
    ids = tuple(value for value in resource_ids if value)
    if not ids:
        return []
    try:
        result = await load_resource_evidence(
            client,
            ResourceEvidenceQuery(resource_ids=ids),
        )
    except (
        SmartCmpAuthenticationError,
        SmartCmpPermissionError,
        SmartCmpRateLimitError,
    ):
        raise
    except SmartCmpError:
        return []
    records = [dict(record) for record in result.records]
    for record in records:
        if record.get("fetchStatus") == "ok":
            record["normalized"] = build_normalized_resource(record)
    return records


async def _load_violation_resource_records(
    client: SmartCmpClient,
    violation: dict[str, Any],
) -> list[dict[str, Any]]:
    """Resolve violation resource evidence through one explicit fallback chain."""

    direct_id = str(violation.get("resourceId") or "").strip()
    records = await _optional_resource_records(client, [direct_id])
    if any(record.get("fetchStatus") == "ok" for record in records):
        return records

    node_instance_id = str(
        violation.get("nodeInstanceId")
        or violation.get("resourceNodeInstanceId")
        or ""
    ).strip()
    external_id = str(
        violation.get("resourceExternalId")
        or violation.get("externalId")
        or ""
    ).strip()
    resource_name = str(
        violation.get("resourceExternalName")
        or violation.get("resourceName")
        or ""
    ).strip()
    resolved_ids: list[str] = []
    lookup_candidates = (
        ({"nodeInstanceId": node_instance_id}, None)
        if node_instance_id
        else None,
        ({"externalIds": external_id}, None) if external_id else None,
        (None, {"queryValue": resource_name}) if resource_name else None,
    )
    for lookup in lookup_candidates:
        if lookup is None:
            continue
        params, payload = lookup
        try:
            summaries = await search_resource_summaries(
                client,
                ResourceSummarySearchQuery(
                    params=params or {},
                    payload=payload,
                ),
            )
        except (
            SmartCmpAuthenticationError,
            SmartCmpPermissionError,
            SmartCmpRateLimitError,
        ):
            raise
        except SmartCmpError:
            continue
        candidates = collect_resource_ids_from_summaries(
            list(summaries.items),
            expected_name=resource_name if payload else "",
            preferred_external_id=external_id,
            preferred_node_instance_id=node_instance_id,
        )
        if candidates:
            resolved_ids.extend(candidates)
            break
    fallback_ids = list(
        dict.fromkeys(
            resource_id
            for resource_id in resolved_ids
            if resource_id and resource_id != direct_id
        )
    )
    if not fallback_ids:
        return records
    return records + await _optional_resource_records(client, fallback_ids)


async def _enrich_resource_executions(
    client: SmartCmpClient,
    coverages: list[dict[str, Any]],
    *,
    resource_id: str,
) -> list[str]:
    """Attach exact execution evidence for applicable policy coverages."""

    errors: list[str] = []
    cache: dict[str, tuple[dict[str, Any], ...] | SmartCmpError] = {}
    for coverage in coverages:
        if coverage.get("applicable") is not True:
            continue
        execution_id = str(coverage.get("lastExecutionId") or "")
        if not execution_id:
            status = str(
                coverage.get("lastExecuteStatus") or ""
            ).upper()
            if status in {"ERROR", "FAILED", "FAILURE"}:
                coverage["resourceExecution"] = {
                    "status": status,
                    "extra": {},
                }
            continue
        if execution_id not in cache:
            try:
                result = await list_resource_executions(
                    client,
                    CostListQuery(
                        filters={"executionId": execution_id},
                        page=0,
                        size=100,
                        max_pages=100,
                    ),
                )
                cache[execution_id] = result.items
            except (
                SmartCmpAuthenticationError,
                SmartCmpPermissionError,
                SmartCmpRateLimitError,
            ):
                raise
            except SmartCmpError as exc:
                cache[execution_id] = exc
        cached = cache[execution_id]
        if isinstance(cached, SmartCmpError):
            message = (
                "Resource execution lookup failed for policy "
                f"'{coverage.get('policyName')}'."
            )
            errors.append(message)
            coverage["resourceExecution"] = {
                "status": "ERROR",
                "errMsg": message,
                "extra": {},
            }
            continue
        matching = next(
            (
                execution
                for execution in cached
                if str(
                    execution.get("executionId")
                    or execution.get("taskInstanceId")
                    or ""
                )
                == execution_id
                and str(execution.get("resourceId") or "")
                == resource_id
                and str(execution.get("policyId") or "")
                == str(coverage.get("policyId") or "")
            ),
            None,
        )
        if matching is not None:
            coverage["resourceExecution"] = {
                "executionId": str(
                    matching.get("executionId")
                    or matching.get("taskInstanceId")
                    or ""
                ),
                "policyId": str(matching.get("policyId") or ""),
                "status": str(matching.get("status") or ""),
                "startTime": matching.get("startTime"),
                "endTime": matching.get("endTime"),
                "policyViolationId": str(
                    matching.get("policyViolationId") or ""
                ),
                "errorReported": bool(
                    str(matching.get("errMsg") or "").strip()
                ),
                "extra": project_execution_extra(matching.get("extra")),
            }
    return errors
