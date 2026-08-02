"""AtlasClaw-only request and result helpers for SmartCMP Skill adapters.

This module is deliberately outside :mod:`smartcmp_provider`: it translates
AtlasClaw ``RunContext`` state and user-facing Tool results, while the Provider
implementation remains independent of AtlasClaw and MCP.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, TypeVar

from pydantic import BaseModel

try:
    from pydantic_ai import RunContext
except ImportError:  # Provider-only tests do not install AtlasClaw runtime.
    RunContext = Any

from _provider_bootstrap import load_provider

load_provider()

from smartcmp_provider.auth.models import ResolvedSmartCmpRequest  # noqa: E402
from smartcmp_provider.auth.resolver import (  # noqa: E402
    resolve_atlasclaw_instance_request,
)
from smartcmp_provider.errors import SmartCmpError  # noqa: E402
from smartcmp_provider.transport.client import SmartCmpClient  # noqa: E402


ResultT = TypeVar("ResultT")


class AtlasClawAdapterError(RuntimeError):
    """Report invalid AtlasClaw Context or selected Provider state."""


def selected_provider_request(
    ctx: Any,
    *,
    request_cookie_only: bool = False,
) -> ResolvedSmartCmpRequest:
    """Resolve one immutable SmartCMP request from AtlasClaw-owned Context.

    Args:
        ctx: AtlasClaw ``RunContext`` whose dependencies contain the selected
            Provider instance, request cookies, and optional webhook profile.
        request_cookie_only: Require the current user's SmartCMP session and
            reject configured service credentials.

    Returns:
        Request-scoped execution and authentication context.

    Raises:
        AtlasClawAdapterError: If AtlasClaw did not select a usable instance or
            SmartCMP authentication cannot be resolved.
    """

    deps = getattr(ctx, "deps", None)
    extra = getattr(deps, "extra", None)
    if not isinstance(extra, dict):
        raise AtlasClawAdapterError(
            "Selected SmartCMP Provider instance is unavailable."
        )
    instance_name = str(extra.get("provider_instance_name") or "").strip()
    instance = extra.get("provider_instance")
    if not instance_name or not isinstance(instance, Mapping):
        raise AtlasClawAdapterError(
            "Selected SmartCMP Provider instance is unavailable."
        )

    cookies = getattr(deps, "cookies", None)
    request_session_token = (
        str(cookies.get("CloudChef-Authenticate") or "").strip()
        if isinstance(cookies, Mapping)
        else ""
    )
    robot_profile = str(extra.get("robot_profile") or "").strip()
    user_info = getattr(deps, "user_info", None)
    user_id = str(
        getattr(user_info, "user_id", "")
        or getattr(deps, "user_id", "")
        or ""
    ).strip()
    subject = robot_profile or user_id or "atlasclaw-user"
    trace_id = str(
        extra.get("active_internal_request_trace_id")
        or extra.get("internal_request_trace_id")
        or ""
    ).strip()
    try:
        return resolve_atlasclaw_instance_request(
            instance_name=instance_name,
            instance_config=instance,
            request_session_token=request_session_token,
            runtime_cookie=str(
                extra.get("provider_cookie_token") or ""
            ).strip(),
            runtime_sso_token=str(
                extra.get("provider_sso_token") or ""
            ).strip(),
            request_session_only=request_cookie_only,
            subject=subject,
            actor_type="robot" if robot_profile else "user",
            client_id=robot_profile or None,
            trace_id=trace_id or None,
        )
    except (SmartCmpError, ValueError) as error:
        raise AtlasClawAdapterError(str(error)) from error


async def execute(
    ctx: Any,
    operation: Callable[[SmartCmpClient, Any], Awaitable[ResultT]],
    operation_input: Any,
    *,
    request_cookie_only: bool = False,
) -> ResultT:
    """Execute one SmartCMP Provider operation for an AtlasClaw Tool call."""

    result, _request = await execute_with_request(
        ctx,
        operation,
        operation_input,
        request_cookie_only=request_cookie_only,
    )
    return result


async def execute_with_request(
    ctx: Any,
    operation: Callable[[SmartCmpClient, Any], Awaitable[ResultT]],
    operation_input: Any,
    *,
    request_cookie_only: bool = False,
) -> tuple[ResultT, ResolvedSmartCmpRequest]:
    """Execute one Provider operation and retain its selected instance for projection.

    The returned request is used only by the AtlasClaw adapter to derive UI
    links. Authentication is resolved exactly once for the operation.
    """

    request = await resolve_selected_provider_request(
        ctx,
        request_cookie_only=request_cookie_only,
    )
    async with SmartCmpClient(request) as client:
        result = await operation(client, operation_input)
    return result, request


async def resolve_selected_provider_request(
    ctx: Any,
    *,
    request_cookie_only: bool = False,
) -> ResolvedSmartCmpRequest:
    """Resolve authentication off-loop because credential mode may log in."""

    return await asyncio.to_thread(
        selected_provider_request,
        ctx,
        request_cookie_only=request_cookie_only,
    )


def tool_result(
    value: BaseModel | Mapping[str, Any] | list[Any] | tuple[Any, ...] | Any,
    *,
    summary: str,
    internal: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert one typed Provider result into the AtlasClaw Tool result contract.

    The complete structured payload is retained both as ordinary result fields
    and compact ``_internal`` workflow metadata. The visible output intentionally
    stays presentation-only and does not reimplement SmartCMP domain rules.
    """

    payload = _strip_mcp_available_operations(_json_value(value))
    structured = payload if isinstance(payload, dict) else {"data": payload}
    internal_payload = (
        _strip_mcp_available_operations(dict(internal))
        if internal is not None
        else structured
    )
    return {
        "success": True,
        "output": summary,
        "_internal": json.dumps(
            internal_payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        **structured,
    }


def _strip_mcp_available_operations(value: Any) -> Any:
    """Remove MCP Tool-call hints from the independent AtlasClaw protocol."""

    if isinstance(value, dict):
        return {
            key: _strip_mcp_available_operations(item)
            for key, item in value.items()
            if key != "available_operations"
        }
    if isinstance(value, list):
        return [_strip_mcp_available_operations(item) for item in value]
    return value


def tool_error(error: Exception) -> dict[str, Any]:
    """Convert an expected adapter, validation, or Provider failure for AtlasClaw."""

    return {
        "success": False,
        "error": str(error),
        "output": str(error),
    }


def split_values(value: str | list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Normalize Tool string-or-list identifiers without changing their order."""

    if isinstance(value, str):
        values = value.replace(",", " ").split()
    else:
        values = [str(item) for item in value]
    return tuple(item.strip() for item in values if item.strip())


def embedded_object_id(ctx: Any, *, expected_object_type: str) -> str | None:
    """Return the immutable current-page object ID, if this is an embedded call."""

    deps = getattr(ctx, "deps", None)
    extra = getattr(deps, "extra", None)
    context = extra.get("context") if isinstance(extra, dict) else None
    turn_context = (
        context.get("turn_context") if isinstance(context, dict) else None
    )
    if turn_context is None:
        return None
    if not isinstance(turn_context, dict):
        raise AtlasClawAdapterError(
            "This tool requires a valid SmartCMP page Context."
        )
    turn_object = turn_context.get("object")
    default_skill = turn_context.get("default_skill")
    if not isinstance(turn_object, dict) or not isinstance(default_skill, dict):
        raise AtlasClawAdapterError(
            "This tool requires a valid SmartCMP page Context."
        )
    provider_type = str(default_skill.get("provider_type") or "").strip()
    object_type = str(turn_object.get("type") or "").strip()
    object_id = str(turn_object.get("id") or "").strip().lower()
    selected_instance = (
        str(extra.get("provider_instance_name") or "").strip()
        if isinstance(extra, dict)
        else ""
    )
    if (
        provider_type != "smartcmp"
        or object_type != expected_object_type
        or not object_id
        or str(default_skill.get("provider_instance") or "").strip()
        != selected_instance
    ):
        raise AtlasClawAdapterError(
            f"This tool can only read the current {expected_object_type} "
            "page object."
        )
    return object_id


def _json_value(value: Any) -> Any:
    """Return a JSON-compatible value without leaking arbitrary object state."""

    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value
