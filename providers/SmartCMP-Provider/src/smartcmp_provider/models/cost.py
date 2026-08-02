"""Typed inputs and outputs for SmartCMP cost evidence queries."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from smartcmp_provider.models.object_operations import AvailableOperation


class CostListQuery(BaseModel):
    """Describe one bounded paginated cost-domain list query."""

    model_config = ConfigDict(frozen=True)

    filters: dict[str, Any] = Field(default_factory=dict)
    page: int = Field(default=0, ge=0)
    size: int = Field(default=20, ge=1)
    max_pages: int = Field(default=1, ge=1, le=1_000)


class CostItemsResult(BaseModel):
    """Return raw cost-domain facts collected from bounded pages."""

    model_config = ConfigDict(frozen=True)

    items: tuple[dict[str, Any], ...] = ()
    total: int | None = None


class CostRecommendationFactsQuery(BaseModel):
    """Select one cost recommendation and its bounded supporting facts."""

    model_config = ConfigDict(frozen=True)

    violation_id: str = Field(min_length=1)


class CostRecommendationFactsResult(BaseModel):
    """Return one violation plus policy, overview, and history evidence."""

    model_config = ConfigDict(frozen=True)

    violation: dict[str, Any]
    policy: dict[str, Any] | None = None
    saving_summary: Any = None
    operation_summary: Any = None
    saving_trend: Any = None
    resource_top: Any = None
    policy_executions: tuple[dict[str, Any], ...] = ()
    related_policy_count: int = 0


class CurrencyEvidenceResult(BaseModel):
    """Return verified SmartCMP tenant currency facts."""

    model_config = ConfigDict(frozen=True)

    symbol: str | None = None
    code: str = ""
    source: str = ""


class CostExecutionInput(BaseModel):
    """Select one confirmed cost violation for native remediation."""

    model_config = ConfigDict(frozen=True)

    violation_id: str = Field(min_length=1)


class CostExecutionResult(BaseModel):
    """Return facts from one submitted SmartCMP day-two fix request."""

    model_config = ConfigDict(frozen=True)

    violation_id: str
    message: str
    response: Any = None


class CostRecommendationListQuery(CostListQuery):
    """Describe a recommendation list with optional related-policy counts."""

    include_related_policy_count: bool = False


class CostRecommendationListResult(BaseModel):
    """Return normalized recommendation rows and verified currency metadata."""

    model_config = ConfigDict(frozen=True)

    items: tuple[dict[str, Any], ...] = ()
    total: int | None = None
    currency_symbol: str = ""
    currency_code: str = ""


class CostRecommendationAnalysisResult(BaseModel):
    """Return the complete SmartCMP Provider recommendation assessment."""

    model_config = ConfigDict(frozen=True)

    violationId: str
    facts: dict[str, Any]
    assessment: dict[str, Any]
    recommendations: tuple[dict[str, Any], ...]
    suggestedNextStep: str
    available_operations: tuple[AvailableOperation, ...] = ()


class ResourceCostAnalysisQuery(BaseModel):
    """Select one explicit resource for cost evidence analysis."""

    model_config = ConfigDict(frozen=True)

    resource_id: str = Field(min_length=1)


class ResourceCostAnalysisResult(BaseModel):
    """Return the complete bounded resource-first cost evidence payload."""

    model_config = ConfigDict(frozen=True, extra="allow")

    object_type: str
    object_id: str
    object_name: str
    resource: dict[str, Any]
    financialEvidence: dict[str, Any]
    policyCoverage: tuple[dict[str, Any], ...]
    activeViolations: tuple[dict[str, Any], ...]
    platformAssessment: dict[str, Any]
    analysisContract: dict[str, Any]
    missingEvidence: tuple[str, ...]
    errors: tuple[str, ...]


class CostExecutionStatusQuery(BaseModel):
    """Select one cost violation for execution status aggregation."""

    model_config = ConfigDict(frozen=True)

    violation_id: str = Field(min_length=1)


class CostExecutionStatusResult(BaseModel):
    """Return normalized violation and resource execution status evidence."""

    model_config = ConfigDict(frozen=True)

    violationId: str
    overallStatus: str
    sourceAvailability: dict[str, bool]
    trackedExecutionIds: tuple[str, ...]
    recordCounts: dict[str, int]
    statusCounts: dict[str, int]
    violationInstances: tuple[dict[str, Any], ...]
    resourceExecutions: tuple[dict[str, Any], ...]
    records: tuple[dict[str, Any], ...]
    failureMessages: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...]


class CostResourceExecutionCollection(BaseModel):
    """Return normalized resource-execution rows for explicit execution IDs."""

    model_config = ConfigDict(frozen=True)

    items: tuple[dict[str, Any], ...] = ()
    available: bool = True
    warnings: tuple[str, ...] = ()
