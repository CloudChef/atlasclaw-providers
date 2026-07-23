# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""List SmartCMP alarm alerts with human and machine-readable output."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
DATASOURCE_SCRIPT_DIR = SCRIPT_DIR.parent.parent / "datasource" / "scripts"
SHARED_SCRIPT_DIR = SCRIPT_DIR.parent.parent / "shared" / "scripts"
for import_root in (SCRIPT_DIR, SHARED_SCRIPT_DIR):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from _alarm_common import (
    DEFAULT_PAGE,
    DEFAULT_SIZE,
    build_list_params,
    extract_items,
    get_connection,
    get_json,
    normalize_timestamp,
)
from _alarm_object_actions import build_alert_object_actions as build_domain_alert_actions
from _resource_target import (  # noqa: E402
    ResourceResolutionError,
    parse_resource_directory,
    resolve_single_resource,
)


CURRENT_RESOURCE_ALERT_STATUSES = ("ALERT_FIRING", "ALERT_MUTED")
RECENT_RESOURCE_ALERT_STATUSES = ("ALERT_RESOLVED",)
RESOURCE_ALERT_QUERY_SIZE = 100
ALARM_ALERT_QUERY_PATH = "/alarm-alert?query"


def _load_datasource_resource_module():
    """Load shared datasource resource helpers without changing package layout."""
    module_path = DATASOURCE_SCRIPT_DIR / "list_resource.py"
    spec = importlib.util.spec_from_file_location("_smartcmp_alert_list_resource", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load datasource helpers from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_resource_module = _load_datasource_resource_module()
resource_request_json = _resource_module.request_json
search_resource_summaries = _resource_module.search_resource_summaries


def positive_int(value: str) -> int:
    """Parse a strictly positive integer argument."""
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse general or exact-resource alert-listing arguments."""
    parser = argparse.ArgumentParser(description="List SmartCMP alarm alerts.")
    parser.add_argument("--status", dest="statuses", action="append", help="Alert status filter.")
    parser.add_argument("--days", type=positive_int, default=7, help="Look back window in days.")
    parser.add_argument("--level", type=int, help="Alert level filter.")
    parser.add_argument("--deployment-id", help="Deployment identifier filter.")
    parser.add_argument("--entity-instance-id", help="Entity instance identifier filter.")
    parser.add_argument("--node-instance-id", help="Node instance identifier filter.")
    parser.add_argument(
        "--target-entity-id",
        help="Exact SmartCMP alert target identifier filter.",
    )
    parser.add_argument("--alarm-type", help="Alarm type filter.")
    parser.add_argument(
        "--alarm-category",
        dest="alarm_categories",
        action="append",
        help="Alarm category filter.",
    )
    parser.add_argument("--query", help="Optional keyword filter.")
    parser.add_argument("--page", type=positive_int, default=DEFAULT_PAGE, help="Result page number.")
    parser.add_argument("--size", type=positive_int, default=DEFAULT_SIZE, help="Page size.")
    parser.add_argument("--resource-name", default="", help="Exact visible SmartCMP resource name.")
    parser.add_argument(
        "--resource-index",
        type=positive_int,
        help="Visible index from the latest resource list.",
    )
    parser.add_argument(
        "--resource-directory-json",
        default="",
        help="Hidden latest resource-list metadata.",
    )
    parser.add_argument(
        "--resource-id",
        default="",
        help="Internal compatibility-only SmartCMP resource ID.",
    )
    parser.add_argument(
        "--resource-alert-scope",
        choices=("current", "current_and_recent"),
        default="current_and_recent",
        help=(
            "For exact-resource mode, include only current alerts or current alerts plus "
            "currently resolved alerts whose triggerAt is within the lookback."
        ),
    )
    return parser.parse_args(argv)


def normalize_entity_ids(value: Any) -> list[str]:
    """Normalize entity identifiers to a stable string list."""
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def _alert_object_name(alert: Mapping[str, Any]) -> str:
    """Pick a stable, human-visible alert object label."""
    for key in ("alarmPolicyName", "alarmActivityName", "resourceExternalName", "entityInstanceName", "id"):
        value = alert.get(key)
        if value:
            return str(value)
    return "unknown-alert"


def build_alert_object_actions(alert_id: str) -> list[dict[str, object]]:
    """Build explicit UI actions for one SmartCMP alert row."""
    return build_domain_alert_actions(
        {"id": alert_id},
        operations=(),
        analyze_action_id="view_detail",
    )


def build_alert_meta(alert: Mapping[str, Any], index: int) -> dict[str, Any]:
    """Project SmartCMP alert data into stable English metadata keys."""
    alert_id = str(alert.get("id", "") or "")
    object_name = _alert_object_name(alert)
    meta = {
        "index": index,
        "object_type": "alarm_alert",
        "object_id": alert_id,
        "object_name": object_name,
        "object_actions": build_alert_object_actions(alert_id),
        "alertId": alert_id,
        "alarmActivityId": alert.get("alarmActivityId", ""),
        "alarmActivityName": alert.get("alarmActivityName", ""),
        "alarmPolicyId": alert.get("alarmPolicyId", ""),
        "alarmPolicyName": alert.get("alarmPolicyName", ""),
        "status": alert.get("status", ""),
        "level": alert.get("level"),
        "triggerAt": normalize_timestamp(alert.get("triggerAt")),
        "lastTriggerAt": normalize_timestamp(alert.get("lastTriggerAt")),
        "triggerCount": alert.get("triggerCount", 0),
        "deploymentId": alert.get("deploymentId", ""),
        "deploymentName": alert.get("deploymentName", ""),
        "entityInstanceId": normalize_entity_ids(alert.get("entityInstanceId")),
        "entityInstanceName": alert.get("entityInstanceName", ""),
        "nodeInstanceId": alert.get("nodeInstanceId", ""),
        "targetEntityId": alert.get("targetEntityId", ""),
        "resourceExternalId": alert.get("resourceExternalId", ""),
        "resourceExternalName": alert.get("resourceExternalName", ""),
        "metricName": alert.get("metricName", ""),
        "subject": alert.get("subject", ""),
        "operationNum": alert.get("operationNum", 0),
        "notificationNum": alert.get("notificationNum", 0),
    }
    match_basis = str(alert.get("_resourceMatchBasis") or "").strip()
    lifecycle = str(alert.get("_alertLifecycle") or "").strip()
    if match_basis:
        meta["resourceMatchBasis"] = match_basis
    if lifecycle:
        meta["alertLifecycle"] = lifecycle
    return meta


def build_query_params(args: argparse.Namespace) -> dict[str, Any]:
    """Translate parsed arguments into SmartCMP query parameters."""
    return build_list_params(
        page=args.page,
        size=args.size,
        statuses=args.statuses,
        days=args.days,
        level=args.level,
        deployment_id=args.deployment_id or "",
        entity_instance_id=args.entity_instance_id or "",
        node_instance_id=args.node_instance_id or "",
        target_entity_id=args.target_entity_id or "",
        alarm_type=args.alarm_type or "",
        alarm_categories=args.alarm_categories,
        queryValue=args.query or "",
    )


def resource_alert_mode_requested(args: argparse.Namespace) -> bool:
    """Return whether this invocation targets one exact SmartCMP resource."""
    return bool(
        str(args.resource_name or "").strip()
        or str(args.resource_id or "").strip()
        or args.resource_index is not None
    )


def resolve_alert_resource_target(args: argparse.Namespace) -> tuple[str, str]:
    """Resolve the exact resource used to filter current and recent alerts.

    Args:
        args: Parsed resource selector arguments.

    Returns:
        Internal SmartCMP resource ID and exact visible name.

    Raises:
        ResourceResolutionError: If the target is missing, ambiguous, or inconsistent.
    """
    base_url, headers, _instance = get_connection()
    directory = parse_resource_directory(args.resource_directory_json)
    return resolve_single_resource(
        resource_id_value=str(args.resource_id or "").strip(),
        resource_name=str(args.resource_name or "").strip(),
        resource_index=args.resource_index,
        directory_items=directory,
        search_page=lambda page, size, name: search_resource_summaries(
            base_url=base_url,
            headers=headers,
            request_fn=resource_request_json,
            params={"page": page, "size": size, "queryValue": name},
            payload={"queryValue": name},
        ),
    )


def resource_match_basis(
    alert: Mapping[str, Any],
    *,
    resource_id: str,
) -> str:
    """Return the exact Resource ID match used by resource analysis."""
    normalized_id = str(resource_id or "").strip()
    target_entity_id = str(alert.get("targetEntityId") or "").strip()
    if normalized_id and target_entity_id == normalized_id:
        return "resource_id"
    return ""


def extract_resource_query_items(payload: Any) -> list[Any] | None:
    """Return a recognized resource-alert result list or ``None`` if malformed."""
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, Mapping):
        return None
    for key in ("content", "data", "items", "result"):
        if key not in payload:
            continue
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, Mapping):
            nested = extract_resource_query_items(value)
            if nested is not None:
                return nested
    return None


def collect_resource_alerts(
    args: argparse.Namespace,
    *,
    resource_id: str,
    resource_name: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Collect Resource ID-matched current and optional resolved alerts.

    SmartCMP applies ``targetEntityId`` as an exact public-query filter. The
    returned field is verified client-side so a deployment that ignores the
    filter cannot turn unrelated alerts into resource evidence.
    """
    lifecycle_queries: list[tuple[str, tuple[str, ...], int | None]] = [
        ("current", CURRENT_RESOURCE_ALERT_STATUSES, None),
    ]
    if args.resource_alert_scope == "current_and_recent":
        lifecycle_queries.append(
            ("resolved_trigger_lookback", RECENT_RESOURCE_ALERT_STATUSES, args.days)
        )

    matched_by_observation: dict[tuple[str, str], dict[str, Any]] = {}
    lifecycles_by_alert_id: dict[str, set[str]] = {}
    anonymous_matches: list[dict[str, Any]] = []
    query_count = 0
    successful_queries = 0
    candidate_count = 0
    unverified_candidate_count = 0
    errors: list[str] = []

    for lifecycle, statuses, days in lifecycle_queries:
        query_count += 1
        params = build_list_params(
            page=1,
            size=max(int(args.size), RESOURCE_ALERT_QUERY_SIZE),
            statuses=statuses,
            days=days,
            level=args.level,
            target_entity_id=resource_id,
            alarm_type=args.alarm_type or "",
            alarm_categories=args.alarm_categories,
        )
        try:
            payload = get_json(ALARM_ALERT_QUERY_PATH, params=params)
        except RuntimeError:
            errors.append(f"{lifecycle}.targetEntityId:query_failed")
            continue
        raw_candidates = extract_resource_query_items(payload)
        if raw_candidates is None:
            errors.append(f"{lifecycle}.targetEntityId:invalid_response")
            continue
        successful_queries += 1
        candidate_count += len(raw_candidates)
        for candidate in raw_candidates:
            if not isinstance(candidate, Mapping):
                unverified_candidate_count += 1
                continue
            # Verify both lifecycle and Resource ID even though the CMP query
            # is exact, because external deployments remain a trust boundary.
            if str(candidate.get("status") or "").strip() not in statuses:
                unverified_candidate_count += 1
                continue
            basis = resource_match_basis(candidate, resource_id=resource_id)
            if not basis:
                unverified_candidate_count += 1
                continue
            matched = dict(candidate)
            matched["_resourceMatchBasis"] = basis
            matched["_alertLifecycle"] = lifecycle
            alert_id = str(candidate.get("id") or "").strip()
            if alert_id:
                # Deduplicate retries within one lifecycle, but preserve both
                # observations if the alert changes lifecycle between the two
                # requests. Silently preferring either response would hide a
                # race and could present stale alert state as complete evidence.
                matched_by_observation[(alert_id, lifecycle)] = matched
                lifecycles_by_alert_id.setdefault(alert_id, set()).add(lifecycle)
            else:
                anonymous_matches.append(matched)

    lifecycle_conflict_count = sum(
        1 for lifecycles in lifecycles_by_alert_id.values() if len(lifecycles) > 1
    )
    if lifecycle_conflict_count:
        errors.append("cross_lifecycle.alertId:conflicting_observations")
    association_status = "complete"
    if successful_queries == 0:
        association_status = "indeterminate"
    elif (
        successful_queries < query_count
        or unverified_candidate_count
        or lifecycle_conflict_count
    ):
        association_status = "partial"
    matched_alerts = list(matched_by_observation.values()) + anonymous_matches
    coverage = {
        "resourceName": resource_name,
        "scope": args.resource_alert_scope,
        "currentStatuses": list(CURRENT_RESOURCE_ALERT_STATUSES),
        "resolvedTriggerLookbackDays": (
            args.days if args.resource_alert_scope == "current_and_recent" else None
        ),
        "associationStatus": association_status,
        "queriesAttempted": query_count,
        "queriesSucceeded": successful_queries,
        "candidateCount": candidate_count,
        "matchedCount": len(matched_alerts),
        "unverifiedCandidateCount": unverified_candidate_count,
        "lifecycleConflictCount": lifecycle_conflict_count,
        "errors": errors,
    }
    return matched_alerts, coverage


def select_resource_name(meta: Mapping[str, Any]) -> str:
    """Pick the best available resource label for human output."""
    for key in ("resourceExternalName", "entityInstanceName", "deploymentName", "nodeInstanceId", "alertId"):
        value = meta.get(key)
        if value:
            return str(value)
    return "unknown"


def format_alert_line(meta: Mapping[str, Any]) -> str:
    """Render one concise alert summary line."""
    policy_name = (
        meta.get("alarmPolicyName")
        or meta.get("alarmActivityName")
        or meta.get("alertId")
        or "unknown"
    )
    return (
        f"[{meta['index']}] {policy_name} | "
        f"status={meta.get('status', '')} | "
        f"level={meta.get('level', '')} | "
        f"resource={select_resource_name(meta)}"
    )


def escape_markdown_cell(value: object) -> str:
    """Render one value safely inside a Markdown table cell."""
    rendered = str(value or "").replace("\n", " ").replace("\r", " ").strip()
    rendered = " ".join(rendered.split())
    return rendered.replace("|", "\\|")


def render_alert_table(items: list[Mapping[str, Any]], total: int) -> str:
    """Render SmartCMP alert list output as a standard Markdown table."""
    headers = ["#", "Policy", "Status", "Level", "Resource"]
    lines = [
        f"Found {total} alert(s):",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for item in items:
        row = [
            item.get("index", ""),
            item.get("alarmPolicyName") or item.get("alarmActivityName") or item.get("alertId") or "unknown",
            item.get("status", ""),
            item.get("level", ""),
            select_resource_name(item),
        ]
        lines.append("| " + " | ".join(escape_markdown_cell(value) for value in row) + " |")
    return "\n".join(lines)


def extract_total(payload: Any, items: Iterable[Any]) -> int:
    """Extract the total count when available, otherwise fall back to item count."""
    if isinstance(payload, Mapping):
        total = payload.get("totalElements")
        if isinstance(total, int):
            return total
    return len(list(items))


def main(argv: list[str] | None = None) -> int:
    """List general alerts or exact-resource current and recent alert evidence."""
    args = parse_args(argv)
    resource_coverage: dict[str, Any] | None = None
    if resource_alert_mode_requested(args):
        try:
            resource_id, resource_name = resolve_alert_resource_target(args)
            items, resource_coverage = collect_resource_alerts(
                args,
                resource_id=resource_id,
                resource_name=resource_name,
            )
        except (ResourceResolutionError, RuntimeError, ImportError, ValueError) as exc:
            print(f"[ERROR] {exc}")
            return 1
        meta = [build_alert_meta(item, index) for index, item in enumerate(items, start=1)]
        total = len(meta)
    else:
        params = build_query_params(args)
        try:
            payload = get_json(ALARM_ALERT_QUERY_PATH, params=params)
        except RuntimeError as exc:
            print(f"[ERROR] {exc}")
            return 1
        items = extract_items(payload)
        meta = [build_alert_meta(item, index) for index, item in enumerate(items, start=1)]
        total = extract_total(payload, meta)

    if meta:
        print(render_alert_table(meta, total))
    elif resource_coverage is not None:
        resource_label = escape_markdown_cell(resource_coverage.get("resourceName") or "resource")
        if resource_coverage.get("associationStatus") == "complete":
            if resource_coverage.get("scope") == "current":
                print(
                    "No exactly matched current firing or muted alerts were returned for "
                    f"resource {resource_label}."
                )
            else:
                print(
                    "No exactly matched current alerts or resolved alerts triggered within "
                    "the lookback were returned for "
                    f"resource {resource_label}."
                )
        else:
            print(
                "Resource alert association is incomplete for "
                f"{resource_label}; the absence of matched alerts is not proof that no alert exists."
            )
    else:
        print("No alerts found.")

    print()
    print("##ALARM_META_START##")
    print(json.dumps(meta, ensure_ascii=False))
    print("##ALARM_META_END##")
    if resource_coverage is not None:
        print("##RESOURCE_ALERT_COVERAGE_START##")
        print(json.dumps(resource_coverage, ensure_ascii=False))
        print("##RESOURCE_ALERT_COVERAGE_END##")
    return 0


if __name__ == "__main__":
    sys.exit(main())
