"""AtlasClaw Tool adapters for SmartCMP approval reads and decisions."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Literal


_SHARED_SCRIPTS = Path(__file__).resolve().parents[2] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from _atlasclaw_adapter import (  # noqa: E402
    RunContext,
    execute,
    execute_with_request,
    split_values,
    tool_error,
    tool_result,
)
from _approval_object_actions import attach_approval_object_metadata  # noqa: E402
from smartcmp_provider.domain.views import (  # noqa: E402
    project_approval_detail,
    project_pending_list,
)
from smartcmp_provider.models.approvals import (  # noqa: E402
    ApprovalDecisionInput,
    ApprovalDetailQuery,
    ApprovalListResult,
    ApprovalListQuery,
)
from smartcmp_provider.operations.approvals import (  # noqa: E402
    execute_approval_decision,
    get_pending_approval_detail,
)
from smartcmp_provider.services.approval_analysis import (  # noqa: E402
    get_approval_analysis_bundle,
)
from smartcmp_provider.services.approval_queue import (  # noqa: E402
    get_pending_approval_queue,
)


async def list_pending(
    ctx: RunContext[Any],
    days: int | None = None,
) -> dict[str, Any]:
    """List pending approvals visible to the selected SmartCMP principal."""

    try:
        queue, request = await execute_with_request(
            ctx,
            get_pending_approval_queue,
            ApprovalListQuery(days=days),
        )
        result = project_pending_list(
            ApprovalListResult(items=queue.items, total=queue.total)
        )
        items: list[dict[str, Any]] = []
        for index, (projected, raw) in enumerate(
            zip(result.items, queue.items, strict=True),
            start=1,
        ):
            item = attach_approval_object_metadata(
                projected.model_dump(mode="json"),
                item=raw,
                ui_base_url=request.context.instance.ui_base_url,
                include_detail_actions=False,
            )
            item["index"] = index
            items.append(item)
        payload = {"items": items, "total": result.total}
        return tool_result(
            payload,
            summary=_format_pending_output(items, total=result.total),
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def get_request_detail(
    ctx: RunContext[Any],
    identifier: str,
    days: int = 90,
) -> dict[str, Any]:
    """Return one pending approval selected by visible SmartCMP Request ID."""

    try:
        raw_result, request = await execute_with_request(
            ctx,
            get_pending_approval_detail,
            ApprovalDetailQuery(request_id=identifier, days=days),
        )
        result = project_approval_detail(raw_result)
        projected = attach_approval_object_metadata(
            result.model_dump(mode="json"),
            item=raw_result.item,
            ui_base_url=request.context.instance.ui_base_url,
            include_detail_actions=True,
        )
        return tool_result(
            projected,
            summary=_format_detail_output(result.model_dump(mode="json")),
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


def _format_pending_output(
    items: list[dict[str, Any]],
    *,
    total: int,
) -> str:
    """Render the complete visible result required by ``tool_only_ok``."""

    if not items:
        return "No pending SmartCMP approval requests were found."
    lines = [
        f"Found {total} pending approval requests.",
        "",
        "| # | Request ID | Name | Catalog | Applicant | Step | Approver |",
        "|---:|---|---|---|---|---|---|",
    ]
    for item in items:
        lines.append(
            "| {index} | {request_id} | {name} | {catalog_name} | "
            "{applicant} | {approval_step} | {current_approver} |".format(
                **{
                    key: str(item.get(key) or "-").replace("|", "\\|")
                    for key in (
                        "index",
                        "request_id",
                        "name",
                        "catalog_name",
                        "applicant",
                        "approval_step",
                        "current_approver",
                    )
                }
            )
        )
    return "\n".join(lines)


def _format_detail_output(detail: dict[str, Any]) -> str:
    """Render one approval detail without exposing workflow-internal IDs."""

    request = detail.get("request")
    if not isinstance(request, dict):
        request = {}
    fields = (
        ("Request ID", detail.get("request_id")),
        ("Name", request.get("name")),
        ("Catalog", request.get("catalog_name")),
        ("Description", request.get("description")),
        ("Applicant", request.get("applicant")),
        ("Approval step", request.get("approval_step")),
        ("Current approver", request.get("current_approver")),
        ("State", request.get("state")),
    )
    lines = ["SmartCMP approval detail:"]
    lines.extend(
        f"- {label}: {value}"
        for label, value in fields
        if value not in (None, "")
    )
    return "\n".join(lines)


async def analyze_request(
    ctx: RunContext[Any],
    identifier: str,
    days: int = 90,
) -> dict[str, Any]:
    """Collect read-only approval evidence without making a decision."""

    try:
        bundle, request = await execute_with_request(
            ctx,
            get_approval_analysis_bundle,
            ApprovalDetailQuery(request_id=identifier, days=days),
        )
        detail, result = bundle
        projected = attach_approval_object_metadata(
            result.model_dump(mode="json"),
            item=detail.item,
            ui_base_url=request.context.instance.ui_base_url,
            include_detail_actions=True,
        )
        return tool_result(
            projected,
            summary=f"Collected read-only evidence for {result.request_id}.",
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)


async def approve(
    ctx: RunContext[Any],
    ids: str | list[str],
    reason: str | None = None,
) -> dict[str, Any]:
    """Approve user-confirmed SmartCMP Request IDs exactly once."""

    return await _decide(ctx, decision="approve", ids=ids, reason=reason)


async def reject(
    ctx: RunContext[Any],
    ids: str | list[str],
    reason: str | None = None,
) -> dict[str, Any]:
    """Reject user-confirmed SmartCMP Request IDs exactly once."""

    return await _decide(ctx, decision="reject", ids=ids, reason=reason)


async def _decide(
    ctx: Any,
    *,
    decision: Literal["approve", "reject"],
    ids: str | list[str],
    reason: str | None,
) -> dict[str, Any]:
    """Execute one already-confirmed approval decision through SmartCMP Provider."""

    try:
        request_ids = split_values(ids)
        result = await execute(
            ctx,
            execute_approval_decision,
            ApprovalDecisionInput(
                decision=decision,
                request_ids=request_ids,
                reason=reason or "",
            ),
        )
        completed = [
            item.request_id for item in result.items if item.outcome == "succeeded"
        ]
        failed = [item for item in result.items if item.outcome == "failed"]
        unknown = [
            item.request_id for item in result.items if item.outcome == "unknown"
        ]
        verb = "Approved" if decision == "approve" else "Rejected"
        decision_name = "Approval" if decision == "approve" else "Rejection"
        summaries = []
        if completed:
            summaries.append(f"{verb}: {', '.join(completed)}")
        if failed:
            summaries.extend(
                f"{decision_name} failed: {item.request_id}"
                + (f" — {item.message}" if item.message else "")
                for item in failed
            )
        if unknown:
            summaries.append(
                f"{decision_name} submitted but outcome could not be confirmed: "
                + ", ".join(unknown)
            )
        summary = "\n".join(summaries)
        return tool_result(result, summary=summary)
    except (ValueError, RuntimeError) as error:
        return tool_error(error)
