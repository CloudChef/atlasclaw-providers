# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
ALARM_DIR = REPO_ROOT / "providers" / "SmartCMP-Provider" / "skills" / "alarm"
SCRIPTS_DIR = ALARM_DIR / "scripts"


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


def test_alarm_skill_layout():
    assert ALARM_DIR.is_dir(), "alarm skill directory should exist"

    skill_file = ALARM_DIR / "SKILL.md"
    assert skill_file.is_file(), "SKILL.md should exist"

    content = skill_file.read_text(encoding="utf-8")
    assert "name:" in content
    assert "description:" in content

    workflow_file = ALARM_DIR / "references" / "WORKFLOW.md"
    assert workflow_file.is_file(), "WORKFLOW.md should exist"

    expected_scripts = [
        SCRIPTS_DIR / "_alarm_common.py",
        SCRIPTS_DIR / "list_alerts.py",
        SCRIPTS_DIR / "analyze_alert.py",
        SCRIPTS_DIR / "operate_alert.py",
    ]
    for script_path in expected_scripts:
        assert script_path.is_file(), f"{script_path.name} should exist"


def test_alarm_scripts_import_cleanly():
    helper_module = load_module("test_alarm_common_module", SCRIPTS_DIR / "_alarm_common.py")
    assert hasattr(helper_module, "emit_placeholder")

    for script_name in ("list_alerts.py", "analyze_alert.py", "operate_alert.py"):
        module = load_module(f"test_{script_name[:-3]}", SCRIPTS_DIR / script_name)
        assert hasattr(module, "main"), f"{script_name} should define main()"
