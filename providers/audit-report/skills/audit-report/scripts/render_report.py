#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render an audit-report Markdown file into a standalone HTML report.

The Markdown file is the validation source (checked by check_coverage.py);
this script produces the human-facing HTML deliverable.

Usage:
    python render_report.py <audit-report.md> [--out report.html] [--title "..."]
"""

from __future__ import annotations

import argparse
import base64
import html
import mimetypes
import re
import sys
from string import Template
from datetime import datetime
from pathlib import Path

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
LIST_RE = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")
IMAGE_RE = re.compile(r"^!\[(.*?)\]\((.+?)\)$")
SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = SCRIPT_DIR.parent / "references" / "report"


def load_template(name: str) -> str:
    """Load a trusted UTF-8 presentation template beside this skill."""
    path = TEMPLATE_DIR / name
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Unable to load report template {path}: {exc}") from exc


def inline(text: str) -> str:
    """Render inline Markdown (code, bold, links) after escaping HTML."""
    # Inline links are emitted with a quoted href below, so escape quotes in
    # the source before inserting any text into HTML attributes.
    text = html.escape(text, quote=True)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', text)
    return text.replace("&lt;br&gt;", "<br>")


def cell_html(cell: str) -> str:
    text = cell.strip()
    css = ""
    if text in {"A", "B", "C"}:
        css = f"sev sev-{text.lower()}"
    elif re.match(r"^[ABC] · ", text):
        css = f"sev sev-{text[0].lower()}"
    elif text == "通过":
        css = "result result-pass"
    elif text == "不通过":
        css = "result result-fail"
    elif text == "不适用":
        css = "result result-na"
    inner = inline(text)
    return f'<span class="{css}">{inner}</span>' if css else inner


def render_table(lines: list[str], base_dir: Path | None = None) -> str:
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
    if len(rows) < 2:
        return ""
    header, body = rows[0], rows[2:]
    finding_table = "复核结果" in header and any(label in header for label in ("问题摘要", "问题标题"))
    rule_table = all(label in header for label in ("检查项", "结果", "证据位置/说明"))
    if finding_table or rule_table or len(header) > 6:
        out = []
        field_row_template = Template(load_template("field-row.html"))
        check_point_template = Template(load_template("check-point.html"))
        for number, row in enumerate(body, 1):
            if len(row) != len(header):
                raise ValueError("A report table has mismatched header and cell counts")
            values = dict(zip(header, row))
            fid = next((cell.strip("` ") for cell in row if re.fullmatch(r"`?F-(?:\d+-\d+|\d{2,})`?", cell)), None)
            title = values.get("问题摘要", values.get("问题标题", values.get("检查项", " / ".join(row[:2]))))
            identity = fid or row[0] or str(number)
            kind = "finding-point" if finding_table else "rule-point" if rule_table else "record-point"
            field_rows = "\n".join(
                field_row_template.substitute(
                    label=inline(label), value=cell_html(value),
                )
                for label, value in zip(header, row)
            )
            evidence_markup = ""
            if finding_table and fid and base_dir is not None:
                candidates = [base_dir / "evidence" / f"{fid}.png", *sorted((base_dir / "evidence").glob(f"{fid}-p*.png"))]
                seen: set[bytes] = set()
                for path in candidates:
                    if path.is_file():
                        data = path.read_bytes()
                        if data not in seen:
                            seen.add(data)
                            page = re.search(r"-p(\d+)\.png$", path.name)
                            label = f"{fid} · PDF物理页 {page.group(1)}" if page else f"{fid} · {values.get('页码', '报告原文')}"
                            evidence_markup += render_image(label, str(path), base_dir)
                if not seen:
                    evidence_markup = Template(load_template("missing-evidence.html")).substitute(
                        finding_id=inline(fid),
                    )
            out.append(check_point_template.substitute(
                kind=kind, identity=inline(identity), title=inline(title), rows=field_rows,
                evidence=evidence_markup,
            ))
        return "\n".join(out)
    out = ['<div class="table-wrap"><table>', "<thead><tr>"]
    out.extend(f"<th>{inline(cell)}</th>" for cell in header)
    out.append("</tr></thead><tbody>")
    for row in body:
        out.append("<tr>" + "".join(f"<td>{cell_html(cell)}</td>" for cell in row) + "</tr>")
    out.append("</tbody></table></div>")
    return "\n".join(out)


def render_list(lines: list[str], start: int) -> tuple[str, int]:
    first = LIST_RE.match(lines[start])
    base = len(first.group(1)) if first else 0
    tag = "ol" if first and first.group(2).endswith(".") else "ul"
    out = [f"<{tag}>"]
    index = start
    while index < len(lines):
        match = LIST_RE.match(lines[index])
        if not match:
            break
        indent = len(match.group(1))
        if indent != base:
            break
        item_tag = "ol" if match.group(2).endswith(".") else "ul"
        if item_tag != tag:
            break
        text = match.group(3)
        index += 1
        item = f"<li>{inline(text)}"
        if index < len(lines):
            nested = LIST_RE.match(lines[index])
            if nested and len(nested.group(1)) > base:
                sub, index = render_list(lines, index)
                item += sub
        item += "</li>"
        out.append(item)
    out.append(f"</{tag}>")
    return "\n".join(out), index


def render_quote(lines: list[str], start: int) -> tuple[str, int]:
    out = ["<blockquote>"]
    index = start
    while index < len(lines) and lines[index].lstrip().startswith(">"):
        text = lines[index].lstrip()[1:].lstrip()
        out.append(f"<p>{inline(text)}</p>")
        index += 1
    out.append("</blockquote>")
    return "\n".join(out), index


def render_paragraph(lines: list[str], start: int) -> tuple[str, int]:
    buffer: list[str] = []
    index = start
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            break
        if (
            HEADING_RE.match(line)
            or line.lstrip().startswith("|")
            or LIST_RE.match(line)
            or line.lstrip().startswith(">")
            or line.strip() == "---"
        ):
            break
        buffer.append(line.strip())
        index += 1
    text = " ".join(buffer)
    css = ""
    if text.startswith("**总评："):
        if "不通过" in text:
            css = ' class="verdict verdict-fail"'
        elif "通过" in text:
            css = ' class="verdict verdict-pass"'
        else:
            css = ' class="verdict verdict-unknown"'
    return f"<p{css}>{inline(text)}</p>", index


def strip_sections(markdown: str, keywords: list[str]) -> str:
    """Drop level-2 sections whose title contains any keyword."""
    out: list[str] = []
    skipping = False
    for line in markdown.splitlines():
        heading = re.match(r"^##\s+(.*)$", line)
        if heading:
            skipping = any(keyword in heading.group(1) for keyword in keywords)
            if skipping:
                continue
        if not skipping:
            out.append(line)
    return "\n".join(out)


def renumber_h2(markdown: str) -> str:
    """Renumber numbered level-2 headings sequentially."""
    out: list[str] = []
    counter = 0
    for line in markdown.splitlines():
        heading = re.match(r"^##\s+\d+\.\s*(.*)$", line)
        if heading:
            counter += 1
            line = f"## {counter}. {heading.group(1)}"
        out.append(line)
    return "\n".join(out)


def render_image(alt: str, src: str, base_dir: Path) -> str:
    path = Path(src)
    if not path.is_absolute():
        path = base_dir / path
    if not path.is_file():
        return f'<p class="missing-evidence">[缺少证据截图：{html.escape(src)}]</p>'
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return Template(load_template("evidence.html")).substitute(
        mime=html.escape(mime, quote=True), encoded=encoded,
        alt_attribute=html.escape(alt, quote=True), alt_text=inline(alt),
    )


def markdown_to_html(markdown: str, base_dir: Path) -> str:
    lines = markdown.splitlines()
    body: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line.strip() == "---":
            body.append("<hr>")
            index += 1
            continue
        heading = HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            title = heading.group(2)
            css = ' class="finding"' if level == 3 and title.startswith("F-") else ""
            body.append(f"<h{level}{css}>{inline(title)}</h{level}>")
            index += 1
            continue
        if line.lstrip().startswith("|"):
            table_lines = []
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                table_lines.append(lines[index])
                index += 1
            body.append(render_table(table_lines, base_dir))
            continue
        image = IMAGE_RE.match(line.strip())
        if image:
            body.append(render_image(image.group(1), image.group(2), base_dir))
            index += 1
            continue
        if LIST_RE.match(line):
            block, index = render_list(lines, index)
            body.append(block)
            continue
        if line.lstrip().startswith(">"):
            block, index = render_quote(lines, index)
            body.append(block)
            continue
        block, index = render_paragraph(lines, index)
        body.append(block)
    return "\n".join(body)


def build_html(title: str, body: str, footer: str) -> str:
    return Template(load_template("document.html")).substitute(
        title=html.escape(title), css=load_template("report.css"), body=body,
        footer=html.escape(footer),
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Render an audit-report Markdown file to standalone HTML.")
    parser.add_argument("source", help="Audit report Markdown file")
    parser.add_argument("--out", help="Output HTML path (default: same stem with .html)")
    parser.add_argument("--title", help="HTML title (default: source file stem)")
    parser.add_argument(
        "--delivery",
        action="store_true",
        help="Omit coverage table, observations and audit record; renumber sections",
    )
    args = parser.parse_args()

    source = Path(args.source)
    if not source.is_file():
        raise SystemExit(f"File not found: {source}")
    markdown = source.read_text(encoding="utf-8")
    if args.delivery:
        markdown = strip_sections(
            markdown, ["检查覆盖表", "补充观察", "审核记录"]
        )
        markdown = renumber_h2(markdown)
    body = markdown_to_html(markdown, source.parent)
    title = args.title or source.stem
    footer = f"由 audit-report 技能生成 · {datetime.now():%Y-%m-%d %H:%M}"
    output = Path(args.out) if args.out else source.with_suffix(".html")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_html(title, body, footer), encoding="utf-8")
    print(f"[OK] {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
