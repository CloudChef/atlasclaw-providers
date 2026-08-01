"""AtlasClaw Tool adapter for standalone SmartCMP resource-pool browsing."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


_SHARED_SCRIPTS = Path(__file__).resolve().parents[2] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from _atlasclaw_adapter import (  # noqa: E402
    RunContext,
    execute,
    tool_error,
    tool_result,
)
from smartcmp_provider.models.directory import DirectorySearchQuery  # noqa: E402
from smartcmp_provider.operations.directory import (  # noqa: E402
    list_resource_pool_directory,
)


async def list_resource_pools(
    ctx: RunContext[Any],
    query_value: str | None = None,
) -> dict[str, Any]:
    """List standalone resource pools visible to the current principal."""

    try:
        result = await execute(
            ctx,
            list_resource_pool_directory,
            DirectorySearchQuery(query_value=query_value or ""),
        )
        return tool_result(
            result,
            summary=f"Found {result.total or len(result.items)} resource pools.",
        )
    except (ValueError, RuntimeError) as error:
        return tool_error(error)
