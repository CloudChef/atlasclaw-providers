# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.
"""Layout and contract checks for the audit-report provider package."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _json(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_manifest_declares_v1_extension() -> None:
    manifest = _json("provider.schema.json")

    assert manifest["provider_type"] == "audit-report"
    assert manifest["catalog"]["extension_only"] is True
    assert set(manifest["runtime_capabilities"]) == {"documents", "audit"}
    extensions = manifest["extensions"]
    assert extensions["version"] == 1
    assert extensions["api"]["manifest"] == "runtime-api.json"
    nav = extensions["ui"]["nav"][0]
    assert nav["id"] == "file-audit"
    assert nav["entry"] == "index.html"
    assert nav["access"] == "user"
    assert (ROOT / "ui" / nav["entry"]).is_file()
    assert (ROOT / nav["icon_path"]).is_file()
    fields = {field["name"]: field for field in manifest["config_schema"]["fields"]}
    assert set(fields) == {"reports_dir", "standards_dir"}
    assert all(field["required"] is False for field in fields.values())


def test_runtime_manifest_routes_are_consistent() -> None:
    manifest = _json("provider.schema.json")
    runtime = _json("runtime-api.json")
    capabilities = set(manifest["runtime_capabilities"])

    assert runtime["version"] == 1
    assert runtime["routes"]
    for route in runtime["routes"]:
        if route["id"] in {"documents.upload", "standards.upload"}:
            assert route["max_body_bytes"] == 256 * 1024 * 1024
    sys.path.insert(0, str(ROOT / "api"))
    for route in runtime["routes"]:
        assert route["capability"] in capabilities
        assert route["response"] in {"json", "binary"}
        module_path = ROOT / route["module"]
        assert module_path.is_file()
        spec = importlib.util.spec_from_file_location(f"audit_route_{route['id'].replace('.', '_')}", module_path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        handler = getattr(module, route["handler"], None)
        assert handler is not None, route
        assert __import__("inspect").iscoroutinefunction(handler), route


def test_skill_is_bundled_with_the_provider() -> None:
    skill_root = ROOT / "skills" / "audit-report"
    assert (skill_root / "SKILL.md").is_file()
    assert (skill_root / "scripts" / "extract_report.py").is_file()
    assert (skill_root / "scripts" / "render_report.py").is_file()
    assert (skill_root / "test" / "test_skill_layout.py").is_file()


def test_ui_assets_are_relative_and_complete() -> None:
    index = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")

    assert 'src="app.js' in index
    assert 'href="style.css' in index
    assert "http://" not in index and "https://" not in index
    assert "atlasclaw:ready" in script
    assert "atlasclaw:init" in script
    assert "/api/providers/audit-report/default" in script


def test_provider_readme_and_requirements() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "runtime-api.json" in readme
    assert "batch_audit.py" in readme
    requirements = (ROOT / "skills" / "audit-report" / "requirements.txt").read_text(encoding="utf-8")
    assert "pymupdf" in requirements.lower()
    assert "python-docx" in requirements.lower()
