# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Pure helpers for component-model-driven resource health evidence."""

from __future__ import annotations

import json
import math
import re
import statistics
from collections.abc import Mapping, Sequence
from typing import Any


MAX_SERIES_PER_METRIC = 8
MAX_CURRENT_POINTS = 60

_SENSITIVE_KEY_PARTS = {
    "accesskey",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "password",
    "passwd",
    "privatekey",
    "secret",
    "token",
}
_STRONG_RESOURCE_LABELS = {
    "external_id",
    "externalid",
    "instance",
    "instance_id",
    "instanceid",
    "node_id",
    "nodeid",
    "node_instance_id",
    "nodeinstanceid",
    "resource_id",
    "resourceid",
    "target",
    "target_name",
    "targetname",
}
_PROMQL_METRIC_NAME = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]*$")
_PROMQL_SELECTOR = re.compile(r"([a-zA-Z_:][a-zA-Z0-9_:]*)\{([^{}]*)\}")
_PROMQL_IDENTIFIER = re.compile(
    r"(?<![a-zA-Z0-9_:])([a-zA-Z_:][a-zA-Z0-9_:]*)(?![a-zA-Z0-9_:])"
)
_PROMQL_NON_METRIC_WORDS = {
    "and",
    "bool",
    "by",
    "group_left",
    "group_right",
    "ignoring",
    "inf",
    "nan",
    "offset",
    "on",
    "or",
    "unless",
    "without",
}
_PROMQL_UNSCOPED_VECTOR_FUNCTIONS = {"vector"}
_PROMQL_DEFAULT_VECTOR_FUNCTIONS = {
    "day_of_month",
    "day_of_week",
    "day_of_year",
    "days_in_month",
    "hour",
    "minute",
    "month",
    "year",
}
_OPERATIONAL_PROPERTY_KEYS = {
    "architecture",
    "availabilityzone",
    "cores",
    "cpu",
    "cpucorecount",
    "cpucount",
    "createdat",
    "disk",
    "disks",
    "disksize",
    "engine",
    "engineversion",
    "flavor",
    "hostname",
    "instancetype",
    "memory",
    "memorybytes",
    "memorysize",
    "monitorenabled",
    "operatingsystem",
    "osname",
    "ostype",
    "osversion",
    "platform",
    "powerstate",
    "region",
    "runtime",
    "runtimestate",
    "state",
    "status",
    "storage",
    "storagesize",
    "updatedat",
    "version",
    "virtualizationtype",
    "zone",
}
_NESTED_OPERATIONAL_SCHEMAS = {
    "cpu": {
        "count",
        "cores",
        "limit",
        "model",
        "request",
        "sockets",
        "unit",
        "usage",
        "utilization",
    },
    "disk": {"available", "capacity", "free", "name", "size", "total", "unit", "used"},
    "disks": {"available", "capacity", "free", "name", "size", "total", "unit", "used"},
    "engine": {"name", "type", "version"},
    "memory": {"available", "capacity", "free", "limit", "size", "total", "unit", "used"},
    "operatingsystem": {"architecture", "name", "type", "version"},
    "runtime": {
        "lastseenat",
        "phase",
        "startedat",
        "state",
        "status",
        "uptime",
        "version",
    },
    "storage": {"available", "capacity", "free", "name", "size", "total", "unit", "used"},
}
MAX_OPERATIONAL_PROPERTIES = 32
MAX_PROPERTY_STRING_LENGTH = 256
MAX_PROPERTY_COLLECTION_ITEMS = 16
MAX_PROPERTY_DEPTH = 3
MAX_PROPERTY_KEY_LENGTH = 64
_CANONICAL_PROPERTY_NAMES = {
    "availabilityzone": "availabilityZone",
    "cpucorecount": "cpuCoreCount",
    "cpucount": "cpuCount",
    "createdat": "createdAt",
    "disksize": "diskSize",
    "engineversion": "engineVersion",
    "instancetype": "instanceType",
    "lastseenat": "lastSeenAt",
    "memorybytes": "memoryBytes",
    "memorysize": "memorySize",
    "monitorenabled": "monitorEnabled",
    "operatingsystem": "operatingSystem",
    "osname": "osName",
    "ostype": "osType",
    "osversion": "osVersion",
    "powerstate": "powerState",
    "runtimestate": "runtimeState",
    "startedat": "startedAt",
    "storagesize": "storageSize",
    "updatedat": "updatedAt",
    "virtualizationtype": "virtualizationType",
}
_SENSITIVE_ASSIGNMENT = re.compile(
    r'''(?i)(["']?)(password|passwd|access[_-]?token|refresh[_-]?token|token|'''
    r'''client[_-]?secret|secret|cookie|credential|authorization|api[_-]?key|'''
    r'''access[_-]?key|private[_-]?key)\1\s*[:=]\s*'''
    r'''(Bearer\s+(?:\[REDACTED\]|[A-Za-z0-9._~+/=-]+)|'''
    r'''"(?:\\.|[^"])*"|'(?:\\.|[^'])*'|[^\s,;}\]]+)'''
)


def redact_sensitive(value: Any) -> Any:
    """Return a copy with credential-like fields and inline secrets removed.

    Args:
        value: Arbitrary resource, monitoring-model, or error value.

    Returns:
        A recursively redacted JSON-compatible value.
    """
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            rendered_key = str(key)
            if _is_sensitive_key(rendered_key):
                redacted[rendered_key] = "[REDACTED]"
            else:
                redacted[rendered_key] = redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, str):
        return sanitize_error_text(value)
    return value


def sanitize_error_text(value: Any) -> str:
    """Remove common secret assignments and authorization values from text."""
    text = str(value or "")
    text = re.sub(
        r"(?i)([a-z][a-z0-9+.-]*://)[^/@\s]+@",
        r"\1[REDACTED]@",
        text,
    )
    text = re.sub(
        r"(?is)-----BEGIN [^-\r\n]*PRIVATE KEY-----.*?"
        r"-----END [^-\r\n]*PRIVATE KEY-----",
        "[REDACTED PRIVATE KEY]",
        text,
    )
    text = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    return _SENSITIVE_ASSIGNMENT.sub(
        lambda match: f'{match.group(1)}{match.group(2)}{match.group(1)}=[REDACTED]',
        text,
    )


def project_operational_properties(properties: Mapping[str, Any]) -> dict[str, Any]:
    """Project bounded runtime properties suitable for LLM health evidence.

    Args:
        properties: Normalized resource properties from the datasource skill.

    Returns:
        An allowlisted, size-bounded, recursively redacted property mapping.
    """
    projected: dict[str, Any] = {}
    for key, value in properties.items():
        rendered_key = str(key)
        if not _is_safe_property_key(rendered_key):
            continue
        normalized_key = _normalized_key(rendered_key)
        if normalized_key not in _OPERATIONAL_PROPERTY_KEYS:
            continue
        output_key = _canonical_property_name(normalized_key)
        projected[output_key] = _bounded_redacted_value(
            value,
            depth=0,
            allowed_mapping_keys=_NESTED_OPERATIONAL_SCHEMAS.get(
                normalized_key
            ),
        )
        if len(projected) >= MAX_OPERATIONAL_PROPERTIES:
            break
    return projected


def build_effective_monitoring_model(component_type: str, payload: Any) -> dict[str, Any]:
    """Normalize and merge the metric groups returned for one component type.

    SmartCMP returns the effective component monitoring model as ordered metric
    groups. Later definitions override earlier inherited definitions by
    ``primaryKey`` and then by metric name.

    Args:
        component_type: SmartCMP component type used to resolve the model.
        payload: Raw metric-group response from SmartCMP.

    Returns:
        Normalized model with de-duplicated enabled metric definitions.
    """
    raw_groups = _extract_list(payload)
    ordered_groups = sorted(
        (group for group in raw_groups if isinstance(group, Mapping)),
        key=lambda group: _coerce_int(group.get("index"), default=0),
    )
    metric_order: list[str] = []
    metrics_by_key: dict[str, dict[str, Any]] = {}
    group_records: list[dict[str, Any]] = []

    for group_index, group in enumerate(ordered_groups):
        group_key = str(group.get("configName") or group.get("name") or group_index)
        group_record = {
            "key": group_key,
            "name": str(group.get("name") or ""),
            "alias": str(group.get("alias") or ""),
            "aliasZh": str(group.get("aliasZh") or ""),
            "index": _coerce_int(group.get("index"), default=group_index),
            "buildIn": bool(group.get("buildIn")),
            "metricKeys": [],
        }
        for raw_metric in group.get("metrics") or []:
            if not isinstance(raw_metric, Mapping):
                continue
            metric_key = str(raw_metric.get("primaryKey") or raw_metric.get("name") or "").strip()
            if not metric_key:
                continue
            if raw_metric.get("enabled") is False or raw_metric.get("disabled") is True:
                # A child component can explicitly remove an inherited metric.
                # Keep its original order slot so a later descendant may re-enable it.
                metrics_by_key.pop(metric_key, None)
                continue
            metric = _normalize_metric(raw_metric, metric_key=metric_key, group_key=group_key)
            if metric_key not in metric_order:
                metric_order.append(metric_key)
            metrics_by_key[metric_key] = metric
            group_record["metricKeys"].append(metric_key)
        group_records.append(group_record)

    metrics = [metrics_by_key[key] for key in metric_order if key in metrics_by_key]
    effective_group_by_key = {
        metric["key"]: metric["groupKey"]
        for metric in metrics
    }
    for group in group_records:
        group["metricKeys"] = [
            key
            for key in group["metricKeys"]
            if effective_group_by_key.get(key) == group["key"]
        ]

    return {
        "componentType": component_type,
        "source": "component-monitoring-model",
        "metricCount": len(metrics),
        "groups": group_records,
        "metrics": metrics,
    }


def build_resource_identity(
    resource_id: str,
    resource_record: Mapping[str, Any],
    monitor_payload: Any,
) -> dict[str, str]:
    """Build canonical resource bindings used to scope monitoring queries.

    Args:
        resource_id: Internal SmartCMP resource identifier.
        resource_record: Normalized datasource resource record.
        monitor_payload: Resource exporter payload from ``/nodes/{id}/monitor``.

    Returns:
        Canonical label-value bindings without credentials.
    """
    resource = _mapping(resource_record.get("data") or resource_record.get("resource"))
    properties = _mapping((_mapping(resource_record.get("normalized"))).get("properties"))
    monitor = _unwrap_mapping(monitor_payload)
    identity = {
        "resource_id": resource_id,
        "node_id": _first_value(resource.get("nodeId"), properties.get("nodeId"), resource_id),
        "node_instance_id": _first_value(
            monitor.get("nodeInstanceId"), resource.get("nodeInstanceId"), properties.get("nodeInstanceId")
        ),
        "external_id": _first_value(
            monitor.get("externalId"),
            resource.get("externalId"),
            properties.get("externalId"),
        ),
        "deployment_id": _first_value(
            monitor.get("deploymentId"), resource.get("deploymentId"), properties.get("deploymentId")
        ),
        "cloud_entry_id": _first_value(
            monitor.get("cloudEntryId"), resource.get("cloudEntryId"), properties.get("cloudEntryId")
        ),
        "tenant_id": _first_value(resource.get("tenantId"), properties.get("tenantId")),
        "business_group_id": _first_value(
            resource.get("businessGroupId"), properties.get("businessGroupId")
        ),
        "target_name": _first_value(
            monitor.get("targetName"),
            monitor.get("nodeInstanceName"),
            resource.get("name"),
            properties.get("name"),
        ),
    }
    return {key: value for key, value in identity.items() if value}


def build_scoped_metric_query(
    metric: Mapping[str, Any],
    identity: Mapping[str, str],
) -> tuple[str, dict[str, str], str]:
    """Render a component-model query with resource-scoped label matchers.

    Args:
        metric: Normalized component monitoring metric.
        identity: Canonical resource label values.

    Returns:
        Tuple of PromQL query, applied labels, and an error message. An empty
        query means the model definition cannot be scoped safely.
    """
    definition = str(metric.get("definition") or "").strip()
    if not definition:
        return "", {}, "Metric definition is empty."

    model_labels = metric.get("metricLabels") or {}
    if not isinstance(model_labels, Mapping):
        model_labels = {}
    applied_labels: dict[str, str] = {}
    for label in model_labels:
        canonical = _canonical_label(str(label))
        value = identity.get(canonical, "")
        if value:
            applied_labels[str(label)] = value

    rendered = definition
    substituted_labels: set[str] = set()
    for label, value in applied_labels.items():
        quoted_value = _promql_string(value)
        replacements = (f"{{{{{label}}}}}", f"${{{label}}}")
        for placeholder in replacements:
            quoted_placeholder = f'"{placeholder}"'
            if quoted_placeholder in rendered:
                rendered = rendered.replace(quoted_placeholder, quoted_value)
                substituted_labels.add(label)
            if placeholder in rendered:
                rendered = rendered.replace(placeholder, quoted_value)
                substituted_labels.add(label)

    rendered = _strip_promql_comments(rendered).strip()

    remaining_labels = {
        label: value for label, value in applied_labels.items() if label not in substituted_labels
    }
    if _PROMQL_METRIC_NAME.fullmatch(rendered):
        rendered = _append_selector(rendered, remaining_labels)
    elif remaining_labels and _PROMQL_SELECTOR.search(rendered):
        rendered = _PROMQL_SELECTOR.sub(
            lambda match: _merge_selector(match.group(1), match.group(2), remaining_labels),
            rendered,
        )

    selectors = list(_PROMQL_SELECTOR.finditer(rendered))
    if (
        not selectors
        or _contains_unscoped_vector_constructor(rendered)
        or _contains_bare_metric_reference(rendered)
        or not all(
            _selector_has_exact_resource_matcher(match.group(2), applied_labels)
            for match in selectors
        )
    ):
        return "", applied_labels, "Metric definition has no resource-specific label binding."
    return rendered, applied_labels, ""


def summarize_prometheus_payload(
    payload: Any,
    *,
    include_points: bool,
    expected_samples: int | None = None,
    identity_values: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Normalize a Prometheus response into compact per-metric evidence.

    Args:
        payload: Prometheus HTTP API response.
        include_points: Whether downsampled points should be retained.
        expected_samples: Expected samples in the requested range for each
            series. When provided, coverage includes leading and trailing gaps.
        identity_values: Resource-bound values that must not enter LLM-visible
            series labels.

    Returns:
        Aggregate and per-series statistical evidence. Health interpretation is
        intentionally excluded.
    """
    series = sorted(
        _parse_prometheus_series(payload),
        key=lambda item: json.dumps(item["labels"], ensure_ascii=True, sort_keys=True),
    )
    limited_series = series[:MAX_SERIES_PER_METRIC]
    all_points = [point for item in limited_series for point in item["points"]]
    aggregate_summary = summarize_points(all_points)
    if len(limited_series) > 1:
        # There is no generally valid reducer for latest value or trend across
        # independently labelled series. Preserve distribution facts here and
        # make the deterministic per-series summaries authoritative.
        for key in ("latest", "latestAt", "trend", "flatline"):
            aggregate_summary.pop(key, None)
        aggregate_summary["aggregation"] = "all_series_distribution"
        aggregate_summary["seriesSummaryAuthoritative"] = True
    result = {
        "seriesCount": len(series),
        "seriesTruncated": len(series) > MAX_SERIES_PER_METRIC,
        "summary": aggregate_summary,
        "series": [],
    }
    point_limits = _allocate_point_limits(limited_series, MAX_CURRENT_POINTS)
    for index, item in enumerate(limited_series):
        series_summary = summarize_points(item["points"])
        _apply_expected_coverage(series_summary, expected_samples)
        record = {
            "labels": _project_series_labels(item["labels"], identity_values or []),
            "summary": series_summary,
        }
        if include_points:
            record["points"] = downsample_points(item["points"], point_limits[index])
        result["series"].append(record)
    if expected_samples is not None:
        series_coverages = [
            float(item["summary"].get("coverage") or 0.0)
            for item in result["series"]
        ]
        aggregate_summary["expectedSamplesPerSeries"] = expected_samples
        aggregate_summary["coverage"] = round(
            statistics.fmean(series_coverages) if series_coverages else 0.0,
            4,
        )
        aggregate_summary["missingRate"] = round(1.0 - aggregate_summary["coverage"], 4)
    return result


def summarize_points(points: Sequence[Sequence[float]]) -> dict[str, Any]:
    """Calculate descriptive time-series facts without a health threshold."""
    normalized = sorted(
        ([float(point[0]), float(point[1])] for point in points if len(point) >= 2),
        key=lambda point: point[0],
    )
    if not normalized:
        return {
            "sampleCount": 0,
            "coverage": 0.0,
            "missingRate": 1.0,
            "trend": "insufficient",
            "insufficientStatistics": [
                "latest",
                "distribution",
                "volatility",
                "flatline",
                "trend",
            ],
        }

    values = [point[1] for point in normalized]
    average = statistics.fmean(values)
    interval = _median_interval(normalized)
    expected_count = len(normalized)
    if interval > 0 and len(normalized) > 1:
        sampled_span = normalized[-1][0] - normalized[0][0]
        expected_count = max(int(round(sampled_span / interval)) + 1, len(normalized))
    coverage = min(len(normalized) / expected_count, 1.0) if expected_count else 0.0
    tolerance = max(abs(average) * 1e-9, 1e-12)
    summary = {
        "sampleCount": len(normalized),
        "latest": _round_number(values[-1]),
        "latestAt": _round_number(normalized[-1][0]),
        "min": _round_number(min(values)),
        "max": _round_number(max(values)),
        "average": _round_number(average),
        "p50": _round_number(_percentile(values, 0.50)),
        "p95": _round_number(_percentile(values, 0.95)),
        "coverage": round(coverage, 4),
        "missingRate": round(1.0 - coverage, 4),
        "trend": _classify_trend(values),
    }
    if len(values) > 1:
        summary["volatility"] = _round_number(statistics.pstdev(values))
        summary["flatline"] = max(values) - min(values) <= tolerance
    else:
        summary["insufficientStatistics"] = ["volatility", "flatline", "trend"]
    return summary


def downsample_points(points: Sequence[Sequence[float]], limit: int) -> list[list[float]]:
    """Return evenly distributed points while preserving the first and last samples."""
    normalized = [[_round_number(float(point[0])), _round_number(float(point[1]))] for point in points]
    if limit <= 0 or len(normalized) <= limit:
        return normalized
    indexes = sorted({round(index * (len(normalized) - 1) / (limit - 1)) for index in range(limit)})
    return [normalized[index] for index in indexes]


def _allocate_point_limits(series: Sequence[Mapping[str, Any]], total_limit: int) -> list[int]:
    """Distribute one metric's point budget across its retained series."""
    capacities = [len(item.get("points") or []) for item in series]
    limits = [0] * len(capacities)
    remaining = max(total_limit, 0)
    while remaining and any(limits[index] < capacity for index, capacity in enumerate(capacities)):
        for index, capacity in enumerate(capacities):
            if remaining <= 0:
                break
            if limits[index] < capacity:
                limits[index] += 1
                remaining -= 1
    return limits


def _normalize_metric(metric: Mapping[str, Any], *, metric_key: str, group_key: str) -> dict[str, Any]:
    labels = metric.get("metricLabels") if isinstance(metric.get("metricLabels"), Mapping) else {}
    return {
        "key": metric_key,
        "groupKey": group_key,
        "name": str(metric.get("name") or metric_key),
        "displayName": str(metric.get("displayName") or ""),
        "displayEnName": str(metric.get("displayEnName") or ""),
        "description": str(metric.get("description") or ""),
        "unit": str(metric.get("unit") or ""),
        "definition": str(metric.get("definition") or ""),
        "expressionType": str(metric.get("expressionType") or ""),
        "metricLabels": redact_sensitive(dict(labels)),
    }


def _extract_list(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, Mapping):
        return []
    for key in ("content", "items", "result", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, Mapping):
            nested = _extract_list(value)
            if nested:
                return nested
    return []


def _unwrap_mapping(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    for key in ("data", "result", "content", "item"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return dict(payload)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _coerce_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _first_value(*values: Any) -> str:
    for value in values:
        if value not in (None, "", [], {}):
            return str(value)
    return ""


def _normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _is_sensitive_key(key: str) -> bool:
    normalized = _normalized_key(key)
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _canonical_label(label: str) -> str:
    normalized = _normalized_key(label)
    aliases = {
        "resourceid": "resource_id",
        "nodeid": "node_id",
        "nodeinstanceid": "node_instance_id",
        "externalid": "external_id",
        "deploymentid": "deployment_id",
        "cloudentryid": "cloud_entry_id",
        "tenantid": "tenant_id",
        "businessgroupid": "business_group_id",
        "targetname": "target_name",
        "target": "target_name",
        "instance": "node_instance_id",
        "instanceid": "node_instance_id",
    }
    return aliases.get(normalized, label)


def _promql_string(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _append_selector(metric_name: str, labels: Mapping[str, str]) -> str:
    if not labels:
        return metric_name
    matchers = ",".join(f"{label}={_promql_string(value)}" for label, value in sorted(labels.items()))
    return f"{metric_name}{{{matchers}}}"


def _merge_selector(metric_name: str, existing: str, labels: Mapping[str, str]) -> str:
    additions = [
        f"{label}={_promql_string(value)}"
        for label, value in sorted(labels.items())
    ]
    selector_parts = [part for part in (existing.strip(), ",".join(additions)) if part]
    return f"{metric_name}{{{','.join(selector_parts)}}}"


def _selector_has_exact_resource_matcher(
    selector: str,
    applied_labels: Mapping[str, str],
) -> bool:
    strong_labels = {_normalized_key(item) for item in _STRONG_RESOURCE_LABELS}
    for label, value in applied_labels.items():
        if _normalized_key(label) not in strong_labels:
            continue
        exact_matcher = re.compile(
            rf"(?<![!~])\b{re.escape(label)}\s*=\s*{re.escape(_promql_string(value))}"
            rf"(?=\s*(?:,|$))"
        )
        if exact_matcher.search(selector):
            return True
    return False


def _contains_bare_metric_reference(expression: str) -> bool:
    """Detect vector sources that are not explicit, scoped selectors."""
    scrubbed = re.sub(r'"(?:\\.|[^"])*"', '""', expression)
    scrubbed = _PROMQL_SELECTOR.sub(" ", scrubbed)
    scrubbed = re.sub(
        r"\b(?:by|without|on|ignoring|group_left|group_right)\s*\([^)]*\)",
        " ",
        scrubbed,
        flags=re.IGNORECASE,
    )
    for match in _PROMQL_IDENTIFIER.finditer(scrubbed):
        identifier = match.group(1)
        remainder = scrubbed[match.end() :].lstrip()
        if remainder.startswith("(") or identifier.lower() in _PROMQL_NON_METRIC_WORDS:
            continue
        return True
    return False


def _contains_unscoped_vector_constructor(expression: str) -> bool:
    """Reject synthetic vector sources that have no resource label scope."""
    function_pattern = "|".join(
        re.escape(name) for name in sorted(_PROMQL_UNSCOPED_VECTOR_FUNCTIONS)
    )
    if re.search(rf"\b(?:{function_pattern})\s*\(", expression, flags=re.IGNORECASE):
        return True
    default_vector_pattern = "|".join(
        re.escape(name) for name in sorted(_PROMQL_DEFAULT_VECTOR_FUNCTIONS)
    )
    return bool(
        re.search(
            rf"\b(?:{default_vector_pattern})\s*\(\s*\)",
            expression,
            flags=re.IGNORECASE,
        )
    )


def _strip_promql_comments(expression: str) -> str:
    """Remove line comments while preserving hash characters inside strings."""
    output: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(expression):
        character = expression[index]
        if in_string:
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
            output.append(character)
            index += 1
            continue
        if character == "#":
            while index < len(expression) and expression[index] not in "\r\n":
                index += 1
            continue
        output.append(character)
        index += 1
    return "".join(output)


def _bounded_redacted_value(
    value: Any,
    *,
    depth: int,
    allowed_mapping_keys: set[str] | None = None,
) -> Any:
    if depth >= MAX_PROPERTY_DEPTH:
        return "[TRUNCATED]"
    if isinstance(value, Mapping):
        bounded: dict[str, Any] = {}
        for key, item in list(value.items())[:MAX_PROPERTY_COLLECTION_ITEMS]:
            rendered_key = str(key)
            if not _is_safe_property_key(rendered_key):
                continue
            normalized_key = _normalized_key(rendered_key)
            if allowed_mapping_keys is None or normalized_key not in allowed_mapping_keys:
                continue
            output_key = _canonical_property_name(normalized_key)
            if _is_sensitive_key(output_key):
                bounded[output_key] = "[REDACTED]"
            else:
                bounded[output_key] = _bounded_redacted_value(
                    item,
                    depth=depth + 1,
                )
        return bounded
    if isinstance(value, (list, tuple)):
        return [
            _bounded_redacted_value(
                item,
                depth=depth + 1,
                allowed_mapping_keys=allowed_mapping_keys,
            )
            for item in list(value)[:MAX_PROPERTY_COLLECTION_ITEMS]
        ]
    if isinstance(value, str):
        sanitized = sanitize_error_text(value)
        if len(sanitized) > MAX_PROPERTY_STRING_LENGTH:
            return f"{sanitized[:MAX_PROPERTY_STRING_LENGTH]}...[TRUNCATED]"
        return sanitized
    return value


def _project_series_labels(
    labels: Mapping[str, Any],
    identity_values: Sequence[str],
) -> dict[str, Any]:
    """Retain useful dimensions without exposing resource identity values."""
    strong_labels = {_normalized_key(item) for item in _STRONG_RESOURCE_LABELS}
    projected: dict[str, Any] = {}
    for key, value in list(labels.items())[:MAX_PROPERTY_COLLECTION_ITEMS]:
        rendered_key = str(key)
        if _normalized_key(rendered_key) in strong_labels or _looks_like_id_label(rendered_key):
            projected[rendered_key] = "[RESOURCE]"
        else:
            bounded_value = _bounded_redacted_value(value, depth=0)
            if isinstance(bounded_value, str):
                bounded_value = _redact_identity_text(bounded_value, identity_values)
            projected[rendered_key[:MAX_PROPERTY_KEY_LENGTH]] = bounded_value
    return projected


def _looks_like_id_label(label: str) -> bool:
    return bool(
        re.search(
            r"(?:^(?:id|uid|uuid|guid)$|[_-](?:id|uid|uuid|guid)$|"
            r"(?:Id|ID|Uid|UID|Uuid|UUID|Guid|GUID)$)",
            label,
        )
    )


def _is_safe_property_key(key: str) -> bool:
    return len(key) <= MAX_PROPERTY_KEY_LENGTH and bool(
        re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", key)
    )


def _canonical_property_name(normalized_key: str) -> str:
    return _CANONICAL_PROPERTY_NAMES.get(normalized_key, normalized_key)


def _redact_identity_text(value: str, identity_values: Sequence[str]) -> str:
    redacted = value
    for identity_value in sorted(
        {str(item) for item in identity_values if item},
        key=len,
        reverse=True,
    ):
        redacted = redacted.replace(identity_value, "[RESOURCE]")
    return redacted


def _parse_prometheus_series(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return []
    result = data.get("result")
    if not isinstance(result, list):
        return []

    series: list[dict[str, Any]] = []
    for item in result:
        if not isinstance(item, Mapping):
            continue
        raw_values = item.get("values")
        if not isinstance(raw_values, list):
            single_value = item.get("value")
            raw_values = [single_value] if isinstance(single_value, list) else []
        points: list[list[float]] = []
        for point in raw_values:
            if not isinstance(point, Sequence) or isinstance(point, (str, bytes)) or len(point) < 2:
                continue
            try:
                timestamp = float(point[0])
                value = float(point[1])
            except (TypeError, ValueError):
                continue
            if math.isfinite(timestamp) and math.isfinite(value):
                points.append([timestamp, value])
        if points:
            raw_labels = item.get("metric")
            labels = dict(raw_labels) if isinstance(raw_labels, Mapping) else {}
            series.append({"labels": labels, "points": points})
    return series


def _apply_expected_coverage(summary: dict[str, Any], expected_samples: int | None) -> None:
    if expected_samples is None:
        return
    sample_count = int(summary.get("sampleCount") or 0)
    coverage = min(sample_count / expected_samples, 1.0) if expected_samples > 0 else 0.0
    summary["expectedSamples"] = expected_samples
    summary["coverage"] = round(coverage, 4)
    summary["missingRate"] = round(1.0 - coverage, 4)


def _median_interval(points: Sequence[Sequence[float]]) -> float:
    intervals = [points[index][0] - points[index - 1][0] for index in range(1, len(points))]
    positive = [interval for interval in intervals if interval > 0]
    return statistics.median(positive) if positive else 0.0


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _classify_trend(values: Sequence[float]) -> str:
    if len(values) < 3:
        return "insufficient"
    segment_size = max(len(values) // 3, 1)
    first = statistics.fmean(values[:segment_size])
    last = statistics.fmean(values[-segment_size:])
    scale = max(abs(first), abs(statistics.fmean(values)), 1e-9)
    change = (last - first) / scale
    if change > 0.05:
        return "rising"
    if change < -0.05:
        return "falling"
    return "stable"


def _round_number(value: float) -> float:
    return round(float(value), 6)
