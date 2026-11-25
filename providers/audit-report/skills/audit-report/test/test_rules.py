# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.
"""Contracts for the rules directory and rule-pack compile/validate flow."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import _rules  # noqa: E402
import check_coverage  # noqa: E402
from rules_compile import compile_pack, slugify  # noqa: E402


def _pack_markdown() -> str:
    return "\n".join(
        [
            "| 规则ID | 模块 | 检查项 | 判定规则（不通过条件） | 建议等级 | 取证位置 | 适用范围 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
            "| X01 | 客户要求 | 温度曲线 | 未附温度曲线原始记录 | B | 试验记录页、附件 | 含环境试验 |",
            "| X02 | 客户要求 | 分包实验室 | 有分包但未注明分包实验室名称 | A | 声明页 | 始终适用 |",
        ]
    )


def test_builtin_pack_matches_fallback_severity():
    path = SKILL_ROOT / "rules" / "builtin" / "rules.json"
    pack = json.loads(path.read_text(encoding="utf-8"))
    ids = [rule["id"] for rule in pack["rules"]]
    assert ids == [f"R{i:02d}" for i in range(1, 20)]
    assert {rule["id"]: rule["severity"] for rule in pack["rules"]} == _rules.FALLBACK_SEVERITY
    errors, _warnings = _rules.validate_pack(pack, path)
    assert errors == []


def test_compile_table_document_creates_draft_pack(tmp_path):
    source = tmp_path / "rules.md"
    source.write_text(_pack_markdown(), encoding="utf-8")
    pack_dir = tmp_path / "customer"
    pack = compile_pack(source, "customer", pack_dir)

    assert pack["status"] == "draft"
    assert [rule["id"] for rule in pack["rules"]] == ["X01", "X02"]
    assert pack["rules"][1]["severity"] == "A"
    assert (pack_dir / "pack.json").is_file()
    assert (pack_dir / "rules.md").is_file()
    assert (pack_dir / "source" / "rules.md").is_file()

    stored = json.loads((pack_dir / "pack.json").read_text(encoding="utf-8"))
    errors, _warnings = _rules.validate_pack(stored, pack_dir / "pack.json")
    assert errors == []


def test_compile_heading_document(tmp_path):
    source = tmp_path / "rules.md"
    source.write_text(
        "\n".join(
            [
                "# 客户规则",
                "",
                "## X01 温度曲线（B · 主要）",
                "",
                "- **模块**：客户要求",
                "- **不通过条件**：未附温度曲线原始记录",
                "- **取证位置**：试验记录页、附件",
                "- **适用范围**：含环境试验",
                "",
                "## X02 分包实验室",
                "",
                "- **等级**：A",
                "- **不通过条件**：有分包但未注明分包实验室名称",
                "- **取证位置**：声明页",
                "",
            ]
        ),
        encoding="utf-8",
    )
    pack = compile_pack(source, "heading-test", tmp_path / "heading")
    assert [rule["id"] for rule in pack["rules"]] == ["X01", "X02"]
    assert pack["rules"][0]["severity"] == "B"
    assert pack["rules"][1]["severity"] == "A"
    assert pack["rules"][0]["title"] == "温度曲线"


def test_validate_rejects_builtin_id_in_extra_pack(tmp_path):
    pack = {
        "pack": "bad",
        "version": "1.0.0",
        "status": "draft",
        "rules": [
            {
                "id": "R05",
                "title": "占用内置编号",
                "severity": "A",
                "fail_when": "x",
                "evidence": ["封面"],
                "check": {"type": "manual"},
            }
        ],
    }
    errors, _warnings = _rules.validate_pack(pack, tmp_path / "pack.json")
    assert any("不得占用内置规则号" in error for error in errors)


def test_extra_pack_requires_coverage_row(tmp_path):
    rules_dir = tmp_path / "rules"
    shutil.copytree(SKILL_ROOT / "rules" / "builtin", rules_dir / "builtin")
    pack_dir = rules_dir / "packs" / "customer"
    pack_dir.mkdir(parents=True)
    (rules_dir / "config.json").write_text(
        json.dumps(
            {
                "version": 1,
                "builtin": "builtin/rules.json",
                "packs": ["packs/customer"],
                "allow_overrides": False,
            }
        ),
        encoding="utf-8",
    )
    (pack_dir / "pack.json").write_text(
        json.dumps(
            {
                "pack": "customer",
                "version": "1.0.0",
                "status": "active",
                "rules": [
                    {
                        "id": "X01",
                        "module": "客户要求",
                        "title": "温度曲线",
                        "severity": "B",
                        "fail_when": "未附温度曲线",
                        "evidence": ["附件"],
                        "scope": "single",
                        "check": {"type": "manual"},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    ruleset = _rules.load_rules(rules_dir)
    assert "X01" in ruleset.ids
    rows = "\n".join(
        f"| {rule_id} | 模块 | 检查项 | B | 通过 | - |" for rule_id in _rules.BUILTIN_IDS
    )
    report = tmp_path / "report.md"
    report.write_text("**总评：通过**\n\n" + rows + "\n", encoding="utf-8")

    problems = check_coverage.check_report(report, ruleset)
    assert any("missing coverage rows" in problem and "X01" in problem for problem in problems)


def test_slugify_falls_back_to_hash_for_non_ascii_names():
    value = slugify("客户规则")
    assert value.startswith("rules-")
    assert len(value) == len("rules-") + 8


def test_validate_detects_duplicate_rule_across_active_packs(tmp_path):
    rules_dir = tmp_path / "rules"
    shutil.copytree(SKILL_ROOT / "rules" / "builtin", rules_dir / "builtin")
    paths = []
    for name in ("one", "two"):
        pack_dir = rules_dir / "packs" / name
        pack_dir.mkdir(parents=True)
        payload = {
            "pack": name,
            "version": "1.0.0",
            "status": "active",
            "rules": [
                {
                    "id": "X01",
                    "module": "客户要求",
                    "title": "重复规则",
                    "severity": "B",
                    "fail_when": "条件",
                    "evidence": ["附件"],
                    "scope": "single",
                    "check": {"type": "manual"},
                }
            ],
        }
        pack_path = pack_dir / "pack.json"
        pack_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        paths.append(str(pack_path))

    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "rules_validate.py"), *paths, "--rules-dir", str(rules_dir)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )

    assert result.returncode == 1
    assert "重复" in result.stdout


def test_sync_gate_compile_and_activate(tmp_path):
    rules_dir = tmp_path / "rules"
    shutil.copytree(SKILL_ROOT / "rules" / "builtin", rules_dir / "builtin")
    (rules_dir / "_inbox").mkdir()
    (rules_dir / "config.json").write_text(
        json.dumps({"version": 1, "builtin": "builtin/rules.json", "packs": [], "allow_overrides": False}),
        encoding="utf-8",
    )
    (rules_dir / "_inbox" / "customer.md").write_text(_pack_markdown(), encoding="utf-8")

    sync = [sys.executable, str(SCRIPTS / "rules_sync.py"), "--rules-dir", str(rules_dir)]
    checked = subprocess.run(
        [*sync, "--check"], capture_output=True, encoding="utf-8", errors="replace", timeout=60
    )
    assert checked.returncode == 1, checked.stderr

    compiled = subprocess.run(sync, capture_output=True, encoding="utf-8", errors="replace", timeout=60)
    assert compiled.returncode == 0, compiled.stderr

    pack_path = rules_dir / "packs" / "customer" / "pack.json"
    assert pack_path.is_file()
    assert json.loads(pack_path.read_text(encoding="utf-8"))["status"] == "draft"

    activated = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "rules_validate.py"),
            str(pack_path),
            "--rules-dir",
            str(rules_dir),
            "--activate",
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert activated.returncode == 0, activated.stderr
    assert json.loads(pack_path.read_text(encoding="utf-8"))["status"] == "active"
    config = json.loads((rules_dir / "config.json").read_text(encoding="utf-8"))
    assert "packs/customer" in config["packs"]
