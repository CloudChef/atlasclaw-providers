# -*- coding: utf-8 -*-
"""Create local evidence screenshots and a downloadable PDF from audit Markdown."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from string import Template
from pathlib import Path
from typing import Any

import pymupdf

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from render_report import load_template


FINDING_ID_PATTERN = r"F-(?:\d+-\d+|\d{2,})"
FINDING_RE = re.compile(rf"^###\s+({FINDING_ID_PATTERN})\b.*$", re.M)
PAGE_RE = re.compile(r"^-\s+\*\*页码\*\*[：:]\s*(.+)$", re.M)
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
PAGE_RANGE_RE = re.compile(r"第\s*([\d\s,，;；、\-–—~～至到]+?)\s*页")
PAGE_SPEC_RE = re.compile(r"^\s*\d+(?:\s*(?:[,，;；、]\s*\d+|[-–—~～至到]\s*\d+))*\s*(?:页)?\s*$")
PAGE_PART_RE = re.compile(r"(\d+)\s*(?:([-–—~～至到])\s*(\d+))?")
CONTINUATION_RE = re.compile(r"续表|跨页|续页")
SAFE_EVIDENCE_RE = re.compile(r"F-(?:\d+-\d+|\d{2,})(?:-p[1-9]\d*)?\.png")
CONTEXT_FIELD_START_RE = re.compile(r"(?m)^\s*-\s+\*\*原文上下文\*\*(?:[ \t]*[（(][^）)\n]*[）)])?[ \t]*[：:][ \t]*(.*)$")
FENCE_LINE_RE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
OUTER_CONTEXT_METADATA_RE = re.compile(
    r"^\s*-\s+\*\*(?:页码|规则号|等级|位置|判定依据|不规范说明|违反要求|影响|整改建议|关联问题|证据截图|证据)\*\*[：:]"
)
FINDING_REFERENCE_RE = re.compile(
    rf"(?:同|见)\s*`?({FINDING_ID_PATTERN})(?![A-Za-z0-9-])"
)


def _font_file() -> Path | None:
    candidates: list[Path] = []
    if os.name == "nt":
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        candidates.extend([windir / "Fonts" / "msyh.ttc", windir / "Fonts" / "simsun.ttc"])
    candidates.extend([
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
    ])
    return next((path for path in candidates if path.is_file()), None)


def _page_intervals(page_text: str) -> list[tuple[int, int]]:
    """Parse explicitly listed page numbers and inclusive page ranges."""
    specs = [match.group(1) for match in PAGE_RANGE_RE.finditer(page_text)]
    if not specs and PAGE_SPEC_RE.fullmatch(page_text):
        specs = [re.sub(r"\s*页\s*$", "", page_text.strip())]
    intervals: list[tuple[int, int]] = []
    for spec in specs:
        normalized = re.sub(r"[,，;；、]", ",", spec)
        parts = [part.strip() for part in normalized.split(",") if part.strip()]
        consumed = ",".join(parts)
        if not parts or not re.fullmatch(r"[\d\s,\-–—~～至到]+", consumed):
            continue
        for part in parts:
            match = PAGE_PART_RE.fullmatch(part)
            if not match:
                continue
            first = int(match.group(1))
            last = int(match.group(3) or first)
            intervals.append((first, last))
    return intervals


def _clean_context_line(line: str) -> tuple[str, bool]:
    """Strip a context label and return the text plus its problem-line marker."""
    text = re.sub(r"^\s*(?:>\s*)+", "", line).strip()
    text = re.sub(r"^[-*+][ \t]+", "", text).strip()
    text = re.sub(r"^\*\*(.*?)\*\*\s*", r"\1", text)
    text = re.sub(r"^第\s*\d+\s*页[：:]\s*", "", text)
    label = re.match(r"^(问题处|前文|后文|原文)[：:]\s*(.*)$", text)
    if label:
        return label.group(2).strip(), label.group(1) == "问题处"
    return text, False


def _context_source_lines(block: str) -> list[str]:
    """Read context lines until a known outer finding field, respecting code fences."""
    field = CONTEXT_FIELD_START_RE.search(block)
    if not field:
        return []
    source_lines = [field.group(1), *block[field.end():].splitlines()]
    lines: list[str] = []
    fence: tuple[str, int] | None = None
    for index, line in enumerate(source_lines):
        match = FENCE_LINE_RE.match(line)
        if match:
            marker, suffix = match.groups()
            marker_char = marker[0]
            marker_size = len(marker)
            if fence is None:
                fence = (marker_char, marker_size)
                continue
            if marker_char == fence[0] and marker_size >= fence[1] and not suffix.strip():
                fence = None
                continue
        if fence is None and index > 0 and OUTER_CONTEXT_METADATA_RE.match(line):
            break
        lines.append(line.strip())
    return [line for line in lines if line]


def _finding_context_data(block: str) -> tuple[list[tuple[int, int]], str | None]:
    """Extract cited page intervals and a literal quote from common Markdown forms."""
    page_field = PAGE_RE.search(block)
    intervals = _page_intervals(page_field.group(1)) if page_field else []
    quote: str | None = None
    lines = _context_source_lines(block)
    if lines:
        contexts = [_clean_context_line(line) for line in lines]
        context = next((text for text, is_problem in contexts if is_problem and text), None)
        if context is None:
            context = next((text for text, _ in contexts if text), None)
        if context:
            context = re.sub(r"\*\*|`", "", context).strip()
            context = re.sub(r"^[「『\"']+|[」』\"']+$", "", context).strip()
            if not re.match(
                rf"^(?:同|见)\s*`?{FINDING_ID_PATTERN}(?![A-Za-z0-9-])", context
            ):
                quote = context or None
    return intervals, quote


def _finding_context(block: str) -> tuple[int | None, str | None]:
    """Compatibility view of the first cited page and extracted context quote."""
    intervals, quote = _finding_context_data(block)
    return (intervals[0][0] if intervals else None, quote)


def _technical_note(block: str, message: str) -> str:
    note = f"> 本地证据处理错误：{message}。模型审核结论保持原样。"
    if "本地证据处理错误：" in block:
        return re.sub(r"^> 本地证据处理错误：.*$", note, block, flags=re.M)
    image_line = re.search(r"^!\[[^\]]*\]\([^)]+\)\s*$", block, re.M)
    if image_line:
        return block[:image_line.start()] + note + "\n" + block[image_line.end():]
    return block.rstrip() + "\n\n" + note + "\n"


def _safe_image_refs(markdown: str, report_dir: Path) -> str:
    def replace(match: re.Match[str]) -> str:
        raw = match.group(2).strip()
        path = Path(raw)
        if path.is_absolute() or path.parts[:1] != ("evidence",) or len(path.parts) != 2:
            return "> 本地证据处理错误：忽略不安全的本地图片引用。模型审核结论保持原样。"
        if not SAFE_EVIDENCE_RE.fullmatch(path.name):
            return "> 本地证据处理错误：忽略格式不受支持的图片引用。模型审核结论保持原样。"
        target = (report_dir / "evidence" / path.name).resolve()
        if target.parent != (report_dir / "evidence").resolve():
            return "> 本地证据处理错误：忽略越界图片引用。模型审核结论保持原样。"
        return match.group(0)
    return IMAGE_RE.sub(replace, markdown)


def _missing_local_evidence_refs(markdown: str, report_dir: Path) -> list[str]:
    """Return missing files referenced through the accepted local evidence path."""
    evidence_root = (report_dir / "evidence").resolve()
    missing: list[str] = []
    for match in IMAGE_RE.finditer(markdown):
        raw = match.group(2).strip()
        relative = Path(raw)
        if (relative.is_absolute() or relative.parts[:1] != ("evidence",)
                or len(relative.parts) != 2 or not SAFE_EVIDENCE_RE.fullmatch(relative.name)):
            continue
        target = (report_dir / relative).resolve()
        if target.parent != evidence_root or not target.is_file() or target.stat().st_size <= 0:
            missing.append(f"缺少本地证据图片：{relative.as_posix()}")
    return missing


def _mark_pdf_object_table(html: str) -> str:
    """Give the source metadata table a readable PDF-only column split."""
    table_re = re.compile(r"(<table\b[^>]*>)(.*?</table>)", re.I | re.S)

    def mark(match: re.Match[str]) -> str:
        opening, body = match.groups()
        if not (
            re.search(r"<th\b[^>]*>\s*项目\s*</th>", body, re.I | re.S)
            and re.search(r"<th\b[^>]*>\s*内容\s*</th>", body, re.I | re.S)
            and "SHA-256" in body
        ):
            return match.group(0)
        class_match = re.search(r'\bclass\s*=\s*(["\'])(.*?)\1', opening, re.I | re.S)
        if class_match:
            classes = class_match.group(2).split()
            if "audit-object-table" not in classes:
                classes.append("audit-object-table")
                opening = opening[:class_match.start(2)] + " ".join(classes) + opening[class_match.end(2):]
        else:
            opening = opening[:-1] + ' class="audit-object-table">'
        sha_row_re = re.compile(r"<tr\b[^>]*>.*?SHA-256.*?</tr>", re.I | re.S)

        def split_hash(row_match: re.Match[str]) -> str:
            row = row_match.group(0)
            return re.sub(
                r"(<code\b[^>]*>)([0-9a-fA-F]{32})([0-9a-fA-F]{32})(</code>)",
                r"\1\2<br>\3\4",
                row,
                count=1,
            )

        body = sha_row_re.sub(split_hash, body, count=1)
        return opening + body

    return table_re.sub(mark, html)


def _render_pdf(html_path: Path, output_pdf: Path) -> None:
    font = _font_file()
    font_css = (
        f"@font-face {{font-family: AuditCJK; src: url('{font.as_posix()}');}} body {{font-family: AuditCJK;}}"
        if font else "body {font-family: china-s;}"
    )
    css = _pdf_css(font_css)
    # The HTML keeps its color styling; PDF-only layout rules prevent Story's
    # repeated backgrounds and intrinsic table widths from clipping report text.
    html = _mark_pdf_object_table(html_path.read_text(encoding="utf-8"))
    html = re.sub(r"<footer\b[^>]*>.*?</footer>", "", html, flags=re.I | re.S)
    story = pymupdf.Story(html=html, user_css=css)
    page = pymupdf.Rect(0, 0, 595.28, 841.89)
    content = pymupdf.Rect(42, 42, 553.28, 799.89)
    writer = pymupdf.DocumentWriter(str(output_pdf))
    try:
        more = True
        while more:
            device = writer.begin_page(page)
            more, _ = story.place(content)
            story.draw(device)
            writer.end_page()
    finally:
        writer.close()
    document = pymupdf.open(output_pdf)
    for number, page_obj in enumerate(document, 1):
        page_obj.insert_text((page_obj.rect.width - 58, page_obj.rect.height - 14),
                             f"{number} / {document.page_count}", fontname="helv", fontsize=8,
                             color=(0.35, 0.38, 0.42))
    document.saveIncr()
    document.close()


def _pdf_css(font_css: str) -> str:
    """Render the trusted PDF stylesheet, failing on missing substitutions."""
    return Template(load_template("pdf.css")).substitute(font_css=font_css)


def _subset_and_validate_pdf(path: Path) -> None:
    """Subset embedded fonts and verify text, page count, and images survive."""
    optimized = path.with_name(path.stem + ".subset.pdf")
    with pymupdf.open(path) as source_doc:
        page_count = source_doc.page_count
        texts = [page.get_text() for page in source_doc]
        image_count = sum(len(page.get_images(full=True)) for page in source_doc)
        source_doc.subset_fonts()
        source_doc.save(optimized, garbage=4, deflate=True)
    try:
        with pymupdf.open(optimized) as check:
            if check.page_count != page_count or [page.get_text() for page in check] != texts:
                raise RuntimeError("字体优化后页面或文本内容发生变化")
            if sum(len(page.get_images(full=True)) for page in check) != image_count:
                raise RuntimeError("字体优化后图片数量发生变化")
    except Exception:
        optimized.unlink(missing_ok=True)
        raise
    optimized.replace(path)


def deliver_report(markdown_path: str | Path, desensitized_pdf: str | Path, output_pdf: str | Path) -> dict[str, Any]:
    """Generate screenshots, enriched Markdown, HTML, and a Chinese-capable PDF locally.

    Args:
        markdown_path: Path to the untouched Markdown returned by the model.
        desensitized_pdf: PDF used for evidence capture.
        output_pdf: Destination PDF path; sibling `.enriched.md` and `.html` files are created.

    Returns:
        Metadata containing artifact paths, per-finding capture status, and technical errors.
    """
    source = Path(markdown_path).resolve()
    source_pdf = Path(desensitized_pdf).resolve()
    pdf_path = Path(output_pdf).resolve()
    report_dir = pdf_path.parent
    report_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = report_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    enriched_path = pdf_path.with_name(pdf_path.stem + ".enriched.md")
    html_path = pdf_path.with_suffix(".html")
    original = source.read_text(encoding="utf-8")
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    from audit_workflow import _normalize_finding_markdown
    markdown = _safe_image_refs(_normalize_finding_markdown(original), report_dir)
    findings: list[dict[str, Any]] = []
    errors: list[str] = []
    matches = list(FINDING_RE.finditer(markdown))
    finding_ids = [match.group(1) for match in matches]
    if len(finding_ids) != len(set(finding_ids)):
        raise ValueError("Duplicate finding identifiers would overwrite evidence screenshots")
    blocks = {match.group(1): markdown[match.start():matches[i + 1].start() if i + 1 < len(matches) else len(markdown)]
              for i, match in enumerate(matches)}

    def resolve_context(
        finding_id: str, visited: set[str]
    ) -> tuple[list[tuple[int, int]], str | None]:
        if finding_id in visited or finding_id not in blocks:
            return [], None
        visited = visited | {finding_id}
        block = blocks[finding_id]
        page_intervals, quote = _finding_context_data(block)
        page_field = PAGE_RE.search(block)
        if page_field and not page_intervals:
            reference = FINDING_REFERENCE_RE.search(page_field.group(1))
            if reference:
                page_intervals, _ = resolve_context(reference.group(1), visited)
        if quote is None:
            context_text = "\n".join(_context_source_lines(block))
            reference = FINDING_REFERENCE_RE.search(context_text)
            if reference:
                _, quote = resolve_context(reference.group(1), visited)
        return page_intervals, quote

    for index in range(len(matches) - 1, -1, -1):
        heading = matches[index]
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        block = markdown[heading.start():end]
        finding_id = heading.group(1)
        page_intervals, quote = resolve_context(heading.group(1), set())
        page = page_intervals[0][0] if page_intervals else None
        image_path = evidence_dir / f"{finding_id}.png"
        for stale in evidence_dir.glob(f"{finding_id}-p*.png"):
            stale.unlink(missing_ok=True)
        image_path.unlink(missing_ok=True)
        capture_errors: list[str] = []
        captures: list[dict[str, Any]] = []
        if not page_intervals:
            capture_errors.append("缺少可解析的页码")
        elif quote is None:
            capture_errors.append("缺少可用于定位的原文上下文")
        elif not source_pdf.is_file():
            capture_errors.append(f"脱敏 PDF 不存在：{source_pdf.name}")
        else:
            try:
                with pymupdf.open(source_pdf) as source_doc:
                    page_count = source_doc.page_count
                requested_pages: list[int] = []
                seen_pages: set[int] = set()
                for first, last in page_intervals:
                    if last < first:
                        capture_errors.append(f"页码范围 {first}-{last} 无效")
                        continue
                    if first < 1:
                        capture_errors.append(f"页码 {first} 超出脱敏 PDF 页数范围")
                    if last > page_count:
                        capture_errors.append(f"页码 {last} 超出脱敏 PDF 页数范围")
                    valid_first, valid_last = max(first, 1), min(last, page_count)
                    for number in range(valid_first, valid_last + 1):
                        if number not in seen_pages:
                            requested_pages.append(number)
                            seen_pages.add(number)
                if len(seen_pages) == 1 and CONTINUATION_RE.search(block):
                    current_page = requested_pages[0]
                    if current_page > 1:
                        requested_pages.insert(0, current_page - 1)
                        captures_context_page = current_page - 1
                    else:
                        captures_context_page = None
                else:
                    captures_context_page = None
                if not requested_pages and not capture_errors:
                    capture_errors.append("页码列表中没有有效页面")
                for number in requested_pages:
                    page_image = evidence_dir / f"{finding_id}-p{number}.png"
                    capture_mode = "quote"
                    command = [sys.executable, str(SCRIPT_DIR / "capture_evidence.py"), str(source_pdf),
                               "--page", str(number), "--search", quote, "--out", str(page_image)]
                    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                            errors="replace")
                    if result.returncode != 0 and "Search text not found" in (result.stderr + result.stdout):
                        capture_mode = "full-page fallback"
                        command = [sys.executable, str(SCRIPT_DIR / "capture_evidence.py"), str(source_pdf),
                                   "--page", str(number), "--full", "--out", str(page_image)]
                        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                                errors="replace")
                    if result.returncode != 0 or not page_image.is_file():
                        page_image.unlink(missing_ok=True)
                        message = (result.stderr or result.stdout or "截图脚本未生成图片").strip().splitlines()[-1]
                        capture_errors.append(f"第 {number} 页：{message}")
                    else:
                        captures.append({
                            "page": number,
                            "image": str(page_image),
                            "reference": f"evidence/{page_image.name}",
                            "capture_mode": capture_mode,
                            "context_page": number == captures_context_page,
                        })
            except OSError as exc:
                capture_errors.append(f"无法启动截图脚本：{exc}")
        if captures:
            primary_capture = next((item for item in captures if item["page"] == page), captures[0])
            shutil.copyfile(primary_capture["image"], image_path)
            # Keep the model-cited page at the legacy path for existing references.
            capture_references = [f"![{finding_id} 证据：第 {primary_capture['page']} 页](evidence/{finding_id}.png)"]
            capture_references.extend(
                f"![{finding_id} 证据：第 {item['page']} 页](evidence/{Path(item['image']).name})"
                for item in captures if item is not primary_capture
            )
        else:
            capture_references = []
        if capture_errors:
            error = "；".join(capture_errors)
            errors.append(f"{finding_id}: {error}")
            block = _technical_note(block, error)
            status = "error"
        else:
            error = None
            status = "captured"
        block = re.sub(
            rf"!\[[^\]]*\]\(evidence/{re.escape(finding_id)}(?:-p[1-9]\d*)?\.png\)",
            "", block,
        )
        if capture_references:
            evidence_header = re.search(r"\*\*证据截图\*\*[^\n]*(?:\n|$)", block)
            refs = "\n" + "\n".join(capture_references) + "\n"
            if evidence_header:
                block = block[:evidence_header.end()] + refs + block[evidence_header.end():]
            else:
                block = block.rstrip() + "\n\n" + "\n".join(capture_references) + "\n"
        primary_capture_mode = next(
            (item["capture_mode"] for item in captures if item["page"] == page),
            captures[0]["capture_mode"] if captures else None,
        )
        findings.append({
            "id": finding_id,
            "page": page,
            "image": str(image_path) if captures else None,
            "images": captures,
            "status": status,
            "capture_mode": primary_capture_mode,
            "error": error,
        })
        markdown = markdown[:heading.start()] + block + markdown[end:]
    findings.reverse()

    reference_errors = _missing_local_evidence_refs(markdown, report_dir)
    errors.extend(reference_errors)
    enriched_path.write_text(markdown, encoding="utf-8")
    render_script = SCRIPT_DIR / "render_report.py"
    html_temp = report_dir / f".{html_path.stem}.{os.getpid()}.{id(findings)}.tmp.html"
    pdf_temp = report_dir / f".{pdf_path.stem}.{os.getpid()}.{id(findings)}.tmp.pdf"
    render_result = None
    pdf_success = False
    html_success = False
    try:
        render_result = subprocess.run(
            [sys.executable, str(render_script), str(enriched_path), "--out", str(html_temp)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError as exc:
        errors.append(f"HTML 渲染失败：无法启动渲染脚本：{exc}")
    if render_result is not None and render_result.returncode == 0 and html_temp.is_file():
        html_temp.replace(html_path)
        html_success = True
    elif render_result is not None:
        errors.append(f"HTML 渲染失败：{render_result.stderr.strip() or render_result.stdout.strip() or '渲染脚本未生成 HTML'}")
    if html_success:
        try:
            _render_pdf(html_path, pdf_temp)
            _subset_and_validate_pdf(pdf_temp)
            rendered = pymupdf.open(pdf_temp)
            if rendered.page_count < 1:
                raise RuntimeError("PDF 没有页面")
            rendered.close()
            pdf_temp.replace(pdf_path)
            pdf_success = True
        except Exception as exc:
            errors.append(f"PDF 转换失败：{exc}")
    html_temp.unlink(missing_ok=True)
    pdf_temp.unlink(missing_ok=True)
    delivered_pdf = str(pdf_path) if pdf_success else None
    return {"markdown": str(enriched_path), "raw_markdown": str(source), "enriched_markdown": str(enriched_path),
            "html": str(html_path) if html_success else None,
            "pdf": delivered_pdf, "report_pdf": delivered_pdf, "findings": findings, "errors": errors,
            "evidence_errors": [item["error"] for item in findings if item["error"]] + reference_errors}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown")
    parser.add_argument("desensitized_pdf")
    parser.add_argument("output_pdf")
    args = parser.parse_args()
    print(json.dumps(deliver_report(args.markdown, args.desensitized_pdf, args.output_pdf), ensure_ascii=False, indent=2))
