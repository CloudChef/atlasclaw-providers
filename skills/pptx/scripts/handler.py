# -*- coding: utf-8 -*-
"""Executable PPTX skill handler."""

from __future__ import annotations

import json
import re
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
    deps = getattr(ctx, "deps", None)
    session_manager = getattr(deps, "session_manager", None)
    workspace_path = Path(getattr(session_manager, "workspace_path", ".")).resolve()
    user_info = getattr(deps, "user_info", None)
    user_id = str(getattr(user_info, "user_id", "") or "default")
    output_dir = workspace_path / "users" / user_id / "exports"
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


def _coerce_tool_payload_to_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        for key in ("output", "text", "summary", "message"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _extract_meta_payload(text: str, marker_name: str) -> list[dict[str, Any]]:
    if not text:
        return []
    pattern = (
        rf"##{re.escape(marker_name)}_START##\s*(?P<payload>.*?)\s*##{re.escape(marker_name)}_END##"
    )
    match = re.search(pattern, text, flags=re.DOTALL)
    if not match:
        return []
    raw_payload = str(match.group("payload") or "").strip()
    if not raw_payload:
        return []
    try:
        parsed = json.loads(raw_payload)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in parsed:
        if isinstance(item, dict):
            normalized.append(dict(item))
    return normalized


def _resolve_transcript_path(session_manager: Any, session_key: str) -> Optional[Path]:
    if session_manager is None or not session_key:
        return None
    metadata_cache = getattr(session_manager, "_metadata_cache", None)
    session = metadata_cache.get(session_key) if isinstance(metadata_cache, dict) else None
    if session is None:
        return None
    get_transcript_path = getattr(session_manager, "_get_transcript_path", None)
    if not callable(get_transcript_path):
        return None
    try:
        transcript_path = get_transcript_path(session)
    except Exception:
        return None
    return transcript_path if isinstance(transcript_path, Path) else Path(str(transcript_path))


def _recover_pending_items_from_transcript(ctx: Any) -> list[dict[str, Any]]:
    deps = getattr(ctx, "deps", None)
    session_manager = getattr(deps, "session_manager", None)
    session_key = str(getattr(deps, "session_key", "") or "").strip()
    transcript_path = _resolve_transcript_path(session_manager, session_key)
    if transcript_path is None or not transcript_path.is_file():
        return []

    try:
        lines = transcript_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []

    for raw_line in reversed(lines):
        line = str(raw_line or "").strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if str(entry.get("role", "") or "").strip().lower() != "tool":
            continue
        if str(entry.get("tool_name", "") or "").strip() != "smartcmp_list_pending":
            continue
        payload_text = _coerce_tool_payload_to_text(entry.get("content"))
        recovered = _extract_meta_payload(payload_text, "APPROVAL_META")
        if recovered:
            return recovered
    return []


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
        "file_path": str(output_path),
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
    raw_items_include_dict = any(isinstance(item, dict) for item in raw_items)
    if not raw_items_include_dict:
        recovered_items = _recover_pending_items_from_transcript(ctx)
        if recovered_items:
            normalized_items = recovered_items
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


def handler(
    ctx: Any,
    items: list[dict[str, Any]],
    title: str = "PPT Export",
    subtitle: str = "",
    output_filename: Optional[str] = None,
) -> dict[str, Any]:
    """Backward-compatible alias for direct script execution tests."""
    return create_deck_handler(
        ctx=ctx,
        items=items,
        title=title,
        subtitle=subtitle,
        output_filename=output_filename,
    )
