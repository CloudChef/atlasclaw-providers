# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Focused tests for SmartCMP's single Provider-level Context resolver."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from smartcmp_provider.auth import resolver as authentication_resolver
from smartcmp_provider.domain.request_ids import normalize_request_id
from smartcmp_provider.transport.client import SmartCmpClient


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
RESOLVER_ROOT = PROVIDER_ROOT / "assistant_context" / "resolvers"
RESOLVER_PATH = PROVIDER_ROOT / "assistant_context" / "resolve.py"
APPROVAL_ID = "e0b48865-9b12-4f83-a494-745534532995"
GENERIC_REQUEST_ID = "a1111111-3333-4333-8333-333333333333"
WORKFLOW_ID = "SR-2026/000001"
RESOURCE_ID = "7d64abdf-1111-4111-8111-111111111111"
ALERT_ID = "bccacc1a-651c-4d11-b8ea-a58e24e8f32b"
RECOMMENDATION_ID = "7c6196b1-5623-4d85-896d-e74b4f9042cd"
FORM_ID = "0897c154-3c46-414e-906e-2a7277f8def2"
SCRIPT_ID = "3e045633-6ed6-4988-bddf-c7136d54e7de"
POLICY_ID = "e3085cba-e8b9-4e6c-a65d-36331cdbe47d"
SECURITY_POLICY_ID = "policy.security.machine.metadata_service_hardened"
COMPONENT_ID = "010c8da0-9866-4b32-bbff-72f3d49efb4e"


class _Response:
    def __init__(self, payload, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class _Reader:
    """Expose a local SmartCMP Provider reader double without an HTTP fallback."""

    ui_base_url = "https://cmp.example.com"
    api_base_url = "https://cmp.example.com/platform-api"

    def __init__(self, callback: Callable[..., _Response]) -> None:
        self._callback = callback

    async def __aenter__(self) -> _Reader:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    async def read_form_definition(self, object_id: str) -> dict[str, Any]:
        return self._read(f"/forms/{object_id}")

    async def read_script_definition(self, object_id: str) -> dict[str, Any]:
        return self._read(f"/scripts/{object_id}")

    async def read_optimization_policy(self, object_id: str) -> dict[str, Any]:
        return self._read(f"/compliance-policies/{object_id}")

    async def read_security_policy(self, object_id: str) -> dict[str, Any]:
        return self._read(f"/compliance-policies/{object_id}")

    async def read_component_definition(self, object_id: str) -> dict[str, Any]:
        return self._read(f"/components/{object_id}")

    async def read_alert(self, object_id: str) -> dict[str, Any]:
        return self._read(f"/alarm-alert/{object_id}")

    async def read_cost_recommendation(self, object_id: str) -> dict[str, Any]:
        return self._read(f"/compliance-policies/violations/{object_id}")

    async def read_approval(self, object_id: str) -> dict[str, Any]:
        return self._read(f"/approval/{object_id}")

    async def list_current_pending_approvals(
        self,
        workflow_id: str,
    ) -> tuple[dict[str, Any], ...]:
        payload = self._read(
            "/generic-request/current-activity-approval",
            params={
                "page": 1,
                "size": 100,
                "stage": "pending",
                "states": "APPROVAL_PENDING",
                "sort": "updatedDate,desc",
                "searchValues": workflow_id,
            },
        )
        content = payload.get("content")
        return (
            tuple(item for item in content if isinstance(item, dict))
            if isinstance(content, list)
            else ()
        )

    async def list_current_approvals(
        self,
        workflow_id: str,
    ) -> tuple[dict[str, Any], ...]:
        payload = self._read(
            "/generic-request/current-activity-approval",
            params={
                "page": 1,
                "size": 20,
                "stage": "all",
                "sort": "updatedDate,desc",
                "searchValue": workflow_id,
            },
        )
        content = payload.get("content")
        return (
            tuple(item for item in content if isinstance(item, dict))
            if isinstance(content, list)
            else ()
        )

    async def read_catalog(self, object_id: str) -> dict[str, Any]:
        return self._read(f"/catalogs/{object_id}")

    async def read_request(self, object_id: str) -> dict[str, Any]:
        return self._read(f"/generic-request/{object_id}")

    async def read_resource(self, object_id: str) -> dict[str, Any]:
        return self._read(f"/nodes/{object_id}")

    async def has_instance_permission(
        self,
        entity_class: str,
        entity_id: str,
        permission: str,
    ) -> bool:
        payload = self._read(
            "/acl/queryCurrentUserPermissions",
            params={
                "entityClassNames": entity_class,
                "entityInstanceIds": entity_id,
            },
        )
        if not isinstance(payload, list):
            return False
        for item in payload:
            if not isinstance(item, dict):
                continue
            entity = item.get("entityClass")
            permissions = item.get("permissions")
            if (
                isinstance(entity, dict)
                and entity.get("className") == entity_class
                and entity.get("instanceId") in {entity_id, "", "-1"}
                and isinstance(permissions, list)
                and any(
                    (
                        value.get("id") if isinstance(value, dict) else value
                    )
                    == permission
                    for value in permissions
                )
            ):
                return True
        return False

    def _read(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        response = self._callback(
            f"{self.api_base_url}{path}",
            params=params,
        )
        response.raise_for_status()
        return response.json()


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
        "_object_actions_common",
        "_approval_object_actions",
        "_request_object_actions",
        "_resource_object_actions",
        "_security_object_actions",
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


def _resolve_page_context(module: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Run the async production resolver from focused synchronous tests."""

    return asyncio.run(module.resolve_page_context(*args, **kwargs))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("  Mixed Case / 01  ", "Mixed Case / 01"),
        (1, "1"),
        (True, ""),
        ("x" * 256, "x" * 256),
        ("x" * 257, ""),
        ("   ", ""),
    ],
)
def test_request_id_normalization_preserves_opaque_bounded_values(
    value: object,
    expected: str,
) -> None:
    assert normalize_request_id(value) == expected


def test_resolver_import_restores_process_import_state(monkeypatch) -> None:
    """Loading the cached callable must not expose Provider-local module names."""

    _configure(monkeypatch)
    local_names = (
        "_provider_bootstrap",
        "_alarm_object_actions",
        "_approval_object_actions",
        "_atlasclaw_adapter",
        "_context_resolver_common",
        "_cost_object_actions",
        "_object_actions_common",
        "_request_object_actions",
        "_resource_object_actions",
        "_security_object_actions",
    )
    original_path = list(sys.path)
    original_modules = {name: sys.modules.get(name) for name in local_names}
    spec = importlib.util.spec_from_file_location(
        "smartcmp_context_import_isolation",
        RESOLVER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert sys.path == original_path
    assert {
        name: sys.modules.get(name) for name in local_names
    } == original_modules
    assert callable(module.resolve_context)


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

    monkeypatch.setattr(
        authentication_resolver,
        "login_with_password",
        record_login,
    )

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
        "https://cmp.example.com",
        {"id": "CATALOG-1", "name": "Catalog", "status": state},
    )
    assert [action["action_id"] for action in actions] == expected_actions


@pytest.mark.asyncio
async def test_callable_resolver_uses_request_scoped_context(monkeypatch) -> None:
    """The production entrypoint reads identity from ctx without a child process."""

    module = _load(monkeypatch)
    resource = {
        "id": RESOURCE_ID,
        "name": "VM 01",
        "status": "RUNNING",
        "componentType": "cloud.machine.instance.vm",
    }

    def fake_get(url, **_kwargs):
        if url.endswith("/acl/queryCurrentUserPermissions"):
            return _Response(_acl(module.RESOURCE_ENTITY_CLASS, RESOURCE_ID))
        assert url.endswith(f"/nodes/{RESOURCE_ID}")
        return _Response(resource)

    expected_ctx = SimpleNamespace(deps=SimpleNamespace())

    async def load_reader(ctx):
        assert ctx is expected_ctx
        return _Reader(fake_get)

    monkeypatch.setattr(module, "load_context_reader_from_context", load_reader)
    result = await module.resolve_context(
        expected_ctx,
        "virtual-machine-detail",
        f"/main/virtual-machines/{RESOURCE_ID}/details",
        {"resource_id": RESOURCE_ID},
        "virtual-machine-detail",
        "virtual_machine",
    )

    assert result["success"] is True
    assert result["object"]["id"] == RESOURCE_ID


def test_pending_approval_resolves_exact_identifiers(monkeypatch) -> None:
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

    result = _resolve_page_context(
        module,
        "pending-approval-detail",
        f"/main/new-application/pendingApproval/PROVISION_BP/{APPROVAL_ID}",
        {"approval_type": "PROVISION_BP", "approval_id": APPROVAL_ID},
        "approval-detail",
        "approval_request",
        reader=_Reader(fake_get),
    )
    assert result["success"] is True
    assert result["object"]["id"] == WORKFLOW_ID
    assert [action["action_id"] for action in result["object_actions"]] == [
        "open_detail",
        "analyze",
        "approve",
        "reject",
    ]


def test_work_order_approval_resolves_opaque_request_id(monkeypatch) -> None:
    module = _load(monkeypatch)
    pending_row = {
        "id": GENERIC_REQUEST_ID,
        "workflowId": WORKFLOW_ID,
        "name": "Service request",
        "exts": {
            "approval_id": APPROVAL_ID,
            "approval_type": "MANUAL_REQUEST",
            "approval_state": "PENDING",
        },
    }

    def fake_get(url, **kwargs):
        if url.endswith(f"/generic-request/{GENERIC_REQUEST_ID}"):
            return _Response(
                {
                    "id": GENERIC_REQUEST_ID,
                    "workflowId": WORKFLOW_ID,
                }
            )
        if url.endswith(f"/approval/{APPROVAL_ID}"):
            return _Response(
                {
                    "id": APPROVAL_ID,
                    "genericRequestId": GENERIC_REQUEST_ID,
                    "workflowId": WORKFLOW_ID,
                    "state": "PENDING",
                    "type": "MANUAL_REQUEST",
                }
            )
        assert url.endswith("/generic-request/current-activity-approval")
        assert kwargs["params"]["searchValue"] == WORKFLOW_ID
        return _Response({"content": [pending_row]})

    result = _resolve_page_context(
        module,
        "work-order-approval-detail",
        f"/main/work-order-process/ServiceRequest/myApproval/{GENERIC_REQUEST_ID}",
        {"generic_request_id": GENERIC_REQUEST_ID},
        "approval-detail",
        "approval_request",
        reader=_Reader(fake_get),
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
                    "category": "COST-OPTIMIZATION.MACHINE",
                    "status": "ACTIVED",
                    "resourceId": RESOURCE_ID,
                "monthlySaving": 120,
                "fixType": "RESIZE",
            }
        )

    alert = _resolve_page_context(
        module,
        "alarm-alert-detail",
        f"/main/alarm-activity-management/alarm-triggered/edit/{ALERT_ID}",
        {"alert_id": ALERT_ID},
        "alarm-alert-detail",
        "alarm_alert",
        reader=_Reader(fake_get),
    )
    assert alert["object"]["id"] == ALERT_ID
    assert [action["action_id"] for action in alert["object_actions"]] == [
        "analyze",
        "mute",
        "resolve",
    ]

    cost = _resolve_page_context(
        module,
        "cost-optimization-detail",
        f"/main/measurement-billing/resource-usage-analysis/{RECOMMENDATION_ID}",
        {"recommendation_id": RECOMMENDATION_ID},
        "cost-optimization-detail",
        "cost_optimization_recommendation",
        reader=_Reader(fake_get),
    )
    assert cost["object"]["id"] == RECOMMENDATION_ID
    assert [action["action_id"] for action in cost["object_actions"]] == [
        "analyze",
        "remediate",
    ]
    assert cost["object_actions"][1]["requires_confirmation"] is True


def test_cost_context_rejects_security_violation_with_matching_id(monkeypatch) -> None:
    """A matching ID cannot turn a Security violation into a Cost page object."""

    module = _load(monkeypatch)

    def fake_get(url, **_kwargs):
        assert url.endswith(
            f"/compliance-policies/violations/{RECOMMENDATION_ID}"
        )
        return _Response(
            {
                "id": RECOMMENDATION_ID,
                "category": "SECURITY.MACHINE",
                "status": "ACTIVED",
                "fixType": "DAY2",
            }
        )

    result = _resolve_page_context(
        module,
        "cost-optimization-detail",
        f"/main/measurement-billing/resource-usage-analysis/{RECOMMENDATION_ID}",
        {"recommendation_id": RECOMMENDATION_ID},
        "cost-optimization-detail",
        "cost_optimization_recommendation",
        reader=_Reader(fake_get),
    )

    assert result == {
        "success": False,
        "reason": "recommendation_category_mismatch",
    }


def test_security_collection_context_lists_violations_without_provider_io(
    monkeypatch,
) -> None:
    """The records page routes to the Security skill without inventing an object ID."""

    module = _load(monkeypatch)

    def fail_http(*_args, **_kwargs):
        raise AssertionError("Collection context must not call SmartCMP")

    result = _resolve_page_context(
        module,
        "security-compliance-violations",
        "/main/resource-management/records",
        {},
        "security-compliance-violations",
        "security_compliance_violation_collection",
        reader=_Reader(fail_http),
    )

    assert result["success"] is True
    assert result["object"]["id"] == "security"
    assert result["object"]["attributes"] == {"category": "SECURITY"}
    assert [action["action_id"] for action in result["object_actions"]] == [
        "list"
    ]
    prompt = result["object_actions"][0]["agent_prompt"]["default"]
    assert "smartcmp_list_security_violations" in prompt


def test_security_policy_edit_context_binds_security_skill_to_exact_policy(
    monkeypatch,
) -> None:
    """The Security policy editor resolves its dotted policy ID for action turns."""

    module = _load(monkeypatch)

    def fake_get(url, **_kwargs):
        assert url.endswith(f"/compliance-policies/{SECURITY_POLICY_ID}")
        return _Response(
            {
                "id": SECURITY_POLICY_ID,
                "name": "Harden metadata service",
                "category": "SECURITY.MACHINE",
                "severity": "HIGH",
                "type": "COMPLIANCE",
                "status": "ENABLED",
            }
        )

    result = _resolve_page_context(
        module,
        "security-compliance-policy-edit",
        f"/main/resource-management/policy/edit/{SECURITY_POLICY_ID}",
        {"policy_id": SECURITY_POLICY_ID},
        "security-compliance-policy-edit",
        "security_compliance_policy",
        reader=_Reader(fake_get),
    )

    assert result["success"] is True
    assert result["object"] == {
        "type": "security_compliance_policy",
        "id": SECURITY_POLICY_ID,
        "name": "Harden metadata service",
        "state": "enabled",
        "attributes": {
            "category": "SECURITY.MACHINE",
            "severity": "HIGH",
            "policy_type": "COMPLIANCE",
        },
    }
    assert result["object_actions"] == []


def test_security_policy_edit_context_requires_explicit_security_category(
    monkeypatch,
) -> None:
    """A policy without Security category evidence must not bind the page Skill."""

    module = _load(monkeypatch)
    result = _resolve_page_context(
        module,
        "security-compliance-policy-edit",
        f"/main/resource-management/policy/edit/{SECURITY_POLICY_ID}",
        {"policy_id": SECURITY_POLICY_ID},
        "security-compliance-policy-edit",
        "security_compliance_policy",
        reader=_Reader(
            lambda *_args, **_kwargs: _Response(
                {
                    "id": SECURITY_POLICY_ID,
                    "name": "Missing category",
                }
            )
        ),
    )

    assert result == {"success": False, "reason": "policy_category_mismatch"}


def test_edit_pages_resolve_minimal_current_objects_without_business_content(
    monkeypatch,
) -> None:
    """Editor Context resolves identity only; each page Skill reads full content later."""
    module = _load(monkeypatch)

    def fake_get(url, **_kwargs):
        if url.endswith(f"/forms/{FORM_ID}"):
            return _Response(
                {
                    "id": FORM_ID,
                    "name": "test-form",
                    "enabled": True,
                    "content": {"schema": {"type": "object"}},
                }
            )
        if url.endswith(f"/scripts/{SCRIPT_ID}"):
            return _Response(
                {
                    "id": SCRIPT_ID,
                    "name": "example.py",
                    "alias": "example",
                    "type": "PYTHON",
                    "state": "PUBLISHED",
                    "content": "print('private editor content')",
                }
            )
        if url.endswith(f"/compliance-policies/{POLICY_ID}"):
            return _Response(
                {
                    "id": POLICY_ID,
                    "name": "Right-size VM",
                    "category": "COST-OPTIMIZATION.MACHINE",
                    "type": "COMPLIANCE",
                    "resourceType": ["resource.iaas.machine.instance"],
                    "ruleContent": "private-rule-content",
                    "policyConfigs": [{"status": "ENABLED"}],
                }
            )
        assert url.endswith(f"/components/{COMPONENT_ID}")
        return _Response(
            {
                "id": COMPONENT_ID,
                "name": "MongoDB",
                "resourceType": "resource.software.nosql.mongodb",
                "parentType": "resource.software.nosql",
                "published": True,
                "model": {
                    "blueprintFiles": [
                        {"path": "scripts/install.sh", "content": "private-script-content"}
                    ]
                },
            }
        )

    cases = [
        (
            "form-definition-edit",
            f"/main/service-model/forms/edit/{FORM_ID}",
            {"form_id": FORM_ID},
            "form-definition-edit",
            "form_definition",
            FORM_ID,
        ),
        (
            "form-definition-design",
            f"/main/service-model/forms/design/{FORM_ID}",
            {"form_id": FORM_ID},
            "form-definition-design",
            "form_definition",
            FORM_ID,
        ),
        (
            "script-definition-edit",
            f"/main/model-design/scripts/edit/{SCRIPT_ID}",
            {"script_id": SCRIPT_ID},
            "script-definition-edit",
            "script_definition",
            SCRIPT_ID,
        ),
        (
            "optimization-policy-edit",
            (
                "/main/measurement-billing/cost-optimization/"
                f"optimization-policy/edit/{POLICY_ID}"
            ),
            {"policy_id": POLICY_ID},
            "optimization-policy-edit",
            "optimization_policy",
            POLICY_ID,
        ),
        (
            "blueprint-component-edit",
            f"/main/model-design/blueprint-components/edit/{COMPONENT_ID}",
            {"component_id": COMPONENT_ID},
            "blueprint-component-edit",
            "blueprint_component",
            COMPONENT_ID,
        ),
    ]

    for route_id, path, parameters, page_type, object_type, object_id in cases:
        result = _resolve_page_context(
            module,
            route_id,
            path,
            parameters,
            page_type,
            object_type,
            reader=_Reader(fake_get),
        )
        assert result["success"] is True
        assert result["object"]["id"] == object_id
        assert result["object_actions"] == []
        serialized = json.dumps(result, ensure_ascii=False)
        assert "private" not in serialized


def test_optimization_policy_resolver_rejects_deceptive_category_prefix(
    monkeypatch,
) -> None:
    module = _load(monkeypatch)
    result = _resolve_page_context(
        module,
        "optimization-policy-edit",
        (
            "/main/measurement-billing/cost-optimization/"
            f"optimization-policy/edit/{POLICY_ID}"
        ),
        {"policy_id": POLICY_ID},
        "optimization-policy-edit",
        "optimization_policy",
        reader=_Reader(
            lambda *_args, **_kwargs: _Response(
                {
                    "id": POLICY_ID,
                    "name": "Wrong category",
                    "category": "COST-OPTIMIZATIONX.MACHINE",
                }
            )
        ),
    )

    assert result == {"success": False, "reason": "policy_category_mismatch"}


@pytest.mark.parametrize(
    (
        "route_id",
        "path",
        "parameters",
        "page_type",
        "object_type",
        "expected_reason",
    ),
    [
        (
            "form-definition-edit",
            f"/main/service-model/forms/edit/{FORM_ID}",
            {"form_id": FORM_ID},
            "form-definition-edit",
            "form_definition",
            "form_id_mismatch",
        ),
        (
            "form-definition-design",
            f"/main/service-model/forms/design/{FORM_ID}",
            {"form_id": FORM_ID},
            "form-definition-design",
            "form_definition",
            "form_id_mismatch",
        ),
        (
            "script-definition-edit",
            f"/main/model-design/scripts/edit/{SCRIPT_ID}",
            {"script_id": SCRIPT_ID},
            "script-definition-edit",
            "script_definition",
            "script_id_mismatch",
        ),
        (
            "optimization-policy-edit",
            (
                "/main/measurement-billing/cost-optimization/"
                f"optimization-policy/edit/{POLICY_ID}"
            ),
            {"policy_id": POLICY_ID},
            "optimization-policy-edit",
            "optimization_policy",
            "policy_id_mismatch",
        ),
        (
            "blueprint-component-edit",
            f"/main/model-design/blueprint-components/edit/{COMPONENT_ID}",
            {"component_id": COMPONENT_ID},
            "blueprint-component-edit",
            "blueprint_component",
            "component_id_mismatch",
        ),
    ],
)
def test_edit_page_resolvers_reject_provider_object_id_mismatch(
    monkeypatch,
    route_id: str,
    path: str,
    parameters: dict[str, str],
    page_type: str,
    object_type: str,
    expected_reason: str,
) -> None:
    module = _load(monkeypatch)

    result = _resolve_page_context(
        module,
        route_id,
        path,
        parameters,
        page_type,
        object_type,
        reader=_Reader(
            lambda *_args, **_kwargs: _Response(
                {"id": GENERIC_REQUEST_ID}
            )
        ),
    )

    assert result == {"success": False, "reason": expected_reason}


def test_work_order_application_resolves_request_context(monkeypatch) -> None:
    resolver = _load(monkeypatch)
    work_order_request = {
        "id": GENERIC_REQUEST_ID,
        "workflowId": WORKFLOW_ID,
        "type": "CHANGE_SERVICE",
        "name": "Change request",
        "state": "APPROVAL_PENDING",
        "credential": "secret",
    }

    def request_get(url, **_kwargs):
        assert url.endswith(f"/generic-request/{GENERIC_REQUEST_ID}")
        return _Response(work_order_request)

    result = _resolve_page_context(
        resolver,
        "work-order-application-detail",
        (
            "/main/work-order-process/ServiceRequest/myApplication/"
            f"{GENERIC_REQUEST_ID}"
        ),
        {"generic_request_id": GENERIC_REQUEST_ID},
        "request-detail",
        "request",
        reader=_Reader(request_get),
    )

    assert result["success"] is True
    assert result["object"]["id"] == WORKFLOW_ID
    assert result["object"]["attributes"]["application_type"] == "CHANGE_SERVICE"
    assert "credential" not in result["object"]["attributes"]
    assert [action["action_id"] for action in result["object_actions"]] == [
        "open_detail",
    ]


@pytest.mark.parametrize("application_type", [None, "change-service", True])
def test_work_order_application_rejects_invalid_provider_type(
    monkeypatch,
    application_type: object,
) -> None:
    resolver = _load(monkeypatch)
    request = {
        "id": GENERIC_REQUEST_ID,
        "workflowId": WORKFLOW_ID,
        "type": application_type,
    }

    result = _resolve_page_context(
        resolver,
        "work-order-application-detail",
        (
            "/main/work-order-process/ServiceRequest/myApplication/"
            f"{GENERIC_REQUEST_ID}"
        ),
        {"generic_request_id": GENERIC_REQUEST_ID},
        "request-detail",
        "request",
        reader=_Reader(lambda *_args, **_kwargs: _Response(request)),
    )

    assert result == {"success": False, "reason": "invalid_application_type"}


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

    catalog_result = _resolve_page_context(
        resolver,
        "catalog-request",
        f"/main/catalog-ui/request/{catalog_id}",
        {"catalog_id": catalog_id},
        "catalog-request",
        "catalog",
        reader=_Reader(catalog_get),
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
    request_result = _resolve_page_context(
        resolver,
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
        reader=_Reader(lambda *_args, **_kwargs: _Response(request)),
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

    resource_result = _resolve_page_context(
        resolver,
        "virtual-machine-detail",
        f"/main/virtual-machines/{RESOURCE_ID}/details",
        {"resource_id": RESOURCE_ID},
        "virtual-machine-detail",
        "virtual_machine",
        reader=_Reader(resource_get),
    )
    assert resource_result["success"] is True
    assert "credential" not in resource_result["object"]["attributes"]
    assert [action["action_id"] for action in resource_result["object_actions"]] == [
        "open_detail",
        "analyze",
        "list_operations",
    ]
    operations_action = next(
        action
        for action in resource_result["object_actions"]
        if action["action_id"] == "list_operations"
    )
    operations_prompt = operations_action["agent_prompt"]["default"]
    assert RESOURCE_ID in operations_prompt
    assert '"virtual-machines"' in operations_prompt
    assert "do not resolve the target by display name" in operations_prompt

    generic_resource_result = _resolve_page_context(
        resolver,
        "cloud-resource-detail",
        f"/main/cloud-resource/{RESOURCE_ID}",
        {"resource_id": RESOURCE_ID},
        "resource-detail",
        "resource",
        reader=_Reader(resource_get),
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

    result = _resolve_page_context(
        resolver,
        "catalog-request",
        "/main/catalog-ui/request/BUILD-IN-CATALOG-WINDOWS-VM",
        {
            "catalog_id": "BUILD-IN-CATALOG-WINDOWS-VM",
            "unexpected": "value",
        },
        "catalog-request",
        "catalog",
        reader=_Reader(fail_http),
    )
    assert result == {"success": False, "reason": "invalid_route_contract"}
    assert calls == 0
