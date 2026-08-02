"""Focused contracts for SmartCMP Provider page-context reads."""

from __future__ import annotations

import asyncio

import httpx

from smartcmp_provider.auth.resolver import resolve_provided_request
from smartcmp_provider.operations.context_objects import (
    CATALOG_ENTITY_CLASS,
    has_instance_permission,
    list_current_pending_approvals,
    read_alert,
    read_approval,
    read_catalog,
    read_cost_recommendation,
    read_request,
    read_resource,
)
from smartcmp_provider.transport.client import SmartCmpClient


def test_context_reads_use_explicit_provider_operations_and_current_user_acl() -> None:
    """Keep endpoint/auth behavior in the Provider while adapters only project results."""

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path.endswith("/acl/queryCurrentUserPermissions"):
            payload: object = [
                {
                    "entityClass": {
                        "className": CATALOG_ENTITY_CLASS,
                        "instanceId": "CATALOG-1",
                    },
                    "permissions": [{"id": "READ"}],
                }
            ]
        elif path.endswith("/generic-request/current-activity-approval"):
            payload = {"content": [{"workflowId": "RES20260719000004"}]}
        else:
            payload = {"id": path.rsplit("/", 1)[-1]}
        return httpx.Response(200, json=payload, request=request)

    request = resolve_provided_request(
        instance_name="cmp-test",
        base_url="https://cmp.example.com",
        subject="atlasclaw-user",
        auth_type="cookie",
        credential_value="request-session",
        trace_id="context-read",
    )

    async def invoke() -> tuple[object, ...]:
        async with SmartCmpClient(
            request,
            transport=httpx.MockTransport(handler),
        ) as client:
            return (
                await read_alert(client, "alert-1"),
                await read_cost_recommendation(client, "recommendation-1"),
                await read_approval(client, "approval-1"),
                await list_current_pending_approvals(
                    client,
                    "RES20260719000004",
                ),
                await read_catalog(client, "CATALOG-1"),
                await read_request(client, "request-1"),
                await read_resource(client, "resource-1"),
                await has_instance_permission(
                    client,
                    CATALOG_ENTITY_CLASS,
                    "CATALOG-1",
                    "READ",
                ),
            )

    results = asyncio.run(invoke())

    assert results[-1] is True
    assert results[3] == ({"workflowId": "RES20260719000004"},)
    assert [request.method for request in seen] == ["GET"] * 8
    assert [request.url.path for request in seen] == [
        "/platform-api/alarm-alert/alert-1",
        "/platform-api/compliance-policies/violations/recommendation-1",
        "/platform-api/approval/approval-1",
        "/platform-api/generic-request/current-activity-approval",
        "/platform-api/catalogs/CATALOG-1",
        "/platform-api/generic-request/request-1",
        "/platform-api/nodes/resource-1",
        "/platform-api/acl/queryCurrentUserPermissions",
    ]
    pending_params = seen[3].url.params
    assert pending_params["searchValues"] == "RES20260719000004"
    acl_params = seen[-1].url.params
    assert acl_params["entityClassNames"] == CATALOG_ENTITY_CLASS
    assert acl_params["entityInstanceIds"] == "CATALOG-1"
