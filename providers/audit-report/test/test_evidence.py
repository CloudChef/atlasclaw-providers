# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.
"""Evidence screenshots: page rendering and embedding in the report Markdown."""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

import batch_audit  # noqa: E402
import evidence  # noqa: E402


def _pdf(path: Path, text: str) -> Path:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 120), text, fontname="china-s", fontsize=14)
    document.save(str(path))
    document.close()
    return path


def _finding(quote: str = "签发日期：", page: str = "1") -> batch_audit.RuleResult:
    rule = batch_audit.Rule("R02", "三方签章", "A", "", module_name="文件合规", pack="builtin")
    verdict = batch_audit.Verdict("R02", "FAIL", "A", page=page, quote=quote, problem="签署不齐全", suggestion="补齐签名")
    return batch_audit.RuleResult(rule, "FAIL", "A", [verdict])


def test_evidence_is_rendered_and_embedded(tmp_path: Path) -> None:
    pdf = _pdf(tmp_path / "report.pdf", "签发日期：2026-11-24")

    images = evidence.render_evidence(
        {"extension": ".pdf", "file_path": str(pdf)}, tmp_path, [_finding()],
    )

    assert images == {"R02": "evidence/F-01_R02.png"}
    assert (tmp_path / "evidence" / "F-01_R02.png").stat().st_size > 0
    markdown = batch_audit.build_markdown(
        document={"file_name": "report.pdf", "extension": ".pdf", "size": 1024, "pages": 1},
        results=[_finding()],
        manifest={"page_count": 1, "has_text_layer": True, "pages": []},
        started_at=batch_audit.datetime.now().astimezone(),
        finished_at=batch_audit.datetime.now().astimezone(),
        evidence=images,
    )
    assert "![F-01 证据：第 1 页" in markdown
    assert "evidence/F-01_R02.png" in markdown
    assert "未提供可渲染的页面图片" not in markdown


def test_missing_quote_falls_back_to_full_page(tmp_path: Path) -> None:
    pdf = _pdf(tmp_path / "report.pdf", "普通页面内容")

    images = evidence.render_evidence(
        {"extension": ".pdf", "file_path": str(pdf)}, tmp_path, [_finding(quote="不存在的文字")],
    )

    assert images == {"R02": "evidence/F-01_R02.png"}
    meta = (tmp_path / "evidence" / "F-01_R02.png.json").read_text(encoding="utf-8")
    assert '"search": ""' in meta


def test_evidence_renders_all_findings_beyond_old_cap(tmp_path: Path) -> None:
    source = pymupdf.open()
    findings = []
    for page_no in range(1, 31):
        page = source.new_page()
        page.insert_text((72, 120), f"Page {page_no}", fontname="helv")
        rule_id = f"X{page_no:02d}"
        rule = batch_audit.Rule(rule_id, f"Issue {page_no}", "B", "")
        verdict = batch_audit.Verdict(rule_id, "FAIL", "B", page=str(page_no), quote="missing quote")
        findings.append(batch_audit.RuleResult(rule, "FAIL", "B", [verdict]))
    pdf_path = tmp_path / "many-findings.pdf"
    source.save(pdf_path)
    source.close()

    images = evidence.render_evidence(
        {"extension": ".pdf", "file_path": str(pdf_path)}, tmp_path, findings,
    )

    assert len(images) == len(findings) == 30
    assert images["X30"] == "evidence/F-30_X30.png"
    assert (tmp_path / images["X30"]).stat().st_size > 0


def test_non_pdf_documents_skip_evidence(tmp_path: Path) -> None:
    assert evidence.render_evidence({"extension": ".docx", "file_path": "x.docx"}, tmp_path, [_finding()]) == {}


@pytest.mark.parametrize("quote", ["", "短"])
def test_unusable_quotes_do_not_crash(tmp_path: Path, quote: str) -> None:
    pdf = _pdf(tmp_path / "report.pdf", "任意内容")

    images = evidence.render_evidence(
        {"extension": ".pdf", "file_path": str(pdf)}, tmp_path, [_finding(quote=quote)],
    )

    assert images == {"R02": "evidence/F-01_R02.png"}
