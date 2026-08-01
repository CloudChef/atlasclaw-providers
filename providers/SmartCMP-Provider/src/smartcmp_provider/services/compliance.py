"""Shared generic SmartCMP resource compliance evidence service."""

from __future__ import annotations

from typing import Any

from smartcmp_provider.analysis.compliance import (
    build_analysis_contract,
    build_generic_analysis_result,
)
from smartcmp_provider.domain.resource_profiles import (
    build_evidence_coverage,
    build_resource_profile,
    sanitize_error_text,
    structural_missing_evidence,
)
from smartcmp_provider.models.resources import (
    ResourceComplianceQuery,
    ResourceComplianceResult,
    ResourceEvidenceQuery,
)
from smartcmp_provider.operations.resources import load_resource_evidence
from smartcmp_provider.transport.client import SmartCmpClient


async def analyze_resource_compliance(
    client: SmartCmpClient,
    query: ResourceComplianceQuery,
) -> ResourceComplianceResult:
    """Load resources and build adapter-neutral compliance evidence."""

    evidence = await load_resource_evidence(
        client,
        ResourceEvidenceQuery(resource_ids=query.resource_ids),
    )
    return build_resource_compliance_result(list(evidence.records))


def build_resource_compliance_result(
    records: list[dict[str, Any]],
) -> ResourceComplianceResult:
    """Project already loaded resource records into the compliance contract."""

    results = tuple(_build_result(record) for record in records)
    analyzed_count = sum(
        1
        for record in records
        if record.get("fetchStatus") == "ok"
    )
    return ResourceComplianceResult(
        analyzed_count=analyzed_count,
        failed_count=len(records) - analyzed_count,
        analysis_contract=build_analysis_contract(),
        results=results,
    )


def _build_result(record: dict[str, Any]) -> dict[str, Any]:
    profile = build_resource_profile(record)
    coverage = build_evidence_coverage(profile, record)
    fetch_ok = record.get("fetchStatus") == "ok"
    result = build_generic_analysis_result(
        resource_profile=profile,
        evidence_coverage=coverage,
        missing_evidence=structural_missing_evidence(profile, record),
        errors=[
            sanitize_error_text(item)
            for item in record.get("errors") or []
        ],
        analysis_status=(
            "evidence_collected" if fetch_ok else "fetch_failed"
        ),
    )
    identity = profile.get("identity") or {}
    result.update(
        {
            "resourceId": str(record.get("resourceId") or ""),
            "resourceName": str(identity.get("name") or ""),
            "resourceType": str(identity.get("resourceType") or ""),
        }
    )
    return result
