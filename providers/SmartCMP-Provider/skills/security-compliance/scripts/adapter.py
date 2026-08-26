"""AtlasClaw Tool adapters for SmartCMP Security compliance workflows."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


_SHARED_SCRIPTS = Path(__file__).resolve().parents[2] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from _atlasclaw_adapter import (  # noqa: E402
    RunContext,
    execute_with_request,
    split_values,
    tool_error,
    tool_result,
)
from _security_object_actions import (  # noqa: E402
    attach_security_violation_object_metadata,
)
from smartcmp_provider.models.security_compliance import (  # noqa: E402
    SecurityOverviewQuery,
    SecurityViolationAnalysisQuery,
    SecurityViolationListQuery,
    SecurityViolationMarkFixedInput,
)
from smartcmp_provider.services.security_compliance import (  # noqa: E402
    analyze_security_violation as analyze_security_violation_service,
    get_security_compliance_overview,
    list_security_violations as list_security_violations_service,
    mark_security_violation_fixed as mark_security_violation_fixed_service,
)


def _provider_instance_name(request: Any) -> str:
    """Return the SmartCMP instance selected for this completed Tool request."""

    context = getattr(request, "context", None)
    instance = getattr(context, "instance", None)
    return str(getattr(instance, "name", "") or "").strip()


async def get_security_overview(
    ctx: RunContext[Any],
    start_time: int | None = None,
    end_time: int | None = None,
) -> dict[str, Any]:
    """Return the current SmartCMP Security posture and bounded trend facts.

    Args:
        ctx: AtlasClaw request context for the selected SmartCMP instance.
        start_time: Optional trend start in Unix epoch milliseconds. When both
            times are omitted, the Provider uses the most recent 30 days.
        end_time: Optional trend end in Unix epoch milliseconds.

    Returns:
        AtlasClaw's structured Tool result containing Security-only overview,
        policy, execution, severity, and trend evidence.
    """

    try:
        result, request = await execute_with_request(
            ctx,
            get_security_compliance_overview,
            SecurityOverviewQuery(
                start_time=start_time,
                end_time=end_time,
            ),
        )
        return tool_result(
            result,
            summary="Collected the current SmartCMP Security compliance overview.",
            request=request,
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def list_security_violations(
    ctx: RunContext[Any],
    status: str = "ACTIVED",
    severities: str | list[str] | None = None,
    query_value: str = "",
    page: int = 1,
    size: int = 20,
    max_pages: int = 1,
) -> dict[str, Any]:
    """List Security violations while preserving real IDs for object actions.

    Args:
        ctx: AtlasClaw request context for the selected SmartCMP instance.
        status: ``ACTIVED``, ``FIXED``, or an empty value for all states.
        severities: Optional whitespace- or comma-separated severity filters.
        query_value: Optional CMP free-text filter.
        page: One-based first page requested from CMP.
        size: Number of rows per page.
        max_pages: Maximum pages to scan, from 1 through 50.

    Returns:
        A paginated AtlasClaw Tool result whose rows expose only the required
        first-phase Analyze action and keep indexes separate from violation IDs.
    """

    try:
        normalized_status = str(status or "").strip().upper()
        if normalized_status == "ALL":
            normalized_status = ""
        result, request = await execute_with_request(
            ctx,
            list_security_violations_service,
            SecurityViolationListQuery(
                status=normalized_status,
                severities=split_values(severities),
                query_value=str(query_value or "").strip(),
                page=page,
                size=size,
                max_pages=max_pages,
            ),
        )
        payload = result.model_dump(mode="json")
        provider_instance_name = _provider_instance_name(request)
        payload["items"] = [
            attach_security_violation_object_metadata(
                item,
                provider_instance_name=provider_instance_name,
            )
            for item in payload.get("items", [])
        ]
        total = payload.get("total")
        visible_total = total if isinstance(total, int) else len(payload["items"])
        return tool_result(
            payload,
            summary=(
                f"Found {visible_total} SmartCMP Security violations."
            ),
            request=request,
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def analyze_security_violation(
    ctx: RunContext[Any],
    violation_id: str,
) -> dict[str, Any]:
    """Re-read and analyze one authoritative SmartCMP Security violation.

    Args:
        ctx: AtlasClaw request context for the selected SmartCMP instance.
        violation_id: Real CMP violation identifier from trusted metadata.

    Returns:
        Security-specific facts, inference inputs, evidence gaps, manual
        remediation guidance, and validation guidance for LLM synthesis.
    """

    try:
        result, request = await execute_with_request(
            ctx,
            analyze_security_violation_service,
            SecurityViolationAnalysisQuery(violation_id=violation_id),
        )
        payload = result.model_dump(mode="json")
        confirmed_facts = payload.get("cmp_confirmed_facts")
        if not isinstance(confirmed_facts, dict):
            raise RuntimeError(
                "Security analysis result is missing cmp_confirmed_facts."
            )
        violation = confirmed_facts.get("violation")
        if not isinstance(violation, dict):
            raise RuntimeError(
                "Security analysis result is missing cmp_confirmed_facts.violation."
            )
        source = dict(violation)
        policy = confirmed_facts.get("policy")
        if isinstance(policy, dict) and not source.get("policyName"):
            source["policyName"] = policy.get("name") or policy.get("policyName")
        resource = confirmed_facts.get("resource")
        if isinstance(resource, dict) and not source.get("resourceName"):
            identity = resource.get("identity")
            source["resourceName"] = (
                identity.get("name")
                if isinstance(identity, dict)
                else resource.get("name")
            )
        projected = attach_security_violation_object_metadata(
            payload,
            violation=source,
            include_mark_fixed=True,
            provider_instance_name=_provider_instance_name(request),
        )
        return tool_result(
            projected,
            summary=f"Collected current evidence for Security violation {violation_id}.",
            request=request,
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def mark_security_violation_fixed(
    ctx: RunContext[Any],
    violation_id: str,
    confirmed: bool,
) -> dict[str, Any]:
    """Mark one Security violation FIXED after explicit user confirmation.

    This operation changes only the CMP violation state. It neither executes a
    resource repair nor proves that the underlying resource was remediated.

    Args:
        ctx: AtlasClaw request context for the selected SmartCMP instance.
        violation_id: Real CMP violation identifier from trusted metadata.
        confirmed: Must be true only after the user confirms the exact status
            change and understands that the resource is not modified.

    Returns:
        Before/after CMP status evidence with ``resource_remediated=false``.
    """

    try:
        result, request = await execute_with_request(
            ctx,
            mark_security_violation_fixed_service,
            SecurityViolationMarkFixedInput(
                violation_id=violation_id,
                confirmed=confirmed,
            ),
        )
        return tool_result(
            result,
            summary=(
                f"Marked Security violation {violation_id} as FIXED; "
                "the resource was not remediated."
            ),
            request=request,
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)
