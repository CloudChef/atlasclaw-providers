"""Shared pending-approval queue orchestration."""

from __future__ import annotations

from smartcmp_provider.domain.approval_context import (
    items_need_flavor_lookup,
    sort_pending_items,
)
from smartcmp_provider.domain.approval_specs import extract_flavor_name_map
from smartcmp_provider.domain.views import project_pending_list
from smartcmp_provider.errors import SmartCmpError
from smartcmp_provider.models.approvals import (
    ApprovalListQuery,
    ApprovalListResult,
    ApprovalQueueResult,
)
from smartcmp_provider.models.views import PendingApprovalListView
from smartcmp_provider.operations.approvals import (
    list_approval_flavors,
    list_pending_approvals,
)
from smartcmp_provider.transport.client import SmartCmpClient


async def get_pending_approval_queue(
    client: SmartCmpClient,
    query: ApprovalListQuery,
) -> ApprovalQueueResult:
    """Fetch, sort, and optionally enrich the pending approval queue."""

    result = await list_pending_approvals(client, query)
    items = sort_pending_items(list(result.items))
    flavor_names_by_id: dict[str, str] = {}
    warnings: list[str] = []
    if items_need_flavor_lookup(items):
        try:
            flavors = await list_approval_flavors(client)
            flavor_names_by_id = extract_flavor_name_map(
                list(flavors.items)
            )
        except SmartCmpError:
            warnings.append(
                "Flavor names could not be loaded; unresolved specifications "
                "were omitted."
            )
    return ApprovalQueueResult(
        items=tuple(items),
        total=result.total,
        flavor_names_by_id=flavor_names_by_id,
        warnings=tuple(warnings),
    )


async def get_pending_approval_list_view(
    client: SmartCmpClient,
    query: ApprovalListQuery,
) -> PendingApprovalListView:
    """Return the safe pending queue projection used by protocol adapters."""

    queue = await get_pending_approval_queue(client, query)
    return project_pending_list(
        ApprovalListResult(items=queue.items, total=queue.total)
    )
