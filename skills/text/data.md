# Text Cleanup And Extraction

Use this reference for plain text, Markdown, and HTML cleanup or conversion. Keep output scoped to the user-requested final artifact. Do not use this skill for spreadsheet deliverables, application config inspection, log analysis, or secret-bearing files.

## Safe Processing Rules

- Work on explicit work_dir-relative input and output paths.
- Prefer writing a new final file under `exports/` instead of editing source content in place.
- Do not print or expose hidden files, logs, caches, `.env`, key, token, cookie, or password files.
- Prefer Python standard library snippets for transformations that need parsing or escaping.

## Unicode And Whitespace

Normalize Unicode before comparing or deduplicating text.

```python
import re
import unicodedata

TYPOGRAPHY_MAP = {
    "\u201c": '"',
    "\u201d": '"',
    "\u2018": "'",
    "\u2019": "'",
    "\u2013": "-",
    "\u2014": "-",
    "\u2026": "...",
    "\u00a0": " ",
    "\u200b": "",
}

def normalize_text(text):
    text = unicodedata.normalize("NFC", text)
    text = "".join(TYPOGRAPHY_MAP.get(ch, ch) for ch in text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"
```

## Deduplication

Build comparison keys from normalized content; preserve the original text in the final output unless the user asks for canonicalized text.

```python
import re
import unicodedata

def dedup_key(text):
    text = unicodedata.normalize("NFKC", text)
    text = text.casefold().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
```

## Extraction Patterns

Use practical regexes for simple extraction. For ambiguous HTML, parse with the Python standard library or preserve the source and ask for a target format.

```python
import re

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://[^\s<>\"{}|\\^`\[\]]+")
MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

def extract_links_and_emails(text):
    return {
        "emails": sorted(set(EMAIL_RE.findall(text))),
        "urls": sorted(set(URL_RE.findall(text))),
        "headings": [m.group(2).strip() for m in MD_HEADING_RE.finditer(text)],
    }
```

## Markdown Shaping

- Preserve fenced code blocks exactly unless the user asks to reformat code.
- Do not wrap a complete Markdown document inside another code fence.
- Keep one blank line around headings, lists, blockquotes, and fenced code.
- Use ATX headings (`# Heading`) for generated Markdown.
- Prefer relative links only when the destination will exist in the same exported package or workspace.

```python
import re

def normalize_markdown_spacing(markdown):
    markdown = markdown.replace("\r\n", "\n").replace("\r", "\n")
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    markdown = re.sub(r"(?<!\n)\n(#{1,6}\s+)", r"\n\n\1", markdown)
    markdown = re.sub(r"(#{1,6}\s+.+)\n(?!\n)", r"\1\n\n", markdown)
    return markdown.strip() + "\n"
```

## HTML Output

When the user asks for an HTML file, produce a complete standalone document. Escape user-provided plain text before inserting it into HTML.

```python
from html import escape

def plaintext_to_html(title, body):
    safe_title = escape(title)
    paragraphs = []
    for block in body.replace("\r\n", "\n").replace("\r", "\n").split("\n\n"):
        block = block.strip()
        if block:
            paragraphs.append(f"<p>{escape(block).replace(chr(10), '<br>')}</p>")
    content = "\n".join(paragraphs)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{safe_title}</title>
</head>
<body>
  <main>
    <h1>{safe_title}</h1>
    {content}
  </main>
</body>
</html>
"""
```

## Final Check

- The output extension matches the requested format.
- The file is UTF-8 text.
- Markdown renders as Markdown, not as a quoted code block.
- HTML is standalone and escaped where needed.
- Only the final user-facing artifact path is passed to `download_paths`.
