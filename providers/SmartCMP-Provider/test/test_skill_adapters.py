"""Focused contracts for consolidated AtlasClaw SmartCMP Skill adapters."""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from smartcmp_provider.models.approvals import (
    ApprovalDecisionItem,
    ApprovalDecisionResult,
)
from smartcmp_provider.models.catalogs import (
    CatalogItemsResult,
    CatalogListResult,
)
from smartcmp_provider.models.forms import FormDesignResult, FormReadResult
from smartcmp_provider.models.requests import (
    RequestSubmissionItem,
    RequestSubmissionResult,
)


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = PROVIDER_ROOT / "skills"


def _load(path: Path, module_name: str) -> Any:
    """Load one Skill adapter with the same script-directory import semantics."""

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


def _frontmatter(skill_file: Path) -> dict[str, Any]:
    """Parse one SKILL frontmatter mapping."""

    text = skill_file.read_text(encoding="utf-8-sig")
    assert text.startswith("---\n")
    return yaml.safe_load(text.split("---", 2)[1])


def _ctx(
    *,
    instance: dict[str, Any],
    cookies: dict[str, str] | None = None,
    robot_profile: str = "",
) -> SimpleNamespace:
    """Build a minimal AtlasClaw request Context for adapter contracts."""

    return SimpleNamespace(
        deps=SimpleNamespace(
            cookies=cookies or {},
            user_info=SimpleNamespace(user_id="user-1"),
            extra={
                "provider_instance_name": "default",
                "provider_instance": instance,
                "robot_profile": robot_profile,
                "active_internal_request_trace_id": "trace-1",
                "context": {},
            },
        )
    )


def test_every_registered_tool_uses_a_schema_compatible_callable() -> None:
    """Ensure direct handlers resolve and accept their registered Tool schema."""

    tool_count = 0
    for skill_file in sorted(SKILLS_ROOT.glob("*/SKILL.md")):
        metadata = _frontmatter(skill_file)
        for key, entrypoint in metadata.items():
            if not key.startswith("tool_") or not key.endswith("_entrypoint"):
                continue
            tool_count += 1
            module_path, separator, handler_name = str(entrypoint).partition(":")
            assert separator == ":"
            target = (skill_file.parent / module_path).resolve()
            assert target.is_file(), f"Missing Tool entrypoint: {entrypoint}"
            module = _load(
                target,
                f"test_entrypoint_{tool_count}_{target.parent.parent.name}",
            )
            handler = getattr(module, handler_name, None)
            assert callable(handler)

            tool_id = key[len("tool_") : -len("_entrypoint")]
            raw_schema = metadata.get(f"tool_{tool_id}_parameters") or {}
            schema = (
                yaml.safe_load(raw_schema) or {}
                if isinstance(raw_schema, str)
                else raw_schema
            )
            properties = set(schema.get("properties", {}))
            signature = inspect.signature(handler)
            context_parameter = signature.parameters.get("ctx")
            assert context_parameter is not None, (
                f"{entrypoint} must accept AtlasClaw RunContext"
            )
            assert "RunContext" in str(context_parameter.annotation), (
                f"{entrypoint} must annotate ctx with RunContext[...]"
            )
            parameters = {
                name: parameter
                for name, parameter in signature.parameters.items()
                if name != "ctx"
            }
            accepts_kwargs = any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in parameters.values()
            )
            if not accepts_kwargs:
                assert properties <= set(parameters), (
                    f"{entrypoint} does not accept schema fields "
                    f"{sorted(properties - set(parameters))}"
                )
            required_handler_parameters = {
                name
                for name, parameter in parameters.items()
                if parameter.default is inspect.Parameter.empty
                and parameter.kind
                not in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                )
            }
            assert required_handler_parameters <= properties, (
                f"{entrypoint} requires unregistered fields "
                f"{sorted(required_handler_parameters - properties)}"
            )
    assert tool_count == 51


def test_multi_tool_skills_use_one_adapter_entrypoint_module() -> None:
    """Keep helper modules only where they have an independent internal role."""

    expected = {
        "alarm",
        "approval",
        "cost-optimization",
        "datasource",
        "form-designer",
        "request",
        "resource",
    }
    for skill_name in expected:
        metadata = _frontmatter(SKILLS_ROOT / skill_name / "SKILL.md")
        owned_entrypoints = {
            str(value).split(":", 1)[0]
            for key, value in metadata.items()
            if key.startswith("tool_")
            and key.endswith("_entrypoint")
            and not str(value).startswith("../")
        }
        assert owned_entrypoints == {"scripts/adapter.py"}


def test_approval_analysis_returns_to_llm_for_visible_guidance() -> None:
    """Keep structured analysis evidence available for final synthesis."""

    metadata = _frontmatter(SKILLS_ROOT / "approval" / "SKILL.md")

    assert metadata["tool_analyze_result_mode"] == "llm"


def test_atlasclaw_auth_context_distinguishes_cookie_user_and_webhook_robot() -> None:
    """Preserve AtlasClaw Cookie and webhook provider-token authentication."""

    runtime = _load(
        SKILLS_ROOT / "shared" / "scripts" / "_atlasclaw_adapter.py",
        "test_atlasclaw_adapter_auth",
    )
    user_request = runtime.selected_provider_request(
        _ctx(
            instance={
                "base_url": "https://cmp.example.com",
                "auth_type": "cookie",
            },
            cookies={"CloudChef-Authenticate": "user-session"},
        )
    )
    assert user_request.context.principal.actor_type == "user"
    assert user_request.credential.headers()["CloudChef-Authenticate"] == (
        "user-session"
    )

    robot_request = runtime.selected_provider_request(
        _ctx(
            instance={
                "base_url": "https://cmp.example.com",
                "auth_type": "provider_token",
                "provider_token": "cmp_tk_robot",
            },
            cookies={"CloudChef-Authenticate": "must-not-win"},
            robot_profile="approval-bot",
        )
    )
    assert robot_request.context.principal.actor_type == "robot"
    assert robot_request.context.principal.client_id == "approval-bot"
    assert robot_request.credential.headers()["Authorization"] == (
        "Bearer cmp_tk_robot"
    )

    page_request = runtime.selected_provider_request(
        _ctx(
            instance={
                "base_url": "https://cmp.example.com",
                "auth_type": "provider_token",
                "provider_token": "cmp_tk_shared",
            },
            cookies={"CloudChef-Authenticate": "page-user-session"},
        ),
        request_cookie_only=True,
    )
    assert page_request.credential.headers()["CloudChef-Authenticate"] == (
        "page-user-session"
    )
    assert "Authorization" not in page_request.credential.headers()


def test_embedded_object_uses_server_owned_turn_context() -> None:
    """Read the exact page object from AtlasClaw's current Context contract."""

    runtime = _load(
        SKILLS_ROOT / "shared" / "scripts" / "_atlasclaw_adapter.py",
        "test_atlasclaw_adapter_turn_context",
    )
    context = _ctx(
        instance={
            "base_url": "https://cmp.example.com",
            "auth_type": "cookie",
        },
        cookies={"CloudChef-Authenticate": "page-user-session"},
    )
    context.deps.extra["context"]["turn_context"] = {
        "object": {
            "type": "form_definition",
            "id": "0897C154-3C46-414E-906E-2A7277F8DEF2",
        },
        "default_skill": {
            "provider_type": "smartcmp",
            "provider_instance": "default",
        },
    }

    assert runtime.embedded_object_id(
        context,
        expected_object_type="form_definition",
    ) == "0897c154-3c46-414e-906e-2a7277f8def2"


def test_blueprint_component_context_calls_component_provider_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Translate the page object type without rejecting the Component Tool."""

    handler = _load(
        SKILLS_ROOT
        / "component-script-designer"
        / "scripts"
        / "read_current_component_file.py",
        "test_component_page_context",
    )
    captured: dict[str, str] = {}

    async def fake_fetch(
        _ctx: Any,
        *,
        expected_object_type: str,
        api_collection: str,
    ) -> dict[str, Any]:
        captured["object_type"] = expected_object_type
        captured["collection"] = api_collection
        return {
            "id": "010c8da0-9866-4b32-bbff-72f3d49efb4e",
            "name": "CMDB",
            "resourceType": "resource.integration.cmdb.example",
            "model": {
                "blueprintFiles": [
                    {
                        "path": "scripts/client.py",
                        "type": "PYTHON",
                        "content": "READY = True",
                    }
                ]
            },
        }

    monkeypatch.setattr(handler, "fetch_current_page_object", fake_fetch)

    result = asyncio.run(handler.read_current_component_file(object()))

    assert result["success"] is True
    assert captured == {
        "object_type": "blueprint_component",
        "collection": "components",
    }

    current_page = _load(
        SKILLS_ROOT / "shared" / "scripts" / "_current_page_object.py",
        "test_component_provider_type_translation",
    )
    provider_query: dict[str, str] = {}

    class FakeClient:
        def __init__(self, _request: Any) -> None:
            pass

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

    async def fake_get_object(_client: Any, query: Any) -> Any:
        provider_query["object_type"] = query.object_type
        return SimpleNamespace(payload={"id": query.object_id})

    monkeypatch.setattr(
        current_page,
        "_current_scope",
        lambda *_args, **_kwargs: (
            "010c8da0-9866-4b32-bbff-72f3d49efb4e",
            object(),
        ),
    )
    monkeypatch.setattr(current_page, "SmartCmpClient", FakeClient)
    monkeypatch.setattr(current_page, "get_object_by_id", fake_get_object)

    asyncio.run(
        current_page.fetch_current_page_object(
            object(),
            expected_object_type="blueprint_component",
            api_collection="components",
        )
    )

    assert provider_query["object_type"] == "component_definition"


def test_explicit_credential_auth_is_not_replaced_by_request_cookie(
    monkeypatch,
) -> None:
    """Keep service credentials isolated from an interactive browser session."""

    runtime = _load(
        SKILLS_ROOT / "shared" / "scripts" / "_atlasclaw_adapter.py",
        "test_atlasclaw_adapter_credential_identity",
    )
    monkeypatch.setattr(
        "smartcmp_provider.auth.resolver.login_with_password",
        lambda *_args, **_kwargs: "credential-login-session",
    )

    request = runtime.selected_provider_request(
        _ctx(
            instance={
                "base_url": "https://cmp.example.com",
                "auth_type": "credential",
                "username": "service-user",
                "password": "service-password",
            },
            cookies={"CloudChef-Authenticate": "browser-user-session"},
        )
    )

    assert request.credential.headers()["CloudChef-Authenticate"] == (
        "credential-login-session"
    )


def test_atlasclaw_result_omits_mcp_specific_operation_arguments() -> None:
    """Do not advertise MCP argument schemas through AtlasClaw Tool results."""

    runtime = _load(
        SKILLS_ROOT / "shared" / "scripts" / "_atlasclaw_adapter.py",
        "test_atlasclaw_adapter_operation_boundary",
    )
    result = runtime.tool_result(
        {
            "request_id": "RES20260731000001",
            "available_operations": [
                {
                    "tool_name": "smartcmp_approve",
                    "arguments": {"request_ids": ["RES20260731000001"]},
                }
            ],
            "nested": {
                "available_operations": [
                    {
                        "tool_name": "smartcmp_get_request_detail",
                        "arguments": {"request_id": "RES20260731000001"},
                    }
                ]
            },
        },
        summary="approval",
        internal={
            "request_id": "RES20260731000001",
            "available_operations": [
                {
                    "tool_name": "smartcmp_approve",
                    "arguments": {"request_ids": ["RES20260731000001"]},
                }
            ],
        },
    )

    assert "available_operations" not in result
    assert "available_operations" not in result["nested"]
    assert "available_operations" not in result["_internal"]


@pytest.mark.parametrize(
    "auth_type",
    [
        "providre_token",
        ["cookie", "provider_token"],
    ],
)
def test_atlasclaw_auth_context_rejects_unsupported_mode(
    auth_type: object,
) -> None:
    """Reject misspelled or multi-mode auth instead of silently falling back."""

    runtime = _load(
        SKILLS_ROOT / "shared" / "scripts" / "_atlasclaw_adapter.py",
        "test_atlasclaw_adapter_invalid_auth",
    )
    with pytest.raises(
        runtime.AtlasClawAdapterError,
        match="Unsupported SmartCMP auth_type",
    ):
        runtime.selected_provider_request(
            _ctx(
                instance={
                    "base_url": "https://cmp.example.com",
                    "auth_type": auth_type,
                    "provider_token": "cmp_tk_must_not_be_used",
                },
            )
        )


def test_approval_adapter_builds_one_typed_decision(monkeypatch) -> None:
    """Verify the consolidated approval handler delegates one confirmed write."""

    adapter = _load(
        SKILLS_ROOT / "approval" / "scripts" / "adapter.py",
        "test_approval_adapter",
    )
    captured: dict[str, Any] = {}

    async def fake_execute(_ctx, operation, operation_input):
        captured["operation"] = operation
        captured["input"] = operation_input
        return ApprovalDecisionResult(
            decision="approve",
            reason="policy accepted",
            items=(
                ApprovalDecisionItem(
                    request_id="RES20260731000001",
                    outcome="succeeded",
                ),
            ),
            overall_success=True,
        )

    monkeypatch.setattr(adapter, "execute", fake_execute)
    result = asyncio.run(
        adapter.approve(
            object(),
            "RES20260731000001",
            reason="policy accepted",
        )
    )

    assert result["success"] is True
    assert captured["input"].request_ids == ("RES20260731000001",)
    assert captured["input"].reason == "policy accepted"


def test_request_adapter_parses_confirmed_json_once(monkeypatch) -> None:
    """Verify request submission passes one typed body to SmartCMP Provider."""

    adapter = _load(
        SKILLS_ROOT / "request" / "scripts" / "adapter.py",
        "test_request_adapter",
    )
    captured: dict[str, Any] = {}

    async def fake_execute(_ctx, operation, operation_input):
        captured["operation"] = operation
        captured["input"] = operation_input
        return RequestSubmissionResult(
            normalized_body={
                **operation_input.body,
                "credentialPassword": "vm-secret",
                "nested": {"password": "nested-secret"},
            },
            items=(
                RequestSubmissionItem(
                    outcome="success",
                    request_id="RES20260731000002",
                ),
            ),
        )

    monkeypatch.setattr(adapter, "execute", fake_execute)
    result = asyncio.run(
        adapter.submit(
            object(),
            '{"catalogId":"catalog-1","name":"vm-request"}',
        )
    )

    assert result["success"] is True
    assert captured["input"].body["catalogId"] == "catalog-1"
    assert "RES20260731000002" in result["output"]
    assert result["normalized_body"]["credentialPassword"] == "***"
    assert result["normalized_body"]["nested"]["password"] == "***"
    assert "vm-secret" not in result["_internal"]
    assert "nested-secret" not in result["_internal"]


def test_form_adapter_normalizes_omitted_optional_strings(monkeypatch) -> None:
    """Accept AtlasClaw's null optional fields without weakening Provider models."""

    adapter = _load(
        SKILLS_ROOT / "form-designer" / "scripts" / "adapter.py",
        "test_form_adapter_optional_strings",
    )
    captured: dict[str, Any] = {}

    async def fake_execute(
        _ctx,
        _operation,
        operation_input,
        *,
        request_cookie_only,
    ):
        captured["input"] = operation_input
        captured["request_cookie_only"] = request_cookie_only
        return FormDesignResult(
            mode="modify",
            source={"formId": "form-1", "name": "test-form"},
            warnings=(),
            changeSummary="",
            schema={"type": "object"},
        )

    monkeypatch.setattr(adapter, "embedded_object_id", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(adapter, "execute", fake_execute)
    result = asyncio.run(
        adapter.design_form(
            object(),
            "modify",
            schema_json='{"type":"object"}',
            form_url=None,
            change_summary=None,
            catalog_fields_json=None,
            value_expressions_json=None,
            requested_fields_json=None,
        )
    )

    assert result["success"] is True
    assert captured["input"].catalog_fields_json == ""
    assert captured["input"].value_expressions_json == ""
    assert captured["input"].requested_fields_json == ""
    assert "## 4. Complete Replacement JSON" in result["output"]
    assert '"type": "object"' in result["output"]
    assert "Not saved" in result["output"]
    assert result["final_user_output"] == result["output"]


def test_form_read_adapter_passes_editor_url_to_provider(monkeypatch) -> None:
    """Keep URL provenance intact until Provider validates route and origin."""

    adapter = _load(
        SKILLS_ROOT / "form-designer" / "scripts" / "adapter.py",
        "test_form_adapter_url_provenance",
    )
    captured: dict[str, Any] = {}
    form_url = (
        "https://cmp.example.com/#/main/service-model/forms/design/"
        "123e4567-e89b-12d3-a456-426614174000"
    )

    async def fake_execute(
        _ctx,
        _operation,
        operation_input,
        *,
        request_cookie_only,
    ):
        captured["input"] = operation_input
        captured["request_cookie_only"] = request_cookie_only
        return FormReadResult(
            form_id="123e4567-e89b-12d3-a456-426614174000",
            name="Design form",
            description="",
            schema={"type": "object"},
            model={},
            design_mode="schema",
            component_count=0,
            source_route="design",
        )

    monkeypatch.setattr(adapter, "embedded_object_id", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(adapter, "execute", fake_execute)

    result = asyncio.run(adapter.read_form(object(), form_url))

    assert result["success"] is True
    assert captured["input"].form_url == form_url
    assert captured["input"].form_id == ""
    assert captured["request_cookie_only"] is False


def test_execute_resolves_password_credentials_without_blocking_event_loop(
    monkeypatch,
) -> None:
    """Keep synchronous SmartCMP login outside AtlasClaw's async scheduler."""

    runtime = _load(
        SKILLS_ROOT / "shared" / "scripts" / "_atlasclaw_adapter.py",
        "test_atlasclaw_adapter_async_resolution",
    )

    def slow_resolve(_ctx, *, request_cookie_only=False):
        del request_cookie_only
        time.sleep(0.05)
        return "resolved"

    monkeypatch.setattr(runtime, "selected_provider_request", slow_resolve)

    async def scenario() -> list[str]:
        order: list[str] = []
        resolution = asyncio.create_task(
            runtime.resolve_selected_provider_request(object())
        )
        await asyncio.sleep(0)
        order.append("event-loop-progressed")
        assert await resolution == "resolved"
        order.append("authentication-resolved")
        return order

    assert asyncio.run(scenario()) == [
        "event-loop-progressed",
        "authentication-resolved",
    ]


def test_request_catalog_chat_result_restores_atlasclaw_object_actions(
    monkeypatch,
) -> None:
    """Keep UI actions in the AtlasClaw adapter and outside SmartCMP Provider."""

    adapter = _load(
        SKILLS_ROOT / "request" / "scripts" / "adapter.py",
        "test_request_catalog_object_actions",
    )

    async def fake_execute_with_request(_ctx, _operation, _operation_input):
        result = CatalogListResult(
            catalogs=(
                {
                    "id": "catalog-1",
                    "name": "LinuxOS",
                    "status": "PUBLISHED",
                },
            ),
            total=1,
        )
        request = SimpleNamespace(
            context=SimpleNamespace(
                instance=SimpleNamespace(ui_base_url="https://cmp.example.com")
            )
        )
        return result, request

    monkeypatch.setattr(
        adapter,
        "execute_with_request",
        fake_execute_with_request,
    )
    result = asyncio.run(adapter.list_services(object(), keyword=None))

    actions = result["catalogs"][0]["object_actions"]
    assert [action["action_id"] for action in actions] == [
        "open_detail",
        "request",
    ]
    assert actions[0]["href"] == (
        "https://cmp.example.com/#/main/catalog-ui/request/catalog-1"
    )


def test_datasource_adapter_normalizes_optional_logical_template_fields(
    monkeypatch,
) -> None:
    """Keep explicit AtlasClaw nulls outside the strict Provider query model."""

    adapter = _load(
        SKILLS_ROOT / "datasource" / "scripts" / "adapter.py",
        "test_datasource_logical_template_adapter",
    )
    captured: dict[str, Any] = {}

    async def fake_execute(_ctx, operation, operation_input):
        captured["operation"] = operation
        captured["input"] = operation_input
        return CatalogItemsResult()

    monkeypatch.setattr(adapter, "execute", fake_execute)
    result = asyncio.run(
        adapter.list_logical_templates(
            object(),
            query=None,
            resource_bundle_id=None,
            catalog_id=None,
            node_template_name=None,
            os_type=None,
        )
    )

    assert result["success"] is True
    assert captured["input"].query_value == ""
    assert captured["input"].resource_bundle_id == ""
    assert captured["input"].catalog_id == ""
    assert captured["input"].node_template_name == ""
    assert captured["input"].os_type == ""
