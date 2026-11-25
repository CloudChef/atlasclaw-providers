#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify audit findings against the extracted source text and screenshots.

This is the deterministic half of the final finding check:
- page number exists in the extracted document
- at least one quoted excerpt actually occurs on that page
- the screenshot exists and is a valid image
- the rule exists and the severity matches the rule pack
- the coverage table marks that rule as 不通过

Semantic correctness (does the evidence really violate the rule?) still needs
the checklist in references/finding-verification.md, plus human/multimodal
review for image-only findings.

Usage:
    python verify_findings.py report.md --source <extracted-dir> --evidence <dir>
        --out verification.md --json verification.json [--strict]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

from _rules import RulesError, load_rules

FINDING_RE = re.compile(r"^###\s+(F-\d+)\s+\[([ABC])\]\s+(.+?)[（(]\s*`?([A-Z]\d{2})`?\s*[）)]")
ROW_RE = re.compile(r"^\|\s*([A-Z]\d{2})\s*\|")
IMAGE_RE = re.compile(r"!\[.*?\]\((.+?)\)")
VISUAL_KEYWORDS = ("照片", "截图", "图像", "签章", "签名", "印章", "骑缝", "AI 生成", "水印", "空白")


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("→", "")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，,。；;、:：/|\\()（）\[\]【】「」“”\"'‘’<>《》]", "", text)
    return text.lower()


def load_pages(source: Path) -> dict[int, str]:
    if source.is_dir():
        lines_file = source / "lines.md"
        doc_file = source / "document.md"
        source = lines_file if lines_file.is_file() else doc_file
    if not source.is_file():
        raise SystemExit(f"Source text not found: {source}")

    text = source.read_text(encoding="utf-8")
    pages: dict[int, str] = {}
    current = None
    for line in text.splitlines():
        heading = re.match(r"^##\s*Page\s+(\d+)\s*$", line.strip())
        if heading:
            current = int(heading.group(1))
            pages.setdefault(current, "")
            continue
        if current is None:
            continue
        line = re.sub(r"^L\d+\s*\|\s?", "", line)
        pages[current] += line + "\n"
    return pages


def parse_findings(lines: list[str]) -> list[dict]:
    findings = []
    for index, line in enumerate(lines):
        match = FINDING_RE.match(line)
        if not match:
            continue
        finding_id, severity, title, rule = match.groups()
        end = next(
            (i for i in range(index + 1, len(lines))
             if lines[i].startswith("### F-") or lines[i].startswith("## ")),
            len(lines),
        )
        block = "\n".join(lines[index + 1:end])
        page_match = re.search(r"^- \*\*页码\*\*[：:]\s*(.+)$", block, re.M)
        position_match = re.search(r"^- \*\*位置\*\*[：:]\s*(.+)$", block, re.M)
        context_match = re.search(
            r"^- \*\*原文上下文\*\*[：:]\s*\n?(.*?)(?=^- \*\*(?:不规范说明|影响|整改建议|关联问题|证据截图)\*\*[：:])",
            block,
            re.M | re.S,
        )
        screenshot_match = IMAGE_RE.search(block)
        pages = [int(x) for x in re.findall(r"\d+", page_match.group(1))] if page_match else []
        quotes = []
        if context_match:
            context = context_match.group(1)
            for match in re.finditer(r"「([^」]+)」|“([^”]+)”", context):
                quote = (match.group(1) or match.group(2) or "").strip()
                before = context[max(0, match.start() - 8):match.start()]
                after = context[match.end():match.end() + 12]
                if any(word in before for word in ("0 次", "未出现", "未列", "缺失", "未提及", "没有", "无")):
                    continue
                if any(word in after for word in ("0 次", "未出现", "未列", "缺失", "未提及", "没有")):
                    continue
                quotes.append(quote)
        findings.append(
            {
                "id": finding_id,
                "severity": severity,
                "title": title.strip(),
                "rule": rule,
                "pages": pages,
                "position": position_match.group(1).strip() if position_match else "",
                "quotes": [q.strip() for q in quotes if len(q.strip()) >= 4],
                "screenshot": screenshot_match.group(1).strip() if screenshot_match else None,
                "block": block,
            }
        )
    return findings


def coverage_results(lines: list[str]) -> dict[str, str]:
    results = {}
    for line in lines:
        match = ROW_RE.match(line)
        if not match:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 5:
            results[match.group(1)] = cells[4].replace("`", "").strip()
    return results


def check_quote(quote: str, page_text: str) -> str:
    """Return full / partial / missing.

    Exact normalized matching is tried first. If the report paraphrases a
    label/value line (e.g. drops "Test Date:"), fall back to significant
    tokens (IDs, dates, Chinese phrases) so legitimate citations are not
    rejected just because of bilingual layout.
    """
    q = norm(quote)
    if len(q) < 4:
        return "skipped"
    page_norm = norm(page_text)
    if q in page_norm:
        return "full"

    tokens = [
        token for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9._/+-]{2,}|[\u4e00-\u9fff]{2,}", quote)
        if len(token) >= 3 or re.search(r"\d", token)
    ]
    if not tokens:
        return "missing"
    missing = [token for token in tokens if norm(token) not in page_norm]
    if not missing:
        return "full"
    if len(missing) <= max(1, len(tokens) // 4):
        return "partial"
    return "missing"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Verify audit findings against extracted text and screenshots.")
    parser.add_argument("report", help="Audit report Markdown")
    parser.add_argument("--source", required=True, help="Extracted lines.md/document.md, or their directory")
    parser.add_argument("--evidence", help="Evidence screenshot directory (default: report dir)")
    parser.add_argument("--out", help="Verification Markdown output")
    parser.add_argument("--json", help="Verification JSON output")
    parser.add_argument("--strict", action="store_true", help="Fail on REVIEW as well as FAIL")
    parser.add_argument(
        "--page-window",
        type=int,
        default=1,
        help="Allow evidence found on a cited page ±N (default: 1, for cross-page tables)",
    )
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
    rule_severity = ruleset.severity

    report_path = Path(args.report)
    text = report_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    pages = load_pages(Path(args.source))
    findings = parse_findings(lines)
    coverage = coverage_results(lines)
    evidence_dir = Path(args.evidence) if args.evidence else report_path.parent

    results = []
    for finding in findings:
        status = "PASS"
        reasons = []

        rule = finding["rule"]
        if rule not in rule_severity:
            status = "FAIL"
            reasons.append(f"未知规则 {rule}（已启用规则包：{ruleset.summary()}）")
        elif finding["severity"] != rule_severity[rule]:
            status = "FAIL"
            reasons.append(f"等级 {finding['severity']} 与规则固定等级 {rule_severity[rule]} 不一致")

        if coverage.get(rule) != "不通过":
            status = "FAIL"
            reasons.append(f"覆盖表中 {rule} 不是“不通过”（实际 {coverage.get(rule, '缺失')}）")

        if not finding["pages"]:
            status = "FAIL"
            reasons.append("缺少页码")
        else:
            invalid_pages = [p for p in finding["pages"] if p not in pages]
            if invalid_pages:
                status = "FAIL"
                reasons.append(f"页码 {invalid_pages} 不在源文档中")
            else:
                visual = any(keyword in finding["title"] for keyword in VISUAL_KEYWORDS) or all(
                    not pages[p].strip() for p in finding["pages"]
                )
                found_any = 0
                found_cited = 0
                found_adjacent = 0
                found_elsewhere = 0
                missing = 0
                partial = 0
                for quote in finding["quotes"]:
                    cited_statuses = [check_quote(quote, pages[p]) for p in finding["pages"]]
                    if any(s == "full" for s in cited_statuses):
                        found_any += 1
                        found_cited += 1
                    elif any(s == "partial" for s in cited_statuses):
                        found_any += 1
                        found_cited += 1
                        partial += 1
                    elif all(s == "skipped" for s in cited_statuses):
                        continue
                    else:
                        adjacent = []
                        for cited_page in finding["pages"]:
                            for delta in range(1, args.page_window + 1):
                                for candidate in (cited_page - delta, cited_page + delta):
                                    if candidate in pages and check_quote(quote, pages[candidate]) != "missing":
                                        adjacent.append(candidate)
                        if adjacent:
                            found_any += 1
                            found_adjacent += 1
                            continue
                        elsewhere = [
                            candidate for candidate in pages
                            if check_quote(quote, pages[candidate]) != "missing"
                        ]
                        if elsewhere:
                            found_any += 1
                            found_elsewhere += 1
                        else:
                            missing += 1

                if not finding["quotes"]:
                    if status != "FAIL":
                        status = "REVIEW"
                    reasons.append("无文本引文，需查看截图/人工复核")
                elif found_any == 0:
                    if visual:
                        if status != "FAIL":
                            status = "REVIEW"
                        reasons.append("引文未在文本层找到，可能来自图像，需人工/多模态复核")
                    else:
                        status = "FAIL"
                        reasons.append("引文在文本层完全找不到，疑似编造")
                elif missing:
                    if status != "FAIL":
                        status = "REVIEW"
                    reasons.append(f"{missing} 条引文未在文本层找到，需人工确认")
                elif found_cited == 0 and found_adjacent:
                    reasons.append("引文在相邻页，已按跨页内容核对")
                elif found_cited == 0 and found_elsewhere:
                    if status != "FAIL":
                        status = "REVIEW"
                    reasons.append("引文未出现在报告页码的页面，可能页码错误")
                elif partial:
                    if status != "FAIL":
                        status = "REVIEW"
                    reasons.append("部分引文只匹配到片段，需人工确认")
                elif found_elsewhere:
                    reasons.append("部分引文在其他页，已按上下文引用核对")

        screenshot = finding["screenshot"]
        if not screenshot:
            status = "FAIL"
            reasons.append("缺少证据截图")
        else:
            image_path = Path(screenshot)
            candidates = []
            if image_path.is_absolute():
                candidates.append(image_path)
            else:
                candidates.extend([
                    report_path.parent / image_path,
                    evidence_dir / image_path,
                    evidence_dir / image_path.name,
                ])
            image_path = next((path for path in candidates if path.is_file()), candidates[0])
            if not image_path.is_file():
                status = "FAIL"
                reasons.append(f"截图文件不存在: {screenshot}")
            elif image_path.stat().st_size < 1000:
                status = "FAIL"
                reasons.append("截图文件过小")
            else:
                sidecar = image_path.with_suffix(image_path.suffix + ".json")
                if sidecar.is_file() and finding["pages"]:
                    try:
                        meta = json.loads(sidecar.read_text(encoding="utf-8"))
                        if meta.get("page") and meta["page"] not in finding["pages"]:
                            status = "FAIL"
                            reasons.append(
                                f"截图页码 {meta['page']} 不在报告页码 {finding['pages']} 中"
                            )
                    except (OSError, ValueError):
                        reasons.append("截图 sidecar 无法读取")

        if any(keyword in finding["title"] for keyword in VISUAL_KEYWORDS) and status == "PASS":
            status = "REVIEW"
            reasons.append("视觉类问题，需人工/多模态模型确认截图内容")

        results.append(
            {
                "id": finding["id"],
                "rule": rule,
                "severity": finding["severity"],
                "page": finding["pages"][0] if finding["pages"] else None,
                "title": finding["title"],
                "status": status,
                "reasons": reasons,
            }
        )

    counts = {"PASS": 0, "REVIEW": 0, "FAIL": 0}
    for result in results:
        counts[result["status"]] += 1

    out_lines = [
        "# 问题核验",
        "",
        f"- 规则包：{ruleset.summary()}",
        f"- 问题数：{len(results)}",
        f"- 通过：{counts['PASS']}",
        f"- 待人工/多模态复核：{counts['REVIEW']}",
        f"- 未通过：{counts['FAIL']}",
        "",
        "| 问题 | 规则/等级 | 页码 | 引文/截图核验 | 结论 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for result in results:
        out_lines.append(
            f"| {result['id']} | {result['rule']}/{result['severity']} | {result['page'] or '-'} | "
            f"{'；'.join(result['reasons']) or '页码、引文、截图、规则等级均通过'} | {result['status']} |"
        )
    out_lines.append("")
    out_lines.append("> PASS 仅表示页码/引文/截图/规则/等级在文本层可核对；")
    out_lines.append("> REVIEW 表示引文来自图像、部分引文未命中或视觉类问题，必须人工/多模态复核；")
    out_lines.append("> FAIL 表示存在页码错误、引文找不到、截图缺失、规则/等级不一致等硬错误，必须修正后重跑。")

    verification_text = "\n".join(out_lines)
    if args.out:
        Path(args.out).write_text(verification_text, encoding="utf-8")
    if args.json:
        Path(args.json).write_text(
            json.dumps({"counts": counts, "results": results}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(verification_text)

    if counts["FAIL"]:
        return 1
    if args.strict and counts["REVIEW"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
