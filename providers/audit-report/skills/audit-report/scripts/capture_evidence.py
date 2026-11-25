#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Capture an evidence screenshot from a PDF page.

The report should cite page + section + surrounding text, not internal line
numbers. This helper crops the region around a search phrase (or a given
rectangle) and saves a PNG that can be embedded in the HTML report.

Examples:
    python capture_evidence.py report.pdf --page 427 --search "2025-12-11" \
        --out evidence/F-01.png --above 80 --below 120 --margin 50
    python capture_evidence.py report.pdf --page 406 --full --border \
        --out evidence/F-05.png
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pymupdf


def parse_rect(value: str) -> pymupdf.Rect:
    parts = [float(item) for item in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("rect must be x0,y0,x1,y1")
    return pymupdf.Rect(*parts)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Capture a PDF page region as evidence.")
    parser.add_argument("pdf", help="Source PDF")
    parser.add_argument("--page", type=int, required=True, help="1-based page number")
    parser.add_argument("--search", help="Text to locate on the page")
    parser.add_argument("--rect", type=parse_rect, help="Explicit clip rectangle in PDF points")
    parser.add_argument("--full", action="store_true", help="Capture the full page")
    parser.add_argument("--above", type=float, default=60, help="Points above the search match")
    parser.add_argument("--below", type=float, default=160, help="Points below the search match")
    parser.add_argument("--margin", type=float, default=50, help="Points left/right of the match")
    parser.add_argument("--dpi", type=int, default=160, help="Render DPI")
    parser.add_argument("--border", action="store_true", help="Draw a red border (for blank/edge evidence)")
    parser.add_argument("--out", required=True, help="Output PNG path")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.is_file():
        raise SystemExit(f"File not found: {pdf_path}")
    doc = pymupdf.open(pdf_path)
    if not 1 <= args.page <= doc.page_count:
        raise SystemExit(f"Page {args.page} out of range 1..{doc.page_count}")
    page = doc[args.page - 1]

    if args.full:
        clip = page.rect
    elif args.rect is not None:
        clip = args.rect
    elif args.search:
        hits = page.search_for(args.search)
        if not hits:
            raise SystemExit(f"Search text not found on page {args.page}: {args.search!r}")
        hit = hits[0]
        clip = pymupdf.Rect(
            max(page.rect.x0, hit.x0 - args.margin),
            max(page.rect.y0, hit.y0 - args.above),
            min(page.rect.x1, hit.x1 + args.margin),
            min(page.rect.y1, hit.y1 + args.below),
        )
    else:
        raise SystemExit("Provide --search, --rect, or --full")

    pixmap = page.get_pixmap(clip=clip, dpi=args.dpi)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    pixmap.save(str(output))

    meta = {
        "page": args.page,
        "clip": [round(clip.x0, 2), round(clip.y0, 2), round(clip.x1, 2), round(clip.y1, 2)],
        "search": args.search,
        "dpi": args.dpi,
    }
    output.with_suffix(output.suffix + ".json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if args.border:
        from PIL import Image, ImageDraw

        image = Image.open(output).convert("RGB")
        draw = ImageDraw.Draw(image)
        width, height = image.size
        draw.rectangle([2, 2, width - 3, height - 3], outline=(180, 35, 24), width=4)
        image.save(output)

    print(f"[OK] {output} page={args.page} clip=({clip.x0:.0f},{clip.y0:.0f},{clip.x1:.0f},{clip.y1:.0f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
