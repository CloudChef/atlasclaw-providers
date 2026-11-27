#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run local preparation, a configured LLM audit, and local PDF delivery.

Python dependencies and model credentials come from the AtlasClaw runtime.
Existing skill programs are called without changing their implementations.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import html
import hashlib
import json
import os
import re
import sys
import inspect
import subprocess
from pathlib import Path
from typing import Any, Callable, Awaitable

import httpx
from dotenv import dotenv_values

from audit_preparation import prepare_report, prepare_visual_pdf, report_text


async def _emit_progress(callback, stage: str, completed: int, total: int, message: str) -> None:
    """Send a progress event to either synchronous or asynchronous callers."""
    if callback is None:
        return
    result = callback({"stage": stage, "completed": completed, "total": total, "message": message})
    if inspect.isawaitable(result):
        await result


def configured_model(config_path: Path, token_id: str | None = None) -> dict[str, Any]:
    """Resolve a Core model token and dotenv values without logging credentials."""
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    environment = {**dotenv_values(config_path.parent / ".env"), **os.environ}

    def resolve(value: Any) -> str:
        return re.sub(r"\$\{([^}]+)\}", lambda item: str(environment.get(item[1]) or ""), str(value or ""))

    settings = config.get("model", {})
    selected = token_id or settings.get("primary")
    token = next((item for item in settings.get("tokens", []) if item.get("id") == selected), None)
    if token is None:
        raise ValueError("Selected model token is not configured")
    result = {name: resolve(token.get(name)) for name in ("id", "model", "api_key", "base_url", "api_type")}
    result["provider"] = resolve(token.get("provider") or "")
    result["max_tokens"] = settings.get("max_tokens")
    if not all(result.get(name) for name in ("model", "api_key", "base_url")):
        raise ValueError("Selected model configuration is incomplete")
    if result["api_type"] not in ("", "openai"):
        raise ValueError("This skill CLI requires an OpenAI-compatible model endpoint")
    return result


def _effective_max_tokens(model: dict[str, Any], explicit: int | None = None) -> int | None:
    """Resolve a user-specified output limit without imposing a default cap."""
    value = explicit if explicit is not None else model.get("max_tokens")
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("max_output_tokens must be a positive integer")
    try:
        resolved = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_output_tokens must be a positive integer") from exc
    if resolved < 1:
        raise ValueError("max_output_tokens must be a positive integer")
    return resolved


def _delivery_file_exists(value: Any, report_dir: Path) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    root = report_dir.resolve()
    path = Path(value)
    resolved = (path if path.is_absolute() else root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return False
    return resolved.is_file() and resolved.stat().st_size > 0


def _validate_delivery_result(result: Any, report_dir: Path, *, allow_incomplete: bool = False) -> list[str]:
    problems: list[str] = []
    if not isinstance(result, dict):
        raise RuntimeError("Local report delivery is incomplete: invalid delivery result")
    if not _delivery_file_exists(result.get("report_pdf"), report_dir):
        problems.append("report PDF is missing or empty")
    for key in ("errors", "evidence_errors"):
        value = result.get(key)
        if not isinstance(value, list) or value:
            problems.append(f"{key} is missing or non-empty")
    findings = result.get("findings")
    if not isinstance(findings, list):
        problems.append("findings is missing or invalid")
    else:
        for index, finding in enumerate(findings, start=1):
            label = finding.get("id") if isinstance(finding, dict) else None
            label = str(label or f"finding #{index}")
            if not isinstance(finding, dict) or finding.get("status") != "captured":
                problems.append(f"{label} was not captured")
                continue
            if not _delivery_file_exists(finding.get("image"), report_dir):
                problems.append(f"{label} main evidence image is missing or empty")
            images = finding.get("images")
            if not isinstance(images, list) or not images:
                problems.append(f"{label} has no evidence images")
                continue
            for image in images:
                if not isinstance(image, dict):
                    problems.append(f"{label} has an invalid evidence image entry")
                    continue
                if not _delivery_file_exists(image.get("image"), report_dir):
                    problems.append(f"{label} evidence image is missing or empty")
                if not _delivery_file_exists(image.get("reference"), report_dir):
                    problems.append(f"{label} evidence reference is missing or empty")
    if problems and not allow_incomplete:
        raise RuntimeError("Local report delivery is incomplete: " + "; ".join(problems))
    return problems


def _safe_request_error(message: str, usage: dict[str, Any] | None = None) -> RuntimeError:
    error = RuntimeError(message)
    error.usage = usage or {}
    return error


async def request_markdown(
    model: dict[str, Any], prompt: str, max_tokens: int | None = None,
) -> tuple[str, dict]:
    """Call the configured model API once and collect its Markdown response.

    API error details are intentionally excluded from logs because remote error
    bodies can contain submitted documents. Responses and usage are saved locally.
    """
    payload = {"model": model["model"], "messages": [
        {"role": "system", "content": (Path(__file__).resolve().parent.parent / "references/audit-system.md").read_text(encoding="utf-8")},
        {"role": "user", "content": prompt},
    ], "stream": True, "stream_options": {"include_usage": True}}
    effective_max_tokens = _effective_max_tokens(model, max_tokens)
    if effective_max_tokens is not None:
        payload["max_tokens"] = effective_max_tokens
    chunks: list[str] = []
    usage: dict = {}
    finish = None
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", model["base_url"].rstrip("/") + "/chat/completions",
                                 headers={"Authorization": "Bearer " + model["api_key"]}, json=payload) as response:
            if response.status_code != 200:
                raise _safe_request_error(f"Model API rejected audit request (HTTP {response.status_code})", usage)
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                value = line[5:].strip()
                if value == "[DONE]":
                    break
                try:
                    event = json.loads(value)
                except json.JSONDecodeError:
                    raise _safe_request_error("Model API returned a malformed stream event", usage) from None
                if event.get("error"):
                    raise _safe_request_error("Model API reported a streaming failure", usage)
                if event.get("usage"):
                    usage = event["usage"]
                for choice in event.get("choices", []):
                    text = choice.get("delta", {}).get("content")
                    if isinstance(text, str):
                        chunks.append(text)
                    if choice.get("finish_reason") is not None:
                        finish = choice["finish_reason"]
    text = "".join(chunks)
    if finish != "stop" or not text.strip():
        raise _safe_request_error(
            f"Model response is incomplete (finish_reason={finish or 'missing'}, has_content={bool(text.strip())})",
            usage,
        )
    return text, usage


async def request_visual(
    model: dict[str, Any], prompt: str, images: list[dict[str, Any]], max_tokens: int | None = None,
) -> str:
    """Call the configured image-capable model with prepared page images."""
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for image in images:
        media_type = str(image.get("media_type") or "image/png")
        encoded = base64.b64encode(image["data"]).decode("ascii")
        content.append({"type": "text", "text": f"Image {image.get('identifier', '')} (Page {image.get('page', '')})"})
        content.append({"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{encoded}"}})
    payload: dict[str, Any] = {
        "model": model["model"],
        "messages": [
            {"role": "system", "content": (Path(__file__).resolve().parent.parent / "references/audit-system.md").read_text(encoding="utf-8")},
            {"role": "user", "content": content},
        ],
        "stream": False,
    }
    effective_max_tokens = _effective_max_tokens(model, max_tokens)
    if effective_max_tokens is not None:
        payload["max_tokens"] = effective_max_tokens
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            response = await client.post(
                model["base_url"].rstrip("/") + "/chat/completions",
                headers={"Authorization": "Bearer " + model["api_key"]},
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise _safe_request_error(f"Visual model API transport failed ({type(exc).__name__})") from None
    if response.status_code != 200:
        raise _safe_request_error(f"Visual model rejected audit request (HTTP {response.status_code})", {})
    try:
        data = response.json()
    except (TypeError, ValueError):
        raise _safe_request_error("Visual model returned malformed JSON") from None
    if not isinstance(data, dict):
        raise _safe_request_error("Visual model returned an invalid response")
    choices = data.get("choices")
    choice = choices[0] if isinstance(choices, list) and choices else {}
    if not isinstance(choice, dict):
        choice = {}
    message = choice.get("message")
    text = message.get("content") if isinstance(message, dict) else None
    finish_reason = choice.get("finish_reason")
    if finish_reason != "stop" or not isinstance(text, str) or not text.strip():
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        raise _safe_request_error(
            f"Visual model response is incomplete (finish_reason={finish_reason or 'missing'}, "
            f"has_content={bool(isinstance(text, str) and text.strip())})",
            usage,
        )
    return text


def validate_markdown(markdown: str, required_rule_ids: list[str] | None = None,
                      rule_severities: dict[str, str] | None = None) -> str:
    """Check the output container only, without making audit judgments."""
    text = markdown.strip()
    outer_fence = re.match(
        r"^(`{3,}|~{3,})(?:markdown|md)?[ \t]*\r?\n([\s\S]*?)\r?\n\1[ \t]*$",
        text, re.IGNORECASE,
    )
    if outer_fence:
        text = outer_fence.group(2).strip()
    visible = re.sub(r"(?ms)^[ \t]{0,3}(```|~~~)[^\n]*\n.*?^[ \t]{0,3}\1[ \t]*$", "", text)
    if not re.search(r"(?m)^#{1,6}[ \t]+\S", visible):
        raise ValueError("Model response is not a complete Markdown report")
    from _rules import load_rules
    incomplete = []
    rule_ids = load_rules().ids if required_rule_ids is None else required_rule_ids
    coverage_heading = re.search(r"(?m)^#{1,2}[^\n]*检查覆盖表[^\n]*$", text)
    if coverage_heading:
        next_heading = re.search(r"(?m)^#{1,2}\s+", text[coverage_heading.end():])
        coverage = text[coverage_heading.end():
                        coverage_heading.end() + next_heading.start() if next_heading else len(text)]
    else:
        # Compatibility for older callers/tests that pass a minimal table without
        # the current report-template section heading.
        coverage = text
    for rule_id in rule_ids:
        rows = re.findall(rf"^\|\s*`?{re.escape(rule_id)}`?\s*\|([^\n]*)$", coverage, re.MULTILINE)
        cells = [cell.strip().strip("`* ") for cell in rows[0].rstrip().rstrip("|").split("|")] if rows else []
        if (len(rows) != 1 or len(cells) < 5
                or not re.match(r"^(?:不通过|通过|不适用|待复核|证据不足)(?:$|[（(：:,，\s])", cells[3])
                or not cells[4] or re.search(r"<[^>]+>", "|".join(cells))):
            incomplete.append(rule_id)
    if incomplete:
        raise ValueError("Model response has missing or incomplete coverage rows: " + ", ".join(incomplete))
    from audit_delivery import FINDING_RE
    finding_ids = [match.group(1) for match in FINDING_RE.finditer(text)]
    if len(finding_ids) != len(set(finding_ids)):
        raise ValueError("Model response contains duplicate finding identifiers")
    return text


def _report_completeness_warnings(markdown: str, required_rule_ids: list[str]) -> list[str]:
    """Describe missing model output without interpreting any business result."""
    warnings: list[str] = []
    overall_match = re.search(r"(?m)^\*\*总评\s*[：:]\s*([^*\n]+)\*\*", markdown)
    if not overall_match or not overall_match.group(1).strip() or "<" in overall_match.group(1):
        warnings.append("overall_verdict_missing")
    if "模型未提供部分候选处置结论" in markdown:
        warnings.append("candidate_disposition_missing")
    coverage_heading = re.search(r"(?m)^#{1,2}[^\n]*检查覆盖表[^\n]*$", markdown)
    coverage = markdown[coverage_heading.end():] if coverage_heading else ""
    if coverage_heading:
        next_heading = re.search(r"(?m)^#{1,2}\s+", coverage)
        if next_heading:
            coverage = coverage[:next_heading.start()]
    else:
        warnings.append("coverage_table_missing")
    for rule_id in required_rule_ids:
        rows = re.findall(rf"^\|\s*`?{re.escape(rule_id)}`?\s*\|([^\n]*)$", coverage, re.MULTILINE)
        cells = [cell.strip().strip("`* ") for cell in rows[0].rstrip().rstrip("|").split("|")] if len(rows) == 1 else []
        if (len(rows) != 1 or len(cells) < 5
                or not re.match(r"^(?:不通过|通过|不适用|待复核|证据不足)(?:$|[（(：:,，\s])", cells[3])
                or not cells[4] or re.search(r"<[^>]+>", "|".join(cells))):
            warnings.append(f"coverage_row_missing:{rule_id}")
    return warnings


def _report_resource(name: str, **values: str) -> str:
    from audit_project_prompts import render_report_template
    return render_report_template(name, **values).strip()


def _coverage_rows(markdown: str, required_rule_ids: list[str]) -> dict[str, list[str]]:
    heading = re.search(r"(?m)^#{1,2}[^\n]*检查覆盖表[^\n]*$", markdown)
    if not heading:
        return {}
    tail = markdown[heading.end():]
    next_heading = re.search(r"(?m)^#{1,2}\s+", tail)
    coverage = tail[:next_heading.start()] if next_heading else tail
    return {
        rule_id: re.findall(
            rf"^\|\s*`?{re.escape(rule_id)}`?\s*\|[^\n]*$", coverage, re.MULTILINE,
        )
        for rule_id in required_rule_ids
    }


def _coverage_row_complete(rows: list[str]) -> bool:
    if len(rows) != 1:
        return False
    cells = [cell.strip().strip("`* ") for cell in rows[0].rstrip().rstrip("|").split("|")[2:]]
    return (
        len(cells) >= 5
        and bool(re.match(r"^(?:不通过|通过|不适用|待复核|证据不足)(?:$|[（(：:,，\s])", cells[3]))
        and bool(cells[4])
        and not re.search(r"<[^>]+>", "|".join(cells))
    )


def _source_rows_as_table_data(rows: list[str]) -> str:
    return "<br>".join(html.escape(row, quote=False).replace("|", "&#124;") for row in rows)


def normalize_publishable_report(
    markdown: str,
    required_rule_ids: list[str],
    rules_dir: Path | None = None,
    *,
    preserved_source_markdown: str | None = None,
) -> str:
    """Preserve model conclusions and mark every absent or malformed conclusion pending."""
    text = markdown.strip()
    outer_fence = re.match(
        r"^(`{3,}|~{3,})(?:markdown|md)?[ \t]*\r?\n([\s\S]*?)\r?\n\1[ \t]*$",
        text, re.IGNORECASE,
    )
    if outer_fence:
        text = outer_fence.group(2).strip()

    from _rules import load_rules
    rule_set = load_rules(rules_dir) if rules_dir is not None else load_rules()
    original = text
    if not re.search(r"(?m)^#{1,6}[ \t]+\S", text):
        text = _report_resource("incomplete-title.md") + "\n\n" + text

    verdict_match = re.search(r"(?m)^\*\*总评\s*[：:]\s*([^*\n]*?)\s*\*\*", text)
    verdict_missing = not verdict_match or not verdict_match.group(1).strip() or "<" in verdict_match.group(1)
    if verdict_missing:
        verdict_line = _report_resource("pending-overall.md")
        if verdict_match:
            text = text[:verdict_match.start()] + verdict_line + text[verdict_match.end():]
        else:
            total_heading = re.search(r"(?m)^#{1,3}[^\n]*总评[^\n]*$", text)
            if total_heading:
                following_heading = re.search(r"(?m)^#{1,3}\s+", text[total_heading.end():])
                insert_at = total_heading.end() + following_heading.start() if following_heading else len(text)
                text = text[:insert_at].rstrip() + "\n\n" + verdict_line + "\n\n" + text[insert_at:].lstrip()
            else:
                text = text.rstrip() + "\n\n" + _report_resource("pending-overall-section.md") + "\n\n" + verdict_line + "\n"

    coverage_heading = re.search(r"(?m)^#{1,2}[^\n]*检查覆盖表[^\n]*$", text)
    if coverage_heading:
        tail = text[coverage_heading.end():]
        next_heading = re.search(r"(?m)^#{1,2}\s+", tail)
        coverage_end = coverage_heading.end() + next_heading.start() if next_heading else len(text)
        coverage = text[coverage_heading.end():coverage_end]
    else:
        coverage_heading = None
        coverage_end = len(text)
        coverage = ""

    rows_by_rule: dict[str, list[str]] = {}
    preserved_source_rows = _coverage_rows(preserved_source_markdown or "", required_rule_ids)
    for rule_id in required_rule_ids:
        rows_by_rule[rule_id] = re.findall(
            rf"^\|\s*`?{re.escape(rule_id)}`?\s*\|[^\n]*$", coverage, re.MULTILINE,
        )
    pending_rows: list[str] = []
    preserved_rows: dict[str, str] = {}
    for rule_id in required_rule_ids:
        rows = rows_by_rule[rule_id]
        cells = [cell.strip().strip("`* ") for cell in rows[0].rstrip().rstrip("|").split("|")[2:]] if len(rows) == 1 else []
        source_rows = preserved_source_rows.get(rule_id, [])
        source_incomplete = bool(source_rows) and not _coverage_row_complete(source_rows)
        evidence_rows = source_rows if source_incomplete else (
            rows if rows and not _coverage_row_complete(rows) else []
        )
        valid = not source_incomplete and (
            len(rows) == 1 and len(cells) >= 5
            and bool(re.match(r"^(?:不通过|通过|不适用|待复核|证据不足)(?:$|[（(：:,，\s])", cells[3]))
            and bool(cells[4]) and not re.search(r"<[^>]+>", "|".join(cells))
        )
        if valid:
            preserved_rows[rule_id] = rows[0]
            continue
        rule = getattr(rule_set, "rules", {}).get(rule_id, {})
        evidence_cells = [cell.strip().strip("`* ") for cell in evidence_rows[0].rstrip().rstrip("|").split("|")[2:]] if evidence_rows else []
        row_cells = cells if cells else evidence_cells
        module = str((row_cells[0] if len(row_cells) > 0 else "") or rule.get("module") or _report_resource("pending-rule-module.md"))
        name = str((row_cells[1] if len(row_cells) > 1 else "") or rule.get("name") or rule.get("title") or _report_resource("pending-rule-name.md"))
        severity = str((row_cells[2] if len(row_cells) > 2 else "") or rule.get("severity") or _report_resource("pending-rule-severity.md"))
        status = _report_resource("pending-rule-status.md")
        if evidence_rows:
            reason = _report_resource(
                "pending-reason-preserved.md", ORIGINAL_ROWS=_source_rows_as_table_data(evidence_rows),
            )
        else:
            reason = _report_resource("pending-reason-missing.md" if not rows else "pending-reason-malformed.md")
        pending_rows.append(_report_resource(
            "pending-coverage-row.md", RULE_ID=rule_id, MODULE=module, CHECK=name,
            SEVERITY=severity, STATUS=status, REASON=reason,
        ))

    # Remove malformed and duplicate rows for required IDs; retain all other model content.
    if not coverage_heading:
        text = text.rstrip() + "\n\n" + _report_resource("pending-coverage-heading.md") + "\n\n"
        coverage_heading = re.search(r"(?m)^#{1,2}[^\n]*检查覆盖表[^\n]*$", text)
        assert coverage_heading is not None
        coverage_end = len(text)
        coverage = ""

    coverage_lines = coverage.splitlines()
    first_table_line = next((index for index, line in enumerate(coverage_lines) if line.lstrip().startswith("|")), None)
    if first_table_line is None:
        table_prefix = coverage_lines
        table_header = _report_resource("pending-coverage-header.md").splitlines()
        table_body: list[str] = []
        table_suffix: list[str] = []
    else:
        last_table_line = max(index for index, line in enumerate(coverage_lines) if line.lstrip().startswith("|"))
        table_prefix = coverage_lines[:first_table_line]
        table_suffix = coverage_lines[last_table_line + 1:]
        candidate_header = coverage_lines[first_table_line:first_table_line + 2]
        header_cells = [cell.strip() for cell in candidate_header[0].strip().strip("|").split("|")]
        separator_valid = len(candidate_header) == 2 and bool(re.fullmatch(r"\|?\s*[:|\-\s]+\|?", candidate_header[1]))
        if (len(header_cells) == 6 and "检查项" in header_cells
                and ({"结果", "结论"} & set(header_cells)) and separator_valid):
            table_header = candidate_header
            body_start = first_table_line + 2
        else:
            table_header = _report_resource("pending-coverage-header.md").splitlines()
            body_start = first_table_line
        table_body = []
        for line in coverage_lines[body_start:last_table_line + 1]:
            if not line.lstrip().startswith("|"):
                continue
            if "检查项" in line and ({"结果", "结论"} & set(line.strip().strip("|").split("|"))):
                continue
            required_match = next((rule_id for rule_id in required_rule_ids
                                   if re.match(rf"^\|\s*`?{re.escape(rule_id)}`?\s*\|", line)), None)
            if required_match is not None:
                if required_match in preserved_rows and line == preserved_rows[required_match]:
                    table_body.append(line)
                continue
            if re.fullmatch(r"\|?\s*[:|\-\s]+\|?", line):
                continue
            table_body.append(line)
    table_body.extend(pending_rows)
    table = "\n".join([*table_header, *table_body]).rstrip()
    prefix = "\n".join(table_prefix).rstrip()
    clean_coverage = (prefix + "\n\n" if prefix else "") + table + "\n"
    if table_suffix and any(line.strip() for line in table_suffix):
        clean_coverage += "\n" + "\n".join(table_suffix).strip() + "\n"
    text = text[:coverage_heading.end()] + "\n\n" + clean_coverage + text[coverage_end:]

    warnings = _report_completeness_warnings(original, required_rule_ids)
    if warnings or verdict_missing:
        if "报告已生成，部分结果待复核" not in text:
            notice = _report_resource("incomplete-notice.md")
            first_heading = re.search(r"(?m)^#{1,6}[ \t]+", text)
            insert_at = first_heading.start() if first_heading else 0
            text = text[:insert_at] + notice + "\n\n" + text[insert_at:]
    return text.strip()


def _apply_source_identity(markdown: str, source_metadata: dict[str, Any] | None) -> str:
    """Replace model-supplied upload identity with values from the document record."""
    if not source_metadata:
        return markdown
    section = re.search(r"(?m)^##\s*1[.、 ]*审核对象\s*$", markdown)
    filename = str(source_metadata.get("file_name") or "").replace("|", r"\|").replace("`", r"\`")
    size = source_metadata.get("size")
    sha256 = str(source_metadata.get("sha256") or "").strip()
    values: dict[str, str] = {}
    if filename:
        values["文件名"] = f"`{filename}`"
    if size is not None and str(size).strip():
        try:
            values["文件大小"] = f"{int(size):,} bytes"
        except (TypeError, ValueError):
            values["文件大小"] = str(size)
    if sha256:
        values["SHA-256"] = f"`{sha256}`"
    if not section:
        rows = "\n".join(
            _report_resource("source-identity-row.md", LABEL=label, VALUE=value)
            for label, value in values.items()
        )
        object_section = _report_resource("source-identity-section.md", ROWS=rows)
        title = re.search(r"(?m)^#{1,6}[ \t]+[^\n]+$", markdown)
        if title:
            return markdown[:title.end()] + "\n\n" + object_section + "\n\n" + markdown[title.end():].lstrip()
        return object_section + "\n\n" + markdown

    prefix = markdown[:section.start()]
    following = re.search(r"(?m)^#{1,2}\s+", markdown[section.end():])
    end = section.end() + following.start() if following else len(markdown)
    object_text = markdown[section.start():end]
    tail = markdown[end:]
    for label, value in values.items():
        pattern = re.compile(rf"(?m)^(\|\s*{re.escape(label)}\s*\|\s*)([^\n]*?)(\s*\|\s*)$")
        row = f"| {label} | {value} |"
        if pattern.search(object_text):
            object_text = pattern.sub(lambda match: f"{match.group(1)}{value}{match.group(3)}", object_text, count=1)
        else:
            object_text = object_text.rstrip() + "\n" + row + "\n"
    return prefix + object_text + tail


async def render_saved_report(
    raw_markdown: str,
    output_dir: Path,
    source_pdf: Path,
    required_rule_ids: list[str],
    *,
    rules_dir: Path | None = None,
    source_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Regenerate a saved audit report using local formatting and delivery only."""
    from audit_delivery import deliver_report

    output_dir.mkdir(parents=True, exist_ok=True)
    warnings = _report_completeness_warnings(raw_markdown, required_rule_ids)
    summary_path = output_dir / "audit-main-raw.md"
    summary_markdown = None
    if summary_path.is_file():
        summary_markdown = summary_path.read_text(encoding="utf-8")
        warnings.extend(_report_completeness_warnings(summary_markdown, required_rule_ids))
    prior_completion_path = output_dir / "completion.json"
    if prior_completion_path.is_file():
        try:
            prior_completion = json.loads(prior_completion_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            prior_completion = {}
        prior_warnings = prior_completion.get("warnings") if isinstance(prior_completion, dict) else []
        if isinstance(prior_warnings, list):
            warnings.extend(item for item in prior_warnings if isinstance(item, str))
    warnings = list(dict.fromkeys(warnings))
    normalized = normalize_publishable_report(
        raw_markdown, required_rule_ids, rules_dir=rules_dir,
        preserved_source_markdown=summary_markdown,
    )
    normalized = _apply_source_identity(normalized, source_metadata)
    normalized = normalized.replace("报告未完成", "报告已生成，部分结果待复核")
    if warnings and "报告已生成，部分结果待复核" not in normalized:
        normalized = _report_resource("incomplete-notice.md") + "\n\n" + normalized
    if warnings:
        block = _pipeline_incomplete_block(warnings)
        normalized = _insert_pipeline_incomplete_block(normalized, block)
    markdown_path = output_dir / "audit.md"
    markdown_path.write_text(normalized, encoding="utf-8")
    output_pdf = output_dir / "audit-report.pdf"
    try:
        result = await asyncio.to_thread(deliver_report, markdown_path, source_pdf, output_pdf)
    except Exception as exc:  # noqa: BLE001 - report regeneration remains explicitly reviewable
        result = {"report_pdf": None, "errors": [type(exc).__name__], "evidence_errors": [], "findings": []}
        warnings.append("pdf_delivery_failed")
    if not isinstance(result, dict):
        result = {"report_pdf": None, "errors": ["invalid_delivery_result"],
                  "evidence_errors": [], "findings": []}
    problems = _validate_delivery_result(result, output_dir, allow_incomplete=True)
    pdf_missing = not _delivery_file_exists(result.get("report_pdf"), output_dir)
    evidence_problems = [problem for problem in problems if problem != "report PDF is missing or empty"]
    fallback_source = markdown_path
    enriched_path = result.get("enriched_markdown")
    if isinstance(enriched_path, str) and enriched_path.strip():
        enriched_candidate = Path(enriched_path)
        if not enriched_candidate.is_absolute():
            enriched_candidate = output_dir / enriched_candidate
        if _delivery_file_exists(str(enriched_candidate), output_dir):
            fallback_source = enriched_candidate.resolve()
    if evidence_problems:
        warnings.append("delivery_evidence_incomplete")
        if fallback_source.is_file():
            content = fallback_source.read_text(encoding="utf-8")
            if "证据截图未完整生成" not in content:
                fallback_source.write_text(
                    content.rstrip() + "\n\n" + _report_resource("evidence-incomplete.md") + "\n",
                    encoding="utf-8",
                )
    if pdf_missing:
        warnings.extend(["pdf_delivery_failed", "pdf_render_fallback"])
        content = fallback_source.read_text(encoding="utf-8") if fallback_source.is_file() else normalized
        fallback_source = markdown_path
        markdown_path.write_text(
            content.rstrip() + "\n\n" + _report_resource("pdf-render-fallback.md") + "\n",
            encoding="utf-8",
        )
    warnings = list(dict.fromkeys(warnings))
    if evidence_problems or pdf_missing:
        await asyncio.to_thread(_render_report_pdf_fallback, fallback_source, output_pdf)
        result["report_pdf"] = str(output_pdf)
        result["pdf"] = str(output_pdf)
    result.update({
        "completion_status": "needs_review" if warnings else "complete",
        "warnings": warnings,
        "raw_response": "audit-raw.md" if (output_dir / "audit-raw.md").is_file() else None,
        "partial_response_files": sorted(
            path.relative_to(output_dir).as_posix()
            for path in output_dir.rglob("*-raw.*") if path.is_file()
        ),
    })
    (output_dir / "delivery.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "completion.json").write_text(
        json.dumps({key: result[key] for key in (
            "completion_status", "warnings", "raw_response", "partial_response_files",
        )}, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return result


def _incomplete_report_shell(
    output_dir: Path, failure_type: str, required_rule_ids: list[str], rules_dir: Path | None = None,
) -> str:
    """Load a visible incomplete-report shell and list saved partial responses."""
    partial_paths = sorted(path for path in output_dir.rglob("*-raw.*")
                           if path.is_file() and path.name != "audit-raw.md")
    partials = [path.relative_to(output_dir).as_posix() for path in partial_paths]
    partial_text = "\n".join(f"- `{path}`" for path in partials) if partials else _report_resource("no-partial-responses.md")
    shell = _report_resource("incomplete-audit.md", FAILURE_TYPE=failure_type, PARTIAL_FILES=partial_text)
    partial_appendix = []
    seen_finding_ids: set[str] = set()
    try:
        from audit_delivery import FINDING_RE
    except Exception:
        FINDING_RE = re.compile(r"(?!)")
    partial_paths.sort(key=lambda path: (
        0 if path.parent.name == "projects" else 1,
        0 if "retry" in path.name else 1,
        path.as_posix(),
    ))
    for path in partial_paths:
        body = path.read_text(encoding="utf-8").strip()
        if body:
            relative = path.relative_to(output_dir).as_posix()
            finding_ids = {match.group(1) for match in FINDING_RE.finditer(body)}
            duplicate_ids = finding_ids & seen_finding_ids
            heading = _report_resource("partial-response-heading.md", FILE=relative)
            if duplicate_ids:
                body = "\n".join("> " + line for line in body.splitlines())
            partial_appendix.append(f"\n\n{heading}\n\n{body}")
            seen_finding_ids.update(finding_ids)
    if partial_appendix:
        shell = shell.rstrip() + "\n\n" + _report_resource("incomplete-appendix-heading.md") + "\n" + "".join(partial_appendix)
    return normalize_publishable_report(shell, required_rule_ids, rules_dir=rules_dir)


def _append_unfinished_visual_responses(markdown: str, output_dir: Path) -> str:
    """Keep saved visual model responses in the downloadable report appendix."""
    visual_dir = output_dir / "visual"
    paths = sorted(path for path in visual_dir.glob("*-raw.md") if path.is_file())
    sections = []
    for path in paths:
        relative = path.relative_to(output_dir).as_posix()
        if relative in markdown:
            continue
        body = path.read_text(encoding="utf-8").strip()
        if body:
            sections.append(
                "\n\n" + _report_resource("partial-response-heading.md", FILE=relative) + "\n\n" + body
            )
    if not sections:
        return markdown
    return markdown.rstrip() + "\n\n" + _report_resource("visual-partial-responses.md") + "\n" + "".join(sections)


def _pipeline_incomplete_block(
    warnings: list[str], *, failure_type: str = "", visual_prepare_error: str | None = None,
    failed_materials: list[str] | None = None,
) -> str:
    """Render visible process status separately from the model's business verdict."""
    details: list[str] = []
    for warning in warnings:
        if warning == "overall_verdict_missing":
            detail = _report_resource("pipeline-detail-overall.md")
        elif warning.startswith("coverage_row_missing:"):
            detail = _report_resource("pipeline-detail-coverage.md", RULE_ID=warning.split(":", 1)[1])
        elif warning == "coverage_table_missing":
            detail = _report_resource("pipeline-detail-coverage-all.md")
        elif warning == "candidate_disposition_missing":
            detail = _report_resource("pipeline-detail-disposition.md")
        elif warning == "report_text_unavailable":
            detail = _report_resource("pipeline-detail-text.md")
        elif warning == "required_visual_stage_failed":
            detail = _report_resource(
                "pipeline-detail-visual.md",
                ERROR_TYPE=failure_type or _report_resource("pipeline-unknown-error-type.md"),
            )
        elif warning == "required_visual_stage_unavailable":
            detail = (_report_resource("pipeline-detail-visual-source.md", ERROR_TYPE=visual_prepare_error)
                      if visual_prepare_error else _report_resource("pipeline-detail-visual-missing.md"))
        elif warning == "local_image_facts_unavailable":
            detail = _report_resource(
                "pipeline-detail-image-facts.md",
                ERROR_TYPE=failure_type or _report_resource("pipeline-unknown-error-type.md"),
            )
        elif warning in {"audit_workflow_incomplete", "incomplete_report_shell"}:
            detail = _report_resource(
                "pipeline-detail-workflow.md",
                ERROR_TYPE=failure_type or _report_resource("pipeline-unknown-error-type.md"),
            )
        elif warning.startswith("reference_material_unavailable:"):
            filename = warning.split(":", 1)[1].replace("\r", " ").replace("\n", " ").replace("|", "\\|")
            detail = _report_resource("pipeline-detail-reference.md", FILENAME=filename)
        elif warning in {"delivery_evidence_incomplete", "pdf_delivery_failed", "pdf_render_fallback"}:
            detail = _report_resource("pipeline-detail-delivery.md")
        else:
            detail = _report_resource("pipeline-detail-generic.md", STAGE=warning)
        details.append(_report_resource("pipeline-detail-item.md", DETAIL=detail))
    for filename in failed_materials or []:
        safe_name = filename.replace("\r", " ").replace("\n", " ").replace("|", "\\|")
        detail = _report_resource("pipeline-detail-reference.md", FILENAME=safe_name)
        details.append(_report_resource("pipeline-detail-item.md", DETAIL=detail))
    unique_details = list(dict.fromkeys(details))
    if not unique_details:
        return ""
    return _report_resource("pipeline-incomplete.md", DETAILS="\n".join(unique_details))


def _insert_pipeline_incomplete_block(markdown: str, block: str) -> str:
    if not block or "## 流程状态" in markdown:
        return markdown
    title = re.search(r"(?m)^#{1,6}[ \t]+[^\n]+", markdown)
    if not title:
        return block + "\n\n" + markdown
    return markdown[:title.end()] + "\n\n" + block + "\n\n" + markdown[title.end():].lstrip()


def _render_report_pdf_fallback(markdown_path: Path, output_pdf: Path) -> None:
    """Use the normal Markdown and PDF renderers for a delivery fallback."""
    from audit_delivery import _render_pdf, _subset_and_validate_pdf

    html_path = output_pdf.with_suffix(".html")
    render_script = Path(__file__).resolve().parent / "render_report.py"
    rendered = subprocess.run(
        [sys.executable, str(render_script), str(markdown_path), "--out", str(html_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if rendered.returncode != 0 or not html_path.is_file():
        raise RuntimeError("The local Markdown renderer could not create the report HTML")
    _render_pdf(html_path, output_pdf)
    _subset_and_validate_pdf(output_pdf)
    if not output_pdf.is_file() or output_pdf.stat().st_size == 0:
        raise RuntimeError("The local PDF renderer did not create a report")


async def audit_prepared(pdf_path: Path, material_paths: list[Path], output_dir: Path,
                         submit: Callable[[str], Awaitable[str]],
                         on_progress: Callable[[dict], Awaitable[None]] | None = None,
                         rules_dir: Path | None = None,
                         visual_pdf: Path | None = None,
                         submit_visual: Callable[[str, list[dict[str, Any]]], Awaitable[str]] | None = None,
                         visual_dpi: int = 144,
                         require_visual: bool = False,
                         visual_prepare_error: str | None = None,
                         source_metadata: dict[str, Any] | None = None) -> dict:
    """Submit all supplied content to an LLM and deliver its report as a PDF."""
    from audit_materials import read_material
    from audit_delivery import deliver_report
    from audit_workflow import execute_audit

    output_dir.mkdir(parents=True, exist_ok=True)
    if (visual_pdf is None) != (submit_visual is None) and not require_visual:
        raise ValueError("Visual PDF and visual model bridge must be provided together")
    incomplete_reasons: list[str] = []
    partial_failure_type = ""
    try:
        text, count = await asyncio.to_thread(report_text, pdf_path)
    except Exception as exc:  # noqa: BLE001 - still publish an explicitly incomplete shell
        text, count = "", 0
        incomplete_reasons.append("report_text_unavailable")
        partial_failure_type = type(exc).__name__
    materials = []
    failed_materials: list[str] = []
    for file in material_paths:
        try:
            materials.append(await asyncio.to_thread(read_material, file))
        except Exception as exc:  # noqa: BLE001 - one unreadable reference must not block delivery
            filename = Path(file).name
            incomplete_reasons.append(f"reference_material_unavailable:{filename}")
            failed_materials.append(filename)
            partial_failure_type = partial_failure_type or type(exc).__name__

    if require_visual and (visual_pdf is None or submit_visual is None):
        incomplete_reasons.append("required_visual_stage_unavailable")

    if submit_visual is not None and visual_pdf is not None:
        import audit_visual
        await _emit_progress(on_progress, "visual", 0, 1, "正在核查页面图像")
        try:
            visual_results = await audit_visual.inspect_report(
                visual_pdf, text, submit_visual, output_dir / "visual",
                on_progress=on_progress, rules_dir=rules_dir, visual_dpi=visual_dpi,
            )
            visual_sections = []
            for index, result in enumerate(visual_results, start=1):
                pages = result.get("pages") or []
                label = f"第 {pages[0]}–{pages[-1]} 页" if pages else f"组 {index}"
                visual_sections.append(
                    _report_resource("visual-group-heading.md", GROUP=str(index), LABEL=label)
                    + "\n\n" + result.get("markdown", "").strip()
                )
            visual_markdown = _report_resource("visual-record-title.md") + "\n\n" + "\n\n---\n\n".join(visual_sections)
        except Exception as exc:  # noqa: BLE001 - visible missing stage, continue with text and partial evidence
            incomplete_reasons.append("required_visual_stage_failed")
            partial_failure_type = partial_failure_type or type(exc).__name__
            visual_markdown = _report_resource("visual-stage-failed.md", ERROR_TYPE=type(exc).__name__)
            visual_markdown = _append_unfinished_visual_responses(visual_markdown, output_dir)
        if visual_prepare_error:
            visual_markdown += _report_resource("visual-source-failed.md")
        (output_dir / "visual.md").write_text(visual_markdown, encoding="utf-8")
        materials.append({
            "filename": "visual-review.md",
            "kind": "visual",
            "content": visual_markdown,
            "sha256": hashlib.sha256(visual_markdown.encode("utf-8")).hexdigest(),
            "source_position": [{"document": "视觉模型逐页观察记录"}],
            "reference_id": f"M{len(materials) + 1:02d}",
        })
        import image_facts
        try:
            facts = await asyncio.to_thread(image_facts.scan_pdf, visual_pdf)
            facts_markdown = image_facts.to_markdown(facts)
            (output_dir / "image-facts.json").write_text(
                json.dumps(facts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        except Exception as exc:  # noqa: BLE001 - local image facts are supplemental, not a gate
            incomplete_reasons.append("local_image_facts_unavailable")
            partial_failure_type = partial_failure_type or type(exc).__name__
            facts_markdown = _report_resource("image-facts-unavailable.md")
        materials.append({
            "filename": "image-facts.md",
            "kind": "visual-facts",
            "content": facts_markdown,
            "sha256": hashlib.sha256(facts_markdown.encode("utf-8")).hexdigest(),
            "source_position": [{"document": "本地图片尺寸/哈希事实"}],
            "reference_id": f"M{len(materials) + 1:02d}",
        })
        await _emit_progress(on_progress, "visual", 1, 1, "页面图像核查完成")
    elif require_visual:
        visual_markdown = _report_resource("visual-stage-not-run.md")
        if visual_prepare_error:
            visual_markdown += _report_resource("visual-source-failed.md")
        (output_dir / "visual.md").write_text(visual_markdown, encoding="utf-8")
        materials.append({
            "filename": "visual-review.md", "kind": "visual", "content": visual_markdown,
            "sha256": hashlib.sha256(visual_markdown.encode("utf-8")).hexdigest(),
            "source_position": [{"document": "视觉阶段状态"}],
            "reference_id": f"M{len(materials) + 1:02d}",
        })

    (output_dir / "materials-used.json").write_text(json.dumps([
        {"reference_id": item.get("reference_id") or f"M{index:02d}",
         **{key: item.get(key) for key in ("filename", "kind", "sha256")}}
        for index, item in enumerate(materials, start=1)
    ], ensure_ascii=False, indent=2), encoding="utf-8")
    from _rules import load_rules
    required_rule_ids = load_rules(rules_dir).ids if rules_dir is not None else load_rules().ids
    submission = {
        "page_count": count, "report_characters": len(text),
        "rule_ids": required_rule_ids,
        "materials": [{"filename": item["filename"], "kind": item["kind"],
                       "reference_id": item.get("reference_id") or f"M{index:02d}",
                       "sha256": item["sha256"], "characters": len(item["content"])}
                      for index, item in enumerate(materials, start=1)],
    }
    submission_path = output_dir / "submission.json"

    def save_submission() -> None:
        submission_path.write_text(json.dumps(submission, ensure_ascii=False, indent=2), encoding="utf-8")

    save_submission()
    print(f"Prepared {count} pages and {len(materials)} reference files.", flush=True)
    active_rules = load_rules(rules_dir) if rules_dir is not None else load_rules()
    raw = output_dir / "audit-raw.md"
    try:
        markdown = await execute_audit(
            text, materials, count, submit, output_dir, on_progress=on_progress, rules_dir=rules_dir,
        )
        raw.write_text(markdown, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - preserve partial stage files and publish a review shell
        partial_failure_type = partial_failure_type or type(exc).__name__
        incomplete_reasons.append("audit_workflow_incomplete")
        markdown = _incomplete_report_shell(output_dir, partial_failure_type, required_rule_ids, rules_dir)
        (output_dir / "audit-incomplete.md").write_text(markdown, encoding="utf-8")

    initial_warnings = _report_completeness_warnings(markdown, required_rule_ids)
    summary_raw = output_dir / "audit-main-raw.md"
    summary_markdown = None
    if summary_raw.is_file():
        summary_markdown = summary_raw.read_text(encoding="utf-8")
        initial_warnings.extend(_report_completeness_warnings(summary_markdown, required_rule_ids))
        initial_warnings = list(dict.fromkeys(initial_warnings))
    normalized = normalize_publishable_report(
        markdown, required_rule_ids, rules_dir=rules_dir,
        preserved_source_markdown=summary_markdown,
    )
    normalized = _apply_source_identity(normalized, source_metadata)
    normalized = normalized.replace("报告未完成", "报告已生成，部分结果待复核")
    if initial_warnings:
        incomplete_reasons.extend(initial_warnings)
    if "报告已生成，部分结果待复核" in normalized and not initial_warnings and partial_failure_type:
        incomplete_reasons.append("incomplete_report_shell")
    if require_visual and any(reason.startswith("required_visual_") for reason in incomplete_reasons):
        if "视觉核查状态" not in normalized:
            normalized = normalized.rstrip() + "\n\n" + _report_resource("visual-incomplete.md") + "\n"
        normalized = _append_unfinished_visual_responses(normalized, output_dir)
    pipeline_block = _pipeline_incomplete_block(
        incomplete_reasons, failure_type=partial_failure_type,
        visual_prepare_error=visual_prepare_error, failed_materials=failed_materials,
    )
    normalized = _insert_pipeline_incomplete_block(normalized, pipeline_block)
    render_source = output_dir / "audit.md"
    render_source.write_text(normalized, encoding="utf-8")
    await _emit_progress(on_progress, "delivery", 0, 1, "正在生成审核PDF")
    output_pdf = output_dir / "audit-report.pdf"
    try:
        result = await asyncio.to_thread(deliver_report, render_source, pdf_path, output_pdf)
    except Exception as exc:  # noqa: BLE001 - retry delivery after adding a visible technical status
        result = {"report_pdf": None, "errors": [type(exc).__name__], "evidence_errors": [], "findings": []}
        incomplete_reasons.append("pdf_delivery_failed")
    if not isinstance(result, dict):
        result = {"report_pdf": None, "errors": ["invalid_delivery_result"],
                  "evidence_errors": [], "findings": []}
    delivery_problems = _validate_delivery_result(result, output_dir, allow_incomplete=True)
    pdf_missing = not _delivery_file_exists(result.get("report_pdf"), output_dir)
    evidence_problems = [problem for problem in delivery_problems if problem != "report PDF is missing or empty"]
    fallback_source = render_source
    enriched_path = result.get("enriched_markdown")
    if isinstance(enriched_path, str) and enriched_path.strip():
        enriched_candidate = Path(enriched_path)
        if not enriched_candidate.is_absolute():
            enriched_candidate = output_dir / enriched_candidate
        if _delivery_file_exists(str(enriched_candidate), output_dir):
            fallback_source = enriched_candidate.resolve()
    if evidence_problems:
        incomplete_reasons.append("delivery_evidence_incomplete")
        warning = "\n\n" + _report_resource("evidence-incomplete.md") + "\n"
        if "证据截图未完整生成" not in normalized:
            normalized = normalized.rstrip() + warning
            render_source.write_text(normalized, encoding="utf-8")
        if fallback_source != render_source:
            fallback_markdown = fallback_source.read_text(encoding="utf-8")
            if "证据截图未完整生成" not in fallback_markdown:
                fallback_source.write_text(fallback_markdown.rstrip() + warning, encoding="utf-8")
    if pdf_missing:
        incomplete_reasons.append("pdf_delivery_failed")
        incomplete_reasons.append("pdf_render_fallback")
        if "PDF 生成状态" not in normalized:
            normalized = normalized.rstrip() + "\n\n" + _report_resource("pdf-render-fallback.md") + "\n"
            render_source.write_text(normalized, encoding="utf-8")
        if fallback_source != render_source:
            fallback_markdown = fallback_source.read_text(encoding="utf-8")
            fallback_source.write_text(
                fallback_markdown.rstrip() + "\n\n" + _report_resource("pdf-render-fallback.md") + "\n",
                encoding="utf-8",
            )
    if evidence_problems or pdf_missing:
        await asyncio.to_thread(_render_report_pdf_fallback, fallback_source, output_pdf)
        result["report_pdf"] = str(output_pdf)
        result["pdf"] = str(output_pdf)
    (output_dir / "delivery.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _validate_delivery_result(result, output_dir, allow_incomplete=True)
    warnings = list(dict.fromkeys(incomplete_reasons))
    completion = {
        "completion_status": "needs_review" if warnings else "complete",
        "warnings": warnings,
        "raw_response": "audit-raw.md" if raw.is_file() else None,
        "partial_response_files": sorted(path.relative_to(output_dir).as_posix()
                                          for path in output_dir.rglob("*-raw.*") if path.is_file()),
    }
    (output_dir / "completion.json").write_text(json.dumps(completion, ensure_ascii=False, indent=2), encoding="utf-8")
    result.update(completion)
    await _emit_progress(on_progress, "delivery", 1, 1, "审核PDF已生成，部分结果待复核" if warnings else "审核PDF生成完成")
    return result


async def run_cli(args: argparse.Namespace) -> None:
    output = args.out.resolve()
    print("Preparing report locally before model submission.", flush=True)
    prepared = await asyncio.to_thread(prepare_report, args.report, output)
    visual = None
    if not getattr(args, "no_visual", False):
        visual = await asyncio.to_thread(prepare_visual_pdf, args.report, output)
        print(f"Prepared {visual['page_count']} visual pages from the original document.", flush=True)
    model = configured_model(args.core_config, args.model_token_id)
    max_tokens = _effective_max_tokens(model, args.max_output_tokens)
    visual_model = dict(model)
    if getattr(args, "visual_model", None):
        visual_model["model"] = args.visual_model

    usage_records: list[dict[str, Any]] = []

    def save_usage() -> None:
        (output / "model-usage.json").write_text(json.dumps(
            {"model": model["model"], "visual_model": visual_model["model"], "requests": usage_records},
            ensure_ascii=False, indent=2
        ), encoding="utf-8")

    async def request(stage: str, prompt: str) -> str:
        print(f"Submitting {stage} audit request to configured model {model['model']}.", flush=True)
        try:
            text, usage = await request_markdown(model, prompt, max_tokens)
        except Exception as exc:
            usage_records.append({"stage": stage, "usage": getattr(exc, "usage", {})})
            save_usage()
            if isinstance(exc, httpx.HTTPError):
                raise RuntimeError(f"Model API transport failed ({type(exc).__name__})") from None
            raise
        usage_records.append({"stage": stage, "usage": usage})
        save_usage()
        print(f"{stage} model response received.", flush=True)
        return text

    async def submit(prompt: str) -> str:
        stage_markers = {
            "index": "本次任务：识别报告项目目录",
            "project-review": "本次任务：一个项目的完整审核",
            "summary": "本次任务：全局审核与汇总",
        }
        matches = [(prompt.find(marker), stage) for stage, marker in stage_markers.items()
                   if prompt.find(marker) >= 0]
        stage = min(matches)[1] if matches else "text"
        return await request(stage, prompt)

    async def progress(event: dict) -> None:
        print(f"{event['stage']} {event['completed']}/{event['total']}: {event['message']}", flush=True)

    async def submit_visual(prompt: str, images: list[dict[str, Any]]) -> str:
        print(f"Submitting visual audit request to {visual_model['model']}.", flush=True)
        try:
            text = await request_visual(visual_model, prompt, images, max_tokens)
        except Exception as exc:
            usage_records.append({"stage": "visual", "usage": getattr(exc, "usage", {})})
            save_usage()
            if isinstance(exc, httpx.HTTPError):
                raise RuntimeError(f"Visual model API transport failed ({type(exc).__name__})") from None
            raise
        usage_records.append({"stage": "visual", "usage": {}})
        save_usage()
        print("visual model response received.", flush=True)
        return text

    await audit_prepared(
        Path(prepared["pdf"]), args.materials, output, submit,
        on_progress=progress,
        visual_pdf=Path(visual["pdf"]) if visual else None,
        submit_visual=submit_visual if visual else None,
        visual_dpi=getattr(args, "visual_dpi", 144),
    )
    print("Completed: " + str(output / "audit-report.pdf"), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--materials", nargs="+", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--core-config", type=Path, required=True)
    parser.add_argument("--model-token-id")
    parser.add_argument("--visual-model", help="Optional model override for page-image review")
    parser.add_argument("--visual-dpi", type=int, default=144, help="Page render DPI for visual review")
    parser.add_argument("--no-visual", action="store_true", help="Disable page-image visual review")
    parser.add_argument("--max-output-tokens", type=int)
    args = parser.parse_args()
    try:
        asyncio.run(run_cli(args))
        return 0
    except (ValueError, RuntimeError, OSError, httpx.HTTPError) as exc:
        print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
