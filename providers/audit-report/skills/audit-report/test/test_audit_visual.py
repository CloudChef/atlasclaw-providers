# -*- coding: utf-8 -*-
"""Visual review pipeline: page grouping, rendering and response validation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pymupdf
import pytest

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import audit_visual  # noqa: E402


def _pdf(path: Path, page_count: int) -> None:
    with pymupdf.open() as pdf:
        for number in range(1, page_count + 1):
            page = pdf.new_page()
            page.insert_text((40, 60), f"Synthetic page {number}")
        pdf.save(path)


def _report(page_count: int) -> str:
    return "\n\n".join(
        f"## Page {number}\n\nSynthetic text for page {number}"
        for number in range(1, page_count + 1)
    )


@pytest.mark.asyncio
async def test_inspect_report_renders_each_page_and_validates_headings(tmp_path, monkeypatch):
    pdf_path = tmp_path / "synthetic.pdf"
    _pdf(pdf_path, 3)
    monkeypatch.setattr(audit_visual, "_build_visual_prompt", lambda *_args, **_kwargs: "visual prompt")

    async def submit(prompt: str, images: list[dict]) -> str:
        assert prompt == "visual prompt"
        assert all(image["data"].startswith(b"\x89PNG\r\n\x1a\n") for image in images)
        assert all(image["media_type"] == "image/png" for image in images)
        return "\n\n".join(f"### Page {image['page']}\nObservation {image['page']}." for image in images)

    reviews = await audit_visual.inspect_report(pdf_path, _report(3), submit, tmp_path)

    assert len(reviews) == 1
    assert reviews[0]["pages"] == [1, 2, 3]
    assert reviews[0]["context_pages"] == []
    manifest = json.loads((tmp_path / "visual.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete"
    assert manifest["render_dpi"] == audit_visual.RENDER_DPI
    assert all(page["status"] == "complete" for page in manifest["pages"])
    assert len(manifest["groups"][0]["images"]) == 3
    assert (tmp_path / "visual" / "001-raw.md").is_file()


@pytest.mark.asyncio
async def test_inspect_report_fails_when_response_misses_a_page(tmp_path, monkeypatch):
    pdf_path = tmp_path / "synthetic.pdf"
    _pdf(pdf_path, 2)
    monkeypatch.setattr(audit_visual, "_build_visual_prompt", lambda *_args, **_kwargs: "visual prompt")

    async def submit(_prompt: str, _images: list[dict]) -> str:
        return "### Page 1\nOnly one page"

    with pytest.raises(RuntimeError):
        await audit_visual.inspect_report(pdf_path, _report(2), submit, tmp_path)
    manifest = json.loads((tmp_path / "visual.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"


@pytest.mark.asyncio
async def test_visual_format_retry_carries_the_previous_observation(tmp_path, monkeypatch):
    pdf_path = tmp_path / "synthetic.pdf"
    _pdf(pdf_path, 2)
    monkeypatch.setattr(audit_visual, "_build_visual_prompt", lambda *_args, **_kwargs: "visual prompt")
    prompts: list[str] = []
    responses = [
        "### Page 1\nOriginal observed label and evidence.",
        "### Page 1\nOriginal observed label and evidence.\n\n### Page 2\nSecond page observation.",
    ]

    async def submit(prompt: str, _images: list[dict]) -> str:
        prompts.append(prompt)
        return responses.pop(0)

    await audit_visual.inspect_report(pdf_path, _report(2), submit, tmp_path)

    assert len(prompts) == 2
    assert "Original observed label and evidence." in prompts[1]
