#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assemble the directory, project-review, and global-summary LLM prompts."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
REFERENCE_DIR = SKILL_ROOT / "references"
RULES_DIR = SKILL_ROOT / "rules"
PROMPT_TEMPLATE_DIR = REFERENCE_DIR / "prompts"
REPORT_TEMPLATE_DIR = REFERENCE_DIR / "report"


def _render_template(directory: Path, name: str, values: dict[str, str]) -> str:
    template = (directory / name).read_text(encoding="utf-8").removesuffix("\n")
    placeholders = set(re.findall(r"\{\{([A-Z][A-Z0-9_]*)\}\}", template))
    if placeholders != set(values):
        missing = sorted(placeholders - set(values))
        unexpected = sorted(set(values) - placeholders)
        raise ValueError(f"Template {name} placeholders mismatch: missing={missing}, unexpected={unexpected}")
    return re.sub(r"\{\{([A-Z][A-Z0-9_]*)\}\}", lambda match: values[match.group(1)], template)


def render_prompt_template(name: str, **values: str) -> str:
    """Render a trusted UTF-8 prompt template with one-pass named substitutions.

    Template placeholders use ``{{NAME}}``. The supplied values are inserted as
    opaque text, so placeholder-looking content in source documents is not reprocessed.
    """
    return _render_template(PROMPT_TEMPLATE_DIR, name, values)


def render_report_template(name: str, **values: str) -> str:
    """Render a trusted UTF-8 legacy Markdown report template with opaque values."""
    return _render_template(REPORT_TEMPLATE_DIR, name, values)


def _rule_context(rules_dir: Path | None = None, ruleset: Any = None) -> tuple[str, str]:
    """Load the complete built-in and enabled rules without making audit decisions."""
    scripts = str(SCRIPT_DIR)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from _rules import load_rules

    ruleset = ruleset or load_rules(root=rules_dir)
    if not ruleset.rules:
        raise ValueError("The built-in rule JSON is empty")
    resolved_json = json.dumps(
        {
            "packs": [{key: pack[key] for key in ("pack", "version", "status")} for pack in ruleset.packs],
            "rules": list(ruleset.rules.values()),
        },
        ensure_ascii=False,
        indent=2,
    )
    builtin_json = Path(str(ruleset.packs[0].get("path", ""))) if ruleset.packs else None
    rules_markdown = builtin_json.with_name("rules.md") if builtin_json else None
    default_rule_json = RULES_DIR / "builtin" / "rules.json"
    reference_markdown = REFERENCE_DIR / "audit-rules.md"
    if rules_markdown is not None and rules_markdown.is_file():
        explanatory_rules = rules_markdown.read_text(encoding="utf-8")
    elif (builtin_json is None or builtin_json.resolve() == default_rule_json.resolve()) and reference_markdown.is_file():
        explanatory_rules = reference_markdown.read_text(encoding="utf-8")
    else:
        explanatory_rules = ""
    rule_bundle = render_prompt_template(
        "rule-bundle.md", RESOLVED_JSON=resolved_json, EXPLANATORY_RULES=explanatory_rules
    )
    return rule_bundle, explanatory_rules


def _rule_checklist(ruleset: Any) -> str:
    """Render every enabled rule ID and title from the active run snapshot."""
    lines = [(PROMPT_TEMPLATE_DIR / "rule-checklist-header.md").read_text(encoding="utf-8").strip()]
    lines.extend(render_prompt_template(
        "rule-checklist-row.md", RULE_ID=rule_id,
        TITLE=str(rule.get("title", rule.get("name", "规则"))).replace("|", "&#124;"),
        STAGE="全局" if rule.get("stage") == "global" else "项目",
    ) for rule_id, rule in ruleset.rules.items())
    return "\n".join(lines)


def _system_text() -> str:
    return (REFERENCE_DIR / "audit-system.md").read_text(encoding="utf-8")


def _materials_text(materials: list[dict]) -> str:
    """Serialize every supplied material body and provenance without truncation."""
    sections: list[str] = []
    for index, material in enumerate(materials, start=1):
        reference_id = str(material.get("reference_id") or f"M{index:02d}")
        sections.append(render_prompt_template(
            "material.md", REFERENCE_ID=reference_id, FILENAME=material["filename"],
            KIND=material["kind"], SHA256=material.get("sha256", "未提供"),
            CONTENT=material["content"],
        ))
    return "\n\n---\n\n".join(sections) if sections else render_prompt_template("no-materials.md")


def _current_material_manifest(materials: list[dict]) -> list[dict]:
    """Return only file identity metadata, never parsed material bodies."""
    return [
        {
            "reference_id": str(item.get("reference_id") or f"M{index:02d}"),
            "filename": item["filename"],
            "kind": item["kind"],
            "sha256": item.get("sha256", "未提供"),
        }
        for index, item in enumerate(materials, start=1)
    ]


def _text_evidence_contract() -> str:
    return (REFERENCE_DIR / "audit-text-evidence.md").read_text(encoding="utf-8")


def build_index_prompt(report_text: str, page_count: int, *, rules_dir: Path | None = None,
                       ruleset: Any = None) -> str:
    """Build a JSON-only prompt for project identification from native text."""
    rules, _ = _rule_context(rules_dir, ruleset)
    index_contract = (REFERENCE_DIR / "audit-project-index.md").read_text(encoding="utf-8")
    return render_prompt_template("index.md", SYSTEM=_system_text(), TEXT_EVIDENCE=_text_evidence_contract(),
                                  INDEX_CONTRACT=index_contract, PAGE_COUNT=str(page_count), RULES=rules,
                                  REPORT_TEXT=report_text)


def build_index_chunk_prompt(
    page_text: dict[int, str],
    formal_pages: list[int],
    context_pages: list[int],
    page_count: int,
    chunk_index: int,
    chunk_count: int,
    *,
    previous_scan_raw: str | None = None,
) -> str:
    """Build a bounded text-only chunk scan prompt without full rules or materials."""
    contract = (REFERENCE_DIR / "audit-project-index-chunk.md").read_text(encoding="utf-8")
    formal_text = "\n\n".join(page_text[page] for page in formal_pages)
    context_text = "\n\n".join(
        f"### {'前一页' if page < formal_pages[0] else '后一页'}（仅上下文）\n{page_text[page]}"
        for page in context_pages
    )
    return render_prompt_template("chunk.md", SYSTEM=_system_text(), TEXT_EVIDENCE=_text_evidence_contract(),
        CHUNK_CONTRACT=contract, PAGE_COUNT=str(page_count), CHUNK_INDEX=str(chunk_index), CHUNK_COUNT=str(chunk_count),
        FORMAL_PAGE_NUMBERS=json.dumps(formal_pages), CONTEXT_PAGE_NUMBERS=json.dumps(context_pages),
        CONTEXT_TEXT=context_text, PREVIOUS_SCAN_RAW=previous_scan_raw or "（首段，无前段扫描）", FORMAL_TEXT=formal_text)


def build_index_merge_prompt(scans: list[dict], page_count: int) -> str:
    """Build a compact text-directory merge request from validated chunk scans."""
    contract = (REFERENCE_DIR / "audit-project-index-merge.md").read_text(encoding="utf-8")
    return render_prompt_template("merge.md", SYSTEM=_system_text(), TEXT_EVIDENCE=_text_evidence_contract(),
        MERGE_CONTRACT=contract, PAGE_COUNT=str(page_count), SCANS=json.dumps(scans, ensure_ascii=False, indent=2))


def build_project_prompt(
    project: dict,
    project_text: str,
    frontmatter: str,
    materials: list[dict],
    project_index: int,
    *,
    rules_dir: Path | None = None,
    ruleset: Any = None,
) -> str:
    """Build a complete text-only per-project review prompt with all source materials."""
    active_rules = ruleset or _load_rules(rules_dir)
    rules, _ = _rule_context(rules_dir, active_rules)
    project_contract = (REFERENCE_DIR / "audit-project-review.md").read_text(encoding="utf-8")
    materials_contract = (REFERENCE_DIR / "uploaded-materials-audit.md").read_text(encoding="utf-8")
    text_evidence_contract = _text_evidence_contract()
    project_id = str(project["id"])
    title = str(project["title"])
    page_start = int(project["page_start"])
    page_end = int(project["page_end"])
    material_manifest = _current_material_manifest(materials)
    return render_prompt_template("project.md", SYSTEM=_system_text(), PROJECT_ID=project_id,
        TITLE=title, PAGE_START=str(page_start), PAGE_END=str(page_end), PROJECT_INDEX=f"{project_index:03d}",
        RULES=rules, RULE_CHECKLIST=_rule_checklist(active_rules), MATERIALS=_materials_text(materials), FRONTMATTER=frontmatter,
        PROJECT_TEXT=project_text, TEXT_EVIDENCE=text_evidence_contract,
        PROJECT_CONTRACT=project_contract, MATERIALS_CONTRACT=materials_contract,
        MATERIAL_MANIFEST=json.dumps(material_manifest, ensure_ascii=False, indent=2))


def build_visual_prompt(
    page_text: str,
    pages: list[int],
    context_pages: list[int],
    *,
    page_count: int = 0,
    rules_dir: Path | None = None,
) -> str:
    """Build a page-image visual review prompt for the image-capable model."""
    from _rules import load_rules

    ruleset = load_rules(root=rules_dir)
    visual_rules = [
        rule for rule in ruleset.rules.values()
        if (rule.get("check") or {}).get("type") == "visual" or "image" in (rule.get("requires") or [])
    ]
    if not visual_rules:
        raise ValueError("No visual rules are enabled")
    resolved = json.dumps(
        {
            "packs": [{key: pack[key] for key in ("pack", "version", "status")} for pack in ruleset.packs],
            "rules": visual_rules,
        },
        ensure_ascii=False,
        indent=2,
    )
    contract = (REFERENCE_DIR / "audit-visual-review.md").read_text(encoding="utf-8")
    return render_prompt_template(
        "visual.md",
        SYSTEM=_system_text(),
        PAGES=json.dumps(pages),
        CONTEXT_PAGES=json.dumps(context_pages),
        PAGE_COUNT=str(page_count or max(pages or [0])),
        RULES=resolved,
        PAGE_TEXT=page_text,
        VISUAL_CONTRACT=contract,
    )


def build_visual_retry_prompt(base_prompt: str, format_error: str, previous_response: str = "") -> str:
    """Append the reference-backed correction request after a visual format error."""
    retry = render_prompt_template(
        "visual-repair.md", FORMAT_ERROR=format_error, PREVIOUS_RESPONSE=previous_response,
    )
    return f"{base_prompt}\n\n{retry}"


def build_summary_prompt(
    report_text: str,
    materials: list[dict],
    page_count: int,
    reviews: list[dict],
    *,
    rules_dir: Path | None = None,
    ruleset: Any = None,
) -> str:
    """Build a text-only global review prompt with complete source and project responses."""
    active_rules = ruleset or _load_rules(rules_dir)
    rules, _ = _rule_context(rules_dir, active_rules)
    summary_contract = (REFERENCE_DIR / "audit-project-summary.md").read_text(encoding="utf-8")
    materials_contract = (REFERENCE_DIR / "uploaded-materials-audit.md").read_text(encoding="utf-8")
    template = (REFERENCE_DIR / "report-template.md").read_text(encoding="utf-8")
    text_evidence_contract = _text_evidence_contract()
    runtime_timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    review_sections = [
        render_prompt_template("review.md", INDEX=str(index), PROJECT_ID=str(review["project_id"]),
                               PROJECT_INDEX=str(review["project_index"]), MARKDOWN=review["markdown"])
        for index, review in enumerate(reviews, start=1)
    ]
    accepted_finding_index = [
        {
            "project_id": review["project_id"],
            "project_index": review["project_index"],
            "finding_ids_from_headings": re.findall(
                r"(?m)^#{3,6}\s+.*?\b(F-(?:\d+-\d+|\d{2,}))\b", review["markdown"]
            ),
        }
        for review in reviews
    ]
    return render_prompt_template("summary.md", SYSTEM=_system_text(), PAGE_COUNT=str(page_count),
        RUNTIME_TIMESTAMP=render_prompt_template("runtime_timestamp.md", TIMESTAMP=runtime_timestamp),
        RULES=rules, RULE_CHECKLIST=_rule_checklist(active_rules), REPORT_TEMPLATE=template, REPORT_TEXT=report_text, MATERIALS=_materials_text(materials),
        REVIEWS="\n\n---\n\n".join(review_sections) if review_sections else render_prompt_template("no-reviews.md"),
        TEXT_EVIDENCE=text_evidence_contract, SUMMARY_CONTRACT=summary_contract,
        MATERIALS_CONTRACT=materials_contract,
        MATERIAL_MANIFEST=json.dumps(_current_material_manifest(materials), ensure_ascii=False, indent=2),
        FINDING_INDEX=json.dumps(accepted_finding_index, ensure_ascii=False, indent=2))


def _load_rules(rules_dir: Path | None) -> Any:
    from _rules import load_rules
    return load_rules(root=rules_dir)
