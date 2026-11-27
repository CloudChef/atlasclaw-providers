# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.
"""Run the audit-report skill through AtlasClaw's configured model bridges.

Each attempt prepares a private desensitized PDF and shared-library snapshot,
then delegates business judgment to skill LLM calls and publishes its PDF.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import sys
import uuid
import re
from datetime import datetime
from pathlib import Path
from typing import Any

_API_DIR = Path(__file__).resolve().parent
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

import batch_audit
import evidence as evidence_module
import standards_service
from storage import report_data_dir
from errors import ProviderError
from store import DocumentStore

logger = logging.getLogger(__name__)
_TASKS: dict[tuple[Path, str], tuple[str, asyncio.Task]] = {}

BATCH_ATTEMPTS = 3
AUDIT_SKILL_ID = "audit-report:audit-report"


def _require_model_bridges(context: Any) -> None:
    """Retained for compatibility; bridge absence is reported in the published report."""
    return None


async def start_document_audit(context: Any, store: DocumentStore, document: dict[str, Any]) -> None:
    """Start one isolated LLM audit attempt in the background."""
    host = getattr(context, "host", context)
    file_path = Path(str(document.get("file_path") or ""))
    if not file_path.is_file():
        raise ProviderError("Original report file is missing", status_code=404, code="file_not_found")
    key = (store.db_path.resolve(), str(document["id"]))
    active = _TASKS.get(key)
    if active is not None and not active[1].done():
        raise ProviderError("An audit is already running for this document.", status_code=409, code="audit_already_running")

    attempt_id = uuid.uuid4().hex
    attempt_dir = report_data_dir(host) / "documents" / str(document["id"]) / "runs" / attempt_id

    async def run() -> None:
        try:
            await _run_document_audit(context, store, document, attempt_dir)
        finally:
            active_task = _TASKS.get(key)
            if active_task is not None and active_task[1] is asyncio.current_task():
                _TASKS.pop(key, None)

    async def prepare() -> None:
        await asyncio.to_thread(store.fail_interrupted, document["user_id"], document)
        await asyncio.to_thread(
            store.update, document["id"], status="running", progress=2,
            progress_text="正在准备审核", run_id="", error_code="", error_message="",
            report_path="", report_name="", desensitized_path="", desensitized_name="",
            findings_total=0, findings_review=0, grade_summary={},
        )
        _TASKS[key] = (document["id"], asyncio.create_task(run()))

    task = asyncio.create_task(prepare())
    _TASKS[key] = (document["id"], task)
    try:
        await asyncio.shield(task)
    finally:
        if task.done() and _TASKS.get(key) == (document["id"], task):
            _TASKS.pop(key)


async def start_report_regeneration(
    context: Any, store: DocumentStore, document: dict[str, Any],
) -> None:
    """Queue a local-only PDF regeneration from the user's saved audit output."""
    key = (store.db_path.resolve(), str(document["id"]))
    active = _TASKS.get(key)
    if (active is not None and not active[1].done()) or document.get("status") == "running":
        raise ProviderError(
            "An audit is already running for this document.", status_code=409, code="audit_already_running",
        )
    host = getattr(context, "host", context)
    data_root = report_data_dir(host).resolve()
    doc_root = (data_root / "documents" / str(document["id"])).resolve()
    report_path = Path(str(document.get("report_path") or "")).resolve()
    try:
        report_path.relative_to(doc_root / "runs")
    except ValueError as exc:
        raise ProviderError("A saved audit report is not available for regeneration.",
                            status_code=409, code="report_not_regenerable") from exc
    source_attempt = report_path.parent
    if report_path.name != "audit-report.pdf" or not report_path.is_file():
        raise ProviderError("A saved audit report is not available for regeneration.",
                            status_code=409, code="report_not_regenerable")
    if not (source_attempt / "audit-raw.md").is_file() or not (source_attempt / "audit-main-raw.md").is_file():
        raise ProviderError("Saved model output is incomplete; rerun the audit before regenerating.",
                            status_code=409, code="report_not_regenerable")
    prepared_pdf = Path(str(document.get("desensitized_path") or "")).resolve()
    try:
        prepared_pdf.relative_to(data_root)
    except ValueError as exc:
        raise ProviderError("The prepared report is outside provider storage.",
                            status_code=409, code="report_not_regenerable") from exc
    if not prepared_pdf.is_file():
        raise ProviderError("The prepared report is unavailable for local delivery.",
                            status_code=409, code="report_not_regenerable")

    new_attempt = source_attempt.parent / uuid.uuid4().hex
    previous_status = str(document.get("status") or "completed")

    async def run() -> None:
        try:
            await asyncio.to_thread(
                store.update, document["id"], status="running", progress=96,
                progress_text="正在从已保存的审核结果重新生成 PDF",
            )
            await _run_saved_report_regeneration(
                context, store, document, source_attempt, new_attempt, prepared_pdf,
            )
        except Exception as exc:  # noqa: BLE001 - keep the prior downloadable report on local render failure
            logger.exception("Saved report regeneration failed for %s", document["id"])
            await asyncio.to_thread(
                store.update, document["id"], status=previous_status, progress=100,
                progress_text="报告重新生成失败，原报告仍可下载",
                error_code="report_regeneration_failed", error_message=str(exc)[:500],
            )
        finally:
            if _TASKS.get(key) is not None and _TASKS[key][1] is asyncio.current_task():
                _TASKS.pop(key, None)

    task = asyncio.create_task(run())
    _TASKS[key] = (str(document["id"]), task)
    await asyncio.sleep(0)


async def _run_saved_report_regeneration(
    context: Any, store: DocumentStore, document: dict[str, Any],
    source_attempt: Path, new_attempt: Path, prepared_pdf: Path,
) -> None:
    """Copy an owned attempt and regenerate its report without invoking model bridges."""
    host = getattr(context, "host", context)
    data_root = report_data_dir(host).resolve()
    new_attempt.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(shutil.copytree, source_attempt, new_attempt)
    raw_markdown = await asyncio.to_thread(
        (new_attempt / "audit-raw.md").read_text, encoding="utf-8",
    )
    rules_dir = new_attempt / "library" / "rules"
    skill_dir = _skill_dir()
    scripts_dir = skill_dir / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import run_document_audit
    from _rules import load_rules

    await run_document_audit.render_saved_report(
        raw_markdown, new_attempt, prepared_pdf, load_rules(rules_dir).ids,
        rules_dir=rules_dir,
        source_metadata={
            "file_name": document.get("file_name"),
            "size": document.get("size"),
            "sha256": document.get("sha256"),
        },
    )
    rendered_markdown = await asyncio.to_thread(
        (new_attempt / "audit.md").read_text, encoding="utf-8",
    )
    verification, summary = _llm_report_metadata(
        rendered_markdown, load_rules(rules_dir).ids, allow_incomplete=True,
    )
    completion_path = new_attempt / "completion.json"
    completion = json.loads(completion_path.read_text(encoding="utf-8")) if completion_path.is_file() else {}
    if completion.get("completion_status") == "needs_review":
        verification["completion_status"] = "needs_review"
        verification["warnings"] = list(dict.fromkeys([
            *verification.get("warnings", []), *completion.get("warnings", []),
        ]))
        verification["completeness"] = {
            **verification.get("completeness", {}),
            "pipeline_status": "needs_review",
            "pipeline_warnings": completion.get("warnings", []),
        }
    await asyncio.to_thread(
        (new_attempt / "verification.json").write_text,
        json.dumps(verification, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    report_path = (new_attempt / "audit-report.pdf").resolve()
    try:
        report_path.relative_to(data_root)
    except ValueError as exc:
        raise ProviderError("Generated report is outside provider storage.",
                            status_code=500, code="report_path_invalid") from exc
    if not report_path.is_file() or report_path.stat().st_size == 0:
        raise RuntimeError("Local report regeneration did not produce a downloadable PDF")
    await asyncio.to_thread(
        store.update, document["id"], status="completed", progress=100,
        progress_text=("报告已生成，部分结果待复核"
                       if verification.get("completion_status") == "needs_review" else "报告已重新生成"),
        findings_total=summary["findings_total"], findings_review=summary["findings_review"],
        grade_summary=summary["grade_summary"], report_path=str(report_path),
        report_name="audit-report.pdf", error_code="", error_message="",
    )


async def reconcile_document(store: DocumentStore, document: dict[str, Any]) -> dict[str, Any]:
    """Recover a document whose owning pipeline is no longer running."""
    if document.get("status") != "running":
        return document
    key = (store.db_path.resolve(), str(document.get("id") or ""))
    active = _TASKS.get(key)
    if active is not None and active[0] == document["id"] and not active[1].done():
        return document
    await asyncio.to_thread(store.fail_interrupted, document["user_id"], document)
    return await asyncio.to_thread(store.get, document["id"], document["user_id"]) or document


async def _run_document_audit(context: Any, store: DocumentStore, document: dict[str, Any], attempt_dir: Path | None = None) -> None:
    """Prepare a private snapshot, run the skill LLM workflow, and persist its PDF."""
    document_id = str(document["id"])
    host = getattr(context, "host", context)
    try:
        if attempt_dir is None:
            attempt_dir = report_data_dir(host) / "documents" / document_id / "runs" / uuid.uuid4().hex
        await asyncio.to_thread(attempt_dir.mkdir, parents=True, exist_ok=True)
        doc_dir = report_data_dir(host) / "documents" / document_id
        skill_dir = _skill_dir()
        scripts_dir = skill_dir / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        import audit_preparation
        import run_document_audit
        prepared_dir = doc_dir / f"prepared-v{audit_preparation.PREPARATION_VERSION}"
        text_system_prompt = (skill_dir / "references" / "audit-system.md").read_text(encoding="utf-8")

        await _progress(store, document_id, 4, "正在脱敏并准备报告")
        prepared = await asyncio.to_thread(audit_preparation.prepare_report, document["file_path"], prepared_dir)
        prepared_pdf = Path(str(prepared.get("pdf") or "")).resolve()
        try:
            prepared_pdf.relative_to(report_data_dir(host).resolve())
        except ValueError as exc:
            raise ProviderError("Prepared PDF is outside provider storage", status_code=500, code="prepared_path_invalid") from exc
        if not prepared_pdf.is_file():
            raise ProviderError("Desensitized PDF was not created", status_code=500, code="desensitize_failed")
        await asyncio.to_thread(
            store.update, document_id, desensitized_path=str(prepared_pdf),
            desensitized_name=f"{Path(str(document.get('file_name') or 'report')).stem}_脱敏.pdf",
            progress=10, progress_text="脱敏 PDF 已就绪，正在读取共享资料",
        )
        visual_prepare_error = None
        try:
            visual_source = await asyncio.to_thread(
                audit_preparation.prepare_visual_pdf,
                document["file_path"],
                attempt_dir / "visual-source",
            )
            visual_pdf = Path(str(visual_source.get("pdf") or "")).resolve()
            if not visual_pdf.is_file():
                raise RuntimeError("visual source was not created")
        except Exception as exc:  # noqa: BLE001 - publish text/partial results with a visible visual warning
            visual_pdf = None
            visual_prepare_error = type(exc).__name__

        library_dir = attempt_dir / "library"
        snapshot = await asyncio.to_thread(standards_service.snapshot_audit_library, host, library_dir)
        material_paths = [Path(path) for path in snapshot["material_paths"]]
        rules_dir = Path(snapshot["rules_dir"])
        await _progress(store, document_id, 15, f"资料快照完成，共 {len(material_paths)} 份参考资料")

        async def submit(prompt: str) -> str:
            runner = getattr(context, "run_text", None)
            if not callable(runner):
                raise ProviderError(
                    "Text model bridge is unavailable",
                    status_code=503,
                    code="text_model_unavailable",
                )
            answer = await runner(
                prompt=prompt,
                system_prompt=text_system_prompt,
                skill_id=AUDIT_SKILL_ID,
            )
            answer = str(answer or "")
            if not answer.strip():
                raise ProviderError(
                    "Text model bridge returned an empty response",
                    status_code=502,
                    code="text_model_empty",
                )
            return answer

        async def submit_visual(prompt: str, images: list[dict[str, Any]]) -> str:
            runner = getattr(context, "run_visual", None)
            if not callable(runner):
                raise ProviderError(
                    "Visual model bridge is unavailable",
                    status_code=503,
                    code="visual_model_unavailable",
                )
            answer = await runner(
                prompt=prompt,
                system_prompt=text_system_prompt,
                timeout_seconds=None,
                skill_id=AUDIT_SKILL_ID,
                images=images,
            )
            answer = str(answer or "")
            if not answer.strip():
                raise ProviderError(
                    "Visual model bridge returned an empty response",
                    status_code=502,
                    code="visual_model_empty",
                )
            return answer

        async def on_progress(event: dict[str, Any]) -> None:
            stage = str(event.get("stage") or "audit")
            phase = stage.split(":", 1)[0]
            completed = int(event.get("completed") or 0)
            total = max(1, int(event.get("total") or 1))
            ratio = min(1.0, max(0.0, completed / total))
            labels = {"index": "识别项目目录", "project-review": "审核检测项目",
                      "projects": "准备逐项目审核",
                      "summary": "全局审核与汇总", "delivery": "生成审核 PDF",
                      "complete": "审核处理完成"}
            progress = {
                "index": 35 + int(3 * ratio),
                "projects": 38 + int(47 * ratio),
                "summary": 85 + int(8 * ratio),
                "delivery": 93 + int(5 * ratio),
                "complete": 98,
            }.get(phase)
            await _progress(store, document_id, progress,
                            f"{labels.get(phase, stage)}（{completed}/{total}）{str(event.get('message') or '')[:100]}")

        await run_document_audit.audit_prepared(
            prepared_pdf, material_paths, attempt_dir, submit,
            on_progress=on_progress, rules_dir=rules_dir,
            visual_pdf=visual_pdf, submit_visual=submit_visual, require_visual=True,
            visual_prepare_error=visual_prepare_error,
            source_metadata={
                "file_name": document.get("file_name"),
                "size": document.get("size"),
                "sha256": document.get("sha256"),
            },
        )
        report_path = (attempt_dir / "audit-report.pdf").resolve()
        raw_path = attempt_dir / "audit-raw.md"
        if not report_path.is_file() or report_path.stat().st_size == 0:
            raise RuntimeError("Skill audit did not create a downloadable PDF")
        if not raw_path.is_file():
            raw_path = attempt_dir / "audit.md"
        if not raw_path.is_file():
            raise RuntimeError("Skill audit did not create report Markdown")
        raw_markdown = raw_path.read_text(encoding="utf-8")
        from _rules import load_rules
        verification, summary = _llm_report_metadata(
            raw_markdown, load_rules(rules_dir).ids, allow_incomplete=True,
        )
        completion_path = attempt_dir / "completion.json"
        if completion_path.is_file():
            completion = json.loads(completion_path.read_text(encoding="utf-8"))
            if completion.get("completion_status") == "needs_review":
                verification["completion_status"] = "needs_review"
                verification["warnings"] = list(dict.fromkeys([
                    *verification.get("warnings", []),
                    *completion.get("warnings", []),
                ]))
                verification["completeness"] = {
                    **verification.get("completeness", {}),
                    "pipeline_status": "needs_review",
                }
        (attempt_dir / "verification.json").write_text(
            json.dumps(verification, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        await asyncio.to_thread(
            store.update,
            document_id,
            status="completed",
            progress=100,
            progress_text=("报告已生成，部分结果待复核"
                           if verification.get("completion_status") == "needs_review" else "审核完成"),
            findings_total=summary["findings_total"],
            findings_review=summary["findings_review"],
            grade_summary=summary["grade_summary"],
            report_path=str(report_path),
            report_name="audit-report.pdf",
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


def _llm_report_metadata(
    markdown: str,
    required_rule_ids: list[str] | tuple[str, ...],
    *,
    allow_incomplete: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read explicit report metadata, optionally retaining incomplete output for review."""
    main = re.split(r"(?m)^#\s*附录：分项目审核原文\s*$", markdown, maxsplit=1)[0]
    required_ids = list(dict.fromkeys(required_rule_ids))
    warnings: list[str] = []
    verdict_match = re.search(
        r"(?m)^\s*\*\*总评\s*[：:]\s*([^*\n]+?)\s*\*\*",
        main,
    )
    verdict = verdict_match.group(1).strip() if verdict_match else ""
    overall_verdict_complete = bool(verdict) and re.fullmatch(r"<[^<>]*>", verdict) is None
    if not overall_verdict_complete:
        if not allow_incomplete:
            raise RuntimeError("LLM report is missing its explicit overall verdict")
        verdict = "待复核（模型未给出结论）"
        warnings.append("overall_verdict_missing")
    coverage_match = re.search(r"(?ms)^#{1,2}\s*[^\n]*检查覆盖表[^\n]*\n(.*?)(?=^#{1,2}\s|\Z)", main)
    if not coverage_match:
        if not allow_incomplete:
            raise RuntimeError("LLM report is missing its main coverage table")
        warnings.append("coverage_table_missing")
    rows: list[dict[str, str]] = []
    observed_rule_ids: list[str] = []
    for line in coverage_match.group(1).splitlines() if coverage_match else []:
        if not line.lstrip().startswith("|"):
            continue
        cells = [re.sub(r"[`*_]", "", cell.strip()) for cell in line.strip().strip("|").split("|")]
        if not cells or cells[0] not in required_ids:
            continue
        observed_rule_ids.append(cells[0])
        if len(cells) < 6:
            continue
        if not re.match(r"^(通过|不通过|不适用|待复核|证据不足)", cells[4]):
            continue
        rows.append({"rule": cells[0], "name": cells[2], "severity": cells[3],
                     "verdict": cells[4], "reason": cells[5]})
    row_ids = [item["rule"] for item in rows]
    duplicates = sorted({rule_id for rule_id in row_ids if row_ids.count(rule_id) > 1})
    if allow_incomplete:
        duplicates = sorted(set(duplicates) | {
            rule_id for rule_id in observed_rule_ids if observed_rule_ids.count(rule_id) > 1
        })
    if duplicates and not allow_incomplete:
        raise RuntimeError(f"LLM report contains duplicate coverage rows: {', '.join(duplicates)}")
    if duplicates:
        rows = [row for row in rows if row["rule"] not in duplicates]
        row_ids = [row["rule"] for row in rows]
        warnings.append(f"coverage_rows_duplicated:{','.join(duplicates)}")
    missing_rules = [rule_id for rule_id in required_ids if rule_id not in set(row_ids)]
    if missing_rules and not allow_incomplete:
        raise RuntimeError(f"LLM report is missing coverage rows: {', '.join(sorted(missing_rules))}")
    if missing_rules and coverage_match:
        warnings.append(f"coverage_rows_missing:{','.join(missing_rules)}")
    for rule_id in missing_rules:
        rows.append({"rule": rule_id, "name": "", "severity": "", "verdict": "REVIEW",
                     "reason": "模型未提供此规则结论"})
    rule_pattern = "|".join(
        re.escape(rule_id) for rule_id in sorted(required_ids, key=len, reverse=True)
    ) or r"(?!)"
    counts = {"PASS": 0, "FAIL": 0, "REVIEW": 0, "NA": 0}
    for row in rows:
        raw_verdict = row["verdict"]
        if raw_verdict.startswith("不通过"):
            row["verdict"] = "FAIL"
        elif raw_verdict.startswith("通过"):
            row["verdict"] = "PASS"
        elif raw_verdict.startswith("不适用"):
            row["verdict"] = "NA"
        else:
            row["verdict"] = "REVIEW"
        counts[row["verdict"]] += 1
    finding_heads = list(re.finditer(r"(?m)^###\s+(F-[A-Za-z0-9-]+)(?:\s+\[([ABC])\])?\s+([^\n]+)", markdown))
    findings_by_id: dict[str, dict[str, str]] = {}
    for index, match in enumerate(finding_heads):
        finding_id, severity, title = match.groups()
        end = finding_heads[index + 1].start() if index + 1 < len(finding_heads) else len(markdown)
        section = markdown[match.end():end]
        rule_match = re.search(
            rf"(?:规则号|规则)\*{{0,2}}\s*[：:]\s*[`*]*({rule_pattern})(?![A-Za-z0-9])",
            section,
        )
        if not rule_match:
            rule_match = re.search(r"[（(]([A-Z]\d{2,})[）)]", title)
        page_match = re.search(r"(?:页码|页面)\*{0,2}\s*[：:]\s*([^\n|]+)", section)
        summary_match = re.search(r"(?:不规范说明|问题摘要|问题)\*{0,2}\s*[：:]\s*([^\n]+)", section)
        findings_by_id[finding_id] = {
            "id": finding_id,
            "rule": rule_match.group(1) if rule_match else "",
            "severity": severity or "",
            "title": re.sub(r"\s*[（(][A-Z]\d{2,}[）)]\s*$", "", title.strip()),
            "page": page_match.group(1).strip() if page_match else "",
            "problem": summary_match.group(1).strip(" `*_：:") if summary_match else title.strip(),
        }
    # The final LLM overview takes precedence over historical appendix grades.
    grade_column: int | None = None
    decision_column: int | None = None
    reason_column: int | None = None
    decisions: dict[str, tuple[str, str]] = {}
    duplicate_ids: set[str] = set()
    final_columns: dict[str, int] = {}
    identity_column: int | None = None
    disposition_table_seen = False
    current_disposition_table = False
    disposition_row_ids: set[str] = set()
    for line in main.splitlines():
        if not line.lstrip().startswith("|"):
            grade_column = decision_column = reason_column = None
            final_columns = {}
            current_disposition_table = False
            continue
        cells = [re.sub(r"[`*_]", "", cell.strip()) for cell in line.strip().strip("|").split("|")]
        decision_header = next((cell for cell in cells if re.fullmatch(r"复核结果(?:[（(][^）)]*[）)])?", cell)), None)
        if "最终等级" in cells or "等级" in cells or decision_header is not None:
            grade_column = cells.index("最终等级") if "最终等级" in cells else cells.index("等级") if "等级" in cells else None
            decision_column = cells.index(decision_header) if decision_header is not None else None
            reason_column = next((cells.index(label) for label in ("复核依据", "复核理由", "理由/依据") if label in cells), None)
            current_disposition_table = decision_header is not None
            disposition_table_seen = disposition_table_seen or current_disposition_table
            identity_column = next((cells.index(label) for label in ("序号/FID", "FID", "问题编号", "问题ID", "候选编号") if label in cells), None)
            if current_disposition_table and (identity_column is None or decision_column is None or grade_column is None):
                if not allow_incomplete:
                    raise RuntimeError("LLM report has a malformed final-disposition table schema")
                warnings.append("final_disposition_table_malformed")
                current_disposition_table = False
                continue
            final_columns = {
                field: next(cells.index(label) for label in labels if label in cells)
                for field, labels in {"rule": ("最终规则号", "规则号"), "title": ("问题摘要", "问题标题"), "page": ("页码", "PDF页码")}.items()
                if any(label in cells for label in labels)
            }
            continue
        finding_id = None
        if current_disposition_table and identity_column is not None:
            identity_value = cells[identity_column] if identity_column < len(cells) else ""
            id_match = re.search(r"\bF-[A-Za-z0-9-]+\b", identity_value)
            finding_id = id_match.group(0) if id_match else None
            if finding_id and finding_id not in findings_by_id:
                if not allow_incomplete:
                    raise RuntimeError(f"LLM report has a final disposition without detailed evidence: {finding_id}")
                warnings.append(f"final_disposition_without_evidence:{finding_id}")
                finding_id = None
        elif not disposition_table_seen:
            finding_id = next((cell for cell in cells if cell in findings_by_id), None)
        if current_disposition_table and finding_id:
            if finding_id in disposition_row_ids:
                if not allow_incomplete:
                    raise RuntimeError(f"LLM report contains duplicate final dispositions: {finding_id}")
                decisions.pop(finding_id, None)
                warning = f"final_disposition_duplicated:{finding_id}"
                if warning not in warnings:
                    warnings.append(warning)
                continue
            disposition_row_ids.add(finding_id)
        if finding_id and decision_column is not None and decision_column < len(cells):
            decision = cells[decision_column]
            if current_disposition_table and not re.match(r"^(?:成立|待复核|撤回)(?:$|[（(：:\s])", decision):
                if not allow_incomplete:
                    raise RuntimeError(f"LLM report has an unrecognized final disposition for {finding_id}: {decision!r}")
                warnings.append(f"final_disposition_unrecognized:{finding_id}")
                continue
            if re.match(r"^(?:成立|待复核|撤回)(?:$|[（(：:\s])", decision):
                reason = cells[reason_column] if reason_column is not None and reason_column < len(cells) else ""
                grade_text = cells[grade_column] if grade_column is not None and grade_column < len(cells) else ""
                valid_grade = re.match(r"^[ABC](?:$|\s*·|[（(])", grade_text)
                no_grade = grade_text in {"—", "-"} and decision.startswith(("撤回", "待复核"))
                if current_disposition_table and not (valid_grade or no_grade):
                    if not allow_incomplete:
                        raise RuntimeError(f"LLM report is missing a valid final grade for {finding_id}")
                    warnings.append(f"final_disposition_grade_missing:{finding_id}")
                    continue
                decisions[finding_id] = (decision, reason)
                if (re.search(r"不另计|不再计|不重复计|合并计", decision + " " + grade_text)
                        or re.fullmatch(r"成立[（(]重复[）)]", decision)
                        or re.search(r"(?:本行|本条|该候选|该项)(?:不另计|不再计|不重复计)", reason)):
                    duplicate_ids.add(finding_id)
                for field, column in final_columns.items():
                    if column < len(cells) and cells[column] not in {"", "—", "-"}:
                        findings_by_id[finding_id][field] = cells[column]
                        if field == "title":
                            findings_by_id[finding_id]["problem"] = cells[column]
        if finding_id and (current_disposition_table or not disposition_table_seen) and grade_column is not None and grade_column < len(cells):
            grade = re.match(r"^([ABC])(?:$|\s*·|[（(])", cells[grade_column])
            if grade:
                findings_by_id[finding_id]["severity"] = grade.group(1)
    missing_dispositions: list[str] = []
    if disposition_table_seen:
        missing_dispositions = sorted(set(findings_by_id) - set(decisions))
        if missing_dispositions:
            if not allow_incomplete:
                raise RuntimeError(f"LLM report is missing final dispositions: {', '.join(missing_dispositions)}")
            warnings.append(f"missing_final_dispositions:{','.join(missing_dispositions)}")
        unknown = sorted(disposition_row_ids - set(findings_by_id))
        if unknown:
            if not allow_incomplete:
                raise RuntimeError(f"LLM report has final dispositions without detailed evidence: {', '.join(unknown)}")
            warnings.append(f"final_dispositions_without_evidence:{','.join(unknown)}")
    withdrawn_findings, review_findings, duplicate_findings = [], [], []
    for finding_id, (decision, reason) in decisions.items():
        if finding_id in duplicate_ids or decision.startswith(("撤回", "待复核")):
            finding = findings_by_id.pop(finding_id)
            finding.update({"review_status": decision, "review_reason": reason})
            destination = duplicate_findings if finding_id in duplicate_ids else withdrawn_findings if decision.startswith("撤回") else review_findings
            destination.append(finding)
    if allow_incomplete:
        for finding_id in missing_dispositions:
            finding = findings_by_id.pop(finding_id)
            finding.update({
                "review_status": "待复核",
                "review_reason": "模型未提供最终复核结论",
            })
            review_findings.append(finding)
    ids = list(findings_by_id)
    grade_summary = {grade: sum(1 for item in findings_by_id.values() if item["severity"] == grade) for grade in ("A", "B", "C")}
    verification = {"verdict": verdict, "counts": counts, "results": rows,
                    "findings": list(findings_by_id.values()), "finding_ids": ids}
    if decisions or missing_dispositions:
        verification.update({"withdrawn_findings": withdrawn_findings, "review_findings": review_findings,
                             "duplicate_findings": duplicate_findings})
    if allow_incomplete:
        verification.update({
            "completion_status": "needs_review" if warnings else "complete",
            "warnings": warnings,
            "completeness": {
                "overall_verdict": overall_verdict_complete,
                "coverage_table": coverage_match is not None,
                "required_rules": len(required_ids),
                "reported_rules": len(required_ids) - len(missing_rules),
                "missing_rules": missing_rules,
            },
        })
    summary = {"findings_total": len(ids), "findings_review": counts["REVIEW"], "grade_summary": grade_summary}
    return verification, summary


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
    scripts_dir = str(_skill_dir() / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from audit_project_prompts import render_prompt_template

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
            metadata={"document_id": document_id, "rules": ",".join(rule.rule_id for rule in pending)},
        )
        await asyncio.to_thread(store.update, document_id, run_id=handle.run_id)
        snapshot = await handle.wait()
        if snapshot.get("status") != "succeeded":
            error = snapshot.get("error") or {}
            last_error = str(error.get("message") or error.get("code") or "run_failed")
            retry_note = render_prompt_template("batch-error-retry.md", ERROR=last_error[:120])
        else:
            parsed = batch_audit.parse_answer(str(snapshot.get("final_answer") or ""), pending)
            collected.update({item.rule: item for item in parsed})
            last_error = "" if parsed else "model returned no parsable verdicts"
            retry_note = render_prompt_template("batch-missing-retry.md")
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
        stdout, stderr = await proc.communicate()
    except asyncio.CancelledError:
        proc.kill()
        await proc.communicate()
        raise
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
        _stdout, stderr = await proc.communicate()
    except asyncio.CancelledError:
        proc.kill()
        await proc.communicate()
        raise
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
