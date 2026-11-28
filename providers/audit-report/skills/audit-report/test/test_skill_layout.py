# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.
"""Layout and smoke contracts for the standalone audit-report skill."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"


def _frontmatter(text: str) -> dict[str, str]:
    assert text.startswith("---"), "SKILL.md must start with frontmatter"
    block = text.split("---", 2)[1]
    fields: dict[str, str] = {}
    for line in block.splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return fields


def test_skill_frontmatter_and_layout():
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    metadata = _frontmatter(text)
    assert metadata.get("name") == "audit-report"
    assert len(metadata.get("description", "")) > 20
    for name in ("extract_report.py", "selfcheck.py", "render_report.py", "rules_compile.py", "rules_sync.py", "rules_validate.py", "import_builtin_rules.py", "audit_visual.py", "image_facts.py"):
        assert (SCRIPTS / name).is_file()
    for name in ("audit-rules.md", "report-template.md", "audit-visual-review.md"):
        assert (SKILL_ROOT / "references" / name).is_file()
    for name in ("config.json", "builtin/rules.json", "README.md", "builtin/rules.md"):
        assert (SKILL_ROOT / "rules" / name).is_file()
    assert (SKILL_ROOT / "rules" / "builtin" / "source" / "AI报告审核规则_final.xlsx").is_file()


def test_skill_commands_use_runtime_variables():
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "python scripts/" not in text
    assert "${ATLASCLAW_SKILL_DIR}" in text
    assert "${ATLASCLAW_PYTHON}" in text


def test_scripts_compile():
    for script in SCRIPTS.glob("*.py"):
        compile(script.read_text(encoding="utf-8"), str(script), "exec")


@pytest.mark.parametrize("script", ["selfcheck.py", "check_coverage.py"])
def test_scripts_start_without_arguments(script: str):
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / script)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode in (0, 1, 2), result.stderr
    assert "Traceback" not in result.stderr


def test_selfcheck_reports_dependency_state():
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "selfcheck.py")],
        capture_output=True, text=True, timeout=30,
    )
    payload = json.loads(result.stdout)
    assert "pymupdf" in payload and "python_docx" in payload
    assert result.returncode == (0 if payload["ready"] else 1)


def test_extract_report_reads_pdf_when_available(tmp_path):
    pytest.importorskip("pymupdf")
    import pymupdf

    source = tmp_path / "report.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Detection report body")
    document.save(source)
    document.close()

    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "extract_report.py"), str(source), "--out", str(tmp_path / "out")],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    manifest = json.loads((tmp_path / "out" / "report" / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["pages"]) == 1
    assert (tmp_path / "out" / "report" / "pages" / "page-001.png").is_file()
