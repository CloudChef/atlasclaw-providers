"""Typed inputs and outputs for SmartCMP request submission and status."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SubmissionOutcome = Literal[
    "failed",
    "pending_verification",
    "pending_workflow",
    "initialization_failed",
    "success",
]


class RequestActorIdentity(BaseModel):
    """Carry an adapter-resolved SmartCMP request actor identity.

    The model is entry-neutral: AtlasClaw may derive it from trusted request
    context, while another adapter may omit it and let SmartCMP Provider resolve
    the identity through the credential-bound current-user endpoint.
    """

    model_config = ConfigDict(frozen=True)

    user_id: str = ""
    login_id: str = ""


class RequestSubmissionInput(BaseModel):
    """Describe one confirmed request payload and post-submit verification policy."""

    model_config = ConfigDict(frozen=True)

    body: dict[str, Any]
    actor: RequestActorIdentity | None = None
    verification_attempts: int = Field(default=8, ge=1)
    verification_interval_seconds: float = Field(default=1.0, ge=0)


class RequestSubmissionItem(BaseModel):
    """Describe one created request without exposing its internal lookup ID."""

    model_config = ConfigDict(frozen=True)

    outcome: SubmissionOutcome
    request_id: str = ""
    submit_state: str = ""
    state: str = ""
    provision_state: str = ""
    error: str = ""
    message: str = ""
    verification_status_code: int | None = None
    diagnostics: tuple[str, ...] = ()


class RequestSubmissionResult(BaseModel):
    """Return safe request data and outcomes from one non-retried submit.

    The submitted body remains useful for agent explanations, but its recursive
    validator prevents catalog credential fields from crossing either the
    AtlasClaw or MCP adapter boundary.
    """

    model_config = ConfigDict(frozen=True)

    normalized_body: dict[str, Any]
    items: tuple[RequestSubmissionItem, ...]
    overall_failed: bool = False

    @field_validator("normalized_body", mode="before")
    @classmethod
    def redact_normalized_body(cls, value: Any) -> dict[str, Any]:
        """Prevent submitted passwords from crossing any Adapter boundary."""

        redacted = _redact_submission_secrets(value)
        return redacted if isinstance(redacted, dict) else {}


class RequestStatusQuery(BaseModel):
    """Select one request by its user-facing SmartCMP Request ID."""

    model_config = ConfigDict(frozen=True)

    request_id: str


class RequestStatusResult(BaseModel):
    """Return the resolved request detail and normalized status metadata."""

    model_config = ConfigDict(frozen=True)

    detail: dict[str, Any]
    metadata: dict[str, Any]


def _redact_submission_secrets(value: Any) -> Any:
    """Recursively clone request data while masking credential passwords."""

    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).replace("_", "").replace("-", "").casefold()
            if normalized_key in {"credentialpassword", "password"}:
                redacted[key] = "***"
            else:
                redacted[key] = _redact_submission_secrets(item)
        return redacted
    if isinstance(value, list):
        return [_redact_submission_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_submission_secrets(item) for item in value)
    return value
