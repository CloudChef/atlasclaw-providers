# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.
"""Handler helpers: upload validation, document serialization and summary parsing."""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path
from datetime import datetime
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(ROOT / "skills" / "audit-report" / "scripts"))

import handlers  # noqa: E402
import batch_audit  # noqa: E402
from errors import ProviderError  # noqa: E402
from report_no import extract_report_no  # noqa: E402
from store import DocumentStore  # noqa: E402


async def _unused_visual(**_kwargs) -> str:
    return "### Page 1\nVisual observation"


@pytest.mark.asyncio
async def test_configured_report_storage_upload_and_download_are_user_scoped(tmp_path: Path) -> None:
    class Upload:
        filename = "report.pdf"

        def __init__(self) -> None:
            self.data = b"%PDF-test"

        async def read(self, size: int) -> bytes:
            chunk, self.data = self.data[:size], self.data[size:]
            return chunk

    class Request:
        query_params = {}

        async def form(self) -> dict:
            return {"file": Upload()}

    reports = tmp_path / "reports"
    host = SimpleNamespace(
        data_dir=tmp_path / "index" / "tenant-a" / "alice",
        config={"reports_dir": str(reports)},
        user=SimpleNamespace(user_id="alice", tenant_id="tenant-a"),
    )
    context = SimpleNamespace(
        host=host, user_id="alice", provider_type="audit-report", provider_instance="default",
        path_params={},
    )

    uploaded = await handlers.upload_document(Request(), context)
    stored_path = reports / "tenant-a" / "alice" / "documents" / uploaded["id"] / "original.pdf"
    assert stored_path.read_bytes() == b"%PDF-test"
    assert (reports / "tenant-a" / "alice" / "audit.db").is_file()

    context.path_params = {"document_id": uploaded["id"]}
    response = await handlers.download_document(Request(), context)
    assert response.body == b"%PDF-test"

    other_context = SimpleNamespace(
        host=SimpleNamespace(data_dir=host.data_dir, config={"reports_dir": str(reports)},
                             user=SimpleNamespace(user_id="bob", tenant_id="tenant-a")),
        user_id="bob", path_params={"document_id": uploaded["id"]},
    )
    with pytest.raises(ProviderError) as error:
        await handlers.download_document(Request(), other_context)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_configured_report_storage_places_audit_attempts_under_user_root(tmp_path: Path, monkeypatch) -> None:
    import audit_service

    reports = tmp_path / "reports"
    host = SimpleNamespace(
        data_dir=tmp_path / "index" / "tenant-a" / "alice",
        config={"reports_dir": str(reports)},
        user=SimpleNamespace(user_id="alice", tenant_id="tenant-a"),
    )
    store = DocumentStore(reports / "tenant-a" / "alice")
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-source")
    document = store.create({
        "id": "doc-1", "user_id": "alice", "file_name": "source.pdf",
        "file_path": str(source), "extension": ".pdf", "sha256": "",
    })
    context = SimpleNamespace(host=host, run_text=lambda **_kwargs: None, run_visual=_unused_visual)
    started = asyncio.Event()
    observed: list[Path] = []

    async def capture_attempt(_context, _store, _document, attempt_dir: Path) -> None:
        observed.append(attempt_dir)
        started.set()

    monkeypatch.setattr(audit_service, "_run_document_audit", capture_attempt)
    await audit_service.start_document_audit(context, store, document)
    await asyncio.wait_for(started.wait(), timeout=2)
    assert observed[0].is_relative_to(reports / "tenant-a" / "alice" / "documents" / "doc-1" / "runs")


@pytest.mark.asyncio
async def test_configured_report_storage_runs_pipeline_and_publishes_external_paths(tmp_path: Path, monkeypatch) -> None:
    import types
    import audit_service

    reports = tmp_path / "reports"
    user_root = reports / "tenant-a" / "alice"
    host = SimpleNamespace(
        data_dir=tmp_path / "old-index",
        config={"reports_dir": str(reports)},
        user=SimpleNamespace(user_id="alice", tenant_id="tenant-a"),
    )
    store = DocumentStore(user_root)
    source = user_root / "documents" / "doc-2" / "original.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF-source")
    document = store.create({
        "id": "doc-2", "user_id": "alice", "file_name": "source.pdf",
        "file_path": str(source), "extension": ".pdf", "sha256": "",
    })
    skill = tmp_path / "skill"
    (skill / "references").mkdir(parents=True)
    (skill / "references" / "audit-system.md").write_text("system", encoding="utf-8")
    monkeypatch.setattr(audit_service, "_skill_dir", lambda: skill)

    def prepare_report(_source: str, output_dir: Path) -> dict:
        output_dir.mkdir(parents=True, exist_ok=True)
        prepared = output_dir / "desensitized.pdf"
        prepared.write_bytes(b"%PDF-prepared")
        return {"pdf": str(prepared)}

    preparation = types.SimpleNamespace(
        PREPARATION_VERSION=1,
        prepare_report=prepare_report,
        prepare_visual_pdf=lambda source, _output: {"pdf": str(source)},
    )
    metadata_inputs: list[str] = []
    async def audit_prepared(prepared_pdf, _materials, attempt_dir, _submit, **_kwargs):
        assert Path(prepared_pdf).is_relative_to(user_root)
        Path(attempt_dir, "audit-report.pdf").write_bytes(b"%PDF-report")
        Path(attempt_dir, "audit-raw.md").write_text("audited", encoding="utf-8")
        Path(attempt_dir, "audit.md").write_text("published normalized report", encoding="utf-8")

    monkeypatch.setitem(sys.modules, "audit_preparation", preparation)
    monkeypatch.setitem(sys.modules, "run_document_audit", types.SimpleNamespace(audit_prepared=audit_prepared))
    monkeypatch.setattr(audit_service.standards_service, "snapshot_audit_library", lambda _host, target: {
        "material_paths": [], "rules_dir": target / "rules",
    })
    def capture_metadata(markdown, *_args, **_kwargs):
        metadata_inputs.append(markdown)
        return (
            {"verdict": "通过", "results": [], "findings": []},
            {"findings_total": 0, "findings_review": 0, "grade_summary": {}},
        )

    monkeypatch.setattr(audit_service, "_llm_report_metadata", capture_metadata)
    context = SimpleNamespace(host=host, run_text=lambda **_kwargs: "ok", run_visual=_unused_visual)
    attempt = user_root / "documents" / "doc-2" / "runs" / "attempt"

    await audit_service._run_document_audit(context, store, document, attempt)

    updated = store.get("doc-2", "alice")
    assert updated["status"] == "completed"
    assert Path(updated["report_path"]) == attempt / "audit-report.pdf"
    assert Path(updated["desensitized_path"]).is_relative_to(user_root)
    assert metadata_inputs == ["published normalized report"]


@pytest.mark.asyncio
async def test_incomplete_skill_run_cannot_publish_report_but_keeps_prepared_pdf(tmp_path: Path, monkeypatch) -> None:
    import audit_service
    import audit_preparation
    import run_document_audit

    store = DocumentStore(tmp_path)
    original = tmp_path / "large.pdf"
    original.write_bytes(b"placeholder")
    doc_dir = tmp_path / "documents" / "doc"
    prepared_dir = doc_dir / f"prepared-v{audit_preparation.PREPARATION_VERSION}"
    prepared = prepared_dir / "desensitized.pdf"
    prepared_dir.mkdir(parents=True)
    prepared.write_bytes(b"%PDF prepared")
    legacy_prepared = doc_dir / "prepared" / "desensitized.pdf"
    legacy_prepared.parent.mkdir(parents=True)
    legacy_prepared.write_bytes(b"legacy-v3-prepared")
    document = store.create({"id": "doc", "user_id": "alice", "status": "running", "file_name": "large.pdf",
                             "file_path": str(original), "extension": ".pdf", "sha256": ""})
    async def unused_text(**_kwargs) -> str:
        return ""

    host = SimpleNamespace(data_dir=tmp_path, agent=object(), run_text=unused_text, run_visual=_unused_visual)
    prepare_outputs: list[Path] = []

    def prepare(source_path: str, output_dir: Path) -> dict:
        output_dir = Path(output_dir)
        prepare_outputs.append(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        prepared_path = output_dir / "desensitized.pdf"
        prepared_path.write_bytes(b"%PDF prepared")
        return {"pdf": str(prepared_path)}

    monkeypatch.setattr(audit_preparation, "prepare_report", prepare)
    visual_source = doc_dir / "visual-source.pdf"
    monkeypatch.setattr(audit_preparation, "prepare_visual_pdf", lambda _source, _output: {
        "pdf": str(visual_source),
    })
    monkeypatch.setattr(audit_service.standards_service, "snapshot_audit_library", lambda *_args: {
        "material_paths": [], "rules_dir": tmp_path / "rules",
    })

    async def incomplete(*_args, **_kwargs):
        raise RuntimeError("LLM response incomplete: missing formal pages")

    monkeypatch.setattr(run_document_audit, "audit_prepared", incomplete)
    await audit_service._run_document_audit(host, store, document, tmp_path / "runs" / "attempt-1")
    await audit_service._run_document_audit(host, store, document, tmp_path / "runs" / "attempt-2")

    result = store.get(document["id"], "alice")
    assert result["status"] == "failed"
    assert result["error_code"] == "run_failed"
    assert result["desensitized_path"] == str(prepared)
    assert not result["report_path"]
    expected_dir = doc_dir / f"prepared-v{audit_preparation.PREPARATION_VERSION}"
    assert prepare_outputs == [expected_dir, expected_dir]
    assert legacy_prepared.read_bytes() == b"legacy-v3-prepared"


@pytest.mark.asyncio
async def test_skill_pipeline_uses_core_model_bridges_without_host_selector(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import audit_service
    import audit_preparation
    import run_document_audit

    store = DocumentStore(tmp_path)
    original = tmp_path / "source.pdf"
    original.write_bytes(b"synthetic")
    doc_dir = tmp_path / "documents" / "doc"
    prepared = doc_dir / f"prepared-v{audit_preparation.PREPARATION_VERSION}" / "desensitized.pdf"
    prepared.parent.mkdir(parents=True)
    prepared.write_bytes(b"%PDF synthetic")
    document = store.create({
        "id": "doc", "user_id": "alice", "status": "running", "file_name": "source.pdf",
        "file_path": str(original), "extension": ".pdf", "sha256": "",
    })
    prepare_calls: list[bool] = []
    text_calls: list[dict] = []

    class Agent:
        def start_run(self, **_kwargs) -> None:
            raise AssertionError("scripted text calls must not use the Host capability selector")

    host = SimpleNamespace(data_dir=tmp_path, agent=Agent())

    async def run_text(**kwargs) -> str:
        text_calls.append(kwargs)
        return "synthetic response"

    context = SimpleNamespace(host=host, run_text=run_text, run_visual=_unused_visual)

    def prepare(*_args):
        prepare_calls.append(True)
        return {"pdf": str(prepared)}

    monkeypatch.setattr(audit_preparation, "prepare_report", prepare)
    visual_source = doc_dir / "runs" / "visual-source.pdf"
    visual_source.parent.mkdir(parents=True, exist_ok=True)
    visual_source.write_bytes(b"%PDF visual source")
    monkeypatch.setattr(audit_preparation, "prepare_visual_pdf", lambda _source, _output: {
        "pdf": str(visual_source),
    })
    monkeypatch.setattr(audit_service.standards_service, "snapshot_audit_library", lambda *_args: {
        "material_paths": [], "rules_dir": tmp_path / "rules",
    })
    progress_updates: list[tuple[int | None, str]] = []
    original_progress = audit_service._progress

    async def capture_progress(_store, _document_id, value, text):
        progress_updates.append((value, text))
        await original_progress(_store, _document_id, value, text)

    monkeypatch.setattr(audit_service, "_progress", capture_progress)

    async def call_submit(_pdf, _materials, _out, submit, **kwargs):
        assert set(kwargs) == {
            "on_progress", "rules_dir", "visual_pdf", "submit_visual", "require_visual",
            "visual_prepare_error", "source_metadata",
        }
        assert kwargs["source_metadata"]["file_name"] == "source.pdf"
        assert Path(kwargs["visual_pdf"]) == visual_source
        assert callable(kwargs["submit_visual"]) and kwargs["require_visual"] is True
        await kwargs["on_progress"]({"stage": "projects", "completed": 1, "total": 2})
        await kwargs["on_progress"]({"stage": "project-review", "completed": 1, "total": 1})
        for stage in ("index", "project-review", "summary"):
            assert await submit(f"request for {stage}") == "synthetic response"
        raise RuntimeError("test stopped after text bridge calls")

    monkeypatch.setattr(run_document_audit, "audit_prepared", call_submit)
    await audit_service._run_document_audit(context, store, document, doc_dir / "runs" / "attempt-2")
    assert prepare_calls == [True]
    system_prompt = (ROOT / "skills" / "audit-report" / "references" / "audit-system.md").read_text(encoding="utf-8")
    assert len(text_calls) == 3
    assert all(call["system_prompt"] == system_prompt for call in text_calls)
    assert all(set(call) == {"prompt", "system_prompt", "skill_id"} for call in text_calls)
    assert all(call["skill_id"] == "audit-report:audit-report" for call in text_calls)
    stage_progress = [(value, text) for value, text in progress_updates if "准备逐项目审核" in text or "审核检测项目" in text]
    assert stage_progress[0][0] == 61
    assert stage_progress[1][0] is None
    assert not (doc_dir / "runs" / "attempt-2" / "runtime-model.json").exists()
    result = store.get(document["id"], "alice")
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_start_document_audit_without_model_bridges_still_claims_a_report_run(tmp_path: Path, monkeypatch) -> None:
    import audit_service
    import asyncio

    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF synthetic")
    store = DocumentStore(tmp_path)
    document = store.create({
        "id": "doc", "user_id": "alice", "status": "uploaded", "file_name": source.name,
        "file_path": str(source), "extension": ".pdf", "sha256": "",
    })
    context = SimpleNamespace(host=SimpleNamespace(data_dir=tmp_path))
    started = asyncio.Event()

    async def record_run(*_args, **_kwargs) -> None:
        started.set()

    monkeypatch.setattr(audit_service, "_run_document_audit", record_run)
    await audit_service.start_document_audit(context, store, document)
    await asyncio.wait_for(started.wait(), timeout=1)
    assert store.get(document["id"], "alice")["status"] == "running"


@pytest.mark.asyncio
async def test_different_documents_for_same_user_run_independently(tmp_path: Path, monkeypatch) -> None:
    import audit_service

    store = DocumentStore(tmp_path)
    context = SimpleNamespace(
        host=SimpleNamespace(data_dir=tmp_path), run_text=lambda **_kwargs: None, run_visual=_unused_visual,
    )
    documents = []
    for document_id in ("doc-a", "doc-b"):
        source = tmp_path / f"{document_id}.pdf"
        source.write_bytes(b"%PDF-1.4 synthetic")
        documents.append(store.create({
            "id": document_id, "user_id": "alice", "status": "uploaded",
            "file_name": source.name, "file_path": str(source), "extension": ".pdf", "sha256": "",
        }))

    started = {document["id"]: asyncio.Event() for document in documents}
    releases = {document["id"]: asyncio.Event() for document in documents}
    finished = {document["id"]: asyncio.Event() for document in documents}

    async def hold_run(_context, run_store, document, _attempt_dir):
        document_id = document["id"]
        started[document_id].set()
        try:
            await releases[document_id].wait()
            await asyncio.to_thread(run_store.update, document_id, status="completed")
        finally:
            finished[document_id].set()

    monkeypatch.setattr(audit_service, "_run_document_audit", hold_run)
    try:
        await audit_service.start_document_audit(context, store, documents[0])
        await audit_service.start_document_audit(context, store, documents[1])
        await asyncio.wait_for(asyncio.gather(*(event.wait() for event in started.values())), timeout=2)

        with pytest.raises(ProviderError) as exc:
            await audit_service.start_document_audit(context, store, documents[0])
        assert exc.value.code == "audit_already_running"

        releases["doc-a"].set()
        await asyncio.wait_for(finished["doc-a"].wait(), timeout=2)
        assert store.get("doc-a", "alice")["status"] == "completed"
        assert store.get("doc-b", "alice")["status"] == "running"
        with pytest.raises(ProviderError) as exc:
            await audit_service.start_document_audit(context, store, documents[1])
        assert exc.value.code == "audit_already_running"
    finally:
        releases["doc-a"].set()
        releases["doc-b"].set()
        await asyncio.gather(*(event.wait() for event in finished.values()))

    assert (store.db_path.resolve(), "doc-a") not in audit_service._TASKS
    assert (store.db_path.resolve(), "doc-b") not in audit_service._TASKS


@pytest.mark.asyncio
async def test_reconcile_only_fails_observed_orphan_not_other_active_document(
    tmp_path: Path, monkeypatch,
) -> None:
    import audit_service

    store = DocumentStore(tmp_path)
    context = SimpleNamespace(
        host=SimpleNamespace(data_dir=tmp_path), run_text=lambda **_kwargs: None, run_visual=_unused_visual,
    )
    active_source = tmp_path / "active.pdf"
    orphan_source = tmp_path / "orphan.pdf"
    active_source.write_bytes(b"%PDF-1.4 active")
    orphan_source.write_bytes(b"%PDF-1.4 orphan")
    active = store.create({
        "id": "active", "user_id": "alice", "status": "uploaded", "file_name": active_source.name,
        "file_path": str(active_source), "extension": ".pdf", "sha256": "",
    })
    orphan = store.create({
        "id": "orphan", "user_id": "alice", "status": "running", "file_name": orphan_source.name,
        "file_path": str(orphan_source), "extension": ".pdf", "sha256": "",
    })
    release = asyncio.Event()
    started = asyncio.Event()

    async def hold_run(_context, _store, _document, _attempt_dir):
        started.set()
        await release.wait()

    monkeypatch.setattr(audit_service, "_run_document_audit", hold_run)
    try:
        await audit_service.start_document_audit(context, store, active)
        await asyncio.wait_for(started.wait(), timeout=2)

        reconciled = await audit_service.reconcile_document(store, orphan)

        assert reconciled["status"] == "failed"
        assert reconciled["error_code"] == "host_restarted"
        assert store.get("active", "alice")["status"] == "running"
        active_task = audit_service._TASKS[(store.db_path.resolve(), "active")][1]
        assert not active_task.done()
    finally:
        release.set()


@pytest.mark.parametrize("prefix", ["", "## Page 1\n\n"])
def test_text_over_many_batches_is_retained_in_full(prefix: str, monkeypatch) -> None:
    monkeypatch.setattr(batch_audit, "MAX_CHUNK_CHARS", 25)
    source = prefix + ("x" * 225) + "TAIL-SENTINEL"
    chunks, note = batch_audit.chunk_document(source)
    assert len(chunks) > 8
    assert all(len(chunk.text) <= 25 for chunk in chunks)
    assert "TAIL-SENTINEL" in "".join(chunk.text for chunk in chunks)
    assert "".join(chunk.text for chunk in chunks).endswith("TAIL-SENTINEL")
    assert note == ""


@pytest.mark.asyncio
async def test_start_does_not_recover_other_documents_until_they_are_observed(tmp_path: Path, monkeypatch) -> None:
    import audit_service

    source = tmp_path / "report.pdf"
    source.write_bytes(b"%PDF-1.4")
    store = DocumentStore(tmp_path)
    fields = {"user_id": "alice", "file_name": source.name, "file_path": str(source), "extension": ".pdf", "sha256": ""}
    old = store.create({**fields, "status": "running", "run_id": ""})
    new = store.create(fields)
    async def unused_text(**_kwargs) -> str:
        return ""

    context = SimpleNamespace(user_id="alice", provider_type="audit-report", provider_instance="default",
                              path_params={"document_id": new["id"]}, host=SimpleNamespace(data_dir=tmp_path, agent=object()),
                              run_text=unused_text, run_visual=_unused_visual)
    release = asyncio.Event()

    async def run(*args):
        await release.wait()

    monkeypatch.setattr(audit_service, "_run_document_audit", run)
    try:
        result = await handlers.start_audit(None, context)
        assert result["status"] == "running"
        assert store.get(old["id"], "alice")["status"] == "running"
        recovered = await audit_service.reconcile_document(store, old)
        assert recovered["error_code"] == "host_restarted"
        assert store.get(new["id"], "alice")["status"] == "running"
        progress = await handlers.get_document(None, context)
        assert progress["status"] == "running"
        with pytest.raises(ProviderError) as exc:
            await handlers.start_audit(None, context)
        assert exc.value.status_code == 409
    finally:
        release.set()


def _upload_file(tmp_path: Path, name: str, data: bytes) -> Path:
    target = tmp_path / name
    target.write_bytes(data)
    return target


def test_upload_validation_accepts_pdf_and_docx(tmp_path: Path) -> None:
    assert handlers._validate_upload(_upload_file(tmp_path, "report.pdf", b"%PDF-1.4 body"), "report.pdf") == ".pdf"


def test_upload_validation_rejects_bad_inputs_without_provider_size_cap(tmp_path: Path) -> None:
    with pytest.raises(ProviderError) as exc:
        handlers._validate_upload(_upload_file(tmp_path, "report.xls", b"x"), "report.xls")
    assert exc.value.code == "unsupported_file"

    with pytest.raises(ProviderError) as exc:
        handlers._validate_upload(_upload_file(tmp_path, "bad.pdf", b"not a pdf"), "bad.pdf")
    assert exc.value.code == "invalid_document"

    assert handlers._validate_upload(_upload_file(tmp_path, "larger.pdf", b"%PDF-123456"), "larger.pdf") == ".pdf"
    assert not hasattr(handlers, "MAX_DOCUMENT_BYTES")


def test_document_response_and_actions(tmp_path: Path) -> None:
    report = tmp_path / "documents" / "doc-1" / "runs" / "attempt" / "audit-report.pdf"
    desensitized = tmp_path / "documents" / "doc-1" / "prepared" / "脱敏.pdf"
    report.parent.mkdir(parents=True)
    desensitized.parent.mkdir(parents=True)
    report.write_bytes(b"%PDF")
    desensitized.write_bytes(b"%PDF")
    context = SimpleNamespace(user_id="alice", provider_type="audit-report", provider_instance="qa-instance",
                              host=SimpleNamespace(data_dir=tmp_path))
    document = {
        "id": "doc-1",
        "file_name": "report.pdf",
        "report_no": "RPT-2026-0001",
        "status": "completed",
        "findings_total": 13,
        "findings_review": 4,
        "grade_summary": {"A": 9, "B": 4},
        "report_path": str(report),
        "report_name": "审核.pdf",
        "desensitized_path": str(desensitized),
        "desensitized_name": "脱敏.pdf",
        "created_at": "2026-11-24T10:32:00Z",
        "updated_at": "2026-11-24T10:35:00Z",
    }

    payload = handlers._document_response(context, document)

    assert payload["status"] == "completed"
    assert payload["report_available"] is True
    assert payload["report_format"] == "pdf"
    assert payload["desensitized_available"] is True
    assert payload["actions"] == ["view_result", "download_report", "reaudit", "delete", "download_desensitized"]
    assert payload["urls"]["report"].endswith("/documents/doc-1/report")
    assert "/qa-instance/" in payload["urls"]["report_download"]
    assert payload["urls"]["report_preview"].endswith("/report?preview=html")
    document["report_path"] = str(tmp_path / "missing.pdf")
    document["desensitized_path"] = str(tmp_path / "missing-desensitized.pdf")
    unavailable = handlers._document_response(context, document)
    assert unavailable["report_available"] is False
    assert unavailable["desensitized_available"] is False


def test_legacy_standard_without_read_state_keeps_empty_read_status() -> None:
    context = SimpleNamespace(provider_type="audit-report", provider_instance="legacy")
    response = handlers._standard_response(context, {"id": "standard-old", "status": "active"})
    assert response["status"] == "active"
    assert response["read_status"] == ""


def test_llm_report_metadata_reads_only_main_coverage_and_explicit_verdict() -> None:
    import audit_service

    rule_ids = [f"R{i:02d}" for i in range(1, 20)] + ["C01"]
    rows = [f"| {rule} | 模块 | 通过标准检查项 | A | **通过** | 证据 |" for rule in rule_ids]
    markdown = "# 审核报告\n\n## 2. 总评\n\n**总评：不通过（不合格）**\n\n## 5. 检查覆盖表\n\n" + "\n".join(rows)
    markdown += "\n\n## 6. 问题详情\n\n提及 F-000009 但不新建问题。\n\n# 附录：分项目审核原文\n\n### F-1000-999 [A] 项目问题（R12）\n\n- **页码**：第 12 页\n- **不规范说明**：源数据不符合判定要求。\n\n### F-1000-1000 [B] 下一问题（R01）\n\n- **页码**：第 13 页\n- **不规范说明**：第二个问题。\n\n## 项目覆盖表\n| R01 | ... |"

    verification, summary = audit_service._llm_report_metadata(markdown, rule_ids)

    assert verification["verdict"] == "不通过（不合格）"
    assert len(verification["results"]) == 20
    assert verification["counts"]["PASS"] == 20
    assert verification["finding_ids"] == ["F-1000-999", "F-1000-1000"]
    assert verification["findings"] == [
        {"id": "F-1000-999", "rule": "R12", "severity": "A",
         "title": "项目问题", "page": "第 12 页", "problem": "源数据不符合判定要求。"},
        {"id": "F-1000-1000", "rule": "R01", "severity": "B",
         "title": "下一问题", "page": "第 13 页", "problem": "第二个问题。"},
    ]
    assert summary["grade_summary"] == {"A": 1, "B": 1, "C": 0}


@pytest.mark.parametrize("status", ["待复核", "证据不足"])
def test_llm_report_metadata_maps_review_coverage_to_review_not_pass_or_na(status: str) -> None:
    import audit_service

    markdown = (
        "# 报告\n**总评：暂缓判定**\n\n## 检查覆盖表\n"
        f"| R01 | 文件完整性 | 页码连续 | B | {status} | 仅有脱敏后的文本证据 |\n"
    )
    verification, summary = audit_service._llm_report_metadata(markdown, ["R01"])

    assert verification["results"][0]["verdict"] == "REVIEW"
    assert verification["counts"] == {"PASS": 0, "FAIL": 0, "REVIEW": 1, "NA": 0}
    assert summary["findings_review"] == 1


@pytest.mark.parametrize("table", [
    "| 序号 | 规则号 | 等级 | 页码 |\n| --- | --- | --- | --- |\n| F-016-001 | R15 | C | 第269页 |",
    "| 序号 | 问题编号 | 规则号 | 等级 |\n| --- | --- | --- | --- |\n| 1 | F-016-001 | R15 | C |",
    "| 编号 | 规则号 | 原等级 | 最终等级 |\n| --- | --- | --- | --- |\n| F-016-001 | R15 | B | C |",
])
def test_llm_report_metadata_preserves_explicit_verdict_and_final_overview_grade(table: str) -> None:
    import audit_service

    markdown = (
        "# 报告\n**总评：待复核，需核对原始记录**\n\n# 检查覆盖表\n"
        "| R15 | 时间逻辑 | 校准日期 | A | 待复核 | 缺少历史证书 |\n\n"
        "## 问题总表\n" + table + "\n\n"
        "# 附录：分项目审核原文\n### F-016-001 [B] 校准记录待复核（R15）\n"
        "- **页码**：第269页\n- **规则号**：R15\n"
    )
    original = markdown
    verification, summary = audit_service._llm_report_metadata(markdown, ["R15"])

    assert verification["verdict"] == "待复核，需核对原始记录"
    assert verification["findings"][0]["severity"] == "C"
    assert summary["grade_summary"] == {"A": 0, "B": 0, "C": 1}
    assert markdown == original


def test_llm_report_metadata_fails_when_custom_rule_row_is_missing() -> None:
    import audit_service

    rows = "\n".join(f"| R{i:02d} | 模块 | 检查项 | A | 通过 | 证据 |" for i in range(1, 20))
    markdown = f"**总评：通过**\n\n## 检查覆盖表\n\n{rows}"
    with pytest.raises(RuntimeError, match="C01"):
        audit_service._llm_report_metadata(markdown, [f"R{i:02d}" for i in range(1, 20)] + ["C01"])


def test_llm_report_metadata_preserves_extended_rule_ids() -> None:
    import audit_service

    markdown = (
        "**总评：不通过**\n\n## 检查覆盖表\n"
        "| Z100 | 扩展规则 | 检查项 | A | 不通过 | 证据 |\n\n"
        "# 附录：分项目审核原文\n"
        "### F-1000-1000 [A] 扩展规则问题（Z100）\n"
        "- **页码**：第 8 页\n"
    )
    verification, _ = audit_service._llm_report_metadata(markdown, ["Z100"])
    assert verification["findings"][0]["rule"] == "Z100"
    assert verification["findings"][0]["title"] == "扩展规则问题"


def test_llm_report_metadata_matches_longest_complete_rule_id() -> None:
    import audit_service

    rule_ids = ["R01", "X10", "X100"]
    rows = "\n".join(
        f"| {rule} | 扩展规则 | 检查项 | A | 通过 | 证据 |" for rule in rule_ids
    )
    markdown = (
        f"**总评：不通过**\n\n## 检查覆盖表\n{rows}\n\n"
        "# 附录：分项目审核原文\n"
        "### F-001-001 [A] 扩展规则问题（X100）\n"
        "- **规则号**：`X100`\n- **页码**：第 8 页\n"
    )
    verification, _ = audit_service._llm_report_metadata(markdown, rule_ids)
    assert verification["findings"][0]["rule"] == "X100"


@pytest.mark.parametrize("rows, message", [
    ("| 1 | F-001-001 | 成立 | B | reason |", "missing final dispositions: F-002-001"),
    ("| 1 | F-001-001 | maybe | B | reason |\n| 2 | F-002-001 | 撤回 | C | reason |", "unrecognized final disposition"),
    ("| 1 | F-001-001 | 成立 |  | reason |\n| 2 | F-002-001 | 撤回 | C | reason |", "missing a valid final grade"),
    ("| 1 | F-003-001 | 成立 | B | mentioned F-001-001 |", "without detailed evidence: F-003-001"),
])
def test_llm_report_metadata_rejects_incomplete_or_unbacked_dispositions(rows: str, message: str) -> None:
    import audit_service

    markdown = (
        "**总评：不通过**\n\n## 问题总表\n"
        "| 序号 | FID | 复核结果 | 最终等级 | 复核依据 |\n| --- | --- | --- | --- | --- |\n"
        f"{rows}\n\n## 检查覆盖表\n| 规则号 | 模块 | 检查项 | 等级 | 结论 | 证据 |\n"
        "| --- | --- | --- | --- | --- | --- |\n| R01 | 模块 | 检查项 | A | 通过 | 证据 |\n\n"
        "### F-001-001 [B] 问题一（R01）\n- **页码**：第1页\n"
        "### F-002-001 [C] 问题二（R01）\n- **页码**：第2页\n"
    )
    with pytest.raises(RuntimeError, match=message):
        audit_service._llm_report_metadata(markdown, ["R01"])


def test_llm_report_metadata_reads_sequence_fid_column_without_matching_reason_references() -> None:
    import audit_service

    markdown = (
        "**总评：不通过**\n\n## 问题总表\n"
        "| 序号/FID | 规则号 | 复核结果 | 最终等级 | 理由/依据 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| 1. F-001-001 | R01 | 成立 | B | 与 F-009-009 对照后成立 |\n\n"
        "## 检查覆盖表\n| 规则号 | 模块 | 检查项 | 等级 | 结论 | 证据 |\n"
        "| --- | --- | --- | --- | --- | --- |\n| R01 | 模块 | 检查项 | A | 通过 | 证据 |\n\n"
        "### F-001-001 [B] 问题（R01）\n- **页码**：第1页\n"
    )

    verification, _ = audit_service._llm_report_metadata(markdown, ["R01"])

    assert verification["finding_ids"] == ["F-001-001"]


def test_coverage_row_cannot_override_final_disposition_grade() -> None:
    import audit_service

    markdown = (
        "**总评：不通过**\n\n## 问题总表\n"
        "| 序号/FID | 复核结果 | 最终等级 | 理由/依据 |\n| --- | --- | --- | --- |\n"
        "| F-001-001 | 成立 | B | 按复核结果计入 B |\n\n"
        "## 检查覆盖表\n| 规则号 | 模块 | 检查项 | 等级 | 结论 | 证据 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| R15 | 时间 | 校准日期 | A | 不通过 | F-001-001 |\n\n"
        "### F-001-001 [A] 校准记录问题（R15）\n- **页码**：第1页\n"
    )

    verification, summary = audit_service._llm_report_metadata(markdown, ["R15"])

    assert verification["findings"][0]["severity"] == "B"
    assert summary["grade_summary"] == {"A": 0, "B": 1, "C": 0}


def test_report_number_extraction() -> None:
    assert extract_report_no("报告编号：RPT-2026-0214") == "RPT-2026-0214"
    assert extract_report_no("Sample JC-2026-1234567A") == "JC-2026-1234567A"
    assert extract_report_no("no number here") == ""


def test_summary_from_verification_results(tmp_path: Path) -> None:
    rules = [
        batch_audit.Rule("R01", "页码连续完整", "B", ""),
        batch_audit.Rule("R05", "报告编号唯一性", "A", ""),
        batch_audit.Rule("R09", "评判要求完整性", "B", ""),
    ]
    verdicts = [
        batch_audit.Verdict("R01", "PASS", "B", page="1"),
        batch_audit.Verdict("R05", "FAIL", "A", page="1", problem="封面与页眉编号不一致"),
        batch_audit.Verdict("R09", "REVIEW", "B", page="5", problem="证据不足"),
    ]

    results = batch_audit.merge_results(rules, verdicts)
    summary = batch_audit.summarize(results)
    verification = batch_audit.build_verification(results)

    assert summary == {"findings_total": 2, "findings_review": 1, "grade_summary": {"A": 1}, "verdict": "不通过"}
    assert verification["counts"] == {"PASS": 1, "FAIL": 1, "REVIEW": 1, "NA": 0}
    assert verification["results"][1]["rule"] == "R05"


def test_merge_marks_missing_rule_as_review() -> None:
    rules = [batch_audit.Rule("R01", "页码连续完整", "B", "")]

    results = batch_audit.merge_results(rules, [])

    assert results[0].verdict == "REVIEW"
    assert batch_audit.summarize(results)["findings_review"] == 1


def test_document_results_reads_verification_json(tmp_path: Path) -> None:
    document = {
        "id": "doc-1",
        "user_id": "alice",
        "tenant_id": "default",
        "file_name": "RPT-2026-0214.pdf",
        "file_path": str(tmp_path / "documents" / "doc-1" / "original.pdf"),
        "extension": ".pdf",
        "size": 2048,
        "sha256": "a" * 64,
        "pages": 3,
        "report_no": "RPT-2026-0214",
        "status": "completed",
        "report_path": str(tmp_path / "documents" / "doc-1" / "report.html"),
    }
    from store import DocumentStore  # noqa: E402

    store = DocumentStore(tmp_path)
    store.create(document)
    doc_dir = tmp_path / "documents" / "doc-1"
    doc_dir.mkdir(parents=True, exist_ok=True)
    (doc_dir / "verification.json").write_text(json.dumps({
        "counts": {"PASS": 1, "FAIL": 1, "REVIEW": 1, "NA": 0},
        "results": [
            {"rule": "R01", "verdict": "PASS", "severity": "B"},
            {"rule": "R05", "verdict": "FAIL", "severity": "A", "problem": "编号不一致"},
            {"rule": "R19", "verdict": "REVIEW", "severity": "B", "problem": "图片无法核对"},
        ],
    }), encoding="utf-8")
    context = SimpleNamespace(
        user_id="alice",
        path_params={"document_id": "doc-1"},
        host=SimpleNamespace(data_dir=str(tmp_path)),
    )

    payload = asyncio.run(handlers.document_results(None, context))

    assert payload["verdict"] == "不通过"
    assert payload["counts"] == {"PASS": 1, "FAIL": 1, "REVIEW": 1, "NA": 0}
    assert payload["results"][1]["problem"] == "编号不一致"


@pytest.mark.asyncio
async def test_pdf_and_desensitized_downloads_have_separate_utf8_responses(tmp_path: Path) -> None:
    report = tmp_path / "documents" / "doc-1" / "runs" / "attempt" / "审核报告.pdf"
    desensitized = tmp_path / "documents" / "doc-1" / "prepared" / "脱敏报告.pdf"
    report.parent.mkdir(parents=True)
    desensitized.parent.mkdir(parents=True)
    report.write_bytes(b"%PDF report")
    (report.parent / "audit-report.html").write_text("<html>same audit</html>", encoding="utf-8")
    desensitized.write_bytes(b"%PDF prepared")
    store = DocumentStore(tmp_path)
    store.create({"id": "doc-1", "user_id": "alice", "file_name": "原件.pdf",
                  "file_path": str(tmp_path / "original.pdf"), "extension": ".pdf", "sha256": "",
                  "status": "running", "report_path": str(report), "report_name": "审核报告.pdf",
                  "desensitized_path": str(desensitized), "desensitized_name": "脱敏报告.pdf"})
    context = SimpleNamespace(user_id="alice", path_params={"document_id": "doc-1"},
                              provider_type="audit-report", provider_instance="tenant-a",
                              host=SimpleNamespace(data_dir=tmp_path))

    inline = await handlers.download_report(None, context)
    attachment = await handlers.download_report_file(None, context)
    preview = await handlers.download_report(SimpleNamespace(query_params={"preview": "html"}), context)
    prepared_inline = await handlers.download_desensitized(None, context)
    prepared_attachment = await handlers.download_desensitized_file(None, context)

    assert inline.media_type == "application/pdf"
    assert attachment.media_type == "application/pdf"
    assert preview.media_type == "text/html; charset=utf-8"
    assert preview.body == b"<html>same audit</html>"
    assert "filename*=utf-8''%E5%AE%A1%E6%A0%B8%E6%8A%A5%E5%91%8A.pdf" in attachment.headers["content-disposition"]
    assert prepared_inline.media_type == prepared_attachment.media_type == "application/pdf"
    assert "filename*=utf-8''%E8%84%B1%E6%95%8F%E6%8A%A5%E5%91%8A.pdf" in prepared_attachment.headers["content-disposition"]


@pytest.mark.asyncio
async def test_legacy_html_report_stays_html_and_missing_prepared_pdf_is_404(tmp_path: Path) -> None:
    report = tmp_path / "documents" / "doc-1" / "report.html"
    report.parent.mkdir(parents=True)
    report.write_text("<html>legacy</html>", encoding="utf-8")
    DocumentStore(tmp_path).create({"id": "doc-1", "user_id": "alice", "file_name": "x.pdf",
        "file_path": str(tmp_path / "original.pdf"), "extension": ".pdf", "sha256": "", "status": "completed",
        "report_path": str(report), "report_name": "report.html"})
    context = SimpleNamespace(user_id="alice", provider_type="audit-report", provider_instance="default",
                              path_params={"document_id": "doc-1"},
                              host=SimpleNamespace(data_dir=tmp_path))
    assert (await handlers.download_report(None, context)).media_type == "text/html; charset=utf-8"
    with pytest.raises(ProviderError) as exc:
        await handlers.download_desensitized(None, context)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_pdf_preview_is_404_when_missing_and_rejects_outside_provider_path(tmp_path: Path) -> None:
    report = tmp_path / "documents" / "doc-1" / "runs" / "attempt" / "audit-report.pdf"
    report.parent.mkdir(parents=True)
    report.write_bytes(b"%PDF")
    store = DocumentStore(tmp_path)
    store.create({"id": "doc-1", "user_id": "alice", "file_name": "x.pdf",
                  "file_path": str(tmp_path / "original.pdf"), "extension": ".pdf", "sha256": "",
                  "status": "completed", "report_path": str(report), "report_name": "audit-report.pdf"})
    context = SimpleNamespace(user_id="alice", path_params={"document_id": "doc-1"},
                              host=SimpleNamespace(data_dir=tmp_path))
    with pytest.raises(ProviderError) as exc:
        await handlers.download_report(SimpleNamespace(query_params={"preview": "html"}), context)
    assert exc.value.status_code == 404

    outside_report = tmp_path.parent / "outside-report.pdf"
    outside_report.write_bytes(b"%PDF")
    store.create({"id": "doc-outside", "user_id": "alice", "file_name": "outside.pdf",
                  "file_path": str(tmp_path / "original.pdf"), "extension": ".pdf", "sha256": "",
                  "status": "completed", "report_path": str(outside_report), "report_name": "outside.pdf"})
    context.path_params["document_id"] = "doc-outside"
    with pytest.raises(ProviderError) as exc:
        await handlers.download_report(SimpleNamespace(query_params={"preview": "html"}), context)
    assert exc.value.status_code == 403


@pytest.mark.parametrize("handler_name,query", [
    ("download_report", {}),
    ("download_report", {"preview": "html"}),
    ("download_report_file", {}),
    ("download_desensitized", {}),
    ("download_desensitized_file", {}),
])
@pytest.mark.asyncio
async def test_other_user_cannot_download_audit_artifacts(
    tmp_path: Path, handler_name: str, query: dict[str, str],
) -> None:
    report = tmp_path / "documents" / "alice-doc" / "runs" / "attempt" / "audit-report.pdf"
    preview = report.parent / "audit-report.html"
    desensitized = tmp_path / "documents" / "alice-doc" / "prepared" / "desensitized.pdf"
    report.parent.mkdir(parents=True)
    desensitized.parent.mkdir(parents=True)
    report.write_bytes(b"%PDF alice report")
    preview.write_text("<html>alice preview</html>", encoding="utf-8")
    desensitized.write_bytes(b"%PDF alice redacted")
    DocumentStore(tmp_path).create({
        "id": "alice-doc", "user_id": "alice", "file_name": "report.pdf",
        "file_path": str(tmp_path / "documents" / "alice-doc" / "original.pdf"),
        "extension": ".pdf", "sha256": "", "status": "completed",
        "report_path": str(report), "report_name": "audit-report.pdf",
        "desensitized_path": str(desensitized), "desensitized_name": "desensitized.pdf",
    })
    context = SimpleNamespace(user_id="bob", path_params={"document_id": "alice-doc"},
                              host=SimpleNamespace(data_dir=tmp_path))
    request = SimpleNamespace(query_params=query)

    with pytest.raises(ProviderError) as exc:
        await getattr(handlers, handler_name)(request, context)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_results_are_contained_and_pdf_without_llm_verdict_is_pending(tmp_path: Path) -> None:
    report = tmp_path / "documents" / "doc-pdf" / "runs" / "attempt" / "audit-report.pdf"
    report.parent.mkdir(parents=True)
    report.write_bytes(b"%PDF")
    verification = report.parent / "verification.json"
    verification.write_text(json.dumps({"counts": {}, "results": []}), encoding="utf-8")
    store = DocumentStore(tmp_path)
    store.create({"id": "doc-pdf", "user_id": "alice", "file_name": "x.pdf",
        "file_path": str(tmp_path / "source.pdf"), "extension": ".pdf", "sha256": "", "status": "completed",
        "report_path": str(report), "report_name": "audit-report.pdf"})
    context = SimpleNamespace(user_id="alice", path_params={"document_id": "doc-pdf"},
                              host=SimpleNamespace(data_dir=tmp_path))
    result = await handlers.document_results(None, context)
    assert result["completion_status"] == "needs_review"
    assert result["verdict"] == "待复核（模型未给出结论）"

    outside = tmp_path.parent / "outside.html"
    outside.write_text("legacy", encoding="utf-8")
    store.create({"id": "doc-outside", "user_id": "alice", "file_name": "x.pdf",
        "file_path": str(tmp_path / "source.pdf"), "extension": ".pdf", "sha256": "", "status": "completed",
        "report_path": str(outside), "report_name": "outside.html"})
    context.path_params["document_id"] = "doc-outside"
    with pytest.raises(ProviderError) as exc:
        await handlers.document_results(None, context)
    assert exc.value.code == "file_forbidden"


@pytest.mark.asyncio
async def test_document_results_refreshes_from_published_markdown_and_keeps_r20_evidence(tmp_path: Path) -> None:
    report = tmp_path / "documents" / "doc-r20" / "runs" / "attempt" / "audit-report.pdf"
    report.parent.mkdir(parents=True)
    report.write_bytes(b"%PDF")
    raw = (
        "# 审核报告\n\n**总评：通过**\n\n## 检查覆盖表\n"
        "| # | 模块 | 检查项 | 等级 | 结果 | 证据位置/说明 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| R20 | 设备信息 | 外来设备信息一致性 | B | 待复核 | 模型覆盖行缺失、重复或格式不完整 |\n"
    )
    published = (
        "# 审核报告\n\n**总评：通过**\n\n## 检查覆盖表\n"
        "| # | 模块 | 检查项 | 等级 | 结果 | 证据位置/说明 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| R20 | 设备信息 | 外来设备信息一致性 | B | 待复核 | 模型原始覆盖记录（保留原结论与依据）："
        "&#124; R20 &#124; 设备信息 &#124; 外来设备信息一致性 &#124; B &#124; 通过/待复核 &#124; "
        "S41 是否外来无法确认 &#124;。模型未给出可规范化的单一结论，相关规则列为待复核。 |\n"
    )
    (report.parent / "audit-raw.md").write_text(raw, encoding="utf-8")
    (report.parent / "audit.md").write_text(published, encoding="utf-8")
    (report.parent / "completion.json").write_text(json.dumps({
        "completion_status": "needs_review", "warnings": ["coverage_row_missing:R20"],
    }), encoding="utf-8")
    verification_path = report.parent / "verification.json"
    verification_path.write_text(json.dumps({
        "verdict": "通过", "results": [{"rule": "R20", "verdict": "PASS"}], "findings": [],
    }), encoding="utf-8")
    store = DocumentStore(tmp_path)
    store.create({
        "id": "doc-r20", "user_id": "alice", "file_name": "source.pdf",
        "file_path": str(tmp_path / "source.pdf"), "extension": ".pdf", "sha256": "",
        "status": "completed", "report_path": str(report), "report_name": report.name,
    })
    context = SimpleNamespace(
        user_id="alice", path_params={"document_id": "doc-r20"}, host=SimpleNamespace(data_dir=tmp_path),
    )

    first = await handlers.document_results(None, context)
    first_rule = next(item for item in first["results"] if item["rule"] == "R20")
    assert first_rule["verdict"] == "REVIEW"
    assert "通过/待复核" in first_rule["reason"]
    assert "S41 是否外来无法确认" in first_rule["reason"]
    assert "&#124;" not in first_rule["reason"]
    assert first["completion_status"] == "needs_review"

    second = await handlers.document_results(None, context)
    second_rule = next(item for item in second["results"] if item["rule"] == "R20")
    assert second_rule["verdict"] == "REVIEW"
    assert "通过/待复核" in second_rule["reason"]
    assert "S41 是否外来无法确认" in second_rule["reason"]
    assert second["completion_status"] == "needs_review"


def test_build_verification_includes_evidence_image() -> None:
    rules = [batch_audit.Rule("R02", "三方签章", "A", "")]
    verdicts = [batch_audit.Verdict("R02", "FAIL", "A", page="1", problem="签名空白")]
    results = batch_audit.merge_results(rules, verdicts)

    verification = batch_audit.build_verification(results, evidence={"R02": "evidence/F-01_R02.png"})

    assert verification["results"][0]["image"] == "evidence/F-01_R02.png"


def test_document_evidence_rejects_path_traversal(tmp_path: Path) -> None:
    from store import DocumentStore  # noqa: E402

    document = {
        "id": "doc-1",
        "user_id": "alice",
        "tenant_id": "default",
        "file_name": "report.pdf",
        "file_path": str(tmp_path / "documents" / "doc-1" / "original.pdf"),
        "extension": ".pdf",
        "size": 1024,
        "sha256": "a" * 64,
        "status": "completed",
    }
    DocumentStore(tmp_path).create(document)
    context = SimpleNamespace(
        user_id="alice",
        path_params={"document_id": "doc-1", "evidence_name": "../original.pdf"},
        host=SimpleNamespace(data_dir=str(tmp_path)),
    )

    with pytest.raises(ProviderError) as exc:
        asyncio.run(handlers.document_evidence(None, context))

    assert exc.value.code == "evidence_not_found"


def test_parse_answer_accepts_fenced_json() -> None:
    rules = [batch_audit.Rule("R01", "页码连续完整", "B", "")]
    answer = '```json\n{"results":[{"rule":"R01","verdict":"fail","page":2,"quote":"缺第 3 页"}]}\n```'

    verdicts = batch_audit.parse_answer(answer, rules)

    assert len(verdicts) == 1
    assert verdicts[0].verdict == "FAIL"
    assert verdicts[0].page == "2"


def test_parse_answer_locks_rule_severity() -> None:
    rules = [batch_audit.Rule("R05", "报告编号唯一性", "A", "")]
    answer = '{"results":[{"rule":"R05","verdict":"FAIL","severity":"C","page":1}]}'

    verdicts = batch_audit.parse_answer(answer, rules)

    assert verdicts[0].severity == "A"


def test_parse_answer_rejects_unknown_rules() -> None:
    rules = [batch_audit.Rule("R01", "页码连续完整", "B", "")]

    assert batch_audit.parse_answer('{"results":[{"rule":"R99","verdict":"PASS"}]}', rules) == []
    assert batch_audit.parse_answer("没有 JSON", rules) == []


def test_chunk_document_splits_on_pages_and_reports_overflow() -> None:
    text = "\n\n".join(f"## Page {page}\n\n" + ("内容" * 40) for page in range(1, 7))
    chunks, note = batch_audit.chunk_document(text)

    assert len(chunks) >= 1
    assert chunks[0].first_page == 1
    assert chunks[-1].last_page == 6
    assert note == ""


def test_load_rules_parses_official_rule_set() -> None:
    rules_path = ROOT / "skills" / "audit-report" / "references" / "audit-rules.md"
    rules = batch_audit.load_rules(rules_path)

    assert len(rules) == 46
    assert rules[0].rule_id == "R01"
    assert rules[0].severity == "C"
    assert rules[-1].rule_id == "R46"
    assert rules[-1].title == "多份文档交叉验证"


def test_load_rules_keeps_guidance_after_old_character_cutoff(tmp_path: Path) -> None:
    rules_path = tmp_path / "rules.md"
    sentinel = "GUIDANCE-TAIL-SENTINEL"
    rules_path.write_text(
        "## R01 页码连续完整（B · 主要）\n" + ("完整规则说明。" * 250) + sentinel,
        encoding="utf-8",
    )
    rules = batch_audit.load_rules(rules_path)
    assert sentinel in rules[0].guidance


def _make_skill_dir(tmp_path: Path) -> Path:
    skill = tmp_path / "audit-report"
    (skill / "references").mkdir(parents=True)
    shutil.copy(
        ROOT / "skills" / "audit-report" / "references" / "audit-rules.md",
        skill / "references" / "audit-rules.md",
    )
    shutil.copytree(ROOT / "skills" / "audit-report" / "rules" / "builtin", skill / "rules" / "builtin")
    return skill


def _write_pack(skill: Path, name: str, status: str, rules: list[dict]) -> None:
    pack_dir = skill / "rules" / "packs" / name
    pack_dir.mkdir(parents=True)
    (pack_dir / "pack.json").write_text(
        json.dumps(
            {"pack": name, "version": "1.2.3", "status": status, "rules": rules},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_load_rule_set_merges_active_packs_and_skips_drafts(tmp_path: Path) -> None:
    skill = _make_skill_dir(tmp_path)
    _write_pack(
        skill, "active-pack", "active",
        [{
            "id": "X01", "module": "客户要求", "title": "温度曲线", "severity": "A",
            "fail_when": "未附温度曲线原始记录", "evidence": ["附件"], "scope": "single",
        }],
    )
    _write_pack(
        skill, "draft-pack", "draft",
        [{
            "id": "X02", "module": "客户要求", "title": "草稿规则", "severity": "B",
            "fail_when": "不应加载", "evidence": ["附件"],
        }],
    )
    (skill / "rules" / "config.json").write_text(
        json.dumps({"builtin": "builtin/rules.json", "packs": ["packs/active-pack", "packs/draft-pack"]}),
        encoding="utf-8",
    )

    rules, packs = batch_audit.load_rule_set(skill)

    assert packs == ["builtin@2.0.0", "active-pack@1.2.3"]
    assert len(rules) == 47
    assert rules[-1].rule_id == "X01"
    assert rules[-1].severity == "A"
    assert rules[-1].module == "客户要求"
    assert rules[-1].pack == "active-pack"
    assert "未附温度曲线原始记录" in rules[-1].guidance
    assert "X02" not in {rule.rule_id for rule in rules}


def test_rule_set_includes_builtin_and_active_packs(tmp_path: Path) -> None:
    rules_dir = tmp_path / "rules"
    (rules_dir / "packs" / "customer-xy").mkdir(parents=True)
    skill_dir = tmp_path / "skill"
    (skill_dir / "rules").mkdir(parents=True)
    (skill_dir / "rules" / "config.json").write_text(
        '{"version": 1, "packs": [], "allow_overrides": false}', encoding="utf-8"
    )
    builtin = json.loads(
        (ROOT / "skills" / "audit-report" / "rules" / "builtin" / "rules.json").read_text(encoding="utf-8")
    )
    (rules_dir / "builtin").mkdir(parents=True)
    (rules_dir / "builtin" / "rules.json").write_text(json.dumps(builtin, ensure_ascii=False), encoding="utf-8")
    pack = {
        "pack": "customer-xy",
        "version": "1.2.0",
        "status": "active",
        "rules": [
            {
                "id": "X01",
                "module": "客户要求",
                "title": "温度曲线",
                "severity": "B",
                "fail_when": "未附试验箱温度曲线原始记录",
                "evidence": ["试验记录页"],
                "scope": "single",
                "check": {"type": "manual", "params": {}},
            }
        ],
    }
    pack_dir = rules_dir / "packs" / "customer-xy"
    (pack_dir / "pack.json").write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
    (rules_dir / "config.json").write_text(
        json.dumps({"version": 1, "packs": ["packs/customer-xy"]}), encoding="utf-8"
    )

    rules, packs = batch_audit.load_rule_set(skill_dir, rules_dir=rules_dir)

    ids = [rule.rule_id for rule in rules]
    assert "R01" in ids and "R19" in ids and "X01" in ids
    assert len(ids) == 47
    assert packs == ["builtin@2.0.0", "customer-xy@1.2.0"]
    extra = next(rule for rule in rules if rule.rule_id == "X01")
    assert "未附试验箱温度曲线原始记录" in extra.guidance
    assert extra.module == "客户要求"


def test_prompt_carries_all_rules_of_a_batch() -> None:
    rules = [
        batch_audit.Rule("R01", "页码连续完整", "B", "不通过条件：缺页"),
        batch_audit.Rule("X01", "温度曲线", "B", "不通过条件：未附曲线"),
    ]
    chunk = batch_audit.TextChunk(0, 1, 1, "## Page 1\n\n报告内容")

    prompt = batch_audit.build_prompt(rules, chunk, 1, "", 1, ["builtin@1.0.0", "customer-xy@1.2.0"])

    assert "R01" in prompt and "X01" in prompt
    assert "customer-xy@1.2.0" in prompt
    assert "未附曲线" in prompt
    assert "不设长度上限" in prompt
    assert "最多 120 字" not in prompt


def test_rule_batches_cover_every_rule_once() -> None:
    rules = [batch_audit.Rule(f"X{index:02d}", f"规则{index}", "B", "") for index in range(1, 21)]

    batches = batch_audit.rule_batches(rules)

    assert [len(batch) for batch in batches] == [7, 7, 6]
    flat = [rule.rule_id for batch in batches for rule in batch]
    assert flat == [rule.rule_id for rule in rules]


def test_markdown_report_contains_required_sections() -> None:
    rules = [batch_audit.Rule("R05", "报告编号唯一性", "A", "")]
    verdicts = [batch_audit.Verdict("R05", "FAIL", "A", page="1", quote="GDTSQ-1", problem="编号不一致", suggestion="统一编号")]
    results = batch_audit.merge_results(rules, verdicts)

    markdown = batch_audit.build_markdown(
        document={"file_name": "report.pdf", "extension": ".pdf", "size": 1024, "pages": 2},
        results=results,
        manifest={"page_count": 2, "has_text_layer": True, "pages": []},
        started_at=datetime.now().astimezone(),
        finished_at=datetime.now().astimezone(),
    )

    for heading in ("## 1. 审核对象", "## 2. 总评", "## 3. 问题清单", "## 5. 检查覆盖表（全部已启用规则）"):
        assert heading in markdown
    assert "**总评：不通过**" in markdown
    assert "### F-01 [A]" in markdown


def test_legacy_report_keeps_na_reason_fallback_when_evidence_list_is_empty():
    rule = batch_audit.Rule("R04", "同批编号", "B", "")
    markdown = batch_audit.build_markdown(
        document={"file_name": "report.pdf", "extension": ".pdf"},
        results=[batch_audit.RuleResult(rule=rule, verdict="NA", severity="B", evidence=[])],
        manifest={}, started_at=datetime.now().astimezone(), finished_at=datetime.now().astimezone(),
    )
    assert "本报告不涉及该检查项" in markdown


@pytest.mark.parametrize("decision_header", ["复核结果", "复核结果（成立/待复核/撤回）"])
def test_llm_final_review_dispositions_control_published_findings_not_historical_grades(decision_header: str) -> None:
    import audit_service
    markdown = (
        "# 报告\n**总评：不通过**\n\n## 问题总表\n"
        "| 问题编号 | 规则号 | 原等级 | 最终等级 | 复核结果 | 复核依据 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| F-001-001 | R14 | A | — | 撤回 | 未提供使用有效期不证明已超期 |\n"
        "| F-001-002 | R15 | A | — | 待复核 | 仅有截止日，不能核实完整期间 |\n"
        "| F-001-003 | R18 | C | C | 成立 | 原文将高温译作 Low temp |\n\n"
        "## 检查覆盖表\n"
        "| R14 | 时间逻辑 | 设备使用有效期 | A | 待复核 | 未提供期间 |\n"
        "| R15 | 时间逻辑 | 校准有效期 | A | 待复核 | 未提供起始日 |\n"
        "| R18 | 文字 | 英文 | C | 不通过 | 高温与 Low temp 冲突 |\n\n"
        "# 附录：分项目审核原文\n"
        "### F-001-001 [A] 未提供使用有效期（R14）\n- **页码**：第8页\n"
        "### F-001-002 [A] 未提供历史证书（R15）\n- **页码**：第8页\n"
        "### F-001-003 [C] 英文名称与原文不符（R18）\n- **页码**：第19页\n"
    )
    markdown = markdown.replace("| 复核结果 |", "| " + decision_header + " |")
    original = markdown
    verification, summary = audit_service._llm_report_metadata(markdown, ["R14", "R15", "R18"])
    assert verification["finding_ids"] == ["F-001-003"]
    assert summary["findings_total"] == 1
    assert summary["grade_summary"] == {"A": 0, "B": 0, "C": 1}
    assert [item["id"] for item in verification["withdrawn_findings"]] == ["F-001-001"]
    assert [item["id"] for item in verification["review_findings"]] == ["F-001-002"]
    assert verification["counts"]["REVIEW"] == 2
    assert markdown == original


def test_published_finding_uses_explicit_final_rule_title_and_page_after_llm_reclassification() -> None:
    import audit_service
    markdown = (
        "# 报告\n**总评：不通过**\n\n## 问题总表\n"
        "| 问题编号 | 最终规则号 | 最终等级 | 复核结果 | 页码 | 问题摘要 | 复核依据 |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| F-001-001 | 设备台账一致性 | B | 成立 | 第8页 | 报告与台账校准截止日字段不同 | 非R15日期越界，按用户台账要求核对 |\n\n"
        "## 检查覆盖表\n| R15 | 时间逻辑 | 校准期间 | A | 待复核 | 截止日前检测，起始日未知 |\n\n"
        "# 附录：分项目审核原文\n"
        "### F-001-001 [A] 校准有效期错误（R15）\n- **规则号**：R15\n- **页码**：第9页\n"
    )
    verification, summary = audit_service._llm_report_metadata(markdown, ["R15"])
    finding = verification["findings"][0]
    assert finding["rule"] == "设备台账一致性"
    assert finding["title"] == "报告与台账校准截止日字段不同"
    assert finding["page"] == "第8页"
    assert finding["severity"] == "B"
    assert summary["grade_summary"] == {"A": 0, "B": 1, "C": 0}


@pytest.mark.parametrize("duplicate_decision,duplicate_reason", [
    ("成立（与F-001-001重复，不另计）", "相同事实"),
    ("成立（重复）", "相同事实"),
    ("成立", "与F-001-001同一事实，本行不另计"),
])
def test_published_counts_follow_explicit_llm_duplicate_disposition(duplicate_decision: str, duplicate_reason: str) -> None:
    import audit_service
    markdown = (
        "# 报告\n**总评：不通过**\n\n## 问题总表\n"
        "| 问题编号 | 规则号 | 最终等级 | 复核结果 | 理由/依据 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| F-001-001 | 台账一致性 | B | 成立（含重复设备；另有新增差异） | 有独立字段差异；重复设备不另计 |\n"
        f"| F-002-001 | 台账一致性 | B | {duplicate_decision} | {duplicate_reason} |\n\n"
        "## 检查覆盖表\n| R15 | 时间 | 校准 | A | 待复核 | 未提供起始日 |\n\n"
        "# 附录：分项目审核原文\n"
        "### F-001-001 [A] 原始候选\n- **页码**：第8页\n"
        "### F-002-001 [A] 重复原始候选\n- **页码**：第20页\n"
    )
    verification, summary = audit_service._llm_report_metadata(markdown, ["R15"])
    assert verification["finding_ids"] == ["F-001-001"]
    assert summary["findings_total"] == 1
    assert summary["grade_summary"] == {"A": 0, "B": 1, "C": 0}
    assert verification["duplicate_findings"][0]["id"] == "F-002-001"
    assert verification["duplicate_findings"][0]["review_status"].startswith("成立")


@pytest.mark.asyncio
async def test_results_refresh_stale_index_from_saved_llm_report_without_reauditing(tmp_path: Path):
    report = tmp_path / "documents/doc/runs/attempt/audit-report.pdf"
    report.parent.mkdir(parents=True)
    report.write_bytes(b"%PDF unchanged service output")
    (report.parent / "audit-raw.md").write_text(
        "# 审核报告\n**总评：不通过**\n\n"
        "| FID | 复核结果 | 最终等级 | 理由/依据 |\n"
        "| F-001-001 | 成立 | B | 台账字段差异 |\n"
        "| F-002-001 | 成立 | B | 同一事实，本行不另计 |\n\n"
        "## 检查覆盖表\n| R15 | 时间 | 校准 | A | 待复核 | 缺起始日 |\n\n"
        "# 附录：分项目审核原文\n"
        "### F-001-001 [B] 台账字段差异\n- **页码**：第8页\n"
        "### F-002-001 [B] 同设备字段差异\n- **页码**：第20页\n", encoding="utf-8",
    )
    verification_path = report.parent / "verification.json"
    verification_path.write_text(json.dumps({"verdict": "不通过", "results": [{"rule": "R15", "verdict": "REVIEW"}],
                                            "findings": [{"id": "F-001-001"}, {"id": "F-002-001"}]}), encoding="utf-8")
    store = DocumentStore(tmp_path)
    store.create({"id": "doc", "user_id": "alice", "file_name": "x.pdf", "file_path": str(tmp_path / "source.pdf"),
                  "extension": ".pdf", "sha256": "", "status": "completed", "report_path": str(report),
                  "findings_total": 2, "grade_summary": {"B": 2}})
    context = SimpleNamespace(user_id="alice", path_params={"document_id": "doc"}, host=SimpleNamespace(data_dir=tmp_path))
    result = await handlers.document_results(None, context)
    assert [finding["id"] for finding in result["findings"]] == ["F-001-001"]
    assert store.get("doc", "alice")["findings_total"] == 1
    assert json.loads(verification_path.read_text(encoding="utf-8"))["duplicate_findings"][0]["id"] == "F-002-001"
    assert report.read_bytes() == b"%PDF unchanged service output"


@pytest.mark.asyncio
async def test_results_retry_repairs_db_summary_when_verification_json_is_already_refreshed(tmp_path: Path, monkeypatch):
    report = tmp_path / "documents/doc/runs/attempt/audit-report.pdf"
    report.parent.mkdir(parents=True)
    report.write_bytes(b"unchanged")
    (report.parent / "audit-raw.md").write_text(
        "**总评：不通过**\n\n## 检查覆盖表\n| R15 | 时间 | 校准 | A | 通过 | 证据 |\n\n"
        "### F-001-001 [B] 问题（R15）\n- **页码**：第8页\n", encoding="utf-8",
    )
    verification_path = report.parent / "verification.json"
    verification_path.write_text(json.dumps({"verdict": "不通过", "results": [{"rule": "R15", "verdict": "PASS"}],
                                            "findings": []}), encoding="utf-8")
    store = DocumentStore(tmp_path)
    store.create({"id": "doc", "user_id": "alice", "file_name": "x.pdf", "file_path": str(tmp_path / "source.pdf"),
                  "extension": ".pdf", "sha256": "", "status": "completed", "report_path": str(report),
                  "findings_total": 0, "grade_summary": {}})
    context = SimpleNamespace(user_id="alice", path_params={"document_id": "doc"}, host=SimpleNamespace(data_dir=tmp_path))
    original_update = DocumentStore.update
    failed = False

    def fail_once(*args, **kwargs):
        nonlocal failed
        if not failed:
            failed = True
            raise OSError("temporary database busy")
        return original_update(*args, **kwargs)

    monkeypatch.setattr(DocumentStore, "update", fail_once)
    with pytest.raises(OSError, match="database busy"):
        await handlers.document_results(None, context)
    assert json.loads(verification_path.read_text(encoding="utf-8"))["findings"][0]["id"] == "F-001-001"

    await handlers.document_results(None, context)

    assert store.get("doc", "alice")["findings_total"] == 1
    assert store.get("doc", "alice")["grade_summary"] == {"B": 1, "A": 0, "C": 0}
