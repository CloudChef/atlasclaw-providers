from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import audit_materials  # noqa: E402
import audit_project_prompts  # noqa: E402
import audit_workflow  # noqa: E402
import run_document_audit  # noqa: E402
from _rules import load_rules  # noqa: E402


def test_material_availability_excludes_standard_and_ledger_from_r46_inputs():
    materials = [
        {"filename": "设备台账.xlsx", "kind": "ledger"},
        {"filename": "检测标准库.xlsx", "kind": "standard"},
        {"filename": "未命名附件.xlsx", "kind": "supplement"},
    ]

    availability = audit_materials.material_availability(materials)

    assert availability["kinds"] == {"ledger", "standard"}
    assert availability["supports_materials"] is False
    assert audit_materials.material_availability([])["kinds"] == set()


def test_project_rule_table_fills_missing_enabled_rules_and_keeps_model_rows():
    ruleset = load_rules()
    raw = """## 项目 P-01
### 核查依据
| 规则号 | 结果 | 依据/限制 |
| --- | --- | --- |
| R01 | 通过 | 原文页码已核对 |

### 设备核查
设备记录
### 数值核查
数值记录
### 问题汇总
无
"""

    normalized, warnings = audit_workflow.normalize_project_rule_table(raw, ruleset)

    assert "| R01 | 通过 | 原文页码已核对 |" in normalized
    assert all(f"| {rule_id} | 待复核 | 模型未明确回答" in normalized for rule_id in ruleset.ids if rule_id != "R01")
    assert "project_rule_missing:R02" in warnings and "project_rule_missing:R46" in warnings


def test_project_rule_table_preserves_complete_rows_and_marks_duplicate_pending():
    ruleset = load_rules()
    raw = """## 项目 P-01
### 核查依据
| 规则号 | 结果 | 依据/限制 |
| --- | --- | --- |
| R01 | 通过 | 已查 |
| R01 | 不通过 | 有差异 |

### 设备核查
设备记录
### 数值核查
数值记录
### 问题汇总
无
"""

    normalized, warnings = audit_workflow.normalize_project_rule_table(raw, ruleset)

    assert "| R01 | 待复核 | 模型原始回答无法唯一确认" in normalized
    assert "通过" in normalized and "不通过" in normalized and "已查" in normalized and "有差异" in normalized
    assert "project_rule_malformed:R01" in warnings


def test_project_rule_table_preserves_malformed_source_and_marks_input_missing_separately():
    ruleset = load_rules()
    raw = """## 项目 P-01
### 核查依据
| R19 | 通过 | 原始理由 | 多余字段 |

### 数值核查
数据
### 设备台账
数据
### 项目问题
无
"""

    normalized, warnings = audit_workflow.normalize_project_rule_table(raw, ruleset, [])

    assert "R19 / 通过 / 原始理由 / 多余字段" in normalized
    assert "project_rule_malformed:R19" in warnings
    assert "project_rule_missing:R21" in warnings

    pass_row = raw.replace("| R19 | 通过 | 原始理由 | 多余字段 |", "| R19 | 通过 | 原始理由 |")
    normalized, warnings = audit_workflow.normalize_project_rule_table(pass_row, ruleset, [])
    assert "模型原始回答：通过；原依据：原始理由；缺少输入：设备台账" in normalized
    assert "project_rule_input_missing:R19:ledger" in warnings
    assert "project_rule_malformed:R19" not in warnings


def test_complete_project_rule_rows_are_left_unchanged():
    ruleset = load_rules()
    rows = [f"| {rule_id} | 不适用 | 本项目无对应内容 |" for rule_id in ruleset.ids]
    raw = "## 项目 P-01\n### 核查依据\n| 规则号 | 结果 | 依据/限制 |\n| --- | --- | --- |\n" + "\n".join(rows) + "\n\n### 数值核查\n数据\n### 设备台账\n数据\n### 项目问题\n无\n"

    normalized, warnings = audit_workflow.normalize_project_rule_table(raw, ruleset, [])

    assert warnings == []
    assert all(row in normalized for row in rows)


def test_project_rule_table_stays_contiguous_before_trailing_material_prose(tmp_path: Path):
    ruleset = load_rules()
    raw = """## 项目 P-01
### 核查依据
| 规则号 | 结果 | 依据/限制 |
| --- | --- | --- |
| R01 | 不适用 | 本项目无该内容 |
本次材料 M01：ledger.xlsx，设备编号 DEV-1。
### 数值核查
数据
### 设备台账
数据
### 项目问题
无
"""

    normalized, _warnings = audit_workflow.normalize_project_rule_table(raw, ruleset)
    sys.path.insert(0, str(SCRIPTS))
    import render_report  # noqa: PLC0415
    rendered = render_report.markdown_to_html(normalized, SKILL_ROOT)

    assert "本次材料 M01" in rendered
    assert rendered.count("<td>R") == len(ruleset.ids)


def test_project_warning_retains_colons_in_project_id():
    warning = "project_rule_missing:R07:section%3A01"

    block = run_document_audit._pipeline_incomplete_block([warning])

    assert "section:01" in block and "R07" in block


def test_rule_checklist_preserves_literal_template_tokens_in_rule_title():
    ruleset = SimpleNamespace(rules={
        "X99": {"title": "Literal {{STAGE}} stays unchanged", "stage": "project"},
    })

    checklist = audit_project_prompts._rule_checklist(ruleset)

    assert "Literal {{STAGE}} stays unchanged" in checklist


def test_project_input_pending_reason_preserves_literal_template_tokens():
    ruleset = load_rules()
    raw = """## 项目 P-01
### 核查依据
| 规则号 | 结果 | 依据/限制 |
| --- | --- | --- |
| R19 | 通过 | Literal {{INPUTS}} stays unchanged |
### 数值核查
数据
### 设备台账
数据
### 项目问题
无
"""

    normalized, _warnings = audit_workflow.normalize_project_rule_table(raw, ruleset, [])

    assert "Literal {{INPUTS}} stays unchanged" in normalized
    assert "缺少输入：设备台账" in normalized


def test_check_global_uses_snapshot_title_and_severity_for_pending_rows():
    ruleset = SimpleNamespace(rules={
        "X99": {"module": "Customer pack", "title": "Customer input check", "severity": "C",
                "requires": ["text"]},
    })
    summary = "# Summary\n\n**总评：待复核**\n"

    normalized = audit_workflow._check_global(summary, ["X99"], ruleset=ruleset)

    assert "| X99 | Customer pack | Customer input check | C | 待复核 |" in normalized


def test_global_input_pending_reason_keeps_pass_and_names_missing_input():
    ruleset = SimpleNamespace(rules={
        "X99": {"module": "Customer pack", "title": "Customer input check", "severity": "C",
                "requires": ["text", "ledger"]},
    })
    raw = """# Summary
**总评：通过**
## 5. 检查覆盖表
| 规则号 | 模块 | 检查项 | 等级 | 结果 | 依据 |
| --- | --- | --- | --- | --- | --- |
| X99 | Customer pack | Customer input check | C | 通过 | Original model rationale |
"""

    normalized = run_document_audit.normalize_publishable_report(
        raw, ["X99"], materials=[], ruleset=ruleset,
    )

    assert "Original model rationale" in normalized
    assert "设备台账" in normalized
    assert "不代表业务不通过" in normalized


def test_renamed_excel_standard_and_ledger_are_classified_from_headers(tmp_path: Path):
    openpyxl = pytest.importorskip("openpyxl")
    standard_path = tmp_path / "export-001.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for _ in range(7):
        sheet.append([])
    sheet.append(["标准编号", "标准名称", "最新版本号"])
    sheet.append(["ISO 1234", "方法", "2025"])
    workbook.save(standard_path)

    assert audit_materials.read_material(standard_path)["kind"] == "standard"


def test_rule_prose_mentioning_ledger_fields_does_not_satisfy_ledger_dependency(tmp_path: Path):
    source = tmp_path / "rules-note.txt"
    source.write_text("设备编号与校准有效期应分别核对。", encoding="utf-8")

    material = audit_materials.read_material(source)

    assert material["kind"] == "supplement"
    assert audit_materials.material_availability([material])["kinds"] == set()
