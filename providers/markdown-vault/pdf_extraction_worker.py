"""Resource-limited local PDF text extraction worker for Markdown Vault."""

from __future__ import annotations

import json
import math
from pathlib import Path
import resource
import sys
from typing import Any

from pypdf import PdfReader


def _contains_raster_image(page: Any) -> bool:
    """Return whether a PDF page explicitly contains a raster or inline image."""
    return len(page.images) > 0


def _apply_resource_limits(timeout_seconds: float, max_result_bytes: int) -> None:
    """Limit CPU, address space, and output size before parsing untrusted PDF input."""
    cpu_seconds = max(math.ceil(timeout_seconds), 1)
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    if sys.platform.startswith("linux"):
        memory_bytes = 768 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_FSIZE, (max_result_bytes, max_result_bytes))


def _extract(
    input_path: Path,
    *,
    max_pages: int,
    max_characters: int,
) -> dict[str, Any]:
    """Extract page text and geometry into the provider's bounded JSON contract."""
    reader = PdfReader(str(input_path))
    if not reader.pages:
        return {
            "error": {
                "statusCode": 422,
                "code": "attachment_unextractable",
                "detail": "PDF attachment contains no pages",
            }
        }
    if len(reader.pages) > max_pages:
        return {
            "error": {
                "statusCode": 413,
                "code": "attachment_page_limit_exceeded",
                "detail": f"PDF attachment exceeds the {max_pages}-page limit",
            }
        }
    pages: list[dict[str, Any]] = []
    total_characters = 0
    for page_number, page in enumerate(reader.pages, start=1):
        extracted = str(page.extract_text() or "").strip()
        total_characters += len(extracted)
        if total_characters > max_characters:
            return {
                "error": {
                    "statusCode": 413,
                    "code": "attachment_markdown_too_large",
                    "detail": "Converted attachment Markdown exceeds the configured size limit",
                }
            }
        pages.append(
            {
                "pageNumber": page_number,
                "text": extracted,
                "width": float(page.mediabox.width),
                "height": float(page.mediabox.height),
                "hasRasterImage": _contains_raster_image(page),
            }
        )
    return {"pages": pages}


def main(argv: list[str] | None = None) -> int:
    """Run one isolated extraction and write a structured result for the parent process."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 6:
        return 2
    input_path = Path(arguments[0])
    result_path = Path(arguments[1])
    try:
        max_pages = int(arguments[2])
        max_characters = int(arguments[3])
        timeout_seconds = float(arguments[4])
        max_result_bytes = int(arguments[5])
        _apply_resource_limits(timeout_seconds, max_result_bytes)
        payload = _extract(
            input_path,
            max_pages=max_pages,
            max_characters=max_characters,
        )
    except Exception as exc:
        payload = {
            "error": {
                "statusCode": 422,
                "code": "attachment_unextractable",
                "detail": f"Local PDF extraction failed: {type(exc).__name__}",
            }
        }
    result_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
