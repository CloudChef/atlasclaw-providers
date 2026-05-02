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
    """After merging resource-power into resource, the SKILL.md must register the power tool."""
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert 'name: "resource"' in skill_text
    assert "tool_power_name:" in skill_text
    assert "tool_power_parameters:" in skill_text
    assert "smartcmp_operate_resource" in skill_text
    assert "do not print raw request or response details" in skill_text


def test_resource_power_script_exists_in_resource_skill():
    """operate_resource.py should now live under resource/scripts/."""
    script_path = SKILL_ROOT / "scripts" / "operate_resource.py"
    assert script_path.exists(), "operate_resource.py should exist under resource/scripts/"


def test_resource_power_entrypoint_imports_cleanly():
    module = load_module(
        "test_resource_power_entrypoint_module",
        SKILL_ROOT / "scripts" / "operate_resource.py",
    )
    assert hasattr(module, "main")


def test_resource_power_referenced_in_provider_docs():
    provider_text = (PROVIDER_ROOT / "PROVIDER.md").read_text(encoding="utf-8")
    assert "smartcmp_operate_resource" in provider_text

    readme_text = (PROVIDER_ROOT / "README.md").read_text(encoding="utf-8")
    assert "operate_resource" in readme_text


def test_old_resource_power_skill_directory_removed():
    """The standalone resource-power skill directory should no longer exist."""
    old_dir = PROVIDER_ROOT / "skills" / "resource-power"
    assert not old_dir.exists(), "resource-power directory should be removed after merge"
