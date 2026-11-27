# -*- coding: utf-8 -*-
"""Incomplete LLM reports remain available for human review without inferred passes."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(ROOT / "skills" / "audit-report" / "scripts"))

import audit_service  # noqa: E402
import handlers  # noqa: E402
from store import DocumentStore  # noqa: E402


def test_incomplete_metadata_marks_absent_overall_and_coverage_for_review() -> None:
    markdown = "# 报告\n\n模型未能给出结论。\n"
    with pytest.raises(RuntimeError, match="missing its explicit overall verdict"):
        audit_service._llm_report_metadata(markdown, ["R01", "R02"])

    verification, summary = audit_service._llm_report_metadata(
        markdown, ["R01", "R02"], allow_incomplete=True,
    )

    assert verification["verdict"] == "待复核（模型未给出结论）"
    assert verification["results"] == [
        {"rule": "R01", "name": "", "severity": "", "verdict": "REVIEW", "reason": "模型未提供此规则结论"},
        {"rule": "R02", "name": "", "severity": "", "verdict": "REVIEW", "reason": "模型未提供此规则结论"},
    ]
    assert verification["counts"] == {"PASS": 0, "FAIL": 0, "REVIEW": 2, "NA": 0}
    assert verification["warnings"] == ["overall_verdict_missing", "coverage_table_missing"]
    assert verification["completion_status"] == "needs_review"
    assert verification["completeness"] == {
        "overall_verdict": False,
        "coverage_table": False,
        "required_rules": 2,
        "reported_rules": 0,
        "missing_rules": ["R01", "R02"],
    }
    assert summary["findings_review"] == 2


def test_overall_verdict_placeholder_is_missing_metadata() -> None:
    markdown = (
        "# 报告\n**总评：<通过/不通过/待复核>**\n\n## 检查覆盖表\n"
        "| R01 | 一致性 | 编号相同 | B | 通过 | 编号一致 |\n"
    )

    with pytest.raises(RuntimeError, match="missing its explicit overall verdict"):
        audit_service._llm_report_metadata(markdown, ["R01"])

    verification, _summary = audit_service._llm_report_metadata(
        markdown, ["R01"], allow_incomplete=True,
    )

    assert verification["verdict"] == "待复核（模型未给出结论）"
    assert verification["warnings"] == ["overall_verdict_missing"]
    assert verification["completion_status"] == "needs_review"


def test_incomplete_metadata_preserves_written_verdict_and_marks_malformed_rule_review() -> None:
    markdown = (
        "# 报告\n**总评：待复核，需补充台账**\n\n## 检查覆盖表\n"
        "| 规则号 | 模块 | 检查项 | 等级 | 结论 | 证据 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| R01 | 文件完整性 | 编号一致 | B | 不通过 | 编号冲突 |\n"
        "| R02 | 文件完整性 | 签字完整 | B | 无法判断 | 模型未说明 |\n\n"
        "# 附录：分项目审核原文\n"
        "### F-001-001 [B] 编号冲突（R01）\n- **页码**：第 2 页\n"
    )

    verification, summary = audit_service._llm_report_metadata(
        markdown, ["R01", "R02", "R03"], allow_incomplete=True,
    )

    assert verification["verdict"] == "待复核，需补充台账"
    assert [row["verdict"] for row in verification["results"]] == ["FAIL", "REVIEW", "REVIEW"]
    assert verification["results"][1]["reason"] == "模型未提供此规则结论"
    assert verification["results"][2]["reason"] == "模型未提供此规则结论"
    assert verification["counts"] == {"PASS": 0, "FAIL": 1, "REVIEW": 2, "NA": 0}
    assert verification["warnings"] == ["coverage_rows_missing:R02,R03"]
    assert verification["completion_status"] == "needs_review"
    assert verification["completeness"]["overall_verdict"] is True
    assert verification["completeness"]["missing_rules"] == ["R02", "R03"]
    assert verification["findings"][0]["id"] == "F-001-001"
    assert summary["findings_review"] == 2


def test_incomplete_metadata_does_not_choose_between_duplicate_coverage_rows() -> None:
    markdown = (
        "# 报告\n**总评：通过**\n\n## 检查覆盖表\n"
        "| R01 | 一致性 | 编号相同 | B | 通过 | 一致 |\n"
        "| R01 | 一致性 | 编号相同 | B | 结论无法识别 | 不确定 |\n"
    )

    verification, _summary = audit_service._llm_report_metadata(
        markdown, ["R01"], allow_incomplete=True,
    )

    assert verification["results"] == [
        {"rule": "R01", "name": "", "severity": "", "verdict": "REVIEW", "reason": "模型未提供此规则结论"},
    ]
    assert verification["counts"] == {"PASS": 0, "FAIL": 0, "REVIEW": 1, "NA": 0}
    assert verification["warnings"] == ["coverage_rows_duplicated:R01", "coverage_rows_missing:R01"]


def test_incomplete_metadata_keeps_explicit_findings_when_final_disposition_is_partial() -> None:
    markdown = (
        "# 报告\n**总评：不通过**\n\n## 检查覆盖表\n"
        "| R01 | 一致性 | 编号相同 | B | 不通过 | 编号不一致 |\n\n"
        "## 问题总表\n"
        "| 问题编号 | 复核结果 | 最终等级 | 复核依据 |\n| --- | --- | --- | --- |\n"
        "| F-001-001 | 成立 | B | 有原文支持 |\n\n"
        "# 附录：分项目审核原文\n"
        "### F-001-001 [B] 编号问题（R01）\n- **页码**：第 2 页\n"
        "### F-001-002 [A] 另一问题（R01）\n- **页码**：第 3 页\n"
    )

    verification, summary = audit_service._llm_report_metadata(
        markdown, ["R01"], allow_incomplete=True,
    )

    assert verification["verdict"] == "不通过"
    assert verification["results"][0]["verdict"] == "FAIL"
    assert [finding["id"] for finding in verification["findings"]] == ["F-001-001"]
    assert [finding["id"] for finding in verification["review_findings"]] == ["F-001-002"]
    assert verification["review_findings"][0]["review_reason"] == "模型未提供最终复核结论"
    assert verification["warnings"] == ["missing_final_dispositions:F-001-002"]
    assert summary["findings_total"] == 1


@pytest.mark.asyncio
async def test_document_results_refreshes_legacy_pdf_with_missing_verdict_as_review(tmp_path: Path) -> None:
    report = tmp_path / "documents" / "doc-1" / "runs" / "attempt" / "audit-report.pdf"
    report.parent.mkdir(parents=True)
    report.write_bytes(b"%PDF-legacy")
    (report.parent / "audit-raw.md").write_text("# 审核报告\n\n未形成有效结论。\n", encoding="utf-8")
    verification_path = report.parent / "verification.json"
    verification_path.write_text(json.dumps({
        "results": [{"rule": "R01", "verdict": "PASS"}],
        "findings": [],
    }), encoding="utf-8")

    store = DocumentStore(tmp_path)
    store.create({
        "id": "doc-1", "user_id": "alice", "file_name": "report.pdf",
        "file_path": str(tmp_path / "source.pdf"), "extension": ".pdf", "sha256": "",
        "status": "completed", "report_path": str(report),
    })
    context = SimpleNamespace(
        user_id="alice", path_params={"document_id": "doc-1"},
        host=SimpleNamespace(data_dir=tmp_path),
    )

    result = await handlers.document_results(None, context)

    assert result["verdict"] == "待复核（模型未给出结论）"
    assert result["counts"] == {"PASS": 0, "FAIL": 0, "REVIEW": 1, "NA": 0}
    assert result["results"][0]["verdict"] == "REVIEW"
    assert result["results"][0]["reason"] == "模型未提供此规则结论"
    assert "overall_verdict_missing" in result["warnings"]
    assert result["completion_status"] == "needs_review"
    assert json.loads(verification_path.read_text(encoding="utf-8"))["verdict"] == "待复核（模型未给出结论）"


@pytest.mark.asyncio
async def test_document_results_does_not_infer_overall_pass_without_saved_markdown(tmp_path: Path) -> None:
    report = tmp_path / "documents" / "doc-1" / "runs" / "attempt" / "audit-report.pdf"
    report.parent.mkdir(parents=True)
    report.write_bytes(b"%PDF-legacy")
    verification_path = report.parent / "verification.json"
    verification_path.write_text(json.dumps({
        "counts": {"PASS": 1, "FAIL": 0, "REVIEW": 0, "NA": 0},
        "results": [{"rule": "R01", "verdict": "PASS"}],
        "findings": [],
    }), encoding="utf-8")

    store = DocumentStore(tmp_path)
    store.create({
        "id": "doc-1", "user_id": "alice", "file_name": "report.pdf",
        "file_path": str(tmp_path / "source.pdf"), "extension": ".pdf", "sha256": "",
        "status": "completed", "report_path": str(report),
    })
    context = SimpleNamespace(
        user_id="alice", path_params={"document_id": "doc-1"},
        host=SimpleNamespace(data_dir=tmp_path),
    )

    result = await handlers.document_results(None, context)

    assert result["verdict"] == "待复核（模型未给出结论）"
    assert result["results"][0]["verdict"] == "PASS"
    assert result["completion_status"] == "needs_review"
    assert "overall_verdict_missing" in result["warnings"]
    assert "coverage_metadata_unavailable" in result["warnings"]


@pytest.mark.asyncio
async def test_document_results_preserves_pipeline_incompleteness_across_metadata_refreshes(tmp_path: Path) -> None:
    report = tmp_path / "documents" / "doc-1" / "runs" / "attempt" / "audit-report.pdf"
    report.parent.mkdir(parents=True)
    report.write_bytes(b"%PDF")
    (report.parent / "audit-raw.md").write_text(
        "# 审核报告\n**总评：通过**\n\n## 检查覆盖表\n"
        "| R01 | 一致性 | 编号相同 | B | 通过 | 编号一致 |\n",
        encoding="utf-8",
    )
    completion_path = report.parent / "completion.json"
    completion_path.write_text(json.dumps({
        "completion_status": "needs_review",
        "warnings": ["required_visual_stage_failed"],
    }), encoding="utf-8")
    verification_path = report.parent / "verification.json"
    verification_path.write_text(json.dumps({
        "verdict": "通过",
        "counts": {"PASS": 1, "FAIL": 0, "REVIEW": 0, "NA": 0},
        "results": [{"rule": "R01", "verdict": "PASS", "severity": "B", "reason": "编号一致"}],
        "findings": [],
        "finding_ids": [],
    }), encoding="utf-8")

    store = DocumentStore(tmp_path)
    store.create({
        "id": "doc-1", "user_id": "alice", "file_name": "report.pdf",
        "file_path": str(tmp_path / "source.pdf"), "extension": ".pdf", "sha256": "",
        "status": "completed", "report_path": str(report),
    })
    context = SimpleNamespace(
        user_id="alice", path_params={"document_id": "doc-1"},
        host=SimpleNamespace(data_dir=tmp_path),
    )

    first = await handlers.document_results(None, context)
    second = await handlers.document_results(None, context)
    saved = json.loads(verification_path.read_text(encoding="utf-8"))

    for result in (first, second):
        assert result["completion_status"] == "needs_review"
        assert result["verdict"] == "通过"
        assert result["completeness"]["pipeline_status"] == "needs_review"
        assert result["completeness"]["pipeline_warnings"] == ["required_visual_stage_failed"]
        assert "required_visual_stage_failed" in result["warnings"]
    assert saved["completion_status"] == "needs_review"
    assert saved["completeness"]["pipeline_status"] == "needs_review"
    assert "required_visual_stage_failed" in saved["warnings"]


@pytest.mark.parametrize("completion_status", ["needs_review", "complete"])
def test_document_dto_includes_only_valid_completion_status(
    tmp_path: Path, completion_status: str,
) -> None:
    report = tmp_path / "documents" / "doc-1" / "runs" / "attempt" / "audit-report.pdf"
    report.parent.mkdir(parents=True)
    report.write_bytes(b"%PDF")
    (report.parent / "verification.json").write_text(json.dumps({
        "verdict": "通过",
        "counts": {"PASS": 1, "FAIL": 0, "REVIEW": 0, "NA": 0},
        "results": [{"rule": "R01", "verdict": "PASS", "severity": "B"}],
        "findings": [],
        "finding_ids": [],
        "completion_status": completion_status,
        "warnings": ["required_visual_stage_failed"] if completion_status == "needs_review" else [],
        "completeness": {"overall_verdict": True, "coverage_table": True},
    }), encoding="utf-8")
    context = SimpleNamespace(
        provider_type="audit-report", provider_instance="default",
        host=SimpleNamespace(data_dir=tmp_path),
    )
    document = {
        "id": "doc-1", "file_name": "report.pdf", "status": "completed",
        "report_path": str(report), "findings_total": 0, "findings_review": 0,
    }

    dto = handlers._document_response(context, document)

    assert dto["completion_status"] == completion_status
    assert dto["findings_total"] == 0
    assert dto["findings_review"] == 0
    assert "warnings" not in dto
    assert "completeness" not in dto


def test_document_dto_does_not_read_escaped_verification_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outside_report = tmp_path.parent / "outside" / "audit-report.pdf"
    outside_report.parent.mkdir(parents=True)
    outside_report.write_bytes(b"%PDF")
    (outside_report.parent / "verification.json").write_text(
        json.dumps({"completion_status": "needs_review"}), encoding="utf-8",
    )
    context = SimpleNamespace(
        provider_type="audit-report", provider_instance="default",
        host=SimpleNamespace(data_dir=tmp_path),
    )
    document = {
        "id": "doc-escaped", "file_name": "report.pdf", "status": "completed",
        "report_path": str(outside_report),
    }
    reads: list[str] = []

    def read_owned_file(_context: Any, path_value: str) -> tuple[bytes, Path]:
        reads.append(path_value)
        raise AssertionError("outside verification files must not be read")

    monkeypatch.setattr(handlers, "_read_owned_file", read_owned_file)

    dto = handlers._document_response(context, document)

    assert "completion_status" not in dto
    assert reads == []
