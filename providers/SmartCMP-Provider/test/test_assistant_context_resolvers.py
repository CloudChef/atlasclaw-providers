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
    sys.path.insert(0, str(RESOLVER_ROOT))
    try:
        spec = importlib.util.spec_from_file_location("smartcmp_page_context", RESOLVER_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(RESOLVER_ROOT))


def _acl(entity_class: str, entity_id: str) -> list[dict]:
    return [
        {
            "entityClass": {"className": entity_class, "instanceId": entity_id},
            "permissions": [{"id": "READ"}],
        }
    ]


def _assert_generic_chat_actions(actions: list[dict]) -> None:
    for action in actions:
        common = {"action_id", "kind", "display_label", "effect", "tone"}
        confirmation = (
            {"requires_confirmation", "confirmation_message"}
            if action.get("requires_confirmation") is True
            else set()
        )
        if action["kind"] == "open_url":
            assert set(action) == common | {"href"}
        elif "agent_prompt_template" in action:
            assert set(action) == common | confirmation | {"agent_prompt_template", "inputs"}
            for input_spec in action["inputs"]:
                assert set(input_spec) == {
                    "name",
                    "display_label",
                    "type",
                    "required",
                }
        else:
            assert action["kind"] == "agent_prompt"
            assert set(action) == common | confirmation | {"agent_prompt"}
        assert action["display_label"]["default"]


def test_one_resolver_uses_context_support_without_importing_domain_skills() -> None:
    """Keep the Provider entrypoint independent from domain Skill implementations."""
    assert (RESOLVER_ROOT / "_context_resolver_common.py").is_file()
    assert not (RESOLVER_ROOT / "_common.py").exists()
    source = RESOLVER_PATH.read_text(encoding="utf-8")
    assert "from _context_resolver_common import" in source
    assert "from _common import" not in source
    assert "skill_ref" not in source
    assert "skills/" not in source


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
        return _Response(
            {
                "content": [
                    {
                        "id": GENERIC_REQUEST_ID,
                        "workflowId": WORKFLOW_ID,
                        "name": "Production VM",
                        "exts": {
                            "approval_id": APPROVAL_ID,
                            "approval_type": "PROVISION_BP",
                            "approval_state": "PENDING",
                        },
                    }
                ]
            }
        )

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
    assert result["object_actions"][2]["effect"] == "mutate"
    reject = result["object_actions"][3]
    assert reject["effect"] == "mutate"
    assert reject["inputs"][0]["name"] == "reason"
    assert result["object_actions"][1]["agent_prompt"]["default"] == (
        "Run read-only analysis for the approval request on the current page"
    )
    approve = result["object_actions"][2]
    assert approve["requires_confirmation"] is True
    assert approve["confirmation_message"] == {
        "default": "Confirm approval of the request on the current page?",
        "translations": {
            "en-US": "Confirm approval of the request on the current page?",
            "zh-CN": "确认批准当前页面的审批请求吗？",
        },
    }
    assert approve["agent_prompt"]["default"] == (
        "The user confirmed in the UI: approve the approval request on the current page"
    )
    assert reject["requires_confirmation"] is True
    assert reject["confirmation_message"]["translations"]["zh-CN"] == (
        "确认拒绝当前页面的审批请求吗？"
    )
    assert reject["agent_prompt_template"]["default"] == (
        "The user confirmed in the UI: reject the approval request on the current page, "
        "reason: {{reason}}"
    )
    _assert_generic_chat_actions(result["object_actions"])


def test_catalog_request_and_resource_resolvers_return_selected_display_fields(monkeypatch) -> None:
    resolver = _load(monkeypatch)
    catalog_id = "BUILD-IN-CATALOG-WINDOWS-VM"

    def catalog_get(url, **kwargs):
        if url.endswith("/acl/queryCurrentUserPermissions"):
            return _Response(_acl(resolver.CATALOG_ENTITY_CLASS, catalog_id))
        return _Response(
            {
                "id": catalog_id,
                "name": "Windows VM",
                "description": "Catalog description",
                "sourceKey": "WINDOWS_VM",
                "status": "ACTIVE",
                "inputData": {"password": "secret"},
            }
        )

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
    assert all(
        "requires_confirmation" not in action
        for action in catalog_result["object_actions"]
    )
    _assert_generic_chat_actions(catalog_result["object_actions"])

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
        request_get=lambda *_args, **_kwargs: _Response(
            {
                "id": GENERIC_REQUEST_ID,
                "workflowId": WORKFLOW_ID,
                "type": "CLOUD_BLUEPRINT_SERVICE",
                "name": "My request",
                "state": "PENDING",
                "credential": "secret",
            }
        ),
    )
    assert request_result["success"] is True
    assert "credential" not in request_result["object"]["attributes"]
    assert [action["action_id"] for action in request_result["object_actions"]] == [
        "open_detail",
        "status",
    ]
    assert request_result["object_actions"][1]["agent_prompt"]["default"] == (
        "Check the status of the request on the current page"
    )
    _assert_generic_chat_actions(request_result["object_actions"])

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
        "list_operations",
    ]
    assert all(
        "requires_confirmation" not in action
        for action in resource_result["object_actions"]
    )
    _assert_generic_chat_actions(resource_result["object_actions"])


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
