"""Shared SmartCMP alert analysis orchestration."""

from __future__ import annotations

from typing import Any

from smartcmp_provider.analysis.alarms import (
    build_assessment,
    build_recommendations,
    normalize_alert_fact,
    suggest_status_operation,
)
from smartcmp_provider.domain.alarms import available_alert_operations
from smartcmp_provider.domain.resource_resolution import (
    collect_resource_ids_from_summaries,
)
from smartcmp_provider.domain.resource_normalization import (
    build_normalized_resource,
)
from smartcmp_provider.errors import (
    SmartCmpAuthenticationError,
    SmartCmpError,
    SmartCmpPermissionError,
    SmartCmpRateLimitError,
)
from smartcmp_provider.models.alarms import (
    AlarmAnalysisFactsQuery,
    AlarmAnalysisResult,
)
from smartcmp_provider.models.resources import (
    ResourceEvidenceQuery,
    ResourceSummarySearchQuery,
)
from smartcmp_provider.operations.alarms import get_alarm_analysis_facts
from smartcmp_provider.operations.resources import (
    load_resource_evidence,
    search_resource_summaries,
)
from smartcmp_provider.transport.client import SmartCmpClient


async def analyze_alarm(
    client: SmartCmpClient,
    query: AlarmAnalysisFactsQuery,
) -> AlarmAnalysisResult:
    """Load, enrich, normalize, and assess one SmartCMP alert."""

    facts = await get_alarm_analysis_facts(client, query)
    resource_records = await _load_alert_resource_records(
        client,
        facts.alert,
    )
    fact = normalize_alert_fact(
        facts.alert,
        facts.policy,
        detail=facts.detail,
        resource_records=resource_records,
    )
    assessment = build_assessment(fact)
    recommendations = build_recommendations(fact, assessment)
    return AlarmAnalysisResult(
        alert_ids=(query.alert_id,),
        facts=(fact,),
        assessment=assessment,
        recommendations=tuple(recommendations),
        suggested_status_operation=suggest_status_operation(
            fact,
            assessment,
        ),
        available_operations=available_alert_operations(facts.alert),
    )


async def _load_alert_resource_records(
    client: SmartCmpClient,
    alert: dict[str, Any],
) -> list[dict[str, Any]]:
    """Resolve bounded resource evidence without hiding auth failures."""

    candidate_ids = _candidate_resource_ids(alert)
    records = await _load_records(client, candidate_ids)
    if any(record.get("fetchStatus") == "ok" for record in records):
        return records

    lookup_ids: list[str] = []
    searches = (
        (
            {"nodeInstanceId": str(alert.get("nodeInstanceId") or "")},
            None,
            "",
        ),
        (
            {
                "externalIds": str(
                    alert.get("resourceExternalId") or ""
                )
            },
            None,
            "",
        ),
        (
            {},
            {
                "queryValue": str(
                    alert.get("resourceExternalName")
                    or alert.get("entityInstanceName")
                    or ""
                )
            },
            str(
                alert.get("resourceExternalName")
                or alert.get("entityInstanceName")
                or ""
            ),
        ),
    )
    for params, payload, expected_name in searches:
        if not any(params.values()) and not any((payload or {}).values()):
            continue
        try:
            result = await search_resource_summaries(
                client,
                ResourceSummarySearchQuery(
                    params=params,
                    payload=payload,
                ),
            )
            lookup_ids.extend(
                collect_resource_ids_from_summaries(
                    result.items,
                    expected_name=expected_name,
                    preferred_external_id=str(
                        alert.get("resourceExternalId") or ""
                    ),
                    preferred_node_instance_id=str(
                        alert.get("nodeInstanceId") or ""
                    ),
                )
            )
        except (
            SmartCmpAuthenticationError,
            SmartCmpPermissionError,
            SmartCmpRateLimitError,
        ):
            raise
        except SmartCmpError:
            continue
        if lookup_ids:
            break
    lookup_ids = [
        resource_id
        for resource_id in dict.fromkeys(lookup_ids)
        if resource_id not in candidate_ids
    ]
    return records + await _load_records(client, lookup_ids)


async def _load_records(
    client: SmartCmpClient,
    resource_ids: list[str],
) -> list[dict[str, Any]]:
    if not resource_ids:
        return []
    try:
        result = await load_resource_evidence(
            client,
            ResourceEvidenceQuery(resource_ids=tuple(resource_ids)),
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


def _candidate_resource_ids(alert: dict[str, Any]) -> list[str]:
    raw_ids = alert.get("entityInstanceId")
    values = list(raw_ids) if isinstance(raw_ids, list) else [raw_ids]
    values.extend(
        [
            alert.get("nodeInstanceId"),
            alert.get("resourceId"),
        ]
    )
    return [
        value
        for value in dict.fromkeys(
            str(item or "").strip() for item in values
        )
        if value
    ]
