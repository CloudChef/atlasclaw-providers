#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import the official AI audit rule workbook into rules/builtin/rules.json.

Source: AI报告审核规则_final.xlsx, sheet Sheet1 (46 rules, version 2026-11-27).
The workbook is copied into rules/builtin/source/ for reproducibility, and a
human-readable rules.md plus references/audit-rules.md are regenerated.

Usage:
    python scripts/import_builtin_rules.py
    python scripts/import_builtin_rules.py --xlsx "C:/path/AI报告审核规则_final.xlsx"
    python scripts/import_builtin_rules.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from _rules import RULES_DIR, SKILL_ROOT

DEFAULT_XLSX = RULES_DIR / "builtin" / "source" / "AI报告审核规则_final.xlsx"
DEFAULT_SHEET = "Sheet1"
SEVERITY_LABELS = {"A": "A · 严重", "B": "B · 主要", "C": "C · 次要"}

# Rule number -> check implementation hint. The LLM still makes the judgment.
CHECK_TYPES = {
    1: "page_sequence", 2: "page_sequence", 3: "text_consistency", 4: "text_consistency",
    5: "text_consistency", 6: "text_consistency", 7: "text_consistency", 8: "text_consistency",
    9: "date_chain", 10: "date_chain", 11: "date_chain", 12: "date_chain", 13: "date_chain",
    14: "visual", 15: "visual", 16: "visual", 17: "text_consistency", 18: "page_sequence",
    19: "text_consistency", 20: "text_consistency", 21: "date_chain", 22: "text_consistency",
    23: "text_consistency", 24: "text_regex", 25: "text_regex", 26: "text_regex",
    27: "manual", 28: "manual", 29: "manual", 30: "visual", 31: "visual", 32: "visual",
    33: "visual", 34: "visual", 35: "text_consistency", 36: "numeric_range",
    37: "text_regex", 38: "text_consistency", 39: "text_regex", 40: "numeric_range",
    41: "manual", 42: "numeric_range", 43: "numeric_range", 44: "numeric_range",
    45: "text_consistency", 46: "cross_file",
}

GLOBAL_RULES = {1, 2, 3, 17, 18, 24, 25, 29, 35, 38, 46}
BATCH_RULES = {46}
IMAGE_RULES = {5, 14, 15, 16, 30, 31, 32, 33, 34}
VISUAL_MODEL_RULES = {14, 15, 16, 31, 33, 34}
LEDGER_RULES = {19}
STANDARD_RULES = {7}
MATERIAL_RULES = {46}

EVIDENCE = {
    1: ["页眉/页脚", "PDF 页序"],
    2: ["目录", "正文标题与页码"],
    3: ["页眉", "正文", "声明", "结论"],
    4: ["封面", "样品信息表"],
    5: ["检测结果", "照片下标", "检测照片"],
    6: ["样品清单", "样品数量字段"],
    7: ["检测标准", "标准库"],
    8: ["全文标准号出现位置"],
    9: ["生产日期", "送样日期", "检测日期", "签发日期"],
    10: ["样品信息", "检测记录", "签发页"],
    11: ["生产日期", "检测完成日期"],
    12: ["各项目检测日期", "试验顺序"],
    13: ["检测方法", "检测日期段"],
    14: ["检测照片时间戳", "检测日期"],
    15: ["照片时间戳", "照片内时钟"],
    16: ["照片内设备面板", "检测日期"],
    17: ["目录", "正文标题"],
    18: ["章节号"],
    19: ["报告设备表", "设备台账"],
    20: ["设备表跨页", "设备信息"],
    21: ["设备表", "检测日期"],
    22: ["设备表", "各项目检测日期"],
    23: ["检测方法", "设备表"],
    24: ["分包声明", "全文分包方名称"],
    25: ["认可状态声明", "全文分包方名称"],
    26: ["全文单位"],
    27: ["全文"],
    28: ["英文摘要", "英文项目名", "英文结论"],
    29: ["中英文对照段落"],
    30: ["检测照片"],
    31: ["检测照片"],
    32: ["检测照片"],
    33: ["检测方法", "检测照片"],
    34: ["曲线图", "检测日期"],
    35: ["全文重复信息"],
    36: ["检测环境", "方法温湿度限值"],
    37: ["检测环境"],
    38: ["目录结果评价", "正文结果评价"],
    39: ["检测结果"],
    40: ["检测结果", "修约规则"],
    41: ["检测结果", "结论"],
    42: ["数据表", "计算字段"],
    43: ["色差数据", "ΔL 公式"],
    44: ["数据表", "上下限"],
    45: ["判定依据", "数据表"],
    46: ["报告", "试验大纲/测试计划/原始记录/委托单"],
}

APPLIES = {
    5: ("报告含检测照片和样品编号", "报告无检测照片"),
    6: ("报告有样品数量字段或汇总", "报告无样品数量信息"),
    7: ("报告引用检测标准号", "报告全部为客户要求或无标准号"),
    8: ("报告引用检测标准号", "报告无标准号"),
    11: ("报告含气味、雾化、总碳、甲醛、VOC 等散发类项目", "报告无散发类项目"),
    12: ("报告含顺序试验且可识别项目检测日期", "无顺序试验或日期不可识别"),
    14: ("报告含带时间戳的检测照片", "报告无带时间戳照片"),
    15: ("报告含带时间戳和时钟的检测照片", "报告无对应照片"),
    16: ("报告含设备面板照片", "报告无设备面板照片"),
    19: ("提供了设备台账", "未提供设备台账（按待复核处理）"),
    22: ("报告含多个项目且可识别设备使用时间", "无法识别设备使用时间"),
    24: ("报告含分包声明", "报告无分包声明"),
    25: ("报告含认可状态声明", "报告无认可状态声明"),
    30: ("报告含检测照片", "报告无检测照片"),
    31: ("报告含检测照片", "报告无检测照片"),
    32: ("报告含检测照片", "报告无检测照片"),
    33: ("报告含检测照片", "报告无检测照片"),
    34: ("报告含曲线图", "报告无曲线图"),
    36: ("检测方法给出温湿度限值", "方法未给温湿度限值"),
    43: ("报告含色差/颜色数据", "报告无色差数据"),
    46: ("上传了试验大纲、测试计划、原始记录或委托单", "未上传其他材料"),
}

HEADER_ALIASES = {
    "no": {"序号", "编号"},
    "module": {"审核模块", "模块", "类别"},
    "title": {"检查项", "检查项目", "规则名称"},
    "fail_when": {"判定规则", "判定规则（fail条件）", "判定规则(fail条件)", "不通过条件", "fail条件"},
    "severity": {"建议修改的风险等级", "建议等级", "风险等级", "等级"},
    "note": {"备注", "说明"},
}


def norm(value: object) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", "", text).strip().lower()
    return text.replace("（", "(").replace("）", ")")


def map_headers(row: tuple) -> dict[str, int]:
    columns: dict[str, int] = {}
    for index, value in enumerate(row):
        key = norm(value)
        for field, names in HEADER_ALIASES.items():
            if field not in columns and key in {norm(name) for name in names}:
                columns[field] = index
    return columns


def severity_of(value: object) -> tuple[str, str]:
    text = "" if value is None else str(value).strip()
    if not text:
        return "B", ""
    if "高" in text:
        return "A", "高"
    if "中" in text:
        return "B", "中"
    if "低" in text:
        return "C", "低"
    match = re.search(r"(?<![A-Za-z])([ABC])(?![A-Za-z])", text)
    if match:
        return match.group(1), match.group(1)
    raise ValueError(f"无法识别风险等级: {text!r}")


def build_rule(no: int, module: str, title: str, fail_when: str, severity: str, severity_source: str, note: str, source_row: int) -> dict:
    applies_when, na_when = APPLIES.get(no, ("始终适用", ""))
    requires = ["text"]
    if no in IMAGE_RULES:
        requires.append("image")
    if no in VISUAL_MODEL_RULES:
        requires.append("visual_model")
    if no in LEDGER_RULES:
        requires.append("ledger")
    if no in STANDARD_RULES:
        requires.append("standard")
    if no in MATERIAL_RULES:
        requires.append("materials")
    return {
        "id": f"R{no:02d}",
        "module": module,
        "title": title,
        "severity": severity,
        "severity_source": severity_source,
        "fail_when": fail_when,
        "evidence": EVIDENCE.get(no, [module or "全文"]),
        "scope": "batch" if no in BATCH_RULES else "single",
        "stage": "global" if no in GLOBAL_RULES else "project",
        "applies_when": applies_when,
        "na_when": na_when,
        "requires": requires,
        "check": {"type": CHECK_TYPES.get(no, "manual"), "params": {}},
        "source_row": source_row,
        "doc": f"rules/builtin/rules.md#R{no:02d}",
        "note": note,
    }


def read_rules(xlsx: Path, sheet: str) -> tuple[list[dict], dict]:
    from openpyxl import load_workbook

    workbook = load_workbook(xlsx, data_only=True, read_only=True)
    try:
        if sheet not in workbook.sheetnames:
            raise SystemExit(f"工作表不存在: {sheet}; 可选: {', '.join(workbook.sheetnames)}")
        worksheet = workbook[sheet]
        rows = list(worksheet.iter_rows(values_only=True))
    finally:
        workbook.close()

    header_index = None
    columns: dict[str, int] = {}
    for index, row in enumerate(rows):
        mapped = map_headers(row)
        if {"no", "module", "title", "fail_when", "severity"}.issubset(mapped):
            header_index = index
            columns = mapped
            break
    if header_index is None:
        raise SystemExit("未找到完整规则表头（需要 序号/审核模块/检查项/判定规则/风险等级）")

    rules: list[dict] = []
    for row_index in range(header_index + 1, len(rows)):
        row = rows[row_index]
        def cell(field: str) -> str:
            index = columns.get(field)
            if index is None or index >= len(row) or row[index] is None:
                return ""
            return re.sub(r"\s+", " ", str(row[index])).strip()

        raw_no = cell("no")
        module = cell("module")
        title = cell("title")
        fail_when = cell("fail_when")
        severity_text = cell("severity")
        if not any((raw_no, module, title, fail_when, severity_text, cell("note"))):
            continue
        missing = [
            field for field, value in (
                ("序号", raw_no), ("审核模块", module), ("检查项", title),
                ("判定规则", fail_when),
            ) if not value
        ]
        if missing:
            raise SystemExit(f"Excel 第 {row_index + 1} 行缺少必填字段: {', '.join(missing)}")
        try:
            no = int(float(raw_no))
        except (ValueError, OverflowError):
            raise SystemExit(f"Excel 第 {row_index + 1} 行序号无效: {raw_no!r}") from None
        try:
            severity, severity_source = severity_of(severity_text)
        except ValueError as exc:
            raise SystemExit(f"Excel 第 {row_index + 1} 行风险等级无效: {severity_text!r}") from exc
        rules.append(build_rule(
            no=no,
            module=module,
            title=title,
            fail_when=fail_when,
            severity=severity,
            severity_source=severity_source,
            note=cell("note"),
            source_row=row_index + 1,
        ))
    if not rules:
        raise SystemExit("规则表为空")
    return rules, {"sheet": sheet, "rows": len(rows), "header_row": header_index + 1}


def build_markdown(pack: dict) -> str:
    lines = [
        f"# {pack['title']}",
        "",
        f"- 规则包：`{pack['pack']}@{pack['version']}`",
        f"- 来源：`{pack['compiled_from']['source']}` / `{pack['compiled_from']['sheet']}`",
        f"- 导入时间：{pack['compiled_from']['imported_at']}",
        "",
        "> `rules.json` 是执行事实源；本文件由 `import_builtin_rules.py` 生成，供人阅读和提示词引用。",
        "",
        "| # | 模块 | 检查项 | 不通过条件 | 等级 | 检查类型 | 阶段 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for rule in pack["rules"]:
        lines.append(
            "| {id} | {module} | {title} | {fail_when} | {severity} | {check} | {stage} |".format(
                id=rule["id"], module=rule["module"], title=rule["title"],
                fail_when=str(rule["fail_when"]).replace("|", "\\|"),
                severity=rule["severity"], check=rule["check"]["type"], stage=rule["stage"],
            )
        )
    lines.append("")
    for rule in pack["rules"]:
        lines += [
            f"## {rule['id']} {rule['title']}（{SEVERITY_LABELS[rule['severity']]}）",
            "",
            f"- **模块**：{rule['module']}",
            f"- **不通过条件**：{rule['fail_when']}",
            f"- **取证位置**：{'、'.join(rule['evidence'])}",
            f"- **适用前提**：{rule['applies_when']}",
            f"- **不适用条件**：{rule['na_when'] or '无'}",
            f"- **检查类型**：`{rule['check']['type']}`；**阶段**：`{rule['stage']}`",
            f"- **所需输入**：{'、'.join(rule['requires'])}",
            f"- **来源**：Excel 第 {rule['source_row']} 行；等级来源：{rule['severity_source'] or '未填写（默认 B）'}",
            "",
        ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import the official AI audit rules into rules/builtin/rules.json")
    parser.add_argument("--xlsx", default=str(DEFAULT_XLSX))
    parser.add_argument("--sheet", default=DEFAULT_SHEET)
    parser.add_argument("--check", action="store_true", help="Verify the existing JSON matches the workbook")
    args = parser.parse_args()

    xlsx = Path(args.xlsx)
    if not xlsx.is_file():
        raise SystemExit(f"规则工作簿不存在: {xlsx}")
    digest = hashlib.sha256(xlsx.read_bytes()).hexdigest()
    builtin_dir = RULES_DIR / "builtin"
    json_path = builtin_dir / "rules.json"
    if args.check:
        if not json_path.is_file():
            raise SystemExit("rules/builtin/rules.json 不存在")
        pack = json.loads(json_path.read_text(encoding="utf-8"))
        compiled_from = pack.get("compiled_from") or {}
        if compiled_from.get("sha256") != digest:
            raise SystemExit("内置规则 JSON 与工作簿哈希不一致，请运行 import_builtin_rules.py")
        imported_rules, _meta = read_rules(xlsx, args.sheet)
        if (
            compiled_from.get("source") != f"source/{xlsx.name}"
            or compiled_from.get("sheet") != args.sheet
            or pack.get("rules") != imported_rules
        ):
            raise SystemExit("内置规则 JSON 与工作簿规则内容不一致，请运行 import_builtin_rules.py")
        markdown = build_markdown(pack)
        for generated_path in (
            builtin_dir / "rules.md",
            SKILL_ROOT / "references" / "audit-rules.md",
        ):
            if not generated_path.is_file() or generated_path.read_text(encoding="utf-8") != markdown:
                raise SystemExit(f"生成的规则说明与内置 JSON 不一致: {generated_path}")
        print(f"[OK] {json_path} matches {xlsx.name}")
        return 0

    rules, meta = read_rules(xlsx, args.sheet)
    source_dir = builtin_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / xlsx.name
    if source_path.resolve() != xlsx.resolve():
        shutil.copy2(xlsx, source_path)
    pack = {
        "pack": "builtin",
        "version": "2.0.0",
        "title": "AI 报告审核规则（2026-11-27）",
        "status": "active",
        "compiled_from": {
            "source": f"source/{source_path.name}",
            "sheet": args.sheet,
            "sha256": digest,
            "imported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "importer": "import_builtin_rules.py",
        },
        "rules": rules,
    }
    builtin_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown = build_markdown(pack)
    (builtin_dir / "rules.md").write_text(markdown, encoding="utf-8")
    (SKILL_ROOT / "references" / "audit-rules.md").write_text(markdown, encoding="utf-8")
    print(f"[OK] {json_path}: {len(rules)} rules")
    print(f"[OK] {builtin_dir / 'rules.md'}")
    print(f"[OK] {SKILL_ROOT / 'references' / 'audit-rules.md'}")
    print(f"     source: {source_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
