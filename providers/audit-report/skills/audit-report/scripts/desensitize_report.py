#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local desensitization before a report is sent to the LLM.

Confirmed scope: redact organization/supplier identity, contact details,
customer/project identity and sample/part descriptions. Preserve all identifiers,
versions, materials, dates, quantities, test phases and audit standards.
Only redact identified text or its value cell; never mask row/table bands.
Signature images/names are removed from labeled signature cells; seals/dates remain.
Header/footer image removal remains unchanged.

Usage:
    python desensitize_report.py input.docx --out output.docx
    python desensitize_report.py input.pdf  --out output.pdf --max-pages 20
    python desensitize_report.py input.pdf  --out output.pdf --tables
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EXCLUDE_KEYWORDS = [
    "检测项目", "试验单位地址", "检测依据", "判定依据", "检测方法", "检测标准",
    "试验单位名称", "试验日期", "检测日期", "校准有效期", "报告编号",
    "实验室名称", "实验室地址",
]

SIGNATURE_LABELS = [
    "编制", "编制人", "编写", "编写人", "审核", "审核人", "批准", "批准人", "签名", "签字", "签署",
    "Prepared by", "Prepare", "Audited by", "Audit", "Reviewed by", "Review", "Approved by", "Approve", "Signature", "Signed by",
]

ALL_LABELS = [
    ["委托单位名称", "Client Name", "Applicant name", "生产单位名称", "委托单位", "Client", "Customer", "零件生产商", "Part Manufacturer"],
    ["材质供应商", "Material Supplier", "材料供应商", "表面处理供应商", "Coating Supplier", "零部件一级供应商", "Tier 1 Supplier", "一级供应商", "供应商", "Supplier"],
    ["委托单位地址", "Client Address", "Applicant address", "Tel.", "Tel", "电话", "E-mail", "电子邮箱", "邮箱", "地址", "Address", "联系人", "CONTACT", "Attn."],
    ["车厂", "OEM", "车型", "Vehicle Model", "项目名称", "Project Name"],
    ["样品名称", "Sample Name", "样品规格", "Sample Specification", "样品信息", "Sample information", "零件名称", "DUT"],
    SIGNATURE_LABELS,
]

RETAINED_LABELS = EXCLUDE_KEYWORDS + [
    "零件号", "Part No.", "Part Number", "批次号", "Batch No.", "样件件号", "Sample Part Number",
    "车型项目号", "Vehicle Project Number", "合同号", "Contract No", "Contract No.",
    "测试计划编号", "Test plan No", "Test Plan Approval Number", "测试计划版本", "Test plan Revision",
    "软件版本号", "Software Version", "软件版本", "硬件版本号", "Hardware Version", "硬件版本",
    "材质信息", "Material information", "材料名称", "Material name", "材料牌号", "Material brand",
    "表面处理信息", "Coating information", "生产日期", "Manufacture date", "测试阶段", "试验阶段", "Test phase",
    "零件数量", "Qty", "试验标准", "Specification", "试验大纲", "Test plan", "Report No", "Report No.",
    "收样日期", "Samples received date", "Test date", "Fax", "传真", "序号", "No.", "No",
    "签发日期", "Issue Date", "Project number of the vehicle model", "Project number of", "the vehicle model", "Batch number", "production date",
]

TECHNICAL_HEADER_MARKERS = (
    "产品端电压", "产品工作电流", "静态电流", "MCU温度", "试验样件工作模式",
    "Terminal Voltage", "Operating Current", "Operating mode",
)
TECHNICAL_HEADER_HINTS = (
    "产品端", "端电压", "产品工作电", "工作电流", "静态电", "温度", "MCU",
    "Termina", "Voltage", "Operat", "Current", "工作模式",
)

PARTIAL_REPLACE_WORDS = ["小米", "Xiaomi", "XIAOMI", "主机厂"]
SENSITIVE_LABELS = [label for group in ALL_LABELS for label in group]
FIELD_LABELS = SENSITIVE_LABELS + RETAINED_LABELS
FIELD_ALTERNATIVES = "|".join(re.escape(label) for label in sorted(FIELD_LABELS, key=len, reverse=True))
LABEL_PATTERN = re.compile(
    r"(?<![A-Za-z])((?:" + FIELD_ALTERNATIVES + r")\s*[:：]\s*)([^\n]*?)(?=(?<![A-Za-z])(?:"
    + FIELD_ALTERNATIVES + r")\s*[:：]|\n|$)", re.IGNORECASE | re.MULTILINE,
)
LABEL_VALUE_RE = re.compile(r"^\s*(.+?)\s*[:：]\s*(.*)$")
LABEL_MATCHERS = {
    tuple(labels): re.compile("(?:" + "|".join(re.escape(label) for label in sorted(
        {re.sub(r"[\s:：/()]", "", label).casefold() for label in labels}, key=len, reverse=True
    )) + ")+") for labels in (SENSITIVE_LABELS, RETAINED_LABELS, FIELD_LABELS, SIGNATURE_LABELS)
}


def is_excluded(text: str) -> bool:
    return any(keyword in text for keyword in EXCLUDE_KEYWORDS)


def _matches_labels(text: str, labels: list[str]) -> bool:
    clean = re.sub(r"[\s:：/()]", "", text).casefold()
    return bool(clean and LABEL_MATCHERS[tuple(labels)].fullmatch(clean))


def is_label(text: str) -> bool:
    """Recognize confirmed identity/contact/description and signature field labels."""
    return not is_excluded(text.split(":", 1)[0].split("：", 1)[0]) and _matches_labels(text.split(":", 1)[0].split("：", 1)[0], SENSITIVE_LABELS)


def _is_field_label(text: str) -> bool:
    return _matches_labels(text, FIELD_LABELS) or bool(LABEL_VALUE_RE.match(text))


def _sensitive_ranges(text: str):
    for match in LABEL_PATTERN.finditer(text):
        if is_label(match.group(1)) and match.group(2).strip() not in ("", "N/A"):
            start, end = match.span(2)
            while start < end and text[start].isspace():
                start += 1
            while end > start and text[end - 1].isspace():
                end -= 1
            yield start, end


def _normalize_header_context(text: str) -> str:
    """Normalize whitespace and case only for recognizing technical headers."""
    return re.sub(r"\s+", "", text).casefold()


def _is_technical_header(text: str) -> bool:
    normalized = _normalize_header_context(text)
    return any(_normalize_header_context(marker) in normalized for marker in TECHNICAL_HEADER_MARKERS)


def _is_bare_dut(text: str) -> bool:
    return re.fullmatch(r"\s*DUT\s*", text, re.IGNORECASE) is not None


def _is_technical_dut_line(text: str, rect, has_technical_header: bool, hints: list) -> bool:
    if not _is_bare_dut(text) or not has_technical_header:
        return False
    center_y = (rect.y0 + rect.y1) / 2
    for hint_text, hint_rect in hints:
        normalized = _normalize_header_context(hint_text)
        if not any(_normalize_header_context(hint) in normalized for hint in TECHNICAL_HEADER_HINTS):
            continue
        center_hint_y = (hint_rect.y0 + hint_rect.y1) / 2
        horizontal_gap = max(rect.x0 - hint_rect.x1, hint_rect.x0 - rect.x1, 0)
        if abs(center_y - center_hint_y) <= 55 and horizontal_gap <= 250:
            return True
    return False


def _set_paragraph_text(paragraph, text: str) -> None:
    """Replace paragraph text while preserving the first run's formatting."""
    if paragraph.runs:
        paragraph.runs[0].text = text
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(text)


def _clear_cell_text(cell, text: str = "N/A") -> None:
    """Clear a table cell and write text while preserving basic formatting."""
    if not cell.paragraphs:
        cell.text = text
        return
    first = cell.paragraphs[0]
    _set_paragraph_text(first, text)
    for paragraph in cell.paragraphs[1:]:
        paragraph._element.getparent().remove(paragraph._element)


def _remove_images(element) -> int:
    """Remove w:drawing / w:pict descendants (header logos, shapes)."""
    removed = 0
    for child in list(element.iter()):
        tag = str(child.tag)
        if tag.endswith("}drawing") or tag.endswith("}pict"):
            parent = child.getparent()
            if parent is not None:
                parent.remove(child)
                removed += 1
    return removed


def _process_paragraph(paragraph) -> int:
    text = "".join(run.text for run in paragraph.runs)
    if _matches_labels(text.split(":", 1)[0].split("：", 1)[0], SIGNATURE_LABELS):
        _remove_images(paragraph._element)
    new_text = text
    for start, end in reversed(list(_sensitive_ranges(text))):
        new_text = new_text[:start] + "N/A" + new_text[end:]
    if new_text != text:
        _set_paragraph_text(paragraph, new_text)
        return 1
    return 0


def _partial_word_ranges(text: str):
    retained = [match.span(2) for match in LABEL_PATTERN.finditer(text) if not is_label(match.group(1))]
    if is_excluded(text):
        return
    for word in PARTIAL_REPLACE_WORDS:
        for match in re.finditer(re.escape(word), text, flags=re.IGNORECASE):
            if not any(start <= match.start() and match.end() <= end for start, end in retained):
                yield match.span()


def _process_partial_paragraph(paragraph) -> int:
    text = "".join(run.text for run in paragraph.runs)
    new_text = text
    for start, end in sorted(set(_partial_word_ranges(text)), reverse=True):
        new_text = new_text[:start] + "N/A" + new_text[end:]
    if new_text != text:
        _set_paragraph_text(paragraph, new_text)
        return 1
    return 0


def _iter_tables(container):
    """Yield tables, including tables nested in cells."""
    for table in getattr(container, "tables", []):
        yield table
        for row in table.rows:
            for cell in row.cells:
                yield from _iter_tables(cell)


def _iter_paragraphs(container):
    for paragraph in getattr(container, "paragraphs", []):
        yield paragraph
    for table in getattr(container, "tables", []):
        for row in table.rows:
            for cell in row.cells:
                yield from _iter_paragraphs(cell)


def _process_table(table, stats: dict) -> None:
    headers = table.rows[0].cells if table.rows else []
    if len(headers) > 1 and all(_matches_labels(cell.text, FIELD_LABELS) for cell in headers):
        for index, header in enumerate(headers):
            if is_label(header.text):
                for row in table.rows[1:]:
                    removed = _remove_images(row.cells[index]._tc) if _matches_labels(header.text, SIGNATURE_LABELS) else 0
                    stats["removed_images"] += removed
                    if removed or row.cells[index].text.strip() not in ("", "N/A"):
                        _clear_cell_text(row.cells[index])
                        stats["redacted_cells"] += 1
        return
    for row in table.rows:
        unique_cells = []
        seen = set()
        for cell in row.cells:
            if id(cell._tc) not in seen:
                seen.add(id(cell._tc))
                unique_cells.append(cell)
        for index, cell in enumerate(unique_cells[:-1]):
            text = cell.text.strip()
            if not is_label(text) or (LABEL_VALUE_RE.match(text) and LABEL_VALUE_RE.match(text).group(2).strip()):
                continue
            target = unique_cells[index + 1]
            target_text = target.text.strip()
            removed = _remove_images(target._tc) if _matches_labels(text, SIGNATURE_LABELS) else 0
            stats["removed_images"] += removed
            if (removed or target_text and target_text != "N/A") and not _is_field_label(target_text):
                _clear_cell_text(target)
                stats["redacted_cells"] += 1


def desensitize_docx(input_path: Path, output_path: Path) -> dict:
    try:
        from docx import Document
    except ImportError as exc:
        raise SystemExit(
            "python-docx is required for DOCX desensitization. Install: pip install python-docx"
        ) from exc

    doc = Document(str(input_path))
    stats = {
        "file": str(input_path),
        "type": "docx",
        "redacted_paragraphs": 0,
        "redacted_cells": 0,
        "redacted_partial_words": 0,
        "removed_images": 0,
    }

    # Headers/footers: remove logos and process text.
    for section in doc.sections:
        parts = [
            section.header, section.first_page_header, section.even_page_header,
            section.footer, section.first_page_footer, section.even_page_footer,
        ]
        for part in parts:
            stats["removed_images"] += _remove_images(part._element)
            for paragraph in part.paragraphs:
                stats["redacted_partial_words"] += _process_partial_paragraph(paragraph)
                stats["redacted_paragraphs"] += _process_paragraph(paragraph)
            for table in part.tables:
                _process_table(table, stats)

    # Body: partial OEM words first, then labels/tables.
    for paragraph in doc.paragraphs:
        stats["redacted_partial_words"] += _process_partial_paragraph(paragraph)
    for table in _iter_tables(doc):
        for row in table.rows:
            for index, cell in enumerate(row.cells):
                if index and _matches_labels(row.cells[index - 1].text, RETAINED_LABELS):
                    continue
                for paragraph in cell.paragraphs:
                    stats["redacted_partial_words"] += _process_partial_paragraph(paragraph)

    # Only the identified value cell is cleared; adjacent fields remain intact.
    for table in _iter_tables(doc):
        _process_table(table, stats)

    # Label-value paragraphs (body + table cells).
    for paragraph in doc.paragraphs:
        stats["redacted_paragraphs"] += _process_paragraph(paragraph)
    for table in _iter_tables(doc):
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    stats["redacted_paragraphs"] += _process_paragraph(paragraph)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    return stats


def _redact_pdf_text(page, rects: list, stats: dict) -> None:
    if not rects:
        return
    for rect in rects:
        page.add_redact_annot(rect, fill=(0, 0, 0))
    page.apply_redactions(images=0, graphics=0)
    stats["redacted_regions"] += len(rects)


def _signature_regions(page, lines: list, pymupdf) -> list:
    """Locate signature value cells from their labels and actual table borders."""
    horizontal, vertical = [], []
    for drawing in page.get_drawings():
        for item in drawing["items"]:
            segments = []
            if item[0] == "l":
                segments = [(item[1], item[2])]
            elif item[0] == "re":
                rect = item[1]
                segments = [(rect.tl, rect.tr), (rect.bl, rect.br), (rect.tl, rect.bl), (rect.tr, rect.br)]
            for start, end in segments:
                if abs(start.y - end.y) < 0.5:
                    horizontal.append((start.y, min(start.x, end.x), max(start.x, end.x)))
                if abs(start.x - end.x) < 0.5:
                    vertical.append((start.x, min(start.y, end.y), max(start.y, end.y)))
    regions = []
    for line in lines:
        label = line["text"].split(":", 1)[0].split("：", 1)[0]
        if not _matches_labels(label, SIGNATURE_LABELS):
            continue
        area = line["rect"]
        center_x = (area.x0 + area.x1) / 2
        dividers = sorted({x for x, start, end in vertical if start <= area.y0 + 1 and end >= area.y1 + 2})
        left = max((x for x in dividers if x < center_x), default=None)
        right = min((x for x in dividers if x > center_x), default=None)
        if left is None or right is None:
            continue
        edges = sorted({y for y, start, end in horizontal
                        if y >= area.y1 and start <= left + 1 and end >= right - 1})
        if len(edges) >= 2:
            top, bottom = edges[:2]
            regions.append(pymupdf.Rect(left + 1, top + 1, right - 1, bottom - 1))
    return regions


def desensitize_pdf(input_path: Path, output_path: Path, max_pages: int | None = None, tables: bool = False) -> dict:
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf  # type: ignore
        except ImportError as exc:
            raise SystemExit("PyMuPDF is required for PDF desensitization. Install: pip install pymupdf") from exc

    doc = pymupdf.open(str(input_path))
    stats = {
        "file": str(input_path),
        "type": "pdf",
        "pages": doc.page_count,
        "redacted_regions": 0,
        "removed_header_images": 0,
        "redacted_signatures": 0,
        "removed_signature_widgets": 0,
        "table_pages": 0,
    }
    limit = doc.page_count if max_pages is None else min(doc.page_count, max_pages)

    for page_index in range(limit):
        page = doc[page_index]
        rects = []

        flags = pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_PRESERVE_IMAGES
        lines = []
        for block in page.get_text("rawdict", flags=flags).get("blocks", []):
            for line in block.get("lines", []):
                chars = [char for span in line.get("spans", []) for char in span.get("chars", [])]
                text = "".join(char["c"] for char in chars)
                if text.strip():
                    lines.append({"text": text, "rect": pymupdf.Rect(line["bbox"]), "chars": chars})
        signature_regions = _signature_regions(page, lines, pymupdf) if any(
            _matches_labels(line["text"].split(":", 1)[0].split("：", 1)[0], SIGNATURE_LABELS) for line in lines
        ) else []
        has_technical_header = _is_technical_header(" ".join(line["text"] for line in lines))
        technical_hints = [(line["text"], line["rect"]) for line in lines]

        def text_rect(line, start=0, end=None):
            chars = line["chars"][start:end]
            rect = pymupdf.Rect(chars[0]["bbox"])
            for char in chars[1:]:
                rect |= pymupdf.Rect(char["bbox"])
            # Tighten vertical bounds to avoid touching glyphs on adjacent lines.
            inset = rect.height * 0.2
            return pymupdf.Rect(rect.x0, rect.y0 + inset, rect.x1, rect.y1 - inset)

        table_cells = []
        handled_cells = []
        retained_lines = set()
        if tables:
            try:
                found = page.find_tables()
            except Exception:
                found = None
            if found is not None and found.tables:
                stats["table_pages"] += 1
                for table in found.tables:
                    headers = [pymupdf.Rect(cell) for cell in table.rows[0].cells if cell is not None and page.get_textbox(cell).strip()] if table.rows else []
                    if len(headers) > 1 and all(_matches_labels(page.get_textbox(cell), FIELD_LABELS) for cell in headers):
                        for header in headers:
                            if not is_label(page.get_textbox(header)):
                                continue
                            column = pymupdf.Rect(header.x0, header.y1, header.x1, table.bbox[3])
                            for line in lines:
                                target = text_rect(line) & column
                                if not target.is_empty:
                                    rects.append(target)
                        handled_cells.extend(headers)
                    for row in table.rows:
                        cells = [pymupdf.Rect(cell) for cell in row.cells if cell is not None]
                        table_cells.extend(cells)
                        for index, cell in enumerate(cells[:-1]):
                            label = page.get_textbox(cell).strip()
                            sensitive = is_label(label)
                            if not (sensitive or _matches_labels(label, RETAINED_LABELS)) or (LABEL_VALUE_RE.match(label) and LABEL_VALUE_RE.match(label).group(2).strip()):
                                continue
                            if _is_technical_dut_line(label, cell, has_technical_header, technical_hints):
                                continue
                            target = cells[index + 1]
                            value = page.get_textbox(target).strip()
                            if not value or value == "N/A" or _is_field_label(value):
                                continue
                            handled_cells.append(cell)
                            for line in lines:
                                if target.contains((line["rect"].tl + line["rect"].br) / 2):
                                    if sensitive:
                                        rects.append(text_rect(line) & target)
                                    else:
                                        retained_lines.add(id(line))

        for line in lines:
            text, area = line["text"], line["rect"]
            for start, end in _sensitive_ranges(text):
                rects.append(text_rect(line, start, end))
            sensitive = is_label(text)
            if not (sensitive or _matches_labels(text, RETAINED_LABELS)) or (LABEL_VALUE_RE.match(text) and LABEL_VALUE_RE.match(text).group(2).strip()):
                continue
            if _is_technical_dut_line(text, area, has_technical_header, technical_hints):
                continue
            if any(cell.contains((area.tl + area.br) / 2) for cell in handled_cells):
                continue
            cell = next((cell for cell in table_cells if cell.contains((area.tl + area.br) / 2)), None)
            if cell is not None and _matches_labels(page.get_textbox(cell), FIELD_LABELS):
                cell = None
            peers = lines if cell is None else [other for other in lines
                if cell.contains((other["rect"].tl + other["rect"].br) / 2)]
            # A label inside a value-bearing cell cannot reach neighboring cells.
            candidates = sorted((other for other in peers if other is not line
                and other["rect"].x0 >= area.x1
                and min(area.y1, other["rect"].y1) > max(area.y0, other["rect"].y0)),
                key=lambda other: other["rect"].x0)
            if candidates and not _is_field_label(candidates[0]["text"]):
                first = candidates[0]
                for target in candidates:
                    if abs(target["rect"].x0 - first["rect"].x0) > 2 or _is_field_label(target["text"]):
                        break
                    if target["text"].strip() != "N/A":
                        if sensitive:
                            rects.append(text_rect(target))
                        else:
                            retained_lines.add(id(target))
            else:
                # A stacked value must align with this label and precede any new field.
                below = sorted((other for other in peers if other["rect"].y0 >= area.y1
                    and (cell is not None or abs(other["rect"].x0 - area.x0) <= 2)), key=lambda other: other["rect"].y0)
                for target in below:
                    if _is_field_label(target["text"]) or (cell is None and target["rect"].y0 - area.y1 > 40):
                        break
                    if target["text"].strip() != "N/A":
                        if sensitive:
                            rects.append(text_rect(target))
                        else:
                            retained_lines.add(id(target))
                    if cell is None:
                        break

        for line in lines:
            if id(line) not in retained_lines:
                for start, end in _partial_word_ranges(line["text"]):
                    rects.append(text_rect(line, start, end))
        _redact_pdf_text(page, rects, stats)
        for widget in list(page.widgets() or []):
            if any(region.intersects(widget.rect) for region in signature_regions):
                page.delete_widget(widget)
                stats["removed_signature_widgets"] += 1
        for annotation in list(page.annots() or []):
            if any(region.intersects(annotation.rect) for region in signature_regions):
                page.delete_annot(annotation)
        for region in signature_regions:
            page.add_redact_annot(region, fill=(0, 0, 0))
        if signature_regions:
            page.apply_redactions(images=1, graphics=2)
            stats["redacted_signatures"] += len(signature_regions)
            stats["redacted_regions"] += len(signature_regions)
        image_rects = []
        # Header/footer logo images: redact images in the top/bottom bands.
        for image in page.get_images(full=True):
            for rect in page.get_image_rects(image[0]):
                if (rect.y1 <= page.rect.height * 0.16
                        or rect.y0 >= page.rect.height * 0.92):
                    image_rects.append(rect)
                    stats["removed_header_images"] += 1

        for rect in image_rects:
            page.add_redact_annot(rect, fill=(0, 0, 0))
        if image_rects:
            page.apply_redactions(images=2, graphics=0)
            stats["redacted_regions"] += len(image_rects)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path), garbage=4, deflate=True)
    return stats


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Locally desensitize a report before LLM processing.")
    parser.add_argument("input", help="Input .docx or .pdf")
    parser.add_argument("--out", required=True, help="Output desensitized file")
    parser.add_argument("--report", help="Optional JSON report path")
    parser.add_argument("--max-pages", type=int, help="Limit PDF pages (testing only)")
    parser.add_argument("--tables", action="store_true", help="Also redact PDF table cells (slower)")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.out)
    if not input_path.is_file():
        raise SystemExit(f"File not found: {input_path}")
    suffix = input_path.suffix.lower()
    if suffix == ".docx":
        stats = desensitize_docx(input_path, output_path)
    elif suffix == ".pdf":
        stats = desensitize_pdf(input_path, output_path, args.max_pages, args.tables)
        print("[WARN] PDF table-cell redaction is best-effort; prefer the DOCX source for full desensitization.")
    else:
        raise SystemExit("Only .docx and .pdf are supported; convert .doc to .docx first.")

    if args.report:
        Path(args.report).write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] {output_path}")
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
