"""Typed contracts for SmartCMP security compliance evidence and actions."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


SecurityCoverage = Literal["complete", "partial", "failed"]


class SecurityOverviewQuery(BaseModel):
    """Select the time range for one security compliance overview.

    Times are epoch milliseconds. When neither value is supplied, the service
    uses the current time and the preceding 30 days.
    """

    model_config = ConfigDict(frozen=True)

    start_time: int | None = Field(default=None, ge=0)
    end_time: int | None = Field(default=None, ge=0)


class SecurityOverviewResult(BaseModel):
    """Return aggregated Security policy, execution, violation, and trend facts."""

    model_config = ConfigDict(frozen=True)

    time_range: dict[str, int]
    summary: dict[str, Any]
    compliance_overview: Any = None
    violation_overview: Any = None
    compliance_trend: Any = None
    violation_trend: Any = None
    source_coverage: dict[str, SecurityCoverage]
    errors: tuple[str, ...] = ()


class SecurityViolationListQuery(BaseModel):
    """Describe a bounded, one-based Security violation list query."""

    model_config = ConfigDict(frozen=True)

    status: str = "ACTIVED"
    severities: tuple[str, ...] = ()
    query_value: str = ""
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)
    max_pages: int = Field(default=1, ge=1, le=50)


class SecurityViolationListResult(BaseModel):
    """Return Security violation rows with explicit pagination coverage."""

    model_config = ConfigDict(frozen=True)

    items: tuple[dict[str, Any], ...] = ()
    page: int = Field(ge=1)
    size: int = Field(ge=1)
    total: int | None = None
    scanned_pages: int = Field(ge=0)
    has_more: bool = False
    next_page: int | None = None
    coverage: SecurityCoverage
    truncated: bool = False
    errors: tuple[str, ...] = ()


class SecurityRecordCollection(BaseModel):
    """Return bounded Security policy or execution inventory records."""

    model_config = ConfigDict(frozen=True)

    items: tuple[dict[str, Any], ...] = ()
    total: int | None = None
    scanned_pages: int = Field(ge=0)
    coverage: SecurityCoverage
    truncated: bool = False


class SecurityViolationAnalysisQuery(BaseModel):
    """Select one Security violation for fresh evidence analysis."""

    model_config = ConfigDict(frozen=True)

    violation_id: str = Field(min_length=1)


class SecurityViolationAnalysisResult(BaseModel):
    """Return separated CMP facts and the contract for LLM security analysis."""

    model_config = ConfigDict(frozen=True)

    violation_id: str
    cmp_confirmed_facts: dict[str, Any]
    llm_inferences: tuple[dict[str, Any], ...] = ()
    enrichment_status: dict[str, str]
    missing_evidence: tuple[str, ...] = ()
    manual_remediation_steps: tuple[str, ...]
    verification_steps: tuple[str, ...]
    analysis_contract: dict[str, Any]
    suggested_next_step: str


class SecurityViolationMarkFixedInput(BaseModel):
    """Select one explicitly confirmed Security violation status update."""

    model_config = ConfigDict(frozen=True)

    violation_id: str = Field(min_length=1)
    confirmed: bool


class SecurityViolationMarkFixedResult(BaseModel):
    """Return the verified result of marking a Security violation as fixed."""

    model_config = ConfigDict(frozen=True)

    violation_id: str
    policy_id: str = ""
    policy_name: str = ""
    resource_id: str = ""
    resource_name: str = ""
    before_status: str
    after_status: str
    resource_remediated: Literal[False] = False
    message: str


class ResourceSecurityViolationQuery(BaseModel):
    """Select one resource for a complete bounded Security violation scan."""

    model_config = ConfigDict(frozen=True)

    resource_id: str = Field(min_length=1)
    max_pages: int = Field(default=50, ge=1, le=50)


class ResourceSecurityViolationResult(BaseModel):
    """Return exact resource-linked violations and global scan coverage."""

    model_config = ConfigDict(frozen=True)

    resource_id: str
    items: tuple[dict[str, Any], ...] = ()
    total: int | None = None
    matched_total: int = Field(ge=0)
    scanned_pages: int = Field(ge=0)
    has_more: bool = False
    next_page: int | None = None
    coverage: SecurityCoverage
    truncated: bool = False
    errors: tuple[str, ...] = ()


class ResourceSecurityAnalysisQuery(BaseModel):
    """Select one resource for combined posture and Security violation analysis."""

    model_config = ConfigDict(frozen=True)

    resource_id: str = Field(min_length=1)


class ResourceSecurityAnalysisResult(BaseModel):
    """Return separate LLM posture evidence and CMP-confirmed violations."""

    model_config = ConfigDict(frozen=True)

    object_type: Literal["resource"] = "resource"
    object_id: str
    object_name: str
    resource: dict[str, Any]
    llm_inferred_posture: dict[str, Any]
    cmp_confirmed_violations: tuple[dict[str, Any], ...] = ()
    violation_coverage: dict[str, Any]
    analysis_contract: dict[str, Any]
    missing_evidence: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
