"""Shared SmartCMP cost-remediation execution status aggregation."""

from __future__ import annotations

from typing import Any

from smartcmp_provider.domain.cost import normalize_timestamp
from smartcmp_provider.errors import (
    SmartCmpAuthenticationError,
    SmartCmpError,
    SmartCmpPermissionError,
    SmartCmpRateLimitError,
)
from smartcmp_provider.models.cost import (
    CostExecutionStatusQuery,
    CostExecutionStatusResult,
    CostListQuery,
    CostResourceExecutionCollection,
)
from smartcmp_provider.operations.cost import (
    list_resource_executions,
    list_violation_instances,
)
from smartcmp_provider.transport.client import SmartCmpClient

_STATUS_ALIASES = {
    "RUNNING": "EXECUTING",
    "PROCESSING": "EXECUTING",
    "IN_PROGRESS": "EXECUTING",
    "PENDING": "EXECUTING",
}


async def get_cost_execution_status(
    client: SmartCmpClient,
    query: CostExecutionStatusQuery,
) -> CostExecutionStatusResult:
    """Collect and aggregate violation-instance and resource execution facts."""

    violation_result = await list_violation_instances(
        client,
        CostListQuery(
            filters={
                "violationId": query.violation_id,
                "queryValue": query.violation_id,
            },
            page=0,
            size=100,
        ),
    )
    violations = [
        normalize_violation_instance(dict(item))
        for item in violation_result.items
    ]
    execution_ids = collect_execution_ids(violations)
    collection = await collect_resource_execution_records(
        client,
        execution_ids,
    )
    warnings = list(collection.warnings)
    if not execution_ids:
        warnings.append(
            "No execution IDs were returned from violation instances; "
            "resource executions were not queried."
        )
    return build_cost_execution_status(
        query.violation_id,
        violations,
        list(collection.items),
        resource_available=collection.available,
        warnings=warnings,
    )


async def collect_resource_execution_records(
    client: SmartCmpClient,
    execution_ids: list[str],
) -> CostResourceExecutionCollection:
    """Collect and de-duplicate resource execution rows for exact IDs."""

    resource_executions: list[dict[str, Any]] = []
    warnings: list[str] = []
    resource_available = True
    seen: set[tuple[str, ...]] = set()
    for execution_id in execution_ids:
        try:
            result = await list_resource_executions(
                client,
                CostListQuery(
                    filters={
                        "executionId": execution_id,
                        "queryValue": execution_id,
                    },
                    page=0,
                    size=100,
                ),
            )
        except (
            SmartCmpAuthenticationError,
            SmartCmpPermissionError,
            SmartCmpRateLimitError,
        ):
            raise
        except SmartCmpError:
            resource_available = False
            warnings.append(
                "Resource execution lookup failed for one tracked execution."
            )
            continue
        for item in result.items:
            normalized = normalize_resource_execution(dict(item))
            key = tuple(
                str(normalized.get(field) or "")
                for field in (
                    "source",
                    "recordId",
                    "executionId",
                    "status",
                    "message",
                )
            )
            if key in seen:
                continue
            seen.add(key)
            resource_executions.append(normalized)
    return CostResourceExecutionCollection(
        items=tuple(resource_executions),
        available=resource_available,
        warnings=tuple(warnings),
    )


def normalize_status(value: Any) -> str:
    """Normalize execution status values into stable uppercase labels."""

    if value in (None, "", "null"):
        return "UNKNOWN"
    status = str(value).strip().upper()
    return _STATUS_ALIASES.get(status, status) if status else "UNKNOWN"


def normalize_violation_instance(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize one violation-instance row into a stable execution record."""

    execution_id = (
        item.get("executionId")
        or item.get("taskInstanceId")
        or item.get("taskId")
        or item.get("id")
        or ""
    )
    return {
        "source": "violation-instance",
        "recordId": item.get("id", ""),
        "violationId": item.get("violationId", ""),
        "executionId": execution_id,
        "policyId": item.get("policyId", ""),
        "policyName": item.get("policyName", ""),
        "resourceId": item.get("resourceId", ""),
        "resourceName": item.get("resourceName", ""),
        "status": normalize_status(item.get("status")),
        "message": (
            item.get("violationMessage")
            or item.get("message")
            or ""
        ),
        "createdAt": normalize_timestamp(
            item.get("createdTime") or item.get("createTime")
        ),
        "updatedAt": normalize_timestamp(
            item.get("updatedTime") or item.get("modifyTime")
        ),
    }


def normalize_resource_execution(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize one resource-execution row into a stable execution record."""

    execution_id = (
        item.get("executionId")
        or item.get("taskInstanceId")
        or item.get("id")
        or ""
    )
    return {
        "source": "resource-execution",
        "recordId": item.get("id", ""),
        "violationId": (
            item.get("policyViolationId")
            or item.get("violationId")
            or ""
        ),
        "executionId": execution_id,
        "resourceName": item.get("resourceName", ""),
        "resourceId": item.get("resourceId", ""),
        "status": normalize_status(item.get("status")),
        "message": item.get("errMsg") or item.get("message") or "",
        "createdAt": normalize_timestamp(
            item.get("createTime") or item.get("createdTime")
        ),
        "updatedAt": normalize_timestamp(
            item.get("updateTime") or item.get("modifiedTime")
        ),
    }


def collect_execution_ids(records: list[dict[str, Any]]) -> list[str]:
    """Collect unique execution IDs in discovery order."""

    return [
        execution_id
        for execution_id in dict.fromkeys(
            str(
                item.get("executionId")
                or item.get("taskInstanceId")
                or item.get("taskId")
                or item.get("id")
                or ""
            ).strip()
            for item in records
        )
        if execution_id
    ]


def collapse_overall_status(records: list[dict[str, Any]]) -> str:
    """Collapse record states into one overall execution status."""

    statuses = {
        record.get("status", "UNKNOWN")
        for record in records
        if record.get("status")
    }
    statuses.discard("UNKNOWN")
    if not records:
        return "FAILED"
    if not statuses:
        return "PARTIAL"
    if statuses == {"SUCCESS"}:
        return "SUCCESS"
    if statuses == {"FAILED"}:
        return "FAILED"
    if statuses == {"EXECUTING"}:
        return "EXECUTING"
    return "PARTIAL"


def build_cost_execution_status(
    violation_id: str,
    violations: list[dict[str, Any]],
    resource_executions: list[dict[str, Any]],
    *,
    resource_available: bool,
    warnings: list[str],
) -> CostExecutionStatusResult:
    """Build one normalized cost execution status from collected records."""

    records = violations + resource_executions
    failure_messages: list[dict[str, Any]] = []
    seen_messages: set[tuple[str, str, str]] = set()
    for record in records:
        if record.get("status") != "FAILED":
            continue
        message = str(record.get("message") or "").strip()
        key = (
            str(record.get("source") or ""),
            str(record.get("executionId") or ""),
            message,
        )
        if not message or key in seen_messages:
            continue
        seen_messages.add(key)
        failure_messages.append(
            {
                "source": key[0],
                "executionId": key[1],
                "recordId": record.get("recordId", ""),
                "message": message,
            }
        )
    status_counts: dict[str, int] = {}
    for record in records:
        status = str(record.get("status") or "UNKNOWN")
        status_counts[status] = status_counts.get(status, 0) + 1
    return CostExecutionStatusResult(
        violationId=violation_id,
        overallStatus=collapse_overall_status(records),
        sourceAvailability={
            "violationInstances": True,
            "resourceExecutions": resource_available,
        },
        trackedExecutionIds=tuple(collect_execution_ids(violations)),
        recordCounts={
            "violationInstances": len(violations),
            "resourceExecutions": len(resource_executions),
            "total": len(records),
        },
        statusCounts=status_counts,
        violationInstances=tuple(violations),
        resourceExecutions=tuple(resource_executions),
        records=tuple(records),
        failureMessages=tuple(failure_messages),
        warnings=tuple(warnings),
    )
