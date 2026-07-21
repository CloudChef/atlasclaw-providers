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
sys.path.insert(0, SUPPORT_ROOT)
sys.path.insert(0, os.path.abspath(SHARED_SCRIPTS_ROOT))
sys.path.insert(0, os.path.abspath(REQUEST_SCRIPTS_ROOT))
sys.path.insert(0, os.path.abspath(APPROVAL_SCRIPTS_ROOT))
sys.path.insert(0, os.path.abspath(RESOURCE_SCRIPTS_ROOT))

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


_APPLICATION_TYPE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_APPROVAL_TYPE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_OBJECT_PARAMETER_NAMES: dict[str, frozenset[str]] = {
    "approval_request": frozenset(("approval_type", "approval_id")),
    "catalog": frozenset(("catalog_id",)),
    "request": frozenset(("application_type", "request_id")),
    "resource": frozenset(("resource_id",)),
    "virtual_machine": frozenset(("resource_id",)),
}


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
    if normalized_object_type == "catalog":
        return _resolve_catalog(route_parameters, request_get=request_get)
    if normalized_object_type == "request":
        return _resolve_request(route_parameters, request_get=request_get)
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
