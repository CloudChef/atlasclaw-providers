"""Shared normalized SmartCMP resource services."""

from smartcmp_provider.domain.resource_views import build_resource_detail_view
from smartcmp_provider.domain.resource_views import build_resource_operation_view
from smartcmp_provider.models.resources import (
    ResourceDetailQuery,
    ResourceDetailView,
    ResourceOperationsQuery,
    ResourceOperationsView,
)
from smartcmp_provider.operations.resources import (
    get_resource_detail,
    list_resource_operations,
)
from smartcmp_provider.transport.client import SmartCmpClient


async def get_resource_detail_view(
    client: SmartCmpClient,
    query: ResourceDetailQuery,
) -> ResourceDetailView:
    """Resolve and normalize one resource for every output adapter."""

    result = await get_resource_detail(client, query)
    return build_resource_detail_view(
        result.resource_id,
        result.payload,
        category=query.category,
    )


async def get_resource_operations_view(
    client: SmartCmpClient,
    query: ResourceOperationsQuery,
) -> ResourceOperationsView:
    """Resolve and normalize executable operations for every output adapter."""

    result = await list_resource_operations(client, query)
    return ResourceOperationsView(
        category=query.category,
        resource_id=query.resource_id,
        operations=tuple(
            build_resource_operation_view(
                index,
                operation,
                resource_id=query.resource_id,
                resource_category=query.category,
            )
            for index, operation in enumerate(result.operations, start=1)
        ),
    )
