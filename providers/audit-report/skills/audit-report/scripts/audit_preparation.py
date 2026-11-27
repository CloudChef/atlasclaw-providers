#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prepare a local desensitized PDF using the existing skill programs."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import uuid
from collections import Counter
from pathlib import Path

import pymupdf

PREPARATION_VERSION = 8


def _convert_docx_with_word(source: Path, target: Path) -> Path:
    """Convert DOCX to PDF with local Microsoft Word when LibreOffice is absent."""
    try:
        import win32com.client  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Neither LibreOffice nor pywin32 is available for DOCX to PDF conversion") from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    document = None
    try:
        document = word.Documents.Open(
            FileName=str(source), ConfirmConversions=False, ReadOnly=True,
            AddToRecentFiles=False, Visible=False,
        )
        document.SaveAs2(str(target), FileFormat=17)
    finally:
        if document is not None:
            document.Close(False)
        word.Quit()
    if not target.is_file():
        raise RuntimeError("Word did not produce the visual PDF")
    return target


def prepare_visual_pdf(source: str | Path, output_dir: str | Path) -> dict:
    """Return an original-page PDF for the separately authorized visual review."""
    source, output_dir = Path(source).resolve(), Path(output_dir).resolve()
    if source.suffix.lower() not in {".pdf", ".docx"} or not source.is_file():
        raise ValueError("A readable PDF or DOCX report is required for visual review")
    output_dir.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".pdf":
        pdf = source
    else:
        pdf = output_dir / "visual-source.pdf"
        if not pdf.is_file() or pdf.stat().st_mtime < source.stat().st_mtime:
            from extract_report import convert_office
            converted, _note = convert_office(source, output_dir, "pdf")
            if converted is None:
                _convert_docx_with_word(source, pdf)
            else:
                converted.replace(pdf)
    with pymupdf.open(pdf) as document:
        if document.needs_pass or document.page_count < 1:
            raise ValueError("Visual PDF is empty or encrypted")
        page_count = document.page_count
    return {"pdf": str(pdf), "page_count": page_count, "source_sha256": file_digest(source)}


def file_digest(path: Path) -> str:
    """Hash a file without retaining its bytes in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare_report(source: str | Path, output_dir: str | Path) -> dict:
    """Desensitize a PDF/DOCX and return its checked PDF and local provenance.

    A valid prior preparation in the same directory can be reused. Exceptions
    stop the text workflow before any model request. The original document is
    kept local and used only by the separately authorized visual review.
    """
    source, output_dir = Path(source).resolve(), Path(output_dir).resolve()
    if source.suffix.lower() not in {".pdf", ".docx"} or not source.is_file():
        raise ValueError("A readable PDF or DOCX report is required")
    output_dir.mkdir(parents=True, exist_ok=True)
    original_sha = file_digest(source)
    record_path = output_dir / "preparation.json"
    if record_path.is_file():
        record = json.loads(record_path.read_text(encoding="utf-8"))
        prepared = Path(record.get("pdf", ""))
        if (record.get("preparation_version") == PREPARATION_VERSION
                and record.get("source_sha256") == original_sha and prepared.is_file()
                and file_digest(prepared) == record.get("pdf_sha256")):
            return record
    scripts = Path(__file__).resolve().parent
    stage = output_dir / ("prepare-" + uuid.uuid4().hex)
    stage.mkdir()
    sanitized = stage / ("desensitized" + source.suffix.lower())
    command = [sys.executable, str(scripts / "desensitize_report.py"), str(source),
               "--out", str(sanitized), "--report", str(stage / "desensitize.json")]
    if source.suffix.lower() == ".pdf":
        command.append("--tables")
    result = subprocess.run(command, capture_output=True)
    if result.returncode or not sanitized.is_file():
        raise RuntimeError("Local desensitization failed; no model request was made")
    if sanitized.suffix == ".docx":
        from extract_report import convert_office
        pdf, note = convert_office(sanitized, stage, "pdf")
        if pdf is None:
            pdf = _convert_docx_with_word(sanitized, stage / (sanitized.stem + ".pdf"))
    else:
        pdf = sanitized
    with pymupdf.open(pdf) as document:
        if document.needs_pass or document.page_count < 1:
            raise ValueError("Prepared PDF is empty or encrypted")
        pages = document.page_count
        split_regions = 0  # Split label/value handling is part of the shared redactor.
        document.set_metadata({})
        document.del_xml_metadata()
        clean_pdf = stage / "metadata-cleared.pdf"
        document.save(clean_pdf, garbage=4, deflate=True)
    final = output_dir / "desensitized.pdf"
    clean_pdf.replace(final)
    record = {"preparation_version": PREPARATION_VERSION,
              "pdf": str(final), "source_sha256": original_sha,
              "pdf_sha256": file_digest(final), "page_count": pages,
              "split_label_regions": split_regions,
              "desensitization": json.loads((stage / "desensitize.json").read_text(encoding="utf-8"))}
    temp = record_path.with_suffix(".tmp")
    temp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(record_path)
    return record

def report_text(pdf_path: str | Path) -> tuple[str, int]:
    """Read every PDF page in layout order, falling back per page if text differs."""
    pdf_path = Path(pdf_path).resolve()
    with pymupdf.open(pdf_path) as pdf:
        native_pages = [page.get_text() for page in pdf]
        page_count = pdf.page_count

    with tempfile.TemporaryDirectory(prefix="audit-layout-text-") as temp_dir:
        layout_path = Path(temp_dir) / "layout.txt"
        command = [
            sys.executable, "-m", "pymupdf", "gettext", str(pdf_path),
            "-mode", "layout", "-fontsize", "0", "-output", str(layout_path),
        ]
        try:
            result = subprocess.run(command, capture_output=True)
        except OSError as exc:
            raise RuntimeError(f"PyMuPDF layout text extraction could not start: {exc}") from exc
        if result.returncode != 0 or not layout_path.is_file():
            raise RuntimeError("PyMuPDF layout text extraction failed")
        try:
            layout_text = layout_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise RuntimeError(f"PyMuPDF layout text output could not be read: {exc}") from exc

    layout_pages = layout_text.split("\f")
    if layout_pages and not layout_pages[-1].strip():
        layout_pages.pop()
    if len(layout_pages) != page_count:
        raise RuntimeError(
            f"PyMuPDF layout text page count mismatch: expected {page_count}, got {len(layout_pages)}"
        )

    def non_whitespace_counts(text: str) -> Counter[str]:
        return Counter(character for character in text if not character.isspace())

    pages = []
    for index, (native, layout) in enumerate(zip(native_pages, layout_pages), start=1):
        page_text = layout if non_whitespace_counts(native) == non_whitespace_counts(layout) else native
        pages.append(f"## Page {index}\n\n{page_text}")
    return "\n\n".join(pages), page_count
