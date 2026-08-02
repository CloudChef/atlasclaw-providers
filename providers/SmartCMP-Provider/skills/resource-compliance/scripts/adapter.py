"""AtlasClaw Tool adapter for SmartCMP resource compliance evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


_SHARED_SCRIPTS = Path(__file__).resolve().parents[2] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from _atlasclaw_adapter import (  # noqa: E402
    RunContext,
    execute,
    split_values,
    tool_error,
    tool_result,
)
from smartcmp_provider.domain.resource_resolution import (  # noqa: E402
    parse_resource_directory,
    resolve_single_resource,
)
from smartcmp_provider.models.resources import (  # noqa: E402
    ResourceComplianceQuery,
    ResourceDetailQuery,
)
from smartcmp_provider.services.compliance import (  # noqa: E402
    analyze_resource_compliance,
)
from smartcmp_provider.services.resources import (  # noqa: E402
    get_resource_detail_view,
)


async def analyze_resource(
    ctx: RunContext[Any],
    resource_name: str = "",
    resource_index: int | None = None,
    resource_directory_json: str = "",
    trigger_source: str = "user",
    payload_json: str = "",
    resource_ids: str | list[str] = "",
) -> dict[str, Any]:
    """Collect bounded SmartCMP facts for generic LLM compliance analysis."""

    del trigger_source
    try:
        ids = list(split_values(resource_ids))
        if payload_json:
            payload = json.loads(payload_json)
            if not isinstance(payload, dict):
                raise ValueError("payload_json must contain one JSON object.")
            ids.extend(
                split_values(
                    payload.get("resourceIds")
                    or payload.get("resource_ids")
                    or ""
                )
            )
            resource_name = str(
                payload.get("resourceName")
                or payload.get("resource_name")
                or resource_name
            ).strip()
            raw_index = (
                payload.get("resourceIndex")
                if payload.get("resourceIndex") is not None
                else payload.get("resource_index")
            )
            if raw_index not in (None, ""):
                resource_index = int(raw_index)
            resource_directory_json = str(
                payload.get("resourceDirectoryJson")
                or payload.get("resource_directory_json")
                or resource_directory_json
            )
        if not ids:
            resource_id, _resolved_name = await _resolve_resource(
                ctx,
                resource_name=resource_name,
                resource_index=resource_index,
                resource_directory_json=resource_directory_json,
            )
            ids.append(resource_id)
        result = await execute(
            ctx,
            analyze_resource_compliance,
            ResourceComplianceQuery(resource_ids=tuple(dict.fromkeys(ids))),
        )
        return tool_result(
            result,
            summary=(
                f"Collected compliance evidence for "
                f"{result.analyzed_count} resources; "
                f"{result.failed_count} reads failed."
            ),
        )
    except (json.JSONDecodeError, ValueError, RuntimeError) as error:
        return tool_error(error)


async def _resolve_resource(
    ctx: Any,
    *,
    resource_name: str,
    resource_index: int | None,
    resource_directory_json: str,
) -> tuple[str, str]:
    """Resolve an interactive resource name or recent visible index."""

    directory = parse_resource_directory(resource_directory_json)
    if resource_index is not None or directory:
        return resolve_single_resource(
            resource_id_value="",
            resource_name=resource_name,
            resource_index=resource_index,
            directory_items=directory,
        )
    detail = await execute(
        ctx,
        get_resource_detail_view,
        ResourceDetailQuery(resource_name=resource_name),
    )
    return detail.resource_id, detail.name or resource_name
