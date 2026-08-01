"""Shared projections and reads for SmartCMP designer objects."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from smartcmp_provider.errors import SmartCmpValidationError
from smartcmp_provider.models.objects import (
    ComponentDefinitionView,
    ComponentFileView,
    ObjectIdQuery,
    ObjectReadQuery,
    OptimizationPolicyView,
    ScriptDefinitionView,
)
from smartcmp_provider.operations.objects import get_object_by_id
from smartcmp_provider.transport.client import SmartCmpClient

_POLICY_EDITABLE_FIELDS = (
    "name",
    "nameZh",
    "description",
    "descriptionZh",
    "remedie",
    "remedieZh",
    "category",
    "type",
    "resourceType",
    "severity",
    "ruleContent",
    "policyConfigs",
)
_SCRIPT_EDITABLE_FIELDS = (
    "name",
    "alias",
    "aliasZh",
    "description",
    "descriptionZh",
    "type",
    "params",
    "properties",
    "formContent",
    "resourceTypes",
    "osType",
)


async def read_component_definition(
    client: SmartCmpClient,
    query: ObjectIdQuery,
) -> ComponentDefinitionView:
    """Read and validate one component definition through SmartCMP Provider."""

    result = await get_object_by_id(
        client,
        ObjectReadQuery(
            object_type="component_definition",
            object_id=query.object_id,
        ),
    )
    return project_component_definition(result.payload)


async def read_optimization_policy(
    client: SmartCmpClient,
    query: ObjectIdQuery,
) -> OptimizationPolicyView:
    """Read and validate one cost-optimization policy through SmartCMP Provider."""

    result = await get_object_by_id(
        client,
        ObjectReadQuery(
            object_type="optimization_policy",
            object_id=query.object_id,
        ),
    )
    return project_optimization_policy(result.payload)


async def read_script_definition(
    client: SmartCmpClient,
    query: ObjectIdQuery,
) -> ScriptDefinitionView:
    """Read and validate one script definition through SmartCMP Provider."""

    result = await get_object_by_id(
        client,
        ObjectReadQuery(
            object_type="script_definition",
            object_id=query.object_id,
        ),
    )
    return project_script_definition(result.payload)


def project_component_definition(
    payload: dict[str, Any],
) -> ComponentDefinitionView:
    """Project raw component payload into a reusable validated definition."""

    object_id = _object_id(payload)
    resource_type = str(payload.get("resourceType") or "").strip()
    family = component_family_for_resource_type(resource_type)
    if not family:
        raise SmartCmpValidationError(
            "SmartCMP component resourceType is not supported by the component "
            "script designer."
        )
    model = payload.get("model")
    model = model if isinstance(model, dict) else {}
    raw_files = model.get("blueprintFiles")
    raw_files = raw_files if isinstance(raw_files, list) else []
    files: list[ComponentFileView] = []
    for item in raw_files:
        if not isinstance(item, dict) or not isinstance(item.get("content"), str):
            continue
        path = safe_component_script_path(item.get("path"))
        if not path:
            continue
        content = str(item["content"])
        files.append(
            ComponentFileView(
                path=path,
                type=str(item.get("type") or ""),
                mode=str(item.get("mode") or ""),
                size=len(content.encode("utf-8")),
                content=content,
            )
        )
    return ComponentDefinitionView(
        object_id=object_id,
        name=str(payload.get("name") or ""),
        resource_type=resource_type,
        parent_type=str(payload.get("parentType") or ""),
        component_family=family,
        files=tuple(files),
    )


def project_optimization_policy(
    payload: dict[str, Any],
) -> OptimizationPolicyView:
    """Project raw policy payload after enforcing cost-policy invariants."""

    object_id = _object_id(payload)
    category = str(payload.get("category") or "").strip().upper()
    if category != "COST-OPTIMIZATION" and not category.startswith(
        "COST-OPTIMIZATION."
    ):
        raise SmartCmpValidationError(
            "Current policy is not a SmartCMP cost-optimization policy."
        )
    if not isinstance(payload.get("ruleContent"), str):
        raise SmartCmpValidationError(
            "SmartCMP current policy ruleContent must be a string."
        )
    definition = {
        key: payload.get(key)
        for key in _POLICY_EDITABLE_FIELDS
        if key in payload
    }
    return OptimizationPolicyView(
        object_id=object_id,
        name=str(payload.get("name") or ""),
        definition=definition,
    )


def project_script_definition(
    payload: dict[str, Any],
) -> ScriptDefinitionView:
    """Project raw script payload into complete metadata and source content."""

    object_id = _object_id(payload)
    content = payload.get("content")
    if not isinstance(content, str):
        raise SmartCmpValidationError(
            "SmartCMP current script content must be a string."
        )
    metadata = {
        key: payload.get(key)
        for key in _SCRIPT_EDITABLE_FIELDS
        if key in payload
    }
    return ScriptDefinitionView(
        object_id=object_id,
        name=str(payload.get("alias") or payload.get("name") or ""),
        metadata=metadata,
        content=content,
        language=script_language(payload),
    )


def component_family_for_resource_type(resource_type: str) -> str:
    """Map one authoritative SmartCMP resource type to its designer family."""

    normalized = str(resource_type or "").strip().lower()
    exporter_type = "resource.agent.monitoring_agent.prometheus_exporter"
    if normalized == exporter_type or normalized.startswith(f"{exporter_type}."):
        return "exporter"
    if normalized.startswith("resource.integration."):
        return "integration"
    if normalized.startswith("resource.software."):
        return "software"
    if normalized.startswith(
        ("resource.iaas.", "resource.paas.", "resource.caas.")
    ):
        return "resource"
    return ""


def safe_component_script_path(value: Any) -> str:
    """Return a safe relative path under ``scripts/``, or an empty string."""

    path = str(value or "").strip()
    if not path.startswith("scripts/") or "\\" in path:
        return ""
    parts = PurePosixPath(path).parts
    if not parts or parts[0] != "scripts" or any(
        part in {"", ".", ".."} for part in parts
    ):
        return ""
    return path


def script_language(payload: dict[str, Any]) -> str:
    """Infer a Markdown language identifier from script type or name."""

    script_type = str(payload.get("type") or "").strip().lower()
    name = str(payload.get("name") or "").strip().lower()
    if script_type == "python" or name.endswith(".py"):
        return "python"
    if script_type in {"shell", "bash"} or name.endswith((".sh", ".bash")):
        return "bash"
    if script_type in {"javascript", "nodejs"} or name.endswith((".js", ".mjs")):
        return "javascript"
    if script_type in {"powershell", "power_shell"} or name.endswith(".ps1"):
        return "powershell"
    return "text"


def _object_id(payload: dict[str, Any]) -> str:
    object_id = str(payload.get("id") or "").strip()
    if not object_id:
        raise SmartCmpValidationError(
            "SmartCMP designer object response is missing its ID."
        )
    return object_id
