#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Collect component-model-driven resource health evidence for LLM analysis."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, quote_plus, urlsplit, urlunsplit

import requests


SCRIPT_DIR = Path(__file__).resolve().parent
DATASOURCE_SCRIPT_DIR = SCRIPT_DIR.parent.parent / "datasource" / "scripts"
SHARED_SCRIPT_DIR = SCRIPT_DIR.parent.parent / "shared" / "scripts"
for import_root in (SCRIPT_DIR, SHARED_SCRIPT_DIR):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from _alarm_common import default_timeout, get_connection  # noqa: E402
from _resource_target import (  # noqa: E402
    ResourceResolutionError,
    parse_resource_directory as shared_parse_resource_directory,
    resolve_single_resource,
)
from _resource_health import (  # noqa: E402
    build_effective_monitoring_model,
    build_resource_identity,
    build_scoped_metric_query,
    project_operational_properties,
    redact_sensitive,
    sanitize_error_text,
    summarize_prometheus_payload,
)


BASELINE_DAYS = 7
MAX_QUERY_WORKERS = 4


def _load_datasource_resource_module():
    """Load the datasource resource module without colliding with other skills."""
    module_path = DATASOURCE_SCRIPT_DIR / "list_resource.py"
    spec = importlib.util.spec_from_file_location("_smartcmp_health_list_resource", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load datasource helpers from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_resource_module = _load_datasource_resource_module()
load_resource_records = _resource_module.load_resource_records
search_resource_summaries = _resource_module.search_resource_summaries


def resource_request_json(
    method: str,
    path: str,
    *,
    base_url: str,
    headers: dict[str, str],
    payload: Any = None,
    params: Any = None,
    timeout: int = default_timeout,
) -> Any:
    """Call one CMP JSON endpoint without forwarding auth through redirects.

    Args:
        method: HTTP method required by the CMP endpoint.
        path: CMP API path relative to the configured platform base URL.
        base_url: Configured CMP platform API base URL.
        headers: Current-user CMP authentication headers.
        payload: Optional JSON request body.
        params: Optional query parameters.
        timeout: Request timeout in seconds.

    Returns:
        Decoded JSON response.

    Raises:
        RuntimeError: If CMP redirects, returns a non-success status, or emits
            a non-JSON response.
        requests.RequestException: If the network request fails.
    """
    try:
        response = requests.request(
            method,
            f"{base_url.rstrip('/')}/{path.lstrip('/')}",
            headers=headers,
            json=payload,
            params=params,
            verify=False,
            timeout=timeout,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise RuntimeError("CMP API request failed.") from exc
    _reject_redirect(response, "CMP API")
    status_code = int(getattr(response, "status_code", 0) or 0)
    if not 200 <= status_code < 300:
        raise RuntimeError(f"CMP API returned HTTP {status_code}.")
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError("CMP API response did not contain valid JSON.") from exc


def positive_window_hours(value: str) -> int:
    """Parse an analysis window between one hour and seven days."""
    parsed = int(value)
    if parsed < 1 or parsed > 168:
        raise argparse.ArgumentTypeError("window_hours must be between 1 and 168")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse a single-resource health evidence request."""
    parser = argparse.ArgumentParser(
        description="Collect SmartCMP resource health evidence for LLM analysis."
    )
    parser.add_argument("--resource-name", default="", help="Exact visible SmartCMP resource name.")
    parser.add_argument("--resource-index", type=int, help="Visible index from the latest resource list.")
    parser.add_argument("--resource-directory-json", default="", help="Hidden latest resource-list metadata.")
    parser.add_argument("--resource-id", default="", help="Internal compatibility-only SmartCMP resource ID.")
    parser.add_argument("--window-hours", type=positive_window_hours, default=24)
    return parser.parse_args(argv)


def parse_resource_directory(raw_value: Any) -> list[dict[str, Any]]:
    """Extract resource-list records from direct or workflow-context JSON."""
    return shared_parse_resource_directory(raw_value)


def resolve_resource_id(
    *,
    resource_id: str,
    resource_name: str,
    resource_index: int | None,
    directory_items: list[dict[str, Any]],
    base_url: str,
    headers: dict[str, str],
    request_fn: Callable[..., Any] = resource_request_json,
) -> tuple[str, str]:
    """Resolve a name or visible index into one internal resource ID.

    Args:
        resource_id: Internal compatibility target, when already known.
        resource_name: Exact user-visible resource name.
        resource_index: Visible list index selected by the user.
        directory_items: Latest resource-list metadata.
        base_url: SmartCMP platform API base URL.
        headers: Current-user SmartCMP request headers.
        request_fn: Redirect-safe CMP JSON request function.

    Returns:
        Tuple of internal resource ID and resolved visible name.

    Raises:
        ResourceResolutionError: If no single target can be resolved.
    """
    return resolve_single_resource(
        resource_id_value=resource_id,
        resource_name=str(resource_name or "").strip(),
        resource_index=resource_index,
        directory_items=directory_items,
        search_page=lambda page, size, name: search_resource_summaries(
            base_url=base_url,
            headers=headers,
            request_fn=request_fn,
            params={"page": page, "size": size, "queryValue": name},
            payload={"queryValue": name},
        ),
    )


def collect_resource_health_context(
    *,
    resource_id: str,
    resource_name: str,
    window_hours: int,
    base_url: str,
    headers: dict[str, str],
    timeout: int = default_timeout,
    request_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Collect resource, monitoring-model, and time-series evidence.

    Args:
        resource_id: Resolved internal SmartCMP resource identifier.
        resource_name: Resolved visible resource name, when known.
        window_hours: Current time-series analysis window.
        base_url: SmartCMP platform API base URL.
        headers: Current-user SmartCMP request headers.
        timeout: Per-request timeout in seconds.
        request_fn: Optional redirect-safe CMP request function for tests or
            a caller-provided timeout binding.

    Returns:
        Evidence payload for the AtlasClaw LLM. The payload never contains a
        deterministic healthy/abnormal assessment.
    """
    cmp_request = request_fn or partial(resource_request_json, timeout=timeout)
    records = load_resource_records(
        [resource_id],
        base_url=base_url,
        headers=headers,
        request_fn=cmp_request,
    )
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
        "object_actions": [],
    }
    if not component_type:
        payload["missingEvidence"].append("resource.componentType")
        return payload

    try:
        metric_groups = cmp_request(
            "GET",
            "/alarm-policies/alarm-metric-groups",
            base_url=base_url,
            headers=headers,
            params={"resourceType": component_type},
        )
    except (RuntimeError, requests.RequestException) as exc:
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
        monitor_payload = cmp_request(
            "GET",
            f"/nodes/{resource_id}/monitor",
            base_url=base_url,
            headers=headers,
        )
    except (RuntimeError, requests.RequestException) as exc:
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
        monitor_url_payload = fetch_monitor_api_url(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
        )
        monitor_url = extract_monitor_api_url(monitor_url_payload)
        query_url = build_query_range_url(monitor_url)
    except (RuntimeError, ValueError, requests.RequestException) as exc:
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
            except (RuntimeError, TypeError, ValueError, requests.RequestException) as exc:
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


def fetch_monitor_api_url(
    *,
    base_url: str,
    headers: dict[str, str],
    timeout: int,
) -> Any:
    """Read the CMP-managed monitoring URL from JSON or plain text.

    Args:
        base_url: SmartCMP platform API base URL.
        headers: Current-user SmartCMP request headers.
        timeout: Request timeout in seconds.

    Returns:
        Decoded JSON when available, otherwise the plain response body.

    Raises:
        requests.RequestException: If the CMP endpoint cannot be read.
    """
    response = requests.get(
        f"{base_url.rstrip('/')}/monitor/api_url",
        headers=headers,
        verify=False,
        timeout=timeout,
        allow_redirects=False,
    )
    _reject_redirect(response, "CMP monitoring API URL")
    response.raise_for_status()
    try:
        return response.json()
    except ValueError:
        return response.text.strip()


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


def emit_summary(payload: dict[str, Any]) -> None:
    """Print a human summary that does not claim a health verdict."""
    name = str((payload.get("resource") or {}).get("name") or payload.get("object_name") or "resource")
    state = str(payload.get("monitoring_state") or "unsupported")
    metric_count = int((payload.get("monitoringModel") or {}).get("metricCount") or 0)
    print(f"Collected health evidence for {name}. Monitoring state: {state}. Model metrics: {metric_count}.")


def emit_context_block(payload: dict[str, Any]) -> None:
    """Print the structured context consumed by the AtlasClaw LLM."""
    print("##RESOURCE_HEALTH_CONTEXT_START##")
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    print("##RESOURCE_HEALTH_CONTEXT_END##")


def main(argv: list[str] | None = None) -> int:
    """Resolve one resource and emit model-driven health evidence."""
    args = parse_args(argv)
    try:
        base_url, headers, instance = get_connection()
        timeout = _configured_timeout(instance)
        cmp_request = partial(resource_request_json, timeout=timeout)
        directory = parse_resource_directory(args.resource_directory_json)
        resource_id, resource_name = resolve_resource_id(
            resource_id=args.resource_id,
            resource_name=args.resource_name,
            resource_index=args.resource_index,
            directory_items=directory,
            base_url=base_url,
            headers=headers,
            request_fn=cmp_request,
        )
        payload = collect_resource_health_context(
            resource_id=resource_id,
            resource_name=resource_name,
            window_hours=args.window_hours,
            base_url=base_url,
            headers=headers,
            timeout=timeout,
            request_fn=cmp_request,
        )
    except (ResourceResolutionError, RuntimeError, requests.RequestException, SystemExit) as exc:
        print(f"[ERROR] {sanitize_error_text(exc)}")
        return 1

    emit_summary(payload)
    emit_context_block(payload)
    return 0


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
    except (RuntimeError, requests.RequestException) as exc:
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
    except (RuntimeError, requests.RequestException) as exc:
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
    response = requests.get(
        url,
        params={"query": query, "start": start, "end": end, "step": step},
        headers=headers,
        verify=False,
        timeout=timeout,
        allow_redirects=False,
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


def _configured_timeout(instance: Any) -> int:
    if not isinstance(instance, dict):
        return default_timeout
    try:
        return int(instance.get("timeout") or default_timeout)
    except (TypeError, ValueError):
        return default_timeout


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


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
