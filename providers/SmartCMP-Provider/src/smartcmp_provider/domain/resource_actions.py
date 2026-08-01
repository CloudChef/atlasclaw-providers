"""Derive protocol-neutral operations for concrete SmartCMP resources."""

from __future__ import annotations

from smartcmp_provider.domain.object_operations import available_operation
from smartcmp_provider.models.object_operations import AvailableOperation


def normalize_operation_id(operation_id: str) -> str:
    """Normalize a SmartCMP operation ID to lowercase underscore form."""

    return (operation_id or "").strip().lower().replace("-", "_").replace(" ", "_")


def available_resource_operations(
    resource_id: str,
    *,
    category: str = "virtual-machines",
) -> tuple[AvailableOperation, ...]:
    """Return discovery and analysis operations for one exact resource ID."""

    normalized_id = str(resource_id or "").strip()
    if not normalized_id:
        return ()
    normalized_category = str(category or "virtual-machines").strip()
    return (
        available_operation(
            "view_detail",
            "smartcmp.resources.detail",
            arguments={
                "resource_id": normalized_id,
                "category": normalized_category,
            },
        ),
        available_operation(
            "analyze",
            "smartcmp.resources.analysis_evidence",
            arguments={"resource_ids": [normalized_id]},
        ),
        available_operation(
            "list_operations",
            "smartcmp.resources.operations",
            arguments={
                "resource_id": normalized_id,
                "category": normalized_category,
            },
        ),
    )


def available_resource_execution(
    resource_id: str,
    operation_id: str,
    *,
    category: str,
) -> AvailableOperation | None:
    """Return the confirmed execution capability for a discovered operation."""

    normalized_resource_id = str(resource_id or "").strip()
    normalized_operation_id = str(operation_id or "").strip()
    if not normalized_resource_id or not normalized_operation_id:
        return None
    return available_operation(
        "operate",
        "smartcmp.resources.operate",
        arguments={
            "resource_id": normalized_resource_id,
            "action": normalized_operation_id,
            "category": str(category or "virtual-machines").strip(),
        },
    )
