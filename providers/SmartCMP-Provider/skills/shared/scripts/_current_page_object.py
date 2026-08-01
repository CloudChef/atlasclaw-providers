# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Adapt AtlasClaw page Context to SmartCMP Provider object reads."""

from __future__ import annotations

from typing import Any

from _provider_bootstrap import load_provider
from _atlasclaw_adapter import (
    AtlasClawAdapterError,
    embedded_object_id as atlasclaw_embedded_object_id,
    selected_provider_request as atlasclaw_selected_provider_request,
)

load_provider()

from smartcmp_provider.auth.models import ResolvedSmartCmpRequest  # noqa: E402
from smartcmp_provider.errors import SmartCmpError  # noqa: E402
from smartcmp_provider.models.objects import ObjectReadQuery  # noqa: E402
from smartcmp_provider.operations.objects import get_object_by_id  # noqa: E402
from smartcmp_provider.transport.client import SmartCmpClient  # noqa: E402


class CurrentPageObjectError(RuntimeError):
    """Report a page-scope, selected-instance, or Provider read mismatch."""


def selected_provider_request(
    ctx: Any,
    *,
    request_cookie_only: bool = True,
) -> ResolvedSmartCmpRequest:
    """Resolve the selected AtlasClaw Provider through the shared adapter."""

    try:
        return atlasclaw_selected_provider_request(
            ctx,
            request_cookie_only=request_cookie_only,
        )
    except AtlasClawAdapterError as exc:
        raise CurrentPageObjectError(str(exc)) from exc


def _current_scope(
    ctx: Any,
    *,
    expected_object_type: str,
) -> tuple[str, ResolvedSmartCmpRequest]:
    """Validate immutable AtlasClaw page scope and return its Provider request."""

    try:
        object_id = atlasclaw_embedded_object_id(
            ctx,
            expected_object_type=expected_object_type,
        )
    except AtlasClawAdapterError as exc:
        raise CurrentPageObjectError(str(exc)) from exc
    if not object_id:
        raise CurrentPageObjectError(
            "This tool requires an active SmartCMP page Context."
        )
    return object_id, selected_provider_request(ctx)


def embedded_object_id(ctx: Any, *, expected_object_type: str) -> str | None:
    """Return the server-owned object ID, or ``None`` outside embedded pages."""

    try:
        return atlasclaw_embedded_object_id(
            ctx,
            expected_object_type=expected_object_type,
        )
    except AtlasClawAdapterError as exc:
        raise CurrentPageObjectError(str(exc)) from exc


async def fetch_current_page_object(
    ctx: Any,
    *,
    expected_object_type: str,
    api_collection: str,
) -> dict[str, Any]:
    """Read the exact page object through the shared SmartCMP Provider operation."""

    object_contracts = {
        "blueprint_component": ("component_definition", "components"),
        "form_definition": ("form_definition", "forms"),
        "optimization_policy": ("optimization_policy", "compliance-policies"),
        "script_definition": ("script_definition", "scripts"),
    }
    provider_object_type, expected_collection = object_contracts.get(
        expected_object_type,
        ("", ""),
    )
    if expected_collection != str(api_collection or "").strip().strip("/"):
        raise CurrentPageObjectError(
            "Current object API collection is invalid."
        )
    object_id, request = _current_scope(
        ctx,
        expected_object_type=expected_object_type,
    )
    try:
        async with SmartCmpClient(request) as client:
            result = await get_object_by_id(
                client,
                ObjectReadQuery(
                    object_type=provider_object_type,
                    object_id=object_id,
                ),
            )
    except (SmartCmpError, ValueError) as exc:
        raise CurrentPageObjectError(str(exc)) from exc
    return result.payload
