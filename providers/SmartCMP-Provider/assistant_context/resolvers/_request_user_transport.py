# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Side-effect-free SmartCMP request-user configuration and transport helpers."""

from __future__ import annotations

import json
import os
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlparse, urlunparse

from urllib3.exceptions import InsecureRequestWarning


DEFAULT_TIMEOUT_SECONDS = 60


class RequestUserConfigError(RuntimeError):
    """Raised when the exact Provider instance or current request Cookie is unavailable."""


def _parse_json_object(variable_name: str) -> dict[str, Any]:
    raw_value = os.environ.get(variable_name, "")
    try:
        value = json.loads(raw_value)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RequestUserConfigError(f"{variable_name} must be a JSON object") from exc
    if not isinstance(value, dict):
        raise RequestUserConfigError(f"{variable_name} must be a JSON object")
    return value


def _normalize_base_url(value: Any) -> str:
    raw_url = value.strip() if isinstance(value, str) else ""
    if not raw_url:
        raise RequestUserConfigError("selected SmartCMP instance is missing base_url")
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
        raise RequestUserConfigError("selected SmartCMP instance has an invalid base_url")
    path = parsed.path.rstrip("/")
    if not path.endswith("/platform-api"):
        path = f"{path}/platform-api"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def _request_timeout(instance: dict[str, Any]) -> int:
    configured = instance.get("timeout")
    if configured in (None, ""):
        return DEFAULT_TIMEOUT_SECONDS
    try:
        timeout = int(float(str(configured).strip()))
    except (TypeError, ValueError) as exc:
        raise RequestUserConfigError(
            "selected SmartCMP instance has an invalid timeout"
        ) from exc
    if timeout <= 0:
        raise RequestUserConfigError("selected SmartCMP instance has an invalid timeout")
    return timeout


def load_request_user_transport() -> tuple[str, dict[str, str], int]:
    """Return the exact instance URL, current request Cookie header, and timeout.

    This helper deliberately ignores Provider/user tokens, configured cookies,
    credentials, and auto-login settings. Reading environment values has no module-import
    side effect; callers decide when a request-user configuration is required.

    Raises:
        RequestUserConfigError: If the explicit instance or current request Cookie is invalid.
    """
    instance_name = os.environ.get("ATLASCLAW_PROVIDER_INSTANCE", "").strip()
    if not instance_name:
        raise RequestUserConfigError("ATLASCLAW_PROVIDER_INSTANCE is required")

    provider_config = _parse_json_object("ATLASCLAW_PROVIDER_CONFIG")
    smartcmp_instances = provider_config.get("smartcmp")
    if not isinstance(smartcmp_instances, dict):
        raise RequestUserConfigError("SmartCMP provider configuration is missing")
    instance = smartcmp_instances.get(instance_name)
    if not isinstance(instance, dict):
        raise RequestUserConfigError("selected SmartCMP provider instance is missing")

    cookies = _parse_json_object("ATLASCLAW_COOKIES")
    request_cookie = cookies.get("CloudChef-Authenticate")
    if not isinstance(request_cookie, str) or not request_cookie.strip():
        raise RequestUserConfigError(
            "request-scoped CloudChef-Authenticate cookie is required"
        )

    return (
        _normalize_base_url(instance.get("base_url")),
        {"CloudChef-Authenticate": request_cookie.strip()},
        _request_timeout(instance),
    )


@contextmanager
def suppress_insecure_request_warning() -> Iterator[None]:
    """Suppress only the expected warning emitted by enclosed ``verify=False`` calls."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", InsecureRequestWarning)
        yield
