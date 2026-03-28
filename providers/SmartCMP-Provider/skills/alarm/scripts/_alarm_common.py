"""Shared helpers for SmartCMP alarm retrieval, analysis, and operations."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

import requests


SCRIPT_DIR = Path(__file__).resolve().parent
SHARED_SCRIPTS_DIR = SCRIPT_DIR.parents[1] / "shared" / "scripts"

import sys

if str(SHARED_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPTS_DIR))

from _common import create_headers, get_cmp_config


ACTION_STATUS_MAP = {
    "mute": "ALERT_MUTED",
    "resolve": "ALERT_RESOLVED",
    "reopen": "ALERT_FIRING",
}
POLICY_HINT_KEYS = {
    "metric",
    "expression",
    "resourceType",
    "category",
    "type",
    "nameZh",
    "descriptionZh",
    "policyMetricType",
    "relationType",
}

DEFAULT_TIMEOUT = 30
DEFAULT_PAGE = 1
DEFAULT_SIZE = 20
DEFAULT_SORT = ""
ONE_DAY_MS = 86_400_000


def build_placeholder_payload(command: str, **details: Any) -> Dict[str, Any]:
    """Return a stable placeholder payload for scaffold scripts."""
    return {
        "status": "not_implemented",
        "command": command,
        "details": details,
        "message": "Alarm skill scaffold is present, but business logic is not implemented yet.",
    }


def emit_placeholder(command: str, **details: Any) -> int:
    """Print a placeholder payload and exit successfully."""
    print(json.dumps(build_placeholder_payload(command, **details), ensure_ascii=True, indent=2))
    return 0


def normalize_action(action: str) -> str:
    """Normalize an English action and validate it."""
    normalized = (action or "").strip().lower()
    if normalized not in ACTION_STATUS_MAP:
        valid_actions = ", ".join(sorted(ACTION_STATUS_MAP))
        raise ValueError(f"Unsupported action '{action}'. Expected one of: {valid_actions}.")
    return normalized


def map_action_to_status(action: str) -> str:
    """Map an English action to the SmartCMP alert status."""
    return ACTION_STATUS_MAP[normalize_action(action)]


def normalize_timestamp(value: Any) -> str:
    """Normalize supported timestamp shapes to UTC with trailing Z."""
    if value in (None, ""):
        return ""

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ""
        if _looks_like_number(stripped):
            return normalize_timestamp(float(stripped))
        try:
            parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        except ValueError:
            return stripped
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if isinstance(value, (int, float)):
        timestamp = float(value)
        if abs(timestamp) >= 1_000_000_000_000:
            timestamp /= 1000.0
        parsed = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")

    return str(value)


def extract_items(payload: Any) -> List[Any]:
    """Extract list-like content from common SmartCMP response wrappers."""
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, Mapping):
        return []

    for key in ("content", "data", "items", "result"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, Mapping):
            extracted = extract_items(value)
            if extracted:
                return extracted
    return []


def extract_policy(payload: Any) -> Dict[str, Any]:
    """Extract a policy object from direct or wrapped payloads."""
    if isinstance(payload, list):
        for item in payload:
            if _looks_like_policy(item):
                return dict(item)
        return {}

    if isinstance(payload, Mapping):
        if "policy" in payload and _looks_like_policy(payload["policy"]):
            return dict(payload["policy"])

        for key in ("content", "data", "result"):
            value = payload.get(key)
            if isinstance(value, Mapping):
                extracted = extract_policy(value)
                if extracted:
                    return extracted

        if _looks_like_policy(payload):
            return dict(payload)

    return {}


def build_list_params(
    page: int = DEFAULT_PAGE,
    size: int = DEFAULT_SIZE,
    sort: str = DEFAULT_SORT,
    statuses: Any = None,
    days: int | None = None,
    level: int | None = None,
    deployment_id: str = "",
    entity_instance_id: str = "",
    node_instance_id: str = "",
    alarm_type: str = "",
    alarm_categories: Any = None,
    business_group_ids: Any = None,
    group_ids: Any = None,
    now_ms: int | None = None,
    **filters: Any,
) -> Dict[str, Any]:
    """Build query parameters, omitting blank optional values."""
    params: Dict[str, Any] = {"page": page, "size": size}
    if sort:
        params["sort"] = sort

    if days is not None and int(days) > 0:
        end_ms = int(now_ms if now_ms is not None else time.time() * 1000)
        params["triggerAtMin"] = end_ms - (int(days) * ONE_DAY_MS)
        params["triggerAtMax"] = end_ms

    status_list = normalize_list_argument(statuses)
    if status_list:
        params["status"] = status_list

    category_list = normalize_list_argument(alarm_categories)
    if category_list:
        params["alarmCategory"] = category_list

    business_group_list = normalize_list_argument(business_group_ids)
    if business_group_list:
        params["businessGroupIds"] = business_group_list

    group_list = normalize_list_argument(group_ids)
    if group_list:
        params["groupIds"] = group_list

    if level is not None:
        params["level"] = int(level)
    if deployment_id:
        params["deploymentId"] = deployment_id
    if entity_instance_id:
        params["entityInstanceId"] = entity_instance_id
    if node_instance_id:
        params["nodeInstanceId"] = node_instance_id
    if alarm_type:
        params["alarmType"] = alarm_type

    for key, value in filters.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        params[key] = value
    return params


def normalize_list_argument(value: Any) -> List[str]:
    """Normalize list-like filter values into a compact string list."""
    if value in (None, ""):
        return []

    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, Iterable):
        parts = []
        for item in value:
            if item in (None, ""):
                continue
            parts.extend(str(item).split(","))
    else:
        parts = [str(value)]

    normalized = []
    for part in parts:
        stripped = str(part).strip()
        if stripped:
            normalized.append(stripped)
    return normalized


def get_connection(content_type: str = "application/json; charset=utf-8") -> tuple[str, dict[str, str], dict[str, Any]]:
    """Return SmartCMP base URL, headers, and instance config."""
    base_url, auth_token, instance = get_cmp_config(exit_on_error=True)
    return base_url, create_headers(auth_token, content_type=content_type), instance


def request_json(
    method: str,
    path: str,
    *,
    params: Mapping[str, Any] | None = None,
    payload: Mapping[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    """Send a JSON request to SmartCMP and return the decoded payload."""
    base_url, headers, _ = get_connection()
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    request_kwargs = {
        "method": method.upper(),
        "url": url,
        "headers": headers,
        "params": dict(params or {}),
        "verify": False,
        "timeout": timeout,
    }
    if payload is not None:
        request_kwargs["json"] = dict(payload)

    try:
        response = requests.request(**request_kwargs)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"SmartCMP request failed for {method.upper()} {path}: {exc}") from exc

    if response.status_code == 204 or not response.text.strip():
        return {}

    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(f"SmartCMP response is not valid JSON for {method.upper()} {path}.") from exc


def get_json(path: str, *, params: Mapping[str, Any] | None = None, timeout: int = DEFAULT_TIMEOUT) -> Any:
    """Send a GET request and decode the JSON response."""
    return request_json("GET", path, params=params, timeout=timeout)


def post_json(
    path: str,
    *,
    payload: Mapping[str, Any] | None = None,
    params: Mapping[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    """Send a POST request and decode the JSON response."""
    return request_json("POST", path, params=params, payload=payload, timeout=timeout)


def put_json(
    path: str,
    *,
    payload: Mapping[str, Any] | None = None,
    params: Mapping[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    """Send a PUT request and decode the JSON response."""
    return request_json("PUT", path, params=params, payload=payload, timeout=timeout)


def find_alert_by_id(items: Iterable[Mapping[str, Any]], alert_id: str) -> Dict[str, Any]:
    """Return the first alert whose id matches the provided alert_id."""
    for item in items:
        if item.get("id") == alert_id:
            return dict(item)
    return {}


def _looks_like_number(value: str) -> bool:
    if not value:
        return False
    if value[0] in {"+", "-"}:
        value = value[1:]
    return value.replace(".", "", 1).isdigit()


def _looks_like_policy(payload: Any) -> bool:
    if not isinstance(payload, Mapping):
        return False
    if any(key in payload for key in POLICY_HINT_KEYS):
        return True
    return "name" in payload and "nameZh" in payload
