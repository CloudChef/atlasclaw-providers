# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Focused tests for SmartCMP's single Provider-level Context resolver."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import requests


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
RESOLVER_ROOT = PROVIDER_ROOT / "assistant_context" / "resolvers"
RESOLVER_PATH = PROVIDER_ROOT / "assistant_context" / "resolve.py"
APPROVAL_ID = "e0b48865-9b12-4f83-a494-745534532995"
GENERIC_REQUEST_ID = "a1111111-3333-4333-8333-333333333333"
WORKFLOW_ID = "RES20260719000004"
RESOURCE_ID = "7d64abdf-1111-4111-8111-111111111111"
ALERT_ID = "bccacc1a-651c-4d11-b8ea-a58e24e8f32b"
RECOMMENDATION_ID = "7c6196b1-5623-4d85-896d-e74b4f9042cd"


class _Response:
    def __init__(self, payload, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        return self.payload


def _configure(monkeypatch, *, cookies=None) -> None:
    monkeypatch.setenv("ATLASCLAW_PROVIDER_INSTANCE", "default")
    monkeypatch.setenv(
        "ATLASCLAW_PROVIDER_CONFIG",
        json.dumps(
            {"smartcmp": {"default": {"base_url": "https://cmp.example.com"}}}
        ),
    )
    monkeypatch.setenv(
        "ATLASCLAW_COOKIES",
        json.dumps(
            {"CloudChef-Authenticate": "request-user-cookie"}
            if cookies is None
            else cookies
        ),
    )


def _load(monkeypatch):
    _configure(monkeypatch)
    original_path = list(sys.path)
    imported_names = (
        "_context_resolver_common",
        "_request_user_transport",
        "_object_actions_common",
        "_approval_object_actions",
        "_request_object_actions",
        "_resource_object_actions",
        "_alarm_object_actions",
        "_cost_object_actions",
    )
    previous_modules = {name: sys.modules.pop(name, None) for name in imported_names}
    try:
        sys.path.insert(0, str(RESOLVER_ROOT))
        spec = importlib.util.spec_from_file_location("smartcmp_page_context", RESOLVER_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path[:] = original_path
        for name in imported_names:
            sys.modules.pop(name, None)
            previous = previous_modules[name]
            if previous is not None:
                sys.modules[name] = previous


def _acl(entity_class: str, entity_id: str) -> list[dict]:
    return [
        {
            "entityClass": {"className": entity_class, "instanceId": entity_id},
            "permissions": [{"id": "READ"}],
        }
    ]


def test_resolver_import_never_auto_logs_in_with_configured_credentials(
    monkeypatch,
) -> None:
    """Request Cookie resolution must not import the credential-aware common module."""
    _configure(monkeypatch)
    provider_config = {
        "smartcmp": {
            "default": {
                "base_url": "https://cmp.example.com",
                "auth_type": "credential",
                "username": "shared-user",
                "password": "shared-password",
            }
        }
    }
    monkeypatch.setenv("ATLASCLAW_PROVIDER_CONFIG", json.dumps(provider_config))
    login_calls: list[tuple[tuple, dict]] = []

    def record_login(*args, **kwargs):
        login_calls.append((args, kwargs))
        raise AssertionError("Context resolver must not auto-login")

    monkeypatch.setattr(requests, "post", record_login)

    _load(monkeypatch)

    assert login_calls == []


@pytest.mark.parametrize(
    ("state", "expected_actions"),
    [
        ("PUBLISHED", ["open_detail", "request"]),
        ("STAGING", ["open_detail"]),
        ("RETIRED", ["open_detail"]),
        ("", ["open_detail"]),
    ],
)
def test_catalog_request_action_fails_closed_for_unpublished_states(
    monkeypatch,
    state: str,
    expected_actions: list[str],
) -> None:
    resolver = _load(monkeypatch)
    actions = resolver.build_catalog_object_actions(
        "https://cmp.example.com/platform-api",
        {"id": "CATALOG-1", "name": "Catalog", "status": state},
    )
    assert [action["action_id"] for action in actions] == expected_actions


def test_missing_request_cookie_fails_before_provider_io(monkeypatch) -> None:
    _configure(monkeypatch, cookies={})
    calls = 0

    def fail_http(*_args, **_kwargs):
        nonlocal calls
        calls += 1

    monkeypatch.setattr(requests, "get", fail_http)
    with pytest.raises(RuntimeError, match="request-scoped CloudChef-Authenticate"):
        path = RESOLVER_ROOT / "_context_resolver_common.py"
        spec = importlib.util.spec_from_file_location(
            "context_resolver_common_missing_cookie",
            path,
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    assert calls == 0


def test_pending_approval_resolves_exact_three_id_shape(monkeypatch) -> None:
    module = _load(monkeypatch)
    pending_row = {
        "id": GENERIC_REQUEST_ID,
        "workflowId": WORKFLOW_ID,
        "name": "Production VM",
        "exts": {
            "approval_id": APPROVAL_ID,
            "approval_type": "PROVISION_BP",
            "approval_state": "PENDING",
        },
    }

    def fake_get(url, **kwargs):
        if url.endswith(f"/approval/{APPROVAL_ID}"):
            return _Response(
                {
                    "id": APPROVAL_ID,
                    "state": "PENDING",
                    "type": "PROVISION_BP",
                    "genericRequestId": GENERIC_REQUEST_ID,
                    "workflowId": WORKFLOW_ID,
                    "name": "Production VM",
                }
            )
        assert url.endswith("/generic-request/current-activity-approval")
        assert kwargs["params"]["searchValues"] == WORKFLOW_ID
        return _Response({"content": [pending_row]})

    result = module.resolve_page_context(
        "pending-approval-detail",
        f"/main/new-application/pendingApproval/PROVISION_BP/{APPROVAL_ID}",
        {"approval_type": "PROVISION_BP", "approval_id": APPROVAL_ID},
        "approval-detail",
        "approval_request",
        request_get=fake_get,
    )
    assert result["success"] is True
    assert result["object"]["id"] == WORKFLOW_ID
    assert [action["action_id"] for action in result["object_actions"]] == [
        "open_detail",
        "analyze",
        "approve",
        "reject",
    ]


def test_alert_and_cost_context_return_state_aware_actions(monkeypatch) -> None:
    """The two new page objects expose only actions supported by live state."""
    module = _load(monkeypatch)

    def fake_get(url, **_kwargs):
        if url.endswith(f"/alarm-alert/{ALERT_ID}"):
            return _Response(
                {
                    "id": ALERT_ID,
                    "alarmPolicyName": "CPU high",
                    "status": "ALERT_FIRING",
                    "level": 2,
                    "resourceExternalName": "vm-01",
                }
            )
        assert url.endswith(f"/compliance-policies/violations/{RECOMMENDATION_ID}")
        return _Response(
            {
                "id": RECOMMENDATION_ID,
                "policyName": "Right-size VM",
                "status": "ACTIVED",
                "resourceId": RESOURCE_ID,
                "monthlySaving": 120,
                "fixType": "RESIZE",
            }
        )

    alert = module.resolve_page_context(
        "alarm-alert-detail",
        f"/main/alarm-activity-management/alarm-triggered/edit/{ALERT_ID}",
        {"alert_id": ALERT_ID},
        "alarm-alert-detail",
        "alarm_alert",
        request_get=fake_get,
    )
    assert alert["object"]["id"] == ALERT_ID
    assert [action["action_id"] for action in alert["object_actions"]] == [
        "analyze",
        "mute",
        "resolve",
    ]

    cost = module.resolve_page_context(
        "cost-optimization-detail",
        f"/main/measurement-billing/resource-usage-analysis/{RECOMMENDATION_ID}",
        {"recommendation_id": RECOMMENDATION_ID},
        "cost-optimization-detail",
        "cost_optimization_recommendation",
        request_get=fake_get,
    )
    assert cost["object"]["id"] == RECOMMENDATION_ID
    assert [action["action_id"] for action in cost["object_actions"]] == [
        "analyze",
        "remediate",
    ]
    assert cost["object_actions"][1]["requires_confirmation"] is True


def test_catalog_request_and_resource_resolvers_return_selected_display_fields(monkeypatch) -> None:
    resolver = _load(monkeypatch)
    catalog_id = "BUILD-IN-CATALOG-WINDOWS-VM"
    catalog = {
        "id": catalog_id,
        "name": "Windows VM",
        "description": "Catalog description",
        "sourceKey": "WINDOWS_VM",
        "status": "PUBLISHED",
        "inputData": {"password": "secret"},
    }

    def catalog_get(url, **kwargs):
        if url.endswith("/acl/queryCurrentUserPermissions"):
            return _Response(_acl(resolver.CATALOG_ENTITY_CLASS, catalog_id))
        return _Response(catalog)

    catalog_result = resolver.resolve_page_context(
        "catalog-request",
        f"/main/catalog-ui/request/{catalog_id}",
        {"catalog_id": catalog_id},
        "catalog-request",
        "catalog",
        request_get=catalog_get,
    )
    assert catalog_result["success"] is True
    assert "inputData" not in catalog_result["object"]["attributes"]
    assert [action["action_id"] for action in catalog_result["object_actions"]] == [
        "open_detail",
        "request",
    ]

    request = {
        "id": GENERIC_REQUEST_ID,
        "workflowId": WORKFLOW_ID,
        "type": "CLOUD_BLUEPRINT_SERVICE",
        "name": "My request",
        "state": "PENDING",
        "credential": "secret",
    }
    request_result = resolver.resolve_page_context(
        "request-detail",
        (
            "/main/new-process/myApplication/CLOUD_BLUEPRINT_SERVICE/"
            f"{GENERIC_REQUEST_ID}"
        ),
        {
            "application_type": "CLOUD_BLUEPRINT_SERVICE",
            "request_id": GENERIC_REQUEST_ID,
        },
        "request-detail",
        "request",
        request_get=lambda *_args, **_kwargs: _Response(request),
    )
    assert request_result["success"] is True
    assert "credential" not in request_result["object"]["attributes"]
    assert [action["action_id"] for action in request_result["object_actions"]] == [
        "open_detail",
    ]

    def resource_get(url, **kwargs):
        if url.endswith("/acl/queryCurrentUserPermissions"):
            return _Response(_acl(resolver.RESOURCE_ENTITY_CLASS, RESOURCE_ID))
        return _Response(
            {
                "id": RESOURCE_ID,
                "name": "MyVM",
                "status": "RUNNING",
                "componentType": "resource.iaas.machine.instance.vsphere",
                "resourceType": "cloudchef.vsphere.nodes.Server",
                "credential": "secret",
            }
        )

    resource_result = resolver.resolve_page_context(
        "virtual-machine-detail",
        f"/main/virtual-machines/{RESOURCE_ID}/details",
        {"resource_id": RESOURCE_ID},
        "virtual-machine-detail",
        "virtual_machine",
        request_get=resource_get,
    )
    assert resource_result["success"] is True
    assert "credential" not in resource_result["object"]["attributes"]
    assert [action["action_id"] for action in resource_result["object_actions"]] == [
        "open_detail",
        "analyze",
        "list_operations",
    ]

    generic_resource_result = resolver.resolve_page_context(
        "cloud-resource-detail",
        f"/main/cloud-resource/{RESOURCE_ID}",
        {"resource_id": RESOURCE_ID},
        "resource-detail",
        "resource",
        request_get=resource_get,
    )
    assert generic_resource_result["success"] is True
    assert [
        action["action_id"] for action in generic_resource_result["object_actions"]
    ] == ["open_detail", "analyze", "list_operations"]


def test_object_parameter_contract_mismatch_fails_before_provider_io(monkeypatch) -> None:
    resolver = _load(monkeypatch)
    calls = 0

    def fail_http(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("invalid route contract must not reach SmartCMP")

    result = resolver.resolve_page_context(
        "catalog-request",
        "/main/catalog-ui/request/BUILD-IN-CATALOG-WINDOWS-VM",
        {
            "catalog_id": "BUILD-IN-CATALOG-WINDOWS-VM",
            "unexpected": "value",
        },
        "catalog-request",
        "catalog",
        request_get=fail_http,
    )
    assert result == {"success": False, "reason": "invalid_route_contract"}
    assert calls == 0


def test_cli_contract_uses_fixed_provider_level_arguments(monkeypatch) -> None:
    resolver = _load(monkeypatch)
    args = resolver.parse_args(
        [
            "catalog-request",
            "/main/catalog-ui/request/BUILD-IN-CATALOG-WINDOWS-VM",
            '{"catalog_id":"BUILD-IN-CATALOG-WINDOWS-VM"}',
            "catalog-request",
            "catalog",
        ]
    )
    assert vars(args) == {
        "route_id": "catalog-request",
        "path": "/main/catalog-ui/request/BUILD-IN-CATALOG-WINDOWS-VM",
        "route_parameters": '{"catalog_id":"BUILD-IN-CATALOG-WINDOWS-VM"}',
        "page_type": "catalog-request",
        "object_type": "catalog",
    }
