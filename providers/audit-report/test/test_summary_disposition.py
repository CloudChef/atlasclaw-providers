# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "audit-report" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import audit_workflow  # noqa: E402


def _check_summary(markdown: str, project_finding_ids: set[str]) -> str:
    return audit_workflow._check_global(markdown, [], project_finding_ids=project_finding_ids)


def _without_markdown_validation(monkeypatch):
    monkeypatch.setattr(
        "run_document_audit.normalize_publishable_report",
        lambda markdown, **_kwargs: markdown,
        raising=False,
    )


def _disposition_rows(markdown: str, finding_id: str) -> list[str]:
    return [line for line in markdown.splitlines() if line.startswith("| " + finding_id + " |")]


def test_missing_disposition_table_adds_review_rows_and_does_not_infer_pass(monkeypatch):
    _without_markdown_validation(monkeypatch)
    markdown = "# Summary\n\n### F-000-001 [B] New global finding\nDetails.\n"

    result = _check_summary(markdown, {"F-001-001", "F-002-001"})

    assert "| FID | 复核结果 | 最终等级 | 理由/依据 |" in result
    for finding_id in ("F-001-001", "F-002-001"):
        rows = _disposition_rows(result, finding_id)
        assert len(rows) == 1
        assert "| 待复核 | — |" in rows[0]
        assert "模型未给出明确处置" in rows[0]
        assert "| 通过 |" not in rows[0]


@pytest.mark.parametrize("disposition", ["", "maybe"])
def test_blank_or_unrecognized_disposition_becomes_pending_without_blocking(
    monkeypatch, disposition: str,
):
    _without_markdown_validation(monkeypatch)
    markdown = (
        "# Summary\n\n"
        "| FID | 复核结果（成立/待复核/撤回） | 最终等级 | 理由/依据 |\n|---|---|---|---|\n"
        f"| F-001-001 | {disposition} | B | no usable decision |\n"
    )

    result = _check_summary(markdown, {"F-001-001"})

    rows = _disposition_rows(result, "F-001-001")
    assert len(rows) == 1
    assert "| 待复核 | — | 模型未给出明确处置" in rows[0]
    if disposition:
        assert disposition not in rows[0]


def test_valid_model_dispositions_are_preserved_and_only_missing_candidate_is_pending(monkeypatch):
    _without_markdown_validation(monkeypatch)
    valid = "| F-001-001 | 成立（原文确认） | B | 已核实 |"
    markdown = (
        "# Summary\n\n"
        "| FID | 复核结果 | 最终等级 | 理由/依据 |\n|---|---|---|---|\n"
        f"{valid}\n"
    )

    result = _check_summary(markdown, {"F-001-001", "F-002-001"})

    assert valid in result
    pending = _disposition_rows(result, "F-002-001")
    assert len(pending) == 1
    assert "| 待复核 | — | 模型未给出明确处置" in pending[0]


def test_no_disposition_table_is_added_without_project_candidates(monkeypatch):
    _without_markdown_validation(monkeypatch)
    markdown = "# Summary\n\nNo findings.\n"

    result = _check_summary(markdown, set())

    assert result == markdown


def test_duplicate_project_disposition_rows_remain_a_format_error(monkeypatch):
    _without_markdown_validation(monkeypatch)
    markdown = (
        "# Summary\n\n"
        "| FID | 复核结果 | 最终等级 | 理由/依据 |\n|---|---|---|---|\n"
        "| F-001-001 | 成立 | B | 已核实 |\n"
        "| F-001-001 | 撤回 | — | 重复行 |\n"
    )

    with pytest.raises(ValueError, match="Duplicate final disposition: F-001-001"):
        _check_summary(markdown, {"F-001-001"})


def test_pending_disposition_is_preserved_by_publishable_report_normalizer():
    markdown = "# Summary\n\n### F-001-001 [B] Candidate\nEvidence.\n"

    result = _check_summary(markdown, {"F-001-001"})

    row = _disposition_rows(result, "F-001-001")[0]
    assert "| 待复核 | — | 模型未给出明确处置" in row
    assert "报告已生成，部分结果待复核" in result
    assert "待复核不代表通过" in result
