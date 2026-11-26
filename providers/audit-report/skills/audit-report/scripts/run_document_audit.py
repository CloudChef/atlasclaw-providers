#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run local preparation, a configured LLM audit, and local PDF delivery.

Python dependencies and model credentials come from the AtlasClaw runtime.
Existing skill programs are called without changing their implementations.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import inspect
from pathlib import Path
from typing import Any, Callable, Awaitable

import httpx
from dotenv import dotenv_values

from audit_preparation import prepare_report, report_text


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


def _validate_delivery_result(result: Any, report_dir: Path) -> None:
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
    if problems:
        raise RuntimeError("Local report delivery is incomplete: " + "; ".join(problems))


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


async def audit_prepared(pdf_path: Path, material_paths: list[Path], output_dir: Path,
                         submit: Callable[[str], Awaitable[str]],
                         on_progress: Callable[[dict], Awaitable[None]] | None = None,
                         rules_dir: Path | None = None) -> dict:
    """Submit all supplied content to an LLM and deliver its report as a PDF."""
    from audit_materials import read_material
    from audit_delivery import deliver_report
    from audit_workflow import execute_audit

    output_dir.mkdir(parents=True, exist_ok=True)
    text, count = await asyncio.to_thread(report_text, pdf_path)
    materials = [await asyncio.to_thread(read_material, file) for file in material_paths]
    (output_dir / "materials-used.json").write_text(json.dumps([
        {"reference_id": f"M{index:02d}", **{key: item.get(key) for key in ("filename", "kind", "sha256")}}
        for index, item in enumerate(materials, start=1)
    ], ensure_ascii=False, indent=2), encoding="utf-8")
    from _rules import load_rules
    required_rule_ids = load_rules(rules_dir).ids if rules_dir is not None else load_rules().ids
    submission = {
        "page_count": count, "report_characters": len(text),
        "rule_ids": required_rule_ids,
        "materials": [{"filename": item["filename"], "kind": item["kind"],
                       "reference_id": f"M{index:02d}", "sha256": item["sha256"],
                       "characters": len(item["content"])}
                      for index, item in enumerate(materials, start=1)],
    }
    submission_path = output_dir / "submission.json"

    def save_submission() -> None:
        submission_path.write_text(json.dumps(submission, ensure_ascii=False, indent=2), encoding="utf-8")

    save_submission()
    print(f"Prepared {count} pages and {len(materials)} reference files.", flush=True)
    markdown = await execute_audit(
        text, materials, count, submit, output_dir, on_progress=on_progress, rules_dir=rules_dir,
    )
    raw = output_dir / "audit-raw.md"
    raw.write_text(markdown, encoding="utf-8")
    active_rules = load_rules(rules_dir) if rules_dir is not None else load_rules()
    normalized = validate_markdown(markdown, required_rule_ids=required_rule_ids,
                                   rule_severities=active_rules.severity)
    render_source = output_dir / "audit.md"
    render_source.write_text(normalized, encoding="utf-8")
    await _emit_progress(on_progress, "delivery", 0, 1, "正在生成审核PDF")
    result = await asyncio.to_thread(deliver_report, render_source, pdf_path, output_dir / "audit-report.pdf")
    (output_dir / "delivery.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _validate_delivery_result(result, output_dir)
    await _emit_progress(on_progress, "delivery", 1, 1, "审核PDF生成完成")
    return result


async def run_cli(args: argparse.Namespace) -> None:
    output = args.out.resolve()
    print("Preparing report locally before model submission.", flush=True)
    prepared = await asyncio.to_thread(prepare_report, args.report, output)
    model = configured_model(args.core_config, args.model_token_id)
    max_tokens = _effective_max_tokens(model, args.max_output_tokens)

    usage_records: list[dict[str, Any]] = []

    def save_usage() -> None:
        (output / "model-usage.json").write_text(json.dumps(
            {"model": model["model"], "requests": usage_records}, ensure_ascii=False, indent=2
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

    await audit_prepared(
        Path(prepared["pdf"]), args.materials, output, submit,
        on_progress=progress,
    )
    print("Completed: " + str(output / "audit-report.pdf"), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--materials", nargs="+", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--core-config", type=Path, required=True)
    parser.add_argument("--model-token-id")
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
