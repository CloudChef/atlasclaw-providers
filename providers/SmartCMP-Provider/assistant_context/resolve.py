# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Resolve SmartCMP Host pages through one Provider-level Context entrypoint.

AtlasClaw invokes this script with a server-owned route contract. The resolver
validates that contract, reads only the current user's page object, and returns
the provider-neutral Context envelope. It never receives or selects a Skill;
``routes.json`` owns the independent page-to-Skill mapping.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

import requests


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
sys.path.insert(0, SUPPORT_ROOT)
sys.path.insert(0, os.path.abspath(SHARED_SCRIPTS_ROOT))
sys.path.insert(0, os.path.abspath(REQUEST_SCRIPTS_ROOT))
sys.path.insert(0, os.path.abspath(APPROVAL_SCRIPTS_ROOT))
sys.path.insert(0, os.path.abspath(RESOURCE_SCRIPTS_ROOT))
sys.path.insert(0, os.path.abspath(ALARM_SCRIPTS_ROOT))
sys.path.insert(0, os.path.abspath(COST_SCRIPTS_ROOT))

from _context_resolver_common import (  # noqa: E402
    BASE_URL,
    CATALOG_ENTITY_CLASS,
    RESOURCE_ENTITY_CLASS,
    RequestGet,
    exact_catalog_id,
    exact_request_id,
    exact_uuid,
    get_json,
    has_instance_permission,
    success_object,
    text,
    write_result,
)
from _approval_object_actions import build_approval_object_actions  # noqa: E402
from _request_object_actions import (  # noqa: E402
    build_catalog_object_actions,
    build_request_object_actions,
)
from _resource_object_actions import build_resource_object_actions  # noqa: E402
from _alarm_object_actions import build_alert_object_actions  # noqa: E402
from _cost_object_actions import build_cost_object_actions  # noqa: E402


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


def _resolve_form_definition(
    route_parameters: dict[str, Any], *, request_get: RequestGet
) -> dict[str, Any]:
    """Resolve one form editor page to its exact saved form definition."""
    form_id = exact_uuid(route_parameters.get("form_id"))
    if not form_id:
        return _failure("invalid_form_reference")
    try:
        form = get_json(f"forms/{form_id}", request_get=request_get)
    except (requests.exceptions.RequestException, TypeError, ValueError):
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


def _resolve_script_definition(
    route_parameters: dict[str, Any], *, request_get: RequestGet
) -> dict[str, Any]:
    """Resolve one script editor page to its exact saved script definition."""
    script_id = exact_uuid(route_parameters.get("script_id"))
    if not script_id:
        return _failure("invalid_script_reference")
    try:
        script = get_json(f"scripts/{script_id}", request_get=request_get)
    except (requests.exceptions.RequestException, TypeError, ValueError):
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


def _resolve_optimization_policy(
    route_parameters: dict[str, Any], *, request_get: RequestGet
) -> dict[str, Any]:
    """Resolve one cost-optimization policy editor page to its exact policy."""
    policy_id = exact_uuid(route_parameters.get("policy_id"))
    if not policy_id:
        return _failure("invalid_policy_reference")
    try:
        policy = get_json(f"compliance-policies/{policy_id}", request_get=request_get)
    except (requests.exceptions.RequestException, TypeError, ValueError):
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


def _resolve_blueprint_component(
    route_parameters: dict[str, Any], *, request_get: RequestGet
) -> dict[str, Any]:
    """Resolve one component editor page to its exact saved component."""
    component_id = exact_uuid(route_parameters.get("component_id"))
    if not component_id:
        return _failure("invalid_component_reference")
    try:
        component = get_json(f"components/{component_id}", request_get=request_get)
    except (requests.exceptions.RequestException, TypeError, ValueError):
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


def _resolve_alert(
    route_parameters: dict[str, Any], *, request_get: RequestGet
) -> dict[str, Any]:
    """Resolve one exact alarm alert with state-aware actions."""
    alert_id = exact_uuid(route_parameters.get("alert_id"))
    if not alert_id:
        return _failure("invalid_alert_reference")
    try:
        alert = get_json(f"alarm-alert/{alert_id}", request_get=request_get)
    except (requests.exceptions.RequestException, TypeError, ValueError):
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


def _resolve_cost_recommendation(
    route_parameters: dict[str, Any], *, request_get: RequestGet
) -> dict[str, Any]:
    """Resolve one exact cost recommendation with remediation-aware actions."""
    recommendation_id = exact_uuid(route_parameters.get("recommendation_id"))
    if not recommendation_id:
        return _failure("invalid_recommendation_reference")
    try:
        recommendation = get_json(
            f"compliance-policies/violations/{recommendation_id}",
            request_get=request_get,
        )
    except (requests.exceptions.RequestException, TypeError, ValueError):
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


def _pending_items(
    workflow_id: str,
    *,
    request_get: RequestGet,
) -> list[dict[str, Any]]:
    normalized_id = exact_request_id(workflow_id)
    if not normalized_id:
        return []
    payload = get_json(
        "generic-request/current-activity-approval",
        request_get=request_get,
        params={
            "page": 1,
            "size": 100,
            "stage": "pending",
            "states": "APPROVAL_PENDING",
            "sort": "updatedDate,desc",
            "searchValues": normalized_id,
        },
    )
    content = payload.get("content") if isinstance(payload, dict) else None
    if not isinstance(content, list):
        return []
    return [item for item in content if isinstance(item, dict)]


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


def _resolve_pending_approval(
    route_parameters: dict[str, Any],
    *,
    request_get: RequestGet,
) -> dict[str, Any]:
    approval_type = str(route_parameters.get("approval_type") or "").strip().upper()
    approval_id = exact_uuid(route_parameters.get("approval_id"))
    if not _APPROVAL_TYPE.fullmatch(approval_type) or not approval_id:
        return _failure("invalid_approval_reference")

    try:
        approval = get_json(f"approval/{approval_id}", request_get=request_get)
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
                for item in _pending_items(workflow_id, request_get=request_get)
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
    except (requests.exceptions.RequestException, TypeError, ValueError):
        return _failure("provider_unavailable")

    return success_object(
        object_type="approval_request",
        object_id=workflow_id,
        name=text(approval.get("name")) or text(row.get("name")) or workflow_id,
        state="pending",
        attributes={"approval_type": approval_type},
        object_actions=build_approval_object_actions(
            BASE_URL,
            row,
            include_detail_actions=True,
        ),
    )


def _resolve_catalog(
    route_parameters: dict[str, Any],
    *,
    request_get: RequestGet,
) -> dict[str, Any]:
    catalog_id = exact_catalog_id(str(route_parameters.get("catalog_id") or ""))
    if not catalog_id:
        return _failure("invalid_catalog_id")
    try:
        if not has_instance_permission(
            CATALOG_ENTITY_CLASS,
            catalog_id,
            "READ",
            request_get=request_get,
        ):
            return _failure("permission_denied")
        catalog = get_json(f"catalogs/{catalog_id}", request_get=request_get)
        if not isinstance(catalog, dict) or text(catalog.get("id")) != catalog_id:
            return _failure("catalog_id_mismatch")
    except (requests.exceptions.RequestException, TypeError, ValueError):
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
            BASE_URL,
            catalog,
        ),
    )


def _resolve_request(
    route_parameters: dict[str, Any],
    *,
    request_get: RequestGet,
) -> dict[str, Any]:
    application_type = _exact_application_type(route_parameters.get("application_type"))
    request_id = exact_uuid(route_parameters.get("request_id"))
    if not application_type:
        return _failure("invalid_application_type")
    if not request_id:
        return _failure("invalid_request_id")

    try:
        request = get_json(f"generic-request/{request_id}", request_get=request_get)
    except (requests.exceptions.RequestException, TypeError, ValueError):
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
        object_actions=build_request_object_actions(BASE_URL, request),
    )


def _is_virtual_machine(resource: dict[str, Any]) -> bool:
    component_type = text(resource.get("componentType")).lower()
    resource_type = text(resource.get("resourceType")).lower()
    return ".machine.instance." in component_type or resource_type.endswith(".nodes.server")


def _resolve_resource(
    route_parameters: dict[str, Any],
    *,
    expected_kind: str,
    request_get: RequestGet,
) -> dict[str, Any]:
    resource_id = exact_uuid(route_parameters.get("resource_id"))
    if not resource_id:
        return _failure("invalid_resource_reference")
    try:
        if not has_instance_permission(
            RESOURCE_ENTITY_CLASS,
            resource_id,
            "READ",
            request_get=request_get,
        ):
            return _failure("permission_denied")
        resource = get_json(f"nodes/{resource_id}", request_get=request_get)
        if not isinstance(resource, dict) or exact_uuid(resource.get("id")) != resource_id:
            return _failure("resource_id_mismatch")
    except (requests.exceptions.RequestException, TypeError, ValueError):
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
            BASE_URL,
            resource_id,
            category="virtual-machines" if expected_kind == "virtual_machine" else "cloud-resource",
            resource_name=text(resource.get("name")),
            include_operations_action=True,
        ),
    )


def resolve_page_context(
    route_id: str,
    path: str,
    route_parameters: dict[str, Any],
    page_type: str,
    object_type: str,
    *,
    request_get: RequestGet = requests.get,
) -> dict[str, Any]:
    """Resolve one server-matched page without receiving or branching on a Skill.

    Args:
        route_id: Provider route identifier selected by AtlasClaw.
        path: Normalized Host path that matched the route.
        route_parameters: Server-extracted path parameters.
        page_type: Page type declared by the matched route.
        object_type: Object type declared by the matched route.
        request_get: Injectable GET transport used only by focused Provider tests.

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
        return _resolve_pending_approval(route_parameters, request_get=request_get)
    if normalized_object_type == "form_definition":
        return _resolve_form_definition(route_parameters, request_get=request_get)
    if normalized_object_type == "script_definition":
        return _resolve_script_definition(route_parameters, request_get=request_get)
    if normalized_object_type == "optimization_policy":
        return _resolve_optimization_policy(route_parameters, request_get=request_get)
    if normalized_object_type == "blueprint_component":
        return _resolve_blueprint_component(route_parameters, request_get=request_get)
    if normalized_object_type == "catalog":
        return _resolve_catalog(route_parameters, request_get=request_get)
    if normalized_object_type == "request":
        return _resolve_request(route_parameters, request_get=request_get)
    if normalized_object_type == "alarm_alert":
        return _resolve_alert(route_parameters, request_get=request_get)
    if normalized_object_type == "cost_optimization_recommendation":
        return _resolve_cost_recommendation(route_parameters, request_get=request_get)
    return _resolve_resource(
        route_parameters,
        expected_kind=normalized_object_type,
        request_get=request_get,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse AtlasClaw's fixed Provider-level Context resolver protocol."""
    parser = argparse.ArgumentParser(description="Resolve one SmartCMP page Context.")
    parser.add_argument("route_id")
    parser.add_argument("path")
    parser.add_argument("route_parameters")
    parser.add_argument("page_type")
    parser.add_argument("object_type")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Resolve one page and print exactly one JSON envelope for AtlasClaw."""
    args = parse_args(argv)
    try:
        route_parameters = json.loads(args.route_parameters)
    except (json.JSONDecodeError, TypeError):
        write_result(_failure("invalid_route_parameters"))
        return 0
    if not isinstance(route_parameters, dict):
        write_result(_failure("invalid_route_parameters"))
        return 0
    write_result(
        resolve_page_context(
            args.route_id,
            args.path,
            route_parameters,
            args.page_type,
            args.object_type,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
