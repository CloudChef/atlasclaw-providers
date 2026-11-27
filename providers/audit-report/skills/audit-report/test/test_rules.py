# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.
"""Contracts for the rules directory and rule-pack compile/validate flow."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import _rules  # noqa: E402
import check_coverage  # noqa: E402
import import_builtin_rules  # noqa: E402
import verify_findings  # noqa: E402
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


def test_builtin_pack_has_official_46_rules():
    path = SKILL_ROOT / "rules" / "builtin" / "rules.json"
    pack = json.loads(path.read_text(encoding="utf-8"))
    ids = [rule["id"] for rule in pack["rules"]]
    assert ids == [f"R{i:02d}" for i in range(1, 47)]
    assert all(rule["severity"] in {"A", "B", "C"} for rule in pack["rules"])
    errors, _warnings = _rules.validate_pack(pack, path)
    assert errors == []


def test_builtin_import_loads_all_source_rows_with_matching_provenance():
    source = SKILL_ROOT / "rules" / "builtin" / "source" / "AI报告审核规则_final.xlsx"
    pack_path = SKILL_ROOT / "rules" / "builtin" / "rules.json"
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    imported_rules, source_meta = import_builtin_rules.read_rules(source, "Sheet1")
    loaded = _rules.load_rules(SKILL_ROOT / "rules")

    assert import_builtin_rules.DEFAULT_XLSX == source
    assert source_meta == {"sheet": "Sheet1", "rows": 48, "header_row": 2}
    assert len(imported_rules) == 46
    assert [rule["source_row"] for rule in imported_rules] == list(range(3, 49))
    assert pack["rules"] == imported_rules
    assert pack["version"] == "2.0.0"
    assert pack["compiled_from"]["source"] == "source/AI报告审核规则_final.xlsx"
    assert pack["compiled_from"]["sheet"] == "Sheet1"
    assert pack["compiled_from"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert imported_rules[17]["severity"] == "B"
    assert imported_rules[17]["severity_source"] == ""
    assert loaded.builtin_ids == [f"R{index:02d}" for index in range(1, 47)]
    assert loaded.ids == loaded.builtin_ids
    assert loaded.severity == {rule["id"]: rule["severity"] for rule in imported_rules}
    expected_markdown = import_builtin_rules.build_markdown(pack)
    assert (
        SKILL_ROOT / "rules" / "builtin" / "rules.md"
    ).read_text(encoding="utf-8") == expected_markdown
    assert (
        SKILL_ROOT / "references" / "audit-rules.md"
    ).read_text(encoding="utf-8") == expected_markdown


def test_builtin_import_check_rejects_compiled_rule_drift_with_matching_source_hash(
    tmp_path, monkeypatch
):
    source = SKILL_ROOT / "rules" / "builtin" / "source" / "AI报告审核规则_final.xlsx"
    rules_dir = tmp_path / "rules"
    builtin_dir = rules_dir / "builtin"
    builtin_dir.mkdir(parents=True)
    pack = json.loads(
        (SKILL_ROOT / "rules" / "builtin" / "rules.json").read_text(encoding="utf-8")
    )
    pack["rules"][0]["severity"] = "A" if pack["rules"][0]["severity"] != "A" else "C"
    (builtin_dir / "rules.json").write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(import_builtin_rules, "RULES_DIR", rules_dir)
    monkeypatch.setattr(
        sys,
        "argv",
        ["import_builtin_rules.py", "--check", "--xlsx", str(source)],
    )

    with pytest.raises(SystemExit, match="工作簿规则内容"):
        import_builtin_rules.main()


def test_builtin_import_rejects_a_missing_source_severity_header(tmp_path):
    from openpyxl import Workbook

    source = tmp_path / "rules.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["序号", "审核模块", "检查项", "判定规则"])
    sheet.append([1, "检测照片", "照片日期", "照片日期不一致"])
    workbook.save(source)

    with pytest.raises(SystemExit, match="未找到完整规则表头"):
        import_builtin_rules.read_rules(source, "Sheet")


def test_builtin_import_rejects_unrecognized_nonempty_severity():
    with pytest.raises(ValueError, match="无法识别风险等级"):
        import_builtin_rules.severity_of("critical")


def test_builtin_json_matches_source_workbook():
    source = SKILL_ROOT / "rules" / "builtin" / "source" / "AI报告审核规则_final.xlsx"
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "import_builtin_rules.py"), "--check", "--xlsx", str(source)],
        capture_output=True, encoding="utf-8", errors="replace", timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "matches" in result.stdout


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


def test_compile_excel_rule_document(tmp_path):
    from openpyxl import Workbook

    source = tmp_path / "rules.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["规则ID", "模块", "检查项", "判定规则（不通过条件）", "建议等级", "取证位置"])
    sheet.append(["X01", "客户要求", "温度曲线", "未附曲线原始记录", "高", "附件"])
    workbook.save(source)

    pack = compile_pack(source, "excel-test", tmp_path / "excel")
    assert [rule["id"] for rule in pack["rules"]] == ["X01"]
    assert pack["rules"][0]["severity"] == "A"
    assert pack["rules"][0]["fail_when"] == "未附曲线原始记录"


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
    errors, _warnings = _rules.validate_pack(pack, tmp_path / "pack.json", builtin_ids={"R05"})
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
    assert ruleset.builtin_ids == [f"R{index:02d}" for index in range(1, 47)]
    assert ruleset.extra_ids == ["X01"]
    assert "X01" in ruleset.ids
    rows = "\n".join(
        f"| {rule_id} | 模块 | 检查项 | B | 通过 | - |" for rule_id in ruleset.builtin_ids
    )
    report = tmp_path / "report.md"
    report.write_text("**总评：通过**\n\n" + rows + "\n", encoding="utf-8")

    problems = check_coverage.check_report(report, ruleset)
    assert any("missing coverage rows" in problem and "X01" in problem for problem in problems)


def test_rule_ids_over_99_compile_load_and_appear_in_coverage(tmp_path):
    rules_dir = tmp_path / "rules"
    shutil.copytree(SKILL_ROOT / "rules" / "builtin", rules_dir / "builtin")
    pack_dir = rules_dir / "packs" / "large-customer"
    source = tmp_path / "large-rules.md"
    rows = [
        "| 规则ID | 模块 | 检查项 | 判定规则（不通过条件） | 建议等级 | 取证位置 | 适用范围 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    ids = [f"X{index:02d}" for index in range(1, 102)]
    rows.extend(
        f"| {rule_id} | 客户要求 | 检查项 {rule_id} | 条件 {rule_id} | B | 报告页 | 单份 |"
        for rule_id in ids
    )
    source.write_text("\n".join(rows), encoding="utf-8")
    pack = compile_pack(source, "large-customer", pack_dir)

    assert [rule["id"] for rule in pack["rules"]] == ids
    pack_path = pack_dir / "pack.json"
    stored = json.loads(pack_path.read_text(encoding="utf-8"))
    stored["status"] = "active"
    pack_path.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
    (rules_dir / "config.json").write_text(
        json.dumps(
            {
                "version": 1,
                "builtin": "builtin/rules.json",
                "packs": ["packs/large-customer"],
                "allow_overrides": False,
            }
        ),
        encoding="utf-8",
    )
    ruleset = _rules.load_rules(rules_dir)
    assert [rule_id for rule_id in ruleset.ids if rule_id.startswith("X")] == ids

    report = tmp_path / "report.md"
    rows = [
        f"| {rule_id} | 模块 | 检查项 | B | 通过 | 证据 |" for rule_id in ruleset.ids
    ]
    summary = "\n".join(
        [
            "| 等级 | 数量 |",
            "| --- | ---: |",
            "| A · 严重 | 0 |",
            "| B · 主要 | 0 |",
            "| C · 次要 | 0 |",
            "| 不适用 | 0 |",
        ]
    )
    report.write_text("**总评：通过**\n\n" + "\n".join(rows) + "\n\n" + summary, encoding="utf-8")
    assert check_coverage.check_report(report, ruleset) == []


def test_coverage_checker_preserves_review_without_forcing_failure(tmp_path):
    ruleset = _rules.load_rules()
    coverage = [
        f"| {rule_id} | 模块 | 检查项 | {ruleset.severity[rule_id]} | "
        f"{'证据不足' if rule_id == 'R01' else '通过'} | 证据 |"
        for rule_id in ruleset.ids
    ]
    summary = [
        "| 等级 | 数量 |",
        "| --- | ---: |",
        "| A · 严重 | 0 |",
        "| B · 主要 | 1 |",
        "| C · 次要 | 0 |",
        "| 不适用 | 0 |",
    ]
    report = tmp_path / "review.md"
    report.write_text(
        "\n".join(
            [
                "**总评：待复核**",
                *coverage,
                "| 问题 | 等级 | 页码 | 位置 | 说明 |",
                "| --- | --- | --- | --- | --- |",
                "| F-001001 | R01/B | 1 | 第1页记录区域 | 待复核 | 截图 |",
                "### F-001001 [B] 证据不足（R01）",
                "- **页码**：1",
                "- **位置**：第1页记录区域",
                "- **原文上下文**：温度记录",
                "- **不规范说明**：文本来源不足以确认",
                *summary,
            ]
        ),
        encoding="utf-8",
    )

    assert check_coverage.check_report(report, ruleset) == []

    report_text = report.read_text(encoding="utf-8")
    report_text = report_text.replace("**总评：待复核**", "**总评：不通过**")
    report_text = report_text.replace(
        "| R01 | 模块 | 检查项 | B | 证据不足 | 证据 |",
        "| R01 | 模块 | 检查项 | B | 不通过（不合格） | 证据 |",
    )
    report.write_text(report_text, encoding="utf-8")
    assert check_coverage.check_report(report, ruleset) == []

    duplicate_and_missing = [
        line for line in report.read_text(encoding="utf-8").splitlines()
        if not line.startswith("| R46 |")
    ]
    duplicate_and_missing.append("| R01 | 模块 | 重复项 | B | 通过 | 证据 |")
    report.write_text("\n".join(duplicate_and_missing), encoding="utf-8")
    problems = check_coverage.check_report(report, ruleset)
    assert any("R01: duplicate coverage row" in problem for problem in problems)
    assert any("missing coverage rows" in problem and "R46" in problem for problem in problems)


def test_finding_verifier_keeps_uncertain_coverage_as_review_and_decodes_small_image(
    tmp_path, monkeypatch
):
    import base64

    report = tmp_path / "report.md"
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "tiny.png").write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/"
            "pL8AAAAASUVORK5CYII="
        )
    )
    report.write_text(
        "\n".join(
            [
                "**总评：待复核**",
                "| R02 | 模块 | 检查项 | A | 证据不足 | 证据 |",
                "### F-001001 [B] 资料受限待复核（R02）",
                "- **页码**：1",
                "- **位置**：第1页记录区域",
                "- **原文上下文**：",
                "“温度记录”",
                "- **不规范说明**：当前来源不足以确认",
                "![证据截图](evidence/tiny.png)",
            ]
        ),
        encoding="utf-8",
    )
    source = tmp_path / "source.md"
    source.write_text("## Page 1\n温度记录\n", encoding="utf-8")
    result_json = tmp_path / "verify.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_findings.py",
            str(report),
            "--source",
            str(source),
            "--evidence",
            str(evidence),
            "--json",
            str(result_json),
        ],
    )

    original_report = report.read_bytes()
    assert verify_findings.main() == 0
    assert report.read_bytes() == original_report
    result = json.loads(result_json.read_text(encoding="utf-8"))
    assert result["counts"] == {"PASS": 0, "REVIEW": 1, "FAIL": 0}
    assert "证据不足" in result["results"][0]["reasons"][0]

    report_text = report.read_text(encoding="utf-8").replace(
        "| R02 | 模块 | 检查项 | A | 证据不足 | 证据 |",
        "| R02 | 模块 | 检查项 | A | 不通过（不合格） | 证据 |",
    )
    report.write_text(report_text, encoding="utf-8")
    assert verify_findings.main() == 0
    result = json.loads(result_json.read_text(encoding="utf-8"))
    assert result["counts"] == {"PASS": 1, "REVIEW": 0, "FAIL": 0}

    (evidence / "tiny.png").write_bytes(b"invalid image")
    assert verify_findings.main() == 1
    result = json.loads(result_json.read_text(encoding="utf-8"))
    assert result["counts"]["FAIL"] == 1
    assert any("无法解码" in reason for reason in result["results"][0]["reasons"])


def test_findings_and_coverage_recognize_extended_rule_and_finding_ids():
    finding = verify_findings.parse_findings(
        ["### F-1000-1001 [B] extended rule finding（X100）", "- **页码**：8"]
    )
    assert len(finding) == 1
    assert finding[0]["id"] == "F-1000-1001"
    assert finding[0]["rule"] == "X100"
    assert verify_findings.coverage_results(["| X100 | 模块 | 检查项 | B | 不通过 | 证据 |"])["X100"] == "不通过"
    assert check_coverage.FINDING_RE.match(
        "### F-1000-1001 [B] extended rule finding（X100）"
    ).groups()[3] == "X100"

    report_text = "| F-1000-1001 | 不通过 | finding | page 8 | detail |"
    assert check_coverage.OVERVIEW_RE.match(report_text).group(1) == "F-1000-1001"
    legacy = verify_findings.parse_findings(
        ["### F-001001 [B] legacy finding（X100）"]
    )
    assert legacy[0]["id"] == "F-001001"
    assert check_coverage.OVERVIEW_RE.match(
        "| F-001001 | 不通过 | finding | page 8 | detail |"
    ).group(1) == "F-001001"
    short_legacy = verify_findings.parse_findings(
        ["### F-01 [B] short legacy finding（X100）"]
    )
    assert short_legacy[0]["id"] == "F-01"
    assert check_coverage.OVERVIEW_RE.match(
        "| F-01 | 不通过 | finding | page 8 | detail |"
    ).group(1) == "F-01"
    separated_legacy = verify_findings.parse_findings(
        ["### F-1-1 [B] separated legacy finding（X100）"]
    )
    assert separated_legacy[0]["id"] == "F-1-1"
    assert check_coverage.OVERVIEW_RE.match(
        "| F-1-1 | 不通过 | finding | page 8 | detail |"
    ).group(1) == "F-1-1"


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
