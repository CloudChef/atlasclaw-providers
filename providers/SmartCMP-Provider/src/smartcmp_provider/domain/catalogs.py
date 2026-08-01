"""SmartCMP service-catalog availability rules shared by output adapters."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from smartcmp_provider.domain.object_operations import available_operation
from smartcmp_provider.models.object_operations import AvailableOperation


def catalog_is_requestable(catalog: Mapping[str, Any]) -> bool:
    """Return whether SmartCMP reports a catalog as currently requestable.

    Args:
        catalog: Catalog facts returned by a SmartCMP list or detail operation.

    Returns:
        ``True`` only for the authoritative ``PUBLISHED`` state.
    """

    state = str(catalog.get("status") or catalog.get("state") or "").strip().upper()
    return state == "PUBLISHED"


def available_catalog_operations(
    catalog: Mapping[str, Any],
) -> tuple[AvailableOperation, ...]:
    """Return object operations justified by one catalog result."""

    catalog_id = str(catalog.get("id") or "").strip()
    if not catalog_id:
        return ()
    operations = [
        available_operation(
            "view_detail",
            "smartcmp.catalogs.detail",
            arguments={"catalog_id": catalog_id},
        )
    ]
    if catalog_is_requestable(catalog):
        operations.append(
            available_operation(
                "request",
                "smartcmp.requests.submit",
                arguments={},
                required_inputs=("body",),
            )
        )
    return tuple(operations)
