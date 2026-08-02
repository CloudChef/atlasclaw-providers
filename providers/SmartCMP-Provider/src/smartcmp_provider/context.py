"""Request-scoped caller and execution context contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from smartcmp_provider.instance import SmartCmpInstance

ActorType = Literal["user", "robot"]


@dataclass(frozen=True, slots=True)
class Principal:
    """Identify the caller without carrying a SmartCMP secret.

    Attributes:
        subject: Stable caller identifier from the owning adapter.
        actor_type: Whether the caller represents an end user or a robot.
        tenant_id: Optional tenant boundary asserted by the adapter.
        client_id: Optional client or integration identifier.
        scopes: Immutable set of capabilities granted to the caller.
    """

    subject: str
    actor_type: ActorType
    tenant_id: str | None = None
    client_id: str | None = None
    scopes: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """Bind one caller and one SmartCMP instance to a single operation.

    The context is created per invocation and deliberately excludes credentials,
    preventing it from becoming a serializable container for secrets.

    Attributes:
        principal: Caller identity resolved by the adapter.
        instance: Explicit SmartCMP instance selected for this operation.
        trace_id: Correlation identifier for adapter and upstream diagnostics.
        deadline: Optional absolute operation deadline.
        idempotency_key: Optional caller-provided mutation identity.
    """

    principal: Principal
    instance: SmartCmpInstance
    trace_id: str
    deadline: datetime | None = None
    idempotency_key: str | None = None
