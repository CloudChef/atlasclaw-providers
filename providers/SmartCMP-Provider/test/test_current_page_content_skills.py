# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Focused contracts for current-page content designer Skills."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = PROVIDER_ROOT / "skills"
FORM_ID = "0897c154-3c46-414e-906e-2a7277f8def2"
SCRIPT_ID = "3e045633-6ed6-4988-bddf-c7136d54e7de"
POLICY_ID = "e3085cba-e8b9-4e6c-a65d-36331cdbe47d"
COMPONENT_ID = "010c8da0-9866-4b32-bbff-72f3d49efb4e"


def _load(path: Path, module_name: str):
    original_path = list(sys.path)
    try:
        sys.path.insert(0, str(path.parent))
        spec = importlib.util.spec_from_file_location(module_name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path[:] = original_path


def _ctx(
    *,
    object_type: str,
    object_id: str,
    turn_object_id: str | None = None,
    cookies: dict[str, str] | None = None,
):
    context = {
        "embed_scope": {
            "provider_type": "smartcmp",
            "provider_instance": "default",
            "object_type": object_type,
            "object_id": object_id,
        },
        "turn_context": {
            "object": {
                "type": object_type,
                "id": turn_object_id or object_id,
            }
        },
    }
    deps = SimpleNamespace(
        cookies={"CloudChef-Authenticate": "request-cookie"}
        if cookies is None
        else cookies,
        extra={
            "context": context,
            "provider_instance_name": "default",
            "provider_instance": {"base_url": "https://cmp.example.com"},
        },
    )
    return SimpleNamespace(deps=deps)


def _chat_ctx(
    instance: dict[str, object] | None = None,
) -> SimpleNamespace:
    """Build ordinary chat Context with Provider auth but no embedded page scope."""
    provider_instance = instance or {
        "base_url": "https://cmp.example.com",
        "auth_type": "provider_token",
        "provider_token": "cmp_tk_read_only",
    }
    return SimpleNamespace(
        deps=SimpleNamespace(
            cookies={},
            extra={
                "context": {},
                "provider_instance_name": "default",
                "provider_instance": provider_instance,
            },
        )
    )


def test_current_page_scope_requires_exact_turn_object_and_request_cookie() -> None:
    helper = _load(
        SKILLS_ROOT / "shared" / "scripts" / "_current_page_object.py",
        "current_page_object_contract",
    )

    object_id, base_url, headers, timeout = helper._current_scope(
        _ctx(object_type="form_definition", object_id=FORM_ID),
        expected_object_type="form_definition",
    )
    assert object_id == FORM_ID
    assert base_url == "https://cmp.example.com/platform-api"
    assert headers == {"CloudChef-Authenticate": "request-cookie"}
    assert timeout == 60

    with pytest.raises(helper.CurrentPageObjectError, match="inconsistent"):
        helper._current_scope(
            _ctx(
                object_type="form_definition",
                object_id=FORM_ID,
                turn_object_id=SCRIPT_ID,
            ),
            expected_object_type="form_definition",
        )
    with pytest.raises(helper.CurrentPageObjectError, match="session"):
        helper._current_scope(
            _ctx(object_type="form_definition", object_id=FORM_ID, cookies={}),
            expected_object_type="form_definition",
        )


@pytest.mark.parametrize(
    ("instance", "expected_headers"),
    [
        (
            {
                "base_url": "https://cmp.example.com",
                "auth_type": "provider_token",
                "provider_token": "cmp_tk_provider",
            },
            {
                "Authorization": "Bearer cmp_tk_provider",
                "Content-Type": "application/json; charset=utf-8",
            },
        ),
        (
            {
                "base_url": "https://cmp.example.com",
                "auth_type": "user_token",
                "user_token": "user-jwt",
            },
            {
                "CloudChef-Authenticate": "user-jwt",
                "Content-Type": "application/json; charset=utf-8",
            },
        ),
        (
            {
                "base_url": "https://cmp.example.com",
                "auth_type": "cookie",
                "cookie": "cookie-jwt",
            },
            {
                "CloudChef-Authenticate": "cookie-jwt",
                "Content-Type": "application/json; charset=utf-8",
            },
        ),
    ],
)
def test_ordinary_chat_read_config_supports_selected_provider_auth_modes(
    instance: dict[str, object],
    expected_headers: dict[str, str],
) -> None:
    helper = _load(
        SKILLS_ROOT / "shared" / "scripts" / "_current_page_object.py",
        f"current_page_auth_{instance['auth_type']}",
    )

    base_url, headers, timeout = helper.selected_provider_read_config(
        _chat_ctx(instance),
        request_cookie_only=False,
    )

    assert base_url == "https://cmp.example.com/platform-api"
    assert headers == expected_headers
    assert timeout == 60


def test_ordinary_chat_read_config_supports_selected_provider_credentials(
    monkeypatch,
) -> None:
    helper = _load(
        SKILLS_ROOT / "shared" / "scripts" / "_current_page_object.py",
        "current_page_auth_credential",
    )
    calls: list[tuple] = []

    def fake_login(auth_url, username, password, timeout):
        calls.append((auth_url, username, password, timeout))
        return "CloudChef-Authenticate=credential-jwt"

    monkeypatch.setattr(helper, "_auto_login", fake_login)
    base_url, headers, timeout = helper.selected_provider_read_config(
        _chat_ctx(
            {
                "base_url": "https://cmp.example.com",
                "auth_type": "credential",
                "username": "configured-user",
                "password": "configured-password",
            }
        ),
        request_cookie_only=False,
    )

    assert base_url == "https://cmp.example.com/platform-api"
    assert headers["CloudChef-Authenticate"] == "credential-jwt"
    assert timeout == 60
    assert calls == [
        (
            "https://cmp.example.com/platform-api/login",
            "configured-user",
            "configured-password",
            60,
        )
    ]


def test_form_page_tool_returns_complete_normalized_schema(monkeypatch) -> None:
    module = _load(
        SKILLS_ROOT / "form-designer" / "scripts" / "read_current_form.py",
        "read_current_form_contract",
    )

    async def fake_fetch(_ctx, **kwargs):
        assert kwargs == {
            "expected_object_type": "form_definition",
            "api_collection": "forms",
        }
        return {
            "id": FORM_ID,
            "name": "test-form",
            "content": {
                "schema": {
                    "type": "object",
                    "widget": {"id": "object"},
                    "properties": {
                        "name": {
                            "type": "string",
                            "widget": {"id": "string"},
                        }
                    },
                    "fieldsets": [
                        {
                            "id": "fieldset-default",
                            "fields": ["name"],
                        }
                    ],
                },
                "model": {"name": "original"},
                "designMode": "schema",
                "components": [],
            },
        }

    monkeypatch.setattr(module, "fetch_current_page_object", fake_fetch)
    result = asyncio.run(module.read_current_form(None))

    assert result["success"] is True
    assert result["form"]["id"] == FORM_ID
    assert result["form"]["schema"]["properties"]["name"]["type"] == "string"
    assert '"name"' in result["output"]


def test_embedded_form_url_tools_reject_mismatch_before_provider_get(
    monkeypatch,
) -> None:
    read_module = _load(
        SKILLS_ROOT / "form-designer" / "scripts" / "read_form.py",
        "read_form_embedded_identity_contract",
    )
    design_module = _load(
        SKILLS_ROOT / "form-designer" / "scripts" / "design_form_handler.py",
        "design_form_embedded_identity_contract",
    )
    other_id = "123e4567-e89b-12d3-a456-426614174000"
    form_url = (
        "https://cmp.example.com/#/main/service-model/forms/edit/"
        f"{other_id}"
    )
    calls: list[str] = []

    def unexpected_read(*_args, **_kwargs):
        calls.append("read")
        raise AssertionError("mismatch must fail before a Provider GET")

    async def unexpected_current_read(*_args, **_kwargs):
        calls.append("current")
        raise AssertionError("mismatch must fail before a Provider GET")

    monkeypatch.setattr(read_module, "fetch_form_definition", unexpected_read)
    monkeypatch.setattr(
        design_module,
        "fetch_current_page_object",
        unexpected_current_read,
    )
    ctx = _ctx(object_type="form_definition", object_id=FORM_ID)

    read_result = asyncio.run(read_module.read_form(ctx, form_url))
    design_result = asyncio.run(
        design_module.design_form(
            ctx,
            mode="modify",
            schema_json='{"type":"object","properties":{}}',
            form_url=form_url,
        )
    )

    assert read_result["success"] is False
    assert design_result["success"] is False
    assert "does not match" in read_result["error"]
    assert "does not match" in design_result["error"]
    assert calls == []


def test_ordinary_chat_form_url_read_uses_selected_provider_auth_without_host_cookie(
    monkeypatch,
) -> None:
    module = _load(
        SKILLS_ROOT / "form-designer" / "scripts" / "read_form.py",
        "read_form_ordinary_chat_contract",
    )
    calls: list[dict] = []

    def fake_fetch(form_url, base_url, headers, *, timeout):
        calls.append(
            {
                "form_url": form_url,
                "base_url": base_url,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return SimpleNamespace(
            form_id=FORM_ID,
            name="ordinary-chat-form",
            description="",
            schema={"type": "object", "properties": {}},
            model={},
            design_mode="",
            component_count=0,
            source_route="edit",
            raw_content_keys=["schema"],
        )

    monkeypatch.setattr(module, "fetch_form_definition", fake_fetch)
    form_url = (
        "https://cmp.example.com/#/main/service-model/forms/edit/"
        f"{FORM_ID}"
    )
    result = asyncio.run(module.read_form(_chat_ctx(), form_url))

    assert result["success"] is True
    assert calls == [
        {
            "form_url": form_url,
            "base_url": "https://cmp.example.com/platform-api",
            "headers": {
                "Authorization": "Bearer cmp_tk_read_only",
                "Content-Type": "application/json; charset=utf-8",
            },
            "timeout": 60,
        }
    ]


def test_form_design_handler_returns_complete_manual_copy_contract(
    monkeypatch,
) -> None:
    module = _load(
        SKILLS_ROOT / "form-designer" / "scripts" / "design_form_handler.py",
        "design_form_final_output_contract",
    )

    async def fake_fetch(_ctx, **kwargs):
        assert kwargs == {
            "expected_object_type": "form_definition",
            "api_collection": "forms",
        }
        return {
            "id": FORM_ID,
            "name": "test-form",
            "content": {
                "schema": {"type": "object", "properties": {}},
                "model": {},
                "components": [],
            },
        }

    monkeypatch.setattr(module, "fetch_current_page_object", fake_fetch)
    schema_json = (
        '{"type":"object","widget":{"id":"object"},'
        '"properties":{"name":{"type":"string","widget":{"id":"string"}}},'
        '"fieldsets":[{"id":"fieldset-default","fields":["name"]}]}'
    )
    result = asyncio.run(
        module.design_form(
            _ctx(object_type="form_definition", object_id=FORM_ID),
            mode="modify",
            schema_json=schema_json,
            change_summary="Added the requested name field.",
        )
    )

    assert result["success"] is True
    assert result["final_user_output"] == result["output"]
    output = result["final_user_output"]
    for heading in (
        "## 1. Current Object",
        "## 2. Copy Target",
        "## 3. Change Summary",
        "## 4. Complete Replacement JSON",
        "## 5. Validation and Risks",
        "## 6. Save Status",
    ):
        assert heading in output
    assert "test-form" in output
    assert FORM_ID in output
    assert "`content.schema`" in output
    assert '"name"' in output
    assert "Added the requested name field." in output
    assert "Not saved." in output


def test_ordinary_chat_form_design_keeps_url_mode_and_reports_source_name(
    monkeypatch,
) -> None:
    module = _load(
        SKILLS_ROOT / "form-designer" / "scripts" / "design_form_handler.py",
        "design_form_ordinary_chat_contract",
    )

    def fake_fetch(form_url, base_url, headers, *, timeout):
        assert form_url.endswith(FORM_ID)
        assert base_url == "https://cmp.example.com/platform-api"
        assert headers["Authorization"] == "Bearer cmp_tk_read_only"
        assert timeout == 60
        return SimpleNamespace(
            form_id=FORM_ID,
            name="ordinary-chat-form",
            description="",
            schema={"type": "object", "properties": {}},
            model={},
            design_mode="",
            component_count=0,
            source_route="edit",
            raw_content_keys=["schema"],
        )

    monkeypatch.setattr(module, "fetch_form_definition", fake_fetch)
    result = asyncio.run(
        module.design_form(
            _chat_ctx(),
            mode="regenerate",
            form_url=(
                "https://cmp.example.com/#/main/service-model/forms/edit/"
                f"{FORM_ID}"
            ),
            schema_json='{"type":"object","properties":{}}',
        )
    )

    assert result["success"] is True
    assert "ordinary-chat-form" in result["final_user_output"]
    assert FORM_ID in result["final_user_output"]


def test_script_and_policy_page_tools_return_complete_editable_content(
    monkeypatch,
) -> None:
    script_module = _load(
        SKILLS_ROOT / "script-designer" / "scripts" / "read_current_script.py",
        "read_current_script_contract",
    )
    policy_module = _load(
        SKILLS_ROOT
        / "optimization-policy-designer"
        / "scripts"
        / "read_current_policy.py",
        "read_current_policy_contract",
    )

    async def fake_script(_ctx, **_kwargs):
        return {
            "id": SCRIPT_ID,
            "name": "example.py",
            "alias": "example",
            "type": "PYTHON",
            "params": [{"name": "delay"}],
            "content": "def main():\n    return 'complete-script'",
        }

    async def fake_policy(_ctx, **_kwargs):
        return {
            "id": POLICY_ID,
            "name": "Right-size VM",
            "category": "COST-OPTIMIZATION.MACHINE",
            "resourceType": ["resource.iaas.machine.instance"],
            "severity": "HIGH",
            "ruleContent": "return complete_policy_rule",
            "policyConfigs": [{"status": "ENABLED"}],
        }

    monkeypatch.setattr(script_module, "fetch_current_page_object", fake_script)
    monkeypatch.setattr(policy_module, "fetch_current_page_object", fake_policy)

    script = asyncio.run(script_module.read_current_script(None))
    policy = asyncio.run(policy_module.read_current_policy(None))

    assert script["success"] is True
    assert "complete-script" in script["output"]
    assert script["script"]["content"].endswith("'complete-script'")
    assert policy["success"] is True
    assert "complete_policy_rule" in policy["output"]
    assert policy["policy"]["definition"]["severity"] == "HIGH"


def test_policy_page_tool_rejects_deceptive_cost_category_prefix(
    monkeypatch,
) -> None:
    module = _load(
        SKILLS_ROOT
        / "optimization-policy-designer"
        / "scripts"
        / "read_current_policy.py",
        "read_current_policy_category_contract",
    )

    async def fake_policy(_ctx, **_kwargs):
        return {
            "id": POLICY_ID,
            "name": "Wrong category",
            "category": "COST-OPTIMIZATIONX.MACHINE",
            "ruleContent": "return unsafe_match",
        }

    monkeypatch.setattr(module, "fetch_current_page_object", fake_policy)
    result = asyncio.run(module.read_current_policy(None))

    assert result["success"] is False
    assert "not a SmartCMP cost-optimization policy" in result["error"]


@pytest.mark.parametrize(
    "rule_fields",
    [
        {},
        {"ruleContent": {"source": "unexpected-object"}},
    ],
    ids=["missing", "non-string"],
)
def test_policy_page_tool_requires_string_rule_content(
    monkeypatch,
    rule_fields: dict[str, object],
) -> None:
    module = _load(
        SKILLS_ROOT
        / "optimization-policy-designer"
        / "scripts"
        / "read_current_policy.py",
        f"read_current_policy_rule_{len(rule_fields)}",
    )

    async def fake_policy(_ctx, **_kwargs):
        return {
            "id": POLICY_ID,
            "name": "Invalid rule",
            "category": "COST-OPTIMIZATION.MACHINE",
            **rule_fields,
        }

    monkeypatch.setattr(module, "fetch_current_page_object", fake_policy)
    result = asyncio.run(module.read_current_policy(None))

    assert result == {
        "success": False,
        "error": "SmartCMP current policy ruleContent must be a string.",
    }


def test_policy_page_tool_preserves_empty_string_rule_content(
    monkeypatch,
) -> None:
    module = _load(
        SKILLS_ROOT
        / "optimization-policy-designer"
        / "scripts"
        / "read_current_policy.py",
        "read_current_policy_empty_rule_contract",
    )

    async def fake_policy(_ctx, **_kwargs):
        return {
            "id": POLICY_ID,
            "name": "Empty draft",
            "category": "COST-OPTIMIZATION",
            "ruleContent": "",
        }

    monkeypatch.setattr(module, "fetch_current_page_object", fake_policy)
    result = asyncio.run(module.read_current_policy(None))

    assert result["success"] is True
    assert result["policy"]["definition"]["ruleContent"] == ""


def test_component_page_tool_routes_family_and_requires_exact_file_selection(
    monkeypatch,
) -> None:
    module = _load(
        SKILLS_ROOT
        / "component-script-designer"
        / "scripts"
        / "read_current_component_file.py",
        "read_current_component_contract",
    )

    async def fake_component(_ctx, **_kwargs):
        return {
            "id": COMPONENT_ID,
            "name": "Integration",
            "resourceType": "resource.integration.cmdb.example",
            "parentType": "resource.integration.cmdb",
            "model": {
                "blueprintFiles": [
                    {
                        "path": "scripts/client.py",
                        "type": "PYTHON",
                        "content": "CLIENT_COMPLETE = True",
                    },
                    {
                        "path": "scripts/operation.py",
                        "type": "PYTHON",
                        "content": "OPERATION_COMPLETE = True",
                    },
                    {
                        "path": "README.md",
                        "type": "MARKDOWN",
                        "content": "NOT_A_SCRIPT",
                    },
                    {
                        "path": "scripts/../private.yml",
                        "type": "YAML",
                        "content": "NOT_A_SAFE_PATH",
                    },
                    {
                        "path": "/scripts/absolute.py",
                        "type": "PYTHON",
                        "content": "NOT_A_RELATIVE_PATH",
                    },
                    {
                        "path": "scripts\\windows.py",
                        "type": "PYTHON",
                        "content": "NOT_A_POSIX_PATH",
                    },
                ]
            },
        }

    monkeypatch.setattr(module, "fetch_current_page_object", fake_component)

    listing = asyncio.run(module.read_current_component_file(None))
    assert listing["success"] is True
    assert listing["selection_required"] is True
    assert listing["component"]["componentFamily"] == "integration"
    assert [item["path"] for item in listing["component"]["files"]] == [
        "scripts/client.py",
        "scripts/operation.py",
    ]
    assert listing["component"]["files"][0]["size"] == len(
        "CLIENT_COMPLETE = True".encode("utf-8")
    )

    selected = asyncio.run(
        module.read_current_component_file(None, file_path="scripts/operation.py")
    )
    assert selected["success"] is True
    assert "OPERATION_COMPLETE = True" in selected["output"]
    assert selected["component"]["selectedFile"]["path"] == "scripts/operation.py"

    missing = asyncio.run(
        module.read_current_component_file(None, file_path="scripts/missing.py")
    )
    assert missing["success"] is False
    assert len(missing["available_files"]) == 2

    unsafe = asyncio.run(
        module.read_current_component_file(None, file_path="scripts/../private.yml")
    )
    assert unsafe["success"] is False


@pytest.mark.parametrize(
    ("resource_type", "expected_family"),
    [
        (
            "resource.agent.monitoring_agent.prometheus_exporter.node",
            "exporter",
        ),
        ("resource.agent.monitoring_agent.prometheus_exporter", "exporter"),
        ("resource.agent.monitoring_agent.prometheus_exporter_backup", ""),
        ("resource.integration.monitoring.exporter_service", "integration"),
        ("resource.software.exporter_console", "software"),
        ("resource.iaas.machine.instance", "resource"),
        ("resource.unknown.exporter", ""),
    ],
)
def test_component_family_uses_authoritative_resource_type_prefixes(
    resource_type: str,
    expected_family: str,
) -> None:
    module = _load(
        SKILLS_ROOT
        / "component-script-designer"
        / "scripts"
        / "read_current_component_file.py",
        f"read_current_component_family_{expected_family or 'unsupported'}",
    )

    assert module._component_family(resource_type) == expected_family


def test_form_design_script_loads_shared_siblings_without_pythonpath(
    tmp_path: Path,
) -> None:
    """Script-wrapper execution must resolve shared helpers in a clean child process."""
    script = SKILLS_ROOT / "form-designer" / "scripts" / "design_form.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--mode",
            "new",
            "--schema-json",
            (
                '{"type":"object","widget":{"id":"object"},'
                '"properties":{"name":{"type":"string","widget":{"id":"string"}}},'
                '"fieldsets":[{"id":"fieldset-default","fields":["name"]}]}'
            ),
        ],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert '"name"' in result.stdout


def test_page_designer_skills_keep_first_phase_and_component_runtime_contracts() -> None:
    script_skill = (
        SKILLS_ROOT / "script-designer" / "SKILL.md"
    ).read_text(encoding="utf-8")
    component_rules = (
        SKILLS_ROOT
        / "component-script-designer"
        / "references"
        / "component-script-rules.md"
    ).read_text(encoding="utf-8")

    assert "all fields except `content` are read-only" in script_skill
    assert "only generates `content`" in script_skill
    for marker in (
        "script.script_runner.tasks.run",
        "host_agent",
        "set_output key=value",
        "Python 2.7",
        "main()",
        "`connectionConfig`",
        "`params`",
        "`pysdx ctx`",
        "central_deployment_agent",
        "ctx.node.properties.resource_config",
        "runtime-property keys",
    ):
        assert marker in component_rules
