"""Declare adapter-neutral SmartCMP operation and safety metadata.

The registry describes the common Provider surface but does not dispatch calls.
AtlasClaw and MCP retain their own explicit adapters and compatibility names.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

Effect = Literal["read", "write"]
Idempotency = Literal["safe", "idempotent", "non_idempotent"]
Confirmation = Literal["none", "user", "policy"]
Surface = Literal["atlasclaw", "mcp"]


@dataclass(frozen=True, slots=True)
class CapabilitySpec:
    """Describe one provider operation without acting as a string dispatcher.

    Attributes:
        capability_id: Stable provider-domain capability identifier.
        atlasclaw_tool_name: Existing AtlasClaw Tool name kept for compatibility.
        mcp_tool_name: MCP Tool name, or ``None`` when the capability is not exposed.
        input_model: Pydantic model accepted by the domain operation.
        output_model: Pydantic model returned by the domain operation.
        effect: Whether the capability is read-only or mutating.
        idempotency: Retry safety declared for the upstream operation.
        confirmation: Confirmation boundary required before execution.
        surfaces: Adapters allowed to expose this capability.
        destructive: Whether the operation can remove or materially alter state.
    """

    capability_id: str
    atlasclaw_tool_name: str
    mcp_tool_name: str | None
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    effect: Effect
    idempotency: Idempotency
    confirmation: Confirmation
    surfaces: frozenset[Surface]
    destructive: bool = False


def shared_capabilities() -> tuple[CapabilitySpec, ...]:
    """Return the canonical capabilities shared by protocol adapters.

    Imports are intentionally local so the registry stays independent of
    operation implementations and remains the single semantic source for every
    protocol adapter.
    """

    from smartcmp_provider.models.alarms import (
        AlarmAnalysisFactsQuery,
        AlarmAnalysisResult,
        AlarmListQuery,
        AlarmListResult,
        AlarmOperationInput,
        AlarmOperationResult,
        ResourceHealthEvidence,
        ResourceHealthQuery,
    )
    from smartcmp_provider.models.approvals import (
        ApprovalDecisionInput,
        ApprovalDecisionResult,
        ApprovalDetailQuery,
        ApprovalListQuery,
    )
    from smartcmp_provider.models.catalogs import (
        BusinessGroupQuery,
        CatalogDetailQuery,
        CatalogDetailResult,
        CatalogItemsResult,
        CatalogListQuery,
        CatalogListResult,
        FacetQuery,
        FlavorQuery,
        ImageQuery,
        LogicalTemplateQuery,
        PhysicalTemplateQuery,
        ResourceBundleQuery,
    )
    from smartcmp_provider.models.cost import (
        CostExecutionInput,
        CostExecutionResult,
        CostExecutionStatusQuery,
        CostExecutionStatusResult,
        CostRecommendationAnalysisResult,
        CostRecommendationFactsQuery,
        CostRecommendationListQuery,
        CostRecommendationListResult,
        ResourceCostAnalysisQuery,
        ResourceCostAnalysisResult,
    )
    from smartcmp_provider.models.directory import (
        ApplicationListQuery,
        ComponentListQuery,
        DirectoryItemsResult,
        DirectorySearchQuery,
    )
    from smartcmp_provider.models.forms import (
        FormDesignInput,
        FormDesignResult,
        FormReadQuery,
        FormReadResult,
    )
    from smartcmp_provider.models.operations import (
        ResourceActionInput,
        ResourceActionResult,
    )
    from smartcmp_provider.models.objects import (
        ComponentDefinitionView,
        ObjectIdQuery,
        OptimizationPolicyView,
        ScriptDefinitionView,
    )
    from smartcmp_provider.models.requests import (
        RequestStatusQuery,
        RequestSubmissionInput,
        RequestSubmissionResult,
    )
    from smartcmp_provider.models.resources import (
        PermanentResourceRemovalInput,
        PermanentResourceRemovalResult,
        RecycledResourceListResult,
        RecycledResourceQuery,
        ResourceDetailQuery,
        ResourceDetailView,
        ResourceListQuery,
        ResourceListResult,
        ResourceOperationsQuery,
        ResourceOperationsView,
    )
    from smartcmp_provider.models.security_compliance import (
        ResourceSecurityAnalysisQuery,
        ResourceSecurityAnalysisResult,
        ResourceSecurityViolationQuery,
        ResourceSecurityViolationResult,
        SecurityOverviewQuery,
        SecurityOverviewResult,
        SecurityViolationAnalysisQuery,
        SecurityViolationAnalysisResult,
        SecurityViolationListQuery,
        SecurityViolationListResult,
        SecurityViolationMarkFixedInput,
        SecurityViolationMarkFixedResult,
    )
    from smartcmp_provider.models.views import (
        ApprovalAnalysisEvidence,
        ApprovalDetailView,
        PendingApprovalListView,
        RequestStatusView,
    )

    both = frozenset({"atlasclaw", "mcp"})

    # Centralize effect, retry, and confirmation declarations so AtlasClaw and
    # MCP publish the same safety contract for every capability.
    def read(
        capability_id: str,
        tool_name: str,
        input_model: type[BaseModel],
        output_model: type[BaseModel],
        *,
        atlasclaw_tool_name: str | None = None,
    ) -> CapabilitySpec:
        """Declare a retry-safe capability that requires no confirmation."""

        return CapabilitySpec(
            capability_id=capability_id,
            atlasclaw_tool_name=atlasclaw_tool_name or tool_name,
            mcp_tool_name=tool_name,
            input_model=input_model,
            output_model=output_model,
            effect="read",
            idempotency="safe",
            confirmation="none",
            surfaces=both,
        )

    def write(
        capability_id: str,
        tool_name: str,
        input_model: type[BaseModel],
        output_model: type[BaseModel],
        *,
        destructive: bool = False,
    ) -> CapabilitySpec:
        """Declare a confirmed, non-idempotent Provider capability."""

        # SmartCMP writes are deliberately classified as non-idempotent. Each
        # adapter must request user confirmation and must not retry unknown outcomes.
        return CapabilitySpec(
            capability_id=capability_id,
            atlasclaw_tool_name=tool_name,
            mcp_tool_name=tool_name,
            input_model=input_model,
            output_model=output_model,
            effect="write",
            idempotency="non_idempotent",
            confirmation="user",
            surfaces=both,
            destructive=destructive,
        )

    return (
        read(
            "smartcmp.catalogs.list",
            "smartcmp_list_services",
            CatalogListQuery,
            CatalogListResult,
        ),
        read(
            "smartcmp.catalogs.detail",
            "smartcmp_get_request_catalog",
            CatalogDetailQuery,
            CatalogDetailResult,
        ),
        read(
            "smartcmp.catalogs.business_groups",
            "smartcmp_list_available_bgs",
            BusinessGroupQuery,
            CatalogItemsResult,
        ),
        read(
            "smartcmp.catalogs.resource_bundles",
            "smartcmp_list_resource_bundles",
            ResourceBundleQuery,
            CatalogItemsResult,
        ),
        read(
            "smartcmp.catalogs.flavors",
            "smartcmp_list_flavors",
            FlavorQuery,
            CatalogItemsResult,
        ),
        read(
            "smartcmp.catalogs.logical_templates",
            "smartcmp_list_logical_templates",
            LogicalTemplateQuery,
            CatalogItemsResult,
        ),
        read(
            "smartcmp.catalogs.physical_templates",
            "smartcmp_list_physical_templates",
            PhysicalTemplateQuery,
            CatalogItemsResult,
        ),
        read(
            "smartcmp.catalogs.images",
            "smartcmp_list_images",
            ImageQuery,
            CatalogItemsResult,
        ),
        read(
            "smartcmp.catalogs.facets",
            "smartcmp_list_facets",
            FacetQuery,
            CatalogItemsResult,
        ),
        read(
            "smartcmp.directory.business_groups",
            "smartcmp_list_business_groups",
            DirectorySearchQuery,
            DirectoryItemsResult,
            atlasclaw_tool_name="smartcmp_list_all_business_groups",
        ),
        read(
            "smartcmp.directory.resource_pools",
            "smartcmp_list_resource_pools",
            DirectorySearchQuery,
            DirectoryItemsResult,
            atlasclaw_tool_name="smartcmp_list_all_resource_pools",
        ),
        read(
            "smartcmp.directory.applications",
            "smartcmp_list_applications",
            ApplicationListQuery,
            DirectoryItemsResult,
        ),
        read(
            "smartcmp.directory.components",
            "smartcmp_list_components",
            ComponentListQuery,
            DirectoryItemsResult,
        ),
        write(
            "smartcmp.requests.submit",
            "smartcmp_submit_request",
            RequestSubmissionInput,
            RequestSubmissionResult,
        ),
        read(
            "smartcmp.requests.status",
            "smartcmp_get_request_status",
            RequestStatusQuery,
            RequestStatusView,
        ),
        read(
            "smartcmp.resources.list",
            "smartcmp_list_all_resource",
            ResourceListQuery,
            ResourceListResult,
        ),
        read(
            "smartcmp.resources.detail",
            "smartcmp_resource_detail",
            ResourceDetailQuery,
            ResourceDetailView,
        ),
        read(
            "smartcmp.resources.operations",
            "smartcmp_list_resource_operations",
            ResourceOperationsQuery,
            ResourceOperationsView,
        ),
        write(
            "smartcmp.resources.operate",
            "smartcmp_operate_resource",
            ResourceActionInput,
            ResourceActionResult,
            destructive=True,
        ),
        read(
            "smartcmp.resources.recycle_bin.list",
            "smartcmp_list_recycled_resources",
            RecycledResourceQuery,
            RecycledResourceListResult,
        ),
        write(
            "smartcmp.resources.recycle_bin.permanently_remove",
            "smartcmp_permanently_remove_recycled_resource",
            PermanentResourceRemovalInput,
            PermanentResourceRemovalResult,
            destructive=True,
        ),
        read(
            "smartcmp.approvals.list",
            "smartcmp_list_pending",
            ApprovalListQuery,
            PendingApprovalListView,
        ),
        read(
            "smartcmp.approvals.detail",
            "smartcmp_get_request_detail",
            ApprovalDetailQuery,
            ApprovalDetailView,
        ),
        read(
            "smartcmp.approvals.analyze",
            "smartcmp_analyze_approval_request",
            ApprovalDetailQuery,
            ApprovalAnalysisEvidence,
        ),
        write(
            "smartcmp.approvals.approve",
            "smartcmp_approve",
            ApprovalDecisionInput,
            ApprovalDecisionResult,
            destructive=True,
        ),
        write(
            "smartcmp.approvals.reject",
            "smartcmp_reject",
            ApprovalDecisionInput,
            ApprovalDecisionResult,
            destructive=True,
        ),
        read(
            "smartcmp.resources.security.analyze",
            "smartcmp_analyze_resource_security",
            ResourceSecurityAnalysisQuery,
            ResourceSecurityAnalysisResult,
        ),
        read(
            "smartcmp.resources.security.violations.list",
            "smartcmp_list_resource_security_violations",
            ResourceSecurityViolationQuery,
            ResourceSecurityViolationResult,
        ),
        read(
            "smartcmp.security.overview",
            "smartcmp_get_security_overview",
            SecurityOverviewQuery,
            SecurityOverviewResult,
        ),
        read(
            "smartcmp.security.violations.list",
            "smartcmp_list_security_violations",
            SecurityViolationListQuery,
            SecurityViolationListResult,
        ),
        read(
            "smartcmp.security.violation.analyze",
            "smartcmp_analyze_security_violation",
            SecurityViolationAnalysisQuery,
            SecurityViolationAnalysisResult,
        ),
        write(
            "smartcmp.security.violation.mark_fixed",
            "smartcmp_mark_security_violation_fixed",
            SecurityViolationMarkFixedInput,
            SecurityViolationMarkFixedResult,
        ),
        read(
            "smartcmp.alarms.analyze",
            "smartcmp_analyze_alert",
            AlarmAnalysisFactsQuery,
            AlarmAnalysisResult,
        ),
        read(
            "smartcmp.alarms.list",
            "smartcmp_list_alerts",
            AlarmListQuery,
            AlarmListResult,
        ),
        write(
            "smartcmp.alarms.operate",
            "smartcmp_operate_alert",
            AlarmOperationInput,
            AlarmOperationResult,
            destructive=True,
        ),
        read(
            "smartcmp.resources.health",
            "smartcmp_analyze_resource_health",
            ResourceHealthQuery,
            ResourceHealthEvidence,
            atlasclaw_tool_name="analyze_resource_health",
        ),
        read(
            "smartcmp.cost.list_recommendations",
            "smartcmp_list_cost_recommendations",
            CostRecommendationListQuery,
            CostRecommendationListResult,
        ),
        read(
            "smartcmp.cost.analyze_recommendation",
            "smartcmp_analyze_cost_recommendation",
            CostRecommendationFactsQuery,
            CostRecommendationAnalysisResult,
        ),
        read(
            "smartcmp.cost.analyze_resource",
            "smartcmp_analyze_resource_cost",
            ResourceCostAnalysisQuery,
            ResourceCostAnalysisResult,
        ),
        read(
            "smartcmp.cost.execution_status",
            "smartcmp_get_cost_execution_status",
            CostExecutionStatusQuery,
            CostExecutionStatusResult,
            atlasclaw_tool_name="smartcmp_track_cost_optimization",
        ),
        write(
            "smartcmp.cost.execute",
            "smartcmp_execute_cost_optimization",
            CostExecutionInput,
            CostExecutionResult,
            destructive=True,
        ),
        read(
            "smartcmp.forms.read",
            "smartcmp_read_form",
            FormReadQuery,
            FormReadResult,
            atlasclaw_tool_name="smartcmp_read_form_schema",
        ),
        read(
            "smartcmp.forms.design",
            "smartcmp_design_form",
            FormDesignInput,
            FormDesignResult,
            atlasclaw_tool_name="smartcmp_design_form_schema",
        ),
        read(
            "smartcmp.designers.component.read",
            "smartcmp_read_component_definition",
            ObjectIdQuery,
            ComponentDefinitionView,
            atlasclaw_tool_name="smartcmp_read_current_component_file",
        ),
        read(
            "smartcmp.designers.optimization_policy.read",
            "smartcmp_read_optimization_policy",
            ObjectIdQuery,
            OptimizationPolicyView,
            atlasclaw_tool_name="smartcmp_read_current_optimization_policy",
        ),
        read(
            "smartcmp.designers.script.read",
            "smartcmp_read_script_definition",
            ObjectIdQuery,
            ScriptDefinitionView,
            atlasclaw_tool_name="smartcmp_read_current_script_definition",
        ),
    )


def capability_by_id(capability_id: str) -> CapabilitySpec:
    """Return one canonical capability declaration by its stable ID.

    Raises:
        KeyError: If the requested capability is not in the shared registry.
    """

    for spec in shared_capabilities():
        if spec.capability_id == capability_id:
            return spec
    raise KeyError(f"Unknown SmartCMP capability: {capability_id}")


def mcp_capabilities() -> dict[str, CapabilitySpec]:
    """Return the MCP Tool-name index from the canonical capability registry."""

    return {
        spec.mcp_tool_name: spec
        for spec in shared_capabilities()
        if spec.mcp_tool_name is not None and "mcp" in spec.surfaces
    }
