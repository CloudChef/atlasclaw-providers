"""Service catalog and VM request-field discovery operations."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

import yaml

from smartcmp_provider.domain.catalogs import available_catalog_operations
from smartcmp_provider.domain.object_operations import serialize_available_operations
from smartcmp_provider.errors import SmartCmpUpstreamError, SmartCmpValidationError
from smartcmp_provider.models.catalogs import (
    BusinessGroupQuery,
    CatalogDetailQuery,
    CatalogDetailResult,
    CatalogItemsResult,
    CatalogListQuery,
    CatalogListResult,
    FacetQuery,
    FlavorQuery,
    ImageQuery,
    LogicalTemplateQuery,
    PhysicalTemplateQuery,
    ResourceBundleQuery,
)
from smartcmp_provider.transport.client import SmartCmpClient

_PREAPPROVAL_HEADINGS = (
    "# Pre Approval Instructions",
    "# Preapproval Instructions",
    "# Pre-Approval Instructions",
)
_NODE_TEMPLATE_PATTERN = re.compile(r"^\s{2}([A-Za-z0-9_.-]+):\s*$")
_NODE_TYPE_PATTERN = re.compile(
    r"^\s{4}type:\s*[\"']?([^\"'\s]+)[\"']?\s*$"
)


async def list_catalogs(
    client: SmartCmpClient,
    query: CatalogListQuery,
) -> CatalogListResult:
    """List published catalogs or resolve one exact catalog.

    Args:
        client: Request-scoped SmartCMP client.
        query: Keyword pagination or exact catalog selection.

    Returns:
        Normalized catalogs used by the AtlasClaw and MCP request workflows.

    Raises:
        SmartCmpValidationError: If exact selection is empty or mismatched.
        SmartCmpUpstreamError: If SmartCMP violates the catalog response contract.
    """

    exact_catalog_id = query.catalog_id.strip()
    if exact_catalog_id:
        payload = await client.request_json(
            "GET",
            f"/catalogs/{quote(exact_catalog_id, safe='')}",
        )
        if not isinstance(payload, dict):
            raise SmartCmpUpstreamError(
                "SmartCMP catalog detail must be a JSON object.",
                trace_id=client.request.context.trace_id,
            )
        returned_catalog_id = str(payload.get("id") or "").strip()
        if returned_catalog_id != exact_catalog_id:
            raise SmartCmpValidationError(
                "SmartCMP catalog detail returned a different catalog ID: "
                f"{returned_catalog_id or '<missing>'}.",
                trace_id=client.request.context.trace_id,
            )
        catalogs = (
            normalize_catalog(payload, index=1, exact_catalog=True),
        )
        return CatalogListResult(catalogs=catalogs, total=1)

    params: dict[str, Any] = {
        "query": "",
        "states": "PUBLISHED",
        "page": query.page,
        "size": query.size,
        "sort": "catalogIndex,asc",
    }
    if query.keyword:
        params["queryValue"] = query.keyword
    payload = await client.request_json(
        "GET",
        "/catalogs/published/simples",
        params=params,
    )
    if not isinstance(payload, dict) or not isinstance(
        payload.get("content"),
        list,
    ):
        raise SmartCmpUpstreamError(
            "SmartCMP catalog list returned an unexpected JSON shape.",
            trace_id=client.request.context.trace_id,
        )
    rows = payload["content"]
    if any(not isinstance(item, dict) for item in rows):
        raise SmartCmpUpstreamError(
            "SmartCMP catalog list returned a non-object item.",
            trace_id=client.request.context.trace_id,
        )
    total = _coerce_total(payload.get("totalElements"), len(rows))
    catalogs = tuple(
        normalize_catalog(item, index=index, exact_catalog=False)
        for index, item in enumerate(rows, start=1)
    )
    return CatalogListResult(catalogs=catalogs, total=total)


async def get_catalog_detail(
    client: SmartCmpClient,
    query: CatalogDetailQuery,
) -> CatalogDetailResult:
    """Fetch one catalog and extract request/pre-approval detail metadata.

    Args:
        client: Request-scoped SmartCMP client.
        query: Stable SmartCMP catalog ID.

    Returns:
        Raw catalog data and normalized user-facing detail facts.

    Raises:
        SmartCmpValidationError: If catalog ID is empty.
        SmartCmpUpstreamError: If SmartCMP does not return an object.
    """

    catalog_id = query.catalog_id.strip()
    if not catalog_id:
        raise SmartCmpValidationError(
            "Catalog ID is required.",
            trace_id=client.request.context.trace_id,
        )
    payload = await client.request_json(
        "GET",
        f"/catalogs/{quote(catalog_id, safe='')}",
    )
    if not isinstance(payload, dict):
        raise SmartCmpUpstreamError(
            "SmartCMP catalog detail must be a JSON object.",
            trace_id=client.request.context.trace_id,
        )
    returned_catalog_id = str(payload.get("id") or "").strip()
    if returned_catalog_id != catalog_id:
        raise SmartCmpValidationError(
            "SmartCMP catalog detail returned a different catalog ID: "
            f"{returned_catalog_id or '<missing>'}.",
            trace_id=client.request.context.trace_id,
        )
    return CatalogDetailResult(
        catalog=payload,
        metadata=build_catalog_detail_metadata(payload, catalog_id),
    )


async def list_available_business_groups(
    client: SmartCmpClient,
    query: BusinessGroupQuery,
) -> CatalogItemsResult:
    """List business groups available for one selected catalog."""

    catalog_id = _required(
        query.catalog_id,
        "Catalog ID",
        client,
    )
    payload = await client.request_json(
        "GET",
        f"/catalogs/{quote(catalog_id, safe='')}/available-bgs",
    )
    return CatalogItemsResult(items=tuple(_extract_object_list(payload)))


async def list_facets(
    client: SmartCmpClient,
    query: FacetQuery,
) -> CatalogItemsResult:
    """List and compact resource-pool facets for request field selection."""

    business_group_id = _required(
        query.business_group_id,
        "Business group ID",
        client,
    )
    payload = await client.request_json(
        "GET",
        "/resource-bundles/available-facets",
        params={
            "businessGroupId": business_group_id,
            "cloudEntryId": "",
            "nodeType": query.node_type,
        },
    )
    return CatalogItemsResult(
        items=tuple(compact_facets(_extract_object_list(payload)))
    )


async def list_resource_bundles(
    client: SmartCmpClient,
    query: ResourceBundleQuery,
) -> CatalogItemsResult:
    """List static resource pools available to a VM request."""

    payload = await client.request_json(
        "GET",
        "/resource-bundles",
        params={
            "businessGroupId": _required(
                query.business_group_id,
                "Business group ID",
                client,
            ),
            "cloudEntryTypeId": query.cloud_entry_type_id or "",
            "componentType": _required(
                query.component_type,
                "Component type",
                client,
            ),
            "enabled": "true",
            "nodeType": _required(query.node_type, "Node type", client),
            "readOnly": "false",
            "strategy": "RB_POLICY_STATIC",
        },
    )
    return CatalogItemsResult(items=tuple(_extract_object_list(payload)))


async def list_flavors(
    client: SmartCmpClient,
    query: FlavorQuery,
) -> CatalogItemsResult:
    """List machine flavors for an optional provisioning context."""

    payload = await client.request_json(
        "GET",
        "/flavors/provision",
        params={
            "query": "",
            "page": query.page,
            "size": query.size,
            "queryValue": query.query_value,
            "flavorType": "MACHINE",
            "resourceBundleId": query.resource_bundle_id,
            "catalogId": query.catalog_id,
            "nodeTemplateName": query.node_template_name,
        },
    )
    if not isinstance(payload, dict) or not isinstance(
        payload.get("content"),
        list,
    ):
        raise SmartCmpUpstreamError(
            "Flavor query returned an unexpected JSON shape.",
            trace_id=client.request.context.trace_id,
        )
    rows = payload["content"]
    if any(not isinstance(item, dict) for item in rows):
        raise SmartCmpUpstreamError(
            "Flavor query returned a non-object item.",
            trace_id=client.request.context.trace_id,
        )
    return CatalogItemsResult(items=tuple(rows))


async def list_logical_templates(
    client: SmartCmpClient,
    query: LogicalTemplateQuery,
) -> CatalogItemsResult:
    """List logical templates for an optional VM provisioning context."""

    payload = await client.request_json(
        "GET",
        "/logic-templates/search",
        params={
            "expand": "",
            "queryValue": query.query_value.strip(),
            "resourceBundleId": query.resource_bundle_id,
            "catalogId": query.catalog_id,
            "nodeTemplateName": query.node_template_name,
            "osType": query.os_type.strip(),
        },
    )
    rows = _require_direct_object_list(
        payload,
        "Logical-template query",
        client,
    )
    return CatalogItemsResult(items=tuple(rows))


async def list_physical_templates(
    client: SmartCmpClient,
    query: PhysicalTemplateQuery,
) -> CatalogItemsResult:
    """List physical templates compatible with a selected resource pool."""

    logic_template_id = _required(
        query.logic_template_id,
        "Logical template ID",
        client,
    )
    payload = await client.request_json(
        "GET",
        f"/logic-templates/{quote(logic_template_id, safe='')}/physical-templates",
        params={
            "resourceBundleId": _required(
                query.resource_bundle_id,
                "Resource bundle ID",
                client,
            )
        },
    )
    rows = _require_direct_object_list(
        payload,
        "Physical-template query",
        client,
    )
    results: list[dict[str, Any]] = []
    for physical_template in rows:
        physical_template_id = str(physical_template.get("id") or "").strip()
        if not physical_template_id:
            continue
        results.append(
            {
                "id": physical_template_id,
                "physicalTemplateId": physical_template_id,
                "logicTemplateId": logic_template_id,
                "name": (
                    physical_template.get("alias")
                    or physical_template.get("name")
                    or physical_template_id
                ),
                "default": bool(
                    physical_template.get("default")
                    or physical_template.get("isDefault")
                ),
            }
        )
    return CatalogItemsResult(items=tuple(results))


async def list_images(
    client: SmartCmpClient,
    query: ImageQuery,
) -> CatalogItemsResult:
    """List VM images for a selected resource pool and logical template.

    Raises:
        SmartCmpValidationError: If the cloud-entry type does not come from a
            selected SmartCMP resource pool.
        SmartCmpUpstreamError: If the image endpoint violates its list contract.
    """

    cloud_entry_type = query.cloud_entry_type.strip()
    if not cloud_entry_type.startswith("yacmp:cloudentry:type:"):
        raise SmartCmpValidationError(
            "cloudEntryTypeId must come from the selected resource pool and "
            "start with 'yacmp:cloudentry:type:'.",
            trace_id=client.request.context.trace_id,
        )
    payload = await client.request_json(
        "POST",
        "/cloudprovider?action=queryCloudResource",
        json_body={
            "cloudResourceType": f"{cloud_entry_type}::images",
            "limit": 500,
            "queryProperties": {
                "resourceBundleId": query.resource_bundle_id,
                "logicTemplateId": query.logic_template_id,
                "queryResourceBundle": False,
            },
        },
    )
    rows = _require_direct_object_list(payload, "Image query", client)
    return CatalogItemsResult(
        items=tuple(
            normalize_image(item, index)
            for index, item in enumerate(rows, start=1)
        )
    )


def normalize_catalog(
    catalog: dict[str, Any],
    *,
    index: int,
    exact_catalog: bool,
) -> dict[str, Any]:
    """Normalize one SmartCMP catalog for request field discovery.

    Generated Markdown remains authoritative for request fields. When older CMP
    records omit it, a blueprint node/type is derived only as a compatibility
    fallback for non-generic services.
    """

    entry: dict[str, Any] = {
        "index": index,
        "id": catalog.get("id", ""),
        "name": catalog.get("nameZh") or catalog.get("name", ""),
        "sourceKey": catalog.get("sourceKey", ""),
        "serviceCategory": catalog.get("serviceCategory", ""),
    }
    if catalog.get("type"):
        entry["catalogType"] = catalog["type"]

    is_generic_service = (
        str(entry.get("serviceCategory") or "").upper() == "GENERIC_SERVICE"
    )
    derived_resource_type = (
        {} if is_generic_service else _derive_blueprint_resource_type(catalog)
    )
    raw_instructions = str(catalog.get("instructions") or "").strip()
    if raw_instructions:
        instructions = _parse_markdown_instructions(raw_instructions)
        if isinstance(instructions, dict):
            normalized = _normalize_instructions(instructions)
            _add_request_instruction_section(normalized, raw_instructions)
            if normalized:
                entry["instructions"] = normalized
                for key in (
                    "node",
                    "type",
                    "osType",
                    "cloudEntryTypeIds",
                    "componentType",
                ):
                    if normalized.get(key) is not None:
                        entry[key] = normalized[key]
    for key in ("node", "type"):
        if key not in entry and derived_resource_type.get(key):
            entry[key] = derived_resource_type[key]
    if exact_catalog:
        status = str(catalog.get("status") or catalog.get("state") or "").strip()
        if status:
            entry["status"] = status
    else:
        entry["status"] = "PUBLISHED"
    entry["available_operations"] = serialize_available_operations(
        available_catalog_operations(entry)
    )
    return entry


def build_catalog_detail_metadata(
    catalog: dict[str, Any],
    catalog_id: str,
) -> dict[str, Any]:
    """Build stable detail metadata including pre-approval instructions."""

    raw_instructions = _first_text(catalog.get("instructions"))
    preapproval_instructions, preapproval_heading = _extract_markdown_section_any(
        raw_instructions,
        _PREAPPROVAL_HEADINGS,
    )
    metadata: dict[str, Any] = {
        "id": _first_text(catalog.get("id")) or catalog_id,
        "name": _first_text(
            catalog.get("nameZh"),
            catalog.get("name"),
            catalog.get("displayName"),
        ),
        "sourceKey": _first_text(catalog.get("sourceKey")),
        "serviceCategory": _first_text(catalog.get("serviceCategory")),
        "catalogType": _first_text(catalog.get("type")),
        "status": _first_text(catalog.get("status"), catalog.get("state")),
        "hasInstructions": bool(raw_instructions),
        "hasPreApprovalInstructions": bool(preapproval_instructions),
    }
    if preapproval_instructions:
        metadata["preApprovalInstructions"] = preapproval_instructions
        metadata["preApprovalInstructionHeading"] = preapproval_heading
    metadata["available_operations"] = serialize_available_operations(
        available_catalog_operations(metadata)
    )
    return metadata


def compact_facets(facets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only facet fields required to construct request payloads."""

    compacted: list[dict[str, Any]] = []
    for facet in facets:
        facet_key = facet.get("key") or facet.get("id") or facet.get("code") or ""
        if not facet_key:
            continue
        options: list[dict[str, str]] = []
        for option in _option_items(facet):
            option_key = _option_key(option)
            if not option_key:
                continue
            options.append(
                {
                    "key": option_key,
                    "label": _display_name(option) or option_key,
                }
            )
        compacted.append(
            {
                "key": facet_key,
                "label": _display_name(facet) or facet_key,
                "options": options,
            }
        )
    return compacted


def normalize_image(item: dict[str, Any], index: int) -> dict[str, Any]:
    """Normalize one image to the IDs consumed by request payloads."""

    properties = item.get("properties")
    extra = properties.get("extra") if isinstance(properties, dict) else None
    configured_template_id = (
        extra.get("templateId") if isinstance(extra, dict) else None
    )
    template_id = configured_template_id or item.get("id", "")
    return {
        "index": index,
        "id": template_id,
        "templateId": template_id,
        "name": item.get("nameZh")
        or item.get("name")
        or item.get("displayName", ""),
    }


def _required(value: str, label: str, client: SmartCmpClient) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise SmartCmpValidationError(
            f"{label} is required.",
            trace_id=client.request.context.trace_id,
        )
    return normalized


def _coerce_total(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _extract_object_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("content", "items", "result", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def _require_direct_object_list(
    payload: Any,
    operation_name: str,
    client: SmartCmpClient,
) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise SmartCmpUpstreamError(
            f"{operation_name} returned an unexpected JSON shape.",
            trace_id=client.request.context.trace_id,
        )
    if any(not isinstance(item, dict) for item in payload):
        raise SmartCmpUpstreamError(
            f"{operation_name} returned a non-object item.",
            trace_id=client.request.context.trace_id,
        )
    return payload


def _coerce_optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return None


def _resolve_runtime_default_only(raw_param: dict[str, Any]) -> bool:
    for key in ("runtimeDefaultOnly", "runtime_default_only"):
        resolved = _coerce_optional_bool(raw_param.get(key))
        if resolved is not None:
            return resolved
    metadata = raw_param.get("metadata")
    if isinstance(metadata, dict):
        for key in ("runtimeDefaultOnly", "runtime_default_only"):
            resolved = _coerce_optional_bool(metadata.get(key))
            if resolved is not None:
                return resolved
    return False


def _default_value(raw_param: dict[str, Any]) -> Any:
    if "defaultValue" in raw_param:
        return raw_param.get("defaultValue")
    return raw_param.get("default_value")


def _normalize_param(raw_param: dict[str, Any]) -> dict[str, Any]:
    key = str(raw_param.get("key") or "")
    default_value = _default_value(raw_param)
    runtime_default_only = (
        _resolve_runtime_default_only(raw_param)
        and default_value not in (None, "")
    )
    normalized: dict[str, Any] = {
        "key": key,
        "label": raw_param.get("label") or key,
        "required": bool(raw_param.get("required", False)),
        "defaultValue": None if runtime_default_only else default_value,
    }
    if runtime_default_only:
        normalized["runtimeDefaultOnly"] = True
    for field in ("description", "type", "when", "ask", "location", "node"):
        if raw_param.get(field) is not None:
            normalized[field] = raw_param[field]
    if isinstance(raw_param.get("options"), list):
        normalized["options"] = raw_param["options"]
    return normalized


def _field_param(
    field_key: str,
    raw_field: object,
    *,
    location: str,
    node: str | None = None,
) -> dict[str, Any]:
    field = dict(raw_field) if isinstance(raw_field, dict) else {}
    field["key"] = field_key
    field["location"] = location
    if node:
        field["node"] = node
    return _normalize_param(field)


def _normalize_resource_specs(raw_specs: object) -> list[dict[str, Any]]:
    if not isinstance(raw_specs, list):
        return []
    reserved_keys = {
        "node",
        "type",
        "resourceBundleId",
        "resourceBundleParams",
        "resourceBundleTags",
        "params",
        "fields",
    }
    normalized_specs: list[dict[str, Any]] = []
    for raw_spec in raw_specs:
        if not isinstance(raw_spec, dict):
            continue
        node = str(raw_spec.get("node") or "").strip()
        normalized_spec: dict[str, Any] = {}
        if node:
            normalized_spec["node"] = node
        spec_type = raw_spec.get("type")
        if isinstance(spec_type, str) and spec_type.strip():
            normalized_spec["type"] = spec_type.strip()
        resource_bundle_id = raw_spec.get("resourceBundleId")
        if isinstance(resource_bundle_id, dict):
            normalized_spec["resourceBundleId"] = _field_param(
                "resourceBundleId",
                resource_bundle_id,
                location="resourceSpecs",
                node=node,
            )
        resource_bundle_params = raw_spec.get("resourceBundleParams")
        if isinstance(resource_bundle_params, dict):
            normalized_bundle_params = {
                str(param_key): _field_param(
                    str(param_key),
                    raw_param,
                    location="resourceBundleParams",
                    node=node,
                )
                for param_key, raw_param in resource_bundle_params.items()
            }
            if normalized_bundle_params:
                normalized_spec["resourceBundleParams"] = normalized_bundle_params
        resource_bundle_tags = raw_spec.get("resourceBundleTags")
        if isinstance(resource_bundle_tags, dict):
            normalized_spec["resourceBundleTags"] = _field_param(
                "resourceBundleTags",
                resource_bundle_tags,
                location="resourceBundleTags",
                node=node,
            )
        params = raw_spec.get("params")
        if isinstance(params, dict):
            normalized_params = {
                str(param_key): _field_param(
                    str(param_key),
                    raw_param,
                    location="params",
                    node=node,
                )
                for param_key, raw_param in params.items()
            }
            if normalized_params:
                normalized_spec["params"] = normalized_params
        for field_key, raw_field in raw_spec.items():
            if field_key in reserved_keys or not isinstance(raw_field, dict):
                continue
            normalized_spec[str(field_key)] = _field_param(
                str(field_key),
                raw_field,
                location="resourceSpecFields",
                node=node,
            )
        normalized_specs.append(normalized_spec)
    return normalized_specs


def _normalize_generic_request(raw_generic_request: object) -> dict[str, Any]:
    if not isinstance(raw_generic_request, dict):
        return {}
    normalized: dict[str, Any] = {}
    for field_key, raw_field in raw_generic_request.items():
        field_name = str(field_key)
        if field_name in {"processForm", "process_form"}:
            if not isinstance(raw_field, dict):
                continue
            process_form = {
                str(param_key): _field_param(
                    str(param_key),
                    raw_param,
                    location="genericRequest.processForm",
                )
                for param_key, raw_param in raw_field.items()
            }
            if process_form:
                normalized["processForm"] = process_form
        elif isinstance(raw_field, dict):
            normalized[field_name] = _field_param(
                field_name,
                raw_field,
                location="genericRequest",
            )
    return normalized


def _normalize_instructions(raw_instructions: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key in ("node", "type", "osType", "cloudEntryTypeIds"):
        value = raw_instructions.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            if value.strip():
                normalized[key] = value.strip()
        else:
            normalized[key] = value
    catalog_metadata = raw_instructions.get("catalog")
    if isinstance(catalog_metadata, dict):
        component_type = catalog_metadata.get(
            "component_type"
        ) or catalog_metadata.get("componentType")
        if isinstance(component_type, str) and component_type.strip():
            normalized["componentType"] = component_type.strip()
    root_params = raw_instructions.get("params")
    if isinstance(root_params, dict):
        normalized_root_params = {
            str(param_key): _field_param(
                str(param_key),
                raw_param,
                location="rootParams",
            )
            for param_key, raw_param in root_params.items()
        }
        if normalized_root_params:
            normalized["params"] = normalized_root_params
    generic_request = raw_instructions.get(
        "generic_request"
    ) or raw_instructions.get("genericRequest")
    normalized_generic_request = _normalize_generic_request(generic_request)
    if normalized_generic_request:
        normalized["genericRequest"] = normalized_generic_request
    resource_specs = _normalize_resource_specs(
        raw_instructions.get("resource_specs")
        or raw_instructions.get("resourceSpecs")
    )
    if resource_specs:
        normalized["resourceSpecs"] = resource_specs
        if "node" not in normalized and resource_specs[0].get("node"):
            normalized["node"] = resource_specs[0]["node"]
        if "type" not in normalized and resource_specs[0].get("type"):
            normalized["type"] = resource_specs[0]["type"]
    top_level_required = raw_instructions.get(
        "top_level_required"
    ) or raw_instructions.get("topLevelRequired")
    if isinstance(top_level_required, list):
        normalized["topLevelRequired"] = [
            value
            for value in top_level_required
            if isinstance(value, str) and value.strip()
        ]
    top_level_fields = raw_instructions.get(
        "top_level_fields"
    ) or raw_instructions.get("topLevelFields")
    if isinstance(top_level_fields, dict):
        normalized_top_level_fields = {
            str(field_key): _field_param(
                str(field_key),
                raw_field,
                location="topLevel",
            )
            for field_key, raw_field in top_level_fields.items()
        }
        if normalized_top_level_fields:
            normalized["topLevelFields"] = normalized_top_level_fields
    return normalized


def _add_request_instruction_section(
    normalized: dict[str, Any],
    raw_instructions_text: str,
) -> None:
    request_section = _extract_markdown_section(
        raw_instructions_text,
        "# Request Instructions",
    )
    if request_section:
        normalized["requestInstructions"] = request_section


def _extract_markdown_section(markdown_text: str, heading: str) -> str:
    lines = markdown_text.splitlines()
    start_index = next(
        (
            index + 1
            for index, line in enumerate(lines)
            if line.strip().lstrip("\ufeff") == heading
        ),
        -1,
    )
    if start_index == -1:
        return ""
    section_lines: list[str] = []
    for line in lines[start_index:]:
        if line.startswith("# "):
            break
        section_lines.append(line)
    return "\n".join(section_lines).strip()


def _extract_markdown_section_any(
    markdown_text: str,
    headings: tuple[str, ...],
) -> tuple[str, str]:
    lines = markdown_text.splitlines()
    normalized_headings = {
        heading.strip(): heading.strip() for heading in headings
    }
    start_index = -1
    matched_heading = ""
    for index, line in enumerate(lines):
        stripped = line.strip().lstrip("\ufeff")
        if stripped in normalized_headings:
            start_index = index + 1
            matched_heading = normalized_headings[stripped]
            break
    if start_index == -1:
        return "", ""
    section_lines: list[str] = []
    for line in lines[start_index:]:
        if line.startswith("# "):
            break
        section_lines.append(line)
    return "\n".join(section_lines).strip(), matched_heading


def _strip_markdown_code_fence(section_text: str) -> str:
    lines = section_text.strip().splitlines()
    if not lines:
        return ""
    if lines[0].strip().startswith("```"):
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_markdown_instructions(raw_instructions: str) -> dict[str, Any] | None:
    parameter_section = _extract_markdown_section(
        raw_instructions,
        "# Request Parameter Instructions",
    )
    yaml_text = _strip_markdown_code_fence(parameter_section)
    if not yaml_text:
        return None
    try:
        parsed = yaml.safe_load(yaml_text)
    except (TypeError, ValueError, yaml.YAMLError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _iter_blueprint_yaml(raw_catalog: dict[str, Any]) -> tuple[str, ...]:
    blueprint = raw_catalog.get("blueprint")
    if not isinstance(blueprint, dict):
        return ()
    return tuple(
        value
        for key in (
            "mainYaml",
            "toscaYaml",
            "originalToscaYaml",
            "plannedMainYaml",
            "bpYaml",
        )
        if isinstance((value := blueprint.get(key)), str) and value.strip()
    )


def _extract_node_types_from_yaml(yaml_text: str) -> list[tuple[str, str]]:
    nodes: list[tuple[str, str]] = []
    current_node = ""
    in_node_templates = False
    for line in yaml_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "node_templates:":
            in_node_templates = True
            current_node = ""
            continue
        if not in_node_templates:
            continue
        if line and not line.startswith(" "):
            in_node_templates = False
            current_node = ""
            continue
        node_match = _NODE_TEMPLATE_PATTERN.match(line)
        if node_match:
            current_node = node_match.group(1)
            continue
        type_match = _NODE_TYPE_PATTERN.match(line)
        if current_node and type_match:
            node_type = type_match.group(1).strip()
            if node_type.startswith("cloudchef.nodes."):
                nodes.append((current_node, node_type))
    return nodes


def _derive_blueprint_resource_type(
    raw_catalog: dict[str, Any],
) -> dict[str, str]:
    for yaml_text in _iter_blueprint_yaml(raw_catalog):
        nodes = _extract_node_types_from_yaml(yaml_text)
        if not nodes:
            continue
        for node_name, node_type in nodes:
            if node_type == "cloudchef.nodes.Compute":
                return {"node": node_name, "type": node_type}
        node_name, node_type = nodes[0]
        return {"node": node_name, "type": node_type}
    return {}


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, dict) and "value" in value:
            value = value.get("value")
        if isinstance(value, (str, int, float)):
            text = str(value).strip()
            if text:
                return text
    return ""


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("zh", "zh_CN", "nameZh", "label", "en", "name"):
            text = value.get(key)
            if isinstance(text, str) and text:
                return text
        for text in value.values():
            if isinstance(text, str) and text:
                return text
    return ""


def _display_name(item: Any) -> str:
    if not isinstance(item, dict):
        return _text(item)
    for key in (
        "nameZh",
        "labelZh",
        "displayName",
        "label",
        "name",
        "title",
        "i18nTitle",
    ):
        text = _text(item.get(key))
        if text:
            return text
    return ""


def _option_key(option: Any) -> str:
    if not isinstance(option, dict):
        return str(option) if option is not None else ""
    for key in ("key", "id", "value", "code"):
        value = option.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _option_items(facet: dict[str, Any]) -> list[Any]:
    for key in ("options", "values", "items", "children", "source", "selectDatas"):
        value = facet.get(key)
        if isinstance(value, list):
            return value
    return []
