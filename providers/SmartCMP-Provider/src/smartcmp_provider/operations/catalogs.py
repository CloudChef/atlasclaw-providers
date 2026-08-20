"""Service catalog and VM request-field discovery operations."""

from __future__ import annotations

from copy import deepcopy
import json
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
_GENERIC_CLOUD_ENTRY_TYPE = "yacmp:cloudentry:type:generic-cloud"
_SUPPORTED_LOOKUP_ACTIONS = frozenset({"queryCloudResource", "updateCloudResource"})
_LOOKUP_FIELD_REFERENCE = re.compile(r"\{\$\.([A-Za-z0-9_.-]+)}")
_LOOKUP_BUNDLE_REFERENCE = re.compile(
    r"\$\{resource_bundle_config\.([A-Za-z0-9_.-]+)}"
)
_LOOKUP_CONTEXT_REFERENCE = re.compile(r"\$\{([A-Za-z0-9_.-]+)}")
_RESOURCE_BUNDLE_SYSTEM_FIELDS = frozenset(
    {
        "policy_type",
        "policy_resource",
        "facet",
        "facet_copy",
        "related_node",
        "copy_node",
        "alter_resource_bundle_id",
        "alter_resource_bundle_id_copy",
        "cloudEntryTypeId",
        "isClassicNetwork",
        "resource_bundle_config",
        "un_visibility_property",
        "un_modification_property",
    }
)
_COMPUTE_NODE_TYPES = frozenset(
    {"cloudchef.nodes.Compute", "cloudchef.nodes.WindowsCompute"}
)
_COMPUTE_RELATED_RESOURCE_FIELDS = {
    "cloudchef.nodes.Network": ("networkId", "string"),
    "cloudchef.nodes.SecurityGroup": ("securityGroupIds", "array"),
}
_COMPUTE_DIRECT_FIELD_ALIASES = {
    "networkId": ("network_id", "vpc_id"),
    "subnetId": ("subnet_id", "v_switch_id"),
    "securityGroupIds": ("security_group_ids",),
}
_COMPUTE_DIRECT_FIELD_TYPES = {
    "networkId": "string",
    "subnetId": "string",
    "securityGroupIds": "array",
}
_NETWORK_METADATA_KEYS = ("VpcId", "NetworkId", "vpcId", "networkId")
_ZONE_METADATA_KEYS = ("Zone", "zoneId", "availabilityZone")
_RESOURCE_BUNDLE_RESULT_KEYS = ("id", "name", "cloudEntryTypeId")


def _normalize_catalog_summary(
    catalog: dict[str, Any],
    *,
    index: int,
    exact_catalog: bool,
) -> dict[str, Any]:
    """Return catalog identity and supported operations without request details."""

    summary: dict[str, Any] = {
        "index": index,
        "id": catalog.get("id", ""),
        "name": catalog.get("nameZh") or catalog.get("name", ""),
        "sourceKey": catalog.get("sourceKey", ""),
        "serviceCategory": catalog.get("serviceCategory", ""),
    }
    if catalog.get("type"):
        summary["catalogType"] = catalog["type"]
    if exact_catalog:
        status = str(catalog.get("status") or catalog.get("state") or "").strip()
        if status:
            summary["status"] = status
    else:
        summary["status"] = "PUBLISHED"
    summary["available_operations"] = serialize_available_operations(
        available_catalog_operations(summary)
    )
    return summary


def _project_resource_bundle(resource_bundle: dict[str, Any]) -> dict[str, Any]:
    """Return only resource-pool identity fields needed by request consumers."""

    return {
        key: resource_bundle[key]
        for key in _RESOURCE_BUNDLE_RESULT_KEYS
        if key in resource_bundle
    }


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
        catalogs = (_normalize_catalog_summary(payload, index=1, exact_catalog=True),)
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
        _normalize_catalog_summary(item, index=index, exact_catalog=False)
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
        Normalized user-facing request and pre-approval facts.

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
    normalized_metadata = normalize_catalog(payload, index=1, exact_catalog=True)
    normalized_metadata.update(build_catalog_detail_metadata(payload, catalog_id))
    return CatalogDetailResult(metadata=normalized_metadata)


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
    """List resource pools with adapter-neutral request placement options.

    SmartCMP resource pools expose platform collections under API-specific keys.
    This operation projects them onto catalog request-field names and applies
    declared dependencies so AtlasClaw and MCP do not duplicate SmartCMP domain
    rules in their protocol adapters.

    Raises:
        SmartCmpValidationError: If a requested resource pool or declared
            placement field cannot be resolved from the SmartCMP response.
    """

    reserved_context_keys = {"catalogId", "node"}.intersection(query.placement_values)
    if reserved_context_keys:
        raise SmartCmpValidationError(
            "Resource-pool catalog context must use catalog_id and "
            "node_template_name, not placement_values.",
            trace_id=client.request.context.trace_id,
        )
    catalog_id = _required(query.catalog_id, "Catalog ID", client)
    node_name = _required(query.node_template_name, "Node template name", client)
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
    rows = _extract_object_list(payload)
    resource_bundle_id = query.resource_bundle_id.strip()
    if resource_bundle_id:
        rows = [
            item
            for item in rows
            if str(item.get("id") or "").strip() == resource_bundle_id
        ]
        if len(rows) != 1:
            raise SmartCmpValidationError(
                f"Resource pool {resource_bundle_id} must resolve to exactly one "
                "available result for the selected request context.",
                trace_id=client.request.context.trace_id,
            )

    if not resource_bundle_id:
        return CatalogItemsResult(
            items=tuple(_project_resource_bundle(item) for item in rows)
        )

    catalog = await _load_request_catalog(client, catalog_id)
    catalog_node_type = _catalog_node_type(catalog.get("blueprint"), node_name)
    if catalog_node_type != query.node_type.strip():
        raise SmartCmpValidationError(
            "The selected catalog node type does not match the resource-pool "
            "request context.",
            trace_id=client.request.context.trace_id,
        )
    component_id = await _resolve_component_id(client, catalog_node_type)
    normalized = []
    for resource_bundle in rows:
        normalized.append(
            await _resolve_resource_bundle_request_fields(
                client,
                resource_bundle=resource_bundle,
                catalog=catalog,
                node_name=node_name,
                component_id=component_id,
                business_group_id=query.business_group_id,
                requested_fields=query.placement_fields,
                selected_values=query.placement_values,
            )
        )
    selection_field, selection_candidates = _top_level_selection(normalized[0])
    return CatalogItemsResult(
        items=tuple(normalized),
        selection_field=selection_field,
        selection_candidates=selection_candidates,
    )


def _top_level_selection(
    resolved_bundle: dict[str, Any],
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    """Project the next dynamic field and its options outside the pool item."""

    pending_keys = {
        str(key or "").strip()
        for key in list(resolved_bundle.get("missingSelectionFields") or [])
        if str(key or "").strip()
    }
    for field in list(resolved_bundle.get("requestFields") or []):
        if not isinstance(field, dict):
            continue
        field_key = str(field.get("key") or "").strip()
        options = tuple(
            {
                "id": option.get("id"),
                "name": option.get("name"),
            }
            for option in list(field.get("options") or [])
            if isinstance(option, dict)
            and option.get("id") not in (None, "")
            and str(option.get("name") or "").strip()
        )
        if field_key not in pending_keys or not options:
            continue
        selection_field = {
            key: value
            for key, value in {
                "key": field_key,
                "target": field.get("target"),
                "type": field.get("type"),
                "required": field.get("required") is True,
                "dependsOn": list(field.get("dependsOn") or []),
            }.items()
            if value not in (None, "")
        }
        return selection_field, options
    return {}, ()


async def _load_request_catalog(
    client: SmartCmpClient,
    catalog_id: str,
) -> dict[str, Any]:
    payload = await client.request_json(
        "GET",
        f"/catalogs/{quote(catalog_id, safe='')}",
    )
    if not isinstance(payload, dict) or str(payload.get("id") or "") != catalog_id:
        raise SmartCmpUpstreamError(
            "SmartCMP returned an invalid catalog while resolving request fields.",
            trace_id=client.request.context.trace_id,
        )
    return payload


async def _resolve_component_id(
    client: SmartCmpClient,
    node_type: str,
) -> str:
    """Resolve the component identity used by catalog field lookups.

    SmartCMP catalog request forms bind ``componentId`` from the component whose
    orchestration ``model.typeName`` matches the selected blueprint node.  The
    catalog ``componentType`` is a resource-pool filter and is not a component
    database identifier.
    """

    payload = await client.request_json(
        "GET",
        "/components",
        params={"all": "", "types": node_type},
    )
    components = _extract_object_list(payload)
    matching = [
        item
        for item in components
        if str(
            (item.get("model") or {}).get("typeName")
            if isinstance(item.get("model"), dict)
            else ""
        ).strip()
        == node_type
    ]
    if len(matching) != 1:
        raise SmartCmpValidationError(
            f"SmartCMP did not resolve exactly one component for node type "
            f"'{node_type}'.",
            trace_id=client.request.context.trace_id,
        )
    component_id = str(matching[0].get("id") or "").strip()
    if not component_id:
        raise SmartCmpValidationError(
            f"SmartCMP resolved a component without an ID for node type "
            f"'{node_type}'.",
            trace_id=client.request.context.trace_id,
        )
    return component_id


async def _resolve_resource_bundle_request_fields(
    client: SmartCmpClient,
    *,
    resource_bundle: dict[str, Any],
    catalog: dict[str, Any],
    node_name: str,
    component_id: str,
    business_group_id: str,
    requested_fields: tuple[str, ...],
    selected_values: dict[str, str],
) -> dict[str, Any]:
    node_config = _catalog_node_config(catalog, node_name)
    node_type = _catalog_node_type(catalog.get("blueprint"), node_name)
    is_compute_node = node_type in _COMPUTE_NODE_TYPES
    base_fields = await _load_cloud_request_schema(
        client,
        resource_bundle,
        "Compute" if is_compute_node else node_name,
    )
    catalog_fields = _schema_properties(node_config.get("schema"))
    fields = _merge_field_maps(base_fields, catalog_fields)
    data = node_config.get("data") if isinstance(node_config.get("data"), dict) else {}
    if is_compute_node:
        fields = {
            key: schema
            for key, schema in fields.items()
            if _lookup_config(schema) is not None
            or bool(schema.get("cloudResourceType"))
        }
        fields, data = _canonical_compute_fields(fields, data)
    bundle_fields = _resource_bundle_fields(node_config)
    bundle_data = (
        data.get("resource_bundle_config")
        if isinstance(data.get("resource_bundle_config"), dict)
        else {}
    )
    effective_values = _effective_field_values(
        selected_values,
        (fields, data),
        (bundle_fields, bundle_data),
    )
    hidden_fields = _configured_field_names(data.get("un_visibility_property"))
    immutable_fields = _configured_field_names(data.get("un_modification_property"))
    resolved_fields: list[dict[str, Any]] = []
    missing_required_fields: list[str] = []
    missing_selection_fields: list[str] = []
    configuration_errors: list[str] = []
    auto_lookup_pending = not requested_fields

    for target, source_fields, source_data in (
        ("params", fields, data),
        (
            "resourceBundleParams",
            bundle_fields,
            bundle_data,
        ),
    ):
        request_keys = tuple(source_fields)
        for field_name, field_schema in source_fields.items():
            if field_name in _RESOURCE_BUNDLE_SYSTEM_FIELDS or field_name == "version":
                continue
            condition = str(
                field_schema.get("condition")
                or field_schema.get("conditionTemplate")
                or ""
            ).strip()
            if condition and not _condition_matches(
                condition,
                data=data,
                selected_values=effective_values,
                request_keys=request_keys,
            ):
                continue
            source_field_name = str(field_schema.get("_sourceField") or field_name)
            field_values = _selected_values_for_schema(
                effective_values,
                source_field_name=source_field_name,
                canonical_field_name=field_name,
                schema=field_schema,
            )
            field = _request_field(
                field_name,
                target=target,
                schema=field_schema,
                data=source_data,
                hidden=(
                    field_name in hidden_fields
                    or source_field_name in hidden_fields
                ),
                immutable=(
                    field_name in immutable_fields
                    or source_field_name in immutable_fields
                ),
                selected_values=field_values,
            )
            if field is None:
                continue
            if field_name in _COMPUTE_DIRECT_FIELD_TYPES:
                field["target"] = field_name
                field["type"] = _COMPUTE_DIRECT_FIELD_TYPES[field_name]
                field["dependsOn"] = [
                    _canonical_compute_field_name(dependency)
                    for dependency in field["dependsOn"]
                ]
            options_resolved = bool(field.get("options"))
            (
                should_query_options,
                auto_query_options,
                dependencies_resolved,
                explicitly_requested,
            ) = _lookup_resolution_plan(
                field,
                field_name=field_name,
                requested_fields=requested_fields,
                selected_values=field_values,
                auto_lookup_pending=auto_lookup_pending,
            )
            if should_query_options and dependencies_resolved:
                options = await _query_request_field_options(
                    client,
                    field_name=source_field_name,
                    schema=field_schema,
                    resource_bundle=resource_bundle,
                    business_group_id=business_group_id,
                    component_id=component_id,
                    selected_values=field_values,
                )
                field["options"] = options
                options_resolved = True
                if auto_query_options:
                    auto_lookup_pending = False
            if explicitly_requested and not dependencies_resolved:
                configuration_errors.append(
                    f"Lookup field '{field_name}' cannot be validated until "
                    "its dependencies are selected."
                )
            elif options_resolved:
                _append_lookup_option_errors(
                    field_name,
                    field=field,
                    options=field["options"],
                    configuration_errors=configuration_errors,
                )
            if field["ask"] and _is_missing(field.get("value")):
                missing_selection_fields.append(field_name)
            if field["required"] and _is_missing(field.get("value")):
                if field.get("ask"):
                    missing_required_fields.append(field_name)
                else:
                    configuration_errors.append(
                        f"Required field '{field_name}' has no configured value and cannot be selected."
                    )
            resolved_fields.append(field)

    if is_compute_node:
        await _append_compute_related_resource_fields(
            client,
            resource_bundle=resource_bundle,
            catalog=catalog,
            node_name=node_name,
            business_group_id=business_group_id,
            component_id=component_id,
            requested_fields=requested_fields,
            selected_values=effective_values,
            resolved_fields=resolved_fields,
            missing_required_fields=missing_required_fields,
            missing_selection_fields=missing_selection_fields,
            configuration_errors=configuration_errors,
            auto_lookup_pending=auto_lookup_pending,
        )

    normalized = _project_resource_bundle(resource_bundle)
    normalized["requestFields"] = resolved_fields
    normalized["missingRequiredFields"] = missing_required_fields
    normalized["missingSelectionFields"] = missing_selection_fields
    normalized["configurationErrors"] = configuration_errors
    return normalized


async def _append_compute_related_resource_fields(
    client: SmartCmpClient,
    *,
    resource_bundle: dict[str, Any],
    catalog: dict[str, Any],
    node_name: str,
    business_group_id: str,
    component_id: str,
    requested_fields: tuple[str, ...],
    selected_values: dict[str, Any],
    resolved_fields: list[dict[str, Any]],
    missing_required_fields: list[str],
    missing_selection_fields: list[str],
    configuration_errors: list[str],
    auto_lookup_pending: bool,
) -> None:
    existing_keys = {str(field.get("key") or "") for field in resolved_fields}
    has_network_node = False
    node_templates = _catalog_node_templates(catalog.get("blueprint"))
    for related_node in _relationship_targets(node_templates.get(node_name)):
        node_template = node_templates.get(related_node)
        if not isinstance(node_template, dict):
            continue
        related_type = str(node_template.get("type") or "").strip()
        direct_field = _COMPUTE_RELATED_RESOURCE_FIELDS.get(related_type)
        if direct_field is None:
            continue
        direct_key, direct_type = direct_field
        has_network_node = has_network_node or related_type == "cloudchef.nodes.Network"
        if direct_key in existing_keys:
            continue
        schema_node = related_type.rsplit(".", maxsplit=1)[-1]
        base_fields = await _load_cloud_request_schema(
            client,
            resource_bundle,
            schema_node,
        )
        node_config = _catalog_node_config(catalog, related_node)
        fields = _merge_field_maps(
            base_fields,
            _schema_properties(node_config.get("schema")),
        )
        field_schema = fields.get("resource_id")
        if not isinstance(field_schema, dict):
            continue
        data = (
            node_config.get("data")
            if isinstance(node_config.get("data"), dict)
            else {}
        )
        hidden_fields = _configured_field_names(data.get("un_visibility_property"))
        immutable_fields = _configured_field_names(
            data.get("un_modification_property")
        )
        related_values = dict(selected_values)
        if direct_key in related_values:
            related_values["resource_id"] = related_values[direct_key]
        related_values = _selected_values_for_schema(
            related_values,
            source_field_name="resource_id",
            canonical_field_name=direct_key,
            schema=field_schema,
        )
        field = _request_field(
            "resource_id",
            target="params",
            schema=field_schema,
            data=data,
            hidden="resource_id" in hidden_fields,
            immutable="resource_id" in immutable_fields,
            selected_values=related_values,
        )
        if field is None:
            continue
        field["key"] = direct_key
        field["target"] = direct_key
        field["type"] = direct_type
        field["dependsOn"] = [
            _canonical_compute_field_name(dependency)
            for dependency in field["dependsOn"]
        ]
        field["ask"] = (
            field["visible"]
            and field["editable"]
            and field["lookup"]
            and _is_missing(field.get("value"))
        )
        if direct_type == "array" and isinstance(field.get("value"), str):
            field["value"] = _selected_field_value(
                field["value"],
                {"type": "array"},
            )
        options_resolved = bool(field.get("options"))
        (
            should_query_options,
            auto_query_options,
            dependencies_resolved,
            explicitly_requested,
        ) = _lookup_resolution_plan(
            field,
            field_name=direct_key,
            requested_fields=requested_fields,
            selected_values=related_values,
            auto_lookup_pending=auto_lookup_pending,
        )
        if should_query_options and dependencies_resolved:
            options = await _query_request_field_options(
                client,
                field_name=direct_key,
                schema=field_schema,
                resource_bundle=resource_bundle,
                business_group_id=business_group_id,
                component_id=component_id,
                selected_values=related_values,
            )
            field["options"] = options
            options_resolved = True
            if auto_query_options:
                auto_lookup_pending = False
        if explicitly_requested and not dependencies_resolved:
            configuration_errors.append(
                f"Lookup field '{direct_key}' cannot be validated until "
                "its dependencies are selected."
            )
        elif options_resolved:
            _append_lookup_option_errors(
                direct_key,
                field=field,
                options=field["options"],
                configuration_errors=configuration_errors,
            )
        if field["ask"] and _is_missing(field.get("value")):
            missing_selection_fields.append(direct_key)
        if field["required"] and _is_missing(field.get("value")):
            if field["ask"]:
                missing_required_fields.append(direct_key)
            else:
                configuration_errors.append(
                    f"Required field '{direct_key}' has no configured value and cannot be selected."
                )
        resolved_fields.append(field)
        existing_keys.add(direct_key)
    if has_network_node and "subnetId" not in existing_keys:
        _append_compute_subnet_field(
            resource_bundle=resource_bundle,
            requested_fields=requested_fields,
            selected_values=selected_values,
            resolved_fields=resolved_fields,
            missing_selection_fields=missing_selection_fields,
            configuration_errors=configuration_errors,
            auto_lookup_pending=auto_lookup_pending,
        )


def _append_compute_subnet_field(
    *,
    resource_bundle: dict[str, Any],
    requested_fields: tuple[str, ...],
    selected_values: dict[str, Any],
    resolved_fields: list[dict[str, Any]],
    missing_selection_fields: list[str],
    configuration_errors: list[str],
    auto_lookup_pending: bool,
) -> None:
    raw_subnets = resource_bundle.get("subnets")
    if not isinstance(raw_subnets, list):
        return
    subnets = [item for item in raw_subnets if isinstance(item, dict)]
    if not subnets:
        return
    dependencies = []
    if any(_resource_metadata_value(item, _NETWORK_METADATA_KEYS)[0] for item in subnets):
        dependencies.append("networkId")
    if any(_resource_metadata_value(item, _ZONE_METADATA_KEYS)[0] for item in subnets):
        dependencies.append("available_zone_id")
    value = str(selected_values.get("subnetId") or "").strip()
    options: list[dict[str, Any]] = []
    field = {
        "key": "subnetId",
        "target": "subnetId",
        "type": "string",
        "required": False,
        "visible": True,
        "editable": True,
        "ask": _is_missing(value),
        "lookup": True,
        "dependsOn": dependencies,
        "value": value,
        "options": options,
        "validation": {},
    }
    (
        should_resolve_options,
        _auto_query_options,
        dependencies_resolved,
        explicitly_requested,
    ) = _lookup_resolution_plan(
        field,
        field_name="subnetId",
        requested_fields=requested_fields,
        selected_values=selected_values,
        auto_lookup_pending=auto_lookup_pending,
    )
    if should_resolve_options and dependencies_resolved:
        options = [
            option
            for item in subnets
            if _resource_dependency_matches(
                item,
                property_names=_NETWORK_METADATA_KEYS,
                selected_value=selected_values.get("networkId"),
            )
            and _resource_dependency_matches(
                item,
                property_names=_ZONE_METADATA_KEYS,
                selected_value=selected_values.get("available_zone_id"),
            )
            if (option := _normalize_option(item)) is not None
        ]
    field["options"] = options
    if explicitly_requested and not dependencies_resolved:
        configuration_errors.append(
            "Lookup field 'subnetId' cannot be validated until its dependencies are selected."
        )
    elif should_resolve_options:
        _append_lookup_option_errors(
            "subnetId",
            field=field,
            options=options,
            configuration_errors=configuration_errors,
        )
    if field["ask"]:
        missing_selection_fields.append("subnetId")
    resolved_fields.append(field)


def _resource_metadata_value(
    item: dict[str, Any],
    property_names: tuple[str, ...],
) -> tuple[bool, Any]:
    properties = item.get("properties")
    sources = (item, properties if isinstance(properties, dict) else {})
    for source in sources:
        for property_name in property_names:
            if property_name in source:
                return True, source[property_name]
    return False, None


def _resource_dependency_matches(
    item: dict[str, Any],
    *,
    property_names: tuple[str, ...],
    selected_value: Any,
) -> bool:
    declared, declared_value = _resource_metadata_value(item, property_names)
    return (
        not declared
        or _is_missing(selected_value)
        or str(declared_value) == str(selected_value)
    )


def _canonical_compute_fields(
    fields: dict[str, dict[str, Any]],
    data: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    canonical_fields = {
        key: schema
        for key, schema in fields.items()
        if _canonical_compute_field_name(key) == key
    }
    canonical_data = dict(data)
    for canonical_name, aliases in _COMPUTE_DIRECT_FIELD_ALIASES.items():
        candidates = [
            (field_name, fields[field_name])
            for field_name in (canonical_name, *aliases)
            if field_name in fields
        ]
        if not candidates:
            continue
        explicit_schema = fields.get(canonical_name)
        if isinstance(explicit_schema, dict):
            source_name, source_schema = canonical_name, explicit_schema
        else:
            source_name, source_schema = next(
                (
                    candidate
                    for candidate in candidates
                    if _lookup_config(candidate[1]) is not None
                    or bool(candidate[1].get("cloudResourceType"))
                ),
                candidates[0],
            )
        schema = deepcopy(source_schema)
        schema["_sourceField"] = source_name
        if any(
            _request_flag(candidate.get("required"), default=False)
            for _, candidate in candidates
        ):
            schema["required"] = {"inRequest": {"value": True}}
        canonical_fields[canonical_name] = schema
        if _is_missing(_field_value(canonical_data.get(canonical_name))):
            for alias in aliases:
                value = _field_value(data.get(alias))
                if not _is_missing(value):
                    canonical_data[canonical_name] = value
                    break
    return canonical_fields, canonical_data


def _canonical_compute_field_name(field_name: str) -> str:
    for canonical_name, aliases in _COMPUTE_DIRECT_FIELD_ALIASES.items():
        if field_name in aliases:
            return canonical_name
    return field_name


def _selected_values_for_schema(
    selected_values: dict[str, Any],
    *,
    source_field_name: str,
    canonical_field_name: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    values = dict(selected_values)
    if canonical_field_name in values:
        values[source_field_name] = values[canonical_field_name]
    for dependency in _field_dependencies(schema):
        canonical_dependency = _canonical_compute_field_name(dependency)
        if dependency not in values and canonical_dependency in values:
            values[dependency] = values[canonical_dependency]
    return values


def _relationship_targets(node_template: Any) -> tuple[str, ...]:
    if not isinstance(node_template, dict):
        return ()
    relationships = node_template.get("relationships")
    if not isinstance(relationships, list):
        return ()
    return tuple(
        str(relationship.get("target") or "").strip()
        for relationship in relationships
        if isinstance(relationship, dict)
        and str(relationship.get("target") or "").strip()
    )


def _effective_field_values(
    selected_values: dict[str, str],
    *field_sources: tuple[dict[str, dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    values: dict[str, Any] = dict(selected_values)
    for fields, data in field_sources:
        for field_name, schema in fields.items():
            selected = _selected_field_value(values.get(field_name), schema)
            if not _is_missing(selected):
                values[field_name] = selected
                continue
            value = _field_value(data.get(field_name))
            if _is_missing(value):
                value = _field_value(
                    schema.get("defaultValue", schema.get("default", schema.get("value")))
                )
            if not _is_missing(value):
                values[field_name] = value
    return values


def _catalog_node_config(catalog: dict[str, Any], node_name: str) -> dict[str, Any]:
    blueprint = catalog.get("blueprint")
    actual_nodes = _catalog_node_names(blueprint)
    if actual_nodes and node_name not in actual_nodes:
        raise SmartCmpValidationError(
            f"Catalog node '{node_name}' is not present in mainYaml."
        )
    raw = blueprint.get("extensibleParams") if isinstance(blueprint, dict) else None
    try:
        extensible = yaml.safe_load(raw) if isinstance(raw, str) else raw
    except yaml.YAMLError as exc:
        raise SmartCmpValidationError(
            "Catalog extensibleParams is not valid YAML or JSON."
        ) from exc
    if not isinstance(extensible, dict):
        return {}
    node = extensible.get(node_name)
    if not isinstance(node, dict):
        if actual_nodes:
            return {}
        raise SmartCmpValidationError(
            f"Catalog node '{node_name}' has no request configuration."
        )
    blueprint_exts = blueprint.get("exts") if isinstance(blueprint, dict) else None
    logical_component = (
        blueprint_exts.get(node_name) if isinstance(blueprint_exts, dict) else None
    )
    if not logical_component:
        return node
    merged: dict[str, Any] = {}
    for candidate_name, candidate in extensible.items():
        if (
            candidate_name != node_name
            and candidate_name not in actual_nodes
            and isinstance(candidate, dict)
            and blueprint_exts.get(candidate_name) == logical_component
        ):
            merged = _deep_merge(merged, candidate)
    return _deep_merge(merged, node)


def _catalog_node_names(blueprint: Any) -> frozenset[str]:
    return frozenset(_catalog_node_templates(blueprint))


def _catalog_node_type(blueprint: Any, node_name: str) -> str:
    node = _catalog_node_templates(blueprint).get(node_name)
    return str(node.get("type") or "").strip() if isinstance(node, dict) else ""


def _catalog_node_templates(blueprint: Any) -> dict[str, Any]:
    if not isinstance(blueprint, dict):
        return {}
    raw = blueprint.get("mainYaml")
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        main_yaml = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise SmartCmpValidationError("Catalog mainYaml is not valid YAML.") from exc
    if not isinstance(main_yaml, dict):
        return {}
    nodes = main_yaml.get("node_templates")
    if not isinstance(nodes, dict):
        topology = main_yaml.get("topology_template")
        nodes = topology.get("node_templates") if isinstance(topology, dict) else None
    return {str(key): value for key, value in nodes.items()} if isinstance(nodes, dict) else {}


async def _load_cloud_request_schema(
    client: SmartCmpClient,
    resource_bundle: dict[str, Any],
    node_name: str,
) -> dict[str, dict[str, Any]]:
    cloud_entry_type = str(resource_bundle.get("cloudEntryTypeId") or "").strip()
    if not cloud_entry_type:
        return {}
    payload = await client.request_json(
        "POST",
        "/cloudentries?generic-clouds",
        json_body={"cloudEntryType": cloud_entry_type},
    )
    rows = _extract_object_list(payload)
    if not rows:
        raise SmartCmpUpstreamError(
            "SmartCMP returned no cloud request schema.",
            trace_id=client.request.context.trace_id,
        )
    resource_config = rows[0].get("resourceConfig")
    node_schema = resource_config.get(node_name) if isinstance(resource_config, dict) else None
    return _schema_properties(node_schema)


def _schema_properties(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    properties = value.get("properties")
    source = properties if isinstance(properties, dict) else value
    return {
        str(key): deepcopy(item)
        for key, item in source.items()
        if isinstance(item, dict)
    }


def _resource_bundle_fields(node_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    schema = node_config.get("resourceBundleSchema")
    if not isinstance(schema, dict):
        return {}
    resource_bundle_config = schema.get("resource_bundle_config")
    if not isinstance(resource_bundle_config, dict):
        nested = schema.get("schema")
        resource_bundle_config = (
            nested.get("resource_bundle_config") if isinstance(nested, dict) else None
        )
    return _schema_properties(resource_bundle_config)


def _merge_field_maps(
    base_fields: dict[str, dict[str, Any]],
    catalog_fields: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result = deepcopy(base_fields)
    for key, override in catalog_fields.items():
        current = result.get(key)
        result[key] = _deep_merge(current, override) if isinstance(current, dict) else deepcopy(override)
    return result


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _configured_field_names(value: Any) -> frozenset[str]:
    value = _field_value(value)
    if isinstance(value, str):
        return frozenset(item.strip() for item in value.split(",") if item.strip())
    if isinstance(value, list):
        return frozenset(str(item).strip() for item in value if str(item).strip())
    return frozenset()


def _request_field(
    field_name: str,
    *,
    target: str,
    schema: dict[str, Any],
    data: dict[str, Any],
    hidden: bool,
    immutable: bool,
    selected_values: dict[str, Any],
) -> dict[str, Any] | None:
    required = _request_flag(schema.get("required"), default=False)
    visible = not hidden and _request_flag(
        schema.get("visibility"),
        config=schema.get("config"),
        config_key="visibility",
        default=True,
    )
    editable = not immutable and _request_flag(
        schema.get("modification"),
        config=schema.get("config"),
        config_key="modification",
        default=True,
    )
    value = _selected_field_value(selected_values.get(field_name), schema)
    if _is_missing(value):
        value = _field_value(data.get(field_name))
    if _is_missing(value):
        value = _field_value(
            schema.get("defaultValue", schema.get("default", schema.get("value")))
        )
    lookup = _lookup_config(schema) is not None or bool(schema.get("cloudResourceType"))
    if not visible and _is_missing(value) and not required:
        return None
    static_options = _static_options(schema)
    ask = bool(_field_value(schema.get("ask")))
    return {
        "key": field_name,
        "target": f"{target}.{field_name}",
        "type": _field_type(schema),
        "required": required,
        "visible": visible,
        "editable": editable,
        "ask": (required or ask) and visible and editable and _is_missing(value),
        "lookup": lookup,
        "dependsOn": _field_dependencies(schema),
        "value": value,
        "options": static_options,
        "validation": _field_validation(schema),
    }


def _request_flag(
    value: Any,
    *,
    config: Any = None,
    config_key: str = "",
    default: bool,
) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        request = value.get("inRequest")
        if isinstance(request, dict) and "value" in request:
            return bool(request.get("value"))
    if isinstance(config, dict):
        section = config.get(config_key)
        if isinstance(section, dict) and "allowInRequest" in section:
            return bool(section.get("allowInRequest"))
    return default


def _field_value(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return _field_value(value.get("value"))
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.casefold() == "true":
            return True
        if stripped.casefold() == "false":
            return False
        return stripped
    return value


def _selected_field_value(value: Any, schema: dict[str, Any]) -> Any:
    if isinstance(value, dict) and "value" in value:
        value = value.get("value")
    if not isinstance(value, str):
        return value
    value = value.strip()
    field_type = _field_type(schema)
    if field_type == "boolean":
        if value.casefold() == "true":
            return True
        if value.casefold() == "false":
            return False
        return value
    if field_type == "array":
        try:
            parsed = json.loads(value)
        except ValueError:
            return value
        return parsed if isinstance(parsed, list) else value
    if field_type in {"integer", "int"}:
        try:
            return int(value)
        except ValueError:
            return value
    if field_type in {"number", "float", "double"}:
        try:
            return float(value)
        except ValueError:
            return value
    return value


def _is_missing(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _lookup_dependencies_resolved(
    field: dict[str, Any],
    selected_values: dict[str, Any],
) -> bool:
    return all(
        not _is_missing(selected_values.get(str(dependency)))
        for dependency in field.get("dependsOn", [])
    )


def _lookup_resolution_plan(
    field: dict[str, Any],
    *,
    field_name: str,
    requested_fields: tuple[str, ...],
    selected_values: dict[str, Any],
    auto_lookup_pending: bool,
) -> tuple[bool, bool, bool, bool]:
    """Plan one lookup without treating unresolved automatic candidates as errors."""

    dependencies_resolved = _lookup_dependencies_resolved(field, selected_values)
    explicitly_requested = (
        field_name in requested_fields or not _is_missing(field.get("value"))
    )
    auto_query = (
        auto_lookup_pending
        and field.get("ask") is True
        and _is_missing(field.get("value"))
        and dependencies_resolved
    )
    return (
        field.get("lookup") is True and (explicitly_requested or auto_query),
        auto_query,
        dependencies_resolved,
        explicitly_requested,
    )


def _append_lookup_option_errors(
    field_name: str,
    *,
    field: dict[str, Any],
    options: list[dict[str, Any]],
    configuration_errors: list[str],
) -> None:
    if not options:
        configuration_errors.append(
            f"Lookup field '{field_name}' has no selectable options for the "
            "current request context."
        )
        return
    value = field.get("value")
    if _is_missing(value):
        return
    option_ids = {str(option.get("id")) for option in options}
    selected_values = value if isinstance(value, list) else [value]
    invalid_values = [
        selected_value
        for selected_value in selected_values
        if str(selected_value) not in option_ids
    ]
    if invalid_values:
        configuration_errors.append(
            f"Lookup field '{field_name}' contains a value that is not "
            "selectable for the current request context."
        )
        return
    options_by_id = {str(option.get("id")): option for option in options}
    for selected_value in selected_values:
        properties = options_by_id[str(selected_value)].get("properties")
        if not isinstance(properties, dict):
            continue
        allocation_method = str(
            properties.get("ipAllocationMethod") or ""
        ).casefold()
        available_ip_size = properties.get("availableIpSize")
        if (
            allocation_method == "ip_pool"
            and isinstance(available_ip_size, (int, float))
            and not isinstance(available_ip_size, bool)
            and available_ip_size <= 0
        ):
            configuration_errors.append(
                f"Lookup field '{field_name}' selects an IP pool with no "
                "available IP addresses."
            )
            return


def _field_type(schema: dict[str, Any]) -> str:
    value = str(schema.get("type") or "string")
    if value in {"multipleSelect", "multiple", "array"} or schema.get("selectMode") == "multiple":
        return "array"
    if value in {"inputCheckBox", "checkbox"}:
        return "boolean"
    if value in {"input", "select", "compute_input"}:
        return "string"
    return value


def _static_options(schema: dict[str, Any]) -> list[dict[str, Any]]:
    options = (
        schema.get("selectDatas")
        or schema.get("options")
        or schema.get("source")
        or schema.get("items")
    )
    if not isinstance(options, list):
        return []
    return [
        normalized
        for item in options
        if isinstance(item, dict)
        if (normalized := _normalize_option(item)) is not None
    ]


def _normalize_option(item: dict[str, Any]) -> dict[str, Any] | None:
    option_id = item.get("id", item.get("value"))
    if option_id in (None, ""):
        return None
    name = item.get("name", item.get("label", option_id))
    if isinstance(name, dict):
        name = name.get("zh") or name.get("en") or option_id
    return {"id": option_id, "name": str(name), "properties": item.get("properties", {})}


def _field_dependencies(schema: dict[str, Any]) -> list[str]:
    dependencies: list[str] = []
    declared = schema.get("dependencies")
    if isinstance(declared, dict):
        dependencies.extend(str(key) for key in declared)
    lookup = _lookup_config(schema)
    encoded = json.dumps(lookup, ensure_ascii=True) if lookup else ""
    dependencies.extend(_LOOKUP_FIELD_REFERENCE.findall(encoded))
    dependencies.extend(
        item
        for item in _LOOKUP_BUNDLE_REFERENCE.findall(encoded)
        if item not in {"policy_resource", "cloudEntryId"}
    )
    dependency_key = str(schema.get("dependencyKey") or "")
    if dependency_key and dependency_key != "policy_resource":
        dependencies.append(dependency_key)
    return list(dict.fromkeys(dependencies))


def _field_validation(schema: dict[str, Any]) -> dict[str, Any]:
    validation = {
        key: schema[key]
        for key in ("minimum", "maximum", "minLength", "maxLength", "pattern")
        if key in schema
    }
    match = re.search(
        r"validate-type=['\"]([^'\"]+)['\"]",
        str(schema.get("customTemplate") or ""),
    )
    if match:
        validation["rule"] = match.group(1)
    return validation


def _lookup_config(schema: dict[str, Any]) -> dict[str, Any] | None:
    config = schema.get("config")
    if not isinstance(config, dict):
        return None
    value = config.get("value")
    if isinstance(value, dict) and str(value.get("source") or "").casefold() == "api":
        return value
    table = config.get("table")
    body = table.get("body") if isinstance(table, dict) else None
    value = body.get("value") if isinstance(body, dict) else None
    return value if isinstance(value, dict) and str(value.get("source") or "").casefold() == "api" else None


async def _query_request_field_options(
    client: SmartCmpClient,
    *,
    field_name: str,
    schema: dict[str, Any],
    resource_bundle: dict[str, Any],
    business_group_id: str,
    component_id: str,
    selected_values: dict[str, Any],
) -> list[dict[str, Any]]:
    static_options = _static_options(schema)
    if static_options:
        return static_options
    dependencies = _field_dependencies(schema)
    if any(selected_values.get(key) in (None, "") for key in dependencies):
        return []
    lookup = _lookup_config(schema)
    context: dict[str, Any] = {
        "businessGroupId": business_group_id,
        "componentId": component_id,
        "policy_resource": resource_bundle.get("id"),
        "cloudEntryId": resource_bundle.get("cloudEntryId"),
        **selected_values,
    }
    if lookup:
        method = str(lookup.get("method") or "").upper()
        expression = str(lookup.get("expression") or "").strip().lstrip("/")
        action = expression.partition("action=")[2]
        if method != "POST" or action not in _SUPPORTED_LOOKUP_ACTIONS:
            raise SmartCmpValidationError(
                f"Field '{field_name}' declares an unsupported lookup."
            )
        body = _resolve_lookup_value(lookup.get("body"), context)
        if not isinstance(body, dict):
            raise SmartCmpValidationError(
                f"Field '{field_name}' lookup body is invalid."
            )
    else:
        cloud_resource_type = str(schema.get("cloudResourceType") or "").strip()
        if not cloud_resource_type:
            return []
        query_properties = deepcopy(schema.get("queryProperties"))
        if not isinstance(query_properties, dict):
            query_properties = {}
        query_properties.setdefault("resourceBundleId", resource_bundle.get("id"))
        declared = schema.get("dependencies")
        if isinstance(declared, dict):
            for source, target in declared.items():
                if selected_values.get(str(source)) not in (None, ""):
                    query_properties[str(target)] = selected_values[str(source)]
        body = {
            "businessGroupId": business_group_id,
            "cloudEntryId": resource_bundle.get("cloudEntryId"),
            "cloudResourceType": cloud_resource_type,
            "queryProperties": query_properties,
        }
        action = "queryCloudResource"
    payload = await client.request_json(
        "POST",
        f"/cloudprovider?action={action}",
        json_body=body,
    )
    return [
        normalized
        for item in _extract_object_list(payload)
        if (normalized := _normalize_option(item)) is not None
    ]


def _resolve_lookup_value(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _resolve_lookup_value(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_lookup_value(item, context) for item in value]
    if not isinstance(value, str):
        return value
    field_match = _LOOKUP_FIELD_REFERENCE.fullmatch(value)
    if field_match:
        return context.get(field_match.group(1), "")
    bundle_match = _LOOKUP_BUNDLE_REFERENCE.fullmatch(value)
    if bundle_match:
        return context.get(bundle_match.group(1), "")
    context_match = _LOOKUP_CONTEXT_REFERENCE.fullmatch(value)
    if context_match:
        return context.get(context_match.group(1), "")
    return value


def _condition_matches(
    condition: str,
    *,
    data: dict[str, Any],
    selected_values: dict[str, Any],
    request_keys: tuple[str, ...],
) -> bool:
    expression = condition.strip()
    if expression.casefold() in {"", "true"}:
        return True
    if expression.casefold() == "false":
        return False
    expression = _trim_condition_parentheses(expression)
    or_parts = _split_condition(expression, "||")
    if len(or_parts) > 1:
        return any(
            _condition_matches(
                part,
                data=data,
                selected_values=selected_values,
                request_keys=request_keys,
            )
            for part in or_parts
        )
    and_parts = _split_condition(expression, "&&")
    if len(and_parts) > 1:
        return all(
            _condition_matches(
                part,
                data=data,
                selected_values=selected_values,
                request_keys=request_keys,
            )
            for part in and_parts
        )
    comparison = re.match(r"^(.+?)\s*(===|!==|==|!=)\s*(.+)$", expression)
    if comparison:
        left = _condition_value(
            comparison.group(1), data=data, selected_values=selected_values, request_keys=request_keys
        )
        right = _condition_literal(comparison.group(3))
        matched = left == right
        return not matched if comparison.group(2) in {"!==", "!="} else matched
    negated = expression.startswith("!")
    value = _condition_value(
        expression[1:] if negated else expression,
        data=data,
        selected_values=selected_values,
        request_keys=request_keys,
    )
    return not bool(value) if negated else bool(value)


def _trim_condition_parentheses(expression: str) -> str:
    result = expression.strip()
    while _condition_has_outer_parentheses(result):
        result = result[1:-1].strip()
    return result


def _condition_has_outer_parentheses(expression: str) -> bool:
    if not expression.startswith("(") or not expression.endswith(")"):
        return False
    depth = 0
    quote = ""
    escaped = False
    for index, character in enumerate(expression):
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote:
            escaped = True
            continue
        if character in {"'", '"'}:
            quote = "" if quote == character else character if not quote else quote
            continue
        if quote:
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0 and index != len(expression) - 1:
                return False
    return depth == 0 and not quote


def _split_condition(expression: str, operator: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    quote = ""
    escaped = False
    index = 0
    while index < len(expression):
        character = expression[index]
        if escaped:
            escaped = False
        elif character == "\\" and quote:
            escaped = True
        elif character in {"'", '"'}:
            quote = "" if quote == character else character if not quote else quote
        elif not quote:
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
            elif depth == 0 and expression.startswith(operator, index):
                parts.append(expression[start:index].strip())
                index += len(operator)
                start = index
                continue
        index += 1
    if parts:
        parts.append(expression[start:].strip())
        return parts
    return [expression]


def _condition_value(
    expression: str,
    *,
    data: dict[str, Any],
    selected_values: dict[str, Any],
    request_keys: tuple[str, ...],
) -> Any:
    path = _trim_condition_parentheses(expression.strip())
    if path.startswith("model."):
        path = path[len("model.") :]
    elif path.startswith("data."):
        path = path[len("data.") :]
    selected_key = path[:-6] if path.endswith(".value") else path
    if selected_key in request_keys and selected_key in selected_values:
        return selected_values[selected_key]
    current: Any = data
    for part in path.split("."):
        if part == "value" and not isinstance(current, dict):
            continue
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return _field_value(current)


def _condition_literal(value: str) -> Any:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    if stripped.casefold() == "true":
        return True
    if stripped.casefold() == "false":
        return False
    if stripped.casefold() == "null":
        return None
    try:
        return float(stripped) if "." in stripped else int(stripped)
    except ValueError:
        return stripped


async def list_flavors(
    client: SmartCmpClient,
    query: FlavorQuery,
) -> CatalogItemsResult:
    """List compute profiles or mapped cloud flavors for a request context."""

    compute_profile_id = query.compute_profile_id.strip()
    if compute_profile_id:
        resource_bundle_id = query.resource_bundle_id.strip()
        if not resource_bundle_id:
            raise SmartCmpValidationError(
                "Cloud-flavor query requires the selected resource pool.",
                trace_id=client.request.context.trace_id,
            )
        payload = await client.request_json(
            "GET",
            f"/flavors/{quote(compute_profile_id, safe='')}/cloud-flavors",
            params={
                "cloudResource": "true",
                "queryValue": query.query_value,
                "resourceBundleId": resource_bundle_id,
            },
        )
        rows = _require_direct_object_list(payload, "Cloud-flavor query", client)
        normalized = []
        for item in rows:
            flavor_id = str(item.get("flavorId") or "").strip()
            if not flavor_id:
                raise SmartCmpUpstreamError(
                    "Cloud-flavor query returned an item without flavorId.",
                    trace_id=client.request.context.trace_id,
                )
            normalized.append(
                {
                    "id": flavor_id,
                    "name": str(
                        item.get("flavorName") or item.get("name") or flavor_id
                    ),
                }
            )
        return CatalogItemsResult(items=tuple(normalized))

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
            "cloudResourceType": _image_resource_type(cloud_entry_type),
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


def _image_resource_type(cloud_entry_type: str) -> str:
    """Build the CMP image resource type for one resource-pool platform.

    CMP routes every Generic-Cloud implementation through the shared
    ``generic-cloud::images`` resource family. The resource pool still exposes
    its concrete implementation ID, such as Terraform Enterprise or Tencent
    Cloud, so the Provider must normalize only the dispatch type while keeping
    the caller-facing resource-pool contract unchanged.
    """

    if cloud_entry_type == _GENERIC_CLOUD_ENTRY_TYPE or cloud_entry_type.startswith(
        f"{_GENERIC_CLOUD_ENTRY_TYPE}:"
    ):
        return f"{_GENERIC_CLOUD_ENTRY_TYPE}::images"
    return f"{cloud_entry_type}::images"


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
        "runtime_fields",
        "runtimeFields",
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
        runtime_fields = raw_spec.get("runtime_fields")
        if not isinstance(runtime_fields, dict):
            runtime_fields = raw_spec.get("runtimeFields")
        if isinstance(runtime_fields, dict):
            resolver = str(runtime_fields.get("resolver") or "").strip()
            if resolver:
                normalized_spec["runtime_fields"] = {"resolver": resolver}
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
            if node_type in _COMPUTE_NODE_TYPES:
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
