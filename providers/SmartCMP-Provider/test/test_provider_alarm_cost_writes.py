"""Focused contracts for SmartCMP alarm and cost write operations."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

PROVIDER_ROOT = Path(__file__).resolve().parents[1]
PROVIDER_SRC = PROVIDER_ROOT / "src"
if str(PROVIDER_SRC) not in sys.path:
    sys.path.insert(0, str(PROVIDER_SRC))

from smartcmp_provider.auth.resolver import resolve_provided_request  # noqa: E402
from smartcmp_provider.errors import (  # noqa: E402
    SmartCmpUnknownOutcomeError,
    SmartCmpValidationError,
)
from smartcmp_provider.models.alarms import AlarmOperationInput  # noqa: E402
from smartcmp_provider.models.cost import CostExecutionInput  # noqa: E402
from smartcmp_provider.operations.alarms import (  # noqa: E402
    OPERATE_ALERT_CAPABILITY,
    execute_alarm_operation,
)
from smartcmp_provider.operations.cost import (  # noqa: E402
    EXECUTE_COST_OPTIMIZATION_CAPABILITY,
    execute_cost_optimization,
)
from smartcmp_provider.transport.client import SmartCmpClient  # noqa: E402


def make_request():
    """Create one isolated request scope for SmartCMP Provider write tests."""

    return resolve_provided_request(
        instance_name="cmp-test",
        base_url="https://cmp.example.com",
        subject="user-1",
        auth_type="cookie",
        credential_value="session-secret",
        trace_id="run-write-operations",
    )


def test_alarm_operation_preserves_endpoint_payload_and_confirmation_contract():
    """Alert updates use one non-retried PUT with a user-confirmed capability."""

    seen: list[tuple[str, str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            (
                request.method,
                request.url.path,
                json.loads(request.content),
            )
        )
        return httpx.Response(200, json={"updated": 2}, request=request)

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await execute_alarm_operation(
                client,
                AlarmOperationInput(
                    alert_ids=("alert-1", "alert-2"),
                    action="resolve",
                ),
            )

    result = asyncio.run(invoke())

    assert seen == [
        (
            "PUT",
            "/platform-api/alarm-alert/operation",
            {
                "ids": ["alert-1", "alert-2"],
                "status": "ALERT_RESOLVED",
            },
        )
    ]
    assert result.status == "ALERT_RESOLVED"
    assert result.response == {"updated": 2}
    assert OPERATE_ALERT_CAPABILITY.effect == "write"
    assert OPERATE_ALERT_CAPABILITY.idempotency == "non_idempotent"
    assert OPERATE_ALERT_CAPABILITY.confirmation == "user"


def test_cost_execution_quotes_target_and_preserves_confirmation_contract():
    """Cost remediation uses the exact violation endpoint and an empty body."""

    seen: list[tuple[str, str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            (
                request.method,
                request.url.path,
                json.loads(request.content),
            )
        )
        return httpx.Response(
            200,
            json={"taskInstanceId": "task-1"},
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await execute_cost_optimization(
                client,
                CostExecutionInput(violation_id="vio/1"),
            )

    result = asyncio.run(invoke())

    assert seen == [
        (
            "POST",
            "/platform-api/compliance-policies/violations/day2/fix/vio/1",
            {},
        )
    ]
    assert result.violation_id == "vio/1"
    assert result.response == {"taskInstanceId": "task-1"}
    assert EXECUTE_COST_OPTIMIZATION_CAPABILITY.effect == "write"
    assert EXECUTE_COST_OPTIMIZATION_CAPABILITY.idempotency == "non_idempotent"
    assert EXECUTE_COST_OPTIMIZATION_CAPABILITY.confirmation == "user"


@pytest.mark.parametrize(
    ("operation", "operation_input"),
    [
        (
            execute_alarm_operation,
            AlarmOperationInput(alert_ids=("alert-1",), action="mute"),
        ),
        (
            execute_cost_optimization,
            CostExecutionInput(violation_id="vio-1"),
        ),
    ],
)
def test_write_transport_failure_is_reported_as_unknown_outcome(
    operation,
    operation_input,
):
    """A transport failure after write start must prohibit automatic retry."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection lost", request=request)

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            await operation(client, operation_input)

    with pytest.raises(SmartCmpUnknownOutcomeError, match="do not retry"):
        asyncio.run(invoke())


def test_definite_cost_validation_failure_remains_validation_error():
    """A definite upstream 400 must not be mislabeled as unknown outcome."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"message": "no repair action configured"},
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            await execute_cost_optimization(
                client,
                CostExecutionInput(violation_id="vio-1"),
            )

    with pytest.raises(SmartCmpValidationError, match="no repair action configured"):
        asyncio.run(invoke())


@pytest.mark.parametrize(
    ("operation", "operation_input", "status_code"),
    [
        (
            execute_alarm_operation,
            AlarmOperationInput(alert_ids=("alert-1",), action="resolve"),
            204,
        ),
        (
            execute_cost_optimization,
            CostExecutionInput(violation_id="vio-1"),
            200,
        ),
    ],
)
def test_write_operations_accept_contractually_empty_success(
    operation,
    operation_input,
    status_code,
):
    """Legacy-compatible empty write responses must remain successful."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, content=b"", request=request)

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await operation(client, operation_input)

    result = asyncio.run(invoke())
    assert result.response == {}
