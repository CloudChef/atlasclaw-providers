#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local desensitization before a report is sent to the LLM.

Rules recovered from the customer's word_tool.exe (PyInstaller, Python 3.13):
- Replace values after known report labels with "N/A".
- Redact tables containing "表面处理信息" completely (except technical labels).
- Replace full-cell material/coating words (TPE, Rand, 底漆, Primer, ...).
- Replace OEM words 小米/Xiaomi/XIAOMI/主机厂 with "N/A".
- Remove header/footer logo images.
- Keep technical fields listed in EXCLUDE_KEYWORDS.

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

ALL_LABELS = [
    ["委托单位名称", "Client Name", "Applicant name", "生产单位名称"],
    ["委托单位地址", "Client Address", "Applicant address"],
    ["车厂", "OEM"],
    ["车型", "Vehicle Model"],
    ["项目名称", "Project Name"],
    ["测试阶段", "试验阶段", "Test phase"],
    ["样品名称", "Sample Name"],
    ["零件号", "Part No.", "Part Number"],
    ["样品规格", "Sample Specification"],
    ["材质信息", "Material information", "材料名称", "Material name", "材料牌号", "Material brand"],
    ["材质供应商", "Material Supplier", "材料供应商"],
    ["表面处理信息", "Coating information"],
    ["表面处理供应商", "Coating Supplier"],
    ["生产日期", "Manufacture date"],
    ["批次号", "Batch No."],
    ["样件件号", "Sample Part Number"],
    ["委托单位", "Client", "Customer"],
    ["零件生产商", "Part Manufacturer"],
    ["零部件一级供应商", "Tier 1 Supplier", "一级供应商"],
    ["车型项目号", "Vehicle Project Number"],
    ["软件版本号", "Software Version", "软件版本"],
    ["硬件版本号", "Hardware Version", "硬件版本"],
    ["供应商", "Supplier"],
    ["样品信息", "Sample information"],
    ["Tel", "电话"],
    ["E-mail", "邮箱"],
    ["地址", "Address"],
    ["联系人", "CONTACT", "Attn."],
    ["合同号", "Contract No", "测试计划编号", "Test plan No", "测试计划版本",
     "Test plan Revision", "零件名称", "DUT", "零件数量", "Qty",
     "试验标准", "Specification", "试验大纲", "Test plan"],
]

FULL_CELL_REPLACE_WORDS = [
    "TPE LC65A", "TPE", "冼洋 Rand", "洗洋 Rand", "Rand",
    "详见“材质信息”", "Details see Material information", "详见材质信息",
    "底漆", "Primer", "色漆", "Base coat", "清漆", "Clear coat",
]

PARTIAL_REPLACE_WORDS = ["小米", "Xiaomi", "XIAOMI", "主机厂"]

LABEL_PATTERN = re.compile(
    "((?:" + "|".join(re.escape(label) for label in sorted(
        (label for group in ALL_LABELS for label in group), key=len, reverse=True
    )) + r")\s*[:：]\s*)([^\n]*?)(?=\n|$)",
    re.IGNORECASE | re.MULTILINE,
)
LABEL_VALUE_RE = re.compile(r"^\s*(.+?)\s*[:：]\s*(.*)$")


def is_excluded(text: str) -> bool:
    return any(keyword in text for keyword in EXCLUDE_KEYWORDS)


def is_label(text: str) -> bool:
    clean = re.sub(r"[\s:：]", "", text).lower()
    if not clean or len(clean) > 30 or is_excluded(text):
        return False
    return any(
        re.sub(r"\s", "", label).lower() in clean
        for group in ALL_LABELS
        for label in group
    )


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
    if not text or is_excluded(text):
        return 0
    new_text = text
    if LABEL_PATTERN.search(text) and re.search(r"[:：]", text):
        def replace(match):
            prefix, suffix = match.group(1), match.group(2)
            if suffix and suffix.strip() != "N/A" and not is_excluded(suffix):
                return prefix + "N/A"
            return match.group(0)

        new_text = LABEL_PATTERN.sub(replace, text)
    if new_text != text:
        _set_paragraph_text(paragraph, new_text)
        return 1
    return 0


def _process_partial_paragraph(paragraph) -> int:
    text = "".join(run.text for run in paragraph.runs)
    if not text or is_excluded(text):
        return 0
    new_text = text
    for word in PARTIAL_REPLACE_WORDS:
        new_text = re.sub(re.escape(word), "N/A", new_text, flags=re.IGNORECASE)
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
    table_text = "".join(cell.text for row in table.rows for cell in row.cells)
    surface_table = "表面处理信息" in table_text

    if surface_table:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip() and not is_excluded(cell.text):
                    _clear_cell_text(cell)
                    stats["redacted_cells"] += 1
        return

    for row in table.rows:
        unique_cells = []
        seen = set()
        for cell in row.cells:
            tc_id = id(cell._tc)
            if tc_id in seen:
                continue
            seen.add(tc_id)
            unique_cells.append(cell)

        for index, cell in enumerate(unique_cells):
            text = cell.text.strip()
            if not text or is_excluded(text):
                continue
            is_pointer = any(pointer in text for pointer in ("详见“材质信息”", "详见材质信息"))
            if any(word in text for word in FULL_CELL_REPLACE_WORDS) and not is_pointer:
                _clear_cell_text(cell)
                stats["redacted_cells"] += 1
            elif is_label(text):
                for target in unique_cells[index + 1:]:
                    target_text = target.text.strip()
                    if not target_text:
                        continue
                    if is_excluded(target_text) or is_label(target_text):
                        break
                    if target_text != "N/A":
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
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    stats["redacted_partial_words"] += _process_partial_paragraph(paragraph)

    # Surface-treatment tables are fully redacted before the general pass.
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
    page.apply_redactions()
    stats["redacted_regions"] += len(rects)


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
        "table_pages": 0,
    }
    limit = doc.page_count if max_pages is None else min(doc.page_count, max_pages)

    for page_index in range(limit):
        page = doc[page_index]
        rects = []

        # OEM words anywhere.
        for word in PARTIAL_REPLACE_WORDS:
            rects.extend(page.search_for(word))

        # Full-cell material/coating words (do not redact labels themselves).
        for word in FULL_CELL_REPLACE_WORDS:
            if is_label(word):
                continue
            rects.extend(page.search_for(word))

        # Paragraph lines: label: value -> redact value, including adjacent table cells.
        page_dict = page.get_text("dict")
        lines = []
        for block in page_dict.get("blocks", []):
            for line in block.get("lines", []):
                text = "".join(span.get("text", "") for span in line.get("spans", []))
                if text.strip():
                    lines.append({"text": text, "rect": pymupdf.Rect(line["bbox"])})

        for index, line in enumerate(lines):
            text = line["text"]
            if not text.strip() or is_excluded(text):
                continue
            match = LABEL_VALUE_RE.match(text)
            if match:
                label, value = match.group(1).strip(), match.group(2).strip()
                if value and value != "N/A" and not is_excluded(value) and is_label(label):
                    value_rects = page.search_for(value)
                    if value_rects:
                        rects.extend(value_rects)
                    else:
                        label_rects = page.search_for(label)
                        if label_rects:
                            label_rect = label_rects[0]
                            rects.append(
                                pymupdf.Rect(label_rect.x1, line["rect"].y0, line["rect"].x1, line["rect"].y1)
                            )
                continue

            if not is_label(text):
                continue

            # Same row (table cell): redact non-label cells to the right.
            row_targets = []
            for other in lines:
                if other is line:
                    continue
                if abs((other["rect"].y0 + other["rect"].y1) / 2 - (line["rect"].y0 + line["rect"].y1) / 2) <= 6:
                    if other["rect"].x0 >= line["rect"].x1 - 2:
                        row_targets.append(other)
            for target in row_targets:
                target_text = target["text"].strip()
                if not target_text or target_text == "N/A":
                    continue
                if is_excluded(target_text) or is_label(target_text):
                    break
                rects.append(target["rect"])

            # Row-band fallback: cover the area between this label and the next
            # same-row label (or page edge). This handles table cells whose text
            # is not returned as an independent line.
            next_labels = [
                other for other in lines
                if other is not line
                and abs((other["rect"].y0 + other["rect"].y1) / 2 - (line["rect"].y0 + line["rect"].y1) / 2) <= 6
                and other["rect"].x0 > line["rect"].x1
                and is_label(other["text"])
            ]
            boundary = min((other["rect"].x0 for other in next_labels), default=page.rect.x1) - 2
            if boundary > line["rect"].x1:
                rects.append(
                    pymupdf.Rect(line["rect"].x1, line["rect"].y0 - 2, boundary, line["rect"].y1 + 2)
                )

            # Vertical layout: value on the next line(s) below the label.
            if row_targets:
                continue
            redacted_any = False
            label_skips = 0
            for other in lines[index + 1:index + 8]:
                if other["rect"].y0 <= line["rect"].y1:
                    continue
                if other["rect"].y0 - line["rect"].y1 > 40:
                    break
                target_text = other["text"].strip()
                if not target_text or target_text == "N/A":
                    continue
                if is_excluded(target_text):
                    break
                if is_label(target_text):
                    if redacted_any or label_skips >= 2:
                        break
                    label_skips += 1
                    continue
                rects.append(other["rect"])
                redacted_any = True

        # Optional table-cell redaction (slower; recommended for small files).
        if tables:
            try:
                found = page.find_tables()
            except Exception:
                found = None
            if found is not None and found.tables:
                stats["table_pages"] += 1
                for table in found.tables:
                    for row in table.rows:
                        cells = list(row.cells)
                        for index, cell in enumerate(cells):
                            if cell is None:
                                continue
                            cell_text = page.get_textbox(cell).strip()
                            if not cell_text or is_excluded(cell_text):
                                continue
                            if is_label(cell_text):
                                for target in cells[index + 1:]:
                                    if target is None:
                                        continue
                                    target_text = page.get_textbox(target).strip()
                                    if not target_text:
                                        continue
                                    if is_excluded(target_text) or is_label(target_text):
                                        break
                                    if target_text != "N/A":
                                        rects.append(pymupdf.Rect(target))
                            elif any(word in cell_text for word in FULL_CELL_REPLACE_WORDS):
                                rects.append(pymupdf.Rect(cell))

        # Header/footer logo images: redact images in the top/bottom bands.
        for image in page.get_images(full=True):
            for rect in page.get_image_rects(image[0]):
                if rect.y0 < page.rect.height * 0.16 or rect.y1 > page.rect.height * 0.92:
                    rects.append(rect)
                    stats["removed_header_images"] += 1

        _redact_pdf_text(page, rects, stats)

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
