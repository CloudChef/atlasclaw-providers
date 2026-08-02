# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

import hashlib
import importlib.util
import json
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
EXPECTED_PROVIDER_SCHEMA_SHA256 = (
    "6fc94545693692adf22cf0ccb2be9466a71cef465fc8c5719f2a43cacb29539c"
)
EXPECTED_SKILL_METADATA_SHA256 = (
    "984e3bafad5a3f959397aa23822fe54378f4234f0aa55b6f9467b5281f32ab1a"
)
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
    "resource-compliance/SKILL.md",
    "resource-pool/SKILL.md",
    "resource/SKILL.md",
    "script-designer/SKILL.md",
}
EXPECTED_TOOL_NAMES = {
    "analyze_resource_health",
    "smartcmp_analyze_alert",
    "smartcmp_analyze_approval_request",
    "smartcmp_analyze_cost_recommendation",
    "smartcmp_analyze_resource_compliance",
    "smartcmp_analyze_resource_cost",
    "smartcmp_approve",
    "smartcmp_design_form_schema",
    "smartcmp_execute_cost_optimization",
    "smartcmp_get_request_catalog",
    "smartcmp_get_request_detail",
    "smartcmp_get_request_status",
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
    "smartcmp_list_services",
    "smartcmp_operate_alert",
    "smartcmp_operate_resource",
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
    "smartcmp_resource_analyze_compliance",
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


def test_provider_and_skill_metadata_match_p0_compatibility_snapshot() -> None:
    provider_schema_digest = hashlib.sha256(
        (PROVIDER_ROOT / "provider.schema.json").read_bytes()
    ).hexdigest()
    frontmatters = _skill_frontmatters()
    normalized_metadata = json.dumps(
        frontmatters,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    skill_metadata_digest = hashlib.sha256(normalized_metadata).hexdigest()
    tool_names = _tool_names(frontmatters)

    assert set(frontmatters) == EXPECTED_SKILL_PATHS
    assert len(tool_names) == len(set(tool_names)) == 51
    assert set(tool_names) == EXPECTED_TOOL_NAMES
    assert provider_schema_digest == EXPECTED_PROVIDER_SCHEMA_SHA256
    assert skill_metadata_digest == EXPECTED_SKILL_METADATA_SHA256


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
