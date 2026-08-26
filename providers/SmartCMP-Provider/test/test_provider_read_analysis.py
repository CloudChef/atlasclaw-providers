"""Focused contracts for shared directory, alarm, and cost read operations."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx
import pytest

PROVIDER_ROOT = Path(__file__).resolve().parents[1]
PROVIDER_SRC = PROVIDER_ROOT / "src"
if str(PROVIDER_SRC) not in sys.path:
    sys.path.insert(0, str(PROVIDER_SRC))

from smartcmp_provider.auth.resolver import resolve_provided_request  # noqa: E402
from smartcmp_provider.analysis.cost.recommendation import (  # noqa: E402
    normalize_analysis_facts,
)
from smartcmp_provider.domain.cost import available_cost_operations  # noqa: E402
from smartcmp_provider.errors import (  # noqa: E402
    SmartCmpAuthenticationError,
    SmartCmpTargetResolutionError,
    SmartCmpUpstreamError,
    SmartCmpValidationError,
)
from smartcmp_provider.models.alarms import (  # noqa: E402
    AlarmAnalysisFactsQuery,
    AlarmListQuery,
    ResourceAlertListQuery,
)
from smartcmp_provider.models.approvals import ApprovalListQuery  # noqa: E402
from smartcmp_provider.models.catalogs import (  # noqa: E402
    CatalogListQuery,
    FlavorQuery,
    ImageQuery,
)
from smartcmp_provider.models.cost import (  # noqa: E402
    CostExecutionStatusQuery,
    CostListQuery,
    CostRecommendationFactsQuery,
    ResourceCostAnalysisQuery,
)
from smartcmp_provider.models.directory import (  # noqa: E402
    ApplicationListQuery,
    ComponentListQuery,
    DirectorySearchQuery,
)
from smartcmp_provider.models.resources import (  # noqa: E402
    RecycledResourceQuery,
    ResourceListQuery,
)
from smartcmp_provider.models.security_compliance import (  # noqa: E402
    ResourceSecurityViolationQuery,
    SecurityViolationListQuery,
)
from smartcmp_provider.operations.alarms import (  # noqa: E402
    get_alarm_analysis_facts,
    list_alarms,
)
from smartcmp_provider.operations.cost import (  # noqa: E402
    _CURRENCY_EVIDENCE_CACHE,
    get_currency_evidence,
    get_cost_recommendation_facts,
    list_cost_violations,
)
from smartcmp_provider.operations.directory import (  # noqa: E402
    list_applications,
    list_business_group_directory,
    list_components,
    list_resource_pool_directory,
)
from smartcmp_provider.transport.client import SmartCmpClient  # noqa: E402
from smartcmp_provider.services.cost_analysis import (  # noqa: E402
    analyze_cost_recommendation,
    analyze_resource_cost,
)
from smartcmp_provider.services.cost_execution import (  # noqa: E402
    get_cost_execution_status,
)
from smartcmp_provider.services.alarm_analysis import analyze_alarm  # noqa: E402
from smartcmp_provider.services.alarm_listing import (  # noqa: E402
    collect_resource_alerts,
)


def make_request():
    """Create one request scope without exposing its credential in test output."""

    return resolve_provided_request(
        instance_name="cmp-test",
        base_url="https://cmp.example.com",
        subject="user-1",
        auth_type="cookie",
        credential_value="session-secret",
        trace_id="run-read-analysis",
    )


def test_directory_operations_preserve_explicit_paths_and_filters():
    """Directory operations must retain legacy paths without a string executor."""

    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, str(request.url)))
        return httpx.Response(
            200,
            json={"content": [{"id": f"row-{len(seen)}"}], "totalElements": 1},
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return (
                await list_business_group_directory(
                    client,
                    DirectorySearchQuery(query_value="prod group"),
                ),
                await list_resource_pool_directory(
                    client,
                    DirectorySearchQuery(query_value="pool/a"),
                ),
                await list_applications(
                    client,
                    ApplicationListQuery(business_group_id="bg-1"),
                ),
                await list_components(
                    client,
                    ComponentListQuery(source_key="resource.vm"),
                ),
            )

    results = asyncio.run(invoke())

    assert [result.total for result in results] == [1, 1, 1, 1]
    assert seen == [
        (
            "GET",
            "https://cmp.example.com/platform-api/business-groups/"
            "has-update-permission?query&sort=updatedDate%2Cdesc&page=1"
            "&size=50&queryValue=prod%20group",
        ),
        (
            "GET",
            "https://cmp.example.com/platform-api/resource-bundles?"
            "query&sort=createdDate%2Cdesc&page=1&size=50"
            "&queryValue=pool%2Fa",
        ),
        (
            "GET",
            "https://cmp.example.com/platform-api/groups?businessGroupIds=bg-1",
        ),
        (
            "GET",
            "https://cmp.example.com/platform-api/components?"
            "resourceType=resource.vm",
        ),
    ]


def test_component_singleton_is_compact_instead_of_becoming_an_empty_list():
    """Accept the component endpoint's direct object without returning blueprints."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("resourceType") == "resource.empty":
            return httpx.Response(
                200,
                json={"content": [], "totalElements": 0},
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "id": "component-1",
                "key": "resource.vm",
                "name": "Virtual machine",
                "resourceType": "resource.vm",
                "published": True,
                "blueprintFiles": [{"content": "x" * 100_000}],
                "lifecycles": [{"script": "x" * 10_000}],
                "properties": [{"schema": "x" * 10_000}],
            },
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return (
                await list_components(
                    client,
                    ComponentListQuery(source_key="resource.vm"),
                ),
                await list_components(
                    client,
                    ComponentListQuery(source_key="resource.empty"),
                ),
            )

    result, empty = asyncio.run(invoke())

    assert result.total == 1
    assert result.items == (
        {
            "id": "component-1",
            "key": "resource.vm",
            "name": "Virtual machine",
            "resourceType": "resource.vm",
            "published": True,
        },
    )
    assert empty.total == 0
    assert empty.items == ()


def test_alarm_list_omits_rule_and_monitoring_payloads():
    """Retain list identity and association fields without analysis evidence."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "id": "alert-1",
                        "alarmPolicyName": "CPU high",
                        "status": "ALERT_FIRING",
                        "targetEntityId": "resource-1",
                        "triggerAt": 1_700_000_000_000,
                        "queryExpression": "x" * 20_000,
                        "ruleExpression": "x" * 20_000,
                        "policy": {"description": "x" * 20_000},
                    }
                ],
                "totalElements": 1,
            },
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await list_alarms(client, AlarmListQuery())

    result = asyncio.run(invoke())

    assert result.items[0]["targetEntityId"] == "resource-1"
    assert result.items[0]["alarmPolicyName"] == "CPU high"
    assert "queryExpression" not in result.items[0]
    assert "ruleExpression" not in result.items[0]
    assert "policy" not in result.items[0]


def test_currency_evidence_cache_is_principal_scoped_and_payload_free():
    """Reuse only compact verified currency facts for the same principal."""

    _CURRENCY_EVIDENCE_CACHE.clear()
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path.endswith("/tenants/current/setting"):
            return httpx.Response(
                200,
                json={
                    "currencyUnitType": "USD",
                    "unusedTenantSettings": "x" * 50_000,
                },
                request=request,
            )
        if request.url.path.endswith("/tenants/currencyUnits"):
            return httpx.Response(
                200,
                json=[
                    {"code": "USD", "symbol": "$", "unused": "x" * 10_000}
                ],
                request=request,
            )
        raise AssertionError(f"Unexpected request: {request.url}")

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            first = await get_currency_evidence(client)
            second = await get_currency_evidence(client)
        other_request = resolve_provided_request(
            instance_name="cmp-test",
            base_url="https://cmp.example.com",
            subject="user-2",
            auth_type="cookie",
            credential_value="other-session-secret",
            trace_id="run-read-analysis-other-user",
        )
        async with SmartCmpClient(
            other_request,
            transport=httpx.MockTransport(handler),
        ) as other_client:
            other = await get_currency_evidence(other_client)
        return first, second, other

    first, second, other = asyncio.run(invoke())

    assert first == second
    assert first == other
    assert first.model_dump() == {
        "symbol": "$",
        "code": "USD",
        "source": "smartcmp_tenant_settings",
    }
    assert len(seen) == 4
    assert all("unused" not in repr(value) for value in _CURRENCY_EVIDENCE_CACHE.values())
    _CURRENCY_EVIDENCE_CACHE.clear()


@pytest.mark.parametrize(
    "factory",
    [
        lambda: DirectorySearchQuery(size=101),
        lambda: ResourceListQuery(size=101),
        lambda: AlarmListQuery(filters={"size": 101}),
        lambda: CostListQuery(size=101),
        lambda: CatalogListQuery(size=101),
        lambda: FlavorQuery(size=101),
        lambda: ApprovalListQuery(page_size=101),
    ],
)
def test_list_models_reject_page_sizes_over_one_hundred(factory):
    """Prevent every user-facing list family from requesting oversized pages."""

    with pytest.raises(ValueError):
        factory()


@pytest.mark.parametrize("size", [True, 100.9, "20"])
def test_alarm_list_rejects_non_integer_page_sizes(size):
    """Do not accept values that only become valid after implicit coercion."""

    with pytest.raises(ValueError, match="must be an integer"):
        AlarmListQuery(filters={"size": size})


@pytest.mark.parametrize("value", [True, 20.5, "20"])
@pytest.mark.parametrize(
    "factory",
    [
        lambda value: DirectorySearchQuery(page=value),
        lambda value: DirectorySearchQuery(size=value),
        lambda value: ResourceListQuery(page=value),
        lambda value: ResourceListQuery(size=value),
        lambda value: RecycledResourceQuery(page=value),
        lambda value: RecycledResourceQuery(size=value),
        lambda value: AlarmListQuery(filters={"page": value}),
        lambda value: CostListQuery(page=value),
        lambda value: CostListQuery(size=value),
        lambda value: CostListQuery(max_pages=value),
        lambda value: CatalogListQuery(page=value),
        lambda value: FlavorQuery(size=value),
        lambda value: ImageQuery(
            resource_bundle_id="bundle-1",
            logic_template_id="logic-1",
            cloud_entry_type="yacmp:cloudentry:type:vsphere",
            page=value,
        ),
        lambda value: ApprovalListQuery(page_size=value),
        lambda value: ApprovalListQuery(max_pages=value),
        lambda value: SecurityViolationListQuery(page=value),
        lambda value: SecurityViolationListQuery(max_pages=value),
        lambda value: ResourceSecurityViolationQuery(
            resource_id="resource-1",
            max_pages=value,
        ),
    ],
)
def test_list_models_reject_coercible_pagination_values(factory, value):
    """Require actual integers at every Provider pagination boundary."""

    with pytest.raises(ValueError):
        factory(value)


def test_alarm_list_rejects_malformed_success_payload():
    """A malformed 200 response must not be mistaken for an empty alert list."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={}, request=request)

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            await list_alarms(
                client,
                AlarmListQuery(filters={"status": ["ALERT_FIRING"]}),
            )

    with pytest.raises(SmartCmpUpstreamError, match="unexpected alert list"):
        asyncio.run(invoke())


def test_alarm_list_preserves_bare_query_mode_sentinel():
    """Alarm filters must not replace SmartCMP's bare query-mode marker."""

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
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
            await list_alarms(
                client,
                AlarmListQuery(
                    filters={"status": ["ACTIVE"], "page": 1},
                ),
            )

    asyncio.run(invoke())
    assert seen == [
        "https://cmp.example.com/platform-api/alarm-alert"
        "?query&status=ACTIVE&page=1"
    ]


def test_resource_alert_association_is_owned_by_provider():
    """SmartCMP Provider must query both lifecycles and reject unrelated alerts."""

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        statuses = request.url.params.get_list("status")
        is_resolved = statuses == ["ALERT_RESOLVED"]
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "id": (
                            "alert-resolved"
                            if is_resolved
                            else "alert-current"
                        ),
                        "status": (
                            "ALERT_RESOLVED"
                            if is_resolved
                            else "ALERT_FIRING"
                        ),
                        "targetEntityId": (
                            "resource-other"
                            if is_resolved
                            else "resource-1"
                        ),
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
            return await collect_resource_alerts(
                client,
                ResourceAlertListQuery(
                    resource_id="resource-1",
                    resource_name="vm-01",
                ),
            )

    result = asyncio.run(invoke())

    assert [item["id"] for item in result.items] == ["alert-current"]
    assert result.coverage.association_status == "partial"
    assert result.coverage.queries_attempted == 2
    assert result.coverage.queries_succeeded == 2
    assert result.coverage.unverified_candidate_count == 1
    assert all("targetEntityId=resource-1" in url for url in seen)
    assert "triggerAtMin" not in seen[0]
    assert "triggerAtMin" in seen[1]


def test_resource_alert_association_reads_all_reported_pages():
    """A reported total larger than one page must not be marked complete early."""

    seen_pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        seen_pages.append(page)
        start = (page - 1) * 100
        end = min(start + 100, 150)
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "id": f"alert-{index}",
                        "status": "ALERT_FIRING",
                        "targetEntityId": "resource-1",
                    }
                    for index in range(start, end)
                ],
                "totalElements": 150,
            },
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await collect_resource_alerts(
                client,
                ResourceAlertListQuery(
                    resource_id="resource-1",
                    scope="current",
                ),
            )

    result = asyncio.run(invoke())

    assert seen_pages == [1, 2]
    assert len(result.items) == 150
    assert result.coverage.candidate_count == 150
    assert result.coverage.association_status == "complete"
    assert result.coverage.errors == ()


def test_alarm_optional_context_does_not_hide_authentication_failure():
    """Optional enrichment may degrade on service errors, but never on bad auth."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/alarm-alert/alert-1"):
            return httpx.Response(
                200,
                json={"id": "alert-1", "alarmPolicyId": "policy-1"},
                request=request,
            )
        if request.url.path.endswith("/alarm-policies/policy-1"):
            return httpx.Response(
                200,
                json={"id": "policy-1"},
                request=request,
            )
        return httpx.Response(
            401,
            json={"message": "expired"},
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            await get_alarm_analysis_facts(
                client,
                AlarmAnalysisFactsQuery(alert_id="alert-1"),
            )

    with pytest.raises(SmartCmpAuthenticationError):
        asyncio.run(invoke())


def test_alarm_resolves_stale_resource_id_by_visible_name():
    """Resolve a stale alert resource ID through its exact visible name."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/alarm-alert/alert-1"):
            return httpx.Response(
                200,
                json={
                    "id": "alert-1",
                    "alarmPolicyId": "policy-1",
                    "entityInstanceId": ["missing-resource"],
                    "resourceExternalName": "worker-01",
                    "status": "ALERT_FIRING",
                },
                request=request,
            )
        if path.endswith("/alarm-policies/policy-1"):
            return httpx.Response(
                200,
                json={"id": "policy-1", "name": "CPU High"},
                request=request,
            )
        if path.endswith("/nodes/missing-resource/view"):
            return httpx.Response(404, json={}, request=request)
        if path.endswith("/nodes/search"):
            return httpx.Response(
                200,
                json={
                    "content": [
                        {"id": "resolved-resource", "name": "worker-01"}
                    ]
                },
                request=request,
            )
        if path.endswith("/nodes/resolved-resource/view"):
            return httpx.Response(
                200,
                json={
                    "id": "resolved-resource",
                    "name": "worker-01",
                    "resourceType": "VirtualMachine",
                    "status": "RUNNING",
                },
                request=request,
            )
        if path.endswith(
            (
                "/alarm-overview/recent",
                "/alarm-overview/alarm-trend",
                "/stats/alarm-alert/detail",
            )
        ):
            return httpx.Response(200, json=[], request=request)
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await analyze_alarm(
                client,
                AlarmAnalysisFactsQuery(alert_id="alert-1"),
            )

    result = asyncio.run(invoke())

    resource = result.facts[0]["resource"]
    assert resource["resource_context_available"] is True
    assert resource["resolved_name"] == "worker-01"


def test_cost_list_keeps_filters_and_bounded_pagination():
    """Cost queries must preserve filters while stopping at the upstream last page."""

    seen_pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["category"] == "COST-OPTIMIZATION"
        page = int(request.url.params["page"])
        seen_pages.append(page)
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "id": f"violation-{page}",
                        "category": "COST-OPTIMIZATION.MACHINE",
                    }
                ],
                "last": page == 1,
                "totalElements": 2,
            },
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await list_cost_violations(
                client,
                CostListQuery(
                    filters={
                        "status": "ACTIVED",
                    },
                    page=0,
                    size=1,
                    max_pages=5,
                ),
            )

    result = asyncio.run(invoke())

    assert seen_pages == [0, 1]
    assert [item["id"] for item in result.items] == [
        "violation-0",
        "violation-1",
    ]
    assert result.total == 2


def test_cost_list_rejects_non_cost_input_and_response_categories():
    """Cost list boundaries must fail before exposing cross-domain rows."""

    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            200,
            json={
                "content": [
                    {"id": "security-1", "category": "SECURITY.MACHINE"}
                ],
                "last": True,
            },
            request=request,
        )

    async def invoke(query: CostListQuery):
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await list_cost_violations(client, query)

    with pytest.raises(SmartCmpValidationError, match="require category"):
        asyncio.run(
            invoke(CostListQuery(filters={"category": "SECURITY"}))
        )
    assert request_count == 0

    with pytest.raises(SmartCmpUpstreamError, match="non-Cost row"):
        asyncio.run(invoke(CostListQuery()))
    assert request_count == 1


def test_cost_recommendation_keeps_required_fact_and_bounded_optional_inputs():
    """Recommendation analysis returns facts only; final judgment stays outside Provider."""

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        path = request.url.path
        if path.endswith("/violations/vio-1"):
            return httpx.Response(
                200,
                json={
                    "id": "vio-1",
                    "policyId": "policy-1",
                    "category": "COST-OPTIMIZATION",
                },
                request=request,
            )
        if path.endswith("/compliance-policies/policy-1"):
            return httpx.Response(
                200,
                json={"id": "policy-1", "name": "Idle VM"},
                request=request,
            )
        if path.endswith("/policy-executions/search"):
            return httpx.Response(
                200,
                json={"content": [{"id": "execution-1"}]},
                request=request,
            )
        if path.endswith("/compliance-policies/search"):
            return httpx.Response(
                200,
                json={
                    "content": [
                        {"id": "policy-1", "category": "COST-OPTIMIZATION"},
                        {"id": "policy-2", "category": "COST-OPTIMIZATION"},
                    ]
                },
                request=request,
            )
        return httpx.Response(200, json={"source": path}, request=request)

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await get_cost_recommendation_facts(
                client,
                CostRecommendationFactsQuery(violation_id="vio-1"),
            )

    result = asyncio.run(invoke())

    assert result.violation["id"] == "vio-1"
    assert result.policy == {"id": "policy-1", "name": "Idle VM"}
    assert [item["id"] for item in result.policy_executions] == ["execution-1"]
    assert result.related_policy_count == 1
    assert not hasattr(result, "assessment")
    assert any("size=5" in url for url in seen)
    assert any("size=100" in url for url in seen)


def test_cost_analysis_preserves_tracking_identity_for_follow_up_actions():
    """An in-flight repair remains Track-only after recommendation analysis."""

    facts = normalize_analysis_facts(
        {
            "id": "cost-1",
            "category": "COST-OPTIMIZATION.MACHINE",
            "status": "ACTIVED",
            "fixType": "DAY2",
            "taskInstanceId": "task-1",
        }
    )

    assert facts["taskInstanceId"] == "task-1"
    assert tuple(
        operation.operation_id
        for operation in available_cost_operations(facts)
    ) == ("analyze", "track")


def test_cost_recommendation_rejects_security_before_cost_enrichment():
    """Security violations must not be interpreted as cost recommendations."""

    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        return httpx.Response(
            200,
            json={"id": "security-vio", "category": "SECURITY.MACHINE"},
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            await get_cost_recommendation_facts(
                client,
                CostRecommendationFactsQuery(violation_id="security-vio"),
            )

    with pytest.raises(SmartCmpValidationError, match="not a Cost Optimization"):
        asyncio.run(invoke())
    assert seen_paths == [
        "/platform-api/compliance-policies/violations/security-vio"
    ]


def test_cost_recommendation_rejects_mismatched_identity_before_enrichment():
    """A Cost detail for another ID cannot authorize recommendation analysis."""

    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        return httpx.Response(
            200,
            json={"id": "cost-other", "category": "COST-OPTIMIZATION"},
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            await get_cost_recommendation_facts(
                client,
                CostRecommendationFactsQuery(violation_id="cost-requested"),
            )

    with pytest.raises(SmartCmpTargetResolutionError, match="mismatched identity"):
        asyncio.run(invoke())
    assert seen_paths == [
        "/platform-api/compliance-policies/violations/cost-requested"
    ]


def test_cost_tracking_revalidates_target_before_execution_queries():
    """Tracking must not query execution records for a non-Cost target."""

    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        return httpx.Response(
            200,
            json={"id": "security-vio", "category": "SECURITY.MACHINE"},
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            await get_cost_execution_status(
                client,
                CostExecutionStatusQuery(violation_id="security-vio"),
            )

    with pytest.raises(SmartCmpValidationError, match="not a Cost Optimization"):
        asyncio.run(invoke())
    assert seen_paths == [
        "/platform-api/compliance-policies/violations/security-vio"
    ]


def test_cost_recommendation_resolves_stale_resource_id_by_visible_name():
    """Resolve a stale recommendation resource ID through its exact visible name."""

    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        path = request.url.path
        if path.endswith("/violations/vio-1"):
            return httpx.Response(
                200,
                json={
                    "id": "vio-1",
                    "policyId": "policy-1",
                    "category": "COST-OPTIMIZATION",
                    "resourceId": "missing-resource",
                    "resourceName": "vm-prod-01",
                    "status": "ACTIVED",
                    "monthlySaving": "12.5",
                },
                request=request,
            )
        if path.endswith("/compliance-policies/policy-1"):
            return httpx.Response(
                200,
                json={"id": "policy-1", "name": "Idle VM"},
                request=request,
            )
        if path.endswith("/nodes/search"):
            return httpx.Response(
                200,
                json={
                    "content": [
                        {
                            "id": "resolved-resource",
                            "name": "vm-prod-01",
                        }
                    ]
                },
                request=request,
            )
        if path.endswith("/nodes/resolved-resource/view"):
            return httpx.Response(
                200,
                json={
                    "id": "resolved-resource",
                    "name": "vm-prod-01",
                    "resourceType": "VirtualMachine",
                    "status": "RUNNING",
                },
                request=request,
            )
        if path.endswith("/nodes/missing-resource/view"):
            return httpx.Response(404, json={}, request=request)
        if path.endswith("/tenants/current/setting"):
            return httpx.Response(200, json={}, request=request)
        if path.endswith("/compliance-policies/search"):
            return httpx.Response(
                200,
                json={
                    "content": [
                        {"id": "policy-1", "category": "COST-OPTIMIZATION"}
                    ],
                    "last": True,
                },
                request=request,
            )
        if path.endswith(
            (
                "/policy-executions/search",
                "/overview/saving-summary",
                "/overview/operation-summary",
                "/overview/saving-trend",
                "/overview/saving-resource-top",
            )
        ):
            return httpx.Response(
                200,
                json={"content": [], "last": True},
                request=request,
            )
        return httpx.Response(200, json={}, request=request)

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await analyze_cost_recommendation(
                client,
                CostRecommendationFactsQuery(violation_id="vio-1"),
            )

    result = asyncio.run(invoke())

    assert result.facts["resourceId"] == "resolved-resource"
    assert result.facts["resourceContextAvailable"] is True
    assert ("POST", "/platform-api/nodes/search") in seen


def test_resource_cost_attaches_exact_execution_evidence_inside_provider():
    """Resource-cost analysis must include matching policy execution evidence."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/nodes/resource-1/view"):
            return httpx.Response(
                200,
                json={
                    "id": "resource-1",
                    "name": "vm-1",
                    "resourceType": "resource.iaas.machine.instance.vsphere",
                    "componentType": "resource.iaas.machine.instance.vsphere",
                },
                request=request,
            )
        if path.endswith("/compliance-policies/search"):
            return httpx.Response(
                200,
                json={
                    "content": [
                        {
                            "id": "policy-1",
                            "name": "Idle VM",
                            "category": "COST-OPTIMIZATION.MACHINE",
                            "resourceType": ["resource.iaas.machine"],
                            "lastExecutionId": "execution-1",
                            "lastExecuteStatus": "FINISHED",
                            "policyConfigs": [
                                {
                                    "id": "config-1",
                                    "enabled": True,
                                    "scope": {},
                                    "lastExecutionId": "execution-1",
                                    "lastExecuteStatus": "FINISHED",
                                }
                            ],
                        }
                    ],
                    "last": True,
                },
                request=request,
            )
        if path.endswith("/violations/search"):
            return httpx.Response(
                200,
                json={"content": [], "last": True},
                request=request,
            )
        if path.endswith("/resource-executions/search"):
            return httpx.Response(
                200,
                json={
                    "content": [
                        {
                            "executionId": "execution-1",
                            "resourceId": "resource-1",
                            "policyId": "policy-1",
                            "status": "FINISHED",
                            "extra": {"evidenceComplete": True},
                        }
                    ],
                    "last": True,
                },
                request=request,
            )
        if path.endswith("/tenants/current/setting"):
            return httpx.Response(200, json={}, request=request)
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await analyze_resource_cost(
                client,
                ResourceCostAnalysisQuery(resource_id="resource-1"),
            )

    result = asyncio.run(invoke())

    assert result.policyCoverage[0]["resourceExecution"]["executionId"] == (
        "execution-1"
    )
    assert result.policyCoverage[0]["resourceExecution"]["extra"] == {
        "evidenceComplete": True
    }
