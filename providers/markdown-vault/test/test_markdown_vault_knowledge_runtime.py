"""Critical aggregate and failure-preservation tests for Knowledge REST storage."""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import importlib.util
import base64
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import sys
from types import ModuleType
import threading
import zipfile

import pytest
from PIL import Image


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
if str(PROVIDER_ROOT) not in sys.path:
    sys.path.insert(0, str(PROVIDER_ROOT))
_ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class FakeAttachmentConverter:
    """Stand in for the provider's local-text and visual-image attachment converter."""

    def __init__(self) -> None:
        self.file_names: list[str] = []

    async def convert(self, attachment: dict, context: dict) -> str | dict:
        """Return deterministic Markdown while converter tests verify extraction routing."""
        file_name = attachment["fileName"]
        self.file_names.append(file_name)
        markers = {
            "evidence.pdf": "## Page 1\n\nPDF_MARKER_7812",
            "evidence.docx": "# Word Evidence\n\nDOCX_MARKER_3491",
            "evidence.pptx": "## Slide 1\n\nPPTX_MARKER_5628",
            "legacy.doc": "# Legacy Word\n\nLEGACY_DOC_MARKER_7351",
            "diagram.png": "## Image\n\nIMAGE_MARKER_8834",
            "stable.docx": "# Stable\n\nSTABLE_DOCX_MARKER_7219",
        }
        assert context["knowledgeId"] == "knowledge-1"
        if file_name == "diagram.png":
            return {
                "markdown": markers[file_name],
                "assets": [
                    {
                        "fileName": "image.png",
                        "contentType": "image/png",
                        "data": _ONE_PIXEL_PNG,
                    }
                ],
            }
        return markers[file_name]


def _load_runtime() -> ModuleType:
    """Load the provider runtime exactly as AtlasClaw Core loads it."""
    package_name = "markdown_vault_knowledge_runtime_test"
    package = ModuleType(package_name)
    package.__path__ = [str(PROVIDER_ROOT)]  # type: ignore[attr-defined]
    sys.modules[package_name] = package
    runtime_path = PROVIDER_ROOT / "knowledge_runtime.py"
    module_name = f"{package_name}.knowledge_runtime"
    spec = importlib.util.spec_from_file_location(module_name, runtime_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_cancelled_external_lock_waiter_does_not_leak_descriptor(
    tmp_path: Path,
) -> None:
    """Verify cancelling a blocked request cannot permanently retain the Vault lock."""
    runtime = _load_runtime()
    vault = tmp_path / "vault"
    vault.mkdir()
    external_descriptor = os.open(
        vault / ".atlasclaw-knowledge.lock",
        os.O_CREAT | os.O_RDWR,
        0o600,
    )
    fcntl.flock(external_descriptor, fcntl.LOCK_EX)

    async def wait_for_lock() -> None:
        async with runtime._locked_vault(vault):
            pass

    waiter = asyncio.create_task(wait_for_lock())
    await asyncio.sleep(0.1)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    fcntl.flock(external_descriptor, fcntl.LOCK_UN)
    os.close(external_descriptor)

    async with asyncio.timeout(1):
        async with runtime._locked_vault(vault):
            pass


def _pdf_bytes(text: str) -> bytes:
    """Create a minimal PDF-shaped payload for the provider boundary test."""
    return f"%PDF-1.4\n% {text}\n%%EOF\n".encode()


def _docx_bytes(text: str) -> bytes:
    """Create the smallest safe DOCX-shaped OOXML archive accepted by the runtime."""
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", f"<document>{text}</document>")
    return output.getvalue()


def _pptx_bytes(text: str) -> bytes:
    """Create the smallest safe PPTX-shaped OOXML archive accepted by the runtime."""
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", f"<slide>{text}</slide>")
    return output.getvalue()


def _bmp_bytes() -> bytes:
    """Create a small valid BMP payload for provider boundary validation."""
    output = BytesIO()
    Image.new("RGB", (2, 2), color="white").save(output, format="BMP")
    return output.getvalue()


def test_bmp_is_accepted_at_provider_boundary() -> None:
    """Verify BMP extension, MIME type, and signature are accepted as an image."""
    runtime = _load_runtime()

    assert runtime._validate_file_type("diagram.bmp", "image/bmp", _bmp_bytes()) == "image"


def _attachment(file_id: str, file_name: str, content_type: str, data: bytes) -> tuple[dict, dict]:
    """Build matching manifest and multipart entries for one attachment."""
    part_name = f"attachment_{file_id}"
    manifest = {
        "fileId": file_id,
        "partName": part_name,
        "fileName": file_name,
        "contentType": content_type,
        "size": len(data),
        "checksum": f"sha256:{hashlib.sha256(data).hexdigest()}",
    }
    part = {
        "part_name": part_name,
        "filename": file_name,
        "content_type": content_type,
        "data": data,
    }
    return manifest, part


def _snapshot(
    attachments: list[dict],
    *,
    fingerprint: str,
    target_path: str | None = None,
) -> dict:
    """Build the stable SmartCMP metadata contract used by aggregate tests."""
    snapshot = {
        "sourceSystem": "smartcmp",
        "knowledgeId": "knowledge-1",
        "providerType": "markdown-vault",
        "providerInstance": "testVaultMD",
        "sourceFingerprint": fingerprint,
        "title": "Aggregate Knowledge",
        "group": {
            "categoryId": "group-1",
            "categoryName": "Operations",
            "pathIds": ["root", "group-1"],
            "pathNames": ["Root", "Operations"],
        },
        "attachments": attachments,
    }
    if target_path is not None:
        snapshot["targetPath"] = target_path
    return snapshot


@pytest.mark.asyncio
async def test_knowledge_aggregate_converts_all_files_and_supports_crud_query(
    tmp_path: Path,
) -> None:
    """Verify one aggregate is complete, searchable, replaceable, and deletable."""
    runtime = _load_runtime()
    vault = tmp_path / "vault"
    vault.mkdir()
    config = {"vault_path": str(vault), "instance_name": "testVaultMD", "max_file_bytes": 1048576}
    converter = FakeAttachmentConverter()
    raw_files = [
        ("pdf-1", "evidence.pdf", "application/pdf", _pdf_bytes("PDF_MARKER_7812")),
        (
            "docx-1",
            "evidence.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            _docx_bytes("DOCX_MARKER_3491"),
        ),
        (
            "pptx-1",
            "evidence.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            _pptx_bytes("PPTX_MARKER_5628"),
        ),
        ("image-1", "diagram.png", "image/png", _ONE_PIXEL_PNG),
    ]
    entries = [_attachment(*raw_file) for raw_file in raw_files]
    metadata = _snapshot(
        [manifest for manifest, _ in entries],
        fingerprint="sha256:version-1",
        target_path="teams/operations",
    )

    created = await runtime.create_document(
        config,
        metadata,
        b"BODY_MARKER_9043",
        [part for _, part in entries],
        converter,
    )

    assert created["created"] is True
    document_root = vault / "teams" / "operations" / "knowledge-1"
    assert (document_root / "index.md").is_file()
    for file_id, file_name, _, _ in raw_files:
        extension = Path(file_name).suffix
        assert (document_root / "attachments" / file_id / "content.md").is_file()
        assert (document_root / "attachments" / file_id / f"original{extension}").is_file()
        assert (document_root / "assets" / file_id).is_dir()
    assert (document_root / "assets" / "image-1" / "image.png").is_file()
    assert created["attachments"][-1]["assets"][0]["path"] == "assets/image-1/image.png"
    assert "tenantId" not in json.loads(
        (document_root / "manifest.json").read_text(encoding="utf-8")
    )

    for marker, expected_source in (
        ("PDF_MARKER_7812", "attachment"),
        ("DOCX_MARKER_3491", "attachment"),
        ("PPTX_MARKER_5628", "attachment"),
        ("IMAGE_MARKER_8834", "attachment"),
        ("BODY_MARKER_9043", "knowledge"),
    ):
        result = await runtime.query_documents(
            config,
            query=marker,
            keywords=[marker],
            limit=5,
        )
        assert result["result_count"] >= 1
        assert result["results"][0]["citation"]["sourceType"] == expected_source
        assert result["results"][0]["citation"]["knowledgeId"] == "knowledge-1"

    updated_metadata = _snapshot([], fingerprint="sha256:version-2")
    assert set(converter.file_names) == {
        "evidence.pdf",
        "evidence.docx",
        "evidence.pptx",
        "diagram.png",
    }

    await runtime.update_document(config, updated_metadata, b"BODY_MARKER_NEW_1188", [], None)
    assert not (document_root / "attachments" / "pdf-1").exists()
    assert (await runtime.query_documents(
        config,
        query="BODY_MARKER_NEW_1188",
        keywords=["BODY_MARKER_NEW_1188"],
        limit=5,
    ))["result_count"] >= 1
    assert (await runtime.query_documents(
        config,
        query="PDF_MARKER_7812",
        keywords=["PDF_MARKER_7812"],
        limit=5,
    ))["result_count"] == 0

    assert (await runtime.delete_document(config, "knowledge-1"))["deleted"] is True
    assert (await runtime.delete_document(config, "knowledge-1"))["deleted"] is False
    assert (await runtime.query_documents(
        config,
        query="BODY_MARKER_NEW_1188",
        keywords=["BODY_MARKER_NEW_1188"],
        limit=5,
    ))["result_count"] == 0


@pytest.mark.asyncio
async def test_unpublish_hides_content_and_republish_reuses_unchanged_attachment(
    tmp_path: Path,
) -> None:
    """Verify publication state controls search without repeating unchanged conversion."""
    runtime = _load_runtime()
    vault = tmp_path / "vault"
    vault.mkdir()
    config = {"vault_path": str(vault), "instance_name": "testVaultMD"}
    converter = FakeAttachmentConverter()
    data = _docx_bytes("STABLE_DOCX_MARKER_7219")
    manifest, part = _attachment(
        "docx-1",
        "stable.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        data,
    )
    await runtime.create_document(
        config,
        _snapshot([manifest], fingerprint="sha256:published", target_path="operations"),
        b"PUBLISHED_BODY_MARKER_8217",
        [part],
        converter,
    )

    unpublished = await runtime.unpublish_document(config, "knowledge-1")

    assert unpublished["publicationStatus"] == "UNPUBLISHED"
    assert converter.file_names == ["stable.docx"]
    from vault_runtime.config import build_markdown_vault_config
    from vault_runtime.parser import iter_markdown_files

    search_config = build_markdown_vault_config(
        raw_config={"vault_path": str(vault), "exclude_globs": "ordinary-never/**"},
        instance_name="testVaultMD",
        base_dir=tmp_path,
    )
    assert all(".atlasclaw-unpublished" not in path.parts for path in iter_markdown_files(search_config))
    assert (await runtime.query_documents(
        config,
        query="STABLE_DOCX_MARKER_7219",
        keywords=["STABLE_DOCX_MARKER_7219"],
        limit=5,
    ))["result_count"] == 0

    renamed_manifest = {**manifest, "fileName": "renamed.docx"}
    renamed_part = {**part, "fileName": "renamed.docx"}
    republished = await runtime.update_document(
        config,
        _snapshot([renamed_manifest], fingerprint="sha256:republished"),
        b"REPUBLISHED_BODY_MARKER_3374",
        [renamed_part],
        converter,
    )

    assert republished["publicationStatus"] == "PUBLISHED"
    assert republished["attachments"][0]["fileName"] == "renamed.docx"
    assert converter.file_names == ["stable.docx"]
    assert (await runtime.query_documents(
        config,
        query="REPUBLISHED_BODY_MARKER_3374",
        keywords=["REPUBLISHED_BODY_MARKER_3374"],
        limit=5,
    ))["result_count"] >= 1

    await runtime.unpublish_document(config, "knowledge-1")
    assert (await runtime.delete_document(config, "knowledge-1"))["deleted"] is True
    with pytest.raises(runtime.KnowledgeRuntimeError) as error:
        await runtime.get_document(config, "knowledge-1")
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_unpublish_rejects_symlinked_hidden_root(tmp_path: Path) -> None:
    """Verify unpublish cannot move a managed aggregate through a hidden-root symlink."""
    runtime = _load_runtime()
    vault = tmp_path / "vault"
    outside = tmp_path / "outside"
    vault.mkdir()
    outside.mkdir()
    config = {"vault_path": str(vault), "instance_name": "testVaultMD"}
    await runtime.create_document(
        config,
        _snapshot([], fingerprint="sha256:symlinked-unpublish-root"),
        b"PUBLISHED_PATH_SAFETY_MARKER_4197",
        [],
        None,
    )
    (vault / ".atlasclaw-unpublished").symlink_to(outside, target_is_directory=True)

    with pytest.raises(runtime.KnowledgeRuntimeError) as error:
        await runtime.unpublish_document(config, "knowledge-1")

    assert error.value.code == "unsafe_vault_entry"
    assert (vault / "knowledge-1" / "index.md").is_file()
    assert list(outside.iterdir()) == []


@pytest.mark.asyncio
async def test_delete_rejects_symlinked_hidden_root(tmp_path: Path) -> None:
    """Verify delete cannot remove a matching aggregate outside the configured Vault."""
    runtime = _load_runtime()
    vault = tmp_path / "vault"
    outside = tmp_path / "outside"
    vault.mkdir()
    outside.mkdir()
    config = {"vault_path": str(vault), "instance_name": "testVaultMD"}
    await runtime.create_document(
        config,
        _snapshot([], fingerprint="sha256:symlinked-delete-root"),
        b"DELETE_PATH_SAFETY_MARKER_6031",
        [],
        None,
    )
    shutil.copytree(vault / "knowledge-1", outside / "knowledge-1")
    (vault / ".atlasclaw-unpublished").symlink_to(outside, target_is_directory=True)

    with pytest.raises(runtime.KnowledgeRuntimeError) as error:
        await runtime.delete_document(config, "knowledge-1")

    assert error.value.code == "unsafe_vault_entry"
    assert (vault / "knowledge-1" / "index.md").is_file()
    assert (outside / "knowledge-1" / "index.md").is_file()


@pytest.mark.asyncio
async def test_bad_checksum_update_preserves_previous_snapshot(tmp_path: Path) -> None:
    """Verify validation failure cannot replace the last searchable version."""
    runtime = _load_runtime()
    vault = tmp_path / "vault"
    vault.mkdir()
    config = {"vault_path": str(vault), "instance_name": "testVaultMD"}
    converter = FakeAttachmentConverter()
    data = _docx_bytes("STABLE_DOCX_MARKER_7219")
    manifest, part = _attachment(
        "docx-1",
        "stable.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        data,
    )
    await runtime.create_document(
        config,
        _snapshot([manifest], fingerprint="sha256:stable"),
        b"STABLE_BODY_MARKER_4176",
        [part],
        converter,
    )
    document_root = vault / "knowledge-1"
    old_index = (document_root / "index.md").read_text(encoding="utf-8")
    bad_manifest = dict(manifest)
    bad_manifest["checksum"] = "sha256:" + ("0" * 64)

    with pytest.raises(runtime.KnowledgeRuntimeError) as error:
        await runtime.update_document(
            config,
            _snapshot([bad_manifest], fingerprint="sha256:bad"),
            b"BROKEN_NEW_BODY",
            [part],
            converter,
        )

    assert error.value.code == "checksum_mismatch"
    assert (document_root / "index.md").read_text(encoding="utf-8") == old_index
    result = await runtime.query_documents(
        config,
        query="STABLE_BODY_MARKER_4176",
        keywords=["STABLE_BODY_MARKER_4176"],
        limit=5,
    )
    assert result["result_count"] >= 1


@pytest.mark.asyncio
@pytest.mark.parametrize("target_path", ["/absolute/path", "../escape", "nested//empty"])
async def test_create_rejects_unsafe_target_path(tmp_path: Path, target_path: str) -> None:
    """Verify client-selected directories can never escape or ambiguously address the Vault."""
    runtime = _load_runtime()
    vault = tmp_path / "vault"
    vault.mkdir()

    with pytest.raises(runtime.KnowledgeRuntimeError) as error:
        await runtime.create_document(
            {"vault_path": str(vault), "instance_name": "testVaultMD"},
            _snapshot([], fingerprint="sha256:unsafe", target_path=target_path),
            b"SAFE_BODY",
            [],
            None,
        )

    assert error.value.code == "invalid_target_path"
    assert list(vault.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_field", ["files", "path"])
async def test_create_rejects_legacy_metadata_aliases(tmp_path: Path, legacy_field: str) -> None:
    """Verify the REST contract accepts only attachments and targetPath."""
    runtime = _load_runtime()
    vault = tmp_path / "vault"
    vault.mkdir()
    metadata = _snapshot([], fingerprint="sha256:canonical-only")
    metadata[legacy_field] = [] if legacy_field == "files" else "legacy/path"

    with pytest.raises(runtime.KnowledgeRuntimeError) as error:
        await runtime.create_document(
            {"vault_path": str(vault), "instance_name": "testVaultMD"},
            metadata,
            b"SAFE_BODY",
            [],
            None,
        )

    assert error.value.code == "invalid_metadata"
    assert list(vault.iterdir()) == []


@pytest.mark.asyncio
async def test_query_ignores_unmanaged_markdown_without_knowledge_manifest(tmp_path: Path) -> None:
    """Verify unmanaged Markdown is never admitted without a validated Knowledge manifest."""
    runtime = _load_runtime()
    vault = tmp_path / "vault"
    vault.mkdir()
    config = {"vault_path": str(vault), "instance_name": "testVaultMD"}
    await runtime.create_document(
        config,
        _snapshot([], fingerprint="sha256:managed"),
        b"MANAGED_MARKER_2391",
        [],
        None,
    )
    (vault / "forged.md").write_text(
        "---\ntags: []\n---\n\nFORGED_MARKER_9951\n",
        encoding="utf-8",
    )

    forged = await runtime.query_documents(
        config,
        query="FORGED_MARKER_9951",
        keywords=["FORGED_MARKER_9951"],
        limit=5,
    )
    managed = await runtime.query_documents(
        config,
        query="MANAGED_MARKER_2391",
        keywords=["MANAGED_MARKER_2391"],
        limit=5,
    )

    assert forged["result_count"] == 0
    assert managed["result_count"] == 1


@pytest.mark.asyncio
async def test_corrupt_manifest_is_not_reported_as_idempotent_delete(tmp_path: Path) -> None:
    """Verify a known but corrupt aggregate returns an integrity error and remains in place."""
    runtime = _load_runtime()
    vault = tmp_path / "vault"
    vault.mkdir()
    config = {"vault_path": str(vault), "instance_name": "testVaultMD"}
    await runtime.create_document(
        config,
        _snapshot([], fingerprint="sha256:corrupt"),
        b"CORRUPT_MANIFEST_MARKER_2217",
        [],
        None,
    )
    document_root = vault / "knowledge-1"
    (document_root / "manifest.json").write_text("{broken", encoding="utf-8")

    with pytest.raises(runtime.KnowledgeRuntimeError) as error:
        await runtime.delete_document(config, "knowledge-1")

    assert error.value.status_code == 500
    assert document_root.is_dir()


@pytest.mark.asyncio
async def test_delete_failure_is_returned_and_does_not_leave_a_searchable_tombstone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify filesystem deletion failure is not reported as a successful delete."""
    runtime = _load_runtime()
    vault = tmp_path / "vault"
    vault.mkdir()
    config = {"vault_path": str(vault), "instance_name": "testVaultMD"}
    await runtime.create_document(
        config,
        _snapshot([], fingerprint="sha256:delete-failure"),
        b"DELETE_FAILURE_MARKER_4491",
        [],
        None,
    )
    document_root = vault / "knowledge-1"
    real_rmtree = runtime.shutil.rmtree

    def fail_document_delete(path: Path, *args, **kwargs) -> None:
        if Path(path) == document_root:
            raise OSError("injected delete failure")
        real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(runtime.shutil, "rmtree", fail_document_delete)

    with pytest.raises(OSError, match="injected delete failure"):
        await runtime.delete_document(config, "knowledge-1")

    assert document_root.is_dir()
    assert not list(vault.glob(".knowledge-1.deleted-*"))


@pytest.mark.asyncio
async def test_create_rejects_generated_markdown_excluded_from_search(tmp_path: Path) -> None:
    """Verify a REST success cannot produce a snapshot hidden by scan policy."""
    runtime = _load_runtime()
    vault = tmp_path / "vault"
    vault.mkdir()
    config = {
        "vault_path": str(vault),
        "instance_name": "testVaultMD",
        "exclude_globs": "blocked/**",
    }

    with pytest.raises(runtime.KnowledgeRuntimeError) as error:
        await runtime.create_document(
            config,
            _snapshot([], fingerprint="sha256:excluded", target_path="blocked"),
            b"EXCLUDED_MARKER_7814",
            [],
            None,
        )

    assert error.value.code == "knowledge_path_not_searchable"
    assert not (vault / "blocked" / "knowledge-1").exists()


@pytest.mark.asyncio
async def test_get_rejects_symlinked_index_file(tmp_path: Path) -> None:
    """Verify REST reads cannot follow a managed Markdown path outside the Vault."""
    runtime = _load_runtime()
    vault = tmp_path / "vault"
    vault.mkdir()
    config = {"vault_path": str(vault), "instance_name": "testVaultMD"}
    await runtime.create_document(
        config,
        _snapshot([], fingerprint="sha256:symlink"),
        b"SAFE_INDEX_MARKER_6642",
        [],
        None,
    )
    document_root = vault / "knowledge-1"
    external = tmp_path / "outside.md"
    external.write_text("OUTSIDE_SECRET_8134", encoding="utf-8")
    (document_root / "index.md").unlink()
    (document_root / "index.md").symlink_to(external)

    with pytest.raises(runtime.KnowledgeRuntimeError) as error:
        await runtime.get_document(config, "knowledge-1")

    assert error.value.code == "unsafe_vault_entry"


@pytest.mark.asyncio
async def test_create_accepts_legacy_office_for_optional_conversion(tmp_path: Path) -> None:
    """Verify a valid legacy OLE file reaches the optional document converter."""
    runtime = _load_runtime()
    vault = tmp_path / "vault"
    vault.mkdir()
    data = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1legacy-office"
    manifest, part = _attachment("doc-legacy", "legacy.doc", "application/msword", data)

    await runtime.create_document(
        {"vault_path": str(vault), "instance_name": "testVaultMD"},
        _snapshot([manifest], fingerprint="sha256:legacy"),
        b"SAFE_BODY",
        [part],
        FakeAttachmentConverter(),
    )

    assert "LEGACY_DOC_MARKER_7351" in (
        vault / "knowledge-1" / "attachments" / "doc-legacy" / "content.md"
    ).read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_recovery_ignores_similarly_named_user_directory(tmp_path: Path) -> None:
    """Verify recovery never applies filename patterns to ordinary Vault directories."""
    runtime = _load_runtime()
    vault = tmp_path / "vault"
    vault.mkdir()
    ordinary = vault / ".notes.previous-archive"
    ordinary.mkdir()
    (ordinary / "notes.md").write_text("USER_CONTENT_MARKER_8182", encoding="utf-8")

    await runtime.create_document(
        {"vault_path": str(vault), "instance_name": "testVaultMD"},
        _snapshot([], fingerprint="sha256:ordinary-directory"),
        b"SAFE_BODY",
        [],
        None,
    )

    assert (ordinary / "notes.md").read_text(encoding="utf-8") == "USER_CONTENT_MARKER_8182"


@pytest.mark.asyncio
async def test_aggregate_conversion_uses_one_shared_deadline(tmp_path: Path) -> None:
    """Verify sequential attachments cannot each consume the full configured timeout."""
    runtime = _load_runtime()
    vault = tmp_path / "vault"
    vault.mkdir()

    class SlowConverter:
        """Delay each conversion long enough for only the aggregate deadline to catch it."""

        async def convert(self, attachment: dict, context: dict) -> str:
            """Return Markdown after a deterministic delay."""
            await asyncio.sleep(0.6)
            return f"# {attachment['fileName']}"

    first = _attachment(
        "docx-1",
        "first.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        _docx_bytes("first"),
    )
    second = _attachment(
        "docx-2",
        "second.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        _docx_bytes("second"),
    )

    with pytest.raises(runtime.KnowledgeRuntimeError) as error:
        await runtime.create_document(
            {
                "vault_path": str(vault),
                "instance_name": "testVaultMD",
                "conversion_timeout_seconds": 1,
            },
            _snapshot([first[0], second[0]], fingerprint="sha256:aggregate-timeout"),
            b"SAFE_BODY",
            [first[1], second[1]],
            SlowConverter(),
        )

    assert error.value.status_code == 504
    assert error.value.code == "attachment_conversion_timeout"
    assert not (vault / "knowledge-1").exists()


@pytest.mark.asyncio
async def test_recovery_discards_pre_exchange_transactions_without_valid_marker(
    tmp_path: Path,
) -> None:
    """Verify a crash before marker publication cannot block later REST operations."""
    runtime = _load_runtime()
    vault = tmp_path / "vault"
    vault.mkdir()
    transaction_root = vault / ".atlasclaw-transactions"
    missing_marker = transaction_root / ("a" * 32)
    truncated_marker = transaction_root / ("b" * 32)
    (missing_marker / "incoming").mkdir(parents=True)
    (truncated_marker / "incoming").mkdir(parents=True)
    (truncated_marker / "transaction.json").write_text("{", encoding="utf-8")

    await runtime.create_document(
        {"vault_path": str(vault), "instance_name": "testVaultMD"},
        _snapshot([], fingerprint="sha256:recover-abandoned"),
        b"SAFE_BODY",
        [],
        None,
    )

    assert not missing_marker.exists()
    assert not truncated_marker.exists()
    assert (vault / "knowledge-1" / "index.md").is_file()


@pytest.mark.asyncio
async def test_chat_lock_recovers_swap_gap_and_parser_hard_excludes_transactions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Verify first Chat read restores the old snapshot and cannot scan transaction Markdown."""
    runtime = _load_runtime()
    vault = tmp_path / "vault"
    vault.mkdir()
    config = {"vault_path": str(vault), "instance_name": "testVaultMD"}
    await runtime.create_document(
        config,
        _snapshot([], fingerprint="sha256:chat-recovery"),
        b"CHAT_RECOVERY_MARKER_4418",
        [],
        None,
    )
    target = vault / "knowledge-1"
    transaction_id = "c" * 32
    transaction = vault / ".atlasclaw-transactions" / transaction_id
    transaction.mkdir(parents=True)
    previous_state = runtime._snapshot_state(target)
    marker = {
        "transactionId": transaction_id,
        "targetRelative": "knowledge-1",
        "knowledgeId": "knowledge-1",
        "targetPath": "",
        "hadTarget": True,
        "previousState": previous_state,
        "newSourceFingerprint": "sha256:not-installed",
        "phase": "PREPARED",
    }
    (transaction / "transaction.json").write_text(json.dumps(marker), encoding="utf-8")
    os.replace(target, transaction / "previous")

    scripts_path = PROVIDER_ROOT / "skills" / "markdown-vault-query" / "scripts"
    monkeypatch.syspath_prepend(str(scripts_path))
    from vault_runtime.config import build_markdown_vault_config
    from vault_runtime.parser import VaultPathError, iter_markdown_files, read_markdown_lines
    from vault_runtime.vault_io import vault_read_lock

    with vault_read_lock(vault):
        assert (target / "index.md").is_file()
    assert not transaction.exists()

    internal_markdown = (
        vault
        / ".atlasclaw-transactions"
        / "operator-notes"
        / "incoming"
        / "secret.md"
    )
    internal_markdown.parent.mkdir(parents=True)
    internal_markdown.write_text("INTERNAL_TRANSACTION_SECRET_9921", encoding="utf-8")
    search_config = build_markdown_vault_config(
        raw_config={
            "vault_path": str(vault),
            "include_globs": "**/*.md",
            "exclude_globs": "ordinary-never/**",
        },
        instance_name="testVaultMD",
        base_dir=tmp_path,
    )

    assert internal_markdown not in iter_markdown_files(search_config)
    with pytest.raises(VaultPathError, match="transaction"):
        read_markdown_lines(
            search_config,
            ".atlasclaw-transactions/operator-notes/incoming/secret.md",
        )


@pytest.mark.asyncio
async def test_update_fsync_failure_restores_previous_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Verify a post-install durability failure cannot publish new data or delete the backup."""
    runtime = _load_runtime()
    vault = tmp_path / "vault"
    vault.mkdir()
    config = {"vault_path": str(vault), "instance_name": "testVaultMD"}
    original_metadata = _snapshot([], fingerprint="sha256:fsync-old")
    await runtime.create_document(config, original_metadata, b"FSYNC_OLD_MARKER_1127", [], None)

    real_fsync_directory = runtime._fsync_directory
    vault_fsync_calls = 0

    def fail_after_new_install(path: Path) -> None:
        nonlocal vault_fsync_calls
        if path == vault:
            vault_fsync_calls += 1
            if vault_fsync_calls >= 3:
                raise OSError("injected target parent fsync failure")
        real_fsync_directory(path)

    monkeypatch.setattr(runtime, "_fsync_directory", fail_after_new_install)
    updated_metadata = _snapshot([], fingerprint="sha256:fsync-new")

    with pytest.raises(OSError, match="injected"):
        await runtime.update_document(config, updated_metadata, b"FSYNC_NEW_MARKER_8841", [], None)

    current = await runtime.get_document(config, "knowledge-1")
    assert "FSYNC_OLD_MARKER_1127" in current["content"]
    assert "FSYNC_NEW_MARKER_8841" not in current["content"]
    assert not any((vault / ".atlasclaw-transactions").iterdir())


@pytest.mark.asyncio
async def test_create_preserves_target_that_appears_during_conversion(tmp_path: Path) -> None:
    """Verify Create returns conflict without replacing external content created mid-conversion."""
    runtime = _load_runtime()
    vault = tmp_path / "vault"
    vault.mkdir()
    data = _docx_bytes("race")
    manifest, part = _attachment(
        "docx-race",
        "race.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        data,
    )

    class TargetCreatingConverter:
        """Simulate an external process creating the target while conversion runs."""

        async def convert(self, attachment: dict, context: dict) -> str:
            """Create external content and return otherwise valid Markdown."""
            external_target = vault / "knowledge-1"
            external_target.mkdir()
            (external_target / "external.txt").write_text("EXTERNAL_CONTENT_9912", encoding="utf-8")
            return "# Converted"

    with pytest.raises(runtime.KnowledgeRuntimeError) as error:
        await runtime.create_document(
            {"vault_path": str(vault), "instance_name": "testVaultMD"},
            _snapshot([manifest], fingerprint="sha256:create-race"),
            b"SAFE_BODY",
            [part],
            TargetCreatingConverter(),
        )

    assert error.value.status_code == 409
    assert (vault / "knowledge-1" / "external.txt").read_text(encoding="utf-8") == "EXTERNAL_CONTENT_9912"


def test_vault_read_lock_allows_concurrent_readers(tmp_path: Path, monkeypatch) -> None:
    """Verify the normal no-recovery path keeps two Chat readers under compatible SH locks."""
    vault = tmp_path / "vault"
    vault.mkdir()
    scripts_path = PROVIDER_ROOT / "skills" / "markdown-vault-query" / "scripts"
    monkeypatch.syspath_prepend(str(scripts_path))
    from vault_runtime.vault_io import vault_read_lock

    first_entered = threading.Event()
    second_entered = threading.Event()
    release_readers = threading.Event()
    errors: list[BaseException] = []

    def first_reader() -> None:
        try:
            with vault_read_lock(vault):
                first_entered.set()
                release_readers.wait(2)
        except BaseException as exc:
            errors.append(exc)

    def second_reader() -> None:
        try:
            first_entered.wait(2)
            with vault_read_lock(vault):
                second_entered.set()
                release_readers.wait(2)
        except BaseException as exc:
            errors.append(exc)

    first = threading.Thread(target=first_reader)
    second = threading.Thread(target=second_reader)
    first.start()
    second.start()
    try:
        assert first_entered.wait(1)
        assert second_entered.wait(1)
    finally:
        release_readers.set()
        first.join(2)
        second.join(2)

    assert errors == []
