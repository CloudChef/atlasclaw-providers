# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Fail-closed SmartCMP Provider bridge and projections for embedded page context."""

from __future__ import annotations

import re
import uuid
from types import TracebackType
from typing import Any, Protocol

from _atlasclaw_adapter import (
    AtlasClawAdapterError,
    resolve_selected_provider_request,
)
from smartcmp_provider.auth.models import ResolvedSmartCmpRequest
from smartcmp_provider.errors import SmartCmpError
from smartcmp_provider.operations.context_objects import (
    CATALOG_ENTITY_CLASS,
    RESOURCE_ENTITY_CLASS,
    has_instance_permission,
    list_current_pending_approvals,
    read_alert,
    read_approval,
    read_catalog,
    read_component_definition,
    read_cost_recommendation,
    read_form_definition,
    read_optimization_policy,
    read_request,
    read_resource,
    read_script_definition,
)
from smartcmp_provider.transport.client import SmartCmpClient


class ContextConfigError(RuntimeError):
    """Raised before Provider I/O when request-user context configuration is invalid."""


class ContextReader(Protocol):
    """Define the identity-scoped Provider reads required by the page adapter."""

    @property
    def ui_base_url(self) -> str:
        """Return the selected SmartCMP browser base URL for action links."""

    async def read_form_definition(self, object_id: str) -> dict[str, Any]:
        """Read one exact form definition."""

    async def read_script_definition(self, object_id: str) -> dict[str, Any]:
        """Read one exact script definition."""

    async def read_optimization_policy(self, object_id: str) -> dict[str, Any]:
        """Read one exact optimization policy."""

    async def read_component_definition(self, object_id: str) -> dict[str, Any]:
        """Read one exact blueprint component."""

    async def read_alert(self, object_id: str) -> dict[str, Any]:
        """Read one exact alert."""

    async def read_cost_recommendation(self, object_id: str) -> dict[str, Any]:
        """Read one exact cost recommendation."""

    async def read_approval(self, object_id: str) -> dict[str, Any]:
        """Read one exact approval."""

    async def list_current_pending_approvals(
        self,
        workflow_id: str,
    ) -> tuple[dict[str, Any], ...]:
        """List current-user pending approvals for one Request ID."""

    async def read_catalog(self, object_id: str) -> dict[str, Any]:
        """Read one exact catalog."""

    async def read_request(self, object_id: str) -> dict[str, Any]:
        """Read one exact generic request."""

    async def read_resource(self, object_id: str) -> dict[str, Any]:
        """Read one exact resource."""

    async def has_instance_permission(
        self,
        entity_class: str,
        entity_id: str,
        permission: str,
    ) -> bool:
        """Check one current-principal instance permission."""


_CATALOG_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")
_REQUEST_ID = re.compile(r"^[A-Z]{3}\d{14}$")


class SmartCmpProviderContextReader:
    """Execute page-context reads through one resolved SmartCMP Provider request."""

    def __init__(self, request: ResolvedSmartCmpRequest) -> None:
        """Bind all reads to one immutable current-user credential and instance."""

        self._request = request
        self._client: SmartCmpClient | None = None

    async def __aenter__(self) -> SmartCmpProviderContextReader:
        """Open one HTTP connection pool shared by this context resolution."""

        self._client = SmartCmpClient(self._request)
        await self._client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the request-scoped HTTP connection pool."""

        if self._client is not None:
            await self._client.__aexit__(exc_type, exc, traceback)
            self._client = None

    @property
    def ui_base_url(self) -> str:
        """Return the SmartCMP Provider-derived browser base URL used in action metadata."""

        return self._request.context.instance.ui_base_url

    async def read_form_definition(self, object_id: str) -> dict[str, Any]:
        """Read one exact form definition through SmartCMP Provider."""

        return await read_form_definition(self._require_client(), object_id)

    async def read_script_definition(self, object_id: str) -> dict[str, Any]:
        """Read one exact script definition through SmartCMP Provider."""

        return await read_script_definition(self._require_client(), object_id)

    async def read_optimization_policy(self, object_id: str) -> dict[str, Any]:
        """Read one exact optimization policy through SmartCMP Provider."""

        return await read_optimization_policy(self._require_client(), object_id)

    async def read_component_definition(self, object_id: str) -> dict[str, Any]:
        """Read one exact component definition through SmartCMP Provider."""

        return await read_component_definition(self._require_client(), object_id)

    async def read_alert(self, object_id: str) -> dict[str, Any]:
        """Read one exact alert through SmartCMP Provider."""

        return await read_alert(self._require_client(), object_id)

    async def read_cost_recommendation(self, object_id: str) -> dict[str, Any]:
        """Read one exact cost recommendation through SmartCMP Provider."""

        return await read_cost_recommendation(self._require_client(), object_id)

    async def read_approval(self, object_id: str) -> dict[str, Any]:
        """Read one exact approval through SmartCMP Provider."""

        return await read_approval(self._require_client(), object_id)

    async def list_current_pending_approvals(
        self,
        workflow_id: str,
    ) -> tuple[dict[str, Any], ...]:
        """List current-user pending approvals for one Request ID through SmartCMP Provider."""

        return await list_current_pending_approvals(
            self._require_client(),
            workflow_id,
        )

    async def read_catalog(self, object_id: str) -> dict[str, Any]:
        """Read one exact catalog through SmartCMP Provider."""

        return await read_catalog(self._require_client(), object_id)

    async def read_request(self, object_id: str) -> dict[str, Any]:
        """Read one exact generic request through SmartCMP Provider."""

        return await read_request(self._require_client(), object_id)

    async def read_resource(self, object_id: str) -> dict[str, Any]:
        """Read one exact resource through SmartCMP Provider."""

        return await read_resource(self._require_client(), object_id)

    async def has_instance_permission(
        self,
        entity_class: str,
        entity_id: str,
        permission: str,
    ) -> bool:
        """Check one current-principal instance permission through SmartCMP Provider."""

        return await has_instance_permission(
            self._require_client(),
            entity_class,
            entity_id,
            permission,
        )

    def _require_client(self) -> SmartCmpClient:
        """Return the active request client or reject use outside its scope."""

        if self._client is None:
            raise RuntimeError("Context reader must be used inside an async scope.")
        return self._client


async def load_context_reader_from_context(ctx: Any) -> SmartCmpProviderContextReader:
    """Load the current Host user from an AtlasClaw execution context.

    Args:
        ctx: Request-scoped AtlasClaw context containing the selected Provider
            instance and current Host cookies.

    Returns:
        A reader bound to the current SmartCMP browser session.

    Raises:
        ContextConfigError: If the current request has no usable SmartCMP session.
    """

    try:
        request = await resolve_selected_provider_request(
            ctx,
            request_cookie_only=True,
        )
    except AtlasClawAdapterError as error:
        raise ContextConfigError(str(error)) from error
    return SmartCmpProviderContextReader(request)


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
