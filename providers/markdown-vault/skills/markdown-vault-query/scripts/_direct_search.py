"""Direct Markdown scanning search for the Markdown Vault provider."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from _config import MarkdownVaultConfig
from _parser import VaultChunk, VaultDocument, normalize_terms, parse_vault, searchable_markdown_text


SNIPPET_CHARS = 360
TOKEN_COUNT_LIMIT = 5
COMMON_TOKEN_MIN_CHUNKS = 8
COMMON_TOKEN_RATIO = 0.08
COMMON_TOKEN_SCORE_MULTIPLIER = 0.15
ASCII_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "can",
    "for",
    "from",
    "how",
    "is",
    "of",
    "or",
    "the",
    "to",
    "what",
    "when",
    "where",
    "with",
}
QUERY_STOP_TERMS = {
    "是否",
    "可以",
    "能够",
    "怎么",
    "如何",
    "什么",
    "里面",
    "时候",
}


@dataclass(frozen=True)
class SearchNeedle:
    """Normalized query or keyword expression used to score Markdown chunks."""

    display: str
    phrase: str
    tokens: tuple[str, ...]
    from_keyword: bool


@dataclass(frozen=True)
class SearchCandidate:
    """A scored Markdown chunk candidate before context-budget trimming."""

    score: float
    document: VaultDocument
    chunk: VaultChunk
    matched_keywords: tuple[str, ...]


@dataclass(frozen=True)
class SearchItem:
    """A parsed chunk plus normalized fields prepared for one direct-search request."""

    document: VaultDocument
    chunk: VaultChunk
    fields: "SearchFields"


@dataclass(frozen=True)
class SearchFields:
    """Normalized searchable fields for one Markdown chunk."""

    body: str
    title: str
    heading: str
    aliases: str
    tags: str
    path: str


def search_direct(
    config: MarkdownVaultConfig,
    query: str,
    *,
    keywords: list[str],
    limit: int,
    path_filter: str | None,
    tag_filter: str | None,
) -> dict[str, Any]:
    """Scan Markdown files directly and return bounded evidence chunks for LLM analysis."""

    documents = parse_vault(config)
    needles = _build_needles(query, keywords)
    requested_tags = _parse_tag_filter(tag_filter)
    path_filter_normalized = (path_filter or "").strip().lower()

    search_items: list[SearchItem] = []
    scanned_chunks = 0
    for document in documents:
        if path_filter_normalized and path_filter_normalized not in document.path.lower():
            continue
        if requested_tags and not requested_tags.intersection({tag.lower() for tag in document.tags}):
            continue
        for chunk in document.chunks:
            scanned_chunks += 1
            fields = _search_fields(document, chunk)
            search_items.append(SearchItem(document=document, chunk=chunk, fields=fields))

    common_tokens = _dynamic_common_tokens(needles, [item.fields for item in search_items])

    candidates: list[SearchCandidate] = []
    for item in search_items:
        score, matched_keywords = _score_fields(item.fields, needles, common_tokens)
        if score > 0:
            candidates.append(
                SearchCandidate(
                    score=score,
                    document=item.document,
                    chunk=item.chunk,
                    matched_keywords=tuple(matched_keywords),
                )
            )

    candidates.sort(key=lambda item: (-item.score, item.document.path, item.chunk.start_line))
    results, returned_chars, limited_by_context_budget = _trim_results(config, candidates, limit)
    return {
        "success": True,
        "search_backend": "direct",
        "result_count": len(results),
        "results": results,
        "status": {
            "search_backend": "direct",
            "current_documents": len(documents),
            "scanned_chunks": scanned_chunks,
            "returned_context_chars": returned_chars,
            "context_budget_chars": config.max_context_chars,
            "limited_by_context_budget": limited_by_context_budget,
        },
    }


def _build_needles(query: str, keywords: list[str]) -> list[SearchNeedle]:
    values = [item for item in keywords if item and item.strip()]

    needles: list[SearchNeedle] = []
    seen: set[tuple[str, bool]] = set()
    for value in values:
        phrase = _normalize_text(value)
        tokens = tuple(_filtered_terms(value, from_keyword=True))
        if not phrase and not tokens:
            continue
        key = (phrase or " ".join(tokens), True)
        if key not in seen:
            seen.add(key)
            needles.append(SearchNeedle(display=value.strip(), phrase=phrase, tokens=tokens, from_keyword=True))

    query_tokens = tuple(_filtered_terms(query, from_keyword=False))
    query_phrase = _normalize_text(query)
    if query_phrase or query_tokens:
        needles.append(
            SearchNeedle(
                display=query.strip(),
                phrase=query_phrase,
                tokens=query_tokens,
                from_keyword=False,
            )
        )
    return needles


def _search_fields(document: VaultDocument, chunk: VaultChunk) -> SearchFields:
    body = searchable_markdown_text(chunk.text)
    return SearchFields(
        body=_normalize_text(body),
        title=_normalize_text(document.title),
        heading=_normalize_text(" ".join(chunk.heading_path)),
        aliases=_normalize_text(" ".join(document.aliases)),
        tags=_normalize_text(" ".join(document.tags)),
        path=_normalize_text(document.path),
    )


def _dynamic_common_tokens(
    needles: list[SearchNeedle],
    fields: list[SearchFields],
) -> set[str]:
    tokens = {token for needle in needles for token in needle.tokens}
    if not tokens or not fields:
        return set()
    return _common_tokens(tokens, fields)


def _common_tokens(tokens: set[str], fields: list[SearchFields]) -> set[str]:
    threshold = max(COMMON_TOKEN_MIN_CHUNKS, int(len(fields) * COMMON_TOKEN_RATIO))
    counts = {token: 0 for token in tokens}
    for item in fields:
        text = _combined_fields(item)
        for token in tokens:
            if _token_count(text, token) > 0:
                counts[token] += 1
    return {token for token, count in counts.items() if count >= threshold}


def _single_common_token_phrase(
    phrase: str,
    tokens: tuple[str, ...],
    common_tokens: set[str],
) -> bool:
    return len(tokens) == 1 and phrase == tokens[0] and phrase in common_tokens


def _combined_fields(fields: SearchFields) -> str:
    return " ".join((fields.body, fields.title, fields.heading, fields.aliases, fields.tags, fields.path))


def _score_fields(
    fields: SearchFields,
    needles: list[SearchNeedle],
    common_tokens: set[str],
) -> tuple[float, list[str]]:
    score = 0.0
    matched: list[str] = []
    for needle in needles:
        needle_score = _score_needle(fields, needle, common_tokens)
        if needle_score <= 0:
            continue
        score += needle_score
        matched.append(needle.display)
    return score, matched


def _score_needle(fields: SearchFields, needle: SearchNeedle, common_tokens: set[str]) -> float:
    score = 0.0
    keyword_multiplier = 1.35 if needle.from_keyword else 1.0
    phrase = needle.phrase
    phrase_multiplier = (
        COMMON_TOKEN_SCORE_MULTIPLIER
        if _single_common_token_phrase(phrase, needle.tokens, common_tokens)
        else 1.0
    )
    if phrase and len(phrase) >= 2:
        score += phrase_multiplier * _phrase_score(fields.title, phrase, 22.0)
        score += phrase_multiplier * _phrase_score(fields.heading, phrase, 18.0)
        score += phrase_multiplier * _phrase_score(fields.aliases, phrase, 20.0)
        score += phrase_multiplier * _phrase_score(fields.tags, phrase, 12.0)
        score += phrase_multiplier * _phrase_score(fields.path, phrase, 8.0)
        score += phrase_multiplier * _phrase_score(fields.body, phrase, 9.0)
    for token in needle.tokens:
        token_multiplier = COMMON_TOKEN_SCORE_MULTIPLIER if token in common_tokens else 1.0
        score += token_multiplier * _token_score(fields.title, token, 7.0)
        score += token_multiplier * _token_score(fields.heading, token, 6.0)
        score += token_multiplier * _token_score(fields.aliases, token, 6.5)
        score += token_multiplier * _token_score(fields.tags, token, 4.0)
        score += token_multiplier * _token_score(fields.path, token, 3.0)
        score += token_multiplier * _token_score(fields.body, token, 1.3)
    return score * keyword_multiplier


def _phrase_score(text: str, phrase: str, weight: float) -> float:
    count = text.count(phrase)
    if count <= 0:
        return 0.0
    return weight + min(count - 1, TOKEN_COUNT_LIMIT) * (weight * 0.25)


def _token_score(text: str, token: str, weight: float) -> float:
    count = _token_count(text, token)
    if count <= 0:
        return 0.0
    return min(count, TOKEN_COUNT_LIMIT) * weight


def _token_count(text: str, token: str) -> int:
    if _is_ascii_token(token):
        return len(re.findall(rf"(?<![a-z0-9_-]){re.escape(token)}(?![a-z0-9_-])", text))
    return text.count(token)


def _trim_results(
    config: MarkdownVaultConfig,
    candidates: list[SearchCandidate],
    limit: int,
) -> tuple[list[dict[str, Any]], int, bool]:
    results: list[dict[str, Any]] = []
    returned_chars = 0
    limited_by_context_budget = False
    for index, candidate in enumerate(candidates):
        if len(results) >= limit:
            break
        remaining = config.max_context_chars - returned_chars
        if remaining <= 0:
            limited_by_context_budget = index < len(candidates)
            break
        text, text_truncated = _truncate_text(candidate.chunk.text, min(config.max_result_chars, remaining))
        if not text:
            limited_by_context_budget = True
            break
        returned_chars += len(text)
        results.append(
            {
                "path": candidate.chunk.path,
                "title": candidate.document.title,
                "heading_path": candidate.chunk.heading_path,
                "start_line": candidate.chunk.start_line,
                "end_line": candidate.chunk.end_line,
                "score": round(candidate.score, 4),
                "snippet": _snippet(candidate.chunk.text),
                "text": text,
                "text_truncated": text_truncated,
                "matched_keywords": list(candidate.matched_keywords),
                "tags": candidate.document.tags,
            }
        )
    if len(results) < min(limit, len(candidates)):
        limited_by_context_budget = returned_chars >= config.max_context_chars
    return results, returned_chars, limited_by_context_budget


def _filtered_terms(value: str, *, from_keyword: bool) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for term in normalize_terms(value):
        if _should_skip_term(term, from_keyword=from_keyword):
            continue
        if term not in seen:
            seen.add(term)
            terms.append(term)
    return terms


def _should_skip_term(term: str, *, from_keyword: bool) -> bool:
    if not term:
        return True
    if _is_ascii_token(term):
        return len(term) < 2 or (not from_keyword and term in ASCII_STOPWORDS)
    if len(term) < 2:
        return True
    return not from_keyword and term in QUERY_STOP_TERMS


def _normalize_text(value: str) -> str:
    return " ".join(str(value).lower().split())


def _is_ascii_token(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]*", value))


def _parse_tag_filter(value: str | None) -> set[str]:
    if not value:
        return set()
    return {
        item.strip().lstrip("#").lower()
        for item in value.replace("\n", ",").split(",")
        if item.strip()
    }


def _truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    if max_chars <= 0:
        return "", bool(text)
    if len(text) <= max_chars:
        return text, False
    if max_chars <= 4:
        return text[:max_chars], True
    return text[: max_chars - 3].rstrip() + "...", True


def _snippet(text: str, max_chars: int = SNIPPET_CHARS) -> str:
    compact = " ".join(line.strip() for line in text.splitlines() if line.strip())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "..."
