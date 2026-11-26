#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Orchestrate LLM project identification, project reviews, and global synthesis."""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import re
from pathlib import Path
from typing import Any, Awaitable, Callable

from audit_project_prompts import render_prompt_template

Submit = Callable[[str], Awaitable[str]]
Progress = Callable[[dict[str, Any]], Awaitable[None]]
PAGE_MARKER = re.compile(r"(?m)^## Page (\d+)\s*$")
FINDING = re.compile(r"(?m)^###\s+(F-(?:\d+-\d+|\d{2,}))\b.*$")
FINDING_HEADING = re.compile(r"(?m)^(#{1,6})[ \t]+(?=.*\bF-(?:\d+-\d+|\d{2,})\b).*$")
FINDING_METADATA_LABEL = re.compile(
    r"\*\*(页码|规则号|等级|位置|原文上下文|影响|整改建议|关联问题)\*\*[：:]"
)
SECTIONS = ("核查依据", "数值核查", "设备台账", "项目问题")


def _parse_json_object(raw: str, label: str) -> dict[str, Any]:
    text = raw.strip()
    fence = chr(96) * 3
    if text.startswith(fence):
        text = re.sub(r"^" + re.escape(fence) + r"(?:json)?\s*|\s*" + re.escape(fence) + r"$", "", text, flags=re.I).strip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {exc.msg}") from exc
    if not isinstance(result, dict):
        raise ValueError(f"{label} must be a JSON object")
    return result


def _load_builders() -> tuple[Callable, Callable, Callable]:
    """Load prompt builders kept in their separately owned module."""
    from audit_project_prompts import build_index_prompt, build_project_prompt, build_summary_prompt
    return build_index_prompt, build_project_prompt, build_summary_prompt


def _load_chunk_index_builders() -> tuple[Callable, Callable]:
    """Load bounded directory scan and merge prompt builders."""
    from audit_project_prompts import build_index_chunk_prompt, build_index_merge_prompt
    return build_index_chunk_prompt, build_index_merge_prompt


def _save_json(path: Path, value: Any) -> None:
    """Atomically persist JSON-safe technical state."""
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


async def _emit(callback: Progress | None, stage: str, completed: int, total: int, message: str) -> None:
    """Send technical progress only."""
    if callback is not None:
        result = callback({"stage": stage, "completed": completed, "total": total, "message": message})
        if inspect.isawaitable(result):
            await result


def _pages(report_text: str, page_count: int) -> dict[int, str]:
    """Split the full report only at its existing one-based page markers."""
    matches = list(PAGE_MARKER.finditer(report_text))
    pages: dict[int, str] = {}
    for index, match in enumerate(matches):
        number = int(match.group(1))
        if number in pages or number < 1 or number > page_count:
            raise ValueError(f"Invalid or duplicate PDF page marker: {number}")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(report_text)
        pages[number] = report_text[match.start():end].rstrip()
    missing = [number for number in range(1, page_count + 1) if number not in pages]
    if missing:
        raise ValueError("Report is missing PDF page markers: " + ", ".join(map(str, missing[:10])))
    return pages


def _parse_index(raw: str, page_count: int) -> dict[str, Any]:
    """Parse only the LLM-produced project index and validate its container."""
    text = raw.strip()
    fence = chr(96) * 3
    if text.startswith(fence):
        text = re.sub(r"^" + re.escape(fence) + r"(?:json)?\s*|\s*" + re.escape(fence) + r"$", "", text, flags=re.I).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Directory response is not valid JSON: {exc.msg}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("projects"), list):
        raise ValueError("Directory response must contain a projects array")
    reason = value.get("no_projects_reason")
    projects = []
    seen: set[str] = set()
    for index, item in enumerate(value["projects"], 1):
        if not isinstance(item, dict):
            raise ValueError(f"Project {index} must be an object")
        project_id, title = item.get("id"), item.get("title")
        start, end = item.get("page_start"), item.get("page_end")
        if not isinstance(project_id, str) or not project_id.strip():
            raise ValueError(f"Project {index} has an empty id")
        project_id = project_id.strip()
        if project_id in seen:
            raise ValueError(f"Duplicate project id: {project_id}")
        seen.add(project_id)
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"Project {project_id} has an empty title")
        if (not isinstance(start, int) or isinstance(start, bool)
                or not isinstance(end, int) or isinstance(end, bool)):
            raise ValueError(f"Project {project_id} page range must use integer page numbers")
        if start < 1 or end < start or end > page_count:
            raise ValueError(f"Project {project_id} page range is outside the PDF")
        projects.append({"id": project_id, "title": title.strip(), "page_start": start, "page_end": end})
    if not projects and (not isinstance(reason, str) or not reason.strip()):
        raise ValueError("An empty project directory requires no_projects_reason")
    result = {"projects": projects}
    if isinstance(reason, str):
        result["no_projects_reason"] = reason.strip()
    return result


def _validate_index_chunk(
    raw: str,
    formal_pages: list[int],
    page_count: int,
    page_map: dict[int, str],
    known_project_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Validate a chunk scan's schema and exact structural page coverage."""
    value = _parse_json_object(raw, "directory chunk response")
    segments = value.get("segments", [])
    non_project_pages = value.get("non_project_pages", [])
    if not isinstance(segments, list) or not isinstance(non_project_pages, list):
        raise ValueError("Directory chunk must contain segments and non_project_pages arrays")

    covered: set[int] = set()
    segment_ids: set[str] = set()
    seen_project_ids = {project_id.strip() for project_id in (known_project_ids or set())}
    for index, segment in enumerate(segments, 1):
        if not isinstance(segment, dict):
            raise ValueError(f"Directory chunk segment {index} must be an object")
        project_id, title = segment.get("id"), segment.get("title")
        start, end = segment.get("page_start"), segment.get("page_end")
        if not isinstance(project_id, str) or not project_id.strip():
            raise ValueError(f"Directory chunk segment {index} has an empty id")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"Directory chunk segment {index} has an empty title")
        if (not isinstance(start, int) or isinstance(start, bool)
                or not isinstance(end, int) or isinstance(end, bool)):
            raise ValueError(f"Directory chunk segment {index} page range must use integers")
        if start < formal_pages[0] or end < start or end > formal_pages[-1] or end > page_count:
            raise ValueError(f"Directory chunk segment {index} is outside its formal pages")
        project_id = project_id.strip()
        if project_id not in seen_project_ids:
            start_quote = segment.get("start_quote")
            if not isinstance(start_quote, str) or not start_quote.strip():
                raise ValueError(f"Directory chunk segment {index} has a new ID without a literal start_quote")
            normalize_ws = lambda text: re.sub(r"\s+", "", text)
            normalized_quote = normalize_ws(start_quote)
            if not normalized_quote or normalized_quote not in normalize_ws(page_map.get(start, "")):
                raise ValueError(
                    f"Directory chunk segment {index} start_quote is not present on its declared start page {start}"
                )
            seen_project_ids.add(project_id)
        segment_ids.add(project_id)
        covered.update(range(start, end + 1))

    non_project: set[int] = set()
    for index, item in enumerate(non_project_pages, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Directory chunk non_project_pages item {index} must be an object")
        page, reason = item.get("page"), item.get("reason")
        if not isinstance(page, int) or isinstance(page, bool) or page not in formal_pages:
            raise ValueError(f"Directory chunk non-project page {index} is outside its formal pages")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"Directory chunk non-project page {page} requires a reason")
        if page in non_project:
            raise ValueError(f"Directory chunk non-project page {page} is duplicated")
        non_project.add(page)
    conflict = covered & non_project
    if conflict:
        raise ValueError(f"Directory chunk pages cannot be both project and non-project: {sorted(conflict)}")
    expected = set(formal_pages)
    missing = expected - covered - non_project
    if missing:
        raise ValueError(f"Directory chunk leaves formal pages unclassified: {sorted(missing)}")
    result = {
        "segments": segments,
        "non_project_pages": non_project_pages,
        "project_ids": sorted(segment_ids),
    }
    return result


async def _run_chunked_index(
    page_map: dict[int, str],
    page_count: int,
    build_chunk_prompt: Callable,
    build_merge_prompt: Callable,
    send: Callable[[str, str, Path, list[int], list[str]], Awaitable[str]],
    output_dir: Path,
    manifest: dict[str, Any],
    manifest_path: Path,
    on_progress: Progress | None,
) -> dict[str, Any]:
    """Scan long reports sequentially in bounded chunks, then ask the LLM to merge."""
    chunk_size = 32
    ranges = [
        list(range(start, min(start + chunk_size, page_count + 1)))
        for start in range(1, page_count + 1, chunk_size)
    ]
    index_record = manifest["index"]
    index_record["status"] = "running"
    index_record["chunks"] = []
    index_record["merge_attempts"] = []
    scans: list[dict[str, Any]] = []
    previous_scan_raw: str | None = None
    project_ids: set[str] = set()
    project_segment_pages: dict[str, set[int]] = {}
    project_bounds: dict[str, list[int]] = {}

    for chunk_index, formal_pages in enumerate(ranges, 1):
        context_pages = ([formal_pages[0] - 1] if formal_pages[0] > 1 else [])
        if formal_pages[-1] < page_count:
            context_pages.append(formal_pages[-1] + 1)
        chunk_record: dict[str, Any] = {
            "chunk_index": chunk_index,
            "formal_pages": formal_pages,
            "context_pages": context_pages,
            "status": "pending",
            "attempts": [],
        }
        index_record["chunks"].append(chunk_record)
        _save_json(manifest_path, manifest)
        page_text = {page: page_map[page] for page in context_pages + formal_pages}
        base_prompt = build_chunk_prompt(
            page_text, formal_pages, context_pages, page_count, chunk_index, len(ranges),
            previous_scan_raw=previous_scan_raw,
        )
        scan: dict[str, Any] | None = None
        raw: str | None = None
        last_error: ValueError | None = None
        chunk_record["status"] = "running"
        for attempt in range(2):
            name = f"index-chunks/{chunk_index:03d}-raw.json.txt" if not attempt else (
                f"index-chunks/{chunk_index:03d}-retry-raw.json.txt"
            )
            attempt_record = {"response_file": name, "status": "pending"}
            chunk_record["attempts"].append(attempt_record)
            prompt = base_prompt
            if attempt:
                prompt += "\n\n" + render_prompt_template("index-scan-retry.md", ERROR=str(last_error), RAW=str(raw))
            try:
                await _emit(on_progress, "index", chunk_index - 1, len(ranges),
                            f"目录扫描第 {chunk_index}/{len(ranges)} 段（物理页 {formal_pages[0]}–{formal_pages[-1]}）")
                raw = await send(
                    f"index-chunk:{chunk_index:03d}", prompt, output_dir / name, formal_pages, [],
                )
                attempt_record["status"] = "received"
                attempt_record["prompt_sha256"] = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
                attempt_record["prompt_characters"] = len(prompt)
                attempt_record["response_sha256"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                scan = _validate_index_chunk(
                    raw, formal_pages, page_count, page_map, known_project_ids=project_ids
                )
                attempt_record["status"] = "complete"
                break
            except asyncio.CancelledError:
                attempt_record["status"] = "cancelled"
                chunk_record["status"] = "cancelled"
                _save_json(manifest_path, manifest)
                raise
            except ValueError as exc:
                attempt_record["status"] = "invalid_format"
                attempt_record["error"] = str(exc)
                last_error = exc
                _save_json(manifest_path, manifest)
                if attempt:
                    chunk_record.update(status="failed", error=str(exc))
                    index_record["status"] = "failed"
                    _save_json(manifest_path, manifest)
                    raise
            except Exception as exc:
                attempt_record.update(status="failed", error_type=type(exc).__name__)
                chunk_record.update(status="failed", error_type=type(exc).__name__)
                index_record["status"] = "failed"
                _save_json(manifest_path, manifest)
                raise
        if scan is None or raw is None:
            chunk_record["status"] = "failed"
            index_record["status"] = "failed"
            _save_json(manifest_path, manifest)
            raise ValueError(f"Directory chunk {chunk_index} could not be validated")
        chunk_record.update(
            status="complete",
            completed_response_file=chunk_record["attempts"][-1]["response_file"],
            response_sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            project_ids=scan["project_ids"],
        )
        project_ids.update(scan["project_ids"])
        for segment in scan["segments"]:
            project_id = segment["id"].strip()
            start, end = segment["page_start"], segment["page_end"]
            project_segment_pages.setdefault(project_id, set()).update(range(start, end + 1))
            bounds = project_bounds.setdefault(project_id, [start, end])
            bounds[0] = min(bounds[0], start)
            bounds[1] = max(bounds[1], end)
        scans.append({
            "chunk_index": chunk_index,
            "formal_pages": formal_pages,
            "context_pages": context_pages,
            "response_file": chunk_record["completed_response_file"],
            "scan": scan,
            "raw_response": raw,
        })
        previous_scan_raw = raw
        _save_json(manifest_path, manifest)
        await _emit(on_progress, "index", chunk_index, len(ranges),
                    f"目录扫描第 {chunk_index}/{len(ranges)} 段完成")

    for project_id, bounds in project_bounds.items():
        expected_pages = set(range(bounds[0], bounds[1] + 1))
        if project_segment_pages[project_id] != expected_pages:
            index_record["status"] = "failed"
            _save_json(manifest_path, manifest)
            raise ValueError(
                f"Directory scan segments for project {project_id} have a gap; refusing to merge across unclassified pages"
            )

    merge_base = build_merge_prompt(scans, page_count)
    last_error: ValueError | None = None
    raw: str | None = None
    for attempt in range(2):
        name = "index-merge-raw.txt" if not attempt else "index-merge-retry-raw.txt"
        entry = {"response_file": name, "status": "pending"}
        index_record["merge_attempts"].append(entry)
        _save_json(manifest_path, manifest)
        prompt = merge_base
        if attempt:
            prompt += "\n\n" + render_prompt_template("index-merge-retry.md", ERROR=str(last_error), RAW=str(raw))
        try:
            raw = await send("index-merge", prompt, output_dir / name, [], [])
            entry["status"] = "received"
            index = _parse_index(raw, page_count)
            index_ids = {project["id"] for project in index["projects"]}
            if index_ids != project_ids:
                missing, extra = sorted(project_ids - index_ids), sorted(index_ids - project_ids)
                raise ValueError(f"Merged directory project IDs differ from chunk scans; missing={missing}, extra={extra}")
            for project in index["projects"]:
                expected_bounds = project_bounds[project["id"]]
                if [project["page_start"], project["page_end"]] != expected_bounds:
                    raise ValueError(
                        f"Merged directory range for project {project['id']} must match its scanned segment boundaries"
                    )
            entry["status"] = "complete"
            index_record["status"] = "complete"
            index_record["merge_response_file"] = name
            index_record["chunk_project_ids"] = sorted(project_ids)
            _save_json(manifest_path, manifest)
            return index
        except asyncio.CancelledError:
            entry["status"] = "cancelled"
            index_record["status"] = "cancelled"
            _save_json(manifest_path, manifest)
            raise
        except ValueError as exc:
            entry["status"] = "invalid_format"
            entry["error"] = str(exc)
            last_error = exc
            _save_json(manifest_path, manifest)
            if attempt:
                index_record["status"] = "failed"
                _save_json(manifest_path, manifest)
                raise
        except Exception as exc:
            entry.update(status="failed", error_type=type(exc).__name__)
            index_record["status"] = "failed"
            _save_json(manifest_path, manifest)
            raise
    index_record["status"] = "failed"
    _save_json(manifest_path, manifest)
    raise ValueError("Merged directory could not be validated")


def _markdown(raw: Any, label: str) -> str:
    """Normalize an optional outer Markdown fence without altering its content."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{label} response is empty")
    text = raw.strip()
    outer_fence = re.match(
        r"^(`{3,}|~{3,})(?:markdown|md)?[ \t]*\r?\n([\s\S]*?)\r?\n\1[ \t]*$",
        text,
        re.IGNORECASE,
    )
    if outer_fence:
        text = outer_fence.group(2).strip()
    # Agent responses may include a short preface before the report. Preserve
    # the complete response and require a Markdown heading anywhere in it.
    visible_markdown = re.sub(
        r"(?ms)^[ \t]{0,3}(```|~~~)[^\n]*\n.*?^[ \t]{0,3}\1[ \t]*$",
        "",
        text,
    )
    if not re.search(r"(?m)^#{1,6}[ \t]+\S", visible_markdown):
        raise ValueError(f"{label} response must be Markdown")
    return _normalize_finding_markdown(text)


def _format_retry_prompt(base_prompt: str, error: Exception | str, raw: str, stage: str) -> str:
    """Retry a technical format failure while preserving the original model output."""
    return base_prompt + "\n\n" + render_prompt_template(
        "format-retry.md", STAGE=stage, ERROR=str(error), RAW=raw, TAG=stage.upper().replace("-", "_"),
    )


def _normalize_finding_markdown(markdown: str) -> str:
    """Normalize only finding heading levels and explicit metadata list structure.

    This is formatting-only: source words and values are retained. The original
    model response is persisted separately before this function is called.
    """
    lines = markdown.splitlines(keepends=True)
    normalized: list[str] = []
    in_finding = False
    fence_char: str | None = None

    for original_line in lines:
        line = original_line
        content = line.rstrip("\r\n")
        newline = line[len(content):]
        fence = re.match(r"^[ \t]{0,3}(```|~~~)", content)
        if fence_char is not None:
            normalized.append(line)
            if fence and fence.group(1)[0] == fence_char:
                fence_char = None
            continue
        if fence:
            fence_char = fence.group(1)[0]
            normalized.append(line)
            continue

        bold_finding = re.match(
            r"^[ \t]*\*\*(F-(?:\d+-\d+|\d{2,})[ \t]+\[[ABC]\][ \t]+[^*\r\n]+)\*\*[ \t]*$",
            content,
        )
        if bold_finding:
            content = "### " + bold_finding.group(1)

        heading = re.match(r"^(#{1,6})([ \t]+.*)$", content)
        if heading:
            hashes, tail = heading.groups()
            is_finding = re.search(r"\bF-(?:\d+-\d+|\d{2,})\b", tail) is not None
            if is_finding:
                if len(hashes) != 3:
                    content = "###" + tail
                in_finding = True
            elif len(hashes) <= 3:
                in_finding = False

        if in_finding:
            labels = list(FINDING_METADATA_LABEL.finditer(content))
            if labels:
                first = labels[0]
                prefix = content[:first.start()]
                has_list_prefix = re.fullmatch(r"[ \t]*[-*+][ \t]*", prefix) is not None
                chunks = [content[label.start():labels[index + 1].start()]
                          for index, label in enumerate(labels[:-1])]
                chunks.append(content[labels[-1].start():])
                if prefix.strip() and not has_list_prefix:
                    pieces = [prefix + "\n- " + chunks[0]]
                else:
                    # The evidence parser expects these fields at column zero
                    # with a dash, so normalize list syntax only for known fields.
                    pieces = ["- " + chunks[0]]
                # Split subsequent explicit metadata labels onto list lines. Keep
                # delimiters and every source character on the preceding segment.
                pieces.extend("- " + chunk for chunk in chunks[1:])
                content = "\n".join(pieces)
                if newline:
                    content = content.replace("\n", newline)
        normalized.append(content + newline)
    return "".join(normalized)


def _check_finding_heading_levels(markdown: str) -> None:
    """Require every Markdown heading that defines an F-ID to use level three."""
    visible = re.sub(
        r"(?ms)^[ \t]{0,3}(```|~~~)[^\n]*\n.*?^[ \t]{0,3}\1[ \t]*$",
        "",
        markdown,
    )
    invalid = [match for match in FINDING_HEADING.finditer(visible) if len(match.group(1)) != 3]
    if invalid:
        raise ValueError(
            "Finding headings that define F-IDs must use exactly three # characters (###); "
            "please return the Markdown with each finding heading at level ###"
        )


def _check_project(markdown: str, project_index: int, materials: list[dict[str, Any]],
                   rule_severities: dict[str, str] | None = None) -> list[str]:
    """Check required section content, source mentions, and ID namespace only."""
    _check_finding_heading_levels(markdown)
    if not re.search(r"(?m)^##[ \t]*项目(?:[ \t]*.*)$", markdown):
        raise ValueError("Project response is missing its project heading")
    section_matches: dict[str, re.Match[str]] = {}
    for section in SECTIONS:
        match = re.search(rf"(?m)^###[ \t]+{re.escape(section)}[ \t]*$", markdown)
        if not match:
            raise ValueError(f"Project response is missing section {section}")
        section_matches[section] = match
    section_positions = [match.start() for match in section_matches.values()]
    for section in SECTIONS:
        match = section_matches[section]
        next_positions = [position for position in section_positions if position > match.start()]
        end = min(next_positions, default=len(markdown))
        if not markdown[match.end():end].strip():
            raise ValueError(f"Project response section has empty content: {section}")
    for material in materials:
        reference_id = material["reference_id"]
        filename = material["filename"]
        identified = re.search(rf"(?<![A-Za-z0-9_]){re.escape(reference_id)}(?![A-Za-z0-9_])", markdown)
        if not identified and filename not in markdown:
            raise ValueError(f"Project response must identify material {reference_id} or filename {filename}")
    identifiers = [match.group(1) for match in FINDING.finditer(markdown)]
    numbers: list[int] = []
    for value in identifiers:
        separated = re.fullmatch(r"F-(\d+)-(\d+)", value)
        legacy = re.fullmatch(r"F-(\d{3})(\d{3})", value)
        if separated and int(separated.group(1)) == project_index:
            numbers.append(int(separated.group(2)))
        elif legacy and project_index <= 999 and int(legacy.group(1)) == project_index:
            numbers.append(int(legacy.group(2)))
        else:
            raise ValueError(
                f"Project finding IDs must use namespace F-{project_index:03d}-<sequence>"
            )
    if len(numbers) != len(set(numbers)):
        raise ValueError("Project finding IDs must be unique")
    return identifiers


def _check_global(markdown: str, rule_ids: list[str] | None,
                  rule_severities: dict[str, str] | None = None,
                  project_finding_ids: set[str] | None = None) -> str:
    """Use the existing coverage validator, then check global finding namespaces."""
    _check_finding_heading_levels(markdown)
    expected_details = (project_finding_ids or set()) | {match.group(1) for match in FINDING.finditer(markdown)}
    table_ids: set[str] = set()
    table_seen = False
    identity_column: int | None = None
    for line in markdown.splitlines():
        if not line.lstrip().startswith("|"):
            identity_column = None
            continue
        cells = [cell.strip().strip("`* ") for cell in line.strip().strip("|").split("|")]
        if any(re.fullmatch(r"复核结果(?:[（(][^）)]*[）)])?", cell) for cell in cells):
            table_seen = True
            identity_column = next((cells.index(label) for label in ("序号/FID", "FID", "问题编号", "问题ID", "候选编号", "序号") if label in cells), 0)
            continue
        if identity_column is not None and identity_column < len(cells):
            match = re.search(r"\b(F-(?:\d+-\d+|\d{2,}))\b", cells[identity_column])
            if match:
                if match.group(1) in table_ids:
                    raise ValueError(f"Duplicate final disposition: {match.group(1)}")
                table_ids.add(match.group(1))
    if table_seen:
        missing = sorted(expected_details - table_ids)
        if missing:
            raise ValueError("Global report is missing final dispositions: " + ", ".join(missing))
        unknown = sorted(table_ids - expected_details)
        if unknown:
            raise ValueError("Global report has final dispositions without detailed evidence: " + ", ".join(unknown))
    if project_finding_ids:
        # Keep repeated review prose without creating a second finding heading
        # for the same source candidate preserved in the project appendix.
        markdown = FINDING.sub(
            lambda match: "**分项问题复核：" + match.group(0).removeprefix("### ") + "**"
            if match.group(1) in project_finding_ids else match.group(0), markdown,
        )
    from run_document_audit import validate_markdown
    normalized = validate_markdown(markdown, required_rule_ids=rule_ids)
    identifiers = [match.group(1) for match in FINDING.finditer(normalized)]
    numbers: list[int] = []
    for value in identifiers:
        separated = re.fullmatch(r"F-(\d+)-(\d+)", value)
        legacy = re.fullmatch(r"F-000(\d{3})", value)
        if separated and int(separated.group(1)) == 0:
            numbers.append(int(separated.group(2)))
        elif legacy:
            numbers.append(int(legacy.group(1)))
        else:
            raise ValueError("Global finding IDs must use namespace F-000-<sequence>")
    if len(numbers) != len(set(numbers)):
        raise ValueError("Global finding IDs must be unique")
    return normalized


def _materials_state(materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Record source identifiers and hashes without copying material contents."""
    result = []
    for index, item in enumerate(materials, 1):
        content_hash = hashlib.sha256(str(item.get("content", "")).encode("utf-8")).hexdigest()
        result.append({
            "reference_id": f"M{index:02d}",
            "filename": item.get("filename"),
            "kind": item.get("kind"),
            "sha256": item.get("sha256"),
            "content_sha256": content_hash,
        })
    return result


async def execute_audit(
    report_text: str,
    materials: list[dict[str, Any]],
    page_count: int,
    submit: Submit,
    output_dir: Path,
    on_progress: Progress | None = None,
    *,
    rules_dir: Path | None = None,
) -> str:
    """Identify projects, review them concurrently, and request global synthesis.

    All business findings and judgments come from the LLM responses. Local logic
    only slices marked pages, validates response containers, saves originals, and
    assembles the final Markdown.
    """
    if not isinstance(page_count, int) or isinstance(page_count, bool) or page_count < 1:
        raise ValueError("page_count must be a positive integer")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    project_dir = output_dir / "projects"
    project_dir.mkdir(exist_ok=True)
    index_builder, project_builder, summary_builder = _load_builders()
    llm_materials = [
        {**item, "reference_id": f"M{index:02d}"}
        for index, item in enumerate(materials, 1)
    ]
    material_state = _materials_state(materials)
    for item, state in zip(llm_materials, material_state):
        item["reference_id"] = state["reference_id"]
    manifest: dict[str, Any] = {
        "status": "running", "page_count": page_count, "materials": material_state,
        "index": {"status": "pending", "attempts": []},
        "projects": [], "summary": {"status": "pending", "attempts": []}, "requests": [],
    }
    manifest_path = output_dir / "workflow.json"

    async def send(
        stage: str, prompt: str, response_path: Path, source_pages: list[int],
        source_materials: list[str],
    ) -> str:
        prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        retryable_error_codes = {"text_model_incomplete", "text_model_empty"}
        for attempt in (1, 2):
            request_record = {
                "stage": stage,
                "attempt": attempt,
                "source_pages": source_pages,
                "response_file": str(response_path.relative_to(output_dir)),
                "source_materials": source_materials,
                "prompt_sha256": prompt_sha256,
                "prompt_characters": len(prompt),
                "status": "running",
            }
            manifest["requests"].append(request_record)
            _save_json(manifest_path, manifest)
            try:
                raw = await submit(prompt)
                if not isinstance(raw, str):
                    raise TypeError("submit callback must return a string")
                response_sha256 = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                if not raw.strip():
                    request_record.update(
                        status="failed", error_code="text_model_empty",
                        response_sha256=response_sha256, response_characters=len(raw),
                    )
                    if attempt == 1:
                        _save_json(manifest_path, manifest)
                        continue
                    raise RuntimeError("Text model returned an empty response after retry")
                response_path.parent.mkdir(parents=True, exist_ok=True)
                response_path.write_text(raw, encoding="utf-8")
                request_record["status"] = "received"
                request_record["response_sha256"] = response_sha256
                return raw
            except asyncio.CancelledError:
                request_record["status"] = "cancelled"
                raise
            except Exception as exc:
                error_code = getattr(exc, "code", None)
                retryable = isinstance(error_code, str) and error_code in retryable_error_codes
                if retryable:
                    request_record["error_code"] = error_code
                request_record["status"] = "failed"
                request_record["error_type"] = type(exc).__name__
                if attempt == 1 and retryable:
                    _save_json(manifest_path, manifest)
                    continue
                raise
            finally:
                _save_json(manifest_path, manifest)
        raise RuntimeError("Text model request exhausted its retry budget")

    try:
        page_map = _pages(report_text, page_count)
        from _rules import load_rules
        active_rules = load_rules(Path(rules_dir) if rules_dir is not None else None)
        rule_ids = active_rules.ids
        rule_severities = active_rules.severity
        manifest["rule_ids"] = rule_ids
        await _emit(on_progress, "index", 0, 1, "识别报告项目目录")
        index: dict[str, Any] | None = None
        if page_count <= 32:
            base_index_prompt = index_builder(report_text, page_count)
            index_error: ValueError | None = None
            for attempt in range(2):
                name = "index-raw.txt" if attempt == 0 else "index-retry-raw.txt"
                entry = {"response_file": name, "status": "pending"}
                manifest["index"]["attempts"].append(entry)
                _save_json(manifest_path, manifest)
                prompt = base_index_prompt
                if attempt:
                    prompt += "\n\n" + render_prompt_template("index-retry.md", ERROR=str(index_error))
                try:
                    raw = await send("index", prompt, output_dir / name, list(range(1, page_count + 1)), [])
                except asyncio.CancelledError:
                    entry["status"] = "cancelled"
                    manifest["index"]["status"] = "cancelled"
                    _save_json(manifest_path, manifest)
                    raise
                except Exception as exc:
                    entry.update({"status": "failed", "error_type": type(exc).__name__})
                    manifest["index"]["status"] = "failed"
                    _save_json(manifest_path, manifest)
                    raise
                entry["status"] = "received"
                try:
                    index = _parse_index(raw, page_count)
                    entry["status"] = "complete"
                    manifest["index"]["status"] = "complete"
                    break
                except ValueError as exc:
                    entry["status"] = "invalid_format"
                    entry["error"] = str(exc)
                    index_error = exc
                    if attempt:
                        manifest["index"]["status"] = "failed"
                        raise
                    _save_json(manifest_path, manifest)
        else:
            chunk_builder, merge_builder = _load_chunk_index_builders()
            index = await _run_chunked_index(
                page_map, page_count, chunk_builder, merge_builder,
                send, output_dir, manifest, manifest_path, on_progress,
            )
        if index is None:
            raise ValueError("Directory response could not be validated")
        manifest["index"]["status"] = "complete"
        _save_json(output_dir / "index.json", index)
        _save_json(manifest_path, manifest)
        await _emit(on_progress, "index", 1, 1, "项目目录已读取")

        projects = index["projects"]
        first_project_page = min((item["page_start"] for item in projects), default=page_count + 1)
        frontmatter = "\n\n".join(page_map[number] for number in range(1, first_project_page))
        records = []
        for project_index, project in enumerate(projects, 1):
            records.append({
                **project, "project_index": project_index,
                "source_pages": [project["page_start"], project["page_end"]],
                "response_file": f"projects/{project_index:03d}-raw.md",
                "status": "pending", "attempts": [],
            })
        manifest["projects"] = records
        _save_json(manifest_path, manifest)
        project_abort = asyncio.Event()
        completed = 0

        async def review_one(project_index: int, project: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
            nonlocal completed
            project_pages = list(range(project["page_start"], project["page_end"] + 1))
            selected_text = "\n\n".join(page_map[number] for number in project_pages)
            prompt = project_builder(
                project, selected_text, frontmatter, llm_materials, project_index,
                **({"rules_dir": rules_dir} if rules_dir is not None else {}),
            )
            record["source_materials"] = [item["reference_id"] for item in llm_materials]
            last_error: ValueError | None = None
            previous_raw: str | None = None
            normalized: str | None = None
            try:
                if project_abort.is_set():
                    raise asyncio.CancelledError
                for attempt in range(2):
                    name = f"{project_index:03d}-raw.md" if attempt == 0 else f"{project_index:03d}-retry-raw.md"
                    entry = {"response_file": f"projects/{name}", "status": "pending"}
                    record["attempts"].append(entry)
                    request_prompt = prompt if attempt == 0 else _format_retry_prompt(
                        prompt, last_error or "格式不符合要求", previous_raw or "", "project-review"
                    )
                    await _emit(on_progress, "project-review", 0, 1,
                                f"审核检测项目 {project['id']}（第{attempt + 1}次）")
                    raw = await send(
                        f"project-review:{project['id']}", request_prompt, project_dir / name,
                        sorted(set(range(1, first_project_page)) | set(project_pages)),
                        [item["reference_id"] for item in llm_materials],
                    )
                    entry["status"] = "received"
                    try:
                        normalized = _markdown(raw, f"Project {project['id']}")
                        identifiers = _check_project(normalized, project_index, llm_materials, rule_severities)
                        entry["status"] = "complete"
                        record.update(
                            status="complete",
                            response_file=f"projects/{name}",
                            completed_response_file=f"projects/{name}",
                            final_sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                            issue_ids=identifiers,
                            markdown=normalized,
                        )
                        _save_json(manifest_path, manifest)
                        await _emit(on_progress, "project-review", 1, 1,
                                    f"项目 {project['id']} 审核完成")
                        return {"project_id": project["id"], "project_index": project_index,
                                "markdown": normalized}
                    except ValueError as exc:
                        entry["status"] = "invalid_format"
                        entry["error_type"] = type(exc).__name__
                        entry["error"] = str(exc)
                        last_error = exc
                        previous_raw = raw
                        _save_json(manifest_path, manifest)
                        if attempt:
                            raise
                raise ValueError(f"Project {project['id']} response failed validation")
            except asyncio.CancelledError:
                record["status"] = "cancelled"
                record["error_type"] = "CancelledError"
                _save_json(manifest_path, manifest)
                raise
            except Exception as exc:
                project_abort.set()
                record["status"] = "failed"
                record["error_type"] = type(exc).__name__
                if isinstance(exc, ValueError):
                    record["error"] = str(exc)
                _save_json(manifest_path, manifest)
                raise
            finally:
                completed += 1
                await _emit(on_progress, "projects", completed, len(projects), f"项目 {project['id']} 技术处理结束")

        await _emit(on_progress, "projects", 0, len(projects), "开始处理项目")
        project_tasks = [
            asyncio.create_task(review_one(i, project, record))
            for i, (project, record) in enumerate(zip(projects, records), 1)
        ]
        try:
            if project_tasks:
                done, pending = await asyncio.wait(project_tasks, return_when=asyncio.FIRST_EXCEPTION)
                first_failures = []
                saw_cancellation = False
                for task in done:
                    if task.cancelled():
                        saw_cancellation = True
                        continue
                    error = task.exception()
                    if error is not None:
                        first_failures.append(error)
                if first_failures or saw_cancellation:
                    project_abort.set()
                    for task in pending:
                        task.cancel()
                results = await asyncio.gather(*project_tasks, return_exceptions=True)
            else:
                results = []
        except asyncio.CancelledError:
            project_abort.set()
            for task in project_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*project_tasks, return_exceptions=True)
            for task, record in zip(project_tasks, records):
                if task.cancelled() and record["status"] == "pending":
                    record.update(status="cancelled", error_type="CancelledError")
            manifest["status"] = "cancelled"
            manifest["failure_stage"] = "projects"
            _save_json(manifest_path, manifest)
            raise

        failures = [result for result in results
                    if isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError)]
        cancellations = [result for result in results if isinstance(result, asyncio.CancelledError)]
        if failures:
            for result, record in zip(results, records):
                if isinstance(result, asyncio.CancelledError) and record["status"] == "pending":
                    record.update(status="cancelled", error_type="CancelledError")
                elif isinstance(result, BaseException) and record["status"] == "pending":
                    record["status"] = "failed"
                    record["error_type"] = type(result).__name__
            manifest["status"] = "failed"
            manifest["failure_stage"] = "projects"
            manifest["summary"]["status"] = "skipped"
            _save_json(manifest_path, manifest)
            first = failures[0]
            detail = f": {first}" if isinstance(first, ValueError) else ""
            raise RuntimeError(
                f"project review failed ({type(first).__name__}{detail}); no complete audit was published"
            ) from first
        if cancellations:
            manifest["status"] = "cancelled"
            manifest["failure_stage"] = "projects"
            _save_json(manifest_path, manifest)
            raise cancellations[0]
        reviews = [result for result in results if isinstance(result, dict)]

        await _emit(on_progress, "summary", 0, 1, "汇总全局审核")
        summary_prompt = summary_builder(
            report_text, llm_materials, page_count, reviews,
            **({"rules_dir": rules_dir} if rules_dir is not None else {}),
        )
        if not projects:
            summary_prompt += "\n\n" + render_prompt_template("no-projects.md", REASON=str(index["no_projects_reason"]))
        summary_error: Exception | None = None
        previous_summary_raw: str | None = None
        main_markdown: str | None = None
        for attempt in range(2):
            name = "audit-main-raw.md" if attempt == 0 else "audit-main-retry-raw.md"
            entry = {"response_file": name, "status": "pending"}
            manifest["summary"]["attempts"].append(entry)
            _save_json(manifest_path, manifest)
            prompt = summary_prompt if attempt == 0 else _format_retry_prompt(
                summary_prompt, summary_error or "格式不符合要求", previous_summary_raw or "", "summary"
            )
            try:
                raw = await send(
                    "summary", prompt, output_dir / name, list(range(1, page_count + 1)),
                    [item["reference_id"] for item in llm_materials],
                )
            except asyncio.CancelledError:
                entry["status"] = "cancelled"
                manifest["summary"]["status"] = "cancelled"
                _save_json(manifest_path, manifest)
                raise
            except Exception as exc:
                entry.update({"status": "failed", "error_type": type(exc).__name__})
                manifest["summary"]["status"] = "failed"
                _save_json(manifest_path, manifest)
                raise
            entry["status"] = "received"
            try:
                main_markdown = _check_global(
                    _markdown(raw, "Global summary"), rule_ids, rule_severities,
                    project_finding_ids={match.group(1) for review in reviews for match in FINDING.finditer(review["markdown"])},
                )
                entry["status"] = "complete"
                manifest["summary"]["status"] = "complete"
                manifest["summary"]["completed_response_file"] = name
                break
            except ValueError as exc:
                entry["status"] = "invalid_format"
                entry["error"] = str(exc)
                summary_error = exc
                previous_summary_raw = raw
                _save_json(manifest_path, manifest)
                if attempt:
                    manifest["summary"]["status"] = "failed"
                    raise
        if main_markdown is None:
            raise ValueError("Global summary could not be validated")
        await _emit(on_progress, "summary", 1, 1, "全局审核已校验")

        appendix = ["# 附录：分项目审核原文"]
        appendix.extend(_markdown(item["markdown"], "Project") for item in reviews)
        combined = main_markdown.rstrip() + "\n\n" + "\n\n---\n\n".join(appendix) + "\n"
        issue_ids = [match.group(1) for match in FINDING.finditer(combined)]
        if len(issue_ids) != len(set(issue_ids)):
            raise ValueError("Combined report contains duplicate finding identifiers")
        target = output_dir / "audit.md"
        temp = output_dir / "audit.md.tmp"
        temp.write_text(combined, encoding="utf-8")
        temp.replace(target)
        manifest["status"] = "complete"
        manifest["summary"]["status"] = "complete"
        manifest["report_file"] = "audit.md"
        _save_json(manifest_path, manifest)
        await _emit(on_progress, "complete", 1, 1, "分项目与全局审核完成")
        return combined
    except asyncio.CancelledError:
        manifest["status"] = "cancelled"
        _save_json(manifest_path, manifest)
        raise
    except Exception:
        if manifest["status"] == "running":
            manifest["status"] = "failed"
        _save_json(manifest_path, manifest)
        raise
