#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract text, tables and page images from PDF/DOCX for report auditing.

Examples:
    python extract_report.py report.pdf --out .audit/report
    python extract_report.py report.docx --out .audit/report --dpi 200
    python extract_report.py a.pdf b.docx --out .audit --no-images

Output per input file (under <out>/<stem>/):
    manifest.json         summary: hash, page count, text layer, images, docx info
    document.md           PDF: page-separated text; DOCX: paragraphs + tables
    pdf_pages.md          DOCX only, page text from LibreOffice PDF conversion
    pages/page-001.png    rendered page images (PDF, or DOCX after conversion)
    tables.md             tables detected in PDF text layer
    media/                DOCX embedded images

Dependencies:
    PDF: PyMuPDF (pip install pymupdf)
    DOCX: standard library only; LibreOffice optional for page rendering
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
APP_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}"
REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
DRAWING_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
REL_ATTR_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
VML_NS = "{urn:schemas-microsoft-com:vml}"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def md_escape(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\r", " ").replace("\n", "<br>").replace("|", "\\|").strip()


def md_table(rows: list[list[Any]]) -> str:
    rows = [[md_escape(cell) for cell in row] for row in rows if row]
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows[1:])
    return "\n".join(lines)


def reset_generated(outdir: Path) -> None:
    """Remove artifacts from a previous extraction of this output directory.

    Only touches files/directories this script creates, so unrelated content in
    the parent output root is never deleted.
    """
    for name in ("document.md", "pdf_pages.md", "tables.md", "lines.md", "pdf_lines.md", "manifest.json"):
        target = outdir / name
        if target.is_file():
            target.unlink()
    for name in ("pages", "media"):
        target = outdir / name
        if target.is_dir():
            shutil.rmtree(target)


def dir_owned_by_other(outdir: Path, source: Path) -> bool:
    """True when outdir holds output for a different source file."""
    manifest = outdir / "manifest.json"
    if manifest.is_file():
        try:
            previous = json.loads(manifest.read_text(encoding="utf-8")).get("source")
        except (OSError, ValueError):
            return True
        if not previous:
            return True
        try:
            return Path(previous).resolve() != source.resolve()
        except OSError:
            return True
    if outdir.exists():
        try:
            return any(outdir.iterdir())
        except OSError:
            return True
    return False


def choose_output_dir(out_root: Path, source: Path) -> Path:
    candidate = out_root / source.stem
    if not dir_owned_by_other(candidate, source):
        return candidate
    suffix = source.suffix.lower().lstrip(".")
    candidate = out_root / f"{source.stem}-{suffix}"
    counter = 2
    while dir_owned_by_other(candidate, source):
        candidate = out_root / f"{source.stem}-{suffix}-{counter}"
        counter += 1
    return candidate


def find_soffice() -> str | None:
    candidates = [
        shutil.which("soffice"),
        shutil.which("libreoffice"),
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        "/usr/bin/soffice",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    return None


def convert_office(path: Path, outdir: Path, target: str) -> tuple[Path | None, str]:
    """Convert with LibreOffice. Returns (output, note)."""
    exe = find_soffice()
    if not exe:
        return None, "LibreOffice (soffice) not found; conversion skipped"
    profile = tempfile.mkdtemp(prefix="lo-profile-")
    cmd = [
        exe,
        f"-env:UserInstallation={Path(profile).as_uri()}",
        "--headless",
        "--convert-to",
        target,
        "--outdir",
        str(outdir),
        str(path),
    ]
    suffix = "." + target.split(":")[0]
    output = outdir / (path.stem + suffix)
    if output.exists():
        output.unlink()
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True)
    except OSError as exc:
        return None, f"LibreOffice conversion failed: {exc}"
    if proc.returncode != 0 or not output.exists():
        detail = (proc.stderr or proc.stdout or b"").decode("utf-8", errors="replace")[:300]
        return None, f"LibreOffice conversion failed: {detail}"
    return output, ""


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
def load_pymupdf():
    try:
        import pymupdf  # type: ignore

        return pymupdf
    except ImportError:
        try:
            import fitz  # type: ignore

            return fitz
        except ImportError as exc:
            raise SystemExit(
                "PyMuPDF is required for PDF extraction. Install with: pip install pymupdf"
            ) from exc


def extract_pdf(
    path: Path,
    outdir: Path,
    *,
    dpi: int = 150,
    render: bool = True,
    max_pages: int | None = None,
    extract_tables: bool = True,
    text_filename: str = "document.md",
    page_dir_name: str = "pages",
    lines_filename: str = "lines.md",
) -> dict[str, Any]:
    pymupdf = load_pymupdf()
    doc = pymupdf.open(str(path))
    page_dir = outdir / page_dir_name
    if render:
        page_dir.mkdir(parents=True, exist_ok=True)

    pages: list[dict[str, Any]] = []
    md_lines: list[str] = [f"# PDF: {path.name}", ""]
    table_lines: list[str] = [f"# Tables: {path.name}", ""]
    index_lines: list[str] = [
        f"# Line index: {path.name}",
        "",
        "> L001 = first text line on the page, counted from top to bottom in reading order.",
        "",
    ]

    limit = len(doc) if max_pages is None else min(len(doc), max_pages)
    for index in range(limit):
        page = doc[index]
        text = page.get_text("text", sort=True) or ""
        stripped = text.strip()
        image_count = len(page.get_images(full=True))
        pages.append(
            {
                "page": index + 1,
                "chars": len(stripped),
                "text_layer": len(stripped) >= 20,
                "images": image_count,
            }
        )
        md_lines.append(f"## Page {index + 1}")
        md_lines.append("")
        md_lines.append(stripped if stripped else "<!-- NO TEXT LAYER: inspect page image or OCR -->")
        md_lines.append("")

        page_text_lines = [line for line in stripped.splitlines() if line.strip()]
        index_lines.append(f"## Page {index + 1}")
        if page_text_lines:
            for line_no, line in enumerate(page_text_lines, start=1):
                index_lines.append(f"L{line_no:03d} | {line}")
        else:
            index_lines.append("<!-- no text layer: cite the page image region -->")
        index_lines.append("")

        if render:
            pixmap = page.get_pixmap(dpi=dpi)
            pixmap.save(str(page_dir / f"page-{index + 1:03d}.png"))

        if extract_tables and len(stripped) >= 20:
            try:
                found = page.find_tables()
            except Exception:
                found = None
            if found is not None:
                for table_index, table in enumerate(found.tables, start=1):
                    try:
                        rows = table.extract()
                    except Exception:
                        continue
                    if not rows:
                        continue
                    table_lines.append(f"## Page {index + 1} - Table {table_index}")
                    table_lines.append("")
                    table_lines.append(md_table(rows))
                    table_lines.append("")

    page_count = doc.page_count
    metadata = {
        str(key): (None if value is None else str(value))
        for key, value in (doc.metadata or {}).items()
    }
    doc.close()

    write_text(outdir / text_filename, "\n".join(md_lines))
    write_text(outdir / lines_filename, "\n".join(index_lines))
    if extract_tables:
        write_text(outdir / "tables.md", "\n".join(table_lines))

    empty_pages = [p["page"] for p in pages if not p["text_layer"]]
    return {
        "source": str(path.resolve()),
        "type": "pdf",
        "sha256": sha256_file(path),
        "size": path.stat().st_size,
        "page_count": page_count,
        "pages_extracted": limit,
        "pages": pages,
        "has_text_layer": not empty_pages,
        "empty_text_pages": empty_pages,
        "metadata": metadata,
        "render_dpi": dpi if render else None,
        "text_file": text_filename,
        "lines_file": lines_filename,
        "line_numbering": "page visual text lines, 1-based (L001 = first text line on the page)",
        "tables_file": "tables.md" if extract_tables else None,
    }


# --------------------------------------------------------------------------- #
# DOCX
# --------------------------------------------------------------------------- #
def docx_relationships(archive: zipfile.ZipFile) -> dict[str, str]:
    if "word/_rels/document.xml.rels" not in archive.namelist():
        return {}
    try:
        root = ET.fromstring(archive.read("word/_rels/document.xml.rels"))
    except ET.ParseError:
        return {}
    return {
        rel.get("Id", ""): rel.get("Target", "")
        for rel in root.findall(REL_NS + "Relationship")
        if rel.get("Id")
    }


def docx_part_name(target: str) -> str:
    """Normalize an OPC relationship target to a package part name."""
    target = target.lstrip("/")
    return target if target.startswith("word/") else f"word/{target}"


def docx_referenced_parts(root: ET.Element, relationships: dict[str, str]) -> set[str]:
    referenced: set[str] = set()
    for node in root.iter():
        rel_id = None
        if node.tag in (WORD_NS + "headerReference", WORD_NS + "footerReference"):
            rel_id = node.get(REL_ATTR_NS + "id")
        elif node.tag == DRAWING_NS + "blip":
            rel_id = node.get(REL_ATTR_NS + "embed")
        elif node.tag == VML_NS + "imagedata":
            rel_id = node.get(REL_ATTR_NS + "id")
        target = relationships.get(rel_id or "")
        if target:
            referenced.add(docx_part_name(target))
    return referenced


def docx_image_names(element: ET.Element, relationships: dict[str, str]) -> list[str]:
    names: list[str] = []
    for node in element.iter():
        rel_id = None
        if node.tag == DRAWING_NS + "blip":
            rel_id = node.get(REL_ATTR_NS + "embed")
        elif node.tag == VML_NS + "imagedata":
            rel_id = node.get(REL_ATTR_NS + "id")
        if rel_id:
            target = relationships.get(rel_id, rel_id)
            names.append(Path(target).name)
    return names


def docx_paragraph_text(paragraph: ET.Element, relationships: dict[str, str] | None = None) -> str:
    parts: list[str] = []
    for node in paragraph.iter():
        if node.tag == WORD_NS + "t" and node.text:
            parts.append(node.text)
        elif node.tag == WORD_NS + "tab":
            parts.append("\t")
        elif node.tag in (WORD_NS + "br", WORD_NS + "cr"):
            parts.append("\n")
    text = "".join(parts)
    images = docx_image_names(paragraph, relationships or {})
    if images:
        text = f"{text} {' '.join(f'[图片: {name}]' for name in images)}".strip()
    return text


def docx_cell_text(cell: ET.Element, relationships: dict[str, str]) -> str:
    texts = [docx_paragraph_text(p, relationships).strip() for p in cell.findall(WORD_NS + "p")]
    return "<br>".join(t for t in texts if t)


def docx_table_rows(table: ET.Element, relationships: dict[str, str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in table.findall(WORD_NS + "tr"):
        rows.append([docx_cell_text(cell, relationships) for cell in row.findall(WORD_NS + "tc")])
    return rows


def docx_part_text(xml_bytes: bytes) -> str:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return ""
    return "\n".join(
        text for text in (docx_paragraph_text(p).strip() for p in root.iter(WORD_NS + "p")) if text
    )


def docx_block_elements(container: ET.Element):
    """Yield body-level paragraphs/tables, looking through content controls."""
    for child in container:
        if child.tag in (WORD_NS + "p", WORD_NS + "tbl"):
            yield child
        elif child.tag in (WORD_NS + "sdt", WORD_NS + "sdtContent", WORD_NS + "customXml"):
            yield from docx_block_elements(child)


def extract_docx(
    path: Path,
    outdir: Path,
    *,
    dpi: int = 150,
    render: bool = True,
    max_pages: int | None = None,
    convert: bool = True,
) -> dict[str, Any]:
    outdir.mkdir(parents=True, exist_ok=True)
    media_dir = outdir / "media"
    media_dir.mkdir(exist_ok=True)

    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if "word/document.xml" not in names:
            raise SystemExit(f"Not a valid DOCX (missing word/document.xml): {path}")
        root = ET.fromstring(archive.read("word/document.xml"))
        body = root.find(WORD_NS + "body")
        relationships = docx_relationships(archive)
        referenced_parts = docx_referenced_parts(root, relationships)

        blocks: list[str] = [f"# DOCX: {path.name}", ""]
        line_index: list[str] = [
            f"# Line index: {path.name}",
            "",
            "> DOCX has no fixed visual line numbers. P### = paragraph index; T##-R## = table row.",
            "> Convert to PDF (pdf_lines.md) for page visual line numbers.",
            "",
        ]
        paragraph_count = 0
        table_count = 0
        if body is not None:
            for child in docx_block_elements(body):
                if child.tag == WORD_NS + "p":
                    text = docx_paragraph_text(child, relationships).strip()
                    if text:
                        blocks.append(text)
                        paragraph_count += 1
                        line_index.append(f"P{paragraph_count:03d} | {text}")
                elif child.tag == WORD_NS + "tbl":
                    rows = docx_table_rows(child, relationships)
                    if rows:
                        blocks.append(md_table(rows))
                        blocks.append("")
                        table_count += 1
                        for row_no, row in enumerate(rows, start=1):
                            cells = " | ".join(md_escape(cell) for cell in row)
                            line_index.append(f"T{table_count:02d}-R{row_no:02d} | {cells}")

        headers = []
        footers = []
        for name in names:
            if re.fullmatch(r"word/header\d*\.xml", name):
                headers.append(
                    {
                        "part": name,
                        "text": docx_part_text(archive.read(name)),
                        "referenced": name in referenced_parts,
                    }
                )
            elif re.fullmatch(r"word/footer\d*\.xml", name):
                footers.append(
                    {
                        "part": name,
                        "text": docx_part_text(archive.read(name)),
                        "referenced": name in referenced_parts,
                    }
                )

        media_files = []
        for name in names:
            if name.startswith("word/media/"):
                target = media_dir / Path(name).name
                with archive.open(name) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                media_files.append(
                    {
                        "part": name,
                        "saved_as": str(target.relative_to(outdir)),
                        "referenced": name in referenced_parts,
                    }
                )

        notes = []
        for name in ("word/footnotes.xml", "word/endnotes.xml"):
            if name in names:
                text = docx_part_text(archive.read(name))
                if text:
                    notes.append({"part": name, "text": text})

        orphaned_parts = [
            entry["part"]
            for entry in [*headers, *footers, *media_files]
            if not entry["referenced"]
        ]

        declared_pages = None
        if "docProps/app.xml" in names:
            try:
                app = ET.fromstring(archive.read("docProps/app.xml"))
                pages_node = app.find(APP_NS + "Pages")
                if pages_node is not None and pages_node.text and pages_node.text.isdigit():
                    declared_pages = int(pages_node.text)
            except ET.ParseError:
                pass

    write_text(outdir / "document.md", "\n".join(blocks))
    write_text(outdir / "lines.md", "\n".join(line_index))

    manifest: dict[str, Any] = {
        "source": str(path.resolve()),
        "type": "docx",
        "sha256": sha256_file(path),
        "size": path.stat().st_size,
        "declared_page_count": declared_pages,
        "page_count": declared_pages,
        "page_count_source": "docProps/app.xml" if declared_pages else "unknown",
        "converted_pdf": None,
        "conversion_note": "",
        "lines_file": "lines.md",
        "line_numbering": "P### paragraph / T##-R## table row; pdf_lines.md for visual lines after conversion",
        "docx": {
            "paragraphs": paragraph_count,
            "tables": table_count,
            "headers": headers,
            "footers": footers,
            "notes": notes,
            "media": media_files,
            "orphaned_parts": orphaned_parts,
        },
    }

    if convert:
        pdf_path, note = convert_office(path, outdir, "pdf")
        manifest["conversion_note"] = note
        if pdf_path is not None:
            manifest["converted_pdf"] = pdf_path.name
            pdf_manifest = extract_pdf(
                pdf_path,
                outdir,
                dpi=dpi,
                render=render,
                max_pages=max_pages,
                text_filename="pdf_pages.md",
                lines_filename="pdf_lines.md",
            )
            manifest["pdf_pages"] = {
                "page_count": pdf_manifest["page_count"],
                "has_text_layer": pdf_manifest["has_text_layer"],
                "empty_text_pages": pdf_manifest["empty_text_pages"],
                "pages": pdf_manifest["pages"],
                "lines_file": "pdf_lines.md",
            }
            manifest["page_count"] = pdf_manifest["page_count"]
            manifest["page_count_source"] = "libreoffice"
    elif not find_soffice():
        manifest["conversion_note"] = "conversion disabled (--no-convert)"

    return manifest


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def process_file(
    path: Path,
    out_root: Path,
    *,
    dpi: int,
    render: bool,
    max_pages: int | None,
    convert: bool,
) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"File not found: {path}")
    if path.suffix.lower() not in {".pdf", ".docx", ".doc"}:
        raise SystemExit(f"Unsupported file type: {path.suffix} (expected .pdf/.docx/.doc)")

    file_out = choose_output_dir(out_root, path)
    file_out.mkdir(parents=True, exist_ok=True)
    reset_generated(file_out)

    if path.suffix.lower() == ".doc":
        converted, note = convert_office(path, file_out, "docx")
        if converted is None:
            raise SystemExit(
                f"Legacy .doc must be converted to .docx first. {note}\n"
                f"Try: soffice --headless --convert-to docx \"{path}\""
            )
        manifest = extract_docx(
            converted, file_out, dpi=dpi, render=render, max_pages=max_pages, convert=convert
        )
        manifest["converted_from"] = str(path.resolve())
        manifest["converted_docx"] = str(converted.resolve())
        manifest["converted_docx_sha256"] = manifest["sha256"]
        manifest["source"] = str(path.resolve())
        manifest["sha256"] = sha256_file(path)
        manifest["size"] = path.stat().st_size
        manifest["original_sha256"] = manifest["sha256"]
    elif path.suffix.lower() == ".pdf":
        manifest = extract_pdf(
            path, file_out, dpi=dpi, render=render, max_pages=max_pages
        )
    else:
        manifest = extract_docx(
            path, file_out, dpi=dpi, render=render, max_pages=max_pages, convert=convert
        )

    manifest["output_dir"] = str(file_out.resolve())
    write_text(file_out / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Extract PDF/DOCX text, tables and page images for test-report auditing."
    )
    parser.add_argument("files", nargs="+", help="PDF/DOCX files to extract")
    parser.add_argument("--out", default=".audit", help="Output root directory (default: .audit)")
    parser.add_argument("--dpi", type=int, default=150, help="Page render DPI (default: 150)")
    parser.add_argument("--no-images", action="store_true", help="Do not render page images")
    parser.add_argument("--no-tables", action="store_true", help="Skip PDF table detection")
    parser.add_argument("--no-convert", action="store_true", help="Do not convert DOCX to PDF")
    parser.add_argument("--max-pages", type=int, default=None, help="Limit pages (debug only)")
    args = parser.parse_args()

    out_root = Path(args.out)
    render = not args.no_images

    for raw in args.files:
        path = Path(raw)
        try:
            manifest = process_file(
                path,
                out_root,
                dpi=args.dpi,
                render=render,
                max_pages=args.max_pages,
                convert=not args.no_convert,
            )
        except SystemExit:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[ERROR] {path}: {exc}", file=sys.stderr)
            continue

        page_count = manifest.get("page_count")
        empty = manifest.get("empty_text_pages") or (manifest.get("pdf_pages") or {}).get(
            "empty_text_pages", []
        )
        print(f"[OK] {path.name}")
        print(f"     type={manifest['type']} pages={page_count} out={manifest['output_dir']}")
        if empty:
            print(f"     pages without text layer: {empty} -> inspect page images or OCR")
        if manifest.get("conversion_note"):
            print(f"     note: {manifest['conversion_note']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
