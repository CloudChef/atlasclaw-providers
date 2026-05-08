---
name: text
description: Use this skill when the user wants to create, generate, save, export, download, convert, format, clean, or localize plain text, TXT, Markdown/MD, or HTML file deliverables. This skill produces text-family artifacts such as .txt, .text, .md, .markdown, or .html files and exposes the final file for download.
license: MIT-0
source: https://clawhub.ai/ivangdavila/text
artifact_types:
  - text
  - txt
  - md
  - markdown
  - html
triggers:
  - create text
  - create text file
  - create txt
  - create txt file
  - create markdown
  - create markdown file
  - create md
  - create md file
  - create html
  - create html file
  - generate text
  - generate text file
  - generate txt
  - generate txt file
  - generate markdown
  - generate markdown file
  - generate md
  - generate md file
  - generate html
  - generate html file
  - save as text
  - save as txt
  - save as markdown
  - save as md
  - save as html
  - export text
  - export text file
  - export markdown
  - export markdown file
  - export html
  - export html file
  - download text
  - download markdown
  - download html
  - 创建文本
  - 创建文本文件
  - 创建 txt
  - 创建 txt 文件
  - 创建 markdown
  - 创建 markdown 文件
  - 创建 md
  - 创建 md 文件
  - 创建 html
  - 创建 html 文件
  - 生成文本
  - 生成文本文件
  - 生成 txt
  - 生成 txt 文件
  - 生成 markdown
  - 生成 markdown 文件
  - 生成 md
  - 生成 md 文件
  - 生成 html
  - 生成 html 文件
  - 保存为 txt
  - 保存成 txt
  - 保存为 md
  - 保存成 md
  - 保存为 markdown
  - 保存成 markdown
  - 保存为 html
  - 保存成 html
  - 导出文本
  - 导出文本文件
  - 导出 txt
  - 导出 txt 文件
  - 导出 markdown
  - 导出 markdown 文件
  - 导出 md
  - 导出 md 文件
  - 导出 html
  - 导出 html 文件
  - 下载文本
  - 下载文本文件
  - 下载 txt
  - 下载 txt 文件
  - 下载 markdown
  - 下载 markdown 文件
  - 下载 md
  - 下载 md 文件
  - 下载 html
  - 下载 html 文件
use_when:
  - User wants a text-family file deliverable in TXT, plain text, Markdown/MD, or HTML format.
  - User asks to create, generate, save, export, or download text-based content as a file.
  - User wants current context, generated content, notes, provided text, or transformed text saved as TXT, Markdown, or HTML.
  - User asks to clean, normalize, format, localize, or transform text-based content intended for TXT, Markdown, or HTML output.
  - User asks to convert simple text or Markdown content to HTML, or HTML/plain text content to Markdown/text when no dedicated document skill is required.
avoid_when:
  - User wants a PDF file; use the PDF skill.
  - User wants a DOCX/Word document; use the DOCX or word-docx skill.
  - User wants a PPT/PPTX slide deck; use the PPTX skill.
  - User wants an XLS/XLSX/CSV/TSV spreadsheet deliverable; use the XLSX skill.
  - User wants provider-specific workflows, tickets, approvals, or resource operations rather than a text file.
---

# AtlasClaw Workspace Output

When producing a user-facing `.txt`, `.md`, `.markdown`, or `.html` file:

1. Write only the final content under the current work_dir, preferably `exports/<descriptive-name>.<ext>` unless the user requested a safe relative filename.
2. Use UTF-8 text. For HTML, produce a complete standalone document when the user asks for an HTML file.
3. Expose the final file through the existing workspace download flow by passing its work_dir-relative path as `download_paths`.
4. Prefer writing a new output file instead of editing source files in place unless the user explicitly asks for an in-place edit.
5. Do not expose scripts, logs, caches, hidden files, intermediate files, or source documents as downloads.

## AtlasClaw Runtime Commands

Prefer `skill_read`, `skill_write`, and `skill_edit` for simple file operations. If a transformation needs shell features such as pipes, redirects, globs, or compound commands, run it through `bash -lc '<command>'` with explicitly named work_dir-relative files, or use a `python3 -c` command that reads and writes explicit paths. Do not read or print `.env`, key, token, cookie, or password files unless the user explicitly requests it and the output is redacted.

## Quick Reference

| Task | Load |
|------|------|
| Text cleanup, extraction, Markdown, or HTML shaping | `data.md` |
| Translation/localization for text output | `localization.md` |

---

## Universal Text Rules

### Encoding
- **Always verify encoding first:** `file -bi document.txt`
- **Normalize line endings:** `tr -d '\r'`
- **Remove BOM if present:** write a normalized copy instead of editing the source in place.

### Whitespace
- **Collapse multiple spaces:** `sed 's/[[:space:]]\+/ /g'`
- **Trim leading/trailing:** `sed 's/^[[:space:]]*//;s/[[:space:]]*$//'`

### Common Traps
- **Smart quotes** (`\u201c`, `\u201d`, `\u2018`, `\u2019`) break parsers -> normalize to ASCII quotes.
- **Em/en dashes** (`\u2013`, `\u2014`) break ASCII-only output -> normalize to `-`.
- **Zero-width chars** invisible but break comparisons → strip them
- **String length ≠ byte length** in UTF-8 (`"café"` = 4 chars, 5 bytes)

---

## Format Detection

```bash
# Detect encoding
file -I document.txt

# Detect line endings
cat -A document.txt | head -1
# ^M at end = Windows (CRLF)
# No ^M = Unix (LF)

# Detect likely HTML
grep -qiE '<html|<!doctype html' document.html
```

---

## Quick Transformations

| Task | Command |
|------|---------|
| Lowercase | `tr '[:upper:]' '[:lower:]'` |
| Remove punctuation | `tr -d '[:punct:]'` |
| Count words | `wc -w` |
| Count unique lines | `sort -u \| wc -l` |
| Find duplicates | `sort \| uniq -d` |
| Extract emails | `grep -oE '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'` |
| Extract URLs | `grep -oE 'https?://[^[:space:]<>"{}|\\^`\[\]]+'` |

---

## Before Processing Checklist

- [ ] Encoding verified (UTF-8?)
- [ ] Line endings normalized
- [ ] Target format/style defined (TXT, Markdown, or HTML)
- [ ] Edge cases considered (empty, Unicode, special chars)
