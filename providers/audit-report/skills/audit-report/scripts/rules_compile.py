#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compile a rule document (Markdown/Word/PDF) into a rule pack JSON.

The document is the human-facing explanation; ``pack.json`` is the execution
contract used by ``check_coverage.py`` and ``verify_findings.py``. A rule
document is only accepted when it is a table with a 判定规则/不通过条件 column,
or a heading-per-rule document with 不通过条件/取证位置 bullets.

Supported inputs:
    .md/.txt   plain text
    .docx      standard library extraction (no LibreOffice needed)
    .pdf       text layer + detected tables (PyMuPDF needed)

Usage:
    python rules_compile.py rules/_inbox/customer-xy.md --pack customer-xy
    python rules_compile.py rules/packs/customer-xy/source/rules.docx --pack customer-xy --out rules/packs/customer-xy

The generated pack has ``status: draft``. Review it, run rules_validate.py,
then activate it with ``rules_validate.py <pack.json> --activate``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path

from _rules import PACK_NAME_RE, RULES_DIR, RULE_ID_RE
from extract_report import extract_docx, extract_pdf

SUPPORTED_INPUTS = {".md", ".txt", ".docx", ".pdf"}

ID_ALIASES = {"规则id", "规则编号", "规则号", "id", "编号"}
MODULE_ALIASES = {"模块", "类别", "分类", "规则模块"}
TITLE_ALIASES = {"检查项", "规则名称", "规则标题", "标题", "名称", "检查内容"}
FAIL_ALIASES = {
    "判定规则", "不通过条件", "判定条件", "规则内容", "要求", "检查要求", "规则描述",
}
SEVERITY_ALIASES = {"建议等级", "等级", "级别", "severity", "严重程度"}
EVIDENCE_ALIASES = {"取证位置", "证据位置", "检查位置", "取证", "证据"}
SCOPE_ALIASES = {"适用范围", "范围", "审核范围"}
APPLIES_ALIASES = {"适用前提", "触发条件", "适用条件"}
NA_ALIASES = {"不适用条件", "不适用", "排除条件"}
CHECK_ALIASES = {"检查类型", "检查方式", "执行方式", "check"}

HEADING_RE = re.compile(r"^(#{2,4})\s+(.+?)\s*$")
HEADING_ID_RE = re.compile(r"^([A-Z]\d{2,})\s+(.*)$")
SEVERITY_IN_TITLE_RE = re.compile(r"[（(]\s*([ABC])\s*(?:[·•][^）)]*)?[）)]")
BULLET_RE = re.compile(r"^\s*[-*]\s*(?:\*\*)?([^：:*]+?)(?:\*\*)?\s*[：:]\s*(.+)$")
PLAIN_RULE_RE = re.compile(r"^([A-Z]\d{2,})\s+(\S.*)$")
PLAIN_FIELD_RE = re.compile(r"^([^：:]{1,16})[：:]\s*(.+)$")
AUTO_ID_RE = re.compile(r"^([A-Z])(\d{2,})$")


def clean_cell(value: str) -> str:
    value = value.replace("<br>", "；").replace("<br/>", "；")
    value = value.replace("`", "").replace("**", "")
    return re.sub(r"\s+", " ", value).strip()


def split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [clean_cell(cell.replace("\\|", "|")) for cell in re.split(r"(?<!\\)\|", line)]


def norm_header(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).replace("*", "").replace("`", "")
    return re.sub(r"\s+", "", value).strip().lower()


def map_header(cells: list[str]) -> dict[str, int]:
    columns: dict[str, int] = {}
    aliases = {
        "id": ID_ALIASES,
        "module": MODULE_ALIASES,
        "title": TITLE_ALIASES,
        "fail_when": FAIL_ALIASES,
        "severity": SEVERITY_ALIASES,
        "evidence": EVIDENCE_ALIASES,
        "scope": SCOPE_ALIASES,
        "applies_when": APPLIES_ALIASES,
        "na_when": NA_ALIASES,
        "check_type": CHECK_ALIASES,
    }
    for index, cell in enumerate(cells):
        key = norm_header(cell)
        for field, names in aliases.items():
            if field not in columns and any(name in key for name in names):
                columns[field] = index
    return columns


def is_rule_table(columns: dict[str, int]) -> bool:
    return "fail_when" in columns and ("id" in columns or "title" in columns)


def iter_tables(lines: list[str]) -> list[list[list[str]]]:
    tables: list[list[list[str]]] = []
    current: list[str] = []
    for line in lines:
        if line.lstrip().startswith("|"):
            current.append(line)
        elif current:
            tables.append([split_row(row) for row in current])
            current = []
    if current:
        tables.append([split_row(row) for row in current])
    return tables


def severity_of(value: str) -> str:
    match = re.search(r"(?<![A-Za-z])([ABC])(?![A-Za-z])", value or "")
    return match.group(1) if match else ""


def scope_of(value: str) -> str:
    text = (value or "").strip().lower()
    if text in {"batch", "同批", "多份", "批量"} or "同批" in text or "批量" in text:
        return "batch"
    return "single"


def evidence_of(value: str) -> list[str]:
    parts = re.split(r"[、,，;；]", value or "")
    return [part.strip() for part in parts if part.strip()]


def next_auto_id(prefix: str, used: set[str], counter: int) -> tuple[str, int]:
    while True:
        counter += 1
        candidate = f"{prefix}{counter:02d}"
        if candidate not in used:
            return candidate, counter


def rule_from_values(values: dict[str, str], prefix: str, used: set[str], counter: int) -> tuple[dict, int, list[str]]:
    warnings: list[str] = []
    rule_id = clean_cell(values.get("id", ""))
    if not RULE_ID_RE.fullmatch(rule_id):
        rule_id, counter = next_auto_id(prefix, used, counter)
    elif rule_id in used:
        warnings.append(f"规则号 {rule_id} 重复，已自动改名")
        rule_id, counter = next_auto_id(prefix, used, counter)
    used.add(rule_id)

    title = clean_cell(values.get("title", "")) or rule_id
    severity = severity_of(values.get("severity", ""))
    if not severity:
        severity = "B"
        warnings.append(f"{rule_id}: 未给出有效等级，按 B 处理，请人工确认")

    check_type = clean_cell(values.get("check_type", "")).strip().lower()
    if check_type not in {
        "page_sequence", "text_regex", "text_consistency", "numeric_range",
        "date_chain", "cross_page_merge", "cross_file", "visual", "manual", "python",
    }:
        check_type = "manual"

    rule = {
        "id": rule_id,
        "module": clean_cell(values.get("module", "")) or "客户要求",
        "title": title,
        "severity": severity,
        "fail_when": clean_cell(values.get("fail_when", "")),
        "evidence": evidence_of(values.get("evidence", "")),
        "scope": scope_of(values.get("scope", "")),
        "applies_when": clean_cell(values.get("applies_when", "")),
        "na_when": clean_cell(values.get("na_when", "")),
        "check": {"type": check_type, "params": {}},
        "doc": "",
    }
    if not rule["fail_when"]:
        warnings.append(f"{rule_id}: 未解析到不通过条件")
    if "；" in rule["fail_when"]:
        warnings.append(f"{rule_id}: 不通过条件含多个分句，建议拆成多条规则")
    return rule, counter, warnings


def parse_table_rules(lines: list[str], prefix: str) -> tuple[list[dict], list[str]]:
    rules: list[dict] = []
    warnings: list[str] = []
    used: set[str] = set()
    counter = 0
    for rows in iter_tables(lines):
        if len(rows) < 3:
            continue
        columns = map_header(rows[0])
        if not is_rule_table(columns):
            continue
        for row in rows[2:]:
            if not any(row):
                continue
            if set("".join(row)) <= {"-", ":", " "}:
                continue
            values = {
                field: (row[index] if index < len(row) else "")
                for field, index in columns.items()
            }
            rule, counter, rule_warnings = rule_from_values(values, prefix, used, counter)
            rules.append(rule)
            warnings.extend(rule_warnings)
    return rules, warnings


def parse_heading_rules(lines: list[str], prefix: str) -> tuple[list[dict], list[str]]:
    field_aliases = {
        "module": MODULE_ALIASES,
        "fail_when": FAIL_ALIASES,
        "evidence": EVIDENCE_ALIASES,
        "scope": SCOPE_ALIASES,
        "applies_when": APPLIES_ALIASES,
        "na_when": NA_ALIASES,
        "check_type": CHECK_ALIASES,
        "severity": SEVERITY_ALIASES,
    }
    rules: list[dict] = []
    warnings: list[str] = []
    used: set[str] = set()
    counter = 0

    candidates: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        heading = HEADING_RE.match(line)
        if heading:
            candidates.append((index, len(heading.group(1)), heading.group(2).strip()))
            continue
        stripped = line.strip()
        if stripped.startswith("|"):
            continue
        plain = PLAIN_RULE_RE.match(stripped)
        if plain:
            candidates.append((index, 2, stripped))

    for position, (start, level, raw_title) in enumerate(candidates):
        end = candidates[position + 1][0] if position + 1 < len(candidates) else len(lines)
        id_match = HEADING_ID_RE.match(raw_title)
        rule_id = id_match.group(1) if id_match else ""
        title = id_match.group(2).strip() if id_match else raw_title

        values: dict[str, str] = {}
        for line in lines[start + 1:end]:
            bullet = BULLET_RE.match(line)
            if bullet:
                name = norm_header(bullet.group(1))
                value = bullet.group(2).strip()
            else:
                plain_field = PLAIN_FIELD_RE.match(line.strip())
                if not plain_field:
                    continue
                name = norm_header(plain_field.group(1))
                value = plain_field.group(2).strip()
            for field, names in field_aliases.items():
                if field not in values and any(alias in name for alias in names):
                    values[field] = value

        if "fail_when" not in values:
            continue
        if not rule_id:
            rule_id, counter = next_auto_id(prefix, used, counter)
            used.add(rule_id)
        else:
            if rule_id in used:
                warnings.append(f"规则号 {rule_id} 重复，已跳过重复条目")
                continue
            used.add(rule_id)
            counter = max(counter, int(rule_id[1:]))

        severity = severity_of(values.get("severity", "")) or severity_of(title)
        title = SEVERITY_IN_TITLE_RE.sub("", title).strip()
        rule = {
            "id": rule_id,
            "module": clean_cell(values.get("module", "")) or "客户要求",
            "title": clean_cell(title) or rule_id,
            "severity": severity or "B",
            "fail_when": clean_cell(values.get("fail_when", "")),
            "evidence": evidence_of(values.get("evidence", "")),
            "scope": scope_of(values.get("scope", "")),
            "applies_when": clean_cell(values.get("applies_when", "")),
            "na_when": clean_cell(values.get("na_when", "")),
            "check": {"type": clean_cell(values.get("check_type", "")).lower() or "manual", "params": {}},
            "doc": "",
        }
        if not severity:
            warnings.append(f"{rule_id}: 未给出有效等级，按 B 处理，请人工确认")
        rules.append(rule)
    return rules, warnings


def read_source_text(path: Path, workdir: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".docx":
        extract_docx(path, workdir, render=False, convert=False)
        return (workdir / "document.md").read_text(encoding="utf-8")
    if suffix == ".pdf":
        extract_pdf(path, workdir, render=False, extract_tables=True)
        tables = workdir / "tables.md"
        document = workdir / "document.md"
        parts = []
        if tables.is_file():
            parts.append(tables.read_text(encoding="utf-8"))
        if document.is_file():
            parts.append(document.read_text(encoding="utf-8"))
        return "\n\n".join(parts)
    raise SystemExit(f"不支持的规则文档类型: {path.suffix}（支持 .md/.txt/.docx/.pdf）")


def parse_rules(text: str, prefix: str) -> tuple[list[dict], list[str]]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    tables, table_warnings = parse_table_rules(text.splitlines(), prefix)
    if tables:
        return tables, table_warnings
    return parse_heading_rules(text.splitlines(), prefix)


def slugify(name: str) -> str:
    value = unicodedata.normalize("NFKC", name).strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    if not value:
        digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
        return f"rules-{digest}"
    return value


def build_pack_markdown(pack: dict) -> str:
    rows = [
        "| 规则ID | 模块 | 检查项 | 不通过条件 | 等级 | 取证位置 | 检查类型 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for rule in pack["rules"]:
        values = [
            rule["id"],
            rule.get("module", ""),
            rule.get("title", ""),
            rule.get("fail_when", ""),
            rule.get("severity", ""),
            "、".join(rule.get("evidence", []) or []),
            (rule.get("check") or {}).get("type", ""),
        ]
        rows.append("| " + " | ".join(str(value).replace("|", "\\|") for value in values) + " |")
    source = (pack.get("compiled_from") or {}).get("source", "")
    return "\n".join(
        [
            f"# 规则包：{pack.get('title') or pack['pack']}",
            "",
            f"- 规则包：`{pack['pack']}@{pack['version']}`",
            f"- 状态：`{pack.get('status', 'draft')}`",
            f"- 来源：`{source}`",
            f"- 编译时间：{pack.get('compiled_from', {}).get('compiled_at', '')}",
            "",
            "> 本文件由 `rules_compile.py` 生成，供人阅读；执行以 `pack.json` 为准。",
            "",
            *rows,
            "",
        ]
    )


def compile_pack(
    source: Path,
    pack_name: str,
    out_dir: Path,
    *,
    prefix: str = "X",
    title: str = "",
    version: str = "1.0.0",
    copy_source: bool = True,
) -> dict:
    """Compile one rule document into ``<out_dir>/pack.json``."""
    if not PACK_NAME_RE.match(pack_name):
        raise SystemExit(f"pack 名称必须是小写字母/数字/连字符: {pack_name!r}")
    if not source.is_file():
        raise SystemExit(f"规则文档不存在: {source}")

    if copy_source:
        source_dir = out_dir / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        target = source_dir / source.name
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        source = target

    with tempfile.TemporaryDirectory(prefix="rules-extract-") as tmp:
        text = read_source_text(source, Path(tmp))
    rules, warnings = parse_rules(text, prefix)
    if not rules:
        raise SystemExit(
            "未从规则文档解析出任何规则。请确认文档包含规则表"
            "（列：规则ID/检查项/不通过条件/建议等级/取证位置）或每条规则一节的标题结构。"
        )

    for rule in rules:
        rule["doc"] = f"rules/packs/{pack_name}/rules.md#{rule['id']}"

    pack = {
        "pack": pack_name,
        "version": version,
        "title": title or f"{pack_name} 规则包",
        "status": "draft",
        "extends": "builtin",
        "compiled_from": {
            "source": f"source/{source.name}",
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "compiled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "compiler": "rules_compile.py",
        },
        "compile_warnings": warnings,
        "rules": rules,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pack.json").write_text(
        json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "rules.md").write_text(build_pack_markdown(pack), encoding="utf-8")
    return pack


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Compile a rule document into a rule pack JSON.")
    parser.add_argument("source", help="Rule document (.md/.txt/.docx/.pdf)")
    parser.add_argument("--pack", required=True, help="Pack name, lowercase letters/digits/hyphen")
    parser.add_argument("--out", help="Pack output directory (default: rules/packs/<pack>)")
    parser.add_argument("--prefix", default="X", help="Prefix for auto-assigned rule ids (default: X)")
    parser.add_argument("--title", default="", help="Human-readable pack title")
    parser.add_argument("--version", default="1.0.0", help="Semantic version (default: 1.0.0)")
    parser.add_argument("--no-copy", action="store_true", help="Do not copy the source into source/")
    args = parser.parse_args()

    source = Path(args.source)
    out_dir = Path(args.out) if args.out else RULES_DIR / "packs" / args.pack
    pack = compile_pack(
        source,
        args.pack,
        out_dir,
        prefix=args.prefix,
        title=args.title,
        version=args.version,
        copy_source=not args.no_copy,
    )

    print(f"[OK] {out_dir / 'pack.json'}")
    print(f"     pack={pack['pack']}@{pack['version']} rules={len(pack['rules'])} status={pack['status']}")
    for warning in pack["compile_warnings"]:
        print(f"     [WARN] {warning}")
    print("     next: rules_validate.py <pack.json> --activate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
