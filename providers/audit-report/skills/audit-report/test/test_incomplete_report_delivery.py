from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import run_document_audit  # noqa: E402


def test_publishable_report_marks_missing_conclusions_without_inventing_passes() -> None:
    partial = (
        "# 审核报告\n\n## 2. 总评\n\n"
        "## 5. 检查覆盖表\n\n"
        "| # | 模块 | 检查项 | 等级 | 结果 | 证据位置/说明 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| R01 | 页码 | 页码连续完整 | C | 通过 | 第 1 页 |\n"
    )

    normalized = run_document_audit.normalize_publishable_report(partial, ["R01", "R02"])

    assert "总评：待复核（模型未给出结论）" in normalized
    assert "| R01 | 页码 | 页码连续完整 | C | 通过 | 第 1 页 |" in normalized
    assert "| R02 |" in normalized
    assert "| 待复核 | 模型未提供此规则结论 |" in normalized
    assert "报告未完成" in normalized
    assert "通过 | 模型未提供" not in normalized
    assert run_document_audit.validate_markdown(normalized, ["R01", "R02"])
    from render_report import markdown_to_html
    rendered = markdown_to_html(normalized, str(Path.cwd()))
    assert "<table" in rendered
    assert ">待复核</td>" in rendered


def test_publishable_report_keeps_complete_legacy_conclusion_header_unchanged() -> None:
    report = (
        "# 审核报告\n**总评：需补充材料**\n\n## 检查覆盖表\n"
        "| 规则号 | 模块 | 检查项 | 等级 | 结论 | 证据位置/说明 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| R07 | 标准 | 年代号 | B | 通过（仅年代号形式） | 第 2 页 |\n"
    )

    normalized = run_document_audit.normalize_publishable_report(report, ["R07"])

    assert "| 结论 |" in normalized
    assert "| R07 | 标准 | 年代号 | B | 通过（仅年代号形式） | 第 2 页 |" in normalized
    assert "报告未完成" not in normalized
    assert run_document_audit._report_completeness_warnings(normalized, ["R07"]) == []


def test_missing_candidate_disposition_is_a_completeness_warning() -> None:
    markdown = (
        "# 审核报告\n**总评：通过**\n\n## 检查覆盖表\n"
        "| # | 模块 | 检查项 | 等级 | 结果 | 证据位置/说明 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| R01 | 页码 | 页码连续完整 | C | 通过 | 第 1 页 |\n\n"
        "> 报告未完成：模型未提供部分候选处置结论；相关项已标为待复核。待复核不代表通过。\n"
    )

    warnings = run_document_audit._report_completeness_warnings(markdown, ["R01"])

    assert "candidate_disposition_missing" in warnings


def test_placeholder_overall_is_replaced_with_pending_status() -> None:
    report = "# 审核报告\n**总评：<通过 / 不通过>**\n\n## 检查覆盖表\n"

    normalized = run_document_audit.normalize_publishable_report(report, [])

    assert normalized.count("**总评：") == 1
    assert "**总评：待复核（模型未给出结论）**" in normalized
    assert "<通过 / 不通过>" not in normalized


@pytest.mark.asyncio
async def test_audit_prepared_publishes_partial_report_after_model_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import audit_delivery
    import audit_workflow

    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"source")
    monkeypatch.setattr(run_document_audit, "report_text", lambda _path: ("report text", 1))
    async def failed_after_partial(*_args, **kwargs) -> str:
        output_dir = kwargs["output_dir"] if "output_dir" in kwargs else _args[4]
        (output_dir / "project-raw.md").write_text("partial model evidence", encoding="utf-8")
        raise RuntimeError("private upstream detail")

    monkeypatch.setattr(audit_workflow, "execute_audit", failed_after_partial)
    monkeypatch.setitem(
        sys.modules, "_rules",
        SimpleNamespace(load_rules=lambda _root=None: SimpleNamespace(ids=["R01"], severity={"R01": "C"}, rules={})),
    )

    deliveries: list[str] = []

    def deliver(markdown_path: Path, _source_pdf: Path, output_pdf: Path) -> dict:
        markdown = markdown_path.read_text(encoding="utf-8")
        deliveries.append(markdown)
        output_pdf.write_bytes(b"%PDF incomplete shell")
        return {"report_pdf": str(output_pdf), "errors": [], "evidence_errors": [], "findings": []}

    monkeypatch.setattr(audit_delivery, "deliver_report", deliver)

    result = await run_document_audit.audit_prepared(
        pdf_path, [], tmp_path / "out", lambda _prompt: asyncio.sleep(0, result="unused"),
        rules_dir=tmp_path / "rules",
    )

    assert Path(result["report_pdf"]).is_file()
    assert (tmp_path / "out" / "project-raw.md").is_file()
    assert (tmp_path / "out" / "audit-incomplete.md").is_file()
    report = (tmp_path / "out" / "audit.md").read_text(encoding="utf-8")
    assert "待复核" in report
    assert "报告未完成" in report
    assert "RuntimeError" in report
    assert "private upstream detail" not in report
    assert "project-raw.md" in report
    assert "partial model evidence" in report
    assert "| R01 |" in report
    assert deliveries


@pytest.mark.asyncio
async def test_delivery_evidence_errors_do_not_block_incomplete_pdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import audit_delivery
    import audit_workflow
    from PIL import Image

    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"source")
    monkeypatch.setattr(run_document_audit, "report_text", lambda _path: ("report text", 1))
    async def partial_report(*_args, **_kwargs) -> str:
        return "# 审核报告\n"

    monkeypatch.setattr(audit_workflow, "execute_audit", partial_report)
    monkeypatch.setitem(
        sys.modules, "_rules",
        SimpleNamespace(load_rules=lambda _root=None: SimpleNamespace(ids=["R01"], severity={"R01": "C"}, rules={})),
    )
    calls: list[str] = []
    evidence_dir = tmp_path / "out" / "evidence"
    evidence_dir.mkdir(parents=True)
    good_image = evidence_dir / "F-001-001.png"
    Image.new("RGB", (12, 12), (255, 0, 0)).save(good_image)
    good_reference = evidence_dir / "F-001-001-p1.png"
    Image.new("RGB", (12, 12), (0, 255, 0)).save(good_reference)
    enriched = tmp_path / "out" / "audit-report.enriched.md"
    enriched.write_text(
        "# 审核报告\n\n### F-001-001 [A] Captured finding\n\n"
        "![evidence](evidence/F-001-001.png)\n\n### F-001-002 [B] Missing capture\n",
        encoding="utf-8",
    )

    def deliver(markdown_path: Path, _source_pdf: Path, output_pdf: Path) -> dict:
        calls.append(markdown_path.read_text(encoding="utf-8"))
        output_pdf.write_bytes(b"%PDF incomplete shell")
        return {
            "report_pdf": str(output_pdf),
            "enriched_markdown": enriched.name,
            "errors": ["F-001: raw screenshot error"],
            "evidence_errors": ["raw screenshot error"],
            "findings": [
                {"id": "F-001-001", "status": "captured", "image": str(good_image),
                 "images": [{"image": str(good_reference), "reference": str(good_reference)}]},
                {"id": "F-001-002", "status": "error", "error": "raw screenshot error"},
            ],
        }

    monkeypatch.setattr(audit_delivery, "deliver_report", deliver)

    result = await run_document_audit.audit_prepared(
        pdf_path, [], tmp_path / "out", lambda _prompt: asyncio.sleep(0, result="unused"),
        rules_dir=tmp_path / "rules",
    )

    assert Path(result["report_pdf"]).is_file()
    assert len(calls) == 1
    assert "raw screenshot error" not in calls[-1]
    import pymupdf
    with pymupdf.open(result["report_pdf"]) as report_pdf:
        assert report_pdf.page_count > 0
        assert "证据截图未完整生成" in "\n".join(page.get_text() for page in report_pdf)
        assert sum(len(page.get_images(full=True)) for page in report_pdf) >= 1


@pytest.mark.asyncio
async def test_unreadable_reference_keeps_model_verdict_but_marks_pdf_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import audit_delivery
    import audit_materials
    import audit_workflow

    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"source")
    bad_material = tmp_path / "shared-ledger.xlsx"
    bad_material.write_bytes(b"unreadable")
    monkeypatch.setattr(run_document_audit, "report_text", lambda _path: ("report text", 1))

    async def completed_model_report(*_args, **_kwargs) -> str:
        return (
            "# 审核报告\n\n**总评：通过**\n\n## 检查覆盖表\n"
            "| # | 模块 | 检查项 | 等级 | 结果 | 证据位置/说明 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| R01 | 页码 | 页码连续完整 | C | 通过 | 第 1 页 |\n"
        )

    monkeypatch.setattr(audit_workflow, "execute_audit", completed_model_report)
    monkeypatch.setattr(audit_materials, "read_material", lambda _path: (_ for _ in ()).throw(ValueError("private detail")))
    monkeypatch.setitem(sys.modules, "_rules", SimpleNamespace(load_rules=lambda _root=None: SimpleNamespace(
        ids=["R01"], severity={"R01": "C"}, rules={},
    )))

    def deliver(_markdown_path: Path, _source_pdf: Path, output_pdf: Path) -> dict:
        output_pdf.write_bytes(b"%PDF")
        return {"report_pdf": str(output_pdf), "errors": [], "evidence_errors": [], "findings": []}

    monkeypatch.setattr(audit_delivery, "deliver_report", deliver)

    result = await run_document_audit.audit_prepared(
        pdf_path, [bad_material], tmp_path / "out", lambda _prompt: asyncio.sleep(0, result="unused"),
        rules_dir=tmp_path / "rules",
    )

    report = (tmp_path / "out" / "audit.md").read_text(encoding="utf-8")
    assert result["completion_status"] == "needs_review"
    assert "**总评：通过**" in report
    assert "## 流程状态" in report
    assert "shared-ledger.xlsx 未能读取" in report
