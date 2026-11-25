# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.
"""Render PDF page evidence screenshots for audit findings.

The audit itself only reads the extracted text layer. After the verdicts are
merged, this module renders the cited page region for every finding so the HTML
report can show a real screenshot instead of only a text quote.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Sequence

import batch_audit

logger = logging.getLogger(__name__)

EVIDENCE_DPI = 150
FULL_PAGE_DPI = 110
MAX_EVIDENCE = 24
ABOVE = 70.0
BELOW = 170.0
MARGIN = 60.0


def render_evidence(
    document: dict[str, Any],
    doc_dir: Path,
    findings: Sequence[batch_audit.RuleResult],
) -> dict[str, str]:
    """Render one PNG per finding and return ``{rule_id: relative_path}``."""
    if str(document.get("extension") or "").lower() != ".pdf":
        return {}
    source = Path(str(document.get("file_path") or ""))
    if not source.is_file():
        return {}
    try:
        import pymupdf
    except ImportError:  # pragma: no cover - runtime always ships PyMuPDF
        logger.warning("PyMuPDF is unavailable; evidence screenshots are skipped")
        return {}

    evidence_dir = doc_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    images: dict[str, str] = {}
    with pymupdf.open(source) as pdf:
        for item in findings[:MAX_EVIDENCE]:
            page_no = _first_page(item)
            if page_no is None or not 1 <= page_no <= pdf.page_count:
                continue
            page = pdf[page_no - 1]
            name = f"F-{len(images) + 1:02d}_{item.rule.rule_id}.png"
            output = evidence_dir / name
            try:
                captured = _capture_page(page, item, output, pymupdf)
            except Exception as exc:  # noqa: BLE001 - evidence must not fail an audit
                logger.warning("Evidence capture failed for %s: %s", item.rule.rule_id, exc)
                continue
            if captured:
                images[item.rule.rule_id] = f"evidence/{name}"
    return images


def _capture_page(page: Any, item: batch_audit.RuleResult, output: Path, pymupdf: Any) -> bool:
    """Render the quote region of one page, falling back to the full page."""
    quote = item.evidence[0].quote if item.evidence else ""
    clip = None
    search = ""
    for candidate in _search_candidates(quote):
        try:
            hits = page.search_for(candidate)
        except Exception:  # noqa: BLE001 - malformed text must not stop the audit
            hits = []
        if not hits:
            continue
        hit = hits[0]
        clip = pymupdf.Rect(
            max(page.rect.x0, hit.x0 - MARGIN),
            max(page.rect.y0, hit.y0 - ABOVE),
            min(page.rect.x1, hit.x1 + MARGIN),
            min(page.rect.y1, hit.y1 + BELOW),
        )
        search = candidate
        break

    dpi = EVIDENCE_DPI if clip is not None else FULL_PAGE_DPI
    if clip is None:
        clip = page.rect
    pixmap = page.get_pixmap(clip=clip, dpi=dpi)
    pixmap.save(str(output))
    output.with_suffix(output.suffix + ".json").write_text(
        json.dumps(
            {
                "rule": item.rule.rule_id,
                "page": page.number + 1,
                "search": search,
                "dpi": dpi,
                "clip": [round(clip.x0, 2), round(clip.y0, 2), round(clip.x1, 2), round(clip.y1, 2)],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return output.is_file() and output.stat().st_size > 0


def _search_candidates(quote: str) -> list[str]:
    """Return progressively shorter search strings for the finding quote."""
    text = re.sub(r"\s+", " ", str(quote or "")).strip(" 「」『』\"'")
    if not text:
        return []
    candidates = [text[:40], text[:24], text[:14]]
    unique: list[str] = []
    for candidate in candidates:
        candidate = candidate.strip()
        if len(candidate) >= 4 and candidate not in unique:
            unique.append(candidate)
    return unique


def _first_page(item: batch_audit.RuleResult) -> int | None:
    """Parse the first page number cited by a finding."""
    for evidence in item.evidence:
        match = re.search(r"\d+", str(evidence.page or ""))
        if match:
            return int(match.group(0))
    return None
