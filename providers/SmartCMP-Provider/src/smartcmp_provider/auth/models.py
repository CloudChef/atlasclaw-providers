"""Keep authentication input and resolved secrets outside execution context.

Both AtlasClaw and MCP use these Provider-owned contracts. An adapter may supply
a cookie, webhook token, configured reference, or future OAuth context, but only
Provider resolution converts it into SmartCMP request headers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from smartcmp_provider.context import ExecutionContext

CredentialKind = Literal["bearer", "session", "cookie"]
SmartCmpAuthType = Literal[
    "user_token",
    "provider_token",
    "cookie",
    "credential",
    "oauth_token",
]
AuthenticationSource = Literal[
    "configured_reference",
    "provided_credential",
    "oauth_context",
]


@dataclass(frozen=True, slots=True)
class SmartCmpAuthenticationContext:
    """Describe caller authentication before Provider credential resolution.

    This is the shared authentication boundary for AtlasClaw, MCP, and future
    Agent adapters. A configured deployment passes only a credential reference.
    The AtlasClaw adapter may pass its selected per-request credential, and a
    future MCP OAuth adapter may pass the received OAuth context. SmartCMP Provider
    remains the only component that converts any source into the credential
    consumed by the SmartCMP API client.

    Attributes:
        subject: Stable calling principal identifier.
        actor_type: Whether the principal is a user or service robot.
        source: Configured credential reference or future OAuth context.
        auth_type: SmartCMP credential semantics requested by configuration.
        credential_reference: Provider-resolved configured secret reference.
        credential_value: Per-request credential or OAuth token, excluded from repr.
        expires_at: Optional OAuth token expiry asserted by the source adapter.
        tenant_id: Optional tenant boundary asserted by the source adapter.
        client_id: Optional calling client or service identifier.
        scopes: Immutable granted scope set carried across the integration.
    """

    subject: str
    actor_type: Literal["user", "robot"]
    source: AuthenticationSource
    auth_type: SmartCmpAuthType
    credential_reference: str | None = None
    credential_value: str | None = field(default=None, repr=False)
    expires_at: datetime | None = None
    tenant_id: str | None = None
    client_id: str | None = None
    scopes: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        """Validate that exactly the selected authentication source is present."""

        if self.source == "configured_reference":
            if not str(self.credential_reference or "").strip():
                raise ValueError(
                    "Configured SmartCMP authentication requires a credential "
                    "reference."
                )
            if self.credential_value is not None:
                raise ValueError(
                    "Configured SmartCMP authentication cannot carry a credential."
                )
        elif not str(self.credential_value or "").strip():
            raise ValueError(
                "SmartCMP authentication context requires a credential value."
            )

    @classmethod
    def configured(
        cls,
        *,
        subject: str,
        actor_type: Literal["user", "robot"],
        auth_type: SmartCmpAuthType,
        credential_reference: str,
        tenant_id: str | None = None,
        client_id: str | None = None,
        scopes: frozenset[str] = frozenset(),
    ) -> SmartCmpAuthenticationContext:
        """Create a configured reference for Provider resolution on each call."""

        return cls(
            subject=subject,
            actor_type=actor_type,
            source="configured_reference",
            auth_type=auth_type,
            credential_reference=credential_reference,
            tenant_id=tenant_id,
            client_id=client_id,
            scopes=scopes,
        )

    @classmethod
    def provided(
        cls,
        *,
        subject: str,
        actor_type: Literal["user", "robot"],
        auth_type: SmartCmpAuthType,
        credential_value: str,
        tenant_id: str | None = None,
        client_id: str | None = None,
        scopes: frozenset[str] = frozenset(),
    ) -> SmartCmpAuthenticationContext:
        """Carry an adapter-selected cookie or token into Provider resolution."""

        return cls(
            subject=subject,
            actor_type=actor_type,
            source="provided_credential",
            auth_type=auth_type,
            credential_value=credential_value,
            tenant_id=tenant_id,
            client_id=client_id,
            scopes=scopes,
        )

    @classmethod
    def oauth(
        cls,
        *,
        subject: str,
        actor_type: Literal["user", "robot"],
        access_token: str,
        expires_at: datetime | None = None,
        tenant_id: str | None = None,
        client_id: str | None = None,
        scopes: frozenset[str] = frozenset(),
    ) -> SmartCmpAuthenticationContext:
        """Carry future client OAuth state into the existing Provider auth path."""

        return cls(
            subject=subject,
            actor_type=actor_type,
            source="oauth_context",
            auth_type="oauth_token",
            credential_value=access_token,
            expires_at=expires_at,
            tenant_id=tenant_id,
            client_id=client_id,
            scopes=scopes,
        )


@dataclass(frozen=True, slots=True)
class SmartCmpCredential:
    """Carry one request-scoped SmartCMP secret without exposing it in repr.

    Attributes:
        kind: Header scheme required by the resolved SmartCMP credential.
        value: Secret token value. The dataclass representation always omits it.
    """

    kind: CredentialKind
    value: str = field(repr=False)

    def headers(
        self,
        content_type: str = "application/json; charset=utf-8",
    ) -> dict[str, str]:
        """Build fresh HTTP headers for exactly this credential.

        Args:
            content_type: Optional Content-Type value added to the request.

        Returns:
            A new header dictionary that callers may mutate without affecting
            another request or principal.
        """

        if self.kind == "bearer":
            headers = {"Authorization": f"Bearer {self.value}"}
        elif self.kind == "cookie":
            headers = self._cookie_headers()
        else:
            headers = {"CloudChef-Authenticate": self.value}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _cookie_headers(self) -> dict[str, str]:
        """Translate a request cookie or raw session token into CMP headers."""

        cookie_value = str(self.value or "").strip()
        if not cookie_value:
            return {}
        token = ""
        for part in cookie_value.split(";"):
            key, separator, value = part.strip().partition("=")
            if (
                separator
                and key.strip().casefold() == "cloudchef-authenticate"
                and value.strip()
            ):
                token = value.strip()
                break
        if token:
            return {
                "CloudChef-Authenticate": token,
                "Cookie": cookie_value,
            }
        if "=" in cookie_value or ";" in cookie_value:
            return {"Cookie": cookie_value}
        return {"CloudChef-Authenticate": cookie_value}


@dataclass(frozen=True, slots=True)
class ResolvedSmartCmpRequest:
    """Bind one immutable execution context to one request-scoped credential.

    The secret remains outside ``ExecutionContext`` so context values can be
    inspected or serialized without accidentally including authentication data.

    Attributes:
        context: Principal, instance, trace, and deadline for this invocation.
        credential: Credential selected by the owning adapter for this invocation.
    """

    context: ExecutionContext
    credential: SmartCmpCredential
