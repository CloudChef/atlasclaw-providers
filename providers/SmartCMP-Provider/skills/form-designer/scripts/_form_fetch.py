#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Read-only helpers for SmartCMP form designer tools."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse

import requests

try:
    from _common import normalize_ui_base_url
except ImportError:
    import os
    import sys

    sys.path.insert(
        0,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared", "scripts"),
    )
    from _common import normalize_ui_base_url

try:
    from _common import request_timeout
except ImportError:

    def request_timeout() -> int:
        return 30


_FORM_EDIT_ROUTE = re.compile(
    r"^/main/service-model/forms/(?P<route>edit|design)/"
    r"(?P<form_id>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
    r"/?$"
)


@dataclass(frozen=True)
class FormSource:
    """Source metadata extracted from a SmartCMP form edit URL."""

    form_id: str
    form_url: str
    route: str


@dataclass(frozen=True)
class FormDefinition:
    """Read-only SmartCMP form definition used by the form designer."""

    form_id: str
    name: str
    description: str
    schema: dict[str, Any]
    model: dict[str, Any]
    design_mode: str
    component_count: int
    source_route: str
    raw_content_keys: list[str]


def parse_form_edit_url(form_url: str, cmp_base_url: str) -> FormSource:
    """Parse and validate a SmartCMP form edit URL for the current provider instance.

    Args:
        form_url: Browser URL copied from SmartCMP's form editor.
        cmp_base_url: Current SmartCMP provider base URL, usually ending in `/platform-api`.

    Returns:
        Parsed form source metadata.

    Raises:
        ValueError: If the URL is external, malformed, or not a form edit route.
    """
    raw_url = (form_url or "").strip()
    if not raw_url:
        raise ValueError("form_url is required.")

    parsed_url = urlparse(raw_url)
    if not parsed_url.scheme or not parsed_url.netloc:
        raise ValueError("form_url must be an absolute SmartCMP UI URL.")

    expected_ui = urlparse(normalize_ui_base_url(cmp_base_url))
    # Form edit URLs are accepted only from the selected provider instance. This
    # prevents a copied URL from another CMP host from driving cross-instance reads.
    actual_path = parsed_url.path.rstrip("/")
    expected_path = expected_ui.path.rstrip("/")
    if (
        parsed_url.scheme != expected_ui.scheme
        or parsed_url.netloc != expected_ui.netloc
        or actual_path != expected_path
    ):
        raise ValueError("form_url must belong to the selected SmartCMP provider instance.")

    # The form UUID lives in SmartCMP's hash route; query parameters in the
    # fragment are navigation noise and must not affect the API endpoint.
    fragment_route = parsed_url.fragment.split("?", 1)[0].strip()
    route_match = _FORM_EDIT_ROUTE.match(fragment_route)
    if not route_match:
        raise ValueError(
            "form_url must use #/main/service-model/forms/edit/<uuid> "
            "or #/main/service-model/forms/design/<uuid>."
        )

    form_id = str(uuid.UUID(route_match.group("form_id")))
    return FormSource(form_id=form_id, form_url=raw_url, route=route_match.group("route"))


def extract_schema_from_payload(payload: Any) -> dict[str, Any]:
    """Extract `content.schema` from a SmartCMP form definition response.

    Args:
        payload: JSON response from `GET /forms/{uuid}`.

    Returns:
        The schema dictionary.

    Raises:
        ValueError: If the response does not contain an object schema.
    """
    if not isinstance(payload, dict):
        raise ValueError("Form response must be a JSON object.")

    content = payload.get("content")
    if not isinstance(content, dict):
        raise ValueError("Form response is missing content object.")

    schema = content.get("schema")
    if isinstance(schema, str):
        try:
            schema = json.loads(schema)
        except json.JSONDecodeError as error:
            raise ValueError(f"Form content.schema is not valid JSON: {error}") from error

    if not isinstance(schema, dict):
        raise ValueError("Form content.schema must be a JSON object.")
    return schema


def extract_model_from_payload(payload: Any) -> dict[str, Any]:
    """Extract optional `content.model` from a SmartCMP form definition response."""
    content = payload.get("content") if isinstance(payload, dict) else None
    if not isinstance(content, dict):
        return {}

    model = content.get("model")
    if isinstance(model, str):
        try:
            model = json.loads(model)
        except json.JSONDecodeError:
            return {}
    return model if isinstance(model, dict) else {}


def fetch_form_definition(
    form_url: str,
    base_url: str,
    headers: dict[str, str],
    *,
    get: Callable[..., requests.Response] | None = None,
) -> FormDefinition:
    """Fetch one SmartCMP form definition using the read-only form API.

    Args:
        form_url: Current-instance SmartCMP form edit URL.
        base_url: SmartCMP API base URL ending in `/platform-api`.
        headers: Authentication headers from the shared SmartCMP config helper.
        get: Optional injectable HTTP GET function used by tests.

    Returns:
        Form definition with extracted schema.

    Raises:
        ValueError: If the URL or response is invalid.
        requests.RequestException: If the read-only GET fails.
    """
    source = parse_form_edit_url(form_url, base_url)
    getter = get or requests.get
    # Keep the endpoint construction centralized here so the skill never needs a
    # broader form API surface than the read-only detail endpoint.
    response = getter(
        f"{base_url.rstrip('/')}/forms/{source.form_id}",
        headers=headers,
        verify=False,
        timeout=request_timeout(),
    )
    response.raise_for_status()
    payload = response.json()
    schema = extract_schema_from_payload(payload)
    model = extract_model_from_payload(payload)
    content = payload.get("content") if isinstance(payload, dict) else {}
    components = content.get("components") if isinstance(content, dict) else None
    design_mode = content.get("designMode") if isinstance(content, dict) else ""

    return FormDefinition(
        form_id=source.form_id,
        name=str(payload.get("name") or "") if isinstance(payload, dict) else "",
        description=str(payload.get("description") or "") if isinstance(payload, dict) else "",
        schema=schema,
        model=model,
        design_mode=str(design_mode or "") if isinstance(content, dict) else "",
        component_count=len(components) if isinstance(components, list) else 0,
        source_route=source.route,
        raw_content_keys=sorted(content.keys()) if isinstance(content, dict) else [],
    )
