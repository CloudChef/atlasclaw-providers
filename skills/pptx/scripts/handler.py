# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Executable PPTX skill handler."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from pptx import Presentation
from pptx.util import Inches, Pt


def _safe_filename(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in value.strip())
    cleaned = cleaned.strip("-") or "deck"
    if not cleaned.lower().endswith(".pptx"):
        cleaned = f"{cleaned}.pptx"
    return cleaned


def _resolve_output_dir(ctx: Any) -> Path:
    """Return the core-provided user work_dir for generated artifacts."""
    deps = getattr(ctx, "deps", None)
    extra = getattr(deps, "extra", None)
    work_dir = str((extra or {}).get("work_dir", "") if isinstance(extra, dict) else "").strip()
    if not work_dir:
        raise ValueError("AtlasClaw work_dir is required for PPTX output")
    output_dir = Path(work_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _coerce_items(items: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return normalized
    for item in items:
        if isinstance(item, dict):
            normalized.append(dict(item))
            continue
        if isinstance(item, str):
            text = " ".join(item.split()).strip()
            if text:
                normalized.append({"title": text})
    return normalized


def _build_deck(
    *,
    title: str,
    subtitle: str,
    items: list[dict[str, Any]],
    output_path: Path,
) -> dict[str, Any]:
    presentation = Presentation()

    title_slide = presentation.slides.add_slide(presentation.slide_layouts[0])
    title_slide.shapes.title.text = title
    subtitle_shape = title_slide.placeholders[1]
    subtitle_shape.text = subtitle or f"{len(items)} items"

    summary_slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    summary_slide.shapes.title.text = "Summary"
    summary_body = summary_slide.placeholders[1].text_frame
    summary_body.clear()
    for item in items:
        title_text = str(item.get("title") or item.get("name") or item.get("id") or "Item").strip()
        approver = str(item.get("approver") or item.get("currentApprover") or "").strip()
        paragraph = summary_body.add_paragraph()
        paragraph.text = f"{title_text}" + (f" | approver: {approver}" if approver else "")
        paragraph.level = 0

    for item in items:
        slide = presentation.slides.add_slide(presentation.slide_layouts[5])
        title_box = slide.shapes.add_textbox(Inches(0.6), Inches(0.4), Inches(8.8), Inches(0.6))
        title_frame = title_box.text_frame
        title_run = title_frame.paragraphs[0].add_run()
        title_run.text = str(item.get("title") or item.get("name") or item.get("id") or "Request")
        title_run.font.size = Pt(24)
        title_run.font.bold = True

        body_box = slide.shapes.add_textbox(Inches(0.8), Inches(1.3), Inches(8.4), Inches(3.8))
        body_frame = body_box.text_frame
        body_frame.word_wrap = True
        ordered_fields = [
            ("ID", item.get("id")),
            ("Approver", item.get("approver") or item.get("currentApprover")),
            ("Approval ID", item.get("approvalId")),
            ("Description", item.get("summary") or item.get("description")),
        ]
        first = True
        for label, value in ordered_fields:
            if value in (None, ""):
                continue
            paragraph = body_frame.paragraphs[0] if first else body_frame.add_paragraph()
            paragraph.text = f"{label}: {value}"
            paragraph.level = 0
            first = False

    presentation.save(str(output_path))
    return {
        "artifact_path": output_path.name,
        "file_path": output_path.name,
        "slide_count": len(presentation.slides),
        "item_count": len(items),
        "title": title,
    }


def create_deck_handler(
    ctx: Any,
    items: list[dict[str, Any]],
    title: str = "PPT Export",
    subtitle: str = "",
    output_filename: Optional[str] = None,
) -> dict[str, Any]:
    raw_items = items if isinstance(items, list) else []
    normalized_items = _coerce_items(raw_items)
    if not normalized_items:
        return {"success": False, "error": "items must contain at least one object"}

    output_dir = _resolve_output_dir(ctx)
    filename = _safe_filename(output_filename or "pending-approvals.pptx")
    result = _build_deck(
        title=str(title or "PPT Export"),
        subtitle=str(subtitle or ""),
        items=normalized_items,
        output_path=output_dir / filename,
    )
    result["success"] = True
    return result
