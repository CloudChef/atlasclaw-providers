"""Markdown parsing and safe vault file access for the Markdown Vault provider."""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
import hashlib
from pathlib import Path
import re
from typing import Any, Iterable

try:
    import yaml
except ImportError:  # pragma: no cover - AtlasClaw runtime includes PyYAML.
    yaml = None

from _config import MarkdownVaultConfig


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
TAG_RE = re.compile(r"(?<![\w/])#([\w][\w/-]*)", re.UNICODE)
WIKILINK_RE = re.compile(r"!?\[\[([^\]]+)\]\]")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
EMBED_RE = re.compile(r"!\[\[([^\]]+)\]\]")
TERM_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*", re.UNICODE)
CJK_RE = re.compile(r"[\u3400-\u9fff]")
MAX_FRONTMATTER_DEPTH = 12


@dataclass(frozen=True)
class MarkdownReference:
    """A link-like reference discovered in an Obsidian-compatible Markdown file."""

    kind: str
    target: str
    label: str
    line: int


@dataclass(frozen=True)
class VaultChunk:
    """A searchable line range from a vault Markdown document."""

    chunk_id: str
    path: str
    heading_path: list[str]
    start_line: int
    end_line: int
    text: str
    terms: dict[str, float]
    content_hash: str


@dataclass(frozen=True)
class VaultDocument:
    """Parsed Markdown document metadata plus the chunks that should be indexed."""

    path: str
    title: str
    properties: dict[str, Any]
    aliases: list[str]
    tags: list[str]
    links: list[MarkdownReference]
    mtime_ns: int
    size_bytes: int
    content_hash: str
    chunks: list[VaultChunk] = field(default_factory=list)


class VaultPathError(ValueError):
    """Raised when a user-supplied vault path is absolute, non-Markdown, or outside the vault."""


def iter_markdown_files(config: MarkdownVaultConfig) -> list[Path]:
    """Return included Markdown files under the vault, honoring size and exclusion settings."""

    vault_path = config.vault_path
    found: dict[str, Path] = {}
    for pattern in config.include_globs:
        for candidate in vault_path.glob(pattern):
            if not candidate.is_file() or candidate.suffix.lower() != ".md":
                continue
            try:
                relative = _relative_posix(vault_path, candidate)
                size_bytes = candidate.stat().st_size
            except (OSError, ValueError):
                continue
            if _is_excluded(relative, config.exclude_globs):
                continue
            if size_bytes > config.max_file_bytes:
                continue
            found[relative] = candidate
    return [found[key] for key in sorted(found)]


def parse_markdown_file(config: MarkdownVaultConfig, file_path: Path) -> VaultDocument:
    """Parse one vault Markdown file into metadata, references, chunks, and weighted terms."""

    safe_path = resolve_vault_markdown_path(config.vault_path, _relative_posix(config.vault_path, file_path))
    _assert_markdown_file_policy(config, safe_path)
    raw_text = safe_path.read_text(encoding="utf-8", errors="replace")
    lines = raw_text.splitlines()
    frontmatter, body_start_index = _parse_frontmatter(lines)
    properties = _normalize_properties(frontmatter)
    body_lines = lines[body_start_index:]
    relative_path = _relative_posix(config.vault_path, safe_path)
    stat = safe_path.stat()
    content_hash = hashlib.sha1(raw_text.encode("utf-8")).hexdigest()

    inline_tags = sorted(_extract_inline_tags(body_lines))
    frontmatter_tags = _normalize_tags(frontmatter.get("tags") if isinstance(frontmatter, dict) else None)
    tags = sorted(set(frontmatter_tags) | set(inline_tags))
    aliases = _normalize_aliases(frontmatter.get("aliases") if isinstance(frontmatter, dict) else None)
    links = _extract_references(body_lines, line_offset=body_start_index)
    title = _document_title(frontmatter=frontmatter, aliases=aliases, path=safe_path, body_lines=body_lines)

    chunks = _build_chunks(
        relative_path=relative_path,
        body_lines=body_lines,
        line_offset=body_start_index,
        max_chunk_chars=config.max_chunk_chars,
        title=title,
        aliases=aliases,
        tags=tags,
        properties=properties,
        references=links,
    )

    return VaultDocument(
        path=relative_path,
        title=title,
        properties=properties,
        aliases=aliases,
        tags=tags,
        links=links,
        mtime_ns=stat.st_mtime_ns,
        size_bytes=stat.st_size,
        content_hash=content_hash,
        chunks=chunks,
    )


def resolve_vault_markdown_path(vault_path: Path, user_path: str) -> Path:
    """Resolve a vault-relative Markdown path and reject traversal outside the vault root."""

    if not user_path or not str(user_path).strip():
        raise VaultPathError("path is required.")
    raw_path = Path(str(user_path).strip())
    if raw_path.is_absolute():
        raise VaultPathError("Absolute paths are not allowed.")
    candidate = (vault_path / raw_path).resolve()
    vault_root = vault_path.resolve()
    try:
        candidate.relative_to(vault_root)
    except ValueError as exc:
        raise VaultPathError("Path traversal outside the vault is not allowed.") from exc
    if candidate.suffix.lower() != ".md":
        raise VaultPathError("Only Markdown .md files can be read.")
    if not candidate.is_file():
        raise VaultPathError(f"Markdown file not found: {user_path}")
    return candidate


def read_markdown_lines(
    config: MarkdownVaultConfig,
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    default_window: int = 120,
) -> dict[str, Any]:
    """Read a bounded 1-based inclusive line range from a vault Markdown file."""

    file_path = resolve_vault_markdown_path(config.vault_path, path)
    _assert_markdown_file_policy(config, file_path)
    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    total_lines = len(lines)
    start = max(1, int(start_line or 1))
    end = int(end_line or min(total_lines, start + default_window - 1))
    end = max(start, min(total_lines, end))
    selected = lines[start - 1 : end]
    parsed = parse_markdown_file(config, file_path)
    return {
        "path": _relative_posix(config.vault_path, file_path),
        "start_line": start,
        "end_line": end,
        "total_lines": total_lines,
        "title": parsed.title,
        "tags": parsed.tags,
        "text": "\n".join(selected),
    }


def collect_current_file_state(config: MarkdownVaultConfig) -> dict[str, tuple[int, int, str]]:
    """Collect path, mtime, size, and content hash for the current vault scan."""

    state: dict[str, tuple[int, int, str]] = {}
    for file_path in iter_markdown_files(config):
        raw_text = file_path.read_text(encoding="utf-8", errors="replace")
        stat = file_path.stat()
        state[_relative_posix(config.vault_path, file_path)] = (
            stat.st_mtime_ns,
            stat.st_size,
            hashlib.sha1(raw_text.encode("utf-8")).hexdigest(),
        )
    return state


def parse_vault(config: MarkdownVaultConfig) -> list[VaultDocument]:
    """Parse all configured Markdown files in the vault for index refresh."""

    return [parse_markdown_file(config, path) for path in iter_markdown_files(config)]


def normalize_terms(text: str) -> list[str]:
    """Normalize English tokens and Chinese character n-grams for portable search."""

    normalized = text.lower()
    terms: list[str] = [match.group(0) for match in TERM_RE.finditer(normalized)]
    cjk_chars = CJK_RE.findall(normalized)
    terms.extend(cjk_chars)
    terms.extend(
        "".join(pair)
        for pair in zip(cjk_chars, cjk_chars[1:])
    )
    return [term for term in terms if term]


def _parse_frontmatter(lines: list[str]) -> tuple[dict[str, Any], int]:
    if not lines or lines[0].strip() != "---":
        return {}, 0
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            raw = "\n".join(lines[1:index])
            if yaml is None:
                return {}, index + 1
            try:
                payload = yaml.safe_load(raw) or {}
            except (yaml.YAMLError, RecursionError):
                payload = {}
            return payload if isinstance(payload, dict) else {}, index + 1
    return {}, 0


def _build_chunks(
    *,
    relative_path: str,
    body_lines: list[str],
    line_offset: int,
    max_chunk_chars: int,
    title: str,
    aliases: list[str],
    tags: list[str],
    properties: dict[str, Any],
    references: list[MarkdownReference],
) -> list[VaultChunk]:
    chunks: list[VaultChunk] = []
    heading_stack: list[tuple[int, str]] = []
    current_lines: list[tuple[int, str]] = []
    current_heading_path: list[str] = []
    in_fence = False

    def flush() -> None:
        if not current_lines:
            return
        text = "\n".join(line for _, line in current_lines).strip()
        if not text:
            current_lines.clear()
            return
        start_line = current_lines[0][0]
        end_line = current_lines[-1][0]
        searchable_text = _searchable_markdown_text(text)
        terms = _weighted_terms(
            text=searchable_text,
            heading_path=current_heading_path,
            title=title,
            aliases=aliases,
            tags=tags,
            properties=properties,
            references=references,
        )
        content_hash = hashlib.sha1(text.encode("utf-8")).hexdigest()
        chunk_id = hashlib.sha1(f"{relative_path}:{start_line}:{end_line}:{content_hash}".encode("utf-8")).hexdigest()
        chunks.append(
            VaultChunk(
                chunk_id=chunk_id,
                path=relative_path,
                heading_path=list(current_heading_path),
                start_line=start_line,
                end_line=end_line,
                text=text,
                terms=terms,
                content_hash=content_hash,
            )
        )
        current_lines.clear()

    for body_index, line in enumerate(body_lines):
        line_no = line_offset + body_index + 1
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
        match = HEADING_RE.match(line) if not in_fence else None
        if match:
            flush()
            level = len(match.group(1))
            heading = _strip_heading_suffix(match.group(2))
            heading_stack = [entry for entry in heading_stack if entry[0] < level]
            heading_stack.append((level, heading))
            current_heading_path = [item for _, item in heading_stack]
            current_lines.append((line_no, line))
            continue
        if not current_lines and not stripped:
            continue
        if not current_lines:
            current_heading_path = [item for _, item in heading_stack]
        current_lines.append((line_no, line))
        if sum(len(value) + 1 for _, value in current_lines) >= max_chunk_chars:
            flush()
            current_heading_path = [item for _, item in heading_stack]

    flush()
    return chunks


def _weighted_terms(
    *,
    text: str,
    heading_path: list[str],
    title: str,
    aliases: list[str],
    tags: list[str],
    properties: dict[str, Any],
    references: list[MarkdownReference],
) -> dict[str, float]:
    weights: dict[str, float] = {}
    _add_terms(weights, normalize_terms(text), 1.0)
    _add_terms(weights, normalize_terms(" ".join(heading_path)), 3.0)
    _add_terms(weights, normalize_terms(title), 2.5)
    _add_terms(weights, normalize_terms(" ".join(aliases)), 2.0)
    _add_terms(weights, normalize_terms(" ".join(tags)), 2.0)
    _add_terms(weights, normalize_terms(_frontmatter_search_text(properties)), 1.5)
    _add_terms(weights, normalize_terms(" ".join(ref.label + " " + ref.target for ref in references)), 1.5)
    return weights


def _add_terms(weights: dict[str, float], terms: Iterable[str], weight: float) -> None:
    for term in terms:
        weights[term] = weights.get(term, 0.0) + weight


def _extract_inline_tags(lines: list[str]) -> set[str]:
    tags: set[str] = set()
    in_fence = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in TAG_RE.finditer(line):
            tag = match.group(1).strip().strip("/")
            if tag:
                tags.add(tag)
    return tags


def _extract_references(lines: list[str], *, line_offset: int) -> list[MarkdownReference]:
    references: list[MarkdownReference] = []
    in_fence = False
    for index, line in enumerate(lines, start=line_offset + 1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in EMBED_RE.finditer(line):
            label, target = _split_wikilink(match.group(1))
            references.append(MarkdownReference(kind="embed", target=target, label=label, line=index))
        for match in WIKILINK_RE.finditer(line):
            if match.group(0).startswith("!"):
                continue
            label, target = _split_wikilink(match.group(1))
            references.append(MarkdownReference(kind="wikilink", target=target, label=label, line=index))
        for match in MARKDOWN_LINK_RE.finditer(line):
            references.append(
                MarkdownReference(
                    kind="markdown",
                    target=match.group(2).strip(),
                    label=match.group(1).strip(),
                    line=index,
                )
            )
    return references


def _searchable_markdown_text(text: str) -> str:
    def replace_wikilink(match: re.Match[str]) -> str:
        label, target = _split_wikilink(match.group(1))
        return f"{label} {target}".strip()

    text = WIKILINK_RE.sub(replace_wikilink, text)
    text = MARKDOWN_LINK_RE.sub(lambda match: f"{match.group(1)} {match.group(2)}", text)
    normalized_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(">"):
            stripped = stripped.lstrip("> ").strip()
            stripped = re.sub(r"^\[![^\]]+\]\s*", "", stripped)
            normalized_lines.append(stripped)
        else:
            normalized_lines.append(line)
    return "\n".join(normalized_lines)


def _split_wikilink(payload: str) -> tuple[str, str]:
    value = payload.strip()
    if "|" in value:
        target, label = value.split("|", 1)
        return label.strip(), target.strip()
    if "#" in value:
        return value.rsplit("#", 1)[-1].strip() or value.strip(), value.strip()
    return value, value


def _document_title(
    *,
    frontmatter: dict[str, Any],
    aliases: list[str],
    path: Path,
    body_lines: list[str],
) -> str:
    title = str(frontmatter.get("title") or "").strip() if isinstance(frontmatter, dict) else ""
    if title:
        return title
    for line in body_lines:
        match = HEADING_RE.match(line)
        if match and len(match.group(1)) == 1:
            return _strip_heading_suffix(match.group(2))
    return aliases[0] if aliases else path.stem


def _strip_heading_suffix(value: str) -> str:
    return re.sub(r"\s+#+\s*$", "", value).strip()


def _normalize_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = re.split(r"[\s,]+", value)
    elif isinstance(value, list):
        items = [str(item) for item in value]
    else:
        items = [str(value)]
    tags = {item.strip().lstrip("#").strip("/") for item in items if item and item.strip()}
    return sorted(tag for tag in tags if tag)


def _normalize_aliases(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = [str(item) for item in value]
    else:
        items = [str(value)]
    return [item.strip() for item in items if item.strip()]


def _normalize_properties(frontmatter: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(frontmatter, dict):
        return {}
    return {
        str(key): _safe_frontmatter_value(value, seen=set(), depth=0)
        for key, value in frontmatter.items()
        if isinstance(key, str)
    }


def _safe_frontmatter_value(value: Any, *, seen: set[int], depth: int) -> Any:
    if depth >= MAX_FRONTMATTER_DEPTH:
        return ""
    if isinstance(value, dict):
        object_id = id(value)
        if object_id in seen:
            return ""
        seen.add(object_id)
        return {
            str(key): _safe_frontmatter_value(item, seen=seen, depth=depth + 1)
            for key, item in value.items()
            if isinstance(key, str)
        }
    if isinstance(value, list):
        object_id = id(value)
        if object_id in seen:
            return []
        seen.add(object_id)
        return [_safe_frontmatter_value(item, seen=seen, depth=depth + 1) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _frontmatter_search_text(value: Any, *, seen: set[int] | None = None, depth: int = 0) -> str:
    if depth >= MAX_FRONTMATTER_DEPTH:
        return ""
    seen = seen or set()
    if isinstance(value, dict):
        object_id = id(value)
        if object_id in seen:
            return ""
        seen.add(object_id)
        parts: list[str] = []
        for key, item in value.items():
            parts.append(str(key))
            parts.append(_frontmatter_search_text(item, seen=seen, depth=depth + 1))
        return " ".join(parts)
    if isinstance(value, list):
        object_id = id(value)
        if object_id in seen:
            return ""
        seen.add(object_id)
        return " ".join(_frontmatter_search_text(item, seen=seen, depth=depth + 1) for item in value)
    if value is None:
        return ""
    return str(value)


def _relative_posix(vault_path: Path, file_path: Path) -> str:
    return file_path.resolve().relative_to(vault_path.resolve()).as_posix()


def _is_excluded(relative_path: str, patterns: list[str]) -> bool:
    return any(_matches_glob(relative_path, pattern) for pattern in patterns)


def _assert_markdown_file_policy(config: MarkdownVaultConfig, file_path: Path) -> None:
    relative_path = _relative_posix(config.vault_path, file_path)
    if not any(_matches_glob(relative_path, pattern) for pattern in config.include_globs):
        raise VaultPathError(f"Markdown file is not included in this vault index: {relative_path}")
    if _is_excluded(relative_path, config.exclude_globs):
        raise VaultPathError(f"Markdown file is excluded from this vault index: {relative_path}")
    try:
        size_bytes = file_path.stat().st_size
    except OSError as exc:
        raise VaultPathError(f"Markdown file not readable: {relative_path}") from exc
    if size_bytes > config.max_file_bytes:
        raise VaultPathError(f"Markdown file exceeds max_file_bytes: {relative_path}")


def _matches_glob(relative_path: str, pattern: str) -> bool:
    if fnmatch(relative_path, pattern):
        return True
    if "**/" in pattern and fnmatch(relative_path, pattern.replace("**/", "", 1)):
        return True
    if pattern.startswith("**/") and fnmatch(relative_path, pattern[3:]):
        return True
    if pattern.endswith("/**") and (
        relative_path == pattern[:-3].rstrip("/") or relative_path.startswith(pattern[:-3].rstrip("/") + "/")
    ):
        return True
    return False
