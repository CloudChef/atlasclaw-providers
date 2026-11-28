# -*- coding: utf-8 -*-
"""Preparation, configured API and report container integration regressions."""
from __future__ import annotations

import json
import argparse
import io
import re
import subprocess
import sys
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/audit-report/scripts"
sys.path.insert(0, str(SCRIPTS))
from audit_preparation import prepare_report, report_text
import audit_preparation
import extract_report
import run_document_audit
import audit_delivery
import audit_workflow
from run_document_audit import configured_model, validate_markdown
from desensitize_report import desensitize_pdf


def _successful_delivery(_markdown: Path, _source_pdf: Path, output_pdf: Path) -> dict:
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    output_pdf.write_bytes(b"%PDF-1.7 test")
    return {
        "report_pdf": str(output_pdf), "errors": [], "evidence_errors": [], "findings": [],
    }


def test_existing_desensitizer_is_called_before_text_extraction(tmp_path: Path) -> None:
    source = tmp_path / "private.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((40, 70), "Client Name: PRIVATE_CLIENT\nReport No: RPT-2026-001")
        page.insert_text((40, 130), "Applicant name:")
        page.insert_text((240, 130), "SPLIT_PRIVATE_CLIENT")
        page.insert_text((40, 160), "Applicant address:")
        page.insert_text((240, 160), "SPLIT_PRIVATE_LOCATION")
        page.insert_text((40, 190), "Applicant name:")
        page.insert_text((160, 190), "PRIVATE_PERSON")
        page.insert_text((350, 190), "Report No:")
        page.insert_text((450, 190), "KEEP-2026")
        pdf.set_metadata({"author": "PRIVATE_CLIENT"})
        pdf.save(source)
    result = prepare_report(source, tmp_path / "outputs")
    assert result["preparation_version"] == audit_preparation.PREPARATION_VERSION
    text, pages = report_text(result["pdf"])
    assert pages == 1
    assert "PRIVATE_CLIENT" not in text
    assert "SPLIT_PRIVATE_LOCATION" not in text
    assert "RPT-2026-001" in text
    assert "PRIVATE_PERSON" not in text
    assert "KEEP-2026" in text
    with pymupdf.open(result["pdf"]) as pdf:
        assert not pdf.metadata.get("author")
    assert prepare_report(source, tmp_path / "outputs") == result
    prepared = Path(result["pdf"])
    prepared.write_bytes(b"corrupt")
    refreshed = prepare_report(source, tmp_path / "outputs")
    assert report_text(refreshed["pdf"])[1] == 1


def test_report_text_layout_keeps_columns_and_blank_pages(tmp_path: Path) -> None:
    source = tmp_path / "layout-columns.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((40, 72), "LEFT-COLUMN-001")
        page.insert_text((350, 72), "RIGHT-COLUMN-002")
        pdf.new_page()  # A blank physical page must keep its page marker.
        rotated = pdf.new_page()
        rotated.insert_text((200, 200), "ROTATED-TEXT-003", rotate=90)
        pdf.save(source)

    text, page_count = report_text(source)

    assert page_count == 3
    assert "## Page 1" in text and "LEFT-COLUMN-001" in text and "RIGHT-COLUMN-002" in text
    assert re.search(r"LEFT-COLUMN-001 {2,}RIGHT-COLUMN-002", text)
    assert "## Page 2\n\n\n\n## Page 3" in text
    assert "ROTATED-TEXT-003" in text


def test_report_text_falls_back_to_native_text_on_layout_character_mismatch(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "layout-mismatch.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((40, 72), "NATIVE-CHARACTERS-RETAINED")
        pdf.save(source)

    def fake_run(command, **_kwargs):
        Path(command[-1]).write_text("WRONG-LAYOUT-TEXT\f", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(audit_preparation.subprocess, "run", fake_run)
    text, page_count = report_text(source)

    assert page_count == 1
    assert "NATIVE-CHARACTERS-RETAINED" in text
    assert "WRONG-LAYOUT-TEXT" not in text


def test_report_text_fails_closed_when_layout_cli_fails(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "layout-failure.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page()
        pdf.save(source)

    def failed_run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 2)

    monkeypatch.setattr(audit_preparation.subprocess, "run", failed_run)
    with pytest.raises(RuntimeError, match="layout text extraction failed"):
        report_text(source)


def test_preparation_and_layout_extraction_add_no_subprocess_timeout(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "unbounded-local-work.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((40, 70), "LOCAL TEXT")
        pdf.save(source)

    original_run = subprocess.run
    calls = []

    def inspect_run(command, **kwargs):
        assert "timeout" not in kwargs
        calls.append(command)
        return original_run(command, **kwargs)

    monkeypatch.setattr(audit_preparation.subprocess, "run", inspect_run)
    result = prepare_report(source, tmp_path / "prepared")
    text, page_count = report_text(result["pdf"])

    assert len(calls) == 2
    assert page_count == 1 and "LOCAL TEXT" in text


def test_libreoffice_conversion_adds_no_fixed_timeout(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "word.docx"
    source.write_bytes(b"synthetic")
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    calls = []

    def fake_run(command, **kwargs):
        assert "timeout" not in kwargs
        calls.append(command)
        (output_dir / "word.pdf").write_bytes(b"synthetic pdf")
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(extract_report, "find_soffice", lambda: "mock-soffice")
    monkeypatch.setattr(extract_report.subprocess, "run", fake_run)
    converted, error = extract_report.convert_office(source, output_dir, "pdf")

    assert error == "" and converted == output_dir / "word.pdf"
    assert len(calls) == 1


def test_image_spanning_header_or_footer_band_remains_visible(tmp_path: Path) -> None:
    source, output = tmp_path / "image-layout.pdf", tmp_path / "desensitized.pdf"

    def image_bytes(color: tuple[int, int, int]) -> bytes:
        buffer = io.BytesIO()
        Image.new("RGB", (20, 20), color).save(buffer, format="PNG")
        return buffer.getvalue()

    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_image(pymupdf.Rect(15, 15, 55, 55), stream=image_bytes((255, 0, 0)))
        page.insert_image(pymupdf.Rect(80, 120, 160, 210), stream=image_bytes((0, 255, 0)))
        page.insert_image(pymupdf.Rect(200, 790, 240, 830), stream=image_bytes((0, 0, 255)))
        page.insert_image(pymupdf.Rect(270, 700, 350, 790), stream=image_bytes((255, 255, 0)))
        pdf.save(source)

    stats = desensitize_pdf(source, output)
    with pymupdf.open(output) as pdf:
        page = pdf[0]
        pixmap = page.get_pixmap(dpi=72, alpha=False)

    def pixel(x: int, y: int) -> tuple[int, int, int]:
        offset = (y * pixmap.width + x) * pixmap.n
        return tuple(pixmap.samples[offset:offset + 3])

    assert stats["removed_header_images"] == 2
    assert pixel(35, 35) == (0, 0, 0)  # Small header logo was redacted.
    assert pixel(120, 170) == (0, 255, 0)  # Body photo crossing the header band remains.
    assert pixel(220, 810) == (0, 0, 0)  # Small footer logo was redacted.
    assert pixel(310, 745) == (255, 255, 0)  # Body photo crossing the footer band remains.


def test_old_preparation_cache_without_version_is_regenerated(tmp_path: Path, monkeypatch) -> None:
    source, output_dir = tmp_path / "source.pdf", tmp_path / "prepared"
    with pymupdf.open() as pdf:
        pdf.new_page()
        pdf.save(source)
    first = audit_preparation.prepare_report(source, output_dir)
    assert first["preparation_version"] == audit_preparation.PREPARATION_VERSION
    record_path = output_dir / "preparation.json"
    legacy_record = json.loads(record_path.read_text(encoding="utf-8"))
    legacy_record.pop("preparation_version")
    record_path.write_text(json.dumps(legacy_record), encoding="utf-8")

    original_run = audit_preparation.subprocess.run
    calls = 0

    def counted_run(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original_run(*args, **kwargs)

    monkeypatch.setattr(audit_preparation.subprocess, "run", counted_run)
    rebuilt = audit_preparation.prepare_report(source, output_dir)
    assert calls == 1
    assert rebuilt["preparation_version"] == audit_preparation.PREPARATION_VERSION


def test_model_credentials_resolve_from_core_env_without_modifying_environment(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("AUDIT_TEST_KEY", raising=False)
    (tmp_path / ".env").write_text("AUDIT_TEST_KEY=synthetic-value\n", encoding="utf-8")
    cfg = tmp_path / "atlasclaw.json"
    cfg.write_text(json.dumps({"model": {"primary": "one", "tokens": [{"id": "one", "model": "test",
        "api_key": "${AUDIT_TEST_KEY}", "base_url": "https://example.invalid/v1"}]}}), encoding="utf-8")
    model = configured_model(cfg)
    assert model["api_key"] == "synthetic-value"


def test_configured_model_preserves_explicit_token_limit_without_reasoning_override(tmp_path: Path) -> None:
    cfg = tmp_path / "atlasclaw.json"
    cfg.write_text(json.dumps({
        "model": {"primary": "one", "max_tokens": 49152,
                  "tokens": [{"id": "one", "provider": "openrouter", "model": "qwen-test",
                              "api_key": "secret", "base_url": "https://openrouter.ai/api/v1"}]}
    }), encoding="utf-8")

    model = configured_model(cfg)

    assert model["max_tokens"] == 49152
    assert "reasoning_effort" not in model
    assert model["provider"] == "openrouter"


class _FakeStreamResponse:
    status_code = 200

    def __init__(self, events):
        self.events = events

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def aiter_lines(self):
        for event in self.events:
            yield "data: " + (json.dumps(event) if event != "[DONE]" else event)


class _FakeAsyncClient:
    payload = None
    options = None

    def __init__(self, **kwargs):
        type(self).options = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def stream(self, _method, _url, *, headers, json):
        type(self).payload = json
        return _FakeStreamResponse([
            {"choices": [{"delta": {"content": "text result"}, "finish_reason": "stop"}],
             "usage": {"completion_tokens": 7}},
            "[DONE]",
        ])


@pytest.mark.asyncio
async def test_request_markdown_leaves_generation_limits_to_model_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_document_audit.httpx, "AsyncClient", _FakeAsyncClient)
    model = {"model": "qwen-test", "api_key": "secret", "base_url": "https://openrouter.ai/api/v1",
             "provider": "openrouter"}
    text, usage = await run_document_audit.request_markdown(model, "Review extracted report text")

    content = _FakeAsyncClient.payload["messages"][1]["content"]
    assert content == "Review extracted report text"
    assert all("image_url" not in str(message) for message in _FakeAsyncClient.payload["messages"])
    assert "reasoning" not in _FakeAsyncClient.payload
    assert "max_tokens" not in _FakeAsyncClient.payload
    assert "temperature" not in _FakeAsyncClient.payload
    assert _FakeAsyncClient.options == {"timeout": None}
    assert text == "text result" and usage["completion_tokens"] == 7


@pytest.mark.asyncio
async def test_request_markdown_keeps_explicit_token_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_document_audit.httpx, "AsyncClient", _FakeAsyncClient)
    await run_document_audit.request_markdown(
        {"model": "model-test", "api_key": "secret", "base_url": "https://example.invalid/v1"},
        "prompt", max_tokens=6144,
    )
    assert _FakeAsyncClient.payload["max_tokens"] == 6144


@pytest.mark.asyncio
async def test_request_markdown_rejects_length_with_safe_finish_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    class TruncatedClient(_FakeAsyncClient):
        def stream(self, _method, _url, *, headers, json):
            type(self).payload = json
            return _FakeStreamResponse([
                {"choices": [{"delta": {"content": "private partial body"}, "finish_reason": "length"}]},
                "[DONE]",
            ])

    monkeypatch.setattr(run_document_audit.httpx, "AsyncClient", TruncatedClient)
    with pytest.raises(RuntimeError) as exc:
        await run_document_audit.request_markdown(
            {"model": "gpt-test", "api_key": "secret", "base_url": "https://example.invalid/v1"}, "prompt")
    assert "finish_reason=length" in str(exc.value)
    assert "has_content=True" in str(exc.value)
    assert "private partial body" not in str(exc.value)
    assert "reasoning" not in TruncatedClient.payload
    assert "max_tokens" not in TruncatedClient.payload


def test_cli_token_limit_is_only_set_when_user_configures_it() -> None:
    model = {"max_tokens": 49152}
    assert run_document_audit._effective_max_tokens(model, explicit=8192) == 8192
    assert run_document_audit._effective_max_tokens(model, explicit=None) == 49152
    assert run_document_audit._effective_max_tokens({"max_tokens": None}, explicit=None) is None


@pytest.mark.asyncio
async def test_audit_prepared_uses_text_only_workflow_and_keeps_full_materials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import audit_materials
    from _rules import load_rules

    report_text_value = "## Page 1\ncomplete extracted page text"
    material = {"filename": "ledger.xlsx", "kind": "ledger", "content": "full workbook body",
                "sha256": "a" * 64}
    monkeypatch.setattr(run_document_audit, "report_text", lambda _path: (report_text_value, 1))
    monkeypatch.setattr(audit_materials, "read_material", lambda _path: material)
    calls: list[str] = []
    execution: dict = {}

    async def execute(report, materials, count, submit, output, **kwargs):
        execution.update(report=report, materials=materials, count=count, kwargs=kwargs)
        calls.append(await submit("text-only project review prompt"))
        rows = "\n".join(
            f"| {rule} | 模块 | 检查项 | B | 通过 | 来源依据 |" for rule in load_rules().ids
        )
        return f"# 报告\n\n## 5. 检查覆盖表\n{rows}\n"

    monkeypatch.setattr(audit_workflow, "execute_audit", execute)
    monkeypatch.setattr(audit_delivery, "deliver_report", _successful_delivery)

    async def submit(prompt: str) -> str:
        assert isinstance(prompt, str)
        return "text response"

    await run_document_audit.audit_prepared(Path("prepared.pdf"), [Path("ledger.xlsx")], tmp_path, submit)

    assert calls == ["text response"]
    assert execution["report"] == report_text_value
    assert execution["count"] == 1
    assert execution["materials"][0]["content"] == "full workbook body"
    assert set(execution["kwargs"]) == {"on_progress", "rules_dir", "ruleset"}
    submission = json.loads((tmp_path / "submission.json").read_text(encoding="utf-8"))
    assert submission["materials"][0]["characters"] == len("full workbook body")
    assert not any(key.startswith("visual_") or "image" in key for key in submission)
    assert (tmp_path / "audit-report.pdf").is_file()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("findings", "errors", "evidence_errors", "should_complete"),
    [
        ([], [], [], True),
        ([{"id": "F-001001", "status": "error", "image": None, "images": []}],
         ["F-001001: capture failed"], ["F-001001: capture failed"], False),
        ([{"id": "F-001002", "status": "captured", "image": "evidence/F-001002.png",
           "images": [{"page": 1, "image": "evidence/missing.png",
                       "reference": "evidence/missing.png"}]}], [], [], False),
    ],
)
async def test_audit_prepared_publishes_pdf_for_incomplete_evidence_delivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    findings: list[dict], errors: list[str], evidence_errors: list[str], should_complete: bool,
) -> None:
    from _rules import load_rules

    monkeypatch.setattr(run_document_audit, "report_text", lambda _path: ("## Page 1\nreport", 1))

    async def execute(*_args, **_kwargs):
        rows = "\n".join(
            (f"| {rule_id} | 模块 | 检查项 | B | 不适用 | 没有对应输入 |"
             if set(rule.get("requires") or []) & {"standard", "ledger", "materials"}
             else f"| {rule_id} | 模块 | 检查项 | B | 通过 | 来源依据 |")
            for rule_id, rule in load_rules().rules.items()
        )
        return f"# 报告\n\n**总评：通过**\n\n## 5. 检查覆盖表\n{rows}\n"

    def fake_delivery(_markdown: Path, _source_pdf: Path, output_pdf: Path) -> dict:
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        output_pdf.write_bytes(b"%PDF-1.7 diagnostic")
        return {
            "report_pdf": str(output_pdf), "errors": errors,
            "evidence_errors": evidence_errors, "findings": findings,
        }

    monkeypatch.setattr(audit_workflow, "execute_audit", execute)
    monkeypatch.setattr(audit_delivery, "deliver_report", fake_delivery)

    async def submit(_prompt: str) -> str:
        raise AssertionError("mocked workflow should not submit model requests")

    result = await run_document_audit.audit_prepared(Path("prepared.pdf"), [], tmp_path, submit)
    assert result["report_pdf"] == str(tmp_path / "audit-report.pdf")
    assert result["completion_status"] == ("complete" if should_complete else "needs_review")
    if not should_complete:
        assert "delivery_evidence_incomplete" in result["warnings"]
        assert "证据截图未完整生成" in (tmp_path / "audit.md").read_text(encoding="utf-8")
        import pymupdf
        with pymupdf.open(result["report_pdf"]) as report_pdf:
            assert report_pdf.page_count > 0

    saved = json.loads((tmp_path / "delivery.json").read_text(encoding="utf-8"))
    assert saved["findings"] == findings
    assert (tmp_path / "audit-report.pdf").is_file()


def test_delivery_gate_accepts_real_capture_path_shape(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    evidence_dir = report_dir / "evidence"
    evidence_dir.mkdir(parents=True)
    report_pdf = report_dir / "audit-report.pdf"
    primary = evidence_dir / "F-021001.png"
    page_image = evidence_dir / "F-021001-p33.png"
    report_pdf.write_bytes(b"%PDF-1.7")
    primary.write_bytes(b"primary image")
    page_image.write_bytes(b"page image")
    result = {
        "report_pdf": str(report_pdf), "errors": [], "evidence_errors": [],
        "findings": [{
            "id": "F-021001", "status": "captured", "image": str(primary),
            "images": [{"page": 33, "image": str(page_image),
                        "reference": "evidence/F-021001-p33.png"}],
        }],
    }
    run_document_audit._validate_delivery_result(result, report_dir)


@pytest.mark.parametrize("bad_path_kind", ["escape", "empty"])
def test_delivery_gate_rejects_escaped_or_empty_evidence(
    tmp_path: Path, bad_path_kind: str,
) -> None:
    report_dir = tmp_path / "report"
    evidence_dir = report_dir / "evidence"
    evidence_dir.mkdir(parents=True)
    report_pdf = report_dir / "audit-report.pdf"
    primary = evidence_dir / "F-021002.png"
    bad_file = tmp_path / "external.png" if bad_path_kind == "escape" else evidence_dir / "empty.png"
    report_pdf.write_bytes(b"%PDF-1.7")
    primary.write_bytes(b"primary image")
    bad_file.write_bytes(b"outside evidence") if bad_path_kind == "escape" else bad_file.write_bytes(b"")
    result = {
        "report_pdf": str(report_pdf), "errors": [], "evidence_errors": [],
        "findings": [{
            "id": "F-021002", "status": "captured", "image": str(primary),
            "images": [{"page": 33, "image": str(bad_file),
                        "reference": str(bad_file) if bad_path_kind == "escape" else "evidence/empty.png"}],
        }],
    }
    with pytest.raises(RuntimeError, match="delivery is incomplete"):
        run_document_audit._validate_delivery_result(result, report_dir)


@pytest.mark.asyncio
async def test_cli_records_stage_usage_and_explicit_token_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_document_audit, "prepare_report", lambda *_args: {"pdf": "prepared.pdf"})
    monkeypatch.setattr(run_document_audit, "configured_model", lambda *_args: {
        "model": "qwen-test", "max_tokens": 49152, "api_key": "secret", "base_url": "unused",
    })
    requests: list[tuple[str, int]] = []

    async def fake_request(_model, prompt, max_tokens):
        assert isinstance(prompt, str)
        requests.append((prompt, max_tokens))
        return "response", {"completion_tokens": len(requests)}

    monkeypatch.setattr(run_document_audit, "request_markdown", fake_request)

    async def fake_audit_prepared(_pdf, _materials, _out, submit, *, on_progress, **_kwargs):
        await submit("# 本次任务：识别报告项目目录")
        await submit("# 本次任务：一个项目的完整审核")
        await submit("# 本次任务：全局审核与汇总")

    monkeypatch.setattr(run_document_audit, "audit_prepared", fake_audit_prepared)
    args = argparse.Namespace(
        out=tmp_path, report=Path("report.pdf"), core_config=Path("config.json"),
        model_token_id=None, max_output_tokens=8192, materials=[], no_visual=True, visual_dpi=144,
    )
    await run_document_audit.run_cli(args)

    assert all(item[1] == 8192 for item in requests)
    usage = json.loads((tmp_path / "model-usage.json").read_text(encoding="utf-8"))
    assert [item["stage"] for item in usage["requests"]] == ["index", "project-review", "summary"]
    assert [item["usage"]["completion_tokens"] for item in usage["requests"]] == [1, 2, 3]
    assert all("image_identifiers" not in item for item in usage["requests"])
    assert "secret" not in (tmp_path / "model-usage.json").read_text(encoding="utf-8")


def test_incomplete_rule_container_cannot_be_published() -> None:
    md = "# 审核报告\n\n" + "\n".join(f"| R{i:02d} | 模块 | 检查项 | A | 通过 | 模型说明 |" for i in range(1, 47))
    assert validate_markdown(md) == md
    with pytest.raises(ValueError, match="R19"):
        validate_markdown(md.replace("| R19 |", "| missing |"))
    with pytest.raises(ValueError, match="R01"):
        validate_markdown(md.replace("| R01 | 模块 | 检查项 | A | 通过 |", "| R01 | 模块 | 检查项 | A | <结果> |"))
    with pytest.raises(ValueError, match="R01"):
        validate_markdown(md.replace("| R01 | 模块 | 检查项 | A | 通过 | 模型说明 |", "| R01 | 模块 | 检查项 | A | 通过 | |"))


@pytest.mark.parametrize("wrapped", [
    "说明文字\n\n# 报告\n\n| R01 | 模块 | 检查项 | A | 通过 | 依据 |",
    "```markdown\n# 报告\n\n| R01 | 模块 | 检查项 | A | 通过 | 依据 |\n```",
    "```md\n# 报告\n\n| R01 | 模块 | 检查项 | A | 通过 | 依据 |\n```",
    "```\n# 报告\n\n| R01 | 模块 | 检查项 | A | 通过 | 依据 |\n```",
    "~~~MD\n# 报告\n\n| R01 | 模块 | 检查项 | A | 通过 | 依据 |\n~~~",
    "````markdown\n# 报告\n\n| R01 | 模块 | 检查项 | A | 通过 | 依据 |\n````",
])
def test_markdown_container_accepts_preface_short_body_and_common_fences(wrapped: str) -> None:
    assert validate_markdown(wrapped, required_rule_ids=["R01"])


@pytest.mark.parametrize("status", ["待复核", "证据不足"])
def test_coverage_review_status_is_accepted_as_distinct_from_pass_or_not_applicable(status: str) -> None:
    markdown = (
        "# 审核报告\n\n## 5. 检查覆盖表\n"
        f"| R01 | 文件完整性 | 页码连续 | B | {status} | 当前只提供已脱敏的报告文本，相关视觉或原件材料在本轮输入中无法核实；该状态需要复核，不能据此当作通过或不适用。 |\n"
    )

    assert validate_markdown(markdown, required_rule_ids=["R01"]) == markdown.strip()
