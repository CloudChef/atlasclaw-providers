#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract deterministic image facts for photo-related rules.

The script never decides R30/R32. It reports what can be measured locally:
image count, dimensions, aspect ratio, SHA-256, repeated-image candidates, and
ratio outliers. Repetition and shape are evidence for the LLM to review, not
automatic classifications or audit decisions.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

import pymupdf


def scan_pdf(pdf_path: str | Path) -> dict[str, Any]:
    """Return per-image facts, exact duplicate groups and ratio outliers."""
    pdf_path = Path(pdf_path)
    with pymupdf.open(pdf_path) as document:
        page_count = document.page_count
        images: list[dict[str, Any]] = []
        by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for page_index in range(page_count):
            page = document[page_index]
            for image in page.get_images(full=True):
                xref = image[0]
                try:
                    extracted = document.extract_image(xref)
                except Exception:
                    continue
                digest = hashlib.sha256(extracted["image"]).hexdigest()
                width = int(extracted.get("width") or 0)
                height = int(extracted.get("height") or 0)
                record = {
                    "page": page_index + 1,
                    "xref": xref,
                    "width": width,
                    "height": height,
                    "ratio": round(width / height, 3) if height else None,
                    "sha256": digest,
                }
                images.append(record)
                by_hash[digest].append(record)

    duplicate_groups = [
        {"sha256": digest, "pages": [item["page"] for item in items], "count": len(items)}
        for digest, items in by_hash.items()
        if len(items) > 1
    ]
    ratios = [item["ratio"] for item in images if item["ratio"]]
    ratio_outliers = []
    if len(ratios) >= 4:
        median = statistics.median(ratios)
        ratio_outliers = [
            item for item in images
            if item["ratio"] and abs(item["ratio"] - median) > 0.15
        ]

    return {
        "pdf": str(pdf_path.resolve()),
        "page_count": page_count,
        "image_count": len(images),
        "images": images,
        "exact_duplicates": duplicate_groups,
        "ratio_median": round(statistics.median(ratios), 3) if ratios else None,
        "ratio_outliers": ratio_outliers,
    }


def to_markdown(facts: dict[str, Any]) -> str:
    """Render the facts as a compact material for the audit prompts."""
    lines = [
        "# 图片事实（本地确定性提取）",
        "",
        f"- 源 PDF：`{Path(facts['pdf']).name}`",
        f"- 总页数：{facts['page_count']}；图片对象数：{facts['image_count']}",
        f"- 照片比例中位数：{facts.get('ratio_median') or 'N/A'}",
        "",
        "> 以下只是本地图片尺寸/哈希候选事实，不是 R30/R32 的最终判定。包括频繁重复的页眉/logo 图，模型仍需结合页面内容判断是否为检测照片或复用照片。",
        "",
        "## 精确重复图片候选（包括页眉/logo；仍需结合页面内容判断）",
    ]
    if facts["exact_duplicates"]:
        for group in facts["exact_duplicates"]:
            pages = "、".join(f"第 {page} 页" for page in group["pages"])
            lines.append(f"- `{group['sha256'][:16]}`：{pages}（{group['count']} 次）")
    else:
        lines.append("- 无")
    lines += ["", "## 比例异常候选（仅候选，需确认是否为检测照片）"]
    if facts["ratio_outliers"]:
        for item in facts["ratio_outliers"]:
            lines.append(
                f"- 第 {item['page']} 页：{item['width']}×{item['height']}，比例 {item['ratio']}"
            )
    else:
        lines.append("- 无")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    import argparse
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Extract deterministic image facts from a PDF")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    facts = scan_pdf(args.pdf)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(facts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text = to_markdown(facts)
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(text, encoding="utf-8")
    if not args.json and not args.markdown:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
