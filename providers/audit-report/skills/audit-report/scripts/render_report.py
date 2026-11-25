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
from datetime import datetime
from pathlib import Path

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
LIST_RE = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")
IMAGE_RE = re.compile(r"^!\[(.*?)\]\((.+?)\)$")


def inline(text: str) -> str:
    """Render inline Markdown (code, bold, links) after escaping HTML."""
    text = html.escape(text, quote=False)
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


def render_table(lines: list[str]) -> str:
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
    if len(rows) < 2:
        return ""
    header, body = rows[0], rows[2:]
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
    return (
        '<figure class="evidence">'
        f'<img src="data:{mime};base64,{encoded}" alt="{html.escape(alt)}">'
        f"<figcaption>{inline(alt)}</figcaption>"
        "</figure>"
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
            body.append(render_table(table_lines))
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


CSS = """
:root {
  --ink: #1d2939;
  --muted: #475467;
  --line: #d0d5dd;
  --blue: #175cd3;
  --red: #b42318;
  --orange: #b54708;
  --green: #067647;
  --bg: #eef2f6;
}
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "Source Han Sans SC", sans-serif;
  font-size: 14px;
  line-height: 1.75;
}
.page {
  max-width: 1120px;
  margin: 28px auto;
  padding: 52px 58px 44px;
  background: #fff;
  border-radius: 6px;
  box-shadow: 0 10px 30px rgba(16, 24, 40, .10);
}
h1, h2, h3, h4 { color: #101828; line-height: 1.35; }
h1 {
  margin: 0 0 24px;
  padding-bottom: 14px;
  font-size: 30px;
  border-bottom: 2px solid #101828;
  letter-spacing: .5px;
}
h2 {
  margin: 38px 0 14px;
  padding-left: 12px;
  font-size: 21px;
  border-left: 5px solid var(--blue);
}
h3 {
  margin: 26px 0 10px;
  font-size: 16px;
}
h3.finding {
  padding: 10px 14px;
  background: #f8fafc;
  border: 1px solid #e4e7ec;
  border-left: 5px solid var(--blue);
  border-radius: 4px;
}
p { margin: 8px 0; }
strong { color: #101828; }
code {
  padding: 1px 5px;
  background: #f2f4f7;
  border: 1px solid #eaecf0;
  border-radius: 4px;
  font-family: Consolas, "Courier New", monospace;
  font-size: 12.5px;
}
hr { margin: 30px 0; border: 0; border-top: 1px solid var(--line); }
blockquote {
  margin: 16px 0;
  padding: 10px 16px;
  background: #f9fafb;
  border-left: 4px solid #98a2b3;
  color: var(--muted);
}
blockquote p { margin: 4px 0; }
.verdict {
  margin: 18px 0 22px;
  padding: 14px 18px;
  border-radius: 6px;
  font-size: 18px;
  font-weight: 700;
}
.verdict-fail { background: #fef3f2; border-left: 7px solid var(--red); color: var(--red); }
.verdict-pass { background: #ecfdf3; border-left: 7px solid var(--green); color: var(--green); }
.verdict-unknown { background: #fffaeb; border-left: 7px solid var(--orange); color: var(--orange); }
.table-wrap { width: 100%; margin: 14px 0 22px; overflow-x: auto; }
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  background: #fff;
}
th, td {
  padding: 8px 10px;
  border: 1px solid var(--line);
  text-align: left;
  vertical-align: top;
}
th { background: #f2f4f7; color: #344054; font-weight: 700; white-space: nowrap; }
tbody tr:nth-child(even) { background: #fcfcfd; }
tbody tr:hover { background: #f8fafc; }
.sev, .result {
  display: inline-block;
  padding: 1px 9px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}
.sev-a { background: #fee4e2; color: var(--red); }
.sev-b { background: #fef0c7; color: var(--orange); }
.sev-c { background: #d1e9ff; color: var(--blue); }
.result-pass { background: #dcfae6; color: var(--green); }
.result-fail { background: #fee4e2; color: var(--red); }
.result-unknown { background: #f2f4f7; color: #475467; }
.result-na { background: #f2f4f7; color: #667085; }
ul, ol { margin: 8px 0 14px; padding-left: 24px; }
li { margin: 4px 0; }
li > ul, li > ol { margin: 4px 0; }
figure.evidence {
  margin: 14px 0 18px;
  padding: 10px;
  background: #fcfcfd;
  border: 1px solid #e4e7ec;
  border-radius: 6px;
}
figure.evidence img {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 0 auto;
  border: 1px solid #d0d5dd;
}
figure.evidence figcaption {
  margin-top: 8px;
  color: #475467;
  font-size: 12px;
  text-align: center;
}
.missing-evidence {
  padding: 8px 12px;
  color: var(--red);
  background: #fef3f2;
  border-left: 4px solid var(--red);
}
footer {
  margin-top: 42px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
  color: #667085;
  font-size: 12px;
  text-align: right;
}
@media print {
  body { background: #fff; }
  .page { max-width: none; margin: 0; padding: 0; box-shadow: none; border-radius: 0; }
  h2 { page-break-after: avoid; }
  h3.finding { page-break-after: avoid; }
  tr { page-break-inside: avoid; }
  .table-wrap { overflow: visible; }
  @page { size: A4; margin: 14mm; }
}
"""


def build_html(title: str, body: str, footer: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
<main class="page">
{body}
<footer>{html.escape(footer)}</footer>
</main>
</body>
</html>
"""


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
