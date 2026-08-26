"""Focused contracts for the SmartCMP Security compliance domain."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from pydantic import ValidationError

from smartcmp_provider.auth.resolver import resolve_provided_request
from smartcmp_provider.errors import (
    SmartCmpTargetResolutionError,
    SmartCmpUnknownOutcomeError,
    SmartCmpUpstreamError,
    SmartCmpValidationError,
)
from smartcmp_provider.models.security_compliance import (
    ResourceSecurityAnalysisQuery,
    ResourceSecurityViolationQuery,
    SecurityOverviewQuery,
    SecurityViolationAnalysisQuery,
    SecurityViolationListQuery,
    SecurityViolationMarkFixedInput,
)
from smartcmp_provider.services.security_compliance import (
    THIRTY_DAYS_MS,
    analyze_resource_security,
    analyze_security_violation,
    get_security_compliance_overview,
    list_resource_security_violations,
    list_security_violations,
    mark_security_violation_fixed,
)
from smartcmp_provider.transport.client import SmartCmpClient


def make_request():
    """Create one isolated request scope for Security compliance tests."""

    return resolve_provided_request(
        instance_name="cmp-test",
        base_url="https://cmp.example.com",
        subject="user-1",
        auth_type="cookie",
        credential_value="session-secret",
        trace_id="security-compliance-test",
    )


def test_security_violation_list_uses_root_category_and_one_based_pages():
    """The provider must translate one-based requests from zero-based envelopes."""

    seen_pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["category"] == "SECURITY"
        assert request.url.params["status"] == "ACTIVED"
        assert request.url.params["size"] == "1"
        page = int(request.url.params["page"])
        seen_pages.append(page)
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "id": f"violation-{page}",
                        "category": "SECURITY.MACHINE",
                        "resourceId": f"resource-{page}",
                        "monthlySaving": 99,
                    }
                ],
                "number": page - 1,
                "totalPages": 2,
                "totalElements": 2,
            },
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await list_security_violations(
                client,
                SecurityViolationListQuery(page=1, size=1, max_pages=5),
            )

    result = asyncio.run(invoke())

    assert seen_pages == [1, 2]
    assert [item["violationId"] for item in result.items] == [
        "violation-1",
        "violation-2",
    ]
    assert all("monthlySaving" not in item for item in result.items)
    assert result.total == 2
    assert result.scanned_pages == 2
    assert result.coverage == "complete"
    assert result.has_more is False
    assert result.next_page is None


def test_security_violation_list_rejects_non_security_response_rows():
    """A faulty category filter must not relabel Cost rows as Security facts."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [
                    {"id": "cost-1", "category": "COST-OPTIMIZATION.MACHINE"}
                ],
                "last": True,
            },
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            await list_security_violations(client, SecurityViolationListQuery())

    with pytest.raises(SmartCmpUpstreamError, match="non-Security row"):
        asyncio.run(invoke())


def test_resource_violation_scan_filters_exact_id_and_reports_partial_coverage():
    """An incomplete global scan must not turn absence into a definitive claim."""

    seen_pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["category"] == "SECURITY"
        assert "status" not in request.url.params
        assert request.url.params["size"] == "100"
        page = int(request.url.params["page"])
        seen_pages.append(page)
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "id": "other",
                        "resourceId": "resource-other",
                        "category": "SECURITY.MACHINE",
                    }
                ],
                "number": 0,
                "totalPages": 2,
                "totalElements": 2,
            },
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await list_resource_security_violations(
                client,
                ResourceSecurityViolationQuery(
                    resource_id="resource-1",
                    max_pages=1,
                ),
            )

    result = asyncio.run(invoke())

    assert seen_pages == [1]
    assert result.items == ()
    assert result.coverage == "partial"
    assert result.truncated is True
    assert result.has_more is True
    assert result.next_page == 2


def test_resource_violation_scan_reads_every_page_and_filters_exact_resource_id():
    """The provider must not trust SmartCMP's ignored resourceId filter."""

    seen_pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert "resourceId" not in request.url.params
        assert "status" not in request.url.params
        page = int(request.url.params["page"])
        seen_pages.append(page)
        content = (
            [
                {
                    "id": "match-1",
                    "resourceId": "resource-1",
                    "category": "SECURITY.MACHINE",
                },
                {
                    "id": "prefix-only",
                    "resourceId": "resource-10",
                    "category": "SECURITY.MACHINE",
                },
            ]
            if page == 1
            else [
                {
                    "id": "match-2",
                    "resourceId": "resource-1",
                    "category": "SECURITY.STORAGE",
                    "status": "FIXED",
                },
                {
                    "id": "wrong-category",
                    "resourceId": "resource-1",
                    "category": "COST-OPTIMIZATION",
                },
            ]
        )
        return httpx.Response(
            200,
            json={
                "content": content,
                "number": page - 1,
                "totalPages": 2,
                "totalElements": 4,
            },
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await list_resource_security_violations(
                client,
                ResourceSecurityViolationQuery(resource_id="resource-1"),
            )

    result = asyncio.run(invoke())

    assert seen_pages == [1, 2]
    assert [item["violationId"] for item in result.items] == ["match-1", "match-2"]
    assert result.coverage == "complete"
    assert result.total == 4
    assert result.matched_total == 2
    assert result.items[1]["status"] == "FIXED"


def test_resource_violation_scan_preserves_matches_on_malformed_later_page():
    """Malformed later pages must produce partial coverage without losing facts."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["page"] == "1":
            return httpx.Response(
                200,
                json={
                    "content": [
                        {
                            "id": "security-1",
                            "resourceId": "resource-1",
                            "category": "SECURITY.MACHINE",
                        }
                    ],
                    "last": False,
                },
                request=request,
            )
        return httpx.Response(
            200,
            json={"unexpected": []},
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await list_resource_security_violations(
                client,
                ResourceSecurityViolationQuery(resource_id="resource-1"),
            )

    result = asyncio.run(invoke())

    assert [item["violationId"] for item in result.items] == ["security-1"]
    assert result.coverage == "partial"
    assert result.scanned_pages == 1
    assert result.next_page == 2
    assert result.errors


def test_resource_violation_scan_reports_failed_for_malformed_first_page():
    """A malformed first page must return failed coverage, not raise or claim absence."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": []}, request=request)

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await list_resource_security_violations(
                client,
                ResourceSecurityViolationQuery(resource_id="resource-1"),
            )

    result = asyncio.run(invoke())

    assert result.items == ()
    assert result.coverage == "failed"
    assert result.scanned_pages == 0
    assert result.next_page == 1
    assert result.errors


def test_security_analysis_guards_category_before_optional_enrichment():
    """A non-Security violation must fail before policy or resource reads."""

    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "id": "cost-1",
                "category": "COST-OPTIMIZATION",
                "policyId": "policy-1",
                "resourceId": "resource-1",
            },
            request=request,
        )

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            await analyze_security_violation(
                client,
                SecurityViolationAnalysisQuery(violation_id="cost-1"),
            )

    with pytest.raises(SmartCmpValidationError, match="not Security"):
        asyncio.run(invoke())
    assert seen_paths == [
        "/platform-api/compliance-policies/violations/cost-1"
    ]


def test_security_analysis_keeps_optional_enrichment_best_effort_and_separated():
    """Policy failure must not discard the required confirmed violation evidence."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/violations/security-1"):
            return httpx.Response(
                200,
                json={
                    "id": "security-1",
                    "category": "SECURITY.MACHINE",
                    "status": "ACTIVED",
                    "policyId": "policy-1",
                    "resourceId": "resource-1",
                    "monthlySaving": 88,
                    "taskName": None,
                },
                request=request,
            )
        if path.endswith("/compliance-policies/policy-1"):
            return httpx.Response(500, json={"message": "policy unavailable"}, request=request)
        if path.endswith("/nodes/resource-1/view"):
            return httpx.Response(
                200,
                json={
                    "id": "resource-1",
                    "name": "vm-01",
                    "resourceType": "VirtualMachine",
                    "componentType": "iaas.machine.virtual_machine",
                    "status": "RUNNING",
                },
                request=request,
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await analyze_security_violation(
                client,
                SecurityViolationAnalysisQuery(violation_id="security-1"),
            )

    result = asyncio.run(invoke())

    assert result.cmp_confirmed_facts["violation"]["violationId"] == "security-1"
    assert "monthlySaving" not in result.cmp_confirmed_facts["violation"]
    assert result.cmp_confirmed_facts["policy"] is None
    assert result.cmp_confirmed_facts["resource"]["identity"]["name"] == "vm-01"
    assert result.llm_inferences == ()
    assert result.enrichment_status == {
        "policy": "unavailable",
        "resource": "available",
    }
    assert "policy" in result.missing_evidence


def test_security_analysis_validates_identity_and_projects_manual_evidence_only():
    """Required identity and Security-only projection must fail closed."""

    def mismatched_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"id": "security-other", "category": "SECURITY.MACHINE"},
            request=request,
        )

    async def invoke_mismatch():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(mismatched_handler),
        ) as client:
            await analyze_security_violation(
                client,
                SecurityViolationAnalysisQuery(violation_id="security-1"),
            )

    with pytest.raises(SmartCmpTargetResolutionError, match="mismatched identity"):
        asyncio.run(invoke_mismatch())

    def projection_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/violations/security-1"):
            return httpx.Response(
                200,
                json={
                    "id": "security-1",
                    "category": "SECURITY.MACHINE",
                    "status": "ACTIVED",
                    "policyId": "policy-1",
                    "taskDefinition": None,
                    "fixType": None,
                    "taskName": None,
                    "taskInstanceId": None,
                    "savingOperationType": None,
                },
                request=request,
            )
        if request.url.path.endswith("/compliance-policies/policy-1"):
            return httpx.Response(
                200,
                json={
                    "id": "policy-1",
                    "name": "Manual Security policy",
                    "category": "SECURITY.MACHINE",
                    "remedie": "Review and change through an approved workflow.",
                    "taskDefinition": {"name": "must-not-leak"},
                    "fixType": "DAY2",
                    "monthlySaving": 99,
                    "policyConfigs": [
                        {
                            "id": "config-1",
                            "status": "ENABLED",
                            "lastExecuteStatus": "FINISHED",
                            "lastExecutionId": "must-not-leak",
                            "executeAccount": "must-not-leak",
                            "resourceViolation": {"taskName": "must-not-leak"},
                            "taskInstanceId": "must-not-leak",
                            "executeParameters": {"danger": True},
                            "savingOperationType": "resize",
                        }
                    ],
                },
                request=request,
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    async def invoke_projection():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(projection_handler),
        ) as client:
            return await analyze_security_violation(
                client,
                SecurityViolationAnalysisQuery(violation_id="security-1"),
            )

    result = asyncio.run(invoke_projection())
    rendered_facts = str(result.cmp_confirmed_facts).casefold()
    assert result.enrichment_status["policy"] == "available"
    assert result.cmp_confirmed_facts["policy"]["name"] == "Manual Security policy"
    assert all(
        field.casefold() not in rendered_facts
        for field in (
            "taskDefinition",
            "fixType",
            "taskName",
            "taskInstanceId",
            "executeParameters",
            "savingOperationType",
            "monthlySaving",
            "lastExecutionId",
            "executeAccount",
            "resourceViolation",
        )
    )
    assert result.cmp_confirmed_facts["policy"]["policyConfigs"][0][
        "lastExecuteStatus"
    ] == "FINISHED"


def test_overview_defaults_to_thirty_days_and_aggregates_inventory():
    """Overview sources must all use the Security root and resolved time range."""

    trend_ranges: list[tuple[int, int]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        assert request.url.params["category"] == "SECURITY"
        if path.endswith(("/compliance-trend", "/violation-trend")):
            start_time = int(request.url.params["startTime"])
            end_time = int(request.url.params["endTime"])
            trend_ranges.append((start_time, end_time))
            return httpx.Response(200, json=[], request=request)
        if path.endswith("/overview/compliance"):
            return httpx.Response(
                200,
                json=[{"legend": "SECURITY", "violation": 1, "total": 10}],
                request=request,
            )
        if path.endswith("/overview/violation"):
            return httpx.Response(
                200,
                json=[{"legend": "HIGH", "violation": 1, "total": 10}],
                request=request,
            )
        if path.endswith("/compliance-policies/search"):
            return httpx.Response(
                200,
                json={
                    "content": [
                        {
                            "id": "policy-1",
                            "policyConfigs": [
                                {
                                    "status": "ENABLED",
                                    "lastExecuteStatus": "FINISHED",
                                },
                                {
                                    "enabled": False,
                                    "status": "ENABLED",
                                    "lastExecuteStatus": "FAILED",
                                }
                            ],
                        },
                        {
                            "id": "policy-2",
                            "enabled": False,
                            "status": "ENABLED",
                            "lastExecuteStatus": "ERROR",
                        },
                    ],
                    "last": True,
                    "totalElements": 2,
                },
                request=request,
            )
        if path.endswith("/policy-executions/search"):
            return httpx.Response(
                200,
                json={
                    "content": [{"id": "execution-1", "status": "FINISHED"}],
                    "last": True,
                    "totalElements": 1,
                },
                request=request,
            )
        if path.endswith("/violations/search"):
            return httpx.Response(
                200,
                json={
                    "content": [
                        {
                            "id": "violation-1",
                            "category": "SECURITY.MACHINE",
                            "severity": "HIGH",
                        }
                    ],
                    "last": True,
                    "totalElements": 1,
                },
                request=request,
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await get_security_compliance_overview(
                client,
                SecurityOverviewQuery(),
            )

    result = asyncio.run(invoke())

    assert len(trend_ranges) == 2
    assert all(end - start == THIRTY_DAYS_MS for start, end in trend_ranges)
    assert result.summary["policyTotal"] == 2
    assert result.summary["enabledPolicyCount"] == 1
    assert result.summary["policyConfigTotal"] == 2
    assert result.summary["enabledPolicyConfigCount"] == 1
    assert result.summary["policyEvaluationStatusCounts"] == {
        "FINISHED": 1,
        "FAILED": 1,
        "ERROR": 1,
    }
    assert result.summary["activeViolationTotal"] == 1
    assert result.summary["severityCounts"] == {"HIGH": 1}
    assert set(result.source_coverage.values()) == {"complete"}
    assert result.errors == ()


def test_mark_fixed_requires_confirmation_and_verifies_without_resource_change():
    """Mark FIXED must re-read status and must never imply resource remediation."""

    with pytest.raises(ValidationError, match="confirmed"):
        SecurityViolationMarkFixedInput(violation_id="security-1")

    seen_paths: list[str] = []
    detail_reads = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal detail_reads
        seen_paths.append(request.url.path)
        if request.url.path.endswith("/violations/security-1"):
            detail_reads += 1
            return httpx.Response(
                200,
                json={
                    "id": "security-1",
                    "category": "SECURITY.MACHINE",
                    "status": "ACTIVED" if detail_reads == 1 else "FIXED",
                    "policyId": "policy-1",
                    "policyName": "Secure VM",
                    "resourceId": "resource-1",
                    "resourceName": "vm-01",
                },
                request=request,
            )
        if request.url.path.endswith("/security-1/violation/FIXED"):
            return httpx.Response(200, content=b"", request=request)
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    async def invoke(confirmed: bool):
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await mark_security_violation_fixed(
                client,
                SecurityViolationMarkFixedInput(
                    violation_id="security-1",
                    confirmed=confirmed,
                ),
            )

    with pytest.raises(SmartCmpValidationError, match="confirmation"):
        asyncio.run(invoke(False))
    assert seen_paths == []

    result = asyncio.run(invoke(True))

    assert seen_paths == [
        "/platform-api/compliance-policies/violations/security-1",
        "/platform-api/compliance-policies/security-1/violation/FIXED",
        "/platform-api/compliance-policies/violations/security-1",
    ]
    assert result.before_status == "ACTIVED"
    assert result.after_status == "FIXED"
    assert result.resource_remediated is False
    assert "response" not in result.model_dump()


@pytest.mark.parametrize("failure_mode", ["transport", "server"])
def test_mark_fixed_semantic_write_failure_is_unknown_and_not_retried(failure_mode):
    """The legacy GET write must receive semantic-write unknown-outcome handling."""

    status_attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal status_attempts
        if request.url.path.endswith("/violations/security-1"):
            return httpx.Response(
                200,
                json={
                    "id": "security-1",
                    "category": "SECURITY.MACHINE",
                    "status": "ACTIVED",
                },
                request=request,
            )
        if request.url.path.endswith("/security-1/violation/FIXED"):
            status_attempts += 1
            if failure_mode == "transport":
                raise httpx.ConnectError("connection lost", request=request)
            return httpx.Response(
                503,
                json={"message": "temporarily unavailable"},
                request=request,
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            await mark_security_violation_fixed(
                client,
                SecurityViolationMarkFixedInput(
                    violation_id="security-1",
                    confirmed=True,
                ),
            )

    with pytest.raises(SmartCmpUnknownOutcomeError, match="do not retry"):
        asyncio.run(invoke())
    assert status_attempts == 1


@pytest.mark.parametrize(
    ("category", "status", "message"),
    [
        ("COST-OPTIMIZATION", "ACTIVED", "not Security"),
        ("SECURITY.MACHINE", "FIXED", "only ACTIVED"),
    ],
)
def test_mark_fixed_rejects_wrong_category_or_state_before_status_write(
    category,
    status,
    message,
):
    """Category and state preflight must stop the semantic write endpoint."""

    status_writes = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal status_writes
        if request.url.path.endswith("/violations/security-1"):
            return httpx.Response(
                200,
                json={
                    "id": "security-1",
                    "category": category,
                    "status": status,
                },
                request=request,
            )
        status_writes += 1
        return httpx.Response(200, content=b"", request=request)

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            await mark_security_violation_fixed(
                client,
                SecurityViolationMarkFixedInput(
                    violation_id="security-1",
                    confirmed=True,
                ),
            )

    with pytest.raises(SmartCmpValidationError, match=message):
        asyncio.run(invoke())
    assert status_writes == 0


def test_resource_security_analysis_separates_posture_from_confirmed_violations():
    """Resource analysis must keep LLM evidence distinct from CMP policy facts."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/nodes/resource-1/view"):
            return httpx.Response(
                200,
                json={
                    "id": "resource-1",
                    "name": "vm-01",
                    "resourceType": "VirtualMachine",
                    "componentType": "iaas.machine.virtual_machine",
                    "status": "RUNNING",
                },
                request=request,
            )
        if path.endswith("/violations/search"):
            return httpx.Response(
                200,
                json={
                    "content": [
                        {
                            "id": "security-1",
                            "category": "SECURITY.MACHINE",
                            "status": "ACTIVED",
                            "resourceId": "resource-1",
                        }
                    ],
                    "last": True,
                    "totalElements": 1,
                },
                request=request,
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await analyze_resource_security(
                client,
                ResourceSecurityAnalysisQuery(resource_id="resource-1"),
            )

    result = asyncio.run(invoke())

    assert result.object_type == "resource"
    assert result.object_name == "vm-01"
    assert result.llm_inferred_posture["status"] == "pending_llm_analysis"
    assert result.llm_inferred_posture["inferences"] == []
    assert result.cmp_confirmed_violations[0]["violationId"] == "security-1"
    assert result.violation_coverage["status"] == "complete"
    assert result.violation_coverage["absenceConclusion"] == "violations_found"
    contract = result.analysis_contract
    assert contract["sourceSeparation"] == {
        "cmpConfirmedViolations": {
            "path": "cmp_confirmed_violations",
            "authority": "cmp",
        },
        "llmInferredPosture": {
            "path": "llm_inferred_posture",
            "authority": "llm_inference_only",
        },
    }
    assert contract["evidencePaths"] == {
        "resourceProfile": "resource",
        "postureEvidence": "llm_inferred_posture.evidence",
        "cmpConfirmedViolations": "cmp_confirmed_violations",
        "violationCoverage": "violation_coverage",
        "missingEvidence": "missing_evidence",
        "collectionErrors": "errors",
    }
    assert {
        "risks",
        "evidenceCitations",
        "manualRemediation",
        "verification",
        "missingEvidence",
    }.issubset(contract["requiredLLMOutput"])
    assert contract["llmMayCreateCmpConclusion"] is False
    assert contract["llmMayReplaceCmpConclusion"] is False
    assert "usesCmpComplianceRules" not in contract
    assert "allowedComplianceStatuses" not in contract
    assert "complianceStatus" not in contract["requiredLLMOutput"]


def test_resource_security_analysis_reports_matches_from_partial_scan():
    """A partial inventory must retain matches and qualify only its completeness."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/nodes/resource-1/view"):
            return httpx.Response(
                200,
                json={
                    "id": "resource-1",
                    "name": "vm-01",
                    "resourceType": "VirtualMachine",
                    "status": "RUNNING",
                },
                request=request,
            )
        if path.endswith("/violations/search"):
            if request.url.params["page"] == "1":
                return httpx.Response(
                    200,
                    json={
                        "content": [
                            {
                                "id": "security-1",
                                "category": "SECURITY.MACHINE",
                                "status": "ACTIVED",
                                "resourceId": "resource-1",
                            }
                        ],
                        "last": False,
                        "totalElements": 2,
                    },
                    request=request,
                )
            return httpx.Response(
                503,
                json={"message": "next page unavailable"},
                request=request,
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    async def invoke():
        async with SmartCmpClient(
            make_request(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await analyze_resource_security(
                client,
                ResourceSecurityAnalysisQuery(resource_id="resource-1"),
            )

    result = asyncio.run(invoke())

    assert result.violation_coverage["status"] == "partial"
    assert result.violation_coverage["absenceConclusion"] == "violations_found"
    assert result.cmp_confirmed_violations[0]["violationId"] == "security-1"
    assert result.analysis_contract["violationCoverageInterpretation"] == {
        "matchesPresent": (
            "report_confirmed_violations_and_note_incomplete_inventory_"
            "when_coverage_is_not_complete"
        ),
        "noMatchesIncomplete": "not_found_in_scanned_scope",
        "noMatchesComplete": "no_matching_violations",
    }
