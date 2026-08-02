# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Resolve SmartCMP Host pages through one Provider-level Context callable.

AtlasClaw invokes this module with a server-owned route contract. The resolver
validates that contract, reads only the current user's page object, and returns
the provider-neutral Context envelope. It never receives or selects a Skill;
``routes.json`` owns the independent page-to-Skill mapping.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any

ASSISTANT_CONTEXT_ROOT = os.path.dirname(os.path.abspath(__file__))
SUPPORT_ROOT = os.path.join(ASSISTANT_CONTEXT_ROOT, "resolvers")
SHARED_SCRIPTS_ROOT = os.path.join(
    ASSISTANT_CONTEXT_ROOT,
    "..",
    "skills",
    "shared",
    "scripts",
)
REQUEST_SCRIPTS_ROOT = os.path.join(
    ASSISTANT_CONTEXT_ROOT,
    "..",
    "skills",
    "request",
    "scripts",
)
APPROVAL_SCRIPTS_ROOT = os.path.join(
    ASSISTANT_CONTEXT_ROOT,
    "..",
    "skills",
    "approval",
    "scripts",
)
RESOURCE_SCRIPTS_ROOT = os.path.join(
    ASSISTANT_CONTEXT_ROOT,
    "..",
    "skills",
    "resource",
    "scripts",
)
ALARM_SCRIPTS_ROOT = os.path.join(ASSISTANT_CONTEXT_ROOT, "..", "skills", "alarm", "scripts")
COST_SCRIPTS_ROOT = os.path.join(
    ASSISTANT_CONTEXT_ROOT, "..", "skills", "cost-optimization", "scripts"
)
_LOCAL_IMPORT_NAMES = (
    "_provider_bootstrap",
    "_alarm_object_actions",
    "_approval_object_actions",
    "_atlasclaw_adapter",
    "_context_resolver_common",
    "_cost_object_actions",
    "_object_actions_common",
    "_request_object_actions",
    "_resource_object_actions",
)
_MISSING_MODULE = object()
_original_sys_path = list(sys.path)
_previous_local_modules = {
    name: sys.modules.pop(name, _MISSING_MODULE) for name in _LOCAL_IMPORT_NAMES
}
try:
    sys.path[:0] = [
        os.path.abspath(COST_SCRIPTS_ROOT),
        os.path.abspath(ALARM_SCRIPTS_ROOT),
        os.path.abspath(RESOURCE_SCRIPTS_ROOT),
        os.path.abspath(APPROVAL_SCRIPTS_ROOT),
        os.path.abspath(REQUEST_SCRIPTS_ROOT),
        os.path.abspath(SHARED_SCRIPTS_ROOT),
        os.path.abspath(SUPPORT_ROOT),
    ]
    from _context_resolver_common import (  # noqa: E402
        CATALOG_ENTITY_CLASS,
        RESOURCE_ENTITY_CLASS,
        ContextReader,
        SmartCmpError,
        exact_catalog_id,
        exact_request_id,
        exact_uuid,
        load_context_reader_from_context,
        success_object,
        text,
    )
    from _approval_object_actions import build_approval_object_actions  # noqa: E402
    from _request_object_actions import (  # noqa: E402
        build_catalog_object_actions,
        build_request_object_actions,
    )
    from _resource_object_actions import build_resource_object_actions  # noqa: E402
    from _alarm_object_actions import build_alert_object_actions  # noqa: E402
    from _cost_object_actions import build_cost_object_actions  # noqa: E402
finally:
    sys.path[:] = _original_sys_path
    for _module_name, _previous_module in _previous_local_modules.items():
        if _previous_module is _MISSING_MODULE:
            sys.modules.pop(_module_name, None)
        else:
            sys.modules[_module_name] = _previous_module


_APPLICATION_TYPE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_APPROVAL_TYPE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_OBJECT_PARAMETER_NAMES: dict[str, frozenset[str]] = {
    "alarm_alert": frozenset(("alert_id",)),
    "blueprint_component": frozenset(("component_id",)),
    "cost_optimization_recommendation": frozenset(("recommendation_id",)),
    "approval_request": frozenset(("approval_type", "approval_id")),
    "catalog": frozenset(("catalog_id",)),
    "form_definition": frozenset(("form_id",)),
    "optimization_policy": frozenset(("policy_id",)),
    "request": frozenset(("application_type", "request_id")),
    "resource": frozenset(("resource_id",)),
    "script_definition": frozenset(("script_id",)),
    "virtual_machine": frozenset(("resource_id",)),
}


async def _resolve_form_definition(
    route_parameters: dict[str, Any], *, reader: ContextReader
) -> dict[str, Any]:
    """Resolve one form editor page to its exact saved form definition."""
    form_id = exact_uuid(route_parameters.get("form_id"))
    if not form_id:
        return _failure("invalid_form_reference")
    try:
        form = await reader.read_form_definition(form_id)
    except (SmartCmpError, TypeError, ValueError):
        return _failure("provider_unavailable")
    if not isinstance(form, dict) or exact_uuid(form.get("id")) != form_id:
        return _failure("form_id_mismatch")
    return success_object(
        object_type="form_definition",
        object_id=form_id,
        name=text(form.get("name")) or form_id,
        state="enabled" if form.get("enabled") is True else "disabled",
        attributes={
            "description": text(form.get("description")),
            "build_in": bool(form.get("buildIn")),
        },
        object_actions=[],
    )


async def _resolve_script_definition(
    route_parameters: dict[str, Any], *, reader: ContextReader
) -> dict[str, Any]:
    """Resolve one script editor page to its exact saved script definition."""
    script_id = exact_uuid(route_parameters.get("script_id"))
    if not script_id:
        return _failure("invalid_script_reference")
    try:
        script = await reader.read_script_definition(script_id)
    except (SmartCmpError, TypeError, ValueError):
        return _failure("provider_unavailable")
    if not isinstance(script, dict) or exact_uuid(script.get("id")) != script_id:
        return _failure("script_id_mismatch")
    return success_object(
        object_type="script_definition",
        object_id=script_id,
        name=text(script.get("alias") or script.get("name")) or script_id,
        state=text(script.get("state")).lower(),
        attributes={
            "script_name": text(script.get("name")),
            "script_type": text(script.get("type")),
            "published": bool(script.get("published")),
        },
        object_actions=[],
    )


async def _resolve_optimization_policy(
    route_parameters: dict[str, Any], *, reader: ContextReader
) -> dict[str, Any]:
    """Resolve one cost-optimization policy editor page to its exact policy."""
    policy_id = exact_uuid(route_parameters.get("policy_id"))
    if not policy_id:
        return _failure("invalid_policy_reference")
    try:
        policy = await reader.read_optimization_policy(policy_id)
    except (SmartCmpError, TypeError, ValueError):
        return _failure("provider_unavailable")
    if not isinstance(policy, dict) or exact_uuid(policy.get("id")) != policy_id:
        return _failure("policy_id_mismatch")
    category = text(policy.get("category")).upper()
    if category != "COST-OPTIMIZATION" and not category.startswith(
        "COST-OPTIMIZATION."
    ):
        return _failure("policy_category_mismatch")
    policy_configs = policy.get("policyConfigs")
    first_config = (
        policy_configs[0]
        if isinstance(policy_configs, list)
        and policy_configs
        and isinstance(policy_configs[0], dict)
        else {}
    )
    return success_object(
        object_type="optimization_policy",
        object_id=policy_id,
        name=text(policy.get("name")) or policy_id,
        state=text(first_config.get("status")).lower(),
        attributes={
            "category": category,
            "policy_type": text(policy.get("type")),
            "resource_type_count": len(policy.get("resourceType"))
            if isinstance(policy.get("resourceType"), list)
            else 0,
        },
        object_actions=[],
    )


async def _resolve_blueprint_component(
    route_parameters: dict[str, Any], *, reader: ContextReader
) -> dict[str, Any]:
    """Resolve one component editor page to its exact saved component."""
    component_id = exact_uuid(route_parameters.get("component_id"))
    if not component_id:
        return _failure("invalid_component_reference")
    try:
        component = await reader.read_component_definition(component_id)
    except (SmartCmpError, TypeError, ValueError):
        return _failure("provider_unavailable")
    if not isinstance(component, dict) or exact_uuid(component.get("id")) != component_id:
        return _failure("component_id_mismatch")
    model = component.get("model")
    model = model if isinstance(model, dict) else {}
    blueprint_files = model.get("blueprintFiles")
    return success_object(
        object_type="blueprint_component",
        object_id=component_id,
        name=text(component.get("name") or component.get("key")) or component_id,
        state="published" if component.get("published") is True else "draft",
        attributes={
            "resource_type": text(component.get("resourceType")),
            "parent_type": text(component.get("parentType")),
            "file_count": len(blueprint_files) if isinstance(blueprint_files, list) else 0,
            "system_component": bool(component.get("systemComponent")),
        },
        object_actions=[],
    )


async def _resolve_alert(
    route_parameters: dict[str, Any], *, reader: ContextReader
) -> dict[str, Any]:
    """Resolve one exact alarm alert with state-aware actions."""
    alert_id = exact_uuid(route_parameters.get("alert_id"))
    if not alert_id:
        return _failure("invalid_alert_reference")
    try:
        alert = await reader.read_alert(alert_id)
    except (SmartCmpError, TypeError, ValueError):
        return _failure("provider_unavailable")
    if not isinstance(alert, dict) or exact_uuid(alert.get("id")) != alert_id:
        return _failure("alert_id_mismatch")
    return success_object(
        object_type="alarm_alert",
        object_id=alert_id,
        name=text(alert.get("alarmPolicyName") or alert.get("alarmActivityName") or alert.get("subject")) or alert_id,
        state=text(alert.get("status")).lower(),
        attributes={
            "severity": alert.get("level", ""),
            "trigger_at": text(alert.get("triggerAt")),
            "last_trigger_at": text(alert.get("lastTriggerAt")),
            "trigger_count": alert.get("triggerCount", ""),
            "resource_id": text(alert.get("nodeInstanceId") or alert.get("entityInstanceId")),
            "resource_name": text(alert.get("resourceExternalName") or alert.get("entityInstanceName")),
            "metric_name": text(alert.get("metricName")),
            "subject": text(alert.get("subject")),
        },
        object_actions=build_alert_object_actions(alert),
    )


async def _resolve_cost_recommendation(
    route_parameters: dict[str, Any], *, reader: ContextReader
) -> dict[str, Any]:
    """Resolve one exact cost recommendation with remediation-aware actions."""
    recommendation_id = exact_uuid(route_parameters.get("recommendation_id"))
    if not recommendation_id:
        return _failure("invalid_recommendation_reference")
    try:
        recommendation = await reader.read_cost_recommendation(recommendation_id)
    except (SmartCmpError, TypeError, ValueError):
        return _failure("provider_unavailable")
    if not isinstance(recommendation, dict) or exact_uuid(recommendation.get("id")) != recommendation_id:
        return _failure("recommendation_id_mismatch")
    task_definition = recommendation.get("taskDefinition")
    task_definition = task_definition if isinstance(task_definition, dict) else {}
    action_source = dict(recommendation)
    action_source["taskDefinitionName"] = text(task_definition.get("name"))
    return success_object(
        object_type="cost_optimization_recommendation",
        object_id=recommendation_id,
        name=text(recommendation.get("policyName") or recommendation.get("resourceName")) or recommendation_id,
        state=text(recommendation.get("status")).lower(),
        attributes={
            "severity": text(recommendation.get("severity")),
            "category": text(recommendation.get("category")),
            "resource_id": text(recommendation.get("resourceId")),
            "resource_name": text(recommendation.get("resourceName")),
            "resource_type": text(recommendation.get("resourceType") or recommendation.get("componentType")),
            "monthly_cost": recommendation.get("monthlyCost", ""),
            "monthly_saving": recommendation.get("monthlySaving", ""),
            "saving_operation_type": text(recommendation.get("savingOperationType")),
            "fix_type": text(recommendation.get("fixType")),
            "task_instance_id": text(recommendation.get("taskInstanceId")),
        },
        object_actions=build_cost_object_actions(action_source),
    )


def _failure(reason: str) -> dict[str, object]:
    return {"success": False, "reason": reason}


def _exact_application_type(value: Any) -> str:
    normalized = str(value or "").strip()
    return normalized if _APPLICATION_TYPE.fullmatch(normalized) else ""


async def _pending_items(
    workflow_id: str,
    *,
    reader: ContextReader,
) -> list[dict[str, Any]]:
    normalized_id = exact_request_id(workflow_id)
    if not normalized_id:
        return []
    return list(await reader.list_current_pending_approvals(normalized_id))


def _matches_pending_row(
    item: dict[str, Any],
    *,
    approval_type: str,
    approval_id: str,
    generic_request_id: str,
    workflow_id: str,
) -> bool:
    extensions = item.get("exts")
    extensions = extensions if isinstance(extensions, dict) else {}
    # currentActivity.id is the workflow Activity UUID, not Approval.id.
    return (
        exact_uuid(item.get("id")) == generic_request_id
        and exact_request_id(item.get("workflowId")) == workflow_id
        and exact_uuid(extensions.get("approval_id")) == approval_id
        and text(extensions.get("approval_type")).upper() == approval_type
        and text(extensions.get("approval_state")).upper() == "PENDING"
    )


async def _resolve_pending_approval(
    route_parameters: dict[str, Any],
    *,
    reader: ContextReader,
) -> dict[str, Any]:
    approval_type = str(route_parameters.get("approval_type") or "").strip().upper()
    approval_id = exact_uuid(route_parameters.get("approval_id"))
    if not _APPROVAL_TYPE.fullmatch(approval_type) or not approval_id:
        return _failure("invalid_approval_reference")

    try:
        approval = await reader.read_approval(approval_id)
        if not isinstance(approval, dict):
            return _failure("not_found")
        if exact_uuid(approval.get("id")) != approval_id:
            return _failure("approval_id_mismatch")
        if text(approval.get("state")).upper() != "PENDING":
            return _failure("not_pending")
        if text(approval.get("type")).upper() != approval_type:
            return _failure("approval_type_mismatch")

        generic_request_id = exact_uuid(approval.get("genericRequestId"))
        workflow_id = exact_request_id(approval.get("workflowId"))
        if not generic_request_id or not workflow_id:
            return _failure("request_reference_unavailable")

        row = next(
            (
                item
                for item in await _pending_items(workflow_id, reader=reader)
                if _matches_pending_row(
                    item,
                    approval_type=approval_type,
                    approval_id=approval_id,
                    generic_request_id=generic_request_id,
                    workflow_id=workflow_id,
                )
            ),
            None,
        )
        if row is None:
            return _failure("not_in_current_user_pending_queue")
    except (SmartCmpError, TypeError, ValueError):
        return _failure("provider_unavailable")

    return success_object(
        object_type="approval_request",
        object_id=workflow_id,
        name=text(approval.get("name")) or text(row.get("name")) or workflow_id,
        state="pending",
        attributes={"approval_type": approval_type},
        object_actions=build_approval_object_actions(
            reader.ui_base_url,
            row,
            include_detail_actions=True,
        ),
    )


async def _resolve_catalog(
    route_parameters: dict[str, Any],
    *,
    reader: ContextReader,
) -> dict[str, Any]:
    catalog_id = exact_catalog_id(str(route_parameters.get("catalog_id") or ""))
    if not catalog_id:
        return _failure("invalid_catalog_id")
    try:
        if not await reader.has_instance_permission(
            CATALOG_ENTITY_CLASS,
            catalog_id,
            "READ",
        ):
            return _failure("permission_denied")
        catalog = await reader.read_catalog(catalog_id)
        if not isinstance(catalog, dict) or text(catalog.get("id")) != catalog_id:
            return _failure("catalog_id_mismatch")
    except (SmartCmpError, TypeError, ValueError):
        return _failure("provider_unavailable")

    return success_object(
        object_type="catalog",
        object_id=catalog_id,
        name=text(catalog.get("name")) or catalog_id,
        state=text(catalog.get("status")).lower(),
        attributes={
            "description": text(catalog.get("description")),
            "source_key": text(catalog.get("sourceKey")),
            "category": text(catalog.get("category") or catalog.get("serviceCategory")),
            "instructions": text(catalog.get("instructions")),
        },
        object_actions=build_catalog_object_actions(
            reader.ui_base_url,
            catalog,
        ),
    )


async def _resolve_request(
    route_parameters: dict[str, Any],
    *,
    reader: ContextReader,
) -> dict[str, Any]:
    application_type = _exact_application_type(route_parameters.get("application_type"))
    request_id = exact_uuid(route_parameters.get("request_id"))
    if not application_type:
        return _failure("invalid_application_type")
    if not request_id:
        return _failure("invalid_request_id")

    try:
        request = await reader.read_request(request_id)
    except (SmartCmpError, TypeError, ValueError):
        return _failure("provider_unavailable")
    if not isinstance(request, dict) or exact_uuid(request.get("id")) != request_id:
        return _failure("request_id_mismatch")
    if text(request.get("type")) != application_type:
        return _failure("application_type_mismatch")

    workflow_id = exact_request_id(request.get("workflowId"))
    if not workflow_id:
        return _failure("invalid_workflow_id")
    return success_object(
        object_type="request",
        object_id=workflow_id,
        name=text(request.get("name") or request.get("requestName")) or workflow_id,
        state=text(request.get("state")).lower(),
        attributes={
            "application_type": application_type,
            "catalog_name": text(request.get("catalogName")),
        },
        object_actions=build_request_object_actions(reader.ui_base_url, request),
    )


def _is_virtual_machine(resource: dict[str, Any]) -> bool:
    component_type = text(resource.get("componentType")).lower()
    resource_type = text(resource.get("resourceType")).lower()
    return ".machine.instance." in component_type or resource_type.endswith(".nodes.server")


async def _resolve_resource(
    route_parameters: dict[str, Any],
    *,
    expected_kind: str,
    reader: ContextReader,
) -> dict[str, Any]:
    resource_id = exact_uuid(route_parameters.get("resource_id"))
    if not resource_id:
        return _failure("invalid_resource_reference")
    try:
        if not await reader.has_instance_permission(
            RESOURCE_ENTITY_CLASS,
            resource_id,
            "READ",
        ):
            return _failure("permission_denied")
        resource = await reader.read_resource(resource_id)
        if not isinstance(resource, dict) or exact_uuid(resource.get("id")) != resource_id:
            return _failure("resource_id_mismatch")
    except (SmartCmpError, TypeError, ValueError):
        return _failure("provider_unavailable")
    if expected_kind == "virtual_machine" and not _is_virtual_machine(resource):
        return _failure("resource_category_mismatch")

    return success_object(
        object_type=expected_kind,
        object_id=resource_id,
        name=text(resource.get("name")) or resource_id,
        state=text(resource.get("status") or resource.get("state")).lower(),
        attributes={
            "component_type": text(resource.get("componentType")),
            "resource_type": text(resource.get("resourceType")),
            "category": text(resource.get("category")),
        },
        object_actions=build_resource_object_actions(
            reader.ui_base_url,
            resource_id,
            category="virtual-machines" if expected_kind == "virtual_machine" else "cloud-resource",
            resource_name=text(resource.get("name")),
            include_operations_action=True,
        ),
    )


async def resolve_page_context(
    route_id: str,
    path: str,
    route_parameters: dict[str, Any],
    page_type: str,
    object_type: str,
    *,
    reader: ContextReader,
) -> dict[str, Any]:
    """Resolve one server-matched page without receiving or branching on a Skill.

    Args:
        route_id: Provider route identifier selected by AtlasClaw.
        path: Normalized Host path that matched the route.
        route_parameters: Server-extracted path parameters.
        page_type: Page type declared by the matched route.
        object_type: Object type declared by the matched route.
        reader: SmartCMP Provider read boundary; focused tests may supply a local fake.

    Returns:
        A strict success/object envelope or a fail-closed reason. No Provider
        response body or authentication material is returned.
    """
    # AtlasClaw already matched route_id/path/page_type against routes.json. They
    # remain in the fixed protocol for diagnostics, but deliberately do not
    # select Provider behavior or duplicate the route table here.
    if (
        not str(route_id or "").strip()
        or not str(path or "").strip()
        or not str(page_type or "").strip()
        or not isinstance(route_parameters, dict)
    ):
        return _failure("invalid_route_contract")
    normalized_object_type = str(object_type or "").strip()
    parameter_names = _OBJECT_PARAMETER_NAMES.get(normalized_object_type)
    if parameter_names is None:
        return _failure("unsupported_object_type")
    # Exact parameter names keep the manifest as the only URL contract. The
    # resolver adapts an object type and cannot accept client-added query data.
    if set(route_parameters) != parameter_names:
        return _failure("invalid_route_contract")

    if normalized_object_type == "approval_request":
        return await _resolve_pending_approval(route_parameters, reader=reader)
    if normalized_object_type == "form_definition":
        return await _resolve_form_definition(route_parameters, reader=reader)
    if normalized_object_type == "script_definition":
        return await _resolve_script_definition(route_parameters, reader=reader)
    if normalized_object_type == "optimization_policy":
        return await _resolve_optimization_policy(route_parameters, reader=reader)
    if normalized_object_type == "blueprint_component":
        return await _resolve_blueprint_component(route_parameters, reader=reader)
    if normalized_object_type == "catalog":
        return await _resolve_catalog(route_parameters, reader=reader)
    if normalized_object_type == "request":
        return await _resolve_request(route_parameters, reader=reader)
    if normalized_object_type == "alarm_alert":
        return await _resolve_alert(route_parameters, reader=reader)
    if normalized_object_type == "cost_optimization_recommendation":
        return await _resolve_cost_recommendation(route_parameters, reader=reader)
    return await _resolve_resource(
        route_parameters,
        expected_kind=normalized_object_type,
        reader=reader,
    )


async def resolve_context(
    ctx: Any,
    route_id: str,
    path: str,
    route_parameters: dict[str, Any],
    page_type: str,
    object_type: str,
) -> dict[str, Any]:
    """Resolve one Host page with the request-scoped SmartCMP browser identity.

    Args:
        ctx: AtlasClaw execution context for the current embedded Host request.
        route_id: Provider route identifier selected by AtlasClaw.
        path: Normalized Host path that matched the route.
        route_parameters: Server-extracted path parameters.
        page_type: Page type declared by the matched route.
        object_type: Object type declared by the matched route.

    Returns:
        A strict Provider context envelope for AtlasClaw snapshot validation.
    """

    reader = await load_context_reader_from_context(ctx)
    async with reader:
        return await resolve_page_context(
            route_id,
            path,
            route_parameters,
            page_type,
            object_type,
            reader=reader,
        )
