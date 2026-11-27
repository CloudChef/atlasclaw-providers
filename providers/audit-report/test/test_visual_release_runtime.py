# -*- coding: utf-8 -*-
"""Release regressions for the original-page visual audit path."""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest
from PIL import Image

PROVIDER_ROOT = Path(__file__).resolve().parents[1]
API_DIR = PROVIDER_ROOT / "api"
SCRIPTS_DIR = PROVIDER_ROOT / "skills/audit-report/scripts"
sys.path.insert(0, str(API_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

import audit_preparation  # noqa: E402
import audit_service  # noqa: E402
import audit_visual  # noqa: E402
import run_document_audit  # noqa: E402
import audit_project_prompts  # noqa: E402
from errors import ProviderError  # noqa: E402
from store import DocumentStore  # noqa: E402


def _pdf(path: Path) -> None:
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((40, 60), "Prepared visual page")
        pdf.save(path)


@pytest.mark.asyncio
async def test_cli_visual_review_uses_the_original_document(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = tmp_path / "original.pdf"
    original.write_bytes(b"original")
    prepared_pdf = tmp_path / "out" / "prepared-desensitized.pdf"
    prepared_pdf.parent.mkdir()
    prepared_pdf.write_bytes(b"prepared")
    sources: list[Path] = []
    submitted: dict = {}

    monkeypatch.setattr(run_document_audit, "prepare_report", lambda *_args: {"pdf": str(prepared_pdf)})

    def prepare_visual(source: str | Path, _output: Path) -> dict:
        sources.append(Path(source))
        return {"pdf": str(source), "page_count": 1}

    monkeypatch.setattr(run_document_audit, "prepare_visual_pdf", prepare_visual)
    monkeypatch.setattr(run_document_audit, "configured_model", lambda *_args: {
        "model": "configured-model", "api_key": "secret", "base_url": "https://example.invalid/v1",
    })

    async def audit_prepared(_pdf, _materials, _output, _submit, **kwargs) -> None:
        submitted.update(kwargs)

    monkeypatch.setattr(run_document_audit, "audit_prepared", audit_prepared)
    args = argparse.Namespace(
        out=prepared_pdf.parent, report=original, no_visual=False, core_config=tmp_path / "config.json",
        model_token_id=None, visual_model=None, materials=[], max_output_tokens=None, visual_dpi=144,
    )

    await run_document_audit.run_cli(args)

    assert sources == [original]
    assert Path(submitted["visual_pdf"]) == original


@pytest.mark.asyncio
async def test_provider_audit_submits_prepared_pages_through_the_visual_skill_bridge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = SimpleNamespace(data_dir=tmp_path / "provider-data", shared_data_dir=tmp_path / "shared")
    host.data_dir.mkdir(parents=True)
    source = host.data_dir / "original.pdf"
    source.write_bytes(b"original")
    store = DocumentStore(host.data_dir)
    document = store.create({
        "id": "doc-visual", "user_id": "alice", "file_name": "original.pdf",
        "file_path": str(source), "extension": ".pdf", "sha256": "",
    })
    prepared_pdf = host.data_dir / "documents" / "doc-visual" / "prepared" / "desensitized.pdf"
    visual_pdf = host.data_dir / "documents" / "doc-visual" / "runs" / "visual-source.pdf"
    visual_sources: list[Path] = []
    skill_dir = tmp_path / "skill"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "references" / "audit-system.md").write_text("system contract", encoding="utf-8")
    monkeypatch.setattr(audit_service, "_skill_dir", lambda: skill_dir)
    monkeypatch.setattr(audit_preparation, "PREPARATION_VERSION", 1)

    def prepare_report(_source: str, _output: Path) -> dict:
        prepared_pdf.parent.mkdir(parents=True, exist_ok=True)
        prepared_pdf.write_bytes(b"prepared")
        return {"pdf": str(prepared_pdf)}

    monkeypatch.setattr(audit_preparation, "prepare_report", prepare_report)
    def prepare_visual(source_path: str | Path, output_dir: Path) -> dict:
        visual_sources.append(Path(source_path))
        output_dir.mkdir(parents=True, exist_ok=True)
        visual_pdf.write_bytes(b"original visual PDF")
        return {"pdf": str(visual_pdf)}

    monkeypatch.setattr(audit_preparation, "prepare_visual_pdf", prepare_visual)
    monkeypatch.setattr(audit_service.standards_service, "snapshot_audit_library", lambda _host, output: {
        "material_paths": [], "rules_dir": output / "rules",
    })
    monkeypatch.setitem(sys.modules, "_rules", SimpleNamespace(load_rules=lambda _root: SimpleNamespace(ids=[])))
    monkeypatch.setattr(audit_service, "_llm_report_metadata", lambda *_args, **_kwargs: (
        {"verdict": "待复核", "results": [], "findings": []},
        {"findings_total": 0, "findings_review": 0, "grade_summary": {}},
    ))
    model_calls: list[tuple[str, dict]] = []

    async def run_text(**kwargs) -> str:
        model_calls.append(("text", kwargs))
        return "text response"

    async def run_visual(**kwargs) -> str:
        model_calls.append(("visual", kwargs))
        return "### Page 1\nPrepared page observation"

    async def audit_prepared(text_pdf, _materials, attempt_dir: Path, submit, **kwargs) -> None:
        assert Path(text_pdf) == prepared_pdf
        assert Path(kwargs["visual_pdf"]) == visual_pdf
        await submit("text stage")
        await kwargs["submit_visual"]("visual stage", [{
            "data": b"original page pixels", "media_type": "image/png",
            "identifier": "page-1", "page": 1,
        }])
        attempt_dir.mkdir(parents=True, exist_ok=True)
        (attempt_dir / "audit-report.pdf").write_bytes(b"%PDF-report")
        (attempt_dir / "audit-raw.md").write_text("complete report", encoding="utf-8")

    monkeypatch.setattr(run_document_audit, "audit_prepared", audit_prepared)
    context = SimpleNamespace(host=host, run_text=run_text, run_visual=run_visual)
    attempt_dir = host.data_dir / "documents" / "doc-visual" / "runs" / "attempt"

    await audit_service._run_document_audit(context, store, document, attempt_dir)

    assert [kind for kind, _kwargs in model_calls] == ["text", "visual"]
    assert visual_sources == [source]
    assert model_calls[0][1]["skill_id"] == "audit-report:audit-report"
    assert model_calls[1][1]["skill_id"] == "audit-report:audit-report"
    assert model_calls[1][1]["timeout_seconds"] is None
    assert model_calls[1][1]["system_prompt"] == "system contract"
    assert model_calls[1][1]["images"][0]["data"] == b"original page pixels"
    assert store.get(document["id"], "alice")["status"] == "completed"


@pytest.mark.asyncio
async def test_missing_model_bridges_publish_downloadable_pending_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = SimpleNamespace(data_dir=tmp_path, shared_data_dir=tmp_path / "shared")
    original = tmp_path / "original.pdf"
    _pdf(original)
    store = DocumentStore(tmp_path)
    document = store.create({
        "id": "doc-no-model", "user_id": "alice", "file_name": original.name,
        "file_path": str(original), "extension": ".pdf", "sha256": "",
    })
    prepared_pdf = tmp_path / "documents" / document["id"] / "prepared.pdf"

    def prepare_report(_source: str, _output: Path) -> dict:
        prepared_pdf.parent.mkdir(parents=True, exist_ok=True)
        _pdf(prepared_pdf)
        return {"pdf": str(prepared_pdf)}

    monkeypatch.setattr(audit_preparation, "prepare_report", prepare_report)
    monkeypatch.setattr(audit_preparation, "prepare_visual_pdf", lambda *_args: {"pdf": str(original)})
    monkeypatch.setattr(audit_service.standards_service, "snapshot_audit_library", lambda _host, _output: {
        "material_paths": [], "rules_dir": SCRIPTS_DIR.parent / "rules",
    })

    await audit_service._run_document_audit(SimpleNamespace(host=host), store, document, tmp_path / "runs" / "attempt")

    result = store.get(document["id"], "alice")
    assert result["status"] == "completed"
    assert result["progress_text"] == "报告已生成，部分结果待复核"
    assert Path(result["report_path"]).is_file()
    verification = json.loads((tmp_path / "runs" / "attempt" / "verification.json").read_text(encoding="utf-8"))
    assert verification["completion_status"] == "needs_review"
    assert "required_visual_stage_failed" in verification["warnings"]
    assert verification["verdict"] == "待复核（模型未给出结论）"


def test_missing_model_bridge_is_recorded_for_soft_delivery() -> None:
    assert audit_service._require_model_bridges(SimpleNamespace(run_text=lambda **_kwargs: "text")) is None


@pytest.mark.asyncio
async def test_required_visual_stage_missing_becomes_pending_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import audit_delivery
    import audit_workflow

    async def submit(_prompt: str) -> str:
        return "# 审核报告\n**总评：通过**\n"

    async def partial_report(*_args, **_kwargs) -> str:
        return await submit("")

    monkeypatch.setattr(run_document_audit, "report_text", lambda _path: ("report text", 1))
    monkeypatch.setattr(audit_workflow, "execute_audit", partial_report)
    monkeypatch.setitem(sys.modules, "_rules", SimpleNamespace(load_rules=lambda _root=None: SimpleNamespace(
        ids=["R01"], severity={"R01": "C"}, rules={},
    )))

    def deliver(markdown_path: Path, _source_pdf: Path, output_pdf: Path) -> dict:
        output_pdf.write_bytes(b"%PDF incomplete")
        return {"report_pdf": str(output_pdf), "errors": [], "evidence_errors": [], "findings": []}

    monkeypatch.setattr(audit_delivery, "deliver_report", deliver)
    result = await run_document_audit.audit_prepared(
        tmp_path / "prepared.pdf", [], tmp_path / "output", submit, require_visual=True,
    )
    report = (tmp_path / "output" / "audit.md").read_text(encoding="utf-8")
    assert result["completion_status"] == "needs_review"
    assert "视觉阶段未能完整执行" in report
    assert "报告未完成" in report


@pytest.mark.asyncio
async def test_visual_render_dpi_is_per_call_under_concurrent_audits(tmp_path: Path, monkeypatch) -> None:
    pdf_path = tmp_path / "prepared.pdf"
    _pdf(pdf_path)
    monkeypatch.setattr(audit_visual, "_build_visual_prompt", lambda *_args, **_kwargs: "prompt")
    image_sizes: dict[int, tuple[int, int]] = {}

    def submit_for(dpi: int):
        async def submit(_prompt: str, images: list[dict]) -> str:
            with Image.open(io.BytesIO(images[0]["data"])) as image:
                image_sizes[dpi] = image.size
            return "### Page 1\nVisual observation"
        return submit

    original_dpi = audit_visual.RENDER_DPI
    output_dirs = [tmp_path / "dpi-72", tmp_path / "dpi-216"]
    await asyncio.gather(*(
        audit_visual.inspect_report(
            pdf_path, "## Page 1\nPrepared text", submit_for(dpi), output_dir,
            visual_dpi=dpi,
        )
        for dpi, output_dir in zip((72, 216), output_dirs)
    ))

    assert image_sizes[216][0] > image_sizes[72][0]
    assert [json.loads((path / "visual.json").read_text(encoding="utf-8"))["render_dpi"]
            for path in output_dirs] == [72, 216]
    assert audit_visual.RENDER_DPI == original_dpi


@pytest.mark.asyncio
async def test_original_visual_pdf_must_align_with_prepared_text_page_count(tmp_path: Path) -> None:
    pdf_path = tmp_path / "original-two-pages.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page()
        pdf.new_page()
        pdf.save(pdf_path)

    async def should_not_submit(_prompt: str, _images: list[dict]) -> str:
        raise AssertionError("a mismatched page map must not reach the model")

    with pytest.raises(ValueError, match="Visual review is missing page markers: 2"):
        await audit_visual.inspect_report(
            pdf_path, "## Page 1\nPrepared text", should_not_submit, tmp_path / "output",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("finish_reason", "content"),
    [("length", "private partial response"), ("stop", ""), (None, "unconfirmed response")],
)
async def test_request_visual_rejects_incomplete_responses_without_leaking_content_or_key(
    monkeypatch: pytest.MonkeyPatch, finish_reason: str | None, content: str,
) -> None:
    class Response:
        status_code = 200

        def json(self) -> dict:
            return {"choices": [{"message": {"content": content}, "finish_reason": finish_reason}],
                    "usage": {"completion_tokens": 3}}

    class Client:
        payload: dict | None = None

        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, *, headers, json):
            type(self).payload = json
            assert headers["Authorization"] == "Bearer secret-api-key"
            return Response()

    monkeypatch.setattr(run_document_audit.httpx, "AsyncClient", Client)
    with pytest.raises(RuntimeError) as exc:
        await run_document_audit.request_visual(
            {"model": "vision-model", "api_key": "secret-api-key", "base_url": "https://example.invalid/v1"},
            "prompt", [{"data": b"image", "media_type": "image/png"}],
        )

    assert "finish_reason=" in str(exc.value)
    assert "secret-api-key" not in str(exc.value)
    assert "private partial response" not in str(exc.value)
    assert "max_tokens" not in Client.payload
    assert "reasoning" not in Client.payload


@pytest.mark.asyncio
async def test_request_visual_accepts_only_complete_response_and_respects_configured_token_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        status_code = 200

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "complete"}, "finish_reason": "stop"}],
                    "usage": {"completion_tokens": 7}}

    class Client:
        payload: dict | None = None

        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, *, json, **_kwargs):
            type(self).payload = json
            return Response()

    monkeypatch.setattr(run_document_audit.httpx, "AsyncClient", Client)
    result = await run_document_audit.request_visual(
        {"model": "vision-model", "api_key": "secret", "base_url": "https://example.invalid/v1",
         "max_tokens": 49152},
        "prompt", [{"data": b"image", "media_type": "image/png"}],
    )

    assert result == "complete"
    assert Client.payload["max_tokens"] == 49152
    assert "reasoning" not in Client.payload


def test_cli_visual_model_is_not_overridden_by_a_builtin_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    observed: list[str | None] = []
    monkeypatch.setattr(sys, "argv", [
        "run_document_audit.py", str(tmp_path / "report.pdf"), "--materials", str(tmp_path / "material.txt"),
        "--out", str(tmp_path / "out"), "--core-config", str(tmp_path / "config.json"),
    ])

    def capture_run(coroutine) -> None:
        observed.append(coroutine.cr_frame.f_locals["args"].visual_model)
        coroutine.close()

    monkeypatch.setattr(run_document_audit.asyncio, "run", capture_run)
    assert run_document_audit.main() == 0
    assert observed == [None]


def test_visual_format_repair_prompt_comes_from_a_reference_template() -> None:
    error = "Visual page headings must exactly cover [1] once in order"
    previous_response = "Original observed label and evidence."
    rendered = audit_project_prompts.build_visual_retry_prompt("base prompt", error, previous_response)
    template_path = PROVIDER_ROOT / "skills/audit-report/references/prompts/visual-repair.md"
    expected = template_path.read_text(encoding="utf-8").removesuffix("\n").replace(
        "{{FORMAT_ERROR}}", error,
    ).replace("{{PREVIOUS_RESPONSE}}", previous_response)

    assert rendered == "base prompt\n\n" + expected
