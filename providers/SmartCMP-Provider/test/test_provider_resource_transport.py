"""Focused tests for request-scoped resource transport and operations."""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
        SmartCmpTargetResolutionError,
        SmartCmpTimeoutError,
        SmartCmpUnknownOutcomeError,
        SmartCmpUpstreamError,
        SmartCmpValidationError,
    )
    from smartcmp_provider.models.catalogs import (
        CatalogDetailQuery,
        CatalogListQuery,
    )
    from smartcmp_provider.models.requests import (
        RequestActorIdentity,
        RequestStatusQuery,
        RequestSubmissionInput,
    )
    from smartcmp_provider.models.resources import (
        ResourceDetailQuery,
        ResourceEvidenceQuery,
        ResourceListQuery,
        ResourceOperationsQuery,
        ResourceSummarySearchQuery,
    )
    from smartcmp_provider.operations.resources import (
        get_resource_detail,
        load_resource_evidence,
        list_resource_operations,
        list_resources,
        search_resource_summaries,
    )
    from smartcmp_provider.operations.catalogs import (
        get_catalog_detail,
        list_catalogs,
    )
    from smartcmp_provider.operations.requests import (
        get_request_status,
        submit_request,
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


def test_provided_resolver_keeps_secret_out_of_context_and_repr():
    request = make_request(
        instance_name="cmp-a",
        base_url="cmp-a.example/tenant",
        user_id="user-a",
        token="session-a",
        timeout=75,
    )

    assert request.context.instance.base_url == "https://cmp-a.example/tenant/platform-api"
    assert request.context.instance.timeout_seconds == 75
    assert request.context.instance.tls.verify is False
    assert request.context.principal.subject == "user-a"
    assert request.context.trace_id == "run-user-a"
    assert request.credential.headers() == {
        "CloudChef-Authenticate": "session-a",
        "Content-Type": "application/json; charset=utf-8",
    }
    assert "session-a" not in repr(request.credential)
    assert not hasattr(request.context, "credential")


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


def test_resource_operations_preserve_paths_resolution_and_filtering():
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
                        "id": "stop",
                        "name": "STOP",
                        "enabled": False,
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
            operations = await list_resource_operations(
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
    assert [item["id"] for item in operation_result.operations] == ["refresh"]
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


def test_authenticated_transport_rejects_redirect_without_forwarding_headers():
    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )
    seen_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_hosts.append(str(request.url.host))
        return httpx.Response(
            307,
            headers={"Location": "https://redirect.example/collect"},
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            await client.request_json("GET", "/nodes/search")

    with pytest.raises(SmartCmpUpstreamError, match="redirects are not allowed"):
        asyncio.run(invoke())

    assert seen_hosts == ["cmp.example"]


def test_mutation_redirect_has_unknown_outcome_without_following_location() -> None:
    """A rejected write redirect must not make a duplicate retry appear safe."""

    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )
    seen_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_hosts.append(str(request.url.host))
        return httpx.Response(
            303,
            headers={"Location": "https://redirect.example/collect"},
            request=request,
        )

    async def invoke() -> None:
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            await client.request_json("POST", "/requests", json_body={})

    with pytest.raises(SmartCmpUpstreamError) as exc_info:
        asyncio.run(invoke())

    assert exc_info.value.mutation_outcome == "unknown"
    assert seen_hosts == ["cmp.example"]


def test_password_login_rejects_redirect_without_replaying_digest():
    seen_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_hosts.append(str(request.url.host))
        return httpx.Response(
            307,
            headers={"Location": "https://redirect.example/collect"},
            request=request,
        )

    with pytest.raises(SmartCmpAuthenticationError, match="HTTP 307"):
        login_with_password(
            "https://cmp.example/platform-api/login",
            "admin",
            "password",
            transport=httpx.MockTransport(handler),
        )

    assert seen_hosts == ["cmp.example"]


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


def test_transport_redacts_secrets_echoed_by_upstream_errors():
    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "message": "credentialPassword=vm-secret is invalid",
                "request": {"password": "nested-secret"},
            },
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            await client.request_json("POST", "/generic-request/submit")

    with pytest.raises(SmartCmpValidationError) as exc_info:
        asyncio.run(invoke())

    rendered = str(exc_info.value)
    assert "vm-secret" not in rendered
    assert "nested-secret" not in rendered
    assert "[REDACTED]" in rendered


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


def test_password_login_does_not_expose_success_body_without_credentials():
    """A malformed login success response must not cross the error boundary."""

    password_digest = "5f4dcc3b5aa765d61d8327deb882cf99"
    bearer_token = "cmp_tk_secret"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": f"password={password_digest}",
                "message": f"Authorization: Bearer {bearer_token}",
            },
            request=request,
        )

    with pytest.raises(SmartCmpAuthenticationError) as exc_info:
        login_with_password(
            "https://cmp.example/platform-api/login",
            "admin",
            password_digest,
            transport=httpx.MockTransport(handler),
        )

    rendered = str(exc_info.value)
    assert "contains no cookies or tokens" in rendered
    assert password_digest not in rendered
    assert bearer_token not in rendered


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


def test_catalog_operation_normalizes_markdown_and_blueprint_fallbacks():
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
  params:
    computeProfileName:
      required: true

# Request Instructions

Collect the VM shape before submission.
""".strip()

    def handler(request: httpx.Request) -> httpx.Response:
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
            return await list_catalogs(client, CatalogListQuery())

    result = asyncio.run(invoke())

    assert result.total == 2
    assert result.catalogs[0]["componentType"] == (
        "resource.iaas.machine.instance.abstract"
    )
    assert result.catalogs[0]["instructions"]["resourceSpecs"][0]["node"] == (
        "Compute"
    )
    assert result.catalogs[0]["instructions"]["requestInstructions"] == (
        "Collect the VM shape before submission."
    )
    assert result.catalogs[1]["node"] == "LegacyCompute"
    assert result.catalogs[1]["type"] == "cloudchef.nodes.Compute"


def test_catalog_detail_rejects_a_different_response_id():
    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"id": "catalog-other", "name": "Wrong catalog"},
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            await get_catalog_detail(
                client,
                CatalogDetailQuery(catalog_id="catalog-selected"),
            )

    with pytest.raises(
        SmartCmpValidationError,
        match="returned a different catalog ID",
    ):
        asyncio.run(invoke())


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
    assert submitted[0]["userId"] == "user-1"
    assert submitted[0]["userLoginId"] == "admin"
    assert result.items[0].outcome == "success"
    assert result.items[0].request_id == "RES20260731009991"


def test_request_submission_stops_verification_after_first_confirmed_snapshot():
    """A confirmed snapshot must not be overwritten by later polling failures."""

    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )
    verification_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal verification_calls
        if request.url.path.endswith("/generic-request/submit"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "internal-request-id",
                        "workflowId": "RES20260731009992",
                        "state": "INITIALING",
                    }
                ],
                request=request,
            )
        verification_calls += 1
        if verification_calls > 1:
            return httpx.Response(
                500,
                json={"message": "late verification failure"},
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "workflowId": "RES20260731009992",
                "state": "STARTED",
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
                        "name": "confirmed-request",
                        "quantity": 1,
                    },
                    actor=RequestActorIdentity(
                        user_id="user-1",
                        login_id="admin",
                    ),
                    verification_attempts=3,
                    verification_interval_seconds=0,
                ),
            )

    result = asyncio.run(invoke())

    assert verification_calls == 1
    assert result.items[0].outcome == "success"
    assert result.items[0].request_id == "RES20260731009992"


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


def test_request_submission_redacts_credentials_from_verification_snapshot() -> None:
    """Failed request verification must sanitize SmartCMP error fields."""
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
                "errMsg": "password: vm-secret failed validation",
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
                    body={"catalogId": "catalog-linux", "name": "failed"},
                    actor=RequestActorIdentity(
                        user_id="user-1",
                        login_id="admin",
                    ),
                    verification_attempts=1,
                    verification_interval_seconds=0,
                ),
            )

    result = asyncio.run(invoke())

    assert result.items[0].outcome == "initialization_failed"
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


@pytest.mark.parametrize(
    "current_user_payload",
    [
        None,
        {"id": "robot-user-id"},
    ],
)
def test_robot_submission_stops_when_cmp_actor_cannot_be_resolved(
    current_user_payload,
):
    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="webhook-approval-1",
        token="cmp_tk_robot",
        robot_profile="cmp-test-robot",
    )
    submit_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal submit_calls
        if request.url.path.endswith("/users/current-user-details"):
            if current_user_payload is None:
                return httpx.Response(
                    401,
                    json={"message": "Robot credential rejected."},
                    request=request,
                )
            return httpx.Response(
                200,
                json=current_user_payload,
                request=request,
            )
        submit_calls += 1
        return httpx.Response(200, json=[], request=request)

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
                        "name": "robot-vm",
                        "userId": "stale-user-id",
                        "userLoginId": "stale-user",
                    },
                    verification_attempts=1,
                    verification_interval_seconds=0,
                ),
            )

    expected_error = (
        SmartCmpAuthenticationError
        if current_user_payload is None
        else SmartCmpUpstreamError
    )
    with pytest.raises(expected_error):
        asyncio.run(invoke())

    assert submit_calls == 0


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


def test_expired_submit_deadline_fails_before_http_without_unknown_outcome():
    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )
    expired_context = replace(
        request_scope.context,
        deadline=datetime.now(UTC) - timedelta(seconds=1),
    )
    expired_request = replace(request_scope, context=expired_context)
    submit_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal submit_calls
        submit_calls += 1
        return httpx.Response(200, json=[], request=request)

    async def invoke():
        async with SmartCmpClient(
            expired_request,
            transport=httpx.MockTransport(handler),
        ) as client:
            await submit_request(
                client,
                RequestSubmissionInput(
                    body={
                        "catalogId": "catalog-linux",
                        "name": "expired-vm",
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
        SmartCmpTimeoutError,
        match="deadline expired before the upstream call",
    ):
        asyncio.run(invoke())

    assert submit_calls == 0


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


def test_request_status_rejects_detail_for_a_different_visible_request():
    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )
    requested_id = "RES20260731009994"
    detail_id = "e7f746fe-e030-47df-945e-998254944335"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/generic-request/search"):
            return httpx.Response(
                200,
                json={
                    "content": [
                        {"id": detail_id, "workflowId": requested_id},
                    ]
                },
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "id": detail_id,
                "workflowId": "RES20260731009995",
                "state": "STARTED",
            },
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            await get_request_status(
                client,
                RequestStatusQuery(request_id=requested_id),
            )

    with pytest.raises(
        SmartCmpTargetResolutionError,
        match="returned a different Request ID",
    ):
        asyncio.run(invoke())


def test_request_status_rejects_conflicting_visible_request_aliases():
    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )
    requested_id = "RES20260731009996"
    detail_id = "ab2b48cf-4adb-49e9-9c24-95fe58497100"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/generic-request/search"):
            return httpx.Response(
                200,
                json={
                    "content": [
                        {"id": detail_id, "workflowId": requested_id},
                    ]
                },
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "id": detail_id,
                "requestId": "RES20260731009997",
                "workflowId": requested_id,
                "state": "STARTED",
            },
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            await get_request_status(
                client,
                RequestStatusQuery(request_id=requested_id),
            )

    with pytest.raises(
        SmartCmpTargetResolutionError,
        match="returned a different Request ID",
    ):
        asyncio.run(invoke())


@pytest.mark.parametrize("failure_endpoint", ["search", "detail"])
def test_request_status_preserves_authentication_error_type(failure_endpoint):
    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )
    request_id = "RES20260731009998"
    detail_id = "bd6ee27a-40df-41b7-bb70-74dc720bb269"

    def handler(request: httpx.Request) -> httpx.Response:
        is_search = request.url.path.endswith("/generic-request/search")
        if (
            failure_endpoint == "search"
            and is_search
            or failure_endpoint == "detail"
            and not is_search
        ):
            return httpx.Response(
                401,
                json={"message": "Credential expired."},
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "content": [
                    {"id": detail_id, "workflowId": request_id},
                ]
            },
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            await get_request_status(
                client,
                RequestStatusQuery(request_id=request_id),
            )

    with pytest.raises(SmartCmpAuthenticationError, match="HTTP 401"):
        asyncio.run(invoke())


def test_resource_summary_params_only_search_omits_json_body():
    """Params-only legacy searches must not gain an empty JSON request body."""

    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )
    seen: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(bytes(request.content))
        return httpx.Response(
            200,
            json={"content": [], "totalElements": 0},
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            return await search_resource_summaries(
                client,
                ResourceSummarySearchQuery(
                    params={"page": 1, "size": 100},
                ),
            )

    asyncio.run(invoke())
    assert seen == [b""]


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


def test_resource_evidence_falls_back_only_for_version_compatibility_status():
    """A 5xx view failure must propagate instead of invoking legacy GET."""

    request_scope = make_request(
        instance_name="cmp-a",
        base_url="https://cmp.example",
        user_id="user-a",
        token="session-a",
    )
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(
            500,
            json={"message": "view failed"},
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            await load_resource_evidence(
                client,
                ResourceEvidenceQuery(resource_ids=("resource-1",)),
            )

    with pytest.raises(SmartCmpUpstreamError):
        asyncio.run(invoke())
    assert seen == [
        ("PATCH", "/platform-api/nodes/resource-1/view"),
    ]
