#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read audit reference materials without making business judgments."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from datetime import date, datetime, time
from pathlib import Path
from typing import Any


def classify_material(filename: str) -> str:
    """Classify a material by its filename, giving ledger names precedence."""
    if "台账" in filename:
        return "ledger"
    if "检测标准" in filename or "标准库" in filename:
        return "standard"
    return "supplement"


def material_availability(materials: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Describe supplied input kinds without deciding their business applicability."""
    kinds: set[str] = set()
    supporting: list[str] = []
    support_terms = ("试验大纲", "测试大纲", "测试计划", "测试方案", "原始记录", "委托单", "配套材料")
    for item in materials or []:
        filename = str(item.get("filename") or "")
        kind = str(item.get("kind") or classify_material(filename))
        purpose = str(item.get("purpose") or item.get("用途") or "")
        if kind in {"standard", "ledger", "materials", "visual", "visual-facts"}:
            kinds.add(kind)
        elif purpose and (any(term in purpose for term in support_terms)
                          or any(term in purpose.lower() for term in ("r46", "support", "cross-file"))):
            kinds.add("materials")
            supporting.append(filename or purpose)
        elif any(term in filename for term in support_terms):
            kinds.add("materials")
            supporting.append(filename)
        # Generic supplement content is deliberately not treated as proof of an R46 source.
    return {"kinds": kinds, "supports_materials": "materials" in kinds,
            "supporting_files": supporting}


def _cell_text(value: Any, number_format: str | None = None) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if (isinstance(value, (int, float)) and not isinstance(value, bool)
            and float(value).is_integer() and number_format and re.fullmatch(r"0+", number_format)):
        return f"{int(value):0{len(number_format)}d}"
    return str(value)


def _read_excel(path: Path) -> tuple[str, list[dict[str, Any]], str]:
    try:
        from openpyxl import load_workbook
        from openpyxl.utils import get_column_letter
    except ImportError as exc:
        raise RuntimeError("openpyxl is required to read Excel materials") from exc

    workbook = load_workbook(path, read_only=True, data_only=False)
    cached_workbook = load_workbook(path, read_only=True, data_only=True)
    blocks: list[str] = []
    positions: list[dict[str, Any]] = []
    has_values = False
    header_kinds: set[str] = set()
    try:
        for sheet, cached_sheet in zip(workbook.worksheets, cached_workbook.worksheets):
            blocks.append(f"## Sheet: {sheet.title}")
            cached_rows = cached_sheet.iter_rows()
            for row_no, (row, cached_row) in enumerate(zip(sheet.iter_rows(), cached_rows), start=1):
                values = []
                for cell, cached_cell in zip(row, cached_row):
                    if cell.data_type == "f":
                        cached_value = cached_cell.value
                        value = (_cell_text(cached_value, cell.number_format) if cached_value is not None
                                 else f"{cell.value} (cached result unavailable)")
                    else:
                        value = _cell_text(cell.value, cell.number_format)
                    values.append(value)
                if not any(values):
                    continue
                has_values = True
                row_text = "".join(values).replace(" ", "")
                if "校准有效期" in row_text and ("内部编号" in row_text or "设备编号" in row_text):
                    header_kinds.add("ledger")
                if "标准编号" in row_text and ("最新版本号" in row_text or "标准名称" in row_text):
                    header_kinds.add("standard")
                columns = [index + 1 for index, value in enumerate(values) if value]
                line = " | ".join(
                    f"{get_column_letter(index + 1)}{row_no}={values[index]}"
                    for index in range(len(values)) if values[index]
                )
                blocks.append(f"[{sheet.title}!A{row_no}:{get_column_letter(len(row))}{row_no}] {line}")
                positions.append({"sheet": sheet.title, "row": row_no, "columns": [get_column_letter(index) for index in columns]})
    finally:
        workbook.close()
        cached_workbook.close()
    if not has_values:
        raise ValueError("workbook contains no usable cell values")
    kind = "ledger" if "ledger" in header_kinds else "standard" if "standard" in header_kinds else "supplement"
    return "\n".join(blocks), positions, kind


def _extractor() -> Any:
    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import extract_report

    return extract_report


def _read_document(path: Path, output_dir: Path | None) -> tuple[str, list[dict[str, Any]]]:
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md", ".csv"):
        content = path.read_text(encoding="utf-8-sig")
        return content, [{"line": index} for index, _ in enumerate(content.splitlines(), start=1)]
    if suffix not in (".pdf", ".docx"):
        raise ValueError(f"unsupported material type: {suffix or '(no extension)'}")

    extractor = _extractor()
    if output_dir is None:
        temp = tempfile.TemporaryDirectory(prefix="audit-material-")
        outdir = Path(temp.name)
    else:
        temp = None
        outdir = output_dir
    try:
        if suffix == ".pdf":
            metadata = extractor.extract_pdf(path, outdir, render=False, extract_tables=False)
            content = (outdir / metadata["text_file"]).read_text(encoding="utf-8")
            pages = metadata.get("pages", [])
            positions = [{"page": page["page"]} for page in pages]
        else:
            extractor.extract_docx(path, outdir, render=False, convert=False)
            content = (outdir / "lines.md").read_text(encoding="utf-8")
            positions = [{"document": "DOCX paragraphs and tables; P### paragraphs and T##-R## rows"}]
        return content, positions
    finally:
        if temp is not None:
            temp.cleanup()


def read_material(path: str | Path, output_dir: str | Path | None = None) -> dict[str, Any]:
    """Read a material and return JSON-safe content and its source locations.

    Raises an OSError or ValueError with filename context when the file cannot be read.
    """
    source = Path(path)
    try:
        if not source.is_file():
            raise FileNotFoundError("file does not exist")
        if source.suffix.lower() in (".xlsx", ".xlsm"):
            content, positions, excel_header_kind = _read_excel(source)
        else:
            content, positions = _read_document(source, Path(output_dir) if output_dir else None)
            excel_header_kind = "supplement"
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
    except Exception as exc:
        raise ValueError(f"Failed to read material {source.name}: {exc}") from exc
    kind = classify_material(source.name)
    if kind == "supplement" and source.suffix.lower() in (".xlsx", ".xlsm"):
        kind = excel_header_kind
    return {
        "filename": source.name,
        "kind": kind,
        "content": content,
        "sha256": digest,
        "source_position": positions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("materials", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, help="write JSON output to this file (default: stdout)")
    parser.add_argument("--output-dir", type=Path, help="directory for PDF/DOCX extraction artifacts")
    args = parser.parse_args()
    try:
        results = [read_material(path, args.output_dir) for path in args.materials]
        rendered = json.dumps(results, ensure_ascii=False, indent=2)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(rendered + "\n", encoding="utf-8")
        else:
            print(rendered)
        return 0
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
