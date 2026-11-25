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

import handlers  # noqa: E402
import batch_audit  # noqa: E402
from errors import ProviderError  # noqa: E402
from report_no import extract_report_no  # noqa: E402


def _upload_file(tmp_path: Path, name: str, data: bytes) -> Path:
    target = tmp_path / name
    target.write_bytes(data)
    return target


def test_upload_validation_accepts_pdf_and_docx(tmp_path: Path) -> None:
    assert handlers._validate_upload(_upload_file(tmp_path, "report.pdf", b"%PDF-1.4 body"), "report.pdf") == ".pdf"


def test_upload_validation_rejects_bad_inputs(tmp_path: Path, monkeypatch) -> None:
    with pytest.raises(ProviderError) as exc:
        handlers._validate_upload(_upload_file(tmp_path, "report.xls", b"x"), "report.xls")
    assert exc.value.code == "unsupported_file"

    with pytest.raises(ProviderError) as exc:
        handlers._validate_upload(_upload_file(tmp_path, "bad.pdf", b"not a pdf"), "bad.pdf")
    assert exc.value.code == "invalid_document"

    monkeypatch.setattr(handlers, "MAX_DOCUMENT_BYTES", 10)
    with pytest.raises(ProviderError) as exc:
        handlers._validate_upload(_upload_file(tmp_path, "large.pdf", b"%PDF-123456"), "large.pdf")
    assert exc.value.code == "file_too_large"


def test_document_response_and_actions() -> None:
    context = SimpleNamespace(user_id="alice")
    document = {
        "id": "doc-1",
        "file_name": "report.pdf",
        "report_no": "RPT-2026-0001",
        "status": "completed",
        "findings_total": 13,
        "findings_review": 4,
        "grade_summary": {"A": 9, "B": 4},
        "report_path": "/tmp/report.html",
        "created_at": "2026-11-24T10:32:00Z",
        "updated_at": "2026-11-24T10:35:00Z",
    }

    payload = handlers._document_response(context, document)

    assert payload["status"] == "completed"
    assert payload["report_available"] is True
    assert payload["actions"] == ["view_result", "download_report", "reaudit", "delete"]
    assert payload["urls"]["report"].endswith("/documents/doc-1/report")


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


def test_load_rules_parses_all_nineteen_rules() -> None:
    rules_path = ROOT / "skills" / "audit-report" / "references" / "audit-rules.md"
    rules = batch_audit.load_rules(rules_path)

    assert len(rules) == 19
    assert rules[0].rule_id == "R01"
    assert rules[0].severity == "B"
    assert rules[-1].rule_id == "R19"
    assert rules[-1].module == "照片有效性"


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

    assert packs == ["builtin@1.0.0", "active-pack@1.2.3"]
    assert len(rules) == 20
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
    assert len(ids) == 20
    assert packs == ["builtin@1.0.0", "customer-xy@1.2.0"]
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

    for heading in ("## 1. 审核对象", "## 2. 总评", "## 3. 问题清单", "## 5. 检查覆盖表（内置 19 项 + 已启用规则包）"):
        assert heading in markdown
    assert "**总评：不通过**" in markdown
    assert "### F-01 [A]" in markdown
