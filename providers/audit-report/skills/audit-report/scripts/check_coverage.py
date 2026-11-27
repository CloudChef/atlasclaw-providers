#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate the Markdown source of an audit report before HTML rendering.

Checks:
- exactly one coverage row per enabled rule (builtin JSON + active packs)
- each coverage result is one of: 通过 / 不通过 / 不适用 / 待复核 / 证据不足
- every finding heading has a valid severity ([A]/[B]/[C]) and a rule number
- every finding has 页码, 位置, 原文上下文 and 不规范说明 fields
- the 问题总表 lists every finding with page and line
- every rule marked 不通过 has a corresponding finding, and every finding's rule is marked 不通过 or uncertain
- 不适用 rows include a reason
- severity summary counts match the findings and coverage rows
- overall verdict is present; a confirmed 不通过 row must not be described as a pass

Usage:
    python check_coverage.py <audit-report.md> [...] [--rules <pack-dir-or-json>]
Exit code 0 = valid, 1 = problems found, 2 = rule pack error.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from _rules import RuleSet, RulesError, load_rules

VALID_RESULTS = {"通过", "不通过", "不适用", "待复核", "证据不足"}
UNCERTAIN_RESULTS = {"待复核", "证据不足"}
RESULT_ALIASES = {"不通过（不合格）": "不通过"}
RULE_ID_PATTERN = r"[A-Z]\d{2,}"
FINDING_ID_PATTERN = r"F-(?:\d+-\d+|\d+)"
ROW_RE = re.compile(rf"^\|\s*({RULE_ID_PATTERN})\s*\|")
SUMMARY_RE = re.compile(r"^\|\s*(A · 严重|B · 主要|C · 次要|不适用)\s*\|\s*`?(\d+)`?\s*\|")
FINDING_RE = re.compile(
    rf"^###\s+({FINDING_ID_PATTERN})\s+\[([ABC])\]\s+(.+?)[（(]\s*`?({RULE_ID_PATTERN})`?\s*[）)]"
)
OVERVIEW_RE = re.compile(rf"^\|\s*({FINDING_ID_PATTERN})\s*\|")
VERDICT_RE = re.compile(r"\*\*总评[：:]\s*([^*]+?)\*\*")


def split_row(line: str) -> list[str]:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return cells


def check_report(path: Path, ruleset: RuleSet) -> list[str]:
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    coverage: dict[str, str] = {}
    for line in lines:
        match = ROW_RE.match(line)
        if not match:
            continue
        rule = match.group(1)
        cells = split_row(line)
        if len(cells) < 5:
            problems.append(f"{rule}: coverage row has fewer than 5 columns")
            continue
        if rule in coverage:
            problems.append(f"{rule}: duplicate coverage row")
        result = cells[4].replace("`", "").strip()
        coverage[rule] = RESULT_ALIASES.get(result, result)
        if coverage[rule] == "不适用":
            reason = cells[5] if len(cells) > 5 else ""
            if not reason or reason in {"略", "—", "-", "无"}:
                problems.append(f"{rule}: {coverage[rule]} requires a reason in the last column")

    missing = [rule for rule in ruleset.ids if rule not in coverage]
    if missing:
        problems.append("missing coverage rows: " + ", ".join(missing))

    unknown = [rule for rule in coverage if rule not in ruleset.rules]
    if unknown:
        problems.append(
            "coverage rows for rules not in the enabled rule set: " + ", ".join(sorted(unknown))
        )

    for rule, result in coverage.items():
        if result not in VALID_RESULTS:
            problems.append(f"{rule}: invalid result '{result}' (expected 通过/不通过/不适用)")

    findings = []
    finding_positions: list[tuple[int, tuple[str, ...]]] = []
    for index, line in enumerate(lines):
        if not line.startswith("### "):
            continue
        match = FINDING_RE.match(line)
        if match:
            findings.append(match.groups())
            finding_positions.append((index, match.groups()))
        elif line.startswith("### F-"):
            problems.append(f"malformed finding heading: {line.strip()}")

    severity_count = {"A": 0, "B": 0, "C": 0}
    finding_rules: set[str] = set()
    for finding_id, severity, _, rule in findings:
        severity_count[severity] += 1
        finding_rules.add(rule)
        if rule not in coverage:
            problems.append(f"{finding_id}: references {rule} which has no coverage row")
        elif coverage[rule] not in {"不通过", *UNCERTAIN_RESULTS}:
            problems.append(
                f"{finding_id}: {rule} coverage result is '{coverage[rule]}' but the finding implies 不通过"
            )

    uncovered_failures = [
        rule for rule, result in coverage.items() if result == "不通过" and rule not in finding_rules
    ]
    if uncovered_failures:
        problems.append(
            "rules marked 不通过 without a finding: " + ", ".join(sorted(uncovered_failures))
        )

    field_patterns = {
        name: re.compile(
            rf"(?:^-\s*\*\*{name}\*\*[：:]\s*(\S.*)$|^\|\s*{name}\s*\|\s*([^|]+)\|)",
            re.M,
        )
        for name in ("页码", "位置", "原文上下文", "不规范说明")
    }
    for position, (finding_id, _severity, _title, _rule) in finding_positions:
        end = next(
            (
                index
                for index in range(position + 1, len(lines))
                if lines[index].startswith("### F-") or lines[index].startswith("## ")
            ),
            len(lines),
        )
        block = "\n".join(lines[position + 1 : end])
        for name, pattern in field_patterns.items():
            match = pattern.search(block)
            value = (match.group(1) or match.group(2) or "").strip() if match else ""
            if not value or value in {"—", "-", "略"} or value.startswith("<"):
                problems.append(f"{finding_id}: missing/empty {name}")

    overview_ids: set[str] = set()
    for line in lines:
        match = OVERVIEW_RE.match(line)
        if not match:
            continue
        overview_ids.add(match.group(1))
        cells = split_row(line)
        if len(cells) < 6 or not cells[3] or not cells[4]:
            problems.append(f"{match.group(1)}: 问题总表 row missing 页码/位置")
    finding_ids = {finding[0] for finding in findings}
    if findings and not overview_ids:
        problems.append("missing 问题总表 (overview table with F-xx rows)")
    elif findings:
        missing_overview = finding_ids - overview_ids
        extra_overview = overview_ids - finding_ids
        if missing_overview:
            problems.append("findings missing from 问题总表: " + ", ".join(sorted(missing_overview)))
        if extra_overview:
            problems.append("问题总表 rows without a finding: " + ", ".join(sorted(extra_overview)))

    summary: dict[str, int] = {}
    for line in lines:
        match = SUMMARY_RE.match(line)
        if match:
            summary[match.group(1)] = int(match.group(2))
    if not summary:
        problems.append("missing severity summary table (A/B/C/不适用 counts)")
    else:
        expected = {
            "A · 严重": severity_count["A"],
            "B · 主要": severity_count["B"],
            "C · 次要": severity_count["C"],
            "不适用": sum(1 for result in coverage.values() if result == "不适用"),
        }
        for key, value in expected.items():
            if key not in summary:
                problems.append(f"summary table missing row: {key}")
            elif summary[key] != value:
                problems.append(f"summary {key} is {summary[key]} but actual count is {value}")

    verdict_match = VERDICT_RE.search(text)
    if not verdict_match:
        problems.append("missing '**总评：...**' verdict")
    else:
        verdict = verdict_match.group(1).strip()
        has_confirmed_failure = any(result == "不通过" for result in coverage.values())
        if has_confirmed_failure and "不通过" not in verdict:
            problems.append(
                f"verdict '{verdict}' conflicts with coverage marked 不通过"
            )

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate audit-report coverage of builtin and enabled rule packs."
    )
    parser.add_argument("reports", nargs="+", help="Audit report markdown files")
    parser.add_argument(
        "--rules",
        action="append",
        default=[],
        help="Extra rule pack directory or pack.json (repeatable; config.json packs load by default)",
    )
    parser.add_argument("--include-drafts", action="store_true", help="Also load draft packs (debug only)")
    args = parser.parse_args()

    try:
        ruleset = load_rules(extra=args.rules, include_drafts=args.include_drafts)
    except RulesError as exc:
        print(f"[ERROR] {exc}")
        return 2

    if ruleset.extra_ids:
        print(f"[rules] {ruleset.summary()}")

    failed = False
    for raw in args.reports:
        path = Path(raw)
        if not path.is_file():
            print(f"[ERROR] not found: {path}")
            failed = True
            continue
        problems = check_report(path, ruleset)
        if problems:
            failed = True
            print(f"[FAIL] {path}")
            for problem in problems:
                print(f"  - {problem}")
        else:
            builtin_total = len(ruleset.builtin_ids)
            message = f"{builtin_total}/{builtin_total} builtin"
            extra_total = len(ruleset.extra_ids)
            if extra_total:
                message += f" + {extra_total}/{extra_total} extra"
            print(f"[OK] {path.name}: {message} rules covered")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
