# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.
"""Deterministic batched audit pipeline used by the audit-report provider.

The provider pre-extracts the document text itself and then asks the model to
judge a small, fixed set of rules against a bounded text chunk. Every model
answer is structured JSON, so the provider can always assemble a complete HTML
report instead of depending on the model finishing one very large task.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

logger = logging.getLogger(__name__)

MAX_CHUNK_CHARS = 60_000
RULE_BATCH_SIZE = 7
VERDICTS = ("PASS", "FAIL", "REVIEW", "NA")
VERDICT_LABELS = {"PASS": "通过", "FAIL": "不通过", "REVIEW": "待复核", "NA": "不适用"}
SEVERITY_ORDER = {"A": 0, "B": 1, "C": 2}
SEVERITY_LABELS = {"A": "A · 严重", "B": "B · 主要", "C": "C · 次要"}
RULE_MODULES = {
    "R01": "文件合规", "R02": "文件合规", "R03": "文件合规",
    "R04": "身份唯一性", "R05": "身份唯一性", "R06": "身份唯一性",
    "R07": "标准与方法", "R08": "标准与方法",
    "R09": "数据与结论", "R10": "数据与结论", "R11": "数据与结论", "R12": "数据与结论",
    "R13": "时间逻辑", "R14": "时间逻辑", "R15": "时间逻辑",
    "R16": "资质声明", "R17": "语法规范性", "R18": "语法规范性", "R19": "照片有效性",
}
RULE_HEADING = re.compile(r"^## (R\d{2})\s+(.+?)（([ABC])\s*·\s*[^）]+）\s*$", re.M)


@dataclass(frozen=True)
class Rule:
    """One audit rule parsed from the builtin reference or a rule pack."""

    rule_id: str
    title: str
    severity: str
    guidance: str
    module_name: str = ""
    pack: str = "builtin"

    @property
    def module(self) -> str:
        """Return the reporting module that owns this rule."""
        return self.module_name or RULE_MODULES.get(self.rule_id, "其他")


@dataclass(frozen=True)
class TextChunk:
    """A bounded slice of the extracted document text."""

    index: int
    first_page: int
    last_page: int
    text: str

    @property
    def label(self) -> str:
        """Return a human readable page range label."""
        if self.first_page == self.last_page:
            return f"第 {self.first_page} 页"
        return f"第 {self.first_page}–{self.last_page} 页"


@dataclass
class Verdict:
    """One model judgement for one rule against one text chunk."""

    rule: str
    verdict: str
    severity: str
    page: str = ""
    quote: str = ""
    problem: str = ""
    suggestion: str = ""


@dataclass
class RuleResult:
    """Aggregated judgement for one rule across all chunks."""

    rule: Rule
    verdict: str
    severity: str
    evidence: list[Verdict] = field(default_factory=list)


def load_rules(rules_path: Path) -> list[Rule]:
    """Parse the 19 fixed rule definitions from the skill reference."""
    text = rules_path.read_text(encoding="utf-8")
    matches = list(RULE_HEADING.finditer(text))
    rules: list[Rule] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        # Skip trailing sections such as 附录 that follow the last rule heading.
        if not match.group(1).startswith("R"):
            continue
        rule_id = match.group(1)
        rules.append(
            Rule(
                rule_id=rule_id,
                title=match.group(2).strip(),
                severity=match.group(3),
                guidance=body,
                module_name=RULE_MODULES.get(rule_id, "其他"),
            )
        )
    return rules


def load_rule_set(
    skill_dir: Path,
    include_drafts: bool = False,
    rules_dir: Path | None = None,
) -> tuple[list[Rule], list[str]]:
    """Load builtin rules plus active packs from a rules directory.

    ``rules_dir`` defaults to ``<skill>/rules``; the provider passes the shared
    rules root so packs compiled from the standards library are picked up.
    Returns the rules and pack labels such as ``["builtin@1.0.0", "pack@1.0.0"]``.
    Missing or invalid pack files are logged and skipped so a broken extra pack
    cannot stop an audit.
    """
    rules_dir = Path(rules_dir) if rules_dir else skill_dir / "rules"
    reference_path = skill_dir / "references" / "audit-rules.md"
    config = _read_json(rules_dir / "config.json") if (rules_dir / "config.json").is_file() else {}
    builtin_path = Path(str(config.get("builtin") or "builtin/rules.json"))
    if not builtin_path.is_absolute():
        builtin_path = rules_dir / builtin_path
    packs: list[str] = []
    rules: list[Rule] = []

    builtin_rules = _load_builtin_pack(builtin_path, reference_path)
    if builtin_rules:
        rules.extend(builtin_rules)
        payload = _read_json(builtin_path)
        packs.append(f"{payload.get('pack', 'builtin')}@{payload.get('version', '0.0.0')}")
    elif reference_path.is_file():
        rules.extend(load_rules(reference_path))
        packs.append("builtin")

    seen = {rule.rule_id for rule in rules}
    inbox = rules_dir / "_inbox"
    if inbox.is_dir():
        pending = [
            path.name for path in inbox.iterdir()
            if path.is_file()
            and path.suffix.lower() in {".md", ".txt", ".docx", ".pdf"}
            and path.stem.lower() != "readme"
        ]
        if pending:
            logger.warning(
                "Uncompiled audit rule documents in %s: %s; run rules_sync.py before relying on them",
                inbox,
                ", ".join(sorted(pending)),
            )
    for entry in config.get("packs") or []:
        path = Path(str(entry))
        if not path.is_absolute():
            path = rules_dir / path
        if path.is_dir():
            path = path / "pack.json"
        if not path.is_file():
            logger.warning("Audit rule pack is missing: %s", path)
            continue
        payload = _read_json(path)
        if not payload:
            logger.warning("Audit rule pack is unreadable: %s", path)
            continue
        if payload.get("status", "active") != "active" and not include_drafts:
            continue
        pack_name = str(payload.get("pack") or path.parent.name)
        for item in payload.get("rules") or []:
            if not isinstance(item, dict):
                continue
            rule_id = str(item.get("id") or "").strip()
            if not rule_id or rule_id in seen:
                if rule_id:
                    logger.warning("Duplicate audit rule id %s in pack %s; skipped", rule_id, pack_name)
                continue
            seen.add(rule_id)
            rules.append(
                Rule(
                    rule_id=rule_id,
                    title=str(item.get("title") or rule_id),
                    severity=str(item.get("severity") or "B"),
                    guidance=_pack_guidance(item),
                    module_name=str(item.get("module") or "客户要求"),
                    pack=pack_name,
                )
            )
        packs.append(f"{pack_name}@{payload.get('version', '0.0.0')}")
    return rules, packs


def _load_builtin_pack(builtin_path: Path, reference_path: Path) -> list[Rule]:
    """Build builtin rules from rules.json, using the reference for guidance."""
    if not builtin_path.is_file():
        return []
    payload = _read_json(builtin_path)
    if not payload:
        return []
    guidance = {rule.rule_id: rule.guidance for rule in load_rules(reference_path)} if reference_path.is_file() else {}
    rules: list[Rule] = []
    for item in payload.get("rules") or []:
        if not isinstance(item, dict):
            continue
        rule_id = str(item.get("id") or "").strip()
        if not rule_id:
            continue
        rules.append(
            Rule(
                rule_id=rule_id,
                title=str(item.get("title") or rule_id),
                severity=str(item.get("severity") or "B"),
                guidance=guidance.get(rule_id, _pack_guidance(item)),
                module_name=str(item.get("module") or RULE_MODULES.get(rule_id, "其他")),
            )
        )
    return rules


def _pack_guidance(item: dict[str, Any]) -> str:
    """Turn a pack rule's structured fields into prompt guidance."""
    lines: list[str] = []
    fail_when = str(item.get("fail_when") or "").strip()
    if fail_when:
        lines.append(f"不通过条件：{fail_when}")
    applies_when = str(item.get("applies_when") or "").strip()
    if applies_when:
        lines.append(f"适用前提：{applies_when}")
    na_when = str(item.get("na_when") or "").strip()
    if na_when:
        lines.append(f"不适用条件：{na_when}")
    evidence = item.get("evidence") or []
    if isinstance(evidence, str):
        evidence = [evidence]
    if evidence:
        lines.append("取证位置：" + "、".join(str(value) for value in evidence))
    if str(item.get("scope") or "") == "batch":
        lines.append("适用范围：同批全部文件")
    return "\n".join(lines)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def chunk_document(text: str) -> tuple[list[TextChunk], str]:
    """Split page-marked extraction output into bounded chunks.

    Returns all chunks in document order. The chunk size controls request
    batching only; it does not limit the amount of source text processed.
    """
    pages = re.split(r"^## Page (\d+)\s*$", text, flags=re.M)
    header = pages[0].strip()
    blocks: list[tuple[int, str]] = []
    for index in range(1, len(pages) - 1, 2):
        blocks.append((int(pages[index]), f"## Page {pages[index]}\n\n{pages[index + 1].strip()}"))
    if not blocks:
        body = text.strip()
        chunks = [
            TextChunk(i // MAX_CHUNK_CHARS, 1, 1, body[i:i + MAX_CHUNK_CHARS])
            for i in range(0, len(body), MAX_CHUNK_CHARS)
        ]
        return chunks, ""

    chunks: list[TextChunk] = []
    buffer: list[str] = [header] if header else []
    size = sum(len(item) for item in buffer)
    first_page = blocks[0][0]
    last_page = blocks[0][0]
    for page_no, block in blocks:
        for offset in range(0, len(block), MAX_CHUNK_CHARS):
            part = block[offset:offset + MAX_CHUNK_CHARS]
            if buffer and size + len(part) > MAX_CHUNK_CHARS:
                chunks.append(TextChunk(len(chunks), first_page, last_page, "\n\n".join(buffer)))
                buffer = []
                size = 0
                first_page = page_no
            buffer.append(part)
            size += len(part) + 2
            last_page = page_no
    if buffer:
        chunks.append(TextChunk(len(chunks), first_page, last_page, "\n\n".join(buffer)))

    return chunks, ""


def rule_batches(rules: Sequence[Rule]) -> list[list[Rule]]:
    """Split rules into bounded batches; every active rule lands in exactly one batch."""
    if not rules:
        return []
    return [list(rules[index:index + RULE_BATCH_SIZE]) for index in range(0, len(rules), RULE_BATCH_SIZE)]


def _render_report_template(name: str, **values: str) -> str:
    """Render a trusted UTF-8 report template from the audit skill assets."""
    scripts_dir = Path(__file__).resolve().parents[1] / "skills" / "audit-report" / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from audit_project_prompts import render_report_template

    return render_report_template(name, **values)


def build_prompt(
    rules: Sequence[Rule],
    chunk: TextChunk,
    total_chunks: int,
    retry_note: str = "",
    total_pages: int = 0,
    rule_packs: Sequence[str] = (),
) -> str:
    """Build the strict JSON judgement prompt for one rule batch and chunk."""
    rule_text = "\n\n".join(
        f"### {rule.rule_id} {rule.title}（{rule.severity} 级，模块：{rule.module}）\n{rule.guidance}"
        for rule in rules
    )
    rule_ids = "、".join(rule.rule_id for rule in rules)
    retry = f"\n{retry_note}\n" if retry_note else ""
    scope = f"全文共 {total_pages} 页，" if total_pages else ""
    packs = " + ".join(rule_packs) if rule_packs else "builtin"
    scripts_dir = Path(__file__).resolve().parents[1] / "skills" / "audit-report" / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from audit_project_prompts import render_prompt_template

    return render_prompt_template("batch.md", RULE_IDS=rule_ids, PACKS=packs, RULE_TEXT=rule_text,
        CHUNK_LABEL=chunk.label, PAGE_SCOPE=scope, TOTAL_CHUNKS=str(total_chunks),
        CHUNK_TEXT=chunk.text, RETRY=retry)


def parse_answer(answer: str, rules: Sequence[Rule]) -> list[Verdict]:
    """Parse the model answer into normalized verdicts, dropping unknown rules."""
    known = {rule.rule_id: rule for rule in rules}
    for payload in _json_payloads(answer):
        items = payload.get("results") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            continue
        verdicts: list[Verdict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            rule_id = str(item.get("rule") or "").strip().upper()
            rule = known.get(rule_id)
            if rule is None:
                continue
            verdict = str(item.get("verdict") or "").strip().upper()
            if verdict not in VERDICTS:
                verdict = "REVIEW"
            # Severity is locked by the rule pack; the model cannot downgrade it.
            verdicts.append(
                Verdict(
                    rule=rule_id,
                    verdict=verdict,
                    severity=rule.severity,
                    page=_clean(str(item.get("page") or "")),
                    quote=_clean(str(item.get("quote") or "")),
                    problem=_clean(str(item.get("problem") or "")),
                    suggestion=_clean(str(item.get("suggestion") or "")),
                )
            )
        if verdicts:
            return verdicts
    return []


def merge_results(rules: Sequence[Rule], verdicts: Iterable[Verdict]) -> list[RuleResult]:
    """Aggregate per-chunk verdicts into one result per rule.

    A rule fails if any chunk reports a failure; missing judgements are marked
    as REVIEW so the report never claims an unchecked rule passed.
    """
    grouped: dict[str, list[Verdict]] = {rule.rule_id: [] for rule in rules}
    for verdict in verdicts:
        grouped.setdefault(verdict.rule, []).append(verdict)

    results: list[RuleResult] = []
    for rule in rules:
        items = grouped.get(rule.rule_id) or []
        failures = [item for item in items if item.verdict == "FAIL"]
        reviews = [item for item in items if item.verdict == "REVIEW"]
        if failures:
            results.append(RuleResult(rule, "FAIL", _worst_severity(failures, rule), failures + reviews))
        elif reviews:
            results.append(RuleResult(rule, "REVIEW", _worst_severity(reviews, rule), reviews))
        elif any(item.verdict == "PASS" for item in items):
            results.append(RuleResult(rule, "PASS", rule.severity, [i for i in items if i.verdict == "PASS"]))
        elif items:
            results.append(RuleResult(rule, "NA", rule.severity, items))
        else:
            results.append(
                RuleResult(
                    rule,
                    "REVIEW",
                    rule.severity,
                    [Verdict(rule.rule_id, "REVIEW", rule.severity, problem="自动判定未返回该规则结果")],
                )
            )
    return results


def summarize(results: Sequence[RuleResult]) -> dict[str, Any]:
    """Derive list metrics and the overall verdict from merged results."""
    findings = [item for item in results if item.verdict in {"FAIL", "REVIEW"}]
    grades: dict[str, int] = {}
    for item in findings:
        if item.verdict == "FAIL":
            grades[item.severity] = grades.get(item.severity, 0) + 1
    return {
        "findings_total": len(findings),
        "findings_review": sum(1 for item in findings if item.verdict == "REVIEW"),
        "grade_summary": grades,
        "verdict": "不通过" if findings else "通过",
    }


def finding_list(results: Sequence[RuleResult]) -> list[RuleResult]:
    """Return FAIL/REVIEW results in the order they appear as F-01, F-02... in the report."""
    return sorted(
        (item for item in results if item.verdict in {"FAIL", "REVIEW"}),
        key=lambda item: (SEVERITY_ORDER.get(item.severity, 9), item.rule.rule_id),
    )


def build_markdown(
    *,
    document: dict[str, Any],
    results: Sequence[RuleResult],
    manifest: dict[str, Any],
    started_at: datetime,
    finished_at: datetime,
    truncated_note: str = "",
    chunk_count: int = 1,
    rule_packs: Sequence[str] = (),
    evidence: dict[str, str] | None = None,
) -> str:
    """Render the audit markdown source that feeds render_report.py."""
    summary = summarize(results)
    total_rules = len(results)
    pack_label = " + ".join(rule_packs) or "builtin"
    extra_rules = max(0, total_rules - len(RULE_MODULES))
    extra_note = f" + 附加 {extra_rules} 项" if extra_rules else ""
    basis = f"规则包：{pack_label}"
    findings = finding_list(results)
    rows = [
        ("文件名", str(document.get("file_name") or "")),
        ("文件类型", "PDF" if str(document.get("extension") or "").lower() == ".pdf" else "Word（.docx）"),
        ("文件大小", _size_label(int(document.get("size") or 0))),
        ("SHA-256", str(manifest.get("sha256") or "")[:16] or "N/A"),
        ("报告页数", f"{int(manifest.get('page_count') or document.get('pages') or 0)} 页"),
        ("文本层", "完整" if manifest.get("has_text_layer") else "部分或缺失"),
        ("规则包", pack_label),
        ("审核时间", f"{started_at:%Y-%m-%d %H:%M}"),
        ("审核用时", f"{(finished_at - started_at).total_seconds() / 60:.1f} 分钟"),
        ("判定方式", f"文本预提取 + {total_rules} 项规则分批判定（{chunk_count} 个文本片段）"),
        ("审核依据", basis),
    ]
    object_rows = "\n".join(f"| {name} | {_cell(value)} |" for name, value in rows)
    audit_scope = _render_report_template("legacy-audit-scope.md", TOTAL_RULES=str(total_rules), EXTRA_NOTE=extra_note)
    verdict_rows = []
    for grade in ("A", "B", "C"):
        involved = "、".join(item.rule.rule_id for item in findings if item.verdict == "FAIL" and item.severity == grade)
        verdict_rows.append(f"| {SEVERITY_LABELS[grade]} | {summary['grade_summary'].get(grade, 0)} | {involved or '无'} |")
    na_rules = "、".join(item.rule.rule_id for item in results if item.verdict == "NA")
    verdict_rows.append(f"| 不适用 | {sum(1 for item in results if item.verdict == 'NA')} | {na_rules or '无'} |")

    if findings:
        finding_rows = []
        finding_details = []
        for index, item in enumerate(findings, start=1):
            page = item.evidence[0].page if item.evidence and item.evidence[0].page else "-"
            finding_rows.append(
                f"| F-{index:02d} | {item.rule.rule_id} | {item.severity} | 第 {page} 页 | {item.rule.module} | "
                f"{_cell(_finding_title(item))} |"
            )
            finding_details += _finding_detail(index, item, (evidence or {}).get(item.rule.rule_id, ""))
        finding_section = _render_report_template(
            "legacy-findings.md", FINDING_ROWS="\n".join(finding_rows),
            FINDING_DETAILS="\n".join(finding_details).rstrip("\n"),
        )
    else:
        finding_section = _render_report_template("legacy-no-findings.md", TOTAL_RULES=str(total_rules))

    na_items = [item for item in results if item.verdict == "NA"]
    if na_items:
        na_rows = []
        for index, item in enumerate(na_items, start=1):
            reason = item.evidence[0].problem if item.evidence and item.evidence[0].problem else "本报告不涉及该检查项"
            na_rows.append(f"| N-{index:02d} | {item.rule.rule_id} | {_cell(item.rule.title)} | {_cell(reason)} |")
        na_section = _render_report_template("legacy-na-items.md", NA_ROWS="\n".join(na_rows))
    else:
        na_section = _render_report_template("legacy-na-none.md")

    coverage_rows = []
    for item in results:
        first = item.evidence[0] if item.evidence else None
        location = "-"
        if first:
            location = f"第 {first.page} 页" if first.page else ""
            if first.quote:
                location = f"{location} {first.quote}".strip() if location else first.quote
            if not location:
                location = first.problem or "-"
        coverage_rows.append(
            f"| {item.rule.rule_id} | {item.rule.module} | {_cell(item.rule.title)} | {item.rule.severity} | "
            f"{VERDICT_LABELS[item.verdict]} | {_cell(location)} |"
        )

    missing = [item for item in results if item.verdict == "REVIEW" and "缺失" in item.evidence[0].problem]
    if missing:
        missing_rows = "\n".join(
            f"| {_cell(item.rule.title)} | 全文未见 | {item.rule.rule_id} | {_cell(item.evidence[0].problem)} |"
            for item in missing
        )
        missing_section = _render_report_template("legacy-missing.md", MISSING_ROWS=missing_rows)
    else:
        missing_section = _render_report_template("legacy-missing-none.md")

    observations = [
        _render_report_template("legacy-observation.md", RULE_ID=item.rule.rule_id,
                                TITLE=item.rule.title, PROBLEM=_cell(item.evidence[0].problem))
        for item in results if item.verdict == "REVIEW"
    ]
    observation_section = "\n".join(observations) if observations else _render_report_template("legacy-observations-none.md")

    return _render_report_template(
        "legacy-batch-report.md", OBJECT_ROWS=object_rows, AUDIT_SCOPE=audit_scope,
        VERDICT=summary["verdict"], VERDICT_ROWS="\n".join(verdict_rows),
        CONCLUSION=_conclusion(summary, findings, total_rules), FINDING_SECTION=finding_section,
        NA_SECTION=na_section, COVERAGE_ROWS="\n".join(coverage_rows), MISSING_SECTION=missing_section,
        OBSERVATIONS=observation_section,
        TEXT_LAYER="完整" if manifest.get("has_text_layer") else "部分扫描页无文本层",
        SCREENSHOTS=f"{len(evidence or {})} 条问题附 PDF 页面截图" if evidence else "无（未渲染页面图片）",
        BLANK_PAGES=_page_list(manifest), TRUNCATED_NOTE=_cell(truncated_note) if truncated_note else "无",
    ) + "\n"

def build_verification(
    results: Sequence[RuleResult],
    evidence: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the verification.json trace consumed by coverage checks and metrics."""
    counts = {name: 0 for name in VERDICTS}
    entries: list[dict[str, Any]] = []
    for item in results:
        counts[item.verdict] = counts.get(item.verdict, 0) + 1
        item_evidence = item.evidence[0] if item.evidence else None
        entries.append(
            {
                "rule": item.rule.rule_id,
                "title": item.rule.title,
                "verdict": item.verdict,
                "severity": item.severity,
                "page": item_evidence.page if item_evidence else "",
                "quote": item_evidence.quote if item_evidence else "",
                "problem": item_evidence.problem if item_evidence else "",
                "suggestion": item_evidence.suggestion if item_evidence else "",
                "image": (evidence or {}).get(item.rule.rule_id, ""),
            }
        )
    return {"generated_at": datetime.now().astimezone().isoformat(timespec="seconds"), "counts": counts, "results": entries}


def _finding_title(item: RuleResult) -> str:
    evidence = item.evidence[0] if item.evidence else None
    if evidence and evidence.problem:
        return evidence.problem
    return item.rule.title


def _finding_detail(index: int, item: RuleResult, image: str = "") -> list[str]:
    evidence = item.evidence[0] if item.evidence else Verdict(item.rule.rule_id, item.verdict, item.severity)
    page = evidence.page or "-"
    impact = (
        "该缺陷影响报告的有效性与结论可信度，需整改后重新审核。"
        if item.severity == "A"
        else "该缺陷影响报告的规范性，需整改后重新审核。"
    )
    title = _cell(_finding_title(item))
    screenshot_block = (
        _render_report_template("legacy-finding-screenshot.md", INDEX=f"{index:02d}", PAGE=page,
                                TITLE=title, IMAGE=image)
        if image else _render_report_template("legacy-no-finding-screenshot.md")
    )
    markdown = _render_report_template(
        "legacy-finding-detail.md", INDEX=f"{index:02d}", SEVERITY=item.severity, TITLE=title,
        RULE_ID=item.rule.rule_id, PACK=item.rule.pack, SEVERITY_LABEL=SEVERITY_LABELS[item.severity],
        PAGE=page, MODULE=_cell(item.rule.module), RULE_TITLE=_cell(item.rule.title),
        QUOTE=_cell(evidence.quote) or "见原报告", PROBLEM=_cell(evidence.problem) or item.rule.title,
        IMPACT=impact, SUGGESTION=_cell(evidence.suggestion) or "核实原始记录后修正报告并重新签发。",
        SCREENSHOT_BLOCK=screenshot_block,
    )
    return (markdown + "\n").split("\n")


def _conclusion(summary: dict[str, Any], findings: Sequence[RuleResult], total_rules: int = 19) -> str:
    if not findings:
        return f"报告未发现不符合项，{total_rules} 项规则均判定通过或不适用。"
    rules = "、".join(item.rule.rule_id for item in findings)
    return f"报告在 {rules} 检查项上存在不符合或证据不足，需整改后重新审核。"


def _worst_severity(items: Sequence[Verdict], rule: Rule) -> str:
    severities = [item.severity for item in items if item.severity in SEVERITY_ORDER] or [rule.severity]
    return min(severities, key=lambda value: SEVERITY_ORDER.get(value, 9))


def _json_payloads(answer: str) -> list[Any]:
    text = str(answer or "").strip()
    if not text:
        return []
    text = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
    candidates = [text]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])
    payloads: list[Any] = []
    for candidate in candidates:
        try:
            payloads.append(json.loads(candidate))
        except ValueError:
            continue
    return payloads


def _clean(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip().strip("`")
    return text


def _cell(value: str) -> str:
    return _clean(str(value or "")).replace("|", "／")


def _size_label(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size} B"


def _page_list(manifest: dict[str, Any]) -> str:
    pages = [str(item.get("page")) for item in manifest.get("pages") or [] if not item.get("text_layer")]
    return "、".join(pages) if pages else "无"
