# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

import importlib.util
import sys
from pathlib import Path


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = PROVIDER_ROOT / "skills" / "resource"


def load_module(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


def test_resource_skill_includes_power_tool():
    """The resource skill should register operation discovery and execution tools."""
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert 'name: "resource"' in skill_text
    assert "execute resource operations" in skill_text
    assert "run day-2 changes" in skill_text
    assert "restart" in skill_text
    assert "create snapshot" in skill_text
    assert 'tool_list_result_mode: "llm"' in skill_text
    assert "If the user asked for a resource operation" in skill_text
    assert "tool_operations_name:" in skill_text
    assert "tool_operations_parameters:" in skill_text
    assert 'tool_operations_result_mode: "llm"' in skill_text
    assert "smartcmp_list_resource_operations" in skill_text
    assert "use this result as permission/operation validation evidence" in skill_text
    assert '"resource_name"' in skill_text
    assert '"required": []' in skill_text
    assert "tool_power_name:" in skill_text
    assert "tool_power_parameters:" in skill_text
    assert "smartcmp_operate_resource" in skill_text
    assert "do not print raw request or response details" in skill_text


def test_resource_skill_explains_operation_workflow_after_lookup():
    """Operation commands should continue after resource lookup instead of ending with a list."""
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert "## Operation Workflow" in skill_text
    assert "When operation intent is present" in skill_text
    assert "Do not stop at the `smartcmp_list_all_resource` visible list output" in skill_text
    assert "action + index + name" in skill_text
    assert "stop 1 vm-a" in skill_text
    assert "LinUx-testd" not in skill_text
    assert "use `resource_name` for name-based detail inspection" in skill_text
    assert "call `smartcmp_resource_detail` with `resource_name` directly" in skill_text
    assert "Do not call `smartcmp_list_all_resource` first just to resolve or display the name" in skill_text
    assert "latest explicit operation command supersedes older unfinished operation intent" in skill_text
    assert "Confirm this operation?" in skill_text
    assert "确认要执行吗？" not in skill_text


def test_resource_skill_coordinates_comprehensive_read_only_analysis():
    """Overall resource analysis should reuse every owning domain tool."""
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert "## Comprehensive Resource Analysis" in skill_text
    assert "same target for every call" in skill_text
    assert "best-effort" in skill_text
    for tool_name in (
        "smartcmp_resource_analyze_alerts",
        "smartcmp_resource_analyze_health",
        "smartcmp_resource_analyze_compliance",
        "smartcmp_resource_analyze_cost",
    ):
        assert tool_name in skill_text
    for entrypoint in (
        '"../alarm/scripts/list_alerts.py"',
        '"../alarm/scripts/analyze_resource_health.py"',
        '"../resource-compliance/scripts/analyze_resource.py"',
        '"../cost-optimization/scripts/analyze_resource_cost.py"',
    ):
        assert entrypoint in skill_text
    for heading in (
        "资源概况",
        "当前及近期告警",
        "运行健康",
        "合规风险",
        "费用优化",
        "跨维度关联发现",
        "证据缺口",
        "按优先级排列的只读建议",
    ):
        assert heading in skill_text
    assert "no matched resolved alert in the trigger-time lookback" in skill_text
    assert "must not invent a combined" in skill_text
    assert "Do not mute or resolve alerts" in skill_text


def test_resource_operation_list_script_exists_in_resource_skill():
    """list_resource_operations.py should live under resource/scripts/."""
    script_path = SKILL_ROOT / "scripts" / "list_resource_operations.py"
    assert script_path.exists(), "list_resource_operations.py should exist under resource/scripts/"


def test_resource_power_script_exists_in_resource_skill():
    """operate_resource.py should now live under resource/scripts/."""
    script_path = SKILL_ROOT / "scripts" / "operate_resource.py"
    assert script_path.exists(), "operate_resource.py should exist under resource/scripts/"


def test_resource_power_entrypoint_imports_cleanly():
    operations_module = load_module(
        "test_resource_operations_entrypoint_module",
        SKILL_ROOT / "scripts" / "list_resource_operations.py",
    )
    assert hasattr(operations_module, "main")

    module = load_module(
        "test_resource_power_entrypoint_module",
        SKILL_ROOT / "scripts" / "operate_resource.py",
    )
    assert hasattr(module, "main")


def test_resource_detail_uses_view_endpoint(monkeypatch):
    module = load_module(
        "test_resource_detail_entrypoint_module",
        SKILL_ROOT / "scripts" / "resource_detail.py",
    )
    calls = []

    class FakeResponse:
        status_code = 200
        text = "{}"

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "id": "res-1",
                "name": "vm-1",
                "componentType": "resource.iaas.machine.instance.vsphere",
                "status": "started",
                "properties": {"cpu": 2, "memoryInGB": 4},
            }

    def fake_get(*args, **kwargs):
        raise AssertionError("resource_detail must not call GET until the CMP view API bug is fixed")

    def fake_patch(url, *, headers, verify, timeout):
        calls.append(("PATCH", url, headers, verify, timeout))
        return FakeResponse()

    monkeypatch.setattr(module, "require_config", lambda: ("https://cmp.example/platform-api", "", {}, {}))
    monkeypatch.setattr(module.requests, "get", fake_get)
    monkeypatch.setattr(module.requests, "patch", fake_patch)

    assert module.main(["res-1"]) == 0
    assert calls == [("PATCH", "https://cmp.example/platform-api/nodes/res-1/view", {}, False, 60)]


def test_resource_power_referenced_in_provider_docs():
    provider_text = (PROVIDER_ROOT / "PROVIDER.md").read_text(encoding="utf-8")
    assert "smartcmp_list_resource_operations" in provider_text
    assert "smartcmp_operate_resource" in provider_text

    readme_text = (PROVIDER_ROOT / "README.md").read_text(encoding="utf-8")
    assert "list_resource_operations" in readme_text
    assert "operate_resource" in readme_text


def test_old_resource_power_skill_directory_removed():
    """The standalone resource-power skill directory should no longer exist."""
    old_dir = PROVIDER_ROOT / "skills" / "resource-power"
    assert not old_dir.exists(), "resource-power directory should be removed after merge"
