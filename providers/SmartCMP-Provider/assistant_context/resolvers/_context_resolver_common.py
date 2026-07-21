# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Fail-closed request-user configuration and helpers for embedded page context."""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from typing import Any, Callable

import requests

try:
    from _request_user_transport import (
        RequestUserConfigError,
        load_request_user_transport,
        suppress_insecure_request_warning,
    )
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _request_user_transport import (
        RequestUserConfigError,
        load_request_user_transport,
        suppress_insecure_request_warning,
    )


class ContextConfigError(RuntimeError):
    """Raised before Provider I/O when request-user context configuration is invalid."""


RequestGet = Callable[..., Any]
CATALOG_ENTITY_CLASS = "io.cloudchef.yacmp.core.catalog.Catalog"
RESOURCE_ENTITY_CLASS = "io.cloudchef.yacmp.core.resource.Resource"
_CATALOG_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")
_REQUEST_ID = re.compile(r"^[A-Z]{3}\d{14}$")


def load_context_config() -> tuple[str, dict[str, str], int]:
    """Load only an explicit instance and request-scoped Host authentication cookie.

    Provider/user tokens, configured cookies, and credentials are intentionally ignored.
    This resolver path never imports the general SmartCMP helper, so it cannot auto-login.
    """
    try:
        return load_request_user_transport()
    except RequestUserConfigError as exc:
        raise ContextConfigError(str(exc)) from exc


BASE_URL, HEADERS, REQUEST_TIMEOUT = load_context_config()


def exact_uuid(value: Any) -> str:
    """Return a canonical UUID or an empty string when the external ID is invalid."""
    normalized = str(value or "").strip().lower()
    try:
        parsed = uuid.UUID(normalized)
    except (ValueError, AttributeError):
        return ""
    return normalized if str(parsed) == normalized else ""


def exact_catalog_id(value: str) -> str:
    """Validate UUID and built-in SmartCMP catalog identifiers without URL parts."""
    normalized = str(value or "").strip()
    return normalized if _CATALOG_ID.fullmatch(normalized) else ""


def exact_request_id(value: Any) -> str:
    """Return one user-visible SmartCMP workflow ID or an empty string."""
    normalized = str(value or "").strip().upper()
    return normalized if _REQUEST_ID.fullmatch(normalized) else ""


def text(value: Any) -> str:
    """Return a trimmed scalar string while excluding nested provider data."""
    return str(value).strip() if isinstance(value, (str, int, float)) else ""


def get_json(
    path: str,
    *,
    request_get: RequestGet = requests.get,
    params: dict[str, Any] | None = None,
) -> Any:
    """Execute one request-user authenticated, non-mutating Provider GET."""
    # Resolver stdout must remain a single JSON value. urllib3 writes this one
    # expected warning to stderr for verify=False, and the Markdown Tool runtime
    # preserves stderr as Tool output. Keep the suppression local and category-
    # specific so Provider diagnostics, unrelated warnings, and exceptions remain
    # observable and continue to fail closed.
    with suppress_insecure_request_warning():
        response = request_get(
            f"{BASE_URL}/{path.lstrip('/')}",
            headers=HEADERS,
            params=params,
            verify=False,
            timeout=REQUEST_TIMEOUT,
        )
    response.raise_for_status()
    return response.json()


def has_instance_permission(
    entity_class: str,
    entity_id: str,
    permission: str,
    *,
    request_get: RequestGet = requests.get,
) -> bool:
    """Check one effective current-user instance ACL from the read-only permission query."""
    try:
        payload = get_json(
            "acl/queryCurrentUserPermissions",
            request_get=request_get,
            params={
                "entityClassNames": entity_class,
                "entityInstanceIds": entity_id,
            },
        )
    except (requests.exceptions.RequestException, TypeError, ValueError):
        return False
    if not isinstance(payload, list):
        return False

    exact_entries: list[dict[str, Any]] = []
    class_entries: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        entity = item.get("entityClass")
        if not isinstance(entity, dict) or text(entity.get("className")) != entity_class:
            continue
        instance_id = text(entity.get("instanceId"))
        if instance_id == entity_id:
            exact_entries.append(item)
        elif instance_id in {"", "-1"}:
            class_entries.append(item)

    for item in exact_entries + class_entries:
        permissions = item.get("permissions")
        if not isinstance(permissions, list):
            continue
        permission_ids = {
            text(value.get("id")) if isinstance(value, dict) else text(value)
            for value in permissions
        }
        if permission in permission_ids:
            return True
    return False


def success_object(
    *,
    object_type: str,
    object_id: str,
    name: str,
    state: str,
    attributes: dict[str, Any],
    object_actions: list[dict[str, object]],
) -> dict[str, Any]:
    """Build the strict provider-neutral object and action envelope."""
    return {
        "success": True,
        "object": {
            "type": object_type,
            "id": object_id,
            "name": name,
            "state": state,
            "attributes": {key: value for key, value in attributes.items() if value != ""},
        },
        "object_actions": object_actions,
    }


def write_result(result: dict[str, Any]) -> None:
    """Write one coordination JSON value without credentials or raw Provider payloads."""
    print(json.dumps(result, ensure_ascii=False))
