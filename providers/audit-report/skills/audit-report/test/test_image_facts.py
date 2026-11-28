# -*- coding: utf-8 -*-
"""Deterministic image facts used as evidence for R30/R32."""
from __future__ import annotations

import base64
import sys
from pathlib import Path

import pymupdf

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import image_facts  # noqa: E402

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/"
    "pL8AAAAASUVORK5CYII="
)


def test_scan_pdf_keeps_frequent_repeats_in_visual_review_candidates(tmp_path):
    pdf_path = tmp_path / "images.pdf"
    with pymupdf.open() as pdf:
        for page_number in range(1, 5):
            page = pdf.new_page()
            page.insert_image(pymupdf.Rect(20, 20, 120, 120), stream=PNG)
            if page_number in (1, 2):
                page.insert_image(pymupdf.Rect(150, 20, 250, 120), stream=PNG)
        pdf.save(pdf_path)

    facts = image_facts.scan_pdf(pdf_path)

    assert facts["page_count"] == 4
    assert facts["image_count"] == 6
    assert len(facts["exact_duplicates"]) == 1
    assert facts["exact_duplicates"][0]["count"] == 6
    markdown = image_facts.to_markdown(facts)
    assert "页眉/logo" in markdown
    assert "仍需结合页面内容判断" in markdown
    assert "仅候选" in markdown


def test_to_markdown_lists_every_ratio_outlier():
    facts = {
        "pdf": "report.pdf",
        "page_count": 55,
        "image_count": 55,
        "ratio_median": 1.0,
        "exact_duplicates": [],
        "ratio_outliers": [
            {"page": page, "width": page * 10, "height": 10, "ratio": float(page)}
            for page in range(1, 56)
        ],
    }

    markdown = image_facts.to_markdown(facts)

    assert "第 55 页" in markdown
    assert markdown.count("- 第 ") == 55
