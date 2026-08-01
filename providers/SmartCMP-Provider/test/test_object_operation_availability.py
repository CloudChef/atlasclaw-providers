"""Critical contracts for protocol-neutral SmartCMP object operations."""

from smartcmp_provider.domain.alarms import available_alert_operations
from smartcmp_provider.domain.approval_context import (
    available_approval_operations,
)
from smartcmp_provider.domain.catalogs import available_catalog_operations
from smartcmp_provider.domain.cost import available_cost_operations
from smartcmp_provider.domain.resource_actions import (
    available_resource_operations,
)
from smartcmp_provider.domain.resource_views import build_resource_detail_view


def test_each_object_domain_returns_current_provider_capability_ids() -> None:
    """Give MCP and AtlasClaw one shared source for object action eligibility."""

    catalog_operations = available_catalog_operations(
        {"id": "catalog-1", "status": "PUBLISHED"}
    )
    assert _capabilities(catalog_operations) == (
        "smartcmp.catalogs.detail",
        "smartcmp.requests.submit",
    )
    assert catalog_operations[1].tool_name == "smartcmp_submit_request"
    assert catalog_operations[1].required_inputs == ("body",)
    assert _capabilities(available_approval_operations("RES20260731000001")) == (
        "smartcmp.approvals.detail",
        "smartcmp.approvals.analyze",
        "smartcmp.approvals.approve",
        "smartcmp.approvals.reject",
    )
    resource_operations = available_resource_operations(
        "resource-1",
        category="cloud-resource",
    )
    assert _capabilities(resource_operations) == (
        "smartcmp.resources.detail",
        "smartcmp.resources.analysis_evidence",
        "smartcmp.resources.operations",
    )
    assert resource_operations[0].arguments["category"] == "cloud-resource"
    assert resource_operations[2].arguments["category"] == "cloud-resource"
    detail = build_resource_detail_view(
        "resource-1",
        {"id": "resource-1", "name": "generic-resource"},
        category="cloud-resource",
    )
    assert detail.available_operations[0].arguments["category"] == (
        "cloud-resource"
    )
    assert _capabilities(
        available_alert_operations(
            {"id": "alert-1", "status": "ALERT_FIRING"}
        )
    ) == (
        "smartcmp.alarms.analyze",
        "smartcmp.alarms.operate",
        "smartcmp.alarms.operate",
    )
    assert _capabilities(
        available_cost_operations(
            {"id": "violation-1", "fixType": "DAY2"}
        )
    ) == (
        "smartcmp.cost.analyze_recommendation",
        "smartcmp.cost.execute",
    )


def _capabilities(operations) -> tuple[str, ...]:
    return tuple(operation.capability_id for operation in operations)
