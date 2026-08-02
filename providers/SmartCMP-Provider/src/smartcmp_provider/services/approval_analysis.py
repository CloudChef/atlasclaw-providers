"""Shared approval evidence orchestration for all protocol adapters."""

from __future__ import annotations

from smartcmp_provider.domain.views import (
    project_approval_item,
    project_flavors,
)
from smartcmp_provider.errors import (
    SmartCmpAuthenticationError,
    SmartCmpError,
    SmartCmpPermissionError,
    SmartCmpRateLimitError,
)
from smartcmp_provider.models.approvals import (
    ApprovalDetailQuery,
    ApprovalDetailResult,
)
from smartcmp_provider.models.views import ApprovalAnalysisEvidence
from smartcmp_provider.operations.approvals import (
    get_pending_approval_detail,
    list_approval_flavors,
)
from smartcmp_provider.transport.client import SmartCmpClient


async def get_approval_analysis_evidence(
    client: SmartCmpClient,
    query: ApprovalDetailQuery,
) -> ApprovalAnalysisEvidence:
    """Collect approval and optional flavor evidence through one Provider client."""

    _detail, evidence = await get_approval_analysis_bundle(client, query)
    return evidence


async def get_approval_analysis_bundle(
    client: SmartCmpClient,
    query: ApprovalDetailQuery,
) -> tuple[ApprovalDetailResult, ApprovalAnalysisEvidence]:
    """Return raw route facts with the safe analysis projection for adapters."""

    warnings: list[str] = []
    detail = await get_pending_approval_detail(client, query)
    try:
        flavors = project_flavors(await list_approval_flavors(client))
    except (
        SmartCmpAuthenticationError,
        SmartCmpPermissionError,
        SmartCmpRateLimitError,
    ):
        raise
    except SmartCmpError as error:
        flavors = ()
        warnings.append(f"Flavor enrichment unavailable: {error}")
    evidence = ApprovalAnalysisEvidence(
        request_id=detail.request_id,
        request=project_approval_item(
            detail.item,
            request_id=detail.request_id,
        ),
        flavors=flavors,
        warnings=tuple(warnings),
        analysis_instruction=(
            "Analyze necessity, requested specifications, policy evidence, "
            "cost evidence, risk, missing business context, and approval "
            "concerns. Do not approve or reject from this read-only result."
        ),
    )
    return detail, evidence
