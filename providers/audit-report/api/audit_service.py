# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.
"""Audit orchestration through the AtlasClaw provider Agent Host.

The provider never asks one agent run to audit a whole document. It extracts the
text itself, then runs small rule batches as stateless model calls and assembles
the HTML report deterministically. This keeps long or large documents bounded
and guarantees a downloadable report whenever the text layer is readable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

_API_DIR = Path(__file__).resolve().parent
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

import batch_audit
import evidence as evidence_module
import standards_service
from errors import ProviderError
from store import DocumentStore

logger = logging.getLogger(__name__)
_TASKS: set[asyncio.Task] = set()

EXTRACT_TIMEOUT_SECONDS = 1800
BATCH_TIMEOUT_SECONDS = 900
RENDER_TIMEOUT_SECONDS = 180
BATCH_ATTEMPTS = 3


async def start_document_audit(host: Any, store: DocumentStore, document: dict[str, Any]) -> None:
    """Start the deterministic audit pipeline and persist its initial state."""
    agent = getattr(host, "agent", None)
    if agent is None:
        raise ProviderError("Agent runtime is unavailable", status_code=503, code="agent_unavailable")
    file_path = Path(str(document.get("file_path") or ""))
    if not file_path.is_file():
        raise ProviderError("Original report file is missing", status_code=404, code="file_not_found")
    await asyncio.to_thread(
        store.update,
        document["id"],
        status="running",
        progress=2,
        progress_text="正在准备审核",
        run_id="",
        error_code="",
        error_message="",
        report_path="",
        report_name="",
        findings_total=0,
        findings_review=0,
        grade_summary={},
    )
    task = asyncio.create_task(_run_document_audit(host, store, document))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)


async def reconcile_document(host: Any, store: DocumentStore, document: dict[str, Any]) -> dict[str, Any]:
    """Mark interrupted provider runs as failed when the host no longer knows them."""
    if document.get("status") != "running":
        return document
    run_id = str(document.get("run_id") or "")
    agent = getattr(host, "agent", None)
    snapshot = await agent.get_run(run_id) if agent is not None and run_id else {}
    status = str(snapshot.get("status") or "")
    if status not in {"failed", "cancelled"}:
        return document
    error = snapshot.get("error") or {}
    cancelled = status == "cancelled"
    return await asyncio.to_thread(
        store.update,
        document["id"],
        status="failed",
        progress_text="审核已取消" if cancelled else "审核中断",
        error_code="run_cancelled" if cancelled else "host_restarted",
        error_message=str(error.get("message") or "The audit run is no longer available.")[:500],
    ) or document


async def _run_document_audit(host: Any, store: DocumentStore, document: dict[str, Any]) -> None:
    """Extract, judge every rule batch and assemble the final report."""
    document_id = str(document["id"])
    started_at = datetime.now().astimezone()
    try:
        doc_dir = Path(host.data_dir) / "documents" / document_id
        extract_dir = doc_dir / "extract"
        await _progress(store, document_id, 4, "正在提取文档文本")
        markdown_path, manifest = await _extract_document(document, extract_dir)
        text = markdown_path.read_text(encoding="utf-8", errors="replace")
        if not manifest.get("has_text_layer", True):
            raise ProviderError(
                "报告没有可读取的文本层，无法自动判定；请提供可复制文字的 PDF 或 Word 文件",
                status_code=422,
                code="no_text_layer",
            )
        chunks, truncated_note = batch_audit.chunk_document(text)
        if not chunks:
            raise ProviderError("未能从文档中提取到可用文本", status_code=422, code="extract_empty")

        config_path = await asyncio.to_thread(standards_service.ensure_rules_config, host)
        rules, rule_packs = batch_audit.load_rule_set(_skill_dir(), rules_dir=config_path.parent)
        if not rules:
            raise ProviderError("审核规则未能加载", status_code=500, code="rules_missing")
        batches = batch_audit.rule_batches(rules)
        total_pages = int(manifest.get("page_count") or document.get("pages") or 0)
        total_steps = len(chunks) * len(batches)
        done = 0
        verdicts: list[batch_audit.Verdict] = []
        for chunk in chunks:
            for batch in batches:
                label = f"{batch[0].rule_id}–{batch[-1].rule_id}"
                await _progress(
                    store, document_id, 8 + int(74 * done / total_steps),
                    f"判定 {label}（{chunk.label}）",
                )
                verdicts.extend(
                    await _run_batch(
                        host, store, document_id, batch, chunk, len(chunks), total_pages, rule_packs,
                    )
                )
                done += 1

        results = batch_audit.merge_results(rules, verdicts)
        summary = batch_audit.summarize(results)
        finished_at = datetime.now().astimezone()
        findings = batch_audit.finding_list(results)
        await _progress(store, document_id, 88, "正在生成证据截图")
        await asyncio.to_thread(shutil.rmtree, doc_dir / "evidence", True)
        evidence = await asyncio.to_thread(evidence_module.render_evidence, document, doc_dir, findings)
        markdown = batch_audit.build_markdown(
            document=document,
            results=results,
            manifest=manifest,
            started_at=started_at,
            finished_at=finished_at,
            truncated_note=truncated_note,
            chunk_count=len(chunks),
            rule_packs=rule_packs,
            evidence=evidence,
        )
        doc_dir.mkdir(parents=True, exist_ok=True)
        source = doc_dir / "audit-report.md"
        source.write_text(markdown, encoding="utf-8")
        (doc_dir / "verification.json").write_text(
            json.dumps(
                batch_audit.build_verification(results, evidence=evidence),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        await _progress(store, document_id, 92, "正在生成 HTML 报告")
        report_path = doc_dir / "report.html"
        await _render_report(source, report_path)
        await asyncio.to_thread(
            store.update,
            document_id,
            status="completed",
            progress=100,
            progress_text="审核完成",
            findings_total=int(summary["findings_total"]),
            findings_review=int(summary["findings_review"]),
            grade_summary=summary["grade_summary"],
            report_path=str(report_path),
            report_name="audit-report.html",
            error_code="",
            error_message="",
        )
    except ProviderError as exc:
        logger.warning("Audit failed for %s: %s", document_id, exc.detail)
        await asyncio.to_thread(
            store.update,
            document_id,
            status="failed",
            progress=100,
            progress_text="审核失败",
            error_code=exc.code,
            error_message=exc.detail[:500],
        )
    except Exception as exc:  # noqa: BLE001 - pipeline failures become document state
        logger.exception("Audit pipeline failed for %s", document_id)
        await asyncio.to_thread(
            store.update,
            document_id,
            status="failed",
            progress=100,
            progress_text="审核失败",
            error_code="run_failed",
            error_message=str(exc)[:500],
        )


async def _run_batch(
    host: Any,
    store: DocumentStore,
    document_id: str,
    rules: list[batch_audit.Rule],
    chunk: batch_audit.TextChunk,
    total_chunks: int,
    total_pages: int = 0,
    rule_packs: list[str] | None = None,
) -> list[batch_audit.Verdict]:
    """Judge one rule batch against one chunk, asking again for rules left out."""
    agent = getattr(host, "agent", None)
    if agent is None:
        raise ProviderError("Agent runtime is unavailable", status_code=503, code="agent_unavailable")
    collected: dict[str, batch_audit.Verdict] = {}
    retry_note = ""
    last_error = ""
    for _attempt in range(BATCH_ATTEMPTS):
        pending = [rule for rule in rules if rule.rule_id not in collected]
        if not pending:
            break
        prompt = batch_audit.build_prompt(
            pending, chunk, total_chunks, retry_note, total_pages, rule_packs or (),
        )
        handle = await agent.start_run(
            prompt=prompt,
            skills=(),
            timeout_seconds=BATCH_TIMEOUT_SECONDS,
            metadata={"document_id": document_id, "rules": ",".join(rule.rule_id for rule in pending)},
        )
        await asyncio.to_thread(store.update, document_id, run_id=handle.run_id)
        snapshot = await handle.wait(timeout=BATCH_TIMEOUT_SECONDS + 60)
        if snapshot.get("status") != "succeeded":
            error = snapshot.get("error") or {}
            last_error = str(error.get("message") or error.get("code") or "run_failed")
            retry_note = f"上一次运行失败（{last_error[:120]}），请只输出规定的 JSON 对象。"
        else:
            parsed = batch_audit.parse_answer(str(snapshot.get("final_answer") or ""), pending)
            collected.update({item.rule: item for item in parsed})
            last_error = "" if parsed else "model returned no parsable verdicts"
            retry_note = (
                "上一次输出缺少这些规则的结果或无法解析，请只输出规定 JSON，且 results 必须包含本次全部规则。"
            )
        if collected and len(collected) < len(rules):
            logger.warning(
                "Audit batch missing rules for %s %s: %s",
                document_id,
                chunk.label,
                ",".join(rule.rule_id for rule in rules if rule.rule_id not in collected),
            )
    verdicts = [collected[rule.rule_id] for rule in rules if rule.rule_id in collected]
    for rule in rules:
        if rule.rule_id in collected:
            continue
        verdicts.append(
            batch_audit.Verdict(
                rule=rule.rule_id,
                verdict="REVIEW",
                severity=rule.severity,
                problem=f"自动判定失败：{last_error[:160] or '模型未返回结构化结果'}",
            )
        )
    return verdicts


async def _extract_document(document: dict[str, Any], extract_dir: Path) -> tuple[Path, dict[str, Any]]:
    """Extract page text with the skill script and return its markdown and manifest."""
    script = _skill_dir() / "scripts" / "extract_report.py"
    if not script.is_file():
        raise ProviderError("Document extraction tool is missing", status_code=500, code="extract_tool_missing")
    if extract_dir.is_dir():
        await asyncio.to_thread(shutil.rmtree, extract_dir, True)
    extract_dir.parent.mkdir(parents=True, exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(script), str(document["file_path"]), "--out", str(extract_dir), "--no-images",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=EXTRACT_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        raise ProviderError("文档文本提取超时", status_code=504, code="extract_timeout") from None
    markdown_files = sorted(extract_dir.glob("*/document.md"), key=lambda item: item.stat().st_mtime)
    if proc.returncode != 0 or not markdown_files:
        detail = stderr.decode("utf-8", "replace").strip()[-300:] or stdout.decode("utf-8", "replace").strip()[-300:]
        raise ProviderError(f"文档文本提取失败：{detail or 'no output'}", status_code=422, code="extract_failed")
    markdown_path = markdown_files[-1]
    manifest: dict[str, Any] = {}
    manifest_path = markdown_path.parent / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifest = {}
    return markdown_path, manifest


async def _render_report(source: Path, destination: Path) -> None:
    """Render the audit markdown into the deliverable HTML report."""
    script = _skill_dir() / "scripts" / "render_report.py"
    destination.parent.mkdir(parents=True, exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(script), str(source), "--out", str(destination), "--delivery",
        "--title", "检测报告审核报告",
        cwd=str(source.parent),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=RENDER_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        raise ProviderError("审核报告渲染超时", status_code=504, code="render_timeout") from None
    if proc.returncode != 0 or not destination.is_file():
        detail = stderr.decode("utf-8", "replace").strip()[-300:]
        raise ProviderError(f"审核报告渲染失败：{detail or 'no output'}", status_code=500, code="render_failed")


def _skill_dir() -> Path:
    """Return the bundled audit-report skill directory."""
    return Path(__file__).resolve().parents[1] / "skills" / "audit-report"


async def _progress(store: DocumentStore, document_id: str, progress: int | None, text: str) -> None:
    fields: dict[str, Any] = {"progress_text": str(text or "")[:200]}
    if progress is not None:
        fields["progress"] = int(progress)
    await asyncio.to_thread(store.update, document_id, **fields)
