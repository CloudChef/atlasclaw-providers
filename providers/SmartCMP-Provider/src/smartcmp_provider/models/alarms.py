"""Typed inputs and outputs for SmartCMP alarm evidence queries."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from smartcmp_provider.models.object_operations import AvailableOperation


class AlarmListQuery(BaseModel):
    """Describe one bounded SmartCMP alert list query."""

    model_config = ConfigDict(frozen=True)

    filters: dict[str, Any] = Field(default_factory=dict)


class AlarmListResult(BaseModel):
    """Return raw alert facts and optional pagination total."""

    model_config = ConfigDict(frozen=True)

    items: tuple[dict[str, Any], ...] = ()
    total: int | None = None


class ResourceAlertListQuery(BaseModel):
    """Describe exact resource-alert association requirements.

    The query is shared by AtlasClaw and other adapters that need verified
    current or recently resolved alerts for one already-resolved resource.
    """

    model_config = ConfigDict(frozen=True)

    resource_id: str = Field(min_length=1)
    resource_name: str = ""
    scope: Literal["current", "current_and_recent"] = "current_and_recent"
    days: int = Field(default=7, ge=1)
    size: int = Field(default=20, ge=1)
    level: int | None = None
    alarm_type: str = ""
    alarm_categories: tuple[str, ...] = ()


class ResourceAlertCoverage(BaseModel):
    """Report confidence and gaps for exact resource-alert association."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    resource_name: str = Field(serialization_alias="resourceName")
    scope: Literal["current", "current_and_recent"]
    current_statuses: tuple[str, ...] = Field(
        serialization_alias="currentStatuses",
    )
    resolved_trigger_lookback_days: int | None = Field(
        serialization_alias="resolvedTriggerLookbackDays",
    )
    association_status: Literal["complete", "partial", "indeterminate"] = Field(
        serialization_alias="associationStatus",
    )
    queries_attempted: int = Field(serialization_alias="queriesAttempted")
    queries_succeeded: int = Field(serialization_alias="queriesSucceeded")
    candidate_count: int = Field(serialization_alias="candidateCount")
    matched_count: int = Field(serialization_alias="matchedCount")
    unverified_candidate_count: int = Field(
        serialization_alias="unverifiedCandidateCount",
    )
    lifecycle_conflict_count: int = Field(
        serialization_alias="lifecycleConflictCount",
    )
    errors: tuple[str, ...] = ()


class ResourceAlertListResult(BaseModel):
    """Return verified resource alerts and their association coverage."""

    model_config = ConfigDict(frozen=True)

    items: tuple[dict[str, Any], ...] = ()
    coverage: ResourceAlertCoverage


class AlarmAnalysisFactsQuery(BaseModel):
    """Select one alert and its bounded supporting analysis facts."""

    model_config = ConfigDict(frozen=True)

    alert_id: str = Field(min_length=1)
    days: int = Field(default=7, ge=1)


class AlarmAnalysisFactsResult(BaseModel):
    """Return alert, policy, and optional overview/statistical facts."""

    model_config = ConfigDict(frozen=True)

    alert: dict[str, Any]
    policy: dict[str, Any]
    detail: dict[str, Any] = Field(default_factory=dict)


class AlarmAnalysisResult(BaseModel):
    """Return one complete deterministic alert assessment."""

    model_config = ConfigDict(frozen=True)

    alert_ids: tuple[str, ...]
    facts: tuple[dict[str, Any], ...]
    assessment: dict[str, Any]
    recommendations: tuple[dict[str, Any], ...]
    suggested_status_operation: dict[str, Any]
    available_operations: tuple[AvailableOperation, ...] = ()


class AlarmMetricGroupsQuery(BaseModel):
    """Select monitoring-model metric groups by component type."""

    model_config = ConfigDict(frozen=True)

    component_type: str = Field(min_length=1)


class AlarmResourceMonitorQuery(BaseModel):
    """Select the monitor binding for one SmartCMP resource."""

    model_config = ConfigDict(frozen=True)

    resource_id: str = Field(min_length=1)


class AlarmPayloadResult(BaseModel):
    """Return one raw SmartCMP alarm or monitoring evidence payload."""

    model_config = ConfigDict(frozen=True)

    payload: Any = None


class AlarmOperationInput(BaseModel):
    """Describe one confirmed alert-state update."""

    model_config = ConfigDict(frozen=True)

    alert_ids: tuple[str, ...] = Field(min_length=1)
    action: Literal["mute", "resolve", "reopen"]


class AlarmOperationResult(BaseModel):
    """Return the submitted alert-state update and upstream response."""

    model_config = ConfigDict(frozen=True)

    alert_ids: tuple[str, ...]
    action: Literal["mute", "resolve", "reopen"]
    status: str
    response: Any = None


class ResourceHealthQuery(BaseModel):
    """Select one explicit resource and monitoring window for health evidence."""

    model_config = ConfigDict(frozen=True)

    resource_id: str = Field(min_length=1)
    resource_name: str = ""
    window_hours: int = Field(default=24, ge=1, le=168)


class ResourceHealthEvidence(BaseModel):
    """Return the bounded SmartCMP Provider health-evidence payload."""

    model_config = ConfigDict(frozen=True, extra="allow")

    object_type: str
    object_name: str
    analysis_mode: str
    analysis_contract: dict[str, Any]
    resource: dict[str, Any]
    window: dict[str, Any]
    monitoringModel: dict[str, Any]
    monitoring_state: str
    observations: tuple[dict[str, Any], ...] = ()
    missingEvidence: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
