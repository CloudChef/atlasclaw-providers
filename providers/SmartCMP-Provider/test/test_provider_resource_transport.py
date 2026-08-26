"""Focused tests for request-scoped resource transport and operations."""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

PROVIDER_ROOT = Path(__file__).resolve().parents[1]
PROVIDER_SRC = PROVIDER_ROOT / "src"
_ORIGINAL_PATH = list(sys.path)
_ORIGINAL_PROVIDER_MODULES = {
    name: module
    for name, module in sys.modules.items()
    if name == "smartcmp_provider" or name.startswith("smartcmp_provider.")
}
try:
    if str(PROVIDER_SRC) not in sys.path:
        sys.path.insert(0, str(PROVIDER_SRC))

    from smartcmp_provider.auth.models import SmartCmpAuthenticationContext
    from smartcmp_provider.auth.resolver import (
        resolve_integration_request,
        resolve_provided_request,
    )
    from smartcmp_provider.auth.login import login_with_password
    from smartcmp_provider.errors import (
        SmartCmpAuthenticationError,
        SmartCmpConflictError,
        SmartCmpNotFoundError,
        SmartCmpPermissionError,
        SmartCmpRateLimitError,
        SmartCmpTimeoutError,
        SmartCmpUnknownOutcomeError,
        SmartCmpUpstreamError,
        SmartCmpValidationError,
    )
    from smartcmp_provider.models.catalogs import (
        CatalogDetailQuery,
        CatalogListQuery,
        FlavorQuery,
        ImageQuery,
        ResourceBundleQuery,
    )
    from smartcmp_provider.models.requests import (
        RequestActorIdentity,
        RequestStatusQuery,
        RequestSubmissionInput,
    )
    from smartcmp_provider.models.operations import (
        ResourceActionInput,
        ResourceActionTarget,
    )
    from smartcmp_provider.models.resources import (
        ResourceDetailQuery,
        ResourceEvidenceQuery,
        ResourceListQuery,
        ResourceOperationsQuery,
    )
    from smartcmp_provider.operations.resources import (
        get_resource_detail,
        load_resource_evidence,
        list_resources,
    )
    from smartcmp_provider.operations.catalogs import (
        _resolve_option_selection,
        get_catalog_detail,
        list_catalogs,
        list_flavors,
        list_images,
        list_resource_bundles,
    )
    from smartcmp_provider.operations.requests import (
        get_request_status,
        submit_request,
    )
    from smartcmp_provider.operations.resource_actions import execute_resource_action
    from smartcmp_provider.services.resources import (
        get_resource_operations_view,
    )
    from smartcmp_provider.transport.client import SmartCmpClient
    from smartcmp_provider.instance import SmartCmpInstance
finally:
    for _MODULE_NAME in list(sys.modules):
        if _MODULE_NAME == "smartcmp_provider" or _MODULE_NAME.startswith(
            "smartcmp_provider."
        ):
            sys.modules.pop(_MODULE_NAME, None)
    sys.modules.update(_ORIGINAL_PROVIDER_MODULES)
    sys.path[:] = _ORIGINAL_PATH


def make_request(
    *,
    instance_name: str,
    base_url: str,
    user_id: str,
    token: str,
    timeout: int = 60,
    robot_profile: str = "",
):
    return resolve_provided_request(
        instance_name=instance_name,
        base_url=base_url,
        subject=user_id,
        actor_type="robot" if robot_profile else "user",
        client_id=robot_profile or None,
        auth_type=(
            "provider_token"
            if robot_profile
            else "user_token"
            if token.startswith("cmp_tk_")
            else "cookie"
        ),
        credential_value=token,
        timeout_seconds=timeout,
        trace_id=f"run-{user_id}",
    )


@pytest.mark.parametrize(
    ("field_type", "option_id", "expected_value"),
    [
        ("boolean", "false", False),
        ("integer", "7", 7),
        ("array", "security-group-1", ["security-group-1"]),
    ],
)
def test_sole_option_auto_selection_preserves_field_type(
    field_type: str,
    option_id: str,
    expected_value: Any,
) -> None:
    """A sole returned ID follows the same type conversion as user input."""

    field = {
        "visible": True,
        "editable": True,
        "ask": True,
        "type": field_type,
        "value": None,
        "options": [{"id": option_id}],
    }
    selected_values: dict[str, Any] = {}

    pending = _resolve_option_selection(
        field,
        explicitly_selected=False,
        selected_values=selected_values,
        field_names=("field",),
    )

    assert pending is False
    assert field["value"] == expected_value
    assert selected_values["field"] == expected_value


def test_integration_resolver_owns_configured_and_oauth_credentials():
    configured_auth = SmartCmpAuthenticationContext.configured(
        subject="agent-user",
        actor_type="user",
        auth_type="user_token",
        credential_reference="SMARTCMP_TEST_TOKEN",
    )
    configured = resolve_integration_request(
        instance=SmartCmpInstance(
            name="cmp",
            base_url="https://cmp.example.com",
        ),
        authentication=configured_auth,
        trace_id="trace-configured",
        environ={"SMARTCMP_TEST_TOKEN": "cmp_tk_configured_token"},
    )
    oauth_auth = SmartCmpAuthenticationContext.oauth(
        subject="oauth-user",
        actor_type="user",
        access_token="oauth-access-token",
        scopes=frozenset({"smartcmp.read"}),
    )
    oauth = resolve_integration_request(
        instance=SmartCmpInstance(
            name="cmp",
            base_url="https://cmp.example.com",
        ),
        authentication=oauth_auth,
        trace_id="trace-oauth",
    )

    assert configured.credential.headers()["Authorization"] == (
        "Bearer cmp_tk_configured_token"
    )
    assert oauth.credential.headers()["Authorization"] == (
        "Bearer oauth-access-token"
    )
    assert oauth.context.principal.subject == "oauth-user"
    assert oauth.context.principal.scopes == frozenset({"smartcmp.read"})
    assert "cmp_tk_configured_token" not in repr(configured_auth)
    assert "oauth-access-token" not in repr(oauth_auth)


def test_provider_supports_full_atlasclaw_cookie_authentication():
    authentication = SmartCmpAuthenticationContext.provided(
        subject="atlasclaw-user",
        actor_type="user",
        auth_type="cookie",
        credential_value=(
            "tenant_id=tenant-a; "
            "CloudChef-Authenticate=request-cookie-token; session=abc"
        ),
    )

    request = resolve_integration_request(
        instance=SmartCmpInstance(
            name="cmp",
            base_url="https://cmp.example.com",
        ),
        authentication=authentication,
        trace_id="trace-cookie",
    )

    assert request.credential.kind == "cookie"
    assert request.credential.headers() == {
        "CloudChef-Authenticate": "request-cookie-token",
        "Cookie": (
            "tenant_id=tenant-a; "
            "CloudChef-Authenticate=request-cookie-token; session=abc"
        ),
        "Content-Type": "application/json; charset=utf-8",
    }


def test_provided_context_supports_webhook_robot_provider_token():
    request = resolve_provided_request(
        instance_name="cmp",
        base_url="https://cmp.example.com",
        subject="webhook-smartcmp-preapproval",
        actor_type="robot",
        client_id="preapproval_bot",
        auth_type="provider_token",
        credential_value="robot-profile-token",
        trace_id="trace-webhook-robot",
    )

    assert request.context.principal.actor_type == "robot"
    assert request.context.principal.client_id == "preapproval_bot"
    assert request.context.trace_id == "trace-webhook-robot"
    assert request.credential.kind == "bearer"
    assert request.credential.headers()["Authorization"] == (
        "Bearer robot-profile-token"
    )


def test_concurrent_users_and_instances_keep_headers_and_urls_isolated():
    session_request = make_request(
        instance_name="cmp-a",
        base_url="https://cmp-a.example",
        user_id="user-a",
        token="session-a",
    )
    bearer_request = make_request(
        instance_name="cmp-b",
        base_url="https://cmp-b.example/custom",
        user_id="user-b",
        token="cmp_tk_robot_b",
    )
    seen: list[tuple[str, str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0)
        seen.append(
            (
                str(request.url),
                request.headers.get("CloudChef-Authenticate", ""),
                request.headers.get("Authorization", ""),
            )
        )
        return httpx.Response(200, json={"content": []}, request=request)

    transport = httpx.MockTransport(handler)

    async def invoke(resolved_request):
        async with SmartCmpClient(resolved_request, transport=transport) as client:
            return await list_resources(client, ResourceListQuery())

    async def invoke_both():
        return await asyncio.gather(
            invoke(session_request),
            invoke(bearer_request),
        )

    session_result, bearer_result = asyncio.run(invoke_both())

    assert session_result.items == ()
    assert bearer_result.items == ()
    assert set(seen) == {
        (
            "https://cmp-a.example/platform-api/nodes/search"
            "?page=1&size=20&queryValue=&sort=createdDate%2Cdesc"
            "&relation=AND&fullMatch=false&category=-1",
            "session-a",
            "",
        ),
        (
            "https://cmp-b.example/custom/platform-api/nodes/search"
            "?page=1&size=20&queryValue=&sort=createdDate%2Cdesc"
            "&relation=AND&fullMatch=false&category=-1",
            "",
            "Bearer cmp_tk_robot_b",
        ),
    }


def test_list_resources_projects_compact_rows_before_attaching_operations():
    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "id": "res-1",
                        "name": "vm-a",
                        "status": "started",
                        "resourceType": "resource.iaas.machine",
                        "componentType": "machine",
                        "osType": "linux",
                        "osDescription": "Linux",
                        "isAgentInstalled": True,
                        "monitorEnabled": True,
                        "externalId": "vm-1",
                        "nodeInstanceId": "node-1",
                        "cloudEntry": {"large": "unused"},
                        "properties": {"large": "unused"},
                        "addresses": [{"ip": "192.0.2.1"}],
                    }
                ],
                "totalElements": 1,
            },
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            return await list_resources(client, ResourceListQuery())

    result = asyncio.run(invoke())

    assert result.total == 1
    assert set(result.items[0]) == {
        "id",
        "name",
        "resourceType",
        "componentType",
        "status",
        "osType",
        "osDescription",
        "isAgentInstalled",
        "monitorEnabled",
        "externalId",
        "nodeInstanceId",
        "available_operations",
    }
    assert result.items[0]["id"] == "res-1"
    assert result.items[0]["name"] == "vm-a"
    assert result.items[0]["status"] == "started"


def test_resource_operations_keep_only_enabled_agent_supported_actions():
    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )
    seen: list[tuple[str, str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, str(request.url), bytes(request.content)))
        if request.method == "GET" and "fullMatch=true" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "content": [
                        {"id": "res-1", "name": "vm-a", "status": "started"},
                    ],
                    "totalElements": 1,
                },
                request=request,
            )
        if request.method == "PATCH":
            return httpx.Response(
                200,
                json={"id": "res-1", "name": "vm-a", "status": "started"},
                request=request,
            )
        if request.url.path.endswith("/resource-actions"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "refresh",
                        "name": "REFRESH_RESOURCE",
                        "enabled": True,
                        "parameters": "{}",
                    },
                    {
                        "id": "restart",
                        "name": "RESTART",
                        "enabled": True,
                        "parameters": '{"legacyMetadata": true}',
                        "inputsForm": {"legacyField": "ignored"},
                    },
                    {
                        "id": "suspend",
                        "name": "SUSPEND",
                        "enabled": True,
                        "parameters": None,
                    },
                    {
                        "id": "stop",
                        "name": "STOP",
                        "enabled": True,
                        "parameters": "{}",
                    },
                    {
                        "id": "tear_down_in_resource",
                        "name": "upstream-remove-label",
                        "nameZh": "",
                        "enabled": True,
                        "parameters": None,
                    },
                    {
                        "id": "start",
                        "name": "START",
                        "enabled": True,
                        "webOperation": True,
                    },
                    {
                        "id": "tear-down-in-resource",
                        "name": "NEAR_ALIAS",
                        "enabled": True,
                        "parameters": "{}",
                    },
                ],
                request=request,
            )
        return httpx.Response(200, json={"content": []}, request=request)

    transport = httpx.MockTransport(handler)

    async def invoke():
        async with SmartCmpClient(request_scope, transport=transport) as client:
            detail = await get_resource_detail(
                client,
                ResourceDetailQuery(resource_name="vm-a"),
            )
            operations = await get_resource_operations_view(
                client,
                ResourceOperationsQuery(
                    category="virtual-machines",
                    resource_id=detail.resource_id,
                ),
            )
            return detail, operations

    detail_result, operation_result = asyncio.run(invoke())

    assert detail_result.resource_id == "res-1"
    assert detail_result.payload["name"] == "vm-a"
    assert [item.id for item in operation_result.operations] == [
        "refresh",
        "restart",
        "suspend",
        "stop",
        "tear_down_in_resource",
    ]
    tear_down = operation_result.operations[-1]
    assert (tear_down.name, tear_down.name_zh, tear_down.display_name) == (
        "Tear Down",
        "删除",
        "删除",
    )
    assert seen[0][0] == "GET"
    assert "queryValue=vm-a" in seen[0][1]
    assert seen[1] == (
        "PATCH",
        "https://cmp.example/platform-api/nodes/res-1/view",
        b"",
    )
    assert seen[2][1].endswith(
        "/platform-api/nodes/virtual-machines/res-1/resource-actions"
    )


def test_transport_maps_timeout_without_exposing_credential():
    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="never-log-this-token",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("upstream slow", request=request)

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            await client.request_json("GET", "/nodes/search")

    with pytest.raises(SmartCmpTimeoutError) as exc_info:
        asyncio.run(invoke())

    assert exc_info.value.trace_id == "run-user-a"
    assert "never-log-this-token" not in str(exc_info.value)








@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (400, SmartCmpValidationError),
        (401, SmartCmpAuthenticationError),
        (403, SmartCmpPermissionError),
        (404, SmartCmpNotFoundError),
        (409, SmartCmpConflictError),
        (422, SmartCmpValidationError),
        (429, SmartCmpRateLimitError),
        (503, SmartCmpUpstreamError),
    ],
)
def test_transport_maps_http_statuses_to_provider_errors(status_code, error_type):
    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="never-log-this-token",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={"message": "upstream rejected request"},
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            await client.request_json("GET", "/nodes/search")

    with pytest.raises(error_type) as exc_info:
        asyncio.run(invoke())

    assert exc_info.value.trace_id == "run-user-a"
    assert f"HTTP {status_code}" in str(exc_info.value)
    assert "never-log-this-token" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("response_kwargs", "expected_message"),
    [
        ({"text": "not-json"}, "invalid JSON"),
        (
            {
                "json": {
                    "success": False,
                    "code": "CMP_REJECTED",
                    "message": "business rule rejected request",
                }
            },
            "SmartCMP business error CMP_REJECTED",
        ),
    ],
)
def test_transport_maps_invalid_json_and_business_failures(
    response_kwargs,
    expected_message,
):
    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="never-log-this-token",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, **response_kwargs)

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            await client.request_json("GET", "/nodes/search")

    with pytest.raises(SmartCmpUpstreamError) as exc_info:
        asyncio.run(invoke())

    assert exc_info.value.trace_id == "run-user-a"
    assert expected_message in str(exc_info.value)
    assert "never-log-this-token" not in str(exc_info.value)


def test_transport_reports_empty_connection_error_with_actionable_context():
    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="never-log-this-token",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("", request=request)

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            await client.request_json("GET", "/nodes/search")

    with pytest.raises(SmartCmpUpstreamError) as exc_info:
        asyncio.run(invoke())

    message = str(exc_info.value)
    assert message == (
        "Unable to connect to the configured SmartCMP service (ConnectError)."
    )
    assert "never-log-this-token" not in message


@pytest.mark.parametrize(
    ("message", "secret"),
    [
        ("Authorization: Bearer cmp_tk_secret", "cmp_tk_secret"),
        ("password=two word secret", "two word secret"),
    ],
)
def test_transport_redacts_complete_unquoted_credential_values(message, secret):
    """Unquoted credentials remain secret even when their value contains spaces."""

    rendered = SmartCmpClient.sanitize_error_text(message)

    assert secret not in rendered
    assert rendered.endswith("[REDACTED]")




def test_transport_uses_smaller_deadline_and_rejects_expired_deadline():
    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
        timeout=60,
    )
    remaining_timeout: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        remaining_timeout.append(request.extensions["timeout"]["read"])
        return httpx.Response(200, json={"content": []}, request=request)

    active_context = replace(
        request_scope.context,
        deadline=datetime.now(UTC) + timedelta(seconds=2),
    )
    active_request = replace(request_scope, context=active_context)

    async def invoke_active():
        async with SmartCmpClient(
            active_request,
            transport=httpx.MockTransport(handler),
        ) as client:
            await client.request_json("GET", "/nodes/search")

    asyncio.run(invoke_active())

    assert len(remaining_timeout) == 1
    assert 0 < remaining_timeout[0] <= 2

    expired_context = replace(
        request_scope.context,
        deadline=datetime.now(UTC) - timedelta(seconds=1),
    )
    expired_request = replace(request_scope, context=expired_context)

    async def invoke_expired():
        async with SmartCmpClient(
            expired_request,
            transport=httpx.MockTransport(handler),
        ) as client:
            await client.request_json("GET", "/nodes/search")

    with pytest.raises(SmartCmpTimeoutError, match="deadline expired") as exc_info:
        asyncio.run(invoke_expired())

    assert exc_info.value.trace_id == "run-user-a"
    assert len(remaining_timeout) == 1


def test_catalog_list_returns_compact_summaries():
    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )
    markdown = """
# Request Parameter Instructions

catalog:
  component_type: resource.iaas.machine.instance.abstract
resource_specs:
- node: Compute
  type: cloudchef.nodes.Compute
  runtime_fields:
    resolver: resource_bundle_placement
  params:
    computeProfileName:
      required: true

# Request Instructions

Collect the VM shape before submission.
""".strip()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/catalogs/catalog-markdown"):
            return httpx.Response(
                200,
                json={
                    "id": "catalog-markdown",
                    "name": "Linux from Markdown",
                    "serviceCategory": "CLOUD_COMPONENT_SERVICE",
                    "status": "PUBLISHED",
                    "instructions": markdown,
                },
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "id": "catalog-markdown",
                        "name": "Linux from Markdown",
                        "serviceCategory": "CLOUD_COMPONENT_SERVICE",
                        "instructions": markdown,
                    },
                    {
                        "id": "catalog-blueprint",
                        "name": "Linux legacy",
                        "serviceCategory": "CLOUD_COMPONENT_SERVICE",
                        "instructions": "",
                        "blueprint": {
                            "mainYaml": (
                                "node_templates:\n"
                                "  LegacyCompute:\n"
                                "    type: cloudchef.nodes.Compute\n"
                            )
                        },
                    },
                ],
                "totalElements": 2,
            },
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            listed = await list_catalogs(client, CatalogListQuery())
            exact = await list_catalogs(
                client,
                CatalogListQuery(catalog_id="catalog-markdown"),
            )
            return listed, exact

    result, exact = asyncio.run(invoke())

    assert result.total == 2
    assert set(result.catalogs[0]) == {
        "index",
        "id",
        "name",
        "sourceKey",
        "serviceCategory",
        "status",
        "available_operations",
    }
    assert result.catalogs[0]["name"] == "Linux from Markdown"
    assert [
        operation["operation_id"]
        for operation in result.catalogs[0]["available_operations"]
    ] == ["view_detail", "request"]
    assert exact.catalogs == (result.catalogs[0],)


def test_catalog_detail_includes_normalized_request_metadata() -> None:
    """Selected catalog details retain parsed request and preapproval metadata."""

    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )
    markdown = """
# Request Parameter Instructions

catalog:
  component_type: resource.iaas.machine.instance.abstract
resource_specs:
- node: Compute
  type: cloudchef.nodes.Compute
  runtime_fields:
    resolver: resource_bundle_placement

# Preapproval Instructions

Require an owner review.
""".strip()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/catalogs/catalog-1")
        return httpx.Response(
            200,
            json={
                "id": "catalog-1",
                "name": "Linux VM",
                "serviceCategory": "CLOUD_COMPONENT_SERVICE",
                "instructions": markdown,
            },
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            return await get_catalog_detail(
                client,
                CatalogDetailQuery(catalog_id="catalog-1"),
            )

    result = asyncio.run(invoke())

    assert "catalog" not in result.model_dump(mode="json")
    assert result.metadata["componentType"] == (
        "resource.iaas.machine.instance.abstract"
    )
    assert result.metadata["node"] == "Compute"
    assert result.metadata["type"] == "cloudchef.nodes.Compute"
    assert result.metadata["instructions"]["resourceSpecs"][0]["node"] == "Compute"
    assert result.metadata["instructions"]["resourceSpecs"][0][
        "runtime_fields"
    ] == {"resolver": "resource_bundle_placement"}
    assert result.metadata["preApprovalInstructions"] == "Require an owner review."


@pytest.mark.parametrize(
    ("cloud_entry_type", "expected_resource_type"),
    [
        (
            "yacmp:cloudentry:type:generic-cloud:terraform_enterprise",
            "yacmp:cloudentry:type:generic-cloud::images",
        ),
        (
            "yacmp:cloudentry:type:generic-cloud:tencentcloud",
            "yacmp:cloudentry:type:generic-cloud::images",
        ),
        (
            "yacmp:cloudentry:type:vsphere",
            "yacmp:cloudentry:type:vsphere::images",
        ),
    ],
)
def test_image_query_uses_cmp_cloud_family_resource_type(
    cloud_entry_type: str,
    expected_resource_type: str,
) -> None:
    """Generic-Cloud subtypes share CMP image dispatch without changing others."""

    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )
    submitted_payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        submitted_payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=[
                {
                    "id": "provider-image-id",
                    "name": "Selected image",
                    "properties": {
                        "extra": {"templateId": "request-template-id"}
                    },
                }
            ],
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            return await list_images(
                client,
                ImageQuery(
                    resource_bundle_id="resource-bundle-1",
                    logic_template_id="logical-template-1",
                    cloud_entry_type=cloud_entry_type,
                ),
            )

    result = asyncio.run(invoke())

    assert len(submitted_payloads) == 1
    assert submitted_payloads[0]["cloudResourceType"] == expected_resource_type
    assert result.items[0]["templateId"] == "request-template-id"


def test_resource_bundle_list_returns_request_identity_only() -> None:
    """Filter by exact facets, fail closed, and omit upstream pool internals."""

    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )

    tag_only_markdown = """
# Request Parameter Instructions

catalog:
  component_type: resource.iaas.machine.instance.abstract
resource_specs:
- node: Compute
  type: cloudchef.nodes.Compute
  resourceBundleTags:
    required: true
    ask: true
  resourceBundleId:
    required: true
    when: params.placementMode == 'dedicated'
""".strip()
    runtime_only_markdown = """
# Request Parameter Instructions

catalog:
  component_type: resource.iaas.machine.instance.abstract
resource_specs:
- node: Compute
  type: cloudchef.nodes.Compute
  runtime_fields:
    resolver: resource_bundle_placement
""".strip()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/catalogs/catalog-1"):
            return httpx.Response(
                200,
                json={"id": "catalog-1", "instructions": tag_only_markdown},
                request=request,
            )
        if request.url.path.endswith("/catalogs/catalog-runtime"):
            return httpx.Response(
                200,
                json={
                    "id": "catalog-runtime",
                    "instructions": runtime_only_markdown,
                },
                request=request,
            )
        if request.url.path.endswith("/catalogs/catalog-invalid"):
            return httpx.Response(
                200,
                json={"id": "catalog-invalid", "instructions": ""},
                request=request,
            )
        assert request.url.path.endswith("/resource-bundles")
        facets = request.url.params.get_list("facets")
        if facets == ["FACET_ENV:none"]:
            return httpx.Response(200, json=[], request=request)
        assert facets in (
            [],
            ["FACET_ENV:dev"],
            ["FACET_ENV:dev", "FACET_OWNER:platform"],
        )
        return httpx.Response(
            200,
            json=[
                {
                    "id": "resource-bundle-1",
                    "name": "vSphere pool",
                    "cloudEntryTypeId": "yacmp:cloudentry:type:vsphere",
                    "networks": [{"id": "network-1", "raw": "provider-only"}],
                    "storageTypes": [{"id": "storage-1"}],
                    "stats": {"cpu": 42},
                },
                {
                    "id": "resource-bundle-2",
                    "name": "Later matching pool",
                    "cloudEntryTypeId": "yacmp:cloudentry:type:vsphere",
                },
            ],
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            result = await list_resource_bundles(
                client,
                ResourceBundleQuery(
                    business_group_id="business-group-1",
                    component_type="resource.iaas.machine.instance.abstract",
                    node_type="cloudchef.nodes.Compute",
                    catalog_id="catalog-1",
                    node_template_name="Compute",
                    resource_bundle_tags=("FACET_ENV:dev", "FACET_OWNER:platform"),
                ),
            )
            with pytest.raises(
                SmartCmpValidationError,
                match="No resource pools match the selected resource tags",
            ):
                await list_resource_bundles(
                    client,
                    ResourceBundleQuery(
                        business_group_id="business-group-1",
                        component_type="resource.iaas.machine.instance.abstract",
                        node_type="cloudchef.nodes.Compute",
                        catalog_id="catalog-1",
                        node_template_name="Compute",
                        resource_bundle_tags=("FACET_ENV:none",),
                    ),
                )
            runtime_result = await list_resource_bundles(
                client,
                ResourceBundleQuery(
                    business_group_id="business-group-1",
                    component_type="resource.iaas.machine.instance.abstract",
                    node_type="cloudchef.nodes.Compute",
                    catalog_id="catalog-runtime",
                    node_template_name="Compute",
                ),
            )
            with pytest.raises(
                SmartCmpValidationError,
                match="generated request instructions",
            ):
                await list_resource_bundles(
                    client,
                    ResourceBundleQuery(
                        business_group_id="business-group-1",
                        component_type="cloudchef.nodes.Compute",
                        node_type="cloudchef.nodes.Compute",
                        catalog_id="catalog-invalid",
                        node_template_name="Compute",
                        resource_bundle_tags=("FACET_ENV:dev",),
                    ),
                )
            with pytest.raises(ValueError, match="resource_bundle_tags"):
                ResourceBundleQuery(
                    business_group_id="business-group-1",
                    component_type="cloudchef.nodes.Compute",
                    node_type="cloudchef.nodes.Compute",
                    catalog_id="catalog-1",
                    node_template_name="Compute",
                    resource_bundle_tags=(),
                )
            return result, runtime_result

    result, runtime_result = asyncio.run(invoke())

    assert result.items == ({
        "id": "resource-bundle-1",
        "name": "vSphere pool",
        "cloudEntryTypeId": "yacmp:cloudentry:type:vsphere",
    },)
    assert runtime_result.items == result.items


def test_resource_bundle_resolves_declared_placement_fields() -> None:
    """Auto-select a sole lookup option and report remaining required fields."""

    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )
    lookup_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal lookup_calls
        if request.url.path.endswith("/resource-bundles"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "resource-bundle-1",
                        "name": "AWS pool",
                        "cloudEntryTypeId": "yacmp:cloudentry:type:aws",
                        "cloudEntryId": "cloud-entry-1",
                    }
                ],
                request=request,
            )
        if request.url.path.endswith("/catalogs/catalog-1"):
            return httpx.Response(
                200,
                json={
                    "id": "catalog-1",
                    "sourceKey": "catalog-resource-type",
                    "instructions": (
                        "# Request Parameter Instructions\n\n"
                        "catalog:\n"
                        "  component_type: catalog-resource-type\n"
                        "resource_specs:\n"
                        "- node: SecurityGroup\n"
                        "  type: cloudchef.nodes.SecurityGroup\n"
                        "  resourceBundleId:\n"
                        "    required: true\n"
                    ),
                    "blueprint": {
                        "mainYaml": (
                            "node_templates:\n"
                            "  SecurityGroup:\n"
                            "    type: cloudchef.nodes.SecurityGroup\n"
                        ),
                        "extensibleParams": json.dumps(
                            {
                                "SecurityGroup": {
                                    "data": {
                                        "account_id": "account-1",
                                        "un_visibility_property": ["account_id"],
                                    }
                                }
                            }
                        ),
                    },
                },
                request=request,
            )
        if request.url.path.endswith("/components"):
            assert request.url.params.get("all") == ""
            assert request.url.params.get("types") == (
                "cloudchef.nodes.SecurityGroup"
            )
            assert request.url.params.get("resourceType") is None
            return httpx.Response(
                200,
                json=[{
                    "id": "component-security-group",
                    "resourceType": "resource.security-group",
                    "model": {"typeName": "cloudchef.nodes.SecurityGroup"},
                }],
                request=request,
            )
        if request.url.path.endswith("/cloudentries"):
            return httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "resourceConfig": {
                                "SecurityGroup": {
                                    "account_id": {
                                        "type": "string",
                                        "required": {"inRequest": {"value": True}},
                                    },
                                    "vpc_id": {
                                        "type": "string",
                                        "defaultValue": "stale-vpc",
                                        "required": {"inRequest": {"value": True}},
                                        "dependencies": {
                                            "account_id": "accountId",
                                        },
                                        "config": {
                                            "value": {
                                                "source": "api",
                                                "method": "POST",
                                                "expression": (
                                                    "/cloudprovider?"
                                                    "action=queryCloudResource"
                                                ),
                                                "body": {
                                                    "businessGroupId": (
                                                        "${businessGroupId}"
                                                    ),
                                                    "cloudEntryId": "${cloudEntryId}",
                                                    "cloudResourceType": (
                                                        "generic-resource"
                                                    ),
                                                    "queryProperties": {
                                                        "componentId": (
                                                            "${componentId}"
                                                        ),
                                                        "resourceType": "vpc",
                                                        "resourceBundleId": (
                                                            "${resource_bundle_config."
                                                            "policy_resource}"
                                                        ),
                                                        "accountId": "{$.account_id}",
                                                    },
                                                },
                                            }
                                        },
                                    },
                                    "group_description": {
                                        "type": "string",
                                        "required": {"inRequest": {"value": True}},
                                    },
                                }
                            }
                        }
                    ]
                },
                request=request,
            )
        if request.url.path.endswith("/cloudprovider"):
            lookup_calls += 1
            body = json.loads(request.content)
            assert body["queryProperties"] == {
                "componentId": "component-security-group",
                "resourceType": "vpc",
                "resourceBundleId": "resource-bundle-1",
                "accountId": "account-1",
            }
            return httpx.Response(
                200,
                json=(
                    []
                    if lookup_calls == 5
                    else [{"id": 0, "name": "VPC A"}]
                ),
                request=request,
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            auto_pending = await list_resource_bundles(
                client,
                ResourceBundleQuery(
                    business_group_id="business-group-1",
                    component_type="catalog-resource-type",
                    node_type="cloudchef.nodes.SecurityGroup",
                    catalog_id="catalog-1",
                    node_template_name="SecurityGroup",
                    resource_bundle_id="resource-bundle-1",
                ),
            )
            pending = await list_resource_bundles(
                client,
                ResourceBundleQuery(
                    business_group_id="business-group-1",
                    component_type="catalog-resource-type",
                    node_type="cloudchef.nodes.SecurityGroup",
                    catalog_id="catalog-1",
                    node_template_name="SecurityGroup",
                    resource_bundle_id="resource-bundle-1",
                    placement_fields=("vpc_id",),
                ),
            )
            complete = await list_resource_bundles(
                client,
                ResourceBundleQuery(
                    business_group_id="business-group-1",
                    component_type="catalog-resource-type",
                    node_type="cloudchef.nodes.SecurityGroup",
                    catalog_id="catalog-1",
                    node_template_name="SecurityGroup",
                    resource_bundle_id="resource-bundle-1",
                    placement_values={
                        "vpc_id": "0",
                        "group_description": "MCP acceptance group",
                    },
                ),
            )
            invalid_selection = await list_resource_bundles(
                client,
                ResourceBundleQuery(
                    business_group_id="business-group-1",
                    component_type="catalog-resource-type",
                    node_type="cloudchef.nodes.SecurityGroup",
                    catalog_id="catalog-1",
                    node_template_name="SecurityGroup",
                    resource_bundle_id="resource-bundle-1",
                    placement_values={
                        "vpc_id": "vpc-unavailable",
                        "group_description": "Invalid selection",
                    },
                ),
            )
            empty_lookup = await list_resource_bundles(
                client,
                ResourceBundleQuery(
                    business_group_id="business-group-1",
                    component_type="catalog-resource-type",
                    node_type="cloudchef.nodes.SecurityGroup",
                    catalog_id="catalog-1",
                    node_template_name="SecurityGroup",
                    resource_bundle_id="resource-bundle-1",
                    placement_fields=("vpc_id",),
                    placement_values={"group_description": "No VPC available"},
                ),
            )
            return auto_pending, pending, complete, invalid_selection, empty_lookup

    auto_pending, pending, complete, invalid_selection, empty_lookup = asyncio.run(invoke())

    auto_fields = {
        field["key"]: field
        for field in auto_pending.items[0]["requestFields"]
    }
    assert auto_fields["vpc_id"]["options"][0]["id"] == 0
    assert auto_fields["vpc_id"]["options"][0]["name"] == "VPC A"

    assert set(pending.items[0]) == {
        "id",
        "name",
        "cloudEntryTypeId",
        "requestFields",
        "missingRequiredFields",
        "missingSelectionFields",
        "configurationErrors",
    }
    fields = {
        field["key"]: field
        for field in pending.items[0]["requestFields"]
    }
    assert fields["account_id"]["value"] == "account-1"
    assert fields["vpc_id"]["dependsOn"] == ["account_id"]
    assert fields["vpc_id"]["options"][0]["id"] == 0
    assert fields["vpc_id"]["value"] == 0
    assert pending.items[0]["missingRequiredFields"] == ["group_description"]
    assert pending.items[0]["missingSelectionFields"] == ["group_description"]
    assert pending.selection_field == {}
    assert pending.selection_candidates == ()
    assert complete.selection_candidates == ()
    assert "not selectable" in invalid_selection.items[0]["configurationErrors"][0]
    assert "no selectable options" in empty_lookup.items[0]["configurationErrors"][0]


@pytest.mark.parametrize(
    "components, error_pattern",
    [
        ([], "exactly one component"),
        (
            [{"model": {"typeName": "cloudchef.nodes.Compute"}}],
            "component without an ID",
        ),
        (
            [
                {
                    "id": "component-1",
                    "model": {"typeName": "cloudchef.nodes.Compute"},
                },
                {
                    "id": "component-2",
                    "model": {"typeName": "cloudchef.nodes.Compute"},
                },
            ],
            "exactly one component",
        ),
        (
            [
                {
                    "id": "component-1",
                    "model": {"typeName": "cloudchef.nodes.Compute"},
                },
                {"model": {"typeName": "cloudchef.nodes.Compute"}},
            ],
            "exactly one component",
        ),
    ],
)
def test_resource_bundle_rejects_ambiguous_or_missing_node_component(
    components: list[dict[str, object]],
    error_pattern: str,
) -> None:
    """Component resolution must fail closed before request-field lookup."""

    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path.endswith("/resource-bundles"):
            return httpx.Response(
                200,
                json=[{"id": "resource-bundle-1"}],
                request=request,
            )
        if request.url.path.endswith("/catalogs/catalog-1"):
            return httpx.Response(
                200,
                json={
                    "id": "catalog-1",
                    "sourceKey": "catalog-resource-type",
                    "instructions": (
                        "# Request Parameter Instructions\n\n"
                        "catalog:\n"
                        "  component_type: catalog-resource-type\n"
                        "resource_specs:\n"
                        "- node: Compute\n"
                        "  type: cloudchef.nodes.Compute\n"
                        "  resourceBundleId:\n"
                        "    required: true\n"
                    ),
                    "blueprint": {
                        "mainYaml": (
                            "node_templates:\n"
                            "  Compute:\n"
                            "    type: cloudchef.nodes.Compute\n"
                        )
                    },
                },
                request=request,
            )
        if request.url.path.endswith("/components"):
            assert request.url.params.get("types") == "cloudchef.nodes.Compute"
            return httpx.Response(200, json=components, request=request)
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    async def invoke() -> None:
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            await list_resource_bundles(
                client,
                ResourceBundleQuery(
                    business_group_id="business-group-1",
                    component_type="catalog-resource-type",
                    node_type="cloudchef.nodes.Compute",
                    catalog_id="catalog-1",
                    node_template_name="Compute",
                    resource_bundle_id="resource-bundle-1",
                ),
            )

    with pytest.raises(SmartCmpValidationError, match=error_pattern):
        asyncio.run(invoke())

    assert requested_paths == [
        "/platform-api/catalogs/catalog-1",
        "/platform-api/resource-bundles",
        "/platform-api/components",
    ]


@pytest.mark.parametrize(
    "query",
    [
        ResourceBundleQuery(
            business_group_id="business-group-1",
            component_type="cloudchef.nodes.Compute",
            node_type="cloudchef.nodes.Compute",
            catalog_id="",
            node_template_name="",
        ),
        ResourceBundleQuery(
            business_group_id="business-group-1",
            component_type="cloudchef.nodes.Compute",
            node_type="cloudchef.nodes.Compute",
            catalog_id="catalog-1",
            node_template_name="Compute",
            placement_values={"catalogId": "catalog-1", "node": "Compute"},
        ),
    ],
)
def test_resource_bundle_rejects_implicit_context_before_http(
    query: ResourceBundleQuery,
) -> None:
    """Missing or map-encoded catalog context fails before any SmartCMP call."""

    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(200, json=[], request=request)

    async def invoke() -> None:
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            await list_resource_bundles(client, query)

    with pytest.raises(SmartCmpValidationError):
        asyncio.run(invoke())

    assert request_count == 0


@pytest.mark.parametrize(
    ("available_ip_size", "expected_valid"),
    [(1, True), (0, False)],
)
def test_windows_compute_rejects_an_exhausted_ip_pool(
    available_ip_size: int,
    expected_valid: bool,
) -> None:
    """A default network remains selectable and requires usable IP capacity."""

    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/resource-bundles"):
            return httpx.Response(
                200,
                json=[{
                    "id": "resource-bundle-1",
                    "cloudEntryTypeId": "yacmp:cloudentry:type:vsphere",
                    "cloudEntryId": "cloud-entry-1",
                }],
                request=request,
            )
        if request.url.path.endswith("/catalogs/catalog-windows"):
            return httpx.Response(
                200,
                json={
                    "id": "catalog-windows",
                    "sourceKey": "resource.iaas.machine.windows_instance.abstract",
                    "instructions": (
                        "# Request Parameter Instructions\n\n"
                        "catalog:\n"
                        "  component_type: "
                        "resource.iaas.machine.windows_instance.abstract\n"
                        "resource_specs:\n"
                        "- node: WindowsCompute\n"
                        "  type: cloudchef.nodes.WindowsCompute\n"
                        "  resourceBundleId:\n"
                        "    required: true\n"
                    ),
                    "blueprint": {
                        "mainYaml": (
                            "node_templates:\n"
                            "  WindowsCompute:\n"
                            "    type: cloudchef.nodes.WindowsCompute\n"
                        ),
                        "extensibleParams": "{}",
                    },
                },
                request=request,
            )
        if request.url.path.endswith("/components"):
            assert request.url.params.get("types") == (
                "cloudchef.nodes.WindowsCompute"
            )
            return httpx.Response(
                200,
                json=[{
                    "id": "component-windows-compute",
                    "resourceType": (
                        "resource.iaas.machine.windows_instance.abstract"
                    ),
                    "model": {"typeName": "cloudchef.nodes.WindowsCompute"},
                }],
                request=request,
            )
        if request.url.path.endswith("/cloudentries"):
            return httpx.Response(
                200,
                json={
                    "result": [{
                        "resourceConfig": {
                            "Compute": {
                                "network_id": {
                                    "type": "string",
                                    "defaultValue": "network-1",
                                    "required": {"inRequest": {"value": True}},
                                    "visibility": {"inRequest": {"value": True}},
                                    "modification": {"inRequest": {"value": True}},
                                    "cloudResourceType": "generic-resource",
                                    "queryProperties": {"resourceType": "network"},
                                },
                                "subnet_id": {
                                    "type": "string",
                                    "required": {"inRequest": {"value": True}},
                                    "visibility": {"inRequest": {"value": True}},
                                    "modification": {"inRequest": {"value": True}},
                                    "dependencies": {"network_id": "networkId"},
                                    "cloudResourceType": "generic-resource",
                                    "queryProperties": {"resourceType": "subnet"},
                                }
                            }
                        }
                    }]
                },
                request=request,
            )
        if request.url.path.endswith("/cloudprovider"):
            resource_type = json.loads(request.content)["queryProperties"][
                "resourceType"
            ]
            if resource_type == "subnet":
                return httpx.Response(
                    200,
                    json=[{"id": "subnet-1", "name": "Subnet 1"}],
                    request=request,
                )
            assert resource_type == "network"
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "network-1",
                        "name": "Network 1",
                        "properties": {
                            "ipAllocationMethod": "IP_POOL",
                            "availableIpSize": available_ip_size,
                        },
                    },
                    {
                        "id": "network-2",
                        "name": "Network 2",
                        "properties": {"availableIpSize": 1},
                    },
                ],
                request=request,
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            automatic = await list_resource_bundles(
                client,
                ResourceBundleQuery(
                    business_group_id="business-group-1",
                    component_type="resource.iaas.machine.windows_instance.abstract",
                    node_type="cloudchef.nodes.WindowsCompute",
                    catalog_id="catalog-windows",
                    node_template_name="WindowsCompute",
                    resource_bundle_id="resource-bundle-1",
                ),
            )
            selected = await list_resource_bundles(
                client,
                ResourceBundleQuery(
                    business_group_id="business-group-1",
                    component_type="resource.iaas.machine.windows_instance.abstract",
                    node_type="cloudchef.nodes.WindowsCompute",
                    catalog_id="catalog-windows",
                    node_template_name="WindowsCompute",
                    resource_bundle_id="resource-bundle-1",
                    placement_values={"networkId": "network-1"},
                ),
            )
            return automatic, selected

    automatic, result = asyncio.run(invoke())

    automatic_fields = {
        field["key"]: field for field in automatic.items[0]["requestFields"]
    }
    assert automatic_fields["networkId"]["value"] is None
    assert [
        option["id"] for option in automatic_fields["networkId"]["options"]
    ] == ["network-1", "network-2"]
    assert automatic.selection_field["key"] == "networkId"
    assert automatic.selection_candidates == (
        {"id": "network-1", "name": "Network 1"},
        {"id": "network-2", "name": "Network 2"},
    )
    assert automatic.items[0]["configurationErrors"] == []
    assert result.selection_candidates == ()
    assert automatic_fields["subnetId"]["options"] == []
    assert automatic_fields["subnetId"]["value"] is None

    fields = {field["key"]: field for field in result.items[0]["requestFields"]}
    assert fields["networkId"]["target"] == "networkId"
    assert fields["subnetId"]["value"] == "subnet-1"
    network_field = next(
        field
        for field in result.items[0]["requestFields"]
        if field["key"] == "networkId"
    )
    assert network_field["options"][0]["id"] == "network-1"
    if expected_valid:
        assert result.items[0]["configurationErrors"] == []
    else:
        assert "no available IP addresses" in result.items[0][
            "configurationErrors"
        ][0]


def test_supported_deployment_operation_rechecks_and_submits_once() -> None:
    """An allowed deployment action preserves the deployment request contract."""

    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )
    submitted: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            assert request.url.path.endswith(
                "/deployments/deployment-1/deployment-actions"
            )
            return httpx.Response(
                200,
                json=[{
                    "id": "restart",
                    "enabled": True,
                    "supportBatchAction": True,
                    "parameters": {},
                }],
                request=request,
            )
        assert request.url.path.endswith("/deployments/execute-action")
        submitted.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "results": {
                    "deployment-1": {"id": "task-1", "state": "CREATED"}
                }
            },
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            return await execute_resource_action(
                client,
                ResourceActionInput(
                    targets=(ResourceActionTarget(
                        category="deployments",
                        resource_id="deployment-1",
                    ),),
                    action="restart",
                ),
            )

    result = asyncio.run(invoke())

    assert result.submitted is True
    assert len(submitted) == 1
    deployment_request = submitted[0]["deployment-1"]
    assert deployment_request["operationName"] == "restart"
    assert deployment_request["scheduledTaskMetadataRequest"]["cycled"] is False
    assert json.loads(deployment_request["operationParamJson"]) == {
        "systemForm": None,
    }
    assert "recycle" not in deployment_request
    assert "manual" not in deployment_request


def test_cloud_flavor_query_returns_the_request_flavor_id() -> None:
    """Cloud-flavor choices expose the value required by MachineSpec."""

    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(
            "/flavors/compute-profile-1/cloud-flavors"
        )
        assert request.url.params["cloudResource"] == "true"
        assert request.url.params["resourceBundleId"] == "resource-bundle-1"
        return httpx.Response(
            200,
            json=[
                {
                    "id": "cloud-flavor-mapping-1",
                    "name": "2C2G",
                    "flavorId": "S6.MEDIUM2",
                    "flavorName": "InstanceFamily:S6 CPU:2 Memory:2",
                }
            ],
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            return await list_flavors(
                client,
                FlavorQuery(
                    resource_bundle_id="resource-bundle-1",
                    compute_profile_id="compute-profile-1",
                ),
            )

    result = asyncio.run(invoke())

    assert result.items == (
        {"id": "S6.MEDIUM2", "name": "InstanceFamily:S6 CPU:2 Memory:2"},
    )




def test_request_submission_revalidates_the_previewed_resource_pool() -> None:
    """Submission must reuse and revalidate the pool selected for preview."""

    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )
    submitted: list[dict[str, Any]] = []
    tag_only_markdown = """
# Request Parameter Instructions

catalog:
  component_type: resource.iaas.machine.instance.abstract
resource_specs:
- node: Compute
  type: cloudchef.nodes.Compute
  resourceBundleTags:
    required: true
    ask: true
""".strip()
    combined_markdown = """
# Request Parameter Instructions

catalog:
  component_type: resource.iaas.machine.instance.abstract
resource_specs:
- node: Compute
  type: cloudchef.nodes.Compute
  resourceBundleTags:
    required: true
    ask: true
  resourceBundleId:
    required: true
    ask: true
""".strip()
    runtime_only_markdown = """
# Request Parameter Instructions

catalog:
  component_type: resource.iaas.machine.instance.abstract
resource_specs:
- node: Compute
  type: cloudchef.nodes.Compute
  runtime_fields:
    resolver: resource_bundle_placement
""".strip()
    markdown_by_catalog = {
        "catalog-tag-only": tag_only_markdown,
        "catalog-combined": combined_markdown,
        "catalog-runtime": runtime_only_markdown,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        catalog_id = request.url.path.rsplit("/", 1)[-1]
        if catalog_id == "catalog-legacy-compute":
            return httpx.Response(
                200,
                json={
                    "id": catalog_id,
                    "name": "Standard request catalog",
                    "type": "cloudchef.nodes.Database",
                    "instructions": "",
                },
                request=request,
            )
        if catalog_id in markdown_by_catalog:
            return httpx.Response(
                200,
                json={
                    "id": catalog_id,
                    "name": "Linux resource pool mode",
                    "instructions": markdown_by_catalog[catalog_id],
                },
                request=request,
            )
        if request.url.path.endswith("/resource-bundles"):
            assert request.url.params.get_list("facets") in (
                [],
                ["FACET_ENV:dev"],
            )
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "resource-bundle-first",
                        "name": "First matching pool",
                        "cloudEntryTypeId": "yacmp:cloudentry:type:vsphere",
                    },
                    {
                        "id": "resource-bundle-later",
                        "name": "Later matching pool",
                        "cloudEntryTypeId": "yacmp:cloudentry:type:vsphere",
                    },
                    {
                        "id": "resource-bundle-selected",
                        "name": "Explicitly selected pool",
                        "cloudEntryTypeId": "yacmp:cloudentry:type:vsphere",
                    },
                ],
                request=request,
            )
        if request.url.path.endswith("/generic-request/submit"):
            submitted.append(json.loads(request.content))
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "request-record-1",
                        "workflowId": "RES20260821000064",
                        "state": "INITIALING",
                    }
                ],
                request=request,
            )
        if request.url.path.endswith("/generic-request/request-record-1"):
            return httpx.Response(
                200,
                json={
                    "workflowId": "RES20260821000064",
                    "state": "INITIALING",
                    "processInstanceId": "process-1",
                },
                request=request,
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            async def submit(
                body: dict[str, Any],
                selections: dict[str, str] | None = None,
            ):
                return await submit_request(
                    client,
                    RequestSubmissionInput(
                        body=body,
                        resource_bundle_selections=selections or {},
                        actor=RequestActorIdentity(
                            user_id="user-1",
                            login_id="admin",
                        ),
                        verification_attempts=1,
                        verification_interval_seconds=0,
                    ),
                )

            tag_only = await submit(
                {
                    "catalogId": "catalog-tag-only",
                    "businessGroupId": "business-group-1",
                    "name": "tag-only-vm",
                    "resourceSpecs": [{
                        "node": "Compute",
                        "type": "untrusted.node.Type",
                        "resourceBundleTags": ["FACET_ENV:dev"],
                    }],
                },
                {"Compute": "resource-bundle-first"},
            )
            combined = await submit(
                {
                    "catalogId": "catalog-combined",
                    "businessGroupId": "business-group-1",
                    "name": "combined-vm",
                    "resourceSpecs": [{
                        "node": "Compute",
                        "type": "cloudchef.nodes.Compute",
                        "resourceBundleTags": ["FACET_ENV:dev"],
                        "resourceBundleId": "resource-bundle-selected",
                    }],
                },
                {"Compute": "resource-bundle-selected"},
            )
            runtime_only = await submit(
                {
                    "catalogId": "catalog-runtime",
                    "businessGroupId": "business-group-1",
                    "name": "runtime-only-vm",
                    "resourceSpecs": [{
                        "node": "Compute",
                        "type": "cloudchef.nodes.Compute",
                    }],
                },
                {"Compute": "resource-bundle-first"},
            )
            with pytest.raises(
                SmartCmpValidationError,
                match="previewed resource-pool selection changed",
            ):
                await submit(
                    {
                        "catalogId": "catalog-tag-only",
                        "businessGroupId": "business-group-1",
                        "name": "changed-tag-only-vm",
                        "resourceSpecs": [{
                            "node": "Compute",
                            "type": "cloudchef.nodes.Compute",
                            "resourceBundleTags": ["FACET_ENV:dev"],
                        }],
                    },
                    {"Compute": "resource-bundle-later"},
                )
            no_instructions = await submit({
                "catalogId": "catalog-legacy-compute",
                "businessGroupId": "business-group-1",
                "name": "standard-catalog-request",
                "resourceSpecs": [{
                    "node": "Database",
                    "type": "cloudchef.nodes.Database",
                    "resourceBundleTags": ["FACET_ENV:dev"],
                }],
            })
            return tag_only, combined, runtime_only, no_instructions

    results = asyncio.run(invoke())

    assert len(submitted) == 4
    assert submitted[0]["resourceSpecs"][0]["resourceBundleId"] == (
        "resource-bundle-first"
    )
    assert "resourceBundleTags" not in submitted[0]["resourceSpecs"][0]
    assert submitted[1]["resourceSpecs"][0]["resourceBundleId"] == (
        "resource-bundle-selected"
    )
    assert "resourceBundleTags" not in submitted[1]["resourceSpecs"][0]
    assert submitted[2]["resourceSpecs"][0]["resourceBundleId"] == (
        "resource-bundle-first"
    )
    assert submitted[3]["resourceSpecs"][0]["resourceBundleTags"] == [
        "FACET_ENV:dev"
    ]
    assert "resourceBundleId" not in submitted[3]["resourceSpecs"][0]
    assert all(result.items[0].request_id == "RES20260821000064" for result in results)


def test_request_submission_normalizes_payload_and_submits_exactly_once():
    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )
    submitted: list[dict] = []
    submit_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal submit_calls
        if request.url.path.endswith("/catalogs/catalog-linux"):
            return httpx.Response(
                200,
                json={"id": "catalog-linux", "instructions": ""},
                request=request,
            )
        if request.url.path.endswith("/generic-request/submit"):
            submit_calls += 1
            submitted.append(json.loads(request.content))
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "20fef12e-5015-4df5-822b-e1e87c4f64fd",
                        "workflowId": "RES20260731009991",
                        "state": "INITIALING",
                    }
                ],
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "workflowId": "RES20260731009991",
                "state": "INITIALING",
                "processInstanceId": "process-1",
            },
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            return await submit_request(
                client,
                RequestSubmissionInput(
                    body={
                        "catalogId": "catalog-linux",
                        "name": "step3-vm",
                        "quantity": "2",
                        "resourceSpecs": {
                            "node": "Compute",
                            "type": "cloudchef.nodes.Compute",
                            "credentialPassword": "real-vm-password",
                        },
                    },
                    actor=RequestActorIdentity(
                        user_id="user-1",
                        login_id="admin",
                    ),
                    verification_attempts=1,
                    verification_interval_seconds=0,
                ),
            )

    result = asyncio.run(invoke())

    assert submit_calls == 1
    assert submitted[0]["quantity"] == 2
    assert isinstance(submitted[0]["resourceSpecs"], list)
    assert (
        submitted[0]["resourceSpecs"][0]["credentialPassword"]
        == "real-vm-password"
    )
    assert submitted[0]["userId"] == "user-1"
    assert submitted[0]["userLoginId"] == "admin"
    assert result.items[0].outcome == "success"
    assert result.items[0].request_id == "RES20260731009991"


def test_request_submission_marks_verified_initialization_failure() -> None:
    """A failed verification record must not remain an overall success."""
    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/generic-request/submit"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "20fef12e-5015-4df5-822b-e1e87c4f64fd",
                        "workflowId": "RES20260731009995",
                        "state": "INITIALING",
                    }
                ],
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "workflowId": "RES20260731009995",
                "state": "INITIALING_FAILED",
                "errMsg": "blueprint initialization failed",
            },
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            return await submit_request(
                client,
                RequestSubmissionInput(
                    body={"catalogId": "catalog-linux", "name": "failed-vm"},
                    actor=RequestActorIdentity(
                        user_id="user-1",
                        login_id="admin",
                    ),
                    verification_attempts=1,
                    verification_interval_seconds=0,
                ),
            )

    result = asyncio.run(invoke())

    assert result.overall_failed is True
    assert result.items[0].outcome == "initialization_failed"
    assert result.items[0].request_id == "RES20260731009995"


@pytest.mark.parametrize(
    ("secret_field", "preview_mask"),
    [("credentialPassword", "***"), ("password", "******")],
)
def test_request_submission_rejects_nested_preview_mask_before_http(
    secret_field: str,
    preview_mask: str,
) -> None:
    """Presentation masks must never cross the Provider submit boundary."""

    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )
    request_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_calls
        request_calls += 1
        raise AssertionError(f"Preview mask reached HTTP: {request.url}")

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            return await submit_request(
                client,
                RequestSubmissionInput(
                    body={
                        "catalogId": "catalog-linux",
                        "resourceSpecs": [
                            {"nested": {secret_field: preview_mask}}
                        ],
                    },
                ),
            )

    with pytest.raises(SmartCmpValidationError, match="preview masks"):
        asyncio.run(invoke())

    assert request_calls == 0




@pytest.mark.parametrize("error_field", ["errorMessage", "errMsg"])
def test_request_submission_redacts_credentials_from_submit_record(
    error_field: str,
) -> None:
    """HTTP 200 business records must not expose submitted credentials."""
    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "id": "20fef12e-5015-4df5-822b-e1e87c4f64fd",
                    "workflowId": "RES20260731009994",
                    "state": "INITIALING_FAILED",
                    error_field: "credentialPassword=vm-secret is invalid",
                }
            ],
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            return await submit_request(
                client,
                RequestSubmissionInput(
                    body={"catalogId": "catalog-linux", "name": "rejected"},
                    actor=RequestActorIdentity(
                        user_id="user-1",
                        login_id="admin",
                    ),
                    verification_attempts=1,
                    verification_interval_seconds=0,
                ),
            )

    result = asyncio.run(invoke())

    assert result.items[0].outcome == "failed"
    assert "vm-secret" not in result.items[0].error
    assert "[REDACTED]" in result.items[0].error




def test_robot_submission_uses_cmp_actor_instead_of_webhook_user():
    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="webhook-approval-1",
        token="cmp_tk_robot",
        robot_profile="cmp-test-robot",
    )
    submitted: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/users/current-user-details"):
            return httpx.Response(
                200,
                json={"id": "robot-user-id", "loginId": "robot-admin"},
                request=request,
            )
        if request.url.path.endswith("/generic-request/submit"):
            submitted.append(json.loads(request.content))
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "6d279970-c2f6-4b09-ab63-319abf913c06",
                        "workflowId": "RES20260731009992",
                        "state": "INITIALING",
                    }
                ],
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "workflowId": "RES20260731009992",
                "state": "STARTED",
            },
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            return await submit_request(
                client,
                RequestSubmissionInput(
                    body={
                        "catalogId": "catalog-linux",
                        "name": "robot-vm",
                        "userId": "stale-user-id",
                        "userLoginId": "webhook-approval-1",
                    },
                    verification_attempts=1,
                    verification_interval_seconds=0,
                ),
            )

    result = asyncio.run(invoke())

    assert result.items[0].outcome == "success"
    assert submitted[0]["userId"] == "robot-user-id"
    assert submitted[0]["userLoginId"] == "robot-admin"
    assert submitted[0]["userLoginId"] != "webhook-approval-1"




def test_indeterminate_submit_is_not_retried():
    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )
    submit_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal submit_calls
        submit_calls += 1
        raise httpx.ReadTimeout("result lost", request=request)

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            await submit_request(
                client,
                RequestSubmissionInput(
                    body={
                        "catalogId": "catalog-linux",
                        "name": "unknown-vm",
                        "userId": "user-1",
                        "userLoginId": "admin",
                    },
                    actor=RequestActorIdentity(
                        user_id="user-1",
                        login_id="admin",
                    ),
                    verification_attempts=1,
                    verification_interval_seconds=0,
                ),
            )

    with pytest.raises(
        SmartCmpUnknownOutcomeError,
        match="do not resubmit automatically",
    ):
        asyncio.run(invoke())

    assert submit_calls == 1


@pytest.mark.parametrize(
    "submit_payload",
    [
        [],
        [{"id": "internal-request-id", "state": "INITIALING"}],
    ],
)
def test_uncorrelated_successful_submit_is_unknown(submit_payload):
    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )
    submit_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal submit_calls
        submit_calls += 1
        return httpx.Response(200, json=submit_payload, request=request)

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            await submit_request(
                client,
                RequestSubmissionInput(
                    body={"catalogId": "catalog-linux", "name": "uncorrelated"},
                    actor=RequestActorIdentity(
                        user_id="user-1",
                        login_id="admin",
                    ),
                    verification_attempts=1,
                    verification_interval_seconds=0,
                ),
            )

    with pytest.raises(
        SmartCmpUnknownOutcomeError,
        match="do not resubmit automatically",
    ):
        asyncio.run(invoke())

    assert submit_calls == 1




def test_business_rejection_is_definite_and_not_reported_as_unknown():
    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )
    submit_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal submit_calls
        submit_calls += 1
        return httpx.Response(
            200,
            json={
                "success": False,
                "code": "CMP_REQUEST_REJECTED",
                "message": "Catalog is unavailable.",
            },
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            await submit_request(
                client,
                RequestSubmissionInput(
                    body={
                        "catalogId": "catalog-linux",
                        "name": "rejected-vm",
                        "userId": "user-1",
                        "userLoginId": "admin",
                    },
                    actor=RequestActorIdentity(
                        user_id="user-1",
                        login_id="admin",
                    ),
                    verification_attempts=1,
                    verification_interval_seconds=0,
                ),
            )

    with pytest.raises(
        SmartCmpUpstreamError,
        match="SmartCMP business error CMP_REQUEST_REJECTED",
    ):
        asyncio.run(invoke())

    assert submit_calls == 1


def test_request_status_resolves_visible_id_and_normalizes_approval_state():
    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )
    request_id = "RES20260731009993"
    detail_id = "1eeb334e-01c9-4e2b-bf72-b57d5ce2216d"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/generic-request/search"):
            assert request.url.params["queryValue"] == request_id
            return httpx.Response(
                200,
                json={
                    "content": [
                        {"id": detail_id, "workflowId": request_id},
                    ]
                },
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "id": detail_id,
                "workflowId": request_id,
                "state": "APPROVAL_PENDING",
                "currentActivity": {
                    "processStep": {"name": "Manager approval"},
                },
            },
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            return await get_request_status(
                client,
                RequestStatusQuery(request_id=request_id),
            )

    result = asyncio.run(invoke())

    assert result.metadata["requestId"] == request_id
    assert result.metadata["statusCategory"] == "approval_pending"
    assert result.metadata["approvalPassed"] is False
    assert result.metadata["currentStep"] == "Manager approval"










def test_resource_evidence_is_normalized_inside_provider():
    """Direct Provider consumers receive the analyzer-compatible projection."""

    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PATCH"
        return httpx.Response(
            200,
            json={
                "id": "resource-1",
                "name": "vm-01",
                "componentType": "resource.vm",
                "status": "RUNNING",
                "properties": {"cpu": 2, "nested": {"ignored": True}},
                "RuntimeProperties": {"memoryMb": 4096},
            },
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            return await load_resource_evidence(
                client,
                ResourceEvidenceQuery(resource_ids=("resource-1",)),
            )

    result = asyncio.run(invoke())
    normalized = result.records[0]["normalized"]

    assert normalized["type"] == "resource.vm"
    assert normalized["properties"]["name"] == "vm-01"
    assert normalized["properties"]["status"] == "RUNNING"
    assert normalized["properties"]["cpu"] == 2
    assert normalized["properties"]["memoryMb"] == 4096
    assert "nested" not in normalized["properties"]


def test_resource_evidence_does_not_substitute_legacy_get_endpoints():
    """Propagate an authoritative view failure without issuing another read."""

    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        assert request.method == "PATCH"
        assert request.url.path.endswith("/nodes/resource-1/view")
        return httpx.Response(404, json={}, request=request)

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            await load_resource_evidence(
                client,
                ResourceEvidenceQuery(resource_ids=("resource-1",)),
            )

    with pytest.raises(SmartCmpNotFoundError):
        asyncio.run(invoke())

    assert seen == [("PATCH", "/platform-api/nodes/resource-1/view")]
