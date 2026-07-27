# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Read the exact SmartCMP object bound to the current embedded page Context."""

from __future__ import annotations

import re
import uuid
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

try:
    from _common import _auto_login, _resolve_auth_url, create_headers
except ModuleNotFoundError:
    _auto_login = None
    _resolve_auth_url = None
    create_headers = None


_API_COLLECTION = re.compile(r"^[a-z][a-z0-9-]*(?:/[a-z][a-z0-9-]*)*$")
_DEFAULT_TIMEOUT_SECONDS = 60


class CurrentPageObjectError(RuntimeError):
    """Raised when a current-page Tool cannot safely resolve its bound object."""


def _exact_uuid(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    try:
        parsed = uuid.UUID(normalized)
    except (ValueError, AttributeError):
        return ""
    return normalized if str(parsed) == normalized else ""


def _normalize_base_url(value: Any) -> str:
    raw_url = value.strip() if isinstance(value, str) else ""
    parsed = urlparse(raw_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise CurrentPageObjectError("Selected SmartCMP instance has an invalid base URL.")
    path = parsed.path.rstrip("/")
    if not path.endswith("/platform-api"):
        path = f"{path}/platform-api"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def _request_timeout(instance: dict[str, Any]) -> int:
    value = instance.get("timeout")
    if value in (None, ""):
        return _DEFAULT_TIMEOUT_SECONDS
    try:
        timeout = int(float(str(value).strip()))
    except (TypeError, ValueError) as exc:
        raise CurrentPageObjectError(
            "Selected SmartCMP instance has an invalid timeout."
        ) from exc
    if timeout <= 0:
        raise CurrentPageObjectError("Selected SmartCMP instance has an invalid timeout.")
    return timeout


def selected_provider_read_config(
    ctx: Any,
    *,
    request_cookie_only: bool = True,
) -> tuple[str, dict[str, str], int]:
    """Return the selected SmartCMP instance and request-user read credentials.

    Args:
        ctx: AtlasClaw Tool context for the current request.
        request_cookie_only: Require the signed-in request user's SmartCMP
            session. Embedded page reads must keep this enabled; ordinary chat
            URL reads may use the selected Provider instance's configured auth.

    Returns:
        Normalized API base URL, request-user headers, and timeout.

    Raises:
        CurrentPageObjectError: If the selected instance or request-user session
            is unavailable.
    """
    deps = getattr(ctx, "deps", None)
    extra = getattr(deps, "extra", None)
    if not isinstance(extra, dict):
        raise CurrentPageObjectError(
            "Selected SmartCMP Provider instance is unavailable."
        )
    instance_name = str(extra.get("provider_instance_name") or "").strip()
    instance = extra.get("provider_instance")
    if not instance_name or not isinstance(instance, dict):
        raise CurrentPageObjectError(
            "Selected SmartCMP Provider instance is unavailable."
        )

    base_url = _normalize_base_url(instance.get("base_url"))
    timeout = _request_timeout(instance)
    cookies = getattr(deps, "cookies", None)
    request_cookie = (
        cookies.get("CloudChef-Authenticate") if isinstance(cookies, dict) else None
    )
    request_token = (
        request_cookie.strip()
        if isinstance(request_cookie, str) and request_cookie.strip()
        else ""
    )
    if request_cookie_only and not request_token:
        raise CurrentPageObjectError(
            "Current SmartCMP user session is unavailable or expired."
        )
    if request_token:
        return base_url, {"CloudChef-Authenticate": request_token}, timeout

    auth_type_value = instance.get("auth_type")
    if isinstance(auth_type_value, list):
        auth_type = str(auth_type_value[0] if auth_type_value else "").strip()
    else:
        auth_type = str(auth_type_value or "").strip()
    runtime_cookie = str(extra.get("provider_cookie_token") or "").strip()
    runtime_sso = str(extra.get("provider_sso_token") or "").strip()
    if auth_type == "provider_token":
        auth_token = str(instance.get("provider_token") or "").strip()
    elif auth_type == "user_token":
        auth_token = str(instance.get("user_token") or "").strip()
    elif auth_type == "cookie":
        auth_token = runtime_cookie or str(instance.get("cookie") or "").strip()
    elif auth_type == "credential":
        auth_token = runtime_cookie or runtime_sso
    else:
        auth_token = (
            runtime_cookie
            or runtime_sso
            or str(instance.get("provider_token") or "").strip()
            or str(instance.get("user_token") or "").strip()
            or str(instance.get("cookie") or "").strip()
        )

    if (
        not auth_token
        and str(instance.get("username") or "").strip()
        and str(instance.get("password") or "")
        and callable(_auto_login)
        and callable(_resolve_auth_url)
    ):
        try:
            cookie_text = _auto_login(
                _resolve_auth_url(
                    base_url,
                    str(instance.get("auth_url") or "").strip(),
                ),
                str(instance["username"]).strip(),
                str(instance["password"]),
                timeout=timeout,
            )
        except RuntimeError as exc:
            raise CurrentPageObjectError(
                "Selected SmartCMP Provider credentials could not authenticate."
            ) from exc
        for part in cookie_text.split(";"):
            key, separator, value = part.strip().partition("=")
            if separator and key == "CloudChef-Authenticate" and value.strip():
                auth_token = value.strip()
                break
        if not auth_token:
            auth_token = cookie_text.strip()

    if not auth_token:
        raise CurrentPageObjectError(
            "Selected SmartCMP Provider authentication is unavailable."
        )
    if callable(create_headers):
        return base_url, create_headers(auth_token), timeout
    if auth_token.startswith("cmp_tk_"):
        return base_url, {"Authorization": f"Bearer {auth_token}"}, timeout
    return base_url, {"CloudChef-Authenticate": auth_token}, timeout


def _current_scope(
    ctx: Any,
    *,
    expected_object_type: str,
) -> tuple[str, str, dict[str, str], int]:
    deps = getattr(ctx, "deps", None)
    extra = getattr(deps, "extra", None)
    if not isinstance(extra, dict):
        raise CurrentPageObjectError(
            "This tool requires an active SmartCMP page Context."
        )

    context = extra.get("context")
    context = context if isinstance(context, dict) else {}
    scope = context.get("embed_scope")
    turn_context = context.get("turn_context")
    turn_context = turn_context if isinstance(turn_context, dict) else {}
    turn_object = turn_context.get("object")
    turn_object = turn_object if isinstance(turn_object, dict) else {}
    if not isinstance(scope, dict):
        raise CurrentPageObjectError(
            "This tool requires an active SmartCMP page Context."
        )

    provider_type = str(scope.get("provider_type") or "").strip()
    object_type = str(scope.get("object_type") or "").strip()
    object_id = _exact_uuid(scope.get("object_id"))
    if provider_type != "smartcmp" or object_type != expected_object_type or not object_id:
        raise CurrentPageObjectError(
            f"This tool can only read the current {expected_object_type} page object."
        )
    if (
        str(turn_object.get("type") or "").strip() != expected_object_type
        or _exact_uuid(turn_object.get("id")) != object_id
    ):
        raise CurrentPageObjectError("Current SmartCMP page Context is inconsistent.")

    instance_name = str(scope.get("provider_instance") or "").strip()
    selected_instance_name = str(extra.get("provider_instance_name") or "").strip()
    if not instance_name or instance_name != selected_instance_name:
        raise CurrentPageObjectError(
            "Current SmartCMP Provider instance is unavailable."
        )
    base_url, headers, timeout = selected_provider_read_config(ctx)
    return (
        object_id,
        base_url,
        headers,
        timeout,
    )


def embedded_object_id(ctx: Any, *, expected_object_type: str) -> str | None:
    """Return the server-owned embedded object ID when page Context is active.

    Args:
        ctx: AtlasClaw Tool context for the current request.
        expected_object_type: Object type owned by the calling page Skill.

    Returns:
        The exact Context object UUID, or ``None`` for ordinary non-embedded chat.

    Raises:
        CurrentPageObjectError: If an embedded scope exists but is inconsistent
            with the expected object, selected instance, or request-user session.
    """
    deps = getattr(ctx, "deps", None)
    extra = getattr(deps, "extra", None)
    context = extra.get("context") if isinstance(extra, dict) else None
    scope = context.get("embed_scope") if isinstance(context, dict) else None
    if scope is None:
        return None
    object_id, _base_url, _headers, _timeout = _current_scope(
        ctx,
        expected_object_type=expected_object_type,
    )
    return object_id


async def fetch_current_page_object(
    ctx: Any,
    *,
    expected_object_type: str,
    api_collection: str,
) -> dict[str, Any]:
    """Fetch one exact current-page object with request-user authentication.

    Args:
        ctx: AtlasClaw Tool context containing the immutable embedded page scope.
        expected_object_type: Object type declared by the owning page Skill.
        api_collection: Read-only SmartCMP API collection without leading slash.

    Returns:
        The exact Provider JSON object whose ID matches the current Context.

    Raises:
        CurrentPageObjectError: If Context, instance, session, endpoint, response,
            or object identity validation fails.
    """
    collection = str(api_collection or "").strip().strip("/")
    if not _API_COLLECTION.fullmatch(collection):
        raise CurrentPageObjectError("Current object API collection is invalid.")
    object_id, base_url, headers, timeout = _current_scope(
        ctx,
        expected_object_type=expected_object_type,
    )
    try:
        async with httpx.AsyncClient(
            verify=False,
            timeout=timeout,
            trust_env=False,
        ) as client:
            response = await client.get(
                f"{base_url}/{collection}/{object_id}",
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        raise CurrentPageObjectError(
            f"SmartCMP rejected the current object read with HTTP {exc.response.status_code}."
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise CurrentPageObjectError(
            "SmartCMP current object read failed."
        ) from exc

    if not isinstance(payload, dict):
        raise CurrentPageObjectError(
            "SmartCMP current object response must be a JSON object."
        )
    if _exact_uuid(payload.get("id")) != object_id:
        raise CurrentPageObjectError(
            "SmartCMP current object response does not match the page Context."
        )
    return payload
