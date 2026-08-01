"""Focused contracts for approval and resource writes migrated in Step 4."""

from __future__ import annotations

import asyncio
import sys
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

    from smartcmp_provider.auth.resolver import (
        resolve_provided_request,
    )
    from smartcmp_provider.errors import (
        SmartCmpTargetResolutionError,
        SmartCmpUnknownOutcomeError,
        SmartCmpValidationError,
    )
    from smartcmp_provider.domain.views import project_approval_item
    from smartcmp_provider.models.approvals import (
        ApprovalDecisionInput,
        ApprovalDetailQuery,
    )
    from smartcmp_provider.models.operations import (
        ResourceActionInput,
        ResourceActionTarget,
    )
    from smartcmp_provider.operations.approvals import (
        APPROVE_CAPABILITY,
        LIST_PENDING_APPROVALS_CAPABILITY,
        REJECT_CAPABILITY,
        execute_approval_decision,
        get_pending_approval_detail,
    )
    from smartcmp_provider.operations.resource_actions import (
        LIST_RESOURCE_OPERATIONS_CAPABILITY,
        OPERATE_RESOURCE_CAPABILITY,
        execute_resource_action,
    )
    from smartcmp_provider.transport.client import SmartCmpClient
finally:
    for _MODULE_NAME in list(sys.modules):
        if _MODULE_NAME == "smartcmp_provider" or _MODULE_NAME.startswith(
            "smartcmp_provider."
        ):
            sys.modules.pop(_MODULE_NAME, None)
    sys.modules.update(_ORIGINAL_PROVIDER_MODULES)
    sys.path[:] = _ORIGINAL_PATH


def make_request(*, robot: bool = False):
    """Create one isolated test request with a user or robot credential."""

    return resolve_provided_request(
        instance_name="cmp-test",
        base_url="https://cmp.example.com",
        subject="actor-1",
        actor_type="robot" if robot else "user",
        client_id="robot-admin" if robot else None,
        auth_type="provider_token" if robot else "cookie",
        credential_value="cmp_tk_robot" if robot else "user-session",
        trace_id="run-step-4",
    )


def test_batch_approval_resolves_visible_ids_and_reports_partial_failure():
    post_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_count
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "content": [
                        {
                            "workflowId": "RES20260505000010",
                            "currentActivity": {"id": "activity-internal-1"},
                        },
                        {
                            "requestId": "TIC20260502000003",
                            "currentActivity": {"id": "activity-internal-2"},
                        },
                    ]
                },
                request=request,
            )
        post_count += 1
        assert request.url.params["ids"] == (
            "activity-internal-1,activity-internal-2"
        )
        return httpx.Response(
            200,
            json=[
                {
                    "id": "response-row-id-2",
                    "activityId": "activity-internal-2",
                    "success": False,
                    "status": "failed",
                    "message": (
                        "could not approve activity-internal-secret-id"
                    ),
                },
                {
                    "id": "response-row-id-1",
                    "activityId": "activity-internal-1",
                    "success": True,
                    "status": "approved",
                },
            ],
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await execute_approval_decision(
                client,
                ApprovalDecisionInput(
                    decision="approve",
                    request_ids=(
                        "RES20260505000010",
                        "TIC20260502000003",
                    ),
                ),
            )

    result = asyncio.run(invoke())

    assert post_count == 1
    assert result.overall_success is False
    assert [item.request_id for item in result.items] == [
        "RES20260505000010",
        "TIC20260502000003",
    ]
    assert [item.outcome for item in result.items] == ["succeeded", "failed"]
    assert "activity-internal" not in result.model_dump_json()
    assert "secret-id" not in result.model_dump_json()
    assert result.items[1].message == (
        "SmartCMP reported an item-level decision failure."
    )


def test_approval_detail_preserves_five_page_lookup_and_finds_page_two():
    requested_pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        requested_pages.append(page)
        if page == 1:
            rows = [
                {
                    "workflowId": f"RES20260101{index:06d}",
                    "currentActivity": {"id": f"activity-{index}"},
                }
                for index in range(50)
            ]
        else:
            rows = [
                {
                    "workflowId": "RES20260505000010",
                    "currentActivity": {"id": "activity-target"},
                }
            ]
        return httpx.Response(
            200,
            json={"content": rows, "totalElements": 51},
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await get_pending_approval_detail(
                client,
                ApprovalDetailQuery(
                    request_id="RES20260505000010",
                    max_attempts=1,
                    retry_interval_seconds=0,
                ),
            )

    result = asyncio.run(invoke())

    assert requested_pages == [1, 2]
    assert result.request_id == "RES20260505000010"
    assert result.item["currentActivity"]["id"] == "activity-target"


def test_approval_detail_successful_empty_retry_clears_prior_transport_error():
    attempt = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempt
        attempt += 1
        if attempt == 1:
            raise httpx.ReadTimeout("temporary timeout", request=request)
        return httpx.Response(
            200,
            json={"content": [], "totalElements": 0},
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            await get_pending_approval_detail(
                client,
                ApprovalDetailQuery(
                    request_id="RES20260505000010",
                    max_attempts=2,
                    retry_interval_seconds=0,
                ),
            )

    with pytest.raises(
        SmartCmpTargetResolutionError,
        match="No pending SmartCMP approval matched",
    ):
        asyncio.run(invoke())
    assert attempt == 2


def test_approval_conflicting_visible_ids_fails_before_write():
    post_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_count
        if request.method == "POST":
            post_count += 1
            raise AssertionError("ambiguous approval must not be submitted")
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "workflowId": "RES20260505000010",
                        "requestId": "TIC20260502000003",
                        "currentActivity": {"id": "activity-internal-1"},
                    }
                ]
            },
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            await execute_approval_decision(
                client,
                ApprovalDecisionInput(
                    decision="approve",
                    request_ids=("RES20260505000010",),
                ),
            )

    with pytest.raises(
        SmartCmpTargetResolutionError,
        match="conflicting Request IDs",
    ):
        asyncio.run(invoke())
    assert post_count == 0


def test_different_request_ids_cannot_resolve_to_same_activity():
    post_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_count
        if request.method == "POST":
            post_count += 1
            raise AssertionError("duplicate activity must not be submitted")
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "workflowId": "RES20260505000010",
                        "currentActivity": {"id": "shared-activity"},
                    },
                    {
                        "workflowId": "TIC20260502000003",
                        "currentActivity": {"id": "shared-activity"},
                    },
                ]
            },
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            await execute_approval_decision(
                client,
                ApprovalDecisionInput(
                    decision="approve",
                    request_ids=(
                        "RES20260505000010",
                        "TIC20260502000003",
                    ),
                ),
            )

    with pytest.raises(
        SmartCmpTargetResolutionError,
        match="same current approval activity",
    ):
        asyncio.run(invoke())
    assert post_count == 0


def test_unknown_response_activity_is_not_positionally_misattributed():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "content": [
                        {
                            "workflowId": "RES20260505000010",
                            "currentActivity": {"id": "activity-internal-1"},
                        }
                    ]
                },
                request=request,
            )
        return httpx.Response(
            200,
            json=[
                {
                    "activityId": "foreign-activity",
                    "success": True,
                    "status": "approved",
                }
            ],
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await execute_approval_decision(
                client,
                ApprovalDecisionInput(
                    decision="approve",
                    request_ids=("RES20260505000010",),
                ),
            )

    result = asyncio.run(invoke())

    assert result.overall_success is False
    assert result.items[0].outcome == "unknown"
    assert result.items[0].request_id == "RES20260505000010"


def test_unidentified_partial_response_count_mismatch_is_all_unknown():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "content": [
                        {
                            "workflowId": "RES20260505000010",
                            "currentActivity": {"id": "activity-internal-1"},
                        },
                        {
                            "workflowId": "TIC20260502000003",
                            "currentActivity": {"id": "activity-internal-2"},
                        },
                    ]
                },
                request=request,
            )
        return httpx.Response(
            200,
            json=[{"success": False, "status": "failed"}],
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await execute_approval_decision(
                client,
                ApprovalDecisionInput(
                    decision="approve",
                    request_ids=(
                        "RES20260505000010",
                        "TIC20260502000003",
                    ),
                ),
            )

    result = asyncio.run(invoke())

    assert result.overall_success is False
    assert [item.outcome for item in result.items] == ["unknown", "unknown"]


def test_approval_unknown_write_result_is_not_retried():
    post_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_count
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "content": [
                        {
                            "workflowId": "RES20260505000010",
                            "currentActivity": {"id": "activity-internal-1"},
                        }
                    ]
                },
                request=request,
            )
        post_count += 1
        raise httpx.ReadTimeout("response lost", request=request)

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            await execute_approval_decision(
                client,
                ApprovalDecisionInput(
                    decision="approve",
                    request_ids=("RES20260505000010",),
                ),
            )

    with pytest.raises(SmartCmpUnknownOutcomeError, match="do not retry"):
        asyncio.run(invoke())
    assert post_count == 1


def test_reject_response_status_is_a_successful_rejection():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "content": [
                        {
                            "workflowId": "RES20260505000010",
                            "currentActivity": {"id": "activity-internal-1"},
                        }
                    ]
                },
                request=request,
            )
        return httpx.Response(
            200,
            json=[
                {
                    "activityId": "activity-internal-1",
                    "success": True,
                    "status": "rejected",
                }
            ],
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await execute_approval_decision(
                client,
                ApprovalDecisionInput(
                    decision="reject",
                    request_ids=("RES20260505000010",),
                ),
            )

    result = asyncio.run(invoke())

    assert result.overall_success is True
    assert result.items[0].outcome == "succeeded"
    assert result.items[0].status == "rejected"


def test_reject_opposite_approved_status_is_not_reported_as_success():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "content": [
                        {
                            "workflowId": "RES20260505000010",
                            "currentActivity": {"id": "activity-internal-1"},
                        }
                    ]
                },
                request=request,
            )
        return httpx.Response(
            200,
            json=[
                {
                    "activityId": "activity-internal-1",
                    "status": "approved",
                }
            ],
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await execute_approval_decision(
                client,
                ApprovalDecisionInput(
                    decision="reject",
                    request_ids=("RES20260505000010",),
                ),
            )

    result = asyncio.run(invoke())

    assert result.overall_success is False
    assert result.items[0].outcome == "failed"
    assert result.items[0].status == "failed"


def test_resource_action_uses_current_robot_operations_and_submits_once():
    get_count = 0
    post_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal get_count, post_count
        assert request.headers["Authorization"] == "Bearer cmp_tk_robot"
        assert "CloudChef-Authenticate" not in request.headers
        if request.method == "GET":
            get_count += 1
            assert request.url.path.endswith(
                "/nodes/virtual-machines/resource-1/resource-actions"
            )
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "stop",
                        "enabled": True,
                        "parameters": "{}",
                        "inputsForm": None,
                        "webOperation": False,
                    }
                ],
                request=request,
            )
        post_count += 1
        assert request.url.path.endswith("/nodes/resource-operations")
        return httpx.Response(
            200,
            json={"taskId": "internal-task-id"},
            request=request,
        )

    async def invoke():
        request = make_request(robot=True)
        assert request.context.principal.actor_type == "robot"
        async with SmartCmpClient(
            request,
            transport=httpx.MockTransport(handler),
        ) as client:
            return await execute_resource_action(
                client,
                ResourceActionInput(
                    targets=(
                        ResourceActionTarget(
                            category="virtual-machines",
                            resource_id="resource-1",
                        ),
                    ),
                    action="stop",
                ),
            )

    result = asyncio.run(invoke())

    assert get_count == 1
    assert post_count == 1
    assert result.resource_ids == ("resource-1",)
    assert "internal-task-id" not in result.model_dump_json()


def test_resource_action_rejects_disabled_current_user_operation_before_post():
    post_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_count
        if request.method == "POST":
            post_count += 1
            raise AssertionError("disabled operation must not be submitted")
        return httpx.Response(
            200,
            json=[
                {
                    "id": "stop",
                    "enabled": False,
                    "disabledMsgZh": "请先启动实例",
                }
            ],
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            await execute_resource_action(
                client,
                ResourceActionInput(
                    targets=(
                        ResourceActionTarget(
                            category="virtual-machines",
                            resource_id="resource-1",
                        ),
                    ),
                    action="stop",
                ),
            )

    with pytest.raises(SmartCmpValidationError, match="请先启动实例"):
        asyncio.run(invoke())
    assert post_count == 0


def test_resource_action_rejects_unsupported_batch_before_post():
    post_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_count
        if request.method == "POST":
            post_count += 1
            raise AssertionError("unsupported batch must not be submitted")
        return httpx.Response(
            200,
            json=[
                {
                    "id": "stop",
                    "enabled": True,
                    "parameters": "{}",
                    "supportBatchAction": False,
                }
            ],
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            await execute_resource_action(
                client,
                ResourceActionInput(
                    targets=(
                        ResourceActionTarget(
                            category="virtual-machines",
                            resource_id="resource-1",
                        ),
                        ResourceActionTarget(
                            category="virtual-machines",
                            resource_id="resource-2",
                        ),
                    ),
                    action="stop",
                ),
            )

    with pytest.raises(
        SmartCmpValidationError,
        match="does not support batch execution",
    ):
        asyncio.run(invoke())
    assert post_count == 0


def test_resource_action_unknown_write_result_is_not_retried():
    post_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_count
        if request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "start",
                        "enabled": True,
                        "parameters": "{}",
                    }
                ],
                request=request,
            )
        post_count += 1
        raise httpx.ReadTimeout("response lost", request=request)

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            await execute_resource_action(
                client,
                ResourceActionInput(
                    targets=(
                        ResourceActionTarget(
                            category="virtual-machines",
                            resource_id="resource-1",
                        ),
                    ),
                    action="start",
                ),
            )

    with pytest.raises(SmartCmpUnknownOutcomeError, match="do not retry"):
        asyncio.run(invoke())
    assert post_count == 1


def test_step_4_capabilities_declare_read_and_confirmation_boundaries():
    """Prevent adapters from silently weakening write confirmation semantics."""

    for capability in (
        LIST_PENDING_APPROVALS_CAPABILITY,
        LIST_RESOURCE_OPERATIONS_CAPABILITY,
    ):
        assert capability.effect == "read"
        assert capability.idempotency == "safe"
        assert capability.confirmation == "none"

    for capability in (
        APPROVE_CAPABILITY,
        REJECT_CAPABILITY,
        OPERATE_RESOURCE_CAPABILITY,
    ):
        assert capability.effect == "write"
        assert capability.idempotency == "non_idempotent"
        assert capability.confirmation == "user"
        assert capability.mcp_tool_name == capability.atlasclaw_tool_name
        assert capability.surfaces == frozenset({"atlasclaw", "mcp"})


def test_approval_projection_never_uses_an_unrelated_extensible_block():
    """Non-Compute parameters must not become CPU or memory evidence."""

    projected = project_approval_item(
        {
            "workflowId": "RES20260731000001",
            "currentActivity": {
                "requestParams": {
                    "extensibleParameters": {
                        "Other": {
                            "cpus": {"value": 999},
                            "memory": {"value": 999999},
                        },
                        "Compute": {},
                    }
                }
            },
        }
    )

    assert projected.resource_specifications == {}
