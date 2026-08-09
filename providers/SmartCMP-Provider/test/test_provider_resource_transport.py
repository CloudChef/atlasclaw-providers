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
        SmartCmpTimeoutError,
        SmartCmpUnknownOutcomeError,
        SmartCmpUpstreamError,
        SmartCmpValidationError,
    )
    from smartcmp_provider.models.catalogs import (
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
        list_resource_operations,
        list_resources,
    )
    from smartcmp_provider.operations.catalogs import (
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


def test_resource_bundle_resolves_declared_placement_fields() -> None:
    """Resolve one resource-pool lookup and report remaining required fields."""

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
            return httpx.Response(200, json=[], request=request)
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
                                        "required": {"inRequest": {"value": True}},
                                        "cloudResourceType": "generic-resource",
                                        "queryProperties": {"resourceType": "vpc"},
                                        "dependencies": {
                                            "account_id": "accountId",
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
            body = json.loads(request.content)
            assert body["queryProperties"] == {
                "resourceType": "vpc",
                "resourceBundleId": "resource-bundle-1",
                "accountId": "account-1",
            }
            return httpx.Response(
                200,
                json=[{"id": "vpc-a", "name": "VPC A"}],
                request=request,
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    async def invoke():
        async with SmartCmpClient(
            request_scope,
            transport=httpx.MockTransport(handler),
        ) as client:
            pending = await list_resource_bundles(
                client,
                ResourceBundleQuery(
                    business_group_id="business-group-1",
                    component_type="cloudchef.nodes.SecurityGroup",
                    node_type="cloudchef.nodes.SecurityGroup",
                    resource_bundle_id="resource-bundle-1",
                    placement_fields=("vpc_id",),
                    placement_values={
                        "catalogId": "catalog-1",
                        "node": "SecurityGroup",
                    },
                ),
            )
            complete = await list_resource_bundles(
                client,
                ResourceBundleQuery(
                    business_group_id="business-group-1",
                    component_type="cloudchef.nodes.SecurityGroup",
                    node_type="cloudchef.nodes.SecurityGroup",
                    resource_bundle_id="resource-bundle-1",
                    placement_values={
                        "catalogId": "catalog-1",
                        "node": "SecurityGroup",
                        "vpc_id": "vpc-a",
                        "group_description": "MCP acceptance group",
                    },
                ),
            )
            return pending, complete

    pending, complete = asyncio.run(invoke())

    fields = {
        field["key"]: field
        for field in pending.items[0]["requestFields"]
    }
    assert fields["account_id"]["value"] == "account-1"
    assert fields["vpc_id"]["dependsOn"] == ["account_id"]
    assert pending.items[0]["placementOptions"]["vpc_id"][0]["id"] == "vpc-a"
    assert set(pending.items[0]["missingRequiredFields"]) == {
        "vpc_id",
        "group_description",
    }
    assert complete.items[0]["valid"] is True


@pytest.mark.parametrize(
    ("action", "extra"),
    [
        ("Tear Down", {}),
        ("permanently_delete_deployment", {"recycle": True, "manual": True}),
    ],
)
def test_deployment_operation_rechecks_and_submits_once(action: str, extra: dict) -> None:
    """Deployment actions preserve the exact current operation contract."""

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
                    "id": action,
                    "enabled": True,
                    "supportBatchAction": True,
                    "parameters": {},
                }],
                request=request,
            )
        submitted.append(json.loads(request.content))
        assert request.url.path.endswith("/deployments/execute-action")
        return httpx.Response(200, json={"success": True}, request=request)

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
                    action=action,
                ),
            )

    result = asyncio.run(invoke())

    assert result.submitted is True
    assert len(submitted) == 1
    deployment_request = submitted[0]["deployment-1"]
    assert deployment_request["operationName"] == action
    assert {key: deployment_request[key] for key in extra} == extra




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
