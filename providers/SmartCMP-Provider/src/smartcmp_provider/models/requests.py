"""Typed inputs and outputs for SmartCMP request submission and status."""

from __future__ import annotations

import re
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

        redacted = redact_request_secrets(value)
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


_REQUEST_IDENTIFIER_WORD_PATTERN = re.compile(
    r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|[0-9]+"
)
_SENSITIVE_REQUEST_WORDS = frozenset(
    {
        "authentication",
        "authorization",
        "auth",
        "bearer",
        "cookie",
        "credential",
        "passphrase",
        "passwd",
        "password",
        "secret",
    }
)
_SENSITIVE_TOKEN_PREFIXES = frozenset(
    {"access", "api", "auth", "bearer", "id", "oauth", "refresh", "session"}
)
_SENSITIVE_KEY_PREFIXES = frozenset(
    {"access", "api", "client", "private", "secret", "session", "ssh"}
)
_SENSITIVE_COMPACT_PREFIXES = frozenset(
    {
        "access",
        "api",
        "auth",
        "bearer",
        "client",
        "credential",
        "id",
        "oauth",
        "private",
        "refresh",
        "session",
        "ssh",
    }
)


def _request_identifier_words(value: Any) -> tuple[str, ...]:
    """Split one field path into separator- and camel-case-aware words."""

    words: list[str] = []
    for part in re.split(r"[.\[\]/_\-\s]+", str(value or "")):
        words.extend(
            match.casefold()
            for match in _REQUEST_IDENTIFIER_WORD_PATTERN.findall(part)
        )
    return tuple(words)


def is_sensitive_request_field(value: Any) -> bool:
    """Return whether a generic request field name denotes secret material."""

    words = _request_identifier_words(value)
    if not words:
        return False
    if any(word in _SENSITIVE_REQUEST_WORDS for word in words):
        return True
    for previous, word in zip(words, words[1:]):
        if word == "token" and previous in _SENSITIVE_TOKEN_PREFIXES:
            return True
        if word == "key" and previous in _SENSITIVE_KEY_PREFIXES:
            return True
    compact = re.sub(r"[^A-Za-z0-9]+", "", str(value or "")).casefold()
    if len(words) == 1:
        token_compounds = {
            f"{prefix}token" for prefix in _SENSITIVE_TOKEN_PREFIXES
        }
        key_compounds = {f"{prefix}key" for prefix in _SENSITIVE_KEY_PREFIXES}
        secret_compounds = {
            f"{prefix}secret" for prefix in _SENSITIVE_COMPACT_PREFIXES
        }
        if any(
            compound in compact
            for compound in token_compounds | key_compounds | secret_compounds
        ):
            return True
    if words == ("token",):
        return True
    if len(words) >= 2 and words[-1] == "token":
        return words[-2] in _SENSITIVE_TOKEN_PREFIXES
    if len(words) >= 2 and words[-1] == "key":
        return words[-2] in _SENSITIVE_KEY_PREFIXES
    return False


def redact_request_secrets(value: Any) -> Any:
    """Recursively clone request data while masking generic secret fields."""

    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        secret_field = any(
            is_sensitive_request_field(value.get(field_name))
            for field_name in ("key", "name", "target")
        )
        for key, item in value.items():
            if is_sensitive_request_field(key) or (
                secret_field and str(key).casefold() == "value"
            ):
                redacted[key] = "***"
            else:
                redacted[key] = redact_request_secrets(item)
        return redacted
    if isinstance(value, list):
        return [redact_request_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_request_secrets(item) for item in value)
    return value
