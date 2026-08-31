"""Critical local-extraction and visual-OCR tests for Knowledge attachments."""

from __future__ import annotations

import importlib.util
from io import BytesIO
from pathlib import Path
import sys
from types import ModuleType
from typing import Any

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, NumberObject


PROVIDER_ROOT = Path(__file__).resolve().parents[1]


def _load_converter_module() -> ModuleType:
    """Load the provider converter without relying on an installed package name."""
    converter_path = PROVIDER_ROOT / "knowledge_attachment_converter.py"
    spec = importlib.util.spec_from_file_location(
        "markdown_vault_knowledge_attachment_converter_test",
        converter_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


converter_module = _load_converter_module()


class _FakeVisualRuntime:
    """Capture provider visual calls through the same narrow contract Core exposes."""

    def __init__(self, *, model_name: str = "vision-test", available: bool = True) -> None:
        """Create a deterministic visual bridge for one converter test."""
        self.visual_model_name = model_name
        self.visual_available = available
        self.calls: list[dict[str, Any]] = []

    async def run_visual(self, **kwargs: Any) -> str:
        """Record one visual request and return OCR-shaped Markdown."""
        self.calls.append(kwargs)
        return "OCR_VISUAL_MARKER_8834"


def _text_pdf(marker: str) -> bytes:
    """Build a one-page PDF with a real extractable text layer."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    content = DecodedStreamObject()
    content.set_data(f"BT /F1 12 Tf 72 720 Td ({marker}) Tj ET".encode())
    page[NameObject("/Contents")] = content
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _blank_pdf() -> bytes:
    """Build a one-page PDF without text or raster images."""
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _raster_image_pdf() -> bytes:
    """Build a textless PDF page containing one explicit raster image."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    image = DecodedStreamObject()
    image.set_data(bytes([255, 255, 255]))
    image.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Image"),
            NameObject("/Width"): NumberObject(1),
            NameObject("/Height"): NumberObject(1),
            NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
            NameObject("/BitsPerComponent"): NumberObject(8),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/XObject"): DictionaryObject({NameObject("/Im1"): image})}
    )
    content = DecodedStreamObject()
    content.set_data(b"q 100 0 0 100 72 600 cm /Im1 Do Q")
    page[NameObject("/Contents")] = content
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _multipage_pdf(page_count: int) -> bytes:
    """Build a PDF with the requested page count for resource-boundary tests."""
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.mark.asyncio
async def test_text_pdf_is_extracted_locally_without_llm() -> None:
    """Verify even a short PDF text layer is extracted without a visual-model request."""
    runtime = _FakeVisualRuntime()
    converter = converter_module.KnowledgeAttachmentLlmConverter(runtime, timeout_seconds=30)

    result = await converter.convert(
        {
            "fileId": "pdf-1",
            "fileName": "evidence.pdf",
            "contentType": "application/pdf",
            "data": _text_pdf("TITLE"),
        },
        {"knowledgeId": "knowledge-1"},
    )

    assert "## Page 1" in result["markdown"]
    assert "TITLE" in result["markdown"]
    assert result["assets"] == []
    assert runtime.calls == []


@pytest.mark.asyncio
async def test_office_uses_local_pdf_text_extraction_without_llm(monkeypatch) -> None:
    """Verify Office rendering feeds local PDF extraction when a text layer exists."""
    runtime = _FakeVisualRuntime()
    converter = converter_module.KnowledgeAttachmentLlmConverter(runtime, timeout_seconds=30)
    monkeypatch.setattr(
        converter,
        "_office_to_pdf",
        lambda file_name, data, timeout_seconds: _text_pdf("LOCAL_SLIDE_MARKER_5628"),
    )

    result = await converter.convert(
        {
            "fileId": "pptx-1",
            "fileName": "slides.pptx",
            "contentType": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "data": b"office-container",
        },
        {"knowledgeId": "knowledge-1"},
    )

    assert "## Slide 1" in result["markdown"]
    assert "LOCAL_SLIDE_MARKER_5628" in result["markdown"]
    assert result["assets"] == []
    assert runtime.calls == []


@pytest.mark.asyncio
async def test_image_is_delegated_to_visual_llm() -> None:
    """Verify image OCR is delegated through Core's visual-model bridge."""
    runtime = _FakeVisualRuntime()
    converter = converter_module.KnowledgeAttachmentLlmConverter(runtime, timeout_seconds=30)

    result = await converter.convert(
        {
            "fileId": "image-1",
            "fileName": "diagram.png",
            "contentType": "image/png",
            "data": b"\x89PNG\r\n\x1a\nimage-data",
        },
        {"knowledgeId": "knowledge-1"},
    )

    assert "## Image" in result["markdown"]
    assert "OCR_VISUAL_MARKER_8834" in result["markdown"]
    assert result["assets"][0]["fileName"] == "image.png"
    assert runtime.calls[0]["media_type"] == "image/png"
    assert runtime.calls[0]["data"].startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_textless_pdf_page_is_rendered_for_visual_ocr(monkeypatch) -> None:
    """Verify a textless PDF raster-image page is sent to the visual model."""
    runtime = _FakeVisualRuntime()
    converter = converter_module.KnowledgeAttachmentLlmConverter(runtime, timeout_seconds=30)
    monkeypatch.setattr(
        converter,
        "_render_pdf_page",
        lambda pdf_data, page_number, timeout_seconds: b"\x89PNG\r\n\x1a\nrendered-page",
    )

    result = await converter.convert(
        {
            "fileId": "scan-1",
            "fileName": "scan.pdf",
            "contentType": "application/pdf",
            "data": _raster_image_pdf(),
        },
        {"knowledgeId": "knowledge-1"},
    )

    assert "## Page 1" in result["markdown"]
    assert "OCR_VISUAL_MARKER_8834" in result["markdown"]
    assert result["assets"][0]["fileName"] == "page-1.png"
    assert runtime.calls[0]["media_type"] == "image/png"


@pytest.mark.asyncio
async def test_blank_pdf_page_does_not_trigger_visual_ocr(monkeypatch) -> None:
    """Verify a textless page without raster images remains local and does not use a model."""
    runtime = _FakeVisualRuntime()
    converter = converter_module.KnowledgeAttachmentLlmConverter(runtime, timeout_seconds=30)
    rendered_pages: list[int] = []
    monkeypatch.setattr(
        converter,
        "_render_pdf_page",
        lambda pdf_data, page_number, timeout_seconds: rendered_pages.append(page_number),
    )

    result = await converter.convert(
        {
            "fileId": "blank-1",
            "fileName": "blank.pdf",
            "contentType": "application/pdf",
            "data": _blank_pdf(),
        },
        {"knowledgeId": "knowledge-1"},
    )

    assert "## Page 1" in result["markdown"]
    assert result["assets"] == []
    assert rendered_pages == []
    assert runtime.calls == []


@pytest.mark.asyncio
async def test_text_only_deepseek_rejects_visual_ocr() -> None:
    """Verify DeepSeek text models fail explicitly instead of accepting image input."""
    runtime = _FakeVisualRuntime(model_name="deepseek-chat")
    converter = converter_module.KnowledgeAttachmentLlmConverter(runtime, timeout_seconds=30)

    with pytest.raises(
        converter_module.KnowledgeAttachmentConversionError,
        match="does not support visual input",
    ):
        await converter.convert(
            {
                "fileId": "image-1",
                "fileName": "diagram.png",
                "contentType": "image/png",
                "data": b"\x89PNG\r\n\x1a\nimage-data",
            },
            {"knowledgeId": "knowledge-1"},
        )

    assert runtime.calls == []


@pytest.mark.asyncio
async def test_pdf_page_limit_is_enforced_before_visual_conversion() -> None:
    """Verify a large page count cannot trigger unbounded rendering or model calls."""
    runtime = _FakeVisualRuntime()
    converter = converter_module.KnowledgeAttachmentLlmConverter(
        runtime,
        timeout_seconds=30,
        max_document_pages=1,
    )

    with pytest.raises(converter_module.KnowledgeAttachmentConversionError) as error:
        await converter.convert(
            {
                "fileId": "pdf-many",
                "fileName": "many-pages.pdf",
                "contentType": "application/pdf",
                "data": _multipage_pdf(2),
            },
            {"knowledgeId": "knowledge-1"},
        )

    assert error.value.status_code == 413
    assert error.value.code == "attachment_page_limit_exceeded"
    assert runtime.calls == []


@pytest.mark.asyncio
async def test_legacy_office_is_not_sent_to_libreoffice(monkeypatch) -> None:
    """Verify legacy OLE Office formats remain outside the M1 extraction boundary."""
    converter = converter_module.KnowledgeAttachmentLlmConverter(
        _FakeVisualRuntime(available=False),
        timeout_seconds=30,
    )
    office_calls: list[str] = []
    monkeypatch.setattr(
        converter,
        "_office_to_pdf",
        lambda file_name, data, timeout_seconds: office_calls.append(file_name),
    )

    with pytest.raises(
        converter_module.KnowledgeAttachmentConversionError,
        match="Unsupported attachment type",
    ):
        await converter.convert(
            {
                "fileId": "doc-legacy",
                "fileName": "legacy.doc",
                "contentType": "application/msword",
                "data": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1legacy-office",
            },
            {"knowledgeId": "knowledge-1"},
        )

    assert office_calls == []


@pytest.mark.asyncio
async def test_scanned_pdf_stops_before_visual_calls_exceed_asset_budget(monkeypatch) -> None:
    """Verify one scanned attachment cannot accumulate page assets beyond its byte budget."""
    runtime = _FakeVisualRuntime()
    converter = converter_module.KnowledgeAttachmentLlmConverter(
        runtime,
        timeout_seconds=30,
        max_rendered_page_bytes=8,
        max_rendered_document_bytes=10,
    )
    monkeypatch.setattr(
        converter,
        "_extract_pdf_pages",
        lambda pdf_data, timeout_seconds: [
            {
                "pageNumber": 1,
                "text": "",
                "width": 100,
                "height": 100,
                "hasRasterImage": True,
            },
            {
                "pageNumber": 2,
                "text": "",
                "width": 100,
                "height": 100,
                "hasRasterImage": True,
            },
            {
                "pageNumber": 3,
                "text": "",
                "width": 100,
                "height": 100,
                "hasRasterImage": True,
            },
        ],
    )
    rendered_pages: list[int] = []

    def render_page(pdf_data: bytes, page_number: int, timeout_seconds: float) -> bytes:
        rendered_pages.append(page_number)
        return b"123456"

    monkeypatch.setattr(converter, "_render_pdf_page", render_page)

    with pytest.raises(converter_module.KnowledgeAttachmentConversionError) as error:
        await converter.convert(
            {
                "fileId": "scan-budget",
                "fileName": "scan.pdf",
                "contentType": "application/pdf",
                "data": b"%PDF-budget",
            },
            {"knowledgeId": "knowledge-1"},
        )

    assert error.value.status_code == 413
    assert error.value.code == "generated_assets_too_large"
    assert rendered_pages == [1, 2]
    assert len(runtime.calls) == 1
