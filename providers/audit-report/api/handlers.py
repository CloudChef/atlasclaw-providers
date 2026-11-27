# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.
"""HTTP handlers for the audit-report provider extension."""

from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import shutil
import sys
import uuid
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi.responses import Response

_API_DIR = Path(__file__).resolve().parent
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

from audit_service import _llm_report_metadata, reconcile_document, start_document_audit
from errors import ProviderError
from report_no import extract_report_no
import standards_service
from storage import report_data_dir
from store import DocumentStore

UPLOAD_CHUNK_BYTES = 1024 * 1024
ALLOWED_EXTENSIONS = frozenset({".pdf", ".docx"})
STATUS_VALUES = frozenset({"pending", "running", "completed", "failed"})
CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _store(context: Any) -> DocumentStore:
    return DocumentStore(report_data_dir(context.host))


def _user_id(context: Any) -> str:
    return str(getattr(context, "user_id", "") or getattr(context.host.user, "user_id", "") or "")


def _document_dir(context: Any, document_id: str) -> Path:
    return report_data_dir(context.host) / "documents" / document_id


def _validate_upload(path: Path, name: str) -> str:
    extension = Path(name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ProviderError(
            "Only PDF and Word (.docx) reports are supported.",
            status_code=422,
            code="unsupported_file",
        )
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ProviderError("The uploaded file is unavailable.", status_code=422, code="invalid_document") from exc
    if size <= 0:
        raise ProviderError("The uploaded file is empty.", status_code=422, code="invalid_document")
    if extension == ".pdf":
        with path.open("rb") as file_obj:
            if file_obj.read(5) != b"%PDF-":
                raise ProviderError("The PDF file is corrupted.", status_code=422, code="invalid_document")
        return extension
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile as exc:
        raise ProviderError(
            "The Word file is not a valid .docx package.", status_code=422, code="invalid_document",
        ) from exc
    if "[Content_Types].xml" not in names or not any(item.startswith("word/") for item in names):
        raise ProviderError(
            "The Word file is not a valid .docx package.", status_code=422, code="invalid_document",
        )
    return extension


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(UPLOAD_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _probe_document(path: Path, extension: str) -> dict[str, Any]:
    if extension == ".pdf":
        try:
            import pypdf

            reader = pypdf.PdfReader(str(path))
            pages = len(reader.pages)
            text = "\n".join(
                reader.pages[index].extract_text() or "" for index in range(min(3, pages))
            )
            return {"pages": pages, "text": text}
        except Exception:  # noqa: BLE001 - probe is best effort
            return {"pages": None, "text": ""}
    try:
        import docx

        document = docx.Document(str(path))
        paragraphs = [item.text for item in document.paragraphs if item.text.strip()]
        return {"pages": None, "text": "\n".join(paragraphs)}
    except Exception:  # noqa: BLE001 - probe is best effort
        return {"pages": None, "text": ""}


def _actions(document: dict[str, Any]) -> list[str]:
    status = document.get("status")
    if status == "pending":
        actions = ["start_audit", "delete"]
    elif status == "running":
        actions = ["view_progress"]
    elif status == "completed":
        actions = ["view_result", "download_report", "reaudit", "delete"]
    elif status == "failed":
        actions = ["retry", "delete"]
    else:
        actions = []
    if document.get("desensitized_path"):
        actions.append("download_desensitized")
    return actions


def _provider_base(context: Any) -> str:
    provider_type = quote(str(getattr(context, "provider_type", "") or "").strip(), safe="-_.")
    instance = quote(str(getattr(context, "provider_instance", "") or "").strip(), safe="-_.")
    if not provider_type or not instance:
        raise RuntimeError("Provider HTTP context is missing its routed provider instance")
    return f"/api/providers/{provider_type}/{instance}"


def _owned_file_exists(context: Any, path_value: str) -> bool:
    if not path_value:
        return False
    try:
        root = report_data_dir(context.host).resolve()
        path = Path(path_value).resolve()
        path.relative_to(root)
        return path.is_file()
    except (OSError, ValueError, AttributeError):
        return False


def _document_response(context: Any, document: dict[str, Any]) -> dict[str, Any]:
    base = f"{_provider_base(context)}/documents/{document['id']}"
    report_path = str(document.get("report_path") or "")
    desensitized_path = str(document.get("desensitized_path") or "")
    report_available = _owned_file_exists(context, report_path)
    desensitized_available = _owned_file_exists(context, desensitized_path)
    report_format = Path(report_path).suffix.lstrip(".").lower() if report_available else ""
    completion_status = None
    if document.get("status") == "completed" and report_path:
        verification_path = str(Path(report_path).parent / "verification.json")
        if _owned_file_exists(context, verification_path):
            try:
                verification_data, _ = _read_owned_file(context, verification_path)
                verification = json.loads(verification_data.decode("utf-8"))
            except (ProviderError, OSError, UnicodeDecodeError, ValueError):
                verification = None
            if isinstance(verification, dict) and verification.get("completion_status") in {"complete", "needs_review"}:
                completion_status = verification["completion_status"]
    response = {
        "id": document["id"],
        "file_name": document["file_name"],
        "report_no": document.get("report_no") or "",
        "pages": document.get("pages"),
        "size": document.get("size") or 0,
        "status": document.get("status") or "pending",
        "progress": int(document.get("progress") or 0),
        "progress_text": document.get("progress_text") or "",
        "findings_total": int(document.get("findings_total") or 0),
        "findings_review": int(document.get("findings_review") or 0),
        "grade_summary": document.get("grade_summary") or {},
        "error_code": document.get("error_code") or "",
        "error_message": document.get("error_message") or "",
        "report_available": report_available,
        "desensitized_available": desensitized_available,
        "report_format": report_format,
        "created_at": document.get("created_at") or "",
        "updated_at": document.get("updated_at") or "",
        "actions": _actions(document),
        "urls": {
            "detail": base,
            "file": f"{base}/file",
            "report": f"{base}/report",
            "report_preview": f"{base}/report?preview=html" if report_format == "pdf" else f"{base}/report",
            "report_download": f"{base}/report/download",
            "desensitized": f"{base}/desensitized",
            "desensitized_download": f"{base}/desensitized/download",
            "audit": f"{base}/audit",
        },
    }
    if completion_status is not None:
        response["completion_status"] = completion_status
    return response


def _require_document(context: Any, store: DocumentStore) -> dict[str, Any]:
    document_id = str(context.path_params.get("document_id") or "").strip()
    document = store.get(document_id, _user_id(context))
    if document is None:
        raise ProviderError("Document not found", status_code=404, code="document_not_found")
    return document


def _read_owned_file(context: Any, path_value: str) -> tuple[bytes, Path]:
    if not str(path_value or "").strip():
        raise ProviderError("File not found", status_code=404, code="file_not_found")
    data_root = report_data_dir(context.host).resolve()
    path = Path(str(path_value or "")).resolve()
    try:
        path.relative_to(data_root)
    except ValueError as exc:
        raise ProviderError("File is outside provider storage", status_code=403, code="file_forbidden") from exc
    if not path.is_file():
        raise ProviderError("File not found", status_code=404, code="file_not_found")
    return path.read_bytes(), path


async def list_documents(request: Any, context: Any) -> dict[str, Any]:
    """List the current user's documents with search, status and pagination."""
    store = _store(context)
    params = request.query_params
    result = await asyncio.to_thread(
        store.list,
        _user_id(context),
        query=str(params.get("q") or ""),
        status=str(params.get("status") or ""),
        page=int(params.get("page") or 1),
        page_size=int(params.get("page_size") or 20),
    )
    items = result["items"]
    for index, document in enumerate(items):
        if document.get("status") == "running":
            items[index] = await reconcile_document(store, document)
    return {
        "items": [_document_response(context, document) for document in items],
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
    }


async def upload_document(request: Any, context: Any) -> dict[str, Any]:
    """Accept one PDF/DOCX upload, probe metadata and register the document."""
    form = await request.form()
    upload = form.get("file")
    if upload is None or not hasattr(upload, "read"):
        raise ProviderError("A report file is required.", status_code=422, code="file_required")
    file_name = str(getattr(upload, "filename", "") or "report.pdf")
    document_id = uuid.uuid4().hex
    document_dir = _document_dir(context, document_id)
    document_dir.mkdir(parents=True, exist_ok=True)
    temp_path = document_dir / "upload.part"
    total_bytes = 0
    try:
        with temp_path.open("wb") as file_obj:
            while True:
                chunk = await upload.read(UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                total_bytes += len(chunk)
                file_obj.write(chunk)
        extension = await asyncio.to_thread(_validate_upload, temp_path, file_name)
        file_path = document_dir / f"original{extension}"
        await asyncio.to_thread(temp_path.replace, file_path)
        probe = await asyncio.to_thread(_probe_document, file_path, extension)
        sha256 = await asyncio.to_thread(_sha256_file, file_path)
    except BaseException:
        await asyncio.to_thread(shutil.rmtree, document_dir, True)
        raise

    report_no = str(form.get("report_no") or "").strip() or extract_report_no(probe.get("text", ""))

    store = _store(context)
    document = await asyncio.to_thread(store.create, {
        "id": document_id,
        "user_id": _user_id(context),
        "tenant_id": str(getattr(context.host.user, "tenant_id", "") or ""),
        "file_name": Path(file_name).name,
        "file_path": str(file_path),
        "extension": extension,
        "size": total_bytes,
        "sha256": sha256,
        "pages": probe.get("pages"),
        "report_no": report_no,
        "status": "pending",
    })
    return _document_response(context, document)


async def get_document(request: Any, context: Any) -> dict[str, Any]:
    """Return one document, reconciling interrupted runs."""
    store = _store(context)
    document = _require_document(context, store)
    if document.get("status") == "running":
        document = await reconcile_document(store, document)
    return _document_response(context, document)


async def start_audit(request: Any, context: Any) -> dict[str, Any]:
    """Start the audit pipeline for one document."""
    store = _store(context)
    document = _require_document(context, store)
    await start_document_audit(context, store, document)
    updated = store.get(document["id"], _user_id(context)) or document
    return _document_response(context, updated)


async def download_document(request: Any, context: Any) -> Response:
    """Return the original report file."""
    document = _require_document(context, _store(context))
    data, path = _read_owned_file(context, document["file_path"])
    media_type = CONTENT_TYPES.get(Path(path).suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    filename = quote(str(document["file_name"]))
    return Response(content=data, media_type=media_type, headers={
        "Content-Disposition": f"attachment; filename*=utf-8''{filename}",
        "X-Content-Type-Options": "nosniff",
    })


async def download_report(request: Any, context: Any) -> Response:
    """Return the PDF, an HTML preview for new PDFs, or a legacy HTML report."""
    document = _require_document(context, _store(context))
    report_path = str(document.get("report_path") or "")
    if not report_path:
        raise ProviderError("Audit report is not ready", status_code=404, code="report_not_ready")
    data, path = _read_owned_file(context, report_path)
    preview_requested = str(getattr(request, "query_params", {}).get("preview") or "").lower() == "html"
    if preview_requested and path.suffix.lower() == ".pdf":
        preview_path = path.parent / "audit-report.html"
        data, path = _read_owned_file(context, str(preview_path))
        filename = quote(preview_path.name)
        media_type = "text/html; charset=utf-8"
    else:
        filename = quote(str(document.get("report_name") or path.name))
        media_type = "application/pdf" if path.suffix.lower() == ".pdf" else "text/html; charset=utf-8"
    return Response(content=data, media_type=media_type, headers={
        "Content-Disposition": f"inline; filename*=utf-8''{filename}",
        "X-Content-Type-Options": "nosniff",
    })


async def download_report_file(request: Any, context: Any) -> Response:
    """Return the generated PDF or legacy HTML report as an attachment."""
    document = _require_document(context, _store(context))
    report_path = str(document.get("report_path") or "")
    if not report_path:
        raise ProviderError("Audit report is not ready", status_code=404, code="report_not_ready")
    data, path = _read_owned_file(context, report_path)
    filename = quote(str(document.get("report_name") or path.name))
    media_type = "application/pdf" if path.suffix.lower() == ".pdf" else "text/html; charset=utf-8"
    return Response(content=data, media_type=media_type, headers={
        "Content-Disposition": f"attachment; filename*=utf-8''{filename}",
        "X-Content-Type-Options": "nosniff",
    })


async def document_results(request: Any, context: Any) -> dict[str, Any]:
    """Return the per-rule verdicts for one completed document."""
    store = _store(context)
    document = _require_document(context, store)
    if document.get("status") != "completed":
        raise ProviderError("Audit results are not ready", status_code=404, code="results_not_ready")
    raw_report_path = str(document.get("report_path") or "").strip()
    report_path = Path(raw_report_path) if raw_report_path else None
    path = report_path.parent / "verification.json" if report_path is not None else _document_dir(context, document["id"]) / "verification.json"
    try:
        data, _verification_path = _read_owned_file(context, str(path))
    except ProviderError as exc:
        if exc.code == "file_not_found":
            raise ProviderError("Audit results are not ready", status_code=404, code="results_not_ready") from exc
        raise
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ProviderError(f"Audit results are unreadable: {exc}", status_code=500, code="results_unreadable") from exc
    if not isinstance(payload, dict):
        raise ProviderError("Audit results are unreadable", status_code=500, code="results_unreadable")
    raw_path = report_path.parent / "audit-raw.md" if report_path is not None else None
    if report_path is not None and report_path.suffix.lower() == ".pdf" and _owned_file_exists(context, str(raw_path)):
        # Rebuild display metadata after parser fixes from the saved LLM output;
        # do not rerun the audit or alter its Markdown/PDF.
        raw_data, _ = _read_owned_file(context, str(raw_path))
        required_ids = [item["rule"] for item in payload.get("results") or [] if isinstance(item, dict) and item.get("rule")]
        refreshed, summary = _llm_report_metadata(raw_data.decode("utf-8"), required_ids, allow_incomplete=True)
        completion: dict[str, Any] | None = None
        completion_path = report_path.parent / "completion.json"
        if _owned_file_exists(context, str(completion_path)):
            try:
                completion_data, _ = _read_owned_file(context, str(completion_path))
                parsed_completion = json.loads(completion_data.decode("utf-8"))
                if isinstance(parsed_completion, dict):
                    completion = parsed_completion
            except (UnicodeDecodeError, ValueError):
                completion = None
        previous_completeness = payload.get("completeness")
        if not isinstance(previous_completeness, dict):
            previous_completeness = {}
        pipeline_status = previous_completeness.get("pipeline_status")
        pipeline_warnings = previous_completeness.get("pipeline_warnings")
        if not isinstance(pipeline_warnings, list):
            pipeline_warnings = []
        if completion is not None and completion.get("completion_status") in {"complete", "needs_review"}:
            pipeline_status = completion["completion_status"]
            completion_warnings = completion.get("warnings")
            pipeline_warnings = [item for item in completion_warnings if isinstance(item, str)] if isinstance(completion_warnings, list) else []
        if pipeline_status == "needs_review":
            refreshed["completion_status"] = "needs_review"
            refreshed["warnings"] = list(dict.fromkeys([
                *refreshed.get("warnings", []), *pipeline_warnings,
            ]))
            refreshed["completeness"] = {
                **refreshed.get("completeness", {}),
                "pipeline_status": "needs_review",
                "pipeline_warnings": pipeline_warnings,
            }
        if refreshed != payload:
            temporary = _verification_path.with_name(f"{_verification_path.name}.{uuid.uuid4().hex}.tmp")
            try:
                temporary.write_text(json.dumps(refreshed, ensure_ascii=False, indent=2), encoding="utf-8")
                temporary.replace(_verification_path)
            finally:
                temporary.unlink(missing_ok=True)
        # The JSON file may have been refreshed before a prior DB update failed.
        # Compare against the stored row so a retry can repair the index.
        if any(document.get(key) != value for key, value in summary.items()):
            await asyncio.to_thread(store.update, document["id"], **summary)
        payload = refreshed
    results = [item for item in payload.get("results") or [] if isinstance(item, dict)]
    findings = [item for item in payload.get("findings") or [] if isinstance(item, dict)]
    counts = {"PASS": 0, "FAIL": 0, "REVIEW": 0, "NA": 0}
    for item in results:
        verdict = str(item.get("verdict") or "").upper()
        if verdict in counts:
            counts[verdict] += 1
    overall_verdict = payload.get("verdict")
    if not overall_verdict:
        if report_path is not None and report_path.suffix.lower() != ".pdf" and (counts["FAIL"] or counts["REVIEW"]):
            overall_verdict = "不通过"
        else:
            overall_verdict = "待复核（模型未给出结论）"
    response = {
        "document_id": document["id"],
        "file_name": document.get("file_name") or "",
        "verdict": overall_verdict,
        "counts": counts,
        "results": results,
        "findings": findings,
        "report_available": _owned_file_exists(context, str(document.get("report_path") or "")),
    }
    for key in ("completion_status", "warnings", "completeness"):
        if key in payload:
            response[key] = payload[key]
    if "completion_status" not in response:
        response["completion_status"] = "needs_review"
        existing_warnings = payload.get("warnings")
        response["warnings"] = list(existing_warnings) if isinstance(existing_warnings, list) else []
        if not payload.get("verdict") and "overall_verdict_missing" not in response["warnings"]:
            response["warnings"].append("overall_verdict_missing")
        if "coverage_metadata_unavailable" not in response["warnings"]:
            response["warnings"].append("coverage_metadata_unavailable")
        response["completeness"] = {
            "overall_verdict": bool(payload.get("verdict")),
            "coverage_table": None,
        }
    return response


async def document_evidence(request: Any, context: Any) -> Response:
    """Return one rendered evidence screenshot for a completed document."""
    document = _require_document(context, _store(context))
    name = str(context.path_params.get("evidence_name") or "").strip()
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise ProviderError("Evidence image not found", status_code=404, code="evidence_not_found")
    raw_report_path = str(document.get("report_path") or "").strip()
    report_path = Path(raw_report_path) if raw_report_path else None
    evidence_dir = report_path.parent / "evidence" if report_path is not None else _document_dir(context, document["id"]) / "evidence"
    data, _path = _read_owned_file(context, str(evidence_dir / name))
    return Response(content=data, media_type="image/png", headers={
        "Cache-Control": "private, max-age=3600",
        "X-Content-Type-Options": "nosniff",
    })


async def delete_document(request: Any, context: Any) -> dict[str, Any]:
    """Delete one document and its provider-owned files."""
    store = _store(context)
    document = _require_document(context, store)
    if document.get("status") == "running":
        raise ProviderError("Cannot delete a document while its audit is running.", status_code=409, code="audit_running")
    deleted = await asyncio.to_thread(store.delete, document["id"], _user_id(context))
    if not deleted and (await asyncio.to_thread(store.get, document["id"], _user_id(context)) or {}).get("status") == "running":
        raise ProviderError("Cannot delete a document while its audit is running.", status_code=409, code="audit_running")
    if deleted:
        await asyncio.to_thread(shutil.rmtree, _document_dir(context, document["id"]), True)
    return {"deleted": bool(deleted), "id": document["id"]}


async def download_desensitized(request: Any, context: Any) -> Response:
    """Return the prepared, desensitized PDF inline."""
    document = _require_document(context, _store(context))
    data, path = _read_owned_file(context, str(document.get("desensitized_path") or ""))
    filename = quote(str(document.get("desensitized_name") or path.name))
    return Response(content=data, media_type="application/pdf", headers={
        "Content-Disposition": f"inline; filename*=utf-8''{filename}",
        "X-Content-Type-Options": "nosniff",
    })


async def download_desensitized_file(request: Any, context: Any) -> Response:
    """Return the prepared, desensitized PDF as an attachment."""
    document = _require_document(context, _store(context))
    data, path = _read_owned_file(context, str(document.get("desensitized_path") or ""))
    filename = quote(str(document.get("desensitized_name") or path.name))
    return Response(content=data, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename*=utf-8''{filename}",
        "X-Content-Type-Options": "nosniff",
    })


_STANDARD_TASKS: set[asyncio.Task] = set()


def _standard_response(context: Any, standard: dict[str, Any]) -> dict[str, Any]:
    base = f"{_provider_base(context)}/standards/{standard['id']}"
    status = str(standard.get("status") or standards_service.STATUS_COMPILING)
    return {
        "id": standard["id"],
        "file_name": standard.get("file_name") or "",
        "extension": standard.get("extension") or ".pdf",
        "size": int(standard.get("size") or 0),
        "pages": standard.get("pages"),
        "status": status,
        "kind": standard.get("kind") or "other",
        "read_status": standard.get("read_status") or "",
        "read_error": str(standard.get("read_error") or "")[:400],
        "error_message": str(standard.get("error_message") or "")[:400],
        "pack": standard.get("pack") or "",
        "rules": int(standard.get("rules") or 0),
        "uploaded_by": standard.get("uploaded_by") or "",
        "shared": True,
        "created_at": standard.get("created_at") or "",
        "urls": {"file": f"{base}/file", "refresh": f"{base}/refresh"},
        "actions": ["download", "refresh", "recompile", "delete"],
    }


def _schedule_prepare(context: Any, standard_id: str) -> None:
    """Read an uploaded shared reference without interpreting or compiling it."""
    task = asyncio.create_task(standards_service.prepare_standard(context.host, standard_id))
    _STANDARD_TASKS.add(task)
    task.add_done_callback(_STANDARD_TASKS.discard)


def _require_standard(context: Any, standard_id: str) -> dict[str, Any]:
    standard = standards_service.get_standard(context.host, standard_id)
    if standard is None:
        raise ProviderError("Standard not found", status_code=404, code="standard_not_found")
    return standard


async def list_standards(request: Any, context: Any) -> dict[str, Any]:
    """Return the provider-wide audit standard library (shared by all users)."""
    standards = await asyncio.to_thread(standards_service.list_standards, context.host)
    return {"items": [_standard_response(context, standard) for standard in standards], "total": len(standards)}


async def upload_standard(request: Any, context: Any) -> dict[str, Any]:
    """Accept one shared audit reference and read it in the background."""
    form = await request.form()
    upload = form.get("file")
    if upload is None or not hasattr(upload, "read"):
        raise ProviderError("A standard file is required.", status_code=422, code="file_required")
    file_name = standards_service.safe_name(str(getattr(upload, "filename", "") or "standard.pdf"))
    extension = Path(file_name).suffix.lower()
    if extension not in standards_service.SUPPORTED_SUFFIXES:
        raise ProviderError(
            "Only supported reference files are accepted.",
            status_code=422,
            code="unsupported_file",
        )
    standard_id = uuid.uuid4().hex
    standard_dir = await asyncio.to_thread(standards_service.standard_dir, context.host, standard_id)
    await asyncio.to_thread(lambda: standard_dir.mkdir(parents=True, exist_ok=True))
    temp_path = standard_dir / "upload.part"
    total_bytes = 0
    try:
        with temp_path.open("wb") as file_obj:
            while True:
                chunk = await upload.read(UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                total_bytes += len(chunk)
                file_obj.write(chunk)
        if total_bytes == 0:
            raise ProviderError("The standard file is empty.", status_code=422, code="invalid_document")
        file_path = standard_dir / f"original{extension}"
        await asyncio.to_thread(temp_path.replace, file_path)
        sha256 = await asyncio.to_thread(_sha256_file, file_path)
    except BaseException:
        await asyncio.to_thread(shutil.rmtree, standard_dir, True)
        raise

    standard = await asyncio.to_thread(
        standards_service.create_standard,
        context.host,
        standard_id=standard_id,
        file_name=file_name,
        file_path=file_path,
        extension=extension,
        size=total_bytes,
        sha256=sha256,
        pages=None,
        uploader=_user_id(context),
    )
    _schedule_prepare(context, standard_id)
    return _standard_response(context, standard)


async def refresh_standard(request: Any, context: Any) -> dict[str, Any]:
    """Refresh the local text extraction state for one shared reference."""
    standard_id = str(context.path_params.get("standard_id") or "").strip()
    standard = await asyncio.to_thread(_require_standard, context, standard_id)
    _schedule_prepare(context, standard_id)
    standard["read_status"] = standards_service.READ_READING
    standard["read_error"] = ""
    return _standard_response(context, standard)


async def recompile_standard(request: Any, context: Any) -> dict[str, Any]:
    """Re-run compilation for one standard after the source document changed."""
    standard_id = str(context.path_params.get("standard_id") or "").strip()
    standard = await asyncio.to_thread(_require_standard, context, standard_id)
    if standard.get("status") == standards_service.STATUS_COMPILING:
        raise ProviderError("This standard is already compiling.", status_code=409, code="compiling")
    await asyncio.to_thread(
        standards_service.update_standard,
        context.host, standard_id, status=standards_service.STATUS_COMPILING, error_message="",
    )
    task = asyncio.create_task(standards_service.compile_standard(context.host, standard_id))
    _STANDARD_TASKS.add(task)
    task.add_done_callback(_STANDARD_TASKS.discard)
    return _standard_response(context, standard)


async def download_standard(request: Any, context: Any) -> Response:
    """Return one shared audit standard file."""
    standard_id = str(context.path_params.get("standard_id") or "").strip()
    standard = await asyncio.to_thread(_require_standard, context, standard_id)
    path = Path(str(standard.get("file_path") or ""))
    if not path.is_file():
        raise ProviderError("Standard file is missing", status_code=404, code="file_not_found")
    data = await asyncio.to_thread(path.read_bytes)
    media_type = CONTENT_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    filename = quote(str(standard.get("file_name") or path.name))
    return Response(content=data, media_type=media_type, headers={
        "Content-Disposition": f"attachment; filename*=utf-8''{filename}",
        "X-Content-Type-Options": "nosniff",
    })


async def delete_standard(request: Any, context: Any) -> dict[str, Any]:
    """Delete one standard, its compiled rule pack and its config entry."""
    standard_id = str(context.path_params.get("standard_id") or "").strip()
    await asyncio.to_thread(_require_standard, context, standard_id)
    deleted = await asyncio.to_thread(standards_service.delete_standard, context.host, standard_id)
    return {"deleted": bool(deleted), "id": standard_id}
