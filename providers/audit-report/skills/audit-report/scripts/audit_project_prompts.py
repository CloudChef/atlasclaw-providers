#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assemble the directory, project-review, and global-summary LLM prompts."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path


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


def _rule_context(rules_dir: Path | None = None) -> tuple[str, str]:
    """Load the full built-in and enabled rules without making audit decisions."""
    scripts = str(SCRIPT_DIR)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from _rules import load_rules

    ruleset = load_rules(root=rules_dir)
    builtin_ids = {f"R{number:02d}" for number in range(1, 20)}
    if not builtin_ids.issubset(ruleset.rules) or any(
        pack["version"] == "0.0.0-fallback" for pack in ruleset.packs
    ):
        raise ValueError("The complete built-in R01-R19 JSON rule pack is required")
    resolved_json = json.dumps(
        {
            "packs": [{key: pack[key] for key in ("pack", "version", "status")} for pack in ruleset.packs],
            "rules": list(ruleset.rules.values()),
        },
        ensure_ascii=False,
        indent=2,
    )
    explanatory_rules = (REFERENCE_DIR / "audit-rules.md").read_text(encoding="utf-8")
    rule_bundle = render_prompt_template(
        "rule-bundle.md", RESOLVED_JSON=resolved_json, EXPLANATORY_RULES=explanatory_rules
    )
    return rule_bundle, explanatory_rules


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


def build_index_prompt(report_text: str, page_count: int) -> str:
    """Build a JSON-only prompt for project identification from native text."""
    rules, _ = _rule_context()
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
) -> str:
    """Build a complete text-only per-project review prompt with all source materials."""
    rules, _ = _rule_context(rules_dir)
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
        RULES=rules, MATERIALS=_materials_text(materials), FRONTMATTER=frontmatter,
        PROJECT_TEXT=project_text, TEXT_EVIDENCE=text_evidence_contract,
        PROJECT_CONTRACT=project_contract, MATERIALS_CONTRACT=materials_contract,
        MATERIAL_MANIFEST=json.dumps(material_manifest, ensure_ascii=False, indent=2))


def build_summary_prompt(
    report_text: str,
    materials: list[dict],
    page_count: int,
    reviews: list[dict],
    *,
    rules_dir: Path | None = None,
) -> str:
    """Build a text-only global review prompt with complete source and project responses."""
    rules, _ = _rule_context(rules_dir)
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
        RULES=rules, REPORT_TEMPLATE=template, REPORT_TEXT=report_text, MATERIALS=_materials_text(materials),
        REVIEWS="\n\n---\n\n".join(review_sections) if review_sections else render_prompt_template("no-reviews.md"),
        TEXT_EVIDENCE=text_evidence_contract, SUMMARY_CONTRACT=summary_contract,
        MATERIALS_CONTRACT=materials_contract,
        MATERIAL_MANIFEST=json.dumps(_current_material_manifest(materials), ensure_ascii=False, indent=2),
        FINDING_INDEX=json.dumps(accepted_finding_index, ensure_ascii=False, indent=2))
