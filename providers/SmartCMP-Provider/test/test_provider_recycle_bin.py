"""Focused contracts for SmartCMP recycle-bin permanent removal."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from smartcmp_provider.auth.resolver import resolve_provided_request
from smartcmp_provider.errors import (
    SmartCmpTargetResolutionError,
    SmartCmpUnknownOutcomeError,
    SmartCmpUpstreamError,
    SmartCmpValidationError,
)
from smartcmp_provider.models.operations import (
    ResourceActionInput,
    ResourceActionTarget,
)
from smartcmp_provider.models.resources import (
    PermanentResourceRemovalInput,
    RecycledResourceQuery,
)
from smartcmp_provider.operations.recycle_bin import (
    list_recycled_resources,
    permanently_remove_recycled_resource,
)
from smartcmp_provider.operations.resource_actions import execute_resource_action
from smartcmp_provider.transport.client import SmartCmpClient

DEPLOYMENT = {
    "id": "dep-1",
    "name": "Application A",
    "state": "RECYCLED",
    "deleted": False,
    "recycled": True,
}
RESOURCES = [
    {"id": "vm-1", "name": "vm-a", "status": "deleted"},
    {"id": "vm-2", "name": "vm-b", "status": "deleted"},
]
PURGE_ACTION = {
    "id": "permanently_delete_deployment",
    "enabled": True,
    "parameters": {},
}
EXPECTED_PURGE_REQUEST = {
    "operationName": "permanently_delete_deployment",
    "scheduledTaskMetadataRequest": {
        "cronExpression": "",
        "cycleDescription": "",
        "cycled": False,
        "scheduleEnabled": False,
        "scheduledTime": None,
    },
    "operationParamJson": '{"systemForm":null}',
    "recycle": True,
    "manual": True,
}


class RecycleApiStub:
    """Serve configurable recycle-bin responses and retain observed writes."""

    def __init__(
        self,
        *,
        deployments: list[dict[str, Any]] | None = None,
        resources: dict[str, Any] | None = None,
        actions: dict[str, Any] | None = None,
        deployment_pages: list[dict[str, Any]] | None = None,
        total: int | None = None,
        post_response: Any = None,
        post_timeout: bool = False,
    ) -> None:
        self.deployments = deployments if deployments is not None else [DEPLOYMENT]
        self.resources = resources if resources is not None else {"dep-1": RESOURCES}
        self.actions = actions if actions is not None else {"dep-1": [PURGE_ACTION]}
        self.deployment_pages = deployment_pages
        self.total = len(self.deployments) if total is None else total
        self.post_response = (
            {"results": {"dep-1": {"id": "task-1"}}}
            if post_response is None
            else post_response
        )
        self.post_timeout = post_timeout
        self.requests: list[httpx.Request] = []
        self.writes: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Return one response matching the SmartCMP recycle-bin contract."""

        self.requests.append(request)
        path = request.url.path
        if request.method == "POST":
            assert path.endswith("/deployments/execute-action")
            self.writes.append(json.loads(request.content))
            if self.post_timeout:
                raise httpx.ReadTimeout("response lost", request=request)
            return httpx.Response(200, json=self.post_response, request=request)
        if path.endswith("/deployments"):
            if self.deployment_pages is not None:
                payload = self.deployment_pages[int(request.url.params["page"]) - 1]
            else:
                payload = {
                    "content": self.deployments,
                    "totalElements": self.total,
                    "totalPages": 1,
                }
            return httpx.Response(200, json=payload, request=request)
        deployment_id = request.url.params.get("deploymentId")
        if path.endswith("/nodes/deleted"):
            return httpx.Response(
                200,
                json=self.resources.get(str(deployment_id), []),
                request=request,
            )
        if path.endswith("/deployment-actions"):
            deployment_id = path.split("/deployments/", 1)[1].split("/", 1)[0]
            return httpx.Response(
                200,
                json=self.actions.get(deployment_id, []),
                request=request,
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")


def _request_scope():
    return resolve_provided_request(
        instance_name="cmp-test",
        base_url="https://cmp.example.com",
        subject="user-1",
        actor_type="user",
        auth_type="cookie",
        credential_value="session-1",
        trace_id="recycle-bin-test",
    )


async def _list(api: RecycleApiStub, query: RecycledResourceQuery):
    async with SmartCmpClient(
        _request_scope(), transport=httpx.MockTransport(api)
    ) as client:
        return await list_recycled_resources(client, query)


async def _remove(
    api: RecycleApiStub,
    action_input: PermanentResourceRemovalInput,
):
    async with SmartCmpClient(
        _request_scope(), transport=httpx.MockTransport(api)
    ) as client:
        return await permanently_remove_recycled_resource(client, action_input)


def _removal_input(**overrides: Any) -> PermanentResourceRemovalInput:
    values = {
        "deployment_id": "dep-1",
        "confirmed": True,
        "expected_deployment_id": "dep-1",
        "expected_resource_ids": ("vm-1", "vm-2"),
    }
    values.update(overrides)
    return PermanentResourceRemovalInput(**values)


def test_list_exposes_owning_scope_and_bound_permanent_action():
    api = RecycleApiStub(total=3)

    result = asyncio.run(_list(api, RecycledResourceQuery(page=2, size=10)))

    assert (result.total, result.page, result.size) == (3, 2, 10)
    row = result.items[0]
    assert row["owning_deployment"] == {
        **DEPLOYMENT,
        "recycle_delete_time": None,
    }
    assert row["affected_scope"]["resource_ids"] == ("vm-1", "vm-2")
    operation = row["available_operations"][0]
    assert operation["tool_name"] == "smartcmp_permanently_remove_recycled_resource"
    assert operation["arguments"] == {
        "resource_id": "vm-1",
        "expected_deployment_id": "dep-1",
        "expected_resource_ids": ["vm-1", "vm-2"],
    }
    assert operation["required_inputs"] == ["confirmed"]
    assert api.requests[0].url.params["page"] == "2"
    assert api.requests[-1].url.params["recycled"] == "true"


def test_list_rejects_unbounded_page_size():
    with pytest.raises(ValueError):
        RecycledResourceQuery(size=101)


def test_list_rejects_multiple_locators_before_io():
    api = RecycleApiStub()

    with pytest.raises(SmartCmpValidationError, match="at most one"):
        asyncio.run(
            _list(
                api,
                RecycledResourceQuery(resource_id="vm-1", deployment_id="dep-1"),
            )
        )

    assert api.requests == []


@pytest.mark.parametrize(
    "locator",
    [
        {"resource_id": "vm-1"},
        {"resource_name": "vm-a"},
        {"deployment_id": "dep-1"},
        {"deployment_name": "Application A"},
    ],
)
def test_all_four_locators_resolve_the_same_deployment(locator: dict[str, str]):
    api = RecycleApiStub()

    result = asyncio.run(_list(api, RecycledResourceQuery(**locator)))

    assert result.total == 1
    assert {row["deployment_id"] for row in result.items} == {"dep-1"}


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"confirmed": False}, "confirmed must be true"),
        ({"deployment_id": ""}, "exactly one"),
        ({"resource_id": "vm-1"}, "exactly one"),
    ],
)
def test_removal_rejects_invalid_confirmation_or_locator_before_io(
    overrides: dict[str, Any],
    message: str,
):
    api = RecycleApiStub()

    with pytest.raises(SmartCmpValidationError, match=message):
        asyncio.run(_remove(api, _removal_input(**overrides)))

    assert api.requests == []


def test_resource_name_ambiguity_fails_before_write():
    deployments = [
        {"id": "dep-1", "name": "Application A"},
        {"id": "dep-2", "name": "Application B"},
    ]
    api = RecycleApiStub(
        deployments=deployments,
        resources={
            "dep-1": [{"id": "vm-1", "name": "duplicate-vm"}],
            "dep-2": [{"id": "vm-2", "name": "duplicate-vm"}],
        },
    )

    with pytest.raises(
        SmartCmpTargetResolutionError, match="ambiguous recycled ownership"
    ):
        asyncio.run(
            _remove(
                api,
                _removal_input(
                    deployment_id="",
                    resource_name="duplicate-vm",
                ),
            )
        )

    assert api.writes == []


@pytest.mark.parametrize(
    ("expected_deployment_id", "expected_resource_ids"),
    [("dep-stale", ("vm-1", "vm-2")), ("dep-1", ("vm-1",))],
)
def test_changed_confirmation_scope_fails_before_write(
    expected_deployment_id: str,
    expected_resource_ids: tuple[str, ...],
):
    api = RecycleApiStub()

    with pytest.raises(SmartCmpValidationError, match="changed after confirmation"):
        asyncio.run(
            _remove(
                api,
                _removal_input(
                    expected_deployment_id=expected_deployment_id,
                    expected_resource_ids=expected_resource_ids,
                ),
            )
        )

    assert api.writes == []


@pytest.mark.parametrize(
    "payload",
    [{"unexpected": []}, "not-a-resource-list", [{"name": "missing-id"}]],
)
def test_invalid_deleted_resource_payload_fails_closed(payload: Any):
    api = RecycleApiStub(resources={"dep-1": payload})

    with pytest.raises(SmartCmpUpstreamError):
        asyncio.run(_list(api, RecycledResourceQuery()))


def test_terminal_recycle_row_has_no_permanent_action():
    deployment = {
        **DEPLOYMENT,
        "state": "DELETED",
        "deleted": True,
        "recycleDeleteTime": 1786556400000,
    }
    api = RecycleApiStub(deployments=[deployment])

    row = asyncio.run(_list(api, RecycledResourceQuery())).items[0]

    assert row["owning_deployment"]["state"] == "DELETED"
    assert row["owning_deployment"]["deleted"] is True
    assert row["owning_deployment"]["recycle_delete_time"] == 1786556400000
    assert row["available_operations"] == []
    assert not any(
        request.url.path.endswith("/deployment-actions")
        for request in api.requests
    )


def test_deleted_tombstone_does_not_block_live_recycled_deployment():
    deployments = [
        {**DEPLOYMENT, "state": "DELETED", "deleted": True},
        {**DEPLOYMENT, "id": "dep-2", "name": "Application B"},
    ]
    api = RecycleApiStub(
        deployments=deployments,
        resources={"dep-1": RESOURCES, "dep-2": [{"id": "vm-3", "name": "vm-c"}]},
        actions={"dep-2": [PURGE_ACTION]},
    )

    result = asyncio.run(_list(api, RecycledResourceQuery()))

    rows = {row["resource_id"]: row for row in result.items}
    assert rows["vm-1"]["available_operations"] == []
    assert rows["vm-3"]["available_operations"][0]["operation_id"] == (
        "permanently_delete_deployment"
    )
    action_paths = [
        request.url.path
        for request in api.requests
        if request.url.path.endswith("/deployment-actions")
    ]
    assert action_paths == [
        "/platform-api/deployments/dep-2/deployment-actions"
    ]


def test_deleted_tombstone_rejects_permanent_removal_before_action_or_write():
    deployment = {**DEPLOYMENT, "state": "DELETED", "deleted": True}
    api = RecycleApiStub(deployments=[deployment])

    with pytest.raises(SmartCmpValidationError, match="deleted tombstone"):
        asyncio.run(_remove(api, _removal_input()))

    assert not any(
        request.url.path.endswith("/deployment-actions")
        for request in api.requests
    )
    assert api.writes == []


def test_locator_follows_authoritative_total_pages():
    api = RecycleApiStub(
        deployment_pages=[
            {
                "content": [{"id": "dep-1", "name": "Application A"}],
                "totalPages": 2,
            },
            {
                "content": [{"id": "dep-2", "name": "Application B"}],
                "totalPages": 2,
            },
        ],
        resources={
            "dep-2": [
                {"id": "vm-2", "name": "vm-b"},
                {"id": "disk-2", "name": "disk-b"},
            ]
        },
        actions={"dep-2": []},
    )

    result = asyncio.run(
        _list(api, RecycledResourceQuery(deployment_id="dep-2"))
    )

    deployment_pages = [
        int(request.url.params["page"])
        for request in api.requests
        if request.url.path.endswith("/deployments")
    ]
    assert deployment_pages == [1, 2]
    assert result.total == 1
    assert len(result.items) == 2


def test_permanent_removal_rechecks_action_and_submits_exactly_once():
    api = RecycleApiStub()

    result = asyncio.run(
        _remove(
            api,
            _removal_input(
                deployment_id="",
                resource_id="vm-1",
                expected_resource_ids=("vm-2", "vm-1"),
            ),
        )
    )

    assert api.writes == [{"dep-1": EXPECTED_PURGE_REQUEST}]
    assert sum(
        request.url.path.endswith("/deployment-actions")
        for request in api.requests
    ) == 1
    assert result.submitted is True
    assert result.affected_resources == (
        {"resource_id": "vm-1", "resource_name": "vm-a", "status": "deleted"},
        {"resource_id": "vm-2", "resource_name": "vm-b", "status": "deleted"},
    )
    assert "submitted" in result.message
    assert "does not mean deletion is complete" in result.verification_hint


@pytest.mark.parametrize("outcome", ["timeout", "missing-result"])
def test_unknown_write_outcome_is_not_retried(outcome: str):
    api = RecycleApiStub(
        resources={"dep-1": []},
        post_timeout=outcome == "timeout",
        post_response={"results": {"other-deployment": {"id": "task-1"}}},
    )

    with pytest.raises(SmartCmpUnknownOutcomeError, match="do not retry"):
        asyncio.run(
            _remove(api, _removal_input(expected_resource_ids=()))
        )

    assert len(api.writes) == 1


def test_deployment_only_removal_has_no_synthetic_resource():
    api = RecycleApiStub(resources={"dep-1": []})

    result = asyncio.run(_remove(api, _removal_input(expected_resource_ids=())))

    assert result.affected_resources == ()


def test_generic_operation_cannot_bypass_dedicated_removal():
    api = RecycleApiStub()

    async def invoke():
        async with SmartCmpClient(
            _request_scope(), transport=httpx.MockTransport(api)
        ) as client:
            await execute_resource_action(
                client,
                ResourceActionInput(
                    targets=(
                        ResourceActionTarget(
                            category="deployments",
                            resource_id="dep-1",
                        ),
                    ),
                    action="permanently_delete_deployment",
                ),
            )

    with pytest.raises(SmartCmpValidationError, match="dedicated"):
        asyncio.run(invoke())
    assert api.requests == []
