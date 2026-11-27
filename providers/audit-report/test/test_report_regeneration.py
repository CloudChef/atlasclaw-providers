from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(ROOT / "skills" / "audit-report" / "scripts"))

import audit_delivery  # noqa: E402
import audit_service  # noqa: E402
import handlers  # noqa: E402
from errors import ProviderError  # noqa: E402
from store import DocumentStore  # noqa: E402


def _context(reports: Path, user_id: str = "alice") -> SimpleNamespace:
    host = SimpleNamespace(
        data_dir=reports / "legacy" / user_id,
        config={"reports_dir": str(reports)},
        user=SimpleNamespace(user_id=user_id, tenant_id="tenant-a"),
    )
    return SimpleNamespace(
        host=host, user_id=user_id, provider_type="audit-report", provider_instance="default",
        path_params={"document_id": "doc-1"},
        run_text=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("regeneration called text model")),
        run_visual=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("regeneration called visual model")),
    )


@pytest.mark.asyncio
async def test_regenerate_report_uses_saved_outputs_and_preserves_old_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    reports = tmp_path / "reports"
    context = _context(reports)
    user_root = reports / "tenant-a" / "alice"
    doc_root = user_root / "documents" / "doc-1"
    old_attempt = doc_root / "runs" / "original-attempt"
    old_attempt.mkdir(parents=True)
    source_pdf = user_root / "documents" / "doc-1" / "prepared.pdf"
    source_pdf.write_bytes(b"%PDF-prepared")
    old_pdf = old_attempt / "audit-report.pdf"
    old_pdf.write_bytes(b"%PDF-old")
    (old_attempt / "workflow.json").write_text('{"saved":true}', encoding="utf-8")
    (old_attempt / "completion.json").write_text(json.dumps({
        "completion_status": "needs_review",
        "warnings": ["required_visual_stage_failed", "reference_material_unavailable:ledger.xlsx"],
    }), encoding="utf-8")
    (old_attempt / "visual" / "001-raw.md").parent.mkdir(parents=True)
    (old_attempt / "visual" / "001-raw.md").write_text("saved visual observation", encoding="utf-8")
    report = (
        "# 审核报告\n\n## 1. 审核对象\n\n"
        "| 项目 | 内容 |\n| --- | --- |\n"
        "| 文件名 | `model-name.pdf` |\n| 文件大小 | 未提供 |\n| SHA-256 | 未提供 |\n\n"
        "**总评：通过**\n\n## 检查覆盖表\n"
        "| # | 模块 | 检查项 | 等级 | 结果 | 证据位置/说明 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| R20 | 设备信息 | 外来设备信息一致性 | B | 待复核 | 模型覆盖行缺失、重复或格式不完整 |\n"
    )
    (old_attempt / "audit-raw.md").write_text(report, encoding="utf-8")
    summary = report.replace(
        "| R20 | 设备信息 | 外来设备信息一致性 | B | 待复核 | 模型覆盖行缺失、重复或格式不完整 |",
        "| R20 | 设备信息 | 外来设备信息一致性 | B | 通过/待复核 | S41 是否外来无法确认 |",
    )
    (old_attempt / "audit-main-raw.md").write_text(summary, encoding="utf-8")

    store = DocumentStore(user_root)
    store.create({
        "id": "doc-1", "user_id": "alice", "tenant_id": "tenant-a",
        "file_name": "known-source-name.pdf", "file_path": str(source_pdf),
        "extension": ".pdf", "size": 123456, "sha256": "a" * 64,
        "status": "completed", "report_path": str(old_pdf), "report_name": old_pdf.name,
        "desensitized_path": str(source_pdf),
    })

    monkeypatch.setitem(sys.modules, "_rules", SimpleNamespace(
        load_rules=lambda _root=None: SimpleNamespace(
            ids=["R20"], rules={"R20": {"module": "设备信息", "name": "外来设备信息一致性", "severity": "B"}},
        ),
    ))

    def local_delivery(markdown_path: Path, _source: Path, output_pdf: Path) -> dict:
        assert "known-source-name.pdf" in markdown_path.read_text(encoding="utf-8")
        output_pdf.write_bytes(b"%PDF-regenerated")
        output_pdf.with_suffix(".html").write_text("<html>report</html>", encoding="utf-8")
        return {"report_pdf": str(output_pdf), "errors": [], "evidence_errors": [], "findings": []}

    monkeypatch.setattr(audit_delivery, "deliver_report", local_delivery)
    request = SimpleNamespace()
    result = await handlers.regenerate_report(request, context)
    key = (store.db_path.resolve(), "doc-1")
    active = audit_service._TASKS.get(key)
    if active is not None:
        await asyncio.wait_for(active[1], timeout=5)

    updated = store.get("doc-1", "alice")
    new_report = Path(updated["report_path"])
    assert result["id"] == "doc-1"
    assert updated["status"] == "completed"
    assert new_report != old_pdf and new_report.is_file()
    assert old_pdf.is_file() and (old_attempt / "workflow.json").is_file()
    assert (new_report.parent / "visual" / "001-raw.md").read_text(encoding="utf-8") == "saved visual observation"

    regenerated = (new_report.parent / "audit.md").read_text(encoding="utf-8")
    assert "| R20 | 设备信息 | 外来设备信息一致性 | B | 待复核 | 模型原始覆盖记录" in regenerated
    assert "known-source-name.pdf" in regenerated
    assert "123,456 bytes" in regenerated
    assert f"`{'a' * 64}`" in regenerated
    assert "通过/待复核" in regenerated
    assert "S41 是否外来无法确认" in regenerated
    completion = json.loads((new_report.parent / "completion.json").read_text(encoding="utf-8"))
    assert completion["completion_status"] == "needs_review"
    assert "coverage_row_missing:R20" in completion["warnings"]
    assert "required_visual_stage_failed" in completion["warnings"]
    assert "reference_material_unavailable:ledger.xlsx" in completion["warnings"]
    verification = json.loads((new_report.parent / "verification.json").read_text(encoding="utf-8"))
    assert verification["completion_status"] == "needs_review"
    assert next(item for item in verification["results"] if item["rule"] == "R20")["verdict"] == "REVIEW"


@pytest.mark.asyncio
async def test_regenerate_report_requires_owner_and_rejects_competing_job(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    alice_context = _context(reports)
    alice_root = reports / "tenant-a" / "alice"
    store = DocumentStore(alice_root)
    original = alice_root / "documents" / "doc-1" / "runs" / "attempt" / "audit-report.pdf"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"%PDF")
    raw = (
        "# 审核报告\n**总评：通过**\n\n## 检查覆盖表\n"
        "| # | 模块 | 检查项 | 等级 | 结果 | 证据位置/说明 |\n"
        "| --- | --- | --- | --- | --- | --- |\n| R20 | 设备信息 | R20 | B | 待复核 | 待复核 |\n"
    )
    (original.parent / "audit-raw.md").write_text(raw, encoding="utf-8")
    (original.parent / "audit-main-raw.md").write_text(raw, encoding="utf-8")
    prepared = alice_root / "documents" / "doc-1" / "prepared.pdf"
    prepared.parent.mkdir(parents=True, exist_ok=True)
    prepared.write_bytes(b"%PDF")
    store.create({
        "id": "doc-1", "user_id": "alice", "file_name": "source.pdf", "file_path": str(prepared),
        "extension": ".pdf", "size": 4, "sha256": "hash", "status": "completed",
        "report_path": str(original), "desensitized_path": str(prepared),
    })

    bob_context = _context(reports, "bob")
    with pytest.raises(ProviderError) as not_owner:
        await handlers.regenerate_report(SimpleNamespace(), bob_context)
    assert not_owner.value.status_code == 404

    key = (store.db_path.resolve(), "doc-1")
    sentinel = asyncio.create_task(asyncio.sleep(5))
    audit_service._TASKS[key] = ("doc-1", sentinel)
    try:
        with pytest.raises(ProviderError) as conflict:
            await handlers.regenerate_report(SimpleNamespace(), alice_context)
        assert conflict.value.status_code == 409
        assert conflict.value.code == "audit_already_running"
    finally:
        audit_service._TASKS.pop(key, None)
        sentinel.cancel()
        with pytest.raises(asyncio.CancelledError):
            await sentinel


def test_report_regeneration_route_is_owner_scoped_and_uses_audit_capability() -> None:
    routes = json.loads((ROOT / "runtime-api.json").read_text(encoding="utf-8"))["routes"]
    route = next(item for item in routes if item["id"] == "documents.report_regenerate")
    assert route["method"] == "POST"
    assert route["path"] == "documents/{document_id}/report/regenerate"
    assert route["handler"] == "regenerate_report"
    assert route["capability"] == "audit" and route["access"] == "user"
