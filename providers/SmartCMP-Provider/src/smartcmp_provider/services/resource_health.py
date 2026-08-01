#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Collect component-model-driven SmartCMP resource health evidence."""

from __future__ import annotations

import asyncio
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable
from urllib.parse import quote, quote_plus, urlsplit, urlunsplit

import httpx

from smartcmp_provider.analysis.resource_health import (
    build_effective_monitoring_model,
    build_resource_identity,
    build_scoped_metric_query,
    project_operational_properties,
    redact_sensitive,
    sanitize_error_text,
    summarize_prometheus_payload,
)
from smartcmp_provider.auth.models import ResolvedSmartCmpRequest
from smartcmp_provider.domain.resource_resolution import (
    resolve_single_resource,
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
    AlarmMetricGroupsQuery,
    AlarmResourceMonitorQuery,
)
from smartcmp_provider.models.resources import (
    ResourceEvidenceQuery,
    ResourceSummarySearchQuery,
)
from smartcmp_provider.operations.alarms import (
    get_alarm_metric_groups,
    get_monitor_api_url,
    get_resource_monitor_binding,
)
from smartcmp_provider.operations.resources import (
    load_resource_evidence,
    search_resource_summaries,
)
from smartcmp_provider.transport.client import SmartCmpClient
from smartcmp_provider.transport.settings import DEFAULT_TIMEOUT_SECONDS


BASELINE_DAYS = 7
MAX_QUERY_WORKERS = 4


def _run_provider_operation(
    request: ResolvedSmartCmpRequest,
    operation: Callable[[SmartCmpClient], Any],
) -> Any:
    """Execute one asynchronous Provider operation from a synchronous service."""

    async def invoke() -> Any:
        """Own and close the request-scoped client used by this bridge."""

        async with SmartCmpClient(request) as client:
            return await operation(client)

    return asyncio.run(invoke())


def resolve_resource_id(
    *,
    resource_id: str,
    resource_name: str,
    resource_index: int | None,
    directory_items: list[dict[str, Any]],
    provider_request: ResolvedSmartCmpRequest,
) -> tuple[str, str]:
    """Resolve a name or visible index through SmartCMP Provider resource search."""

    return resolve_single_resource(
        resource_id_value=resource_id,
        resource_name=str(resource_name or "").strip(),
        resource_index=resource_index,
        directory_items=directory_items,
        search_page=lambda page, size, name: tuple(
            _run_provider_operation(
                provider_request,
                lambda client: search_resource_summaries(
                    client,
                    ResourceSummarySearchQuery(
                        params={"page": page, "size": size, "queryValue": name},
                        payload={"queryValue": name},
                    ),
                ),
            ).items
        ),
    )


def collect_resource_health_context(
    *,
    resource_id: str,
    resource_name: str,
    window_hours: int,
    provider_request: ResolvedSmartCmpRequest,
) -> dict[str, Any]:
    """Collect resource, monitoring-model, and time-series evidence.

    Args:
        resource_id: Resolved internal SmartCMP resource identifier.
        resource_name: Resolved visible resource name, when known.
        window_hours: Current time-series analysis window.
        provider_request: Shared Authentication and Execution Context.

    Returns:
        Evidence payload for the AtlasClaw LLM. The payload never contains a
        deterministic healthy/abnormal assessment.
    """
    timeout = int(
        provider_request.context.instance.timeout_seconds
        or DEFAULT_TIMEOUT_SECONDS
    )
    base_url = provider_request.context.instance.base_url
    headers = provider_request.credential.headers()
    resource_result = _run_provider_operation(
        provider_request,
        lambda client: load_resource_evidence(
            client,
            ResourceEvidenceQuery(resource_ids=(resource_id,)),
        ),
    )
    records = [dict(record) for record in resource_result.records]
    for candidate in records:
        if candidate.get("fetchStatus") == "ok":
            candidate["normalized"] = build_normalized_resource(candidate)
    if not records or records[0].get("fetchStatus") != "ok":
        raise RuntimeError("The selected SmartCMP resource could not be loaded.")

    record = records[0]
    normalized = record.get("normalized") if isinstance(record.get("normalized"), dict) else {}
    properties = normalized.get("properties") if isinstance(normalized.get("properties"), dict) else {}
    resource = record.get("data") if isinstance(record.get("data"), dict) else record.get("resource") or {}
    component_type = str(normalized.get("type") or "").strip()
    visible_name = sanitize_error_text(
        resource.get("name") or properties.get("name") or resource_name or "resource"
    )[:256]
    resource_facts = {
        "name": visible_name,
        "status": str(resource.get("status") or properties.get("status") or ""),
        "componentType": component_type,
        "resourceType": str(resource.get("resourceType") or properties.get("resourceType") or ""),
        "monitorEnabled": _optional_bool(resource.get("monitorEnabled", properties.get("monitorEnabled"))),
        "properties": project_operational_properties(properties),
    }
    payload: dict[str, Any] = {
        "object_type": "resource_health_context",
        "object_name": visible_name,
        "analysis_mode": "llm_resource_health",
        "analysis_contract": {
            "allowedStatuses": ["healthy", "abnormal", "indeterminate"],
            "usesAlarmRules": False,
            "healthAssessmentProvidedByTool": False,
            "requiredLLMOutput": [
                "status",
                "confidence",
                "findings",
                "metricEvidence",
                "missingEvidence",
                "recommendedActions",
            ],
        },
        "resource": resource_facts,
        "window": {"currentHours": window_hours, "baselineDays": BASELINE_DAYS},
        "monitoringModel": {
            "componentType": component_type,
            "source": "component-monitoring-model",
            "metricCount": 0,
            "groups": [],
            "metrics": [],
        },
        "monitoring_state": "unsupported",
        "observations": [],
        "missingEvidence": [],
        "errors": [],
    }
    if not component_type:
        payload["missingEvidence"].append("resource.componentType")
        return payload

    try:
        metric_groups = _run_provider_operation(
            provider_request,
            lambda client: get_alarm_metric_groups(
                client,
                AlarmMetricGroupsQuery(component_type=component_type),
            ),
        ).payload
    except (
        SmartCmpAuthenticationError,
        SmartCmpPermissionError,
        SmartCmpRateLimitError,
    ):
        raise
    except (SmartCmpError, RuntimeError) as exc:
        payload["monitoring_state"] = "unavailable"
        payload["missingEvidence"].append("component.monitoringModel")
        payload["errors"].append(sanitize_error_text(exc))
        return payload

    monitoring_model = build_effective_monitoring_model(component_type, metric_groups)
    payload["monitoringModel"] = monitoring_model
    if not monitoring_model["metrics"]:
        payload["missingEvidence"].append("component.monitoringModel.metrics")
        return payload
    if resource_facts["monitorEnabled"] is False:
        payload["monitoring_state"] = "disabled"
        payload["missingEvidence"].append("resource.monitorBinding")
        return payload

    monitor_payload: Any = {}
    try:
        monitor_payload = _run_provider_operation(
            provider_request,
            lambda client: get_resource_monitor_binding(
                client,
                AlarmResourceMonitorQuery(resource_id=resource_id),
            ),
        ).payload
    except (
        SmartCmpAuthenticationError,
        SmartCmpPermissionError,
        SmartCmpRateLimitError,
    ):
        raise
    except (SmartCmpError, RuntimeError) as exc:
        payload["monitoring_state"] = "unavailable"
        payload["missingEvidence"].append("resource.monitorBinding")
        payload["errors"].append(sanitize_error_text(exc))
        return payload

    if not _payload_has_monitor_binding(monitor_payload):
        payload["monitoring_state"] = "unavailable"
        payload["missingEvidence"].append("resource.monitorBinding")
        if resource_facts["monitorEnabled"] is True:
            payload["errors"].append(
                "Monitoring is enabled but the resource monitor binding is unavailable."
            )
        return payload

    identity = build_resource_identity(resource_id, record, monitor_payload)
    try:
        monitor_url_payload = _run_provider_operation(
            provider_request,
            get_monitor_api_url,
        ).payload
        monitor_url = extract_monitor_api_url(monitor_url_payload)
        query_url = build_query_range_url(monitor_url)
    except (
        SmartCmpAuthenticationError,
        SmartCmpPermissionError,
        SmartCmpRateLimitError,
    ):
        raise
    except (
        SmartCmpError,
        RuntimeError,
        ValueError,
        httpx.HTTPError,
    ) as exc:
        payload["monitoring_state"] = "unavailable"
        payload["missingEvidence"].append("monitoring.queryEndpoint")
        payload["errors"].append(sanitize_error_text(exc))
        return payload

    query_headers = safe_prometheus_headers(base_url, monitor_url, headers)
    observations = query_monitoring_model(
        monitoring_model["metrics"],
        identity=identity,
        query_url=query_url,
        query_headers=query_headers,
        window_hours=window_hours,
        timeout=timeout,
    )
    payload["observations"] = observations
    payload["monitoring_state"] = classify_monitoring_state(observations)
    payload["errors"] = list(
        dict.fromkeys(
            error
            for observation in observations
            for error in observation.get("errors", [])
            if error
        )
    )
    if payload["monitoring_state"] != "available":
        payload["missingEvidence"].append("monitoring.completeMetricCoverage")
    return redact_sensitive(payload)


def query_monitoring_model(
    metrics: list[dict[str, Any]],
    *,
    identity: dict[str, str],
    query_url: str,
    query_headers: dict[str, str],
    window_hours: int,
    timeout: int,
) -> list[dict[str, Any]]:
    """Query every enabled model metric with bounded concurrency.

    Args:
        metrics: Effective component metric definitions.
        identity: Resource values available for model-label binding.
        query_url: CMP-managed Prometheus ``query_range`` endpoint.
        query_headers: Headers safe to send to the monitoring endpoint.
        window_hours: Size of the current observation window.
        timeout: Per-query timeout in seconds.

    Returns:
        Observations in the same order as the effective metric model.
    """
    now = time.time()
    current_start = now - window_hours * 3600
    baseline_end = current_start
    baseline_start = baseline_end - BASELINE_DAYS * 86400
    current_step = max(int(math.ceil((now - current_start) / 59)), 60)
    baseline_step = max(int(math.ceil((baseline_end - baseline_start) / 119)), 300)

    observations: list[dict[str, Any] | None] = [None] * len(metrics)
    with ThreadPoolExecutor(max_workers=MAX_QUERY_WORKERS) as executor:
        futures = {
            executor.submit(
                _query_one_metric,
                metric,
                identity=identity,
                query_url=query_url,
                query_headers=query_headers,
                current_range=(current_start, now, current_step),
                baseline_range=(baseline_start, baseline_end, baseline_step),
                timeout=timeout,
            ): index
            for index, metric in enumerate(metrics)
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                observations[index] = future.result()
            except (RuntimeError, TypeError, ValueError, httpx.HTTPError) as exc:
                metric = metrics[index]
                observations[index] = _metric_error_observation(metric, sanitize_error_text(exc))
    return [observation for observation in observations if observation is not None]


def extract_monitor_api_url(payload: Any) -> str:
    """Extract and validate the CMP-managed HTTP(S) monitoring endpoint."""
    value = payload
    if isinstance(payload, dict):
        for key in ("url", "apiUrl", "api_url", "value", "data", "result"):
            candidate = payload.get(key)
            if isinstance(candidate, str) and candidate.strip():
                value = candidate
                break
            if isinstance(candidate, dict):
                try:
                    return extract_monitor_api_url(candidate)
                except ValueError:
                    continue
    url = str(value or "").strip()
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("CMP monitoring API URL is missing or is not HTTP(S).")
    return url


def build_query_range_url(monitor_url: str) -> str:
    """Build a Prometheus ``query_range`` endpoint from the CMP monitor URL."""
    parsed = urlsplit(monitor_url)
    path = parsed.path.rstrip("/")
    if path.endswith("/api/v1/query_range"):
        query_path = path
    elif path.endswith("/api/v1/query"):
        query_path = f"{path[:-len('/query')]}/query_range"
    elif path.endswith("/api/v1"):
        query_path = f"{path}/query_range"
    else:
        query_path = f"{path}/api/v1/query_range"
    return urlunsplit((parsed.scheme, parsed.netloc, query_path, "", ""))


def safe_prometheus_headers(
    cmp_base_url: str,
    monitor_url: str,
    cmp_headers: dict[str, str],
) -> dict[str, str]:
    """Forward CMP authentication only when the monitoring endpoint is same-origin."""
    headers = {"Accept": "application/json"}
    if _origin(cmp_base_url) == _origin(monitor_url):
        for key in ("Authorization", "CloudChef-Authenticate"):
            if cmp_headers.get(key):
                headers[key] = cmp_headers[key]
    return headers


def classify_monitoring_state(observations: list[dict[str, Any]]) -> str:
    """Classify metric evidence availability without interpreting resource health."""
    if not observations:
        return "no_data"
    ok_count = sum(1 for observation in observations if observation.get("status") == "ok")
    no_data_count = sum(1 for observation in observations if observation.get("status") == "no_data")
    if ok_count == len(observations) and all(not observation.get("errors") for observation in observations):
        return "available"
    if ok_count:
        return "partial"
    if no_data_count == len(observations) and all(
        not observation.get("errors") for observation in observations
    ):
        return "no_data"
    return "unavailable"


def _query_one_metric(
    metric: dict[str, Any],
    *,
    identity: dict[str, str],
    query_url: str,
    query_headers: dict[str, str],
    current_range: tuple[float, float, int],
    baseline_range: tuple[float, float, int],
    timeout: int,
) -> dict[str, Any]:
    query, _applied_labels, error = build_scoped_metric_query(metric, identity)
    observation = {
        "metricKey": metric.get("key", ""),
        "name": metric.get("name", ""),
        "displayName": metric.get("displayName", ""),
        "displayEnName": metric.get("displayEnName", ""),
        "description": metric.get("description", ""),
        "unit": metric.get("unit", ""),
        "expressionType": metric.get("expressionType", ""),
        "status": "unavailable",
        "current": {},
        "baseline": {},
        "errors": [],
    }
    if error:
        observation["errors"].append(error)
        return observation

    try:
        current_payload = _prometheus_query_range(
            query_url,
            query=query,
            start=current_range[0],
            end=current_range[1],
            step=current_range[2],
            headers=query_headers,
            timeout=timeout,
        )
        observation["current"] = summarize_prometheus_payload(
            current_payload,
            include_points=True,
            expected_samples=_expected_samples(current_range),
            identity_values=list(identity.values()),
        )
    except (RuntimeError, httpx.HTTPError) as exc:
        observation["errors"].append(_sanitize_metric_error(exc, identity))
        return observation

    current_count = int((observation["current"].get("summary") or {}).get("sampleCount") or 0)
    observation["status"] = "ok" if current_count else "no_data"
    try:
        baseline_payload = _prometheus_query_range(
            query_url,
            query=query,
            start=baseline_range[0],
            end=baseline_range[1],
            step=baseline_range[2],
            headers=query_headers,
            timeout=timeout,
        )
        observation["baseline"] = summarize_prometheus_payload(
            baseline_payload,
            include_points=False,
            expected_samples=_expected_samples(baseline_range),
            identity_values=list(identity.values()),
        )
    except (RuntimeError, httpx.HTTPError) as exc:
        observation["errors"].append(
            f"Baseline query failed: {_sanitize_metric_error(exc, identity)}"
        )
    return observation


def _prometheus_query_range(
    url: str,
    *,
    query: str,
    start: float,
    end: float,
    step: int,
    headers: dict[str, str],
    timeout: int,
) -> dict[str, Any]:
    with httpx.Client(
        verify=False,
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        response = client.get(
            url,
            params={
                "query": query,
                "start": start,
                "end": end,
                "step": step,
            },
            headers=headers,
        )
    _reject_redirect(response, "Prometheus query")
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("Prometheus returned invalid JSON.") from exc
    if not isinstance(payload, dict) or payload.get("status") != "success":
        message = payload.get("error") if isinstance(payload, dict) else "invalid response"
        raise RuntimeError(f"Prometheus query failed: {sanitize_error_text(message)}")
    return payload


def _metric_error_observation(metric: dict[str, Any], error: str) -> dict[str, Any]:
    return {
        "metricKey": metric.get("key", ""),
        "name": metric.get("name", ""),
        "displayName": metric.get("displayName", ""),
        "displayEnName": metric.get("displayEnName", ""),
        "description": metric.get("description", ""),
        "unit": metric.get("unit", ""),
        "expressionType": metric.get("expressionType", ""),
        "status": "unavailable",
        "current": {},
        "baseline": {},
        "errors": [error],
    }


def _sanitize_metric_error(error: Any, applied_labels: dict[str, str]) -> str:
    """Remove resource-bound values from Prometheus error text and URLs."""
    sanitized = sanitize_error_text(error)
    values = sorted({str(value) for value in applied_labels.values() if value}, key=len, reverse=True)
    for value in values:
        for rendered in (value, quote(value, safe=""), quote_plus(value)):
            sanitized = sanitized.replace(rendered, "[RESOURCE]")
    return sanitized


def _payload_has_monitor_binding(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return bool(payload)
    for key in ("data", "result", "content", "item"):
        if key in payload:
            value = payload[key]
            return isinstance(value, dict) and bool(value)
    return bool(payload)


def _reject_redirect(response: Any, endpoint_name: str) -> None:
    """Reject redirects so custom CMP authentication cannot cross origins."""
    status_code = int(getattr(response, "status_code", 200) or 200)
    if 300 <= status_code < 400:
        raise RuntimeError(f"{endpoint_name} redirected; redirected authenticated requests are not allowed.")


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return None


def _expected_samples(query_range: tuple[float, float, int]) -> int:
    start, end, step = query_range
    if step <= 0 or end < start:
        return 0
    return int(math.floor((end - start) / step)) + 1


def _origin(url: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(url)
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80 if parsed.scheme == "http" else None
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), port
