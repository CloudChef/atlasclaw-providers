"""Shared exact-resource SmartCMP alert listing orchestration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from smartcmp_provider.domain.alarms import build_list_params
from smartcmp_provider.errors import (
    SmartCmpAuthenticationError,
    SmartCmpError,
    SmartCmpPermissionError,
    SmartCmpRateLimitError,
    SmartCmpUpstreamError,
)
from smartcmp_provider.models.alarms import (
    AlarmListQuery,
    ResourceAlertCoverage,
    ResourceAlertListQuery,
    ResourceAlertListResult,
)
from smartcmp_provider.operations.alarms import list_alarms
from smartcmp_provider.transport.client import SmartCmpClient


CURRENT_RESOURCE_ALERT_STATUSES = ("ALERT_FIRING", "ALERT_MUTED")
RECENT_RESOURCE_ALERT_STATUSES = ("ALERT_RESOLVED",)
RESOURCE_ALERT_QUERY_SIZE = 100
UNKNOWN_TOTAL_MAX_PAGES = 100


def resource_match_basis(
    alert: Mapping[str, Any],
    *,
    resource_id: str,
) -> str:
    """Return the exact resource identifier match established for an alert."""

    normalized_id = str(resource_id or "").strip()
    target_entity_id = str(alert.get("targetEntityId") or "").strip()
    if normalized_id and target_entity_id == normalized_id:
        return "resource_id"
    return ""


async def collect_resource_alerts(
    client: SmartCmpClient,
    query: ResourceAlertListQuery,
) -> ResourceAlertListResult:
    """Collect and verify current and optional recent alerts for one resource.

    SmartCMP receives an exact ``targetEntityId`` filter. SmartCMP Provider still
    validates every returned alert's lifecycle and target identifier because
    upstream filtering is an external trust boundary. Authentication,
    permission, and rate-limit errors are propagated; other per-lifecycle read
    failures are represented in coverage so a successful query can still
    provide bounded evidence.

    Args:
        client: Request-scoped SmartCMP client.
        query: Resolved resource identity and requested alert scope.

    Returns:
        Verified alert observations and explicit association coverage.

    Raises:
        SmartCmpAuthenticationError: If SmartCMP rejects the credential.
        SmartCmpPermissionError: If the principal cannot list alerts.
        SmartCmpRateLimitError: If SmartCMP throttles the request.
    """

    lifecycle_queries: list[tuple[str, tuple[str, ...], int | None]] = [
        ("current", CURRENT_RESOURCE_ALERT_STATUSES, None),
    ]
    if query.scope == "current_and_recent":
        lifecycle_queries.append(
            (
                "resolved_trigger_lookback",
                RECENT_RESOURCE_ALERT_STATUSES,
                query.days,
            )
        )

    matched_by_observation: dict[tuple[str, str], dict[str, Any]] = {}
    lifecycles_by_alert_id: dict[str, set[str]] = {}
    anonymous_matches: list[dict[str, Any]] = []
    successful_queries = 0
    candidate_count = 0
    unverified_candidate_count = 0
    errors: list[str] = []

    for lifecycle, statuses, days in lifecycle_queries:
        filters = build_list_params(
            page=1,
            size=max(query.size, RESOURCE_ALERT_QUERY_SIZE),
            statuses=statuses,
            days=days,
            level=query.level,
            target_entity_id=query.resource_id,
            alarm_type=query.alarm_type,
            alarm_categories=query.alarm_categories,
        )
        (
            lifecycle_candidates,
            lifecycle_started,
            pagination_error,
        ) = await _read_lifecycle_pages(
            client,
            filters=filters,
        )
        if lifecycle_started:
            successful_queries += 1
        if pagination_error:
            errors.append(
                f"{lifecycle}.targetEntityId:{pagination_error}"
            )
        if not lifecycle_started:
            continue

        candidate_count += len(lifecycle_candidates)
        for candidate in lifecycle_candidates:
            if str(candidate.get("status") or "").strip() not in statuses:
                unverified_candidate_count += 1
                continue
            basis = resource_match_basis(
                candidate,
                resource_id=query.resource_id,
            )
            if not basis:
                unverified_candidate_count += 1
                continue

            matched = dict(candidate)
            matched["_resourceMatchBasis"] = basis
            matched["_alertLifecycle"] = lifecycle
            alert_id = str(candidate.get("id") or "").strip()
            if alert_id:
                matched_by_observation[(alert_id, lifecycle)] = matched
                lifecycles_by_alert_id.setdefault(alert_id, set()).add(
                    lifecycle
                )
            else:
                anonymous_matches.append(matched)

    lifecycle_conflict_count = sum(
        1
        for lifecycles in lifecycles_by_alert_id.values()
        if len(lifecycles) > 1
    )
    if lifecycle_conflict_count:
        errors.append("cross_lifecycle.alertId:conflicting_observations")

    query_count = len(lifecycle_queries)
    association_status = "complete"
    if successful_queries == 0:
        association_status = "indeterminate"
    elif (
        successful_queries < query_count
        or unverified_candidate_count
        or lifecycle_conflict_count
        or errors
    ):
        association_status = "partial"

    matched_alerts = (
        list(matched_by_observation.values()) + anonymous_matches
    )
    return ResourceAlertListResult(
        items=tuple(matched_alerts),
        coverage=ResourceAlertCoverage(
            resource_name=query.resource_name,
            scope=query.scope,
            current_statuses=CURRENT_RESOURCE_ALERT_STATUSES,
            resolved_trigger_lookback_days=(
                query.days if query.scope == "current_and_recent" else None
            ),
            association_status=association_status,
            queries_attempted=query_count,
            queries_succeeded=successful_queries,
            candidate_count=candidate_count,
            matched_count=len(matched_alerts),
            unverified_candidate_count=unverified_candidate_count,
            lifecycle_conflict_count=lifecycle_conflict_count,
            errors=tuple(errors),
        ),
    )


async def _read_lifecycle_pages(
    client: SmartCmpClient,
    *,
    filters: dict[str, Any],
) -> tuple[list[dict[str, Any]], bool, str]:
    """Read every available page for one lifecycle query.

    Returns:
        Collected candidates, whether at least one page succeeded, and an
        optional coverage error. A bounded guard is used only when SmartCMP
        omits its total and continues returning full pages.
    """

    page_size = int(filters["size"])
    page = 1
    candidates: list[dict[str, Any]] = []
    known_total: int | None = None
    previous_page: tuple[dict[str, Any], ...] | None = None

    while True:
        page_filters = dict(filters)
        page_filters["page"] = page
        try:
            result = await list_alarms(
                client,
                AlarmListQuery(filters=page_filters),
            )
        except (
            SmartCmpAuthenticationError,
            SmartCmpPermissionError,
            SmartCmpRateLimitError,
        ):
            raise
        except SmartCmpUpstreamError:
            return candidates, bool(page > 1), "invalid_response"
        except SmartCmpError:
            return candidates, bool(page > 1), "query_failed"

        page_items = result.items
        if previous_page is not None and page_items and page_items == previous_page:
            return candidates, True, "pagination_repeated_page"
        previous_page = page_items
        candidates.extend(page_items)

        if result.total is not None:
            known_total = max(known_total or 0, result.total)
            if len(candidates) >= known_total:
                return candidates, True, ""

        if not page_items:
            if known_total is not None and len(candidates) < known_total:
                return candidates, True, "pagination_incomplete"
            return candidates, True, ""

        if len(page_items) < page_size:
            if known_total is not None and len(candidates) < known_total:
                return candidates, True, "pagination_incomplete"
            return candidates, True, ""

        if known_total is None and page >= UNKNOWN_TOTAL_MAX_PAGES:
            return candidates, True, "pagination_limit_reached"
        page += 1
