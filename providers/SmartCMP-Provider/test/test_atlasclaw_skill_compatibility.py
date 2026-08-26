# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

import importlib.util
import sys
import tomllib
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Iterator

import pytest
import yaml
from pydantic import BaseModel

PROVIDER_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = PROVIDER_ROOT / "skills"
BOOTSTRAP_PATH = SKILLS_ROOT / "shared" / "scripts" / "_provider_bootstrap.py"
EXPECTED_SKILL_PATHS = {
    "alarm/SKILL.md",
    "approval/SKILL.md",
    "component-script-designer/SKILL.md",
    "cost-optimization/SKILL.md",
    "datasource/SKILL.md",
    "form-designer/SKILL.md",
    "optimization-policy-designer/SKILL.md",
    "preapproval-agent/SKILL.md",
    "request-decomposition-agent/SKILL.md",
    "request/SKILL.md",
    "resource-pool/SKILL.md",
    "resource/SKILL.md",
    "script-designer/SKILL.md",
    "security-compliance/SKILL.md",
}
EXPECTED_TOOL_NAMES = {
    "analyze_resource_health",
    "smartcmp_analyze_alert",
    "smartcmp_analyze_approval_request",
    "smartcmp_analyze_cost_recommendation",
    "smartcmp_analyze_resource_cost",
    "smartcmp_analyze_resource_security",
    "smartcmp_analyze_security_violation",
    "smartcmp_approve",
    "smartcmp_design_form_schema",
    "smartcmp_execute_cost_optimization",
    "smartcmp_get_request_catalog",
    "smartcmp_get_request_detail",
    "smartcmp_get_request_status",
    "smartcmp_get_security_overview",
    "smartcmp_list_alerts",
    "smartcmp_list_all_business_groups",
    "smartcmp_list_all_resource",
    "smartcmp_list_all_resource_pools",
    "smartcmp_list_applications",
    "smartcmp_list_available_bgs",
    "smartcmp_list_components",
    "smartcmp_list_cost_recommendations",
    "smartcmp_list_facets",
    "smartcmp_list_flavors",
    "smartcmp_list_images",
    "smartcmp_list_logical_templates",
    "smartcmp_list_pending",
    "smartcmp_list_physical_templates",
    "smartcmp_list_resource_bundles",
    "smartcmp_list_resource_operations",
    "smartcmp_list_recycled_resources",
    "smartcmp_list_resource_security_violations",
    "smartcmp_list_security_violations",
    "smartcmp_list_services",
    "smartcmp_mark_security_violation_fixed",
    "smartcmp_operate_alert",
    "smartcmp_operate_resource",
    "smartcmp_permanently_remove_recycled_resource",
    "smartcmp_preapproval_analyze_request",
    "smartcmp_preapproval_approve",
    "smartcmp_preapproval_get_catalog_detail",
    "smartcmp_preapproval_get_request_detail",
    "smartcmp_preapproval_reject",
    "smartcmp_query_images",
    "smartcmp_query_logical_templates",
    "smartcmp_read_current_component_file",
    "smartcmp_read_current_form_schema",
    "smartcmp_read_current_optimization_policy",
    "smartcmp_read_current_script_definition",
    "smartcmp_read_form_schema",
    "smartcmp_reject",
    "smartcmp_resource_analyze_alerts",
    "smartcmp_resource_analyze_cost",
    "smartcmp_resource_analyze_health",
    "smartcmp_resource_detail",
    "smartcmp_submit_request",
    "smartcmp_track_cost_optimization",
}


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8-sig")
    parts = text.split("---", 2)
    assert len(parts) == 3, f"{path}: missing YAML frontmatter boundary"
    return yaml.safe_load(parts[1]) or {}


def _skill_frontmatters() -> dict[str, dict]:
    return {
        path.relative_to(SKILLS_ROOT).as_posix(): _frontmatter(path)
        for path in sorted(SKILLS_ROOT.glob("*/SKILL.md"))
    }


def _tool_names(frontmatters: dict[str, dict]) -> list[str]:
    return [
        value
        for metadata in frontmatters.values()
        for key, value in metadata.items()
        if key.startswith("tool_") and key.endswith("_name")
    ]


def _load_bootstrap() -> ModuleType:
    module_name = "_smartcmp_provider_bootstrap_test"
    spec = importlib.util.spec_from_file_location(module_name, BOOTSTRAP_PATH)
    assert spec is not None and spec.loader is not None
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    return bootstrap


@pytest.fixture
def isolated_provider_import() -> Iterator[ModuleType]:
    original_path = list(sys.path)
    original_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "smartcmp_provider" or name.startswith("smartcmp_provider.")
    }
    for module_name in original_modules:
        sys.modules.pop(module_name, None)

    try:
        yield _load_bootstrap()
    finally:
        for module_name in list(sys.modules):
            if module_name == "smartcmp_provider" or module_name.startswith(
                "smartcmp_provider."
            ):
                sys.modules.pop(module_name, None)
        sys.modules.update(original_modules)
        sys.path[:] = original_path


def test_provider_package_declares_stable_build_contract() -> None:
    pyproject = tomllib.loads((PROVIDER_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["name"] == "smartcmp-provider"
    assert pyproject["project"]["version"] == "1.0.0"
    assert pyproject["project"]["requires-python"] == ">=3.11"
    assert pyproject["tool"]["setuptools"]["packages"]["find"]["where"] == ["src"]


def test_skill_metadata_keeps_expected_tool_contract() -> None:
    frontmatters = _skill_frontmatters()
    tool_names = _tool_names(frontmatters)

    assert set(frontmatters) == EXPECTED_SKILL_PATHS
    assert len(tool_names) == len(set(tool_names))
    assert set(tool_names) == EXPECTED_TOOL_NAMES


def test_security_mark_fixed_metadata_requires_explicit_confirmation() -> None:
    """Keep the status-write confirmation required without a false default."""

    metadata = _frontmatter(SKILLS_ROOT / "security-compliance" / "SKILL.md")
    parameters = yaml.safe_load(metadata["tool_mark_fixed_parameters"])

    assert "confirmed" in parameters["required"]
    assert "default" not in parameters["properties"]["confirmed"]


def test_security_and_resource_natural_language_routing_metadata_is_distinct() -> None:
    """Declare deterministic ownership for representative Security prompts.

    Skill selection is performed by the LLM from metadata rather than by a
    deterministic NLP router, so this test verifies the exact trigger and
    avoid-contract evidence supplied to that selection step.
    """

    frontmatters = _skill_frontmatters()
    owners = {
        "security-compliance/SKILL.md": (
            "查看全部安全违规",
            "分析第 1 条违规",
        ),
        "resource/SKILL.md": (
            "分析 VM 安全",
            "资源综合分析",
        ),
    }
    for owner, prompts in owners.items():
        other = next(candidate for candidate in owners if candidate != owner)
        owner_triggers = set(frontmatters[owner]["triggers"])
        other_triggers = set(frontmatters[other]["triggers"])
        assert set(prompts) <= owner_triggers
        assert not set(prompts) & other_triggers

    security_avoid = " ".join(frontmatters["security-compliance/SKILL.md"]["avoid_when"])
    resource_avoid = " ".join(frontmatters["resource/SKILL.md"]["avoid_when"])
    assert "named or selected resource" in security_avoid
    assert "global violation list" in resource_avoid


def test_resource_skill_binds_bare_page_actions_without_redundant_confirmation(
) -> None:
    """Keep current-page target inheritance distinct from write confirmation."""
    resource_skill = (SKILLS_ROOT / "resource" / "SKILL.md").read_text(
        encoding="utf-8-sig"
    )

    assert "supported action without naming another target" in resource_skill
    assert "Treat the omitted target as the current page resource" in resource_skill
    assert "do not ask whether the user meant the current resource" in resource_skill
    assert "binds the target but does not confirm the operation" in resource_skill
    assert "Treat the target as already resolved" in resource_skill
    assert "Confirm restart on MyBG3409?" in resource_skill
    assert (
        "Never phrase the combined confirmation as target clarification"
        in resource_skill
    )
    assert "Do you want to restart the resource currently shown?" in resource_skill
    assert "do not ask a separate target question" in resource_skill
    assert "a later exact command" in resource_skill
    assert "Proceed to submission in that turn" in resource_skill


def test_atlasclaw_bootstrap_imports_colocated_provider_without_config(
    monkeypatch: pytest.MonkeyPatch,
    isolated_provider_import: ModuleType,
) -> None:
    monkeypatch.setenv("ATLASCLAW_PROVIDER_CONFIG", "{invalid-json")
    monkeypatch.setenv("ATLASCLAW_COOKIES", "{invalid-json")
    bootstrap = isolated_provider_import
    source_path = bootstrap.provider_src()
    sys.path.append(str(source_path))

    assert bootstrap.ensure_provider_importable() == source_path
    provider_package = bootstrap.load_provider()

    assert source_path == PROVIDER_ROOT / "src"
    assert sys.path[0] == str(source_path)
    assert Path(provider_package.__file__).resolve().is_relative_to(source_path)
    assert sys.path.count(str(source_path)) == 1


def test_atlasclaw_bootstrap_rejects_preloaded_external_provider(
    isolated_provider_import: ModuleType,
) -> None:
    external_provider = ModuleType("smartcmp_provider")
    external_provider.__file__ = "/tmp/external-provider/smartcmp_provider/__init__.py"
    sys.modules["smartcmp_provider"] = external_provider

    with pytest.raises(RuntimeError, match="non-colocated SmartCMP Provider"):
        isolated_provider_import.load_provider()


def test_provider_contracts_are_request_scoped_and_immutable(
    isolated_provider_import: ModuleType,
) -> None:
    provider_package = isolated_provider_import.load_provider()
    CapabilitySpec = provider_package.CapabilitySpec
    ExecutionContext = provider_package.ExecutionContext
    Principal = provider_package.Principal
    SmartCmpInstance = provider_package.SmartCmpInstance

    class EmptyInput(BaseModel):
        pass

    class EmptyOutput(BaseModel):
        pass

    principal = Principal(subject="user-1", actor_type="user", scopes=frozenset({"read"}))
    instance = SmartCmpInstance(name="cmp-a", base_url="https://cmp-a.example")
    context = ExecutionContext(
        principal=principal,
        instance=instance,
        trace_id="trace-1",
        deadline=datetime.now(UTC),
    )
    capability = CapabilitySpec(
        capability_id="resources.list",
        atlasclaw_tool_name="smartcmp_list_all_resource",
        mcp_tool_name=None,
        input_model=EmptyInput,
        output_model=EmptyOutput,
        effect="read",
        idempotency="safe",
        confirmation="none",
        surfaces=frozenset({"atlasclaw"}),
    )

    assert context.principal is principal
    assert context.instance is instance
    assert capability.atlasclaw_tool_name == "smartcmp_list_all_resource"
    with pytest.raises(FrozenInstanceError):
        context.trace_id = "other-trace"  # type: ignore[misc]
