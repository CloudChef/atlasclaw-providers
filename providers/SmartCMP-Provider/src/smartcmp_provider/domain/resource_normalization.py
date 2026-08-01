"""Normalize raw SmartCMP resource evidence without performing API calls."""

from __future__ import annotations

from typing import Any


def determine_component_type(record: dict[str, Any]) -> str:
    """Return the best analyzer-compatible component type for one record."""

    summary = record.get("summary") or {}
    resource = _resource_data(record)
    return str(
        resource.get("componentType")
        or summary.get("componentType")
        or resource.get("resourceType")
        or summary.get("resourceType")
        or ""
    )


def build_flat_resource_properties(
    record: dict[str, Any],
) -> dict[str, Any]:
    """Flatten analyzer-relevant scalar evidence in precedence order."""

    summary = record.get("summary") or {}
    resource = _resource_data(record)
    details = record.get("details") or {}
    properties: dict[str, Any] = {}

    _merge_first_wins(properties, _simple_fields(resource))
    _merge_first_wins(properties, _simple_fields(summary))
    for nested_key in (
        "resource",
        "node",
        "basic",
        "basicInfo",
        "resourceView",
        "view",
        "metadata",
        "statusInfo",
    ):
        _merge_first_wins(
            properties,
            _simple_fields(resource.get(nested_key) or {}),
        )
    _merge_first_wins(
        properties,
        _simple_fields(resource.get("properties") or {}),
    )
    _merge_first_wins(
        properties,
        _simple_fields(resource.get("resourceInfo") or {}),
    )
    _merge_first_wins(properties, _extract_runtime_properties(resource))
    _merge_first_wins(
        properties,
        _simple_fields(resource.get("customProperties") or {}),
    )
    _merge_first_wins(properties, _simple_fields(details))
    _merge_first_wins(
        properties,
        _simple_fields(resource.get("extra") or {}),
    )
    return properties


def build_normalized_resource(record: dict[str, Any]) -> dict[str, Any]:
    """Build the stable analyzer-compatible resource projection."""

    return {
        "type": determine_component_type(record),
        "properties": build_flat_resource_properties(record),
    }


def _merge_first_wins(
    target: dict[str, Any],
    source: dict[str, Any],
) -> None:
    for key, value in source.items():
        if not key or key in target or value in (None, ""):
            continue
        target[key] = value


def _simple_fields(mapping: Any) -> dict[str, Any]:
    if not isinstance(mapping, dict):
        return {}
    return {
        key: value
        for key, value in mapping.items()
        if not isinstance(value, (dict, list))
    }


def _extract_runtime_properties(
    resource: dict[str, Any],
) -> dict[str, Any]:
    runtime: dict[str, Any] = {}
    direct_runtime = resource.get("RuntimeProperties")
    if isinstance(direct_runtime, dict):
        _merge_first_wins(runtime, _simple_fields(direct_runtime))

    extensible = resource.get("extensibleProperties")
    if isinstance(extensible, dict):
        runtime_from_ext = extensible.get("RuntimeProperties")
        if isinstance(runtime_from_ext, dict):
            _merge_first_wins(runtime, _simple_fields(runtime_from_ext))

    exts = resource.get("exts")
    if isinstance(exts, dict):
        custom = exts.get("customProperty")
        if isinstance(custom, dict):
            _merge_first_wins(runtime, _simple_fields(custom))
    return runtime


def _resource_data(record: dict[str, Any]) -> dict[str, Any]:
    data = record.get("data")
    if isinstance(data, dict):
        return data
    resource = record.get("resource")
    return resource if isinstance(resource, dict) else {}
