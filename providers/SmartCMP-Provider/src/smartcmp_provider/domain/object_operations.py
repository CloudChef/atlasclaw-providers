"""Build adapter-neutral object operations from Provider capabilities.

The returned operation tells an agent which capability applies to a concrete
SmartCMP object and supplies stable arguments. MCP publishes its ``tool_name``
directly, while the AtlasClaw adapter projects the same operation into its own
``object_actions`` protocol shape.
"""

from __future__ import annotations

from typing import Any

from smartcmp_provider.capabilities import capability_by_id
from smartcmp_provider.models.object_operations import AvailableOperation


def available_operation(
    operation_id: str,
    capability_id: str,
    *,
    arguments: dict[str, Any],
    required_inputs: tuple[str, ...] = (),
) -> AvailableOperation:
    """Bind an object operation to canonical Tool and safety metadata.

    Args:
        operation_id: Object-local operation identifier returned by SmartCMP.
        capability_id: Stable Provider capability identifier.
        arguments: Values already resolved from the object response.
        required_inputs: Values the agent must collect before invocation.

    Returns:
        An adapter-neutral operation usable by MCP and AtlasClaw projections.

    Raises:
        ValueError: If the capability has no MCP-visible Tool mapping.
    """

    capability = capability_by_id(capability_id)
    if capability.mcp_tool_name is None:
        raise ValueError(f"Capability is not available to MCP: {capability_id}")
    return AvailableOperation(
        operation_id=operation_id,
        capability_id=capability.capability_id,
        tool_name=capability.mcp_tool_name,
        effect=capability.effect,
        confirmation=capability.confirmation,
        destructive=capability.destructive,
        arguments=dict(arguments),
        required_inputs=required_inputs,
    )


def serialize_available_operations(
    operations: tuple[AvailableOperation, ...],
) -> list[dict[str, Any]]:
    """Serialize operations into the raw object payload returned to adapters."""

    return [operation.model_dump(mode="json") for operation in operations]
