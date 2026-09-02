"""Synchronous Knowledge aggregate runtime owned by the Markdown Vault provider."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import fcntl
import hashlib
import io
import json
import logging
import os
from pathlib import Path, PurePosixPath
import re
import shutil
from typing import Any
import zipfile
from uuid import uuid4

import yaml

from .vault_runtime.config import build_markdown_vault_config
from .vault_runtime.direct_search import count_search_work_units, search_direct
from .vault_runtime.parser import _matches_glob
from .vault_runtime.vault_io import (
    TRANSACTION_DIR_NAME as _TRANSACTION_DIR_NAME,
    UNPUBLISHED_DIR_NAME as _UNPUBLISHED_DIR_NAME,
    VaultTransactionError,
    contains_symlink as _contains_symlink,
    fsync_directory as _fsync_directory,
    normalize_identifier,
    normalize_target_path,
    recover_vault_transactions,
)


PROVIDER_TYPE = "markdown-vault"
RUNTIME_CAPABILITIES = frozenset({"knowledge_read", "knowledge_write", "knowledge_query"})
_SHA256 = re.compile(r"^(?:sha256:)?([0-9a-fA-F]{64})$")
_ATTACHMENT_CONVERSION_VERSION = 2
_MAX_SEARCH_WORK_UNITS = 256
_VAULT_LOCKS: dict[Path, asyncio.Lock] = {}
logger = logging.getLogger(__name__)


class KnowledgeRuntimeError(ValueError):
    """Represent a safe provider-domain failure for Core's generic error mapper.

    The runtime raises this type for validation, authorization-adjacent provider
    rules, path safety, limits, and storage integrity. Its detail must not disclose
    original attachment bytes, credentials, or unrestricted filesystem paths.
    """

    def __init__(self, status_code: int, code: str, detail: str) -> None:
        """Create a provider error with the HTTP status and safe API error code."""
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail


def _vault_lock(vault_path: Path) -> asyncio.Lock:
    """Return the process-wide lock that serializes one Vault's REST snapshots."""
    resolved = vault_path.resolve()
    lock = _VAULT_LOCKS.get(resolved)
    if lock is None:
        lock = asyncio.Lock()
        _VAULT_LOCKS[resolved] = lock
    return lock


@asynccontextmanager
async def _locked_vault(vault_path: Path):
    """Serialize REST snapshots across tasks and Agent worker processes."""
    async with _vault_lock(vault_path):
        descriptor = await _acquire_vault_file_lock(vault_path)
        try:
            yield
        finally:
            _release_vault_file_lock(descriptor)


async def _acquire_vault_file_lock(vault_path: Path) -> int:
    """Acquire the cross-process lock without leaking it when the waiter is cancelled."""
    descriptor = os.open(
        vault_path / ".atlasclaw-knowledge.lock",
        os.O_CREAT | os.O_RDWR,
        0o600,
    )
    try:
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return descriptor
            except BlockingIOError:
                await asyncio.sleep(0.05)
    except BaseException:
        os.close(descriptor)
        raise


def _release_vault_file_lock(descriptor: int) -> None:
    """Release and close one advisory Vault lock descriptor."""
    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


async def create_document(
    config: dict[str, Any],
    metadata: dict[str, Any],
    content: bytes,
    attachments: list[dict[str, Any]],
    converter: Any,
) -> dict[str, Any]:
    """Create one validated Knowledge aggregate and make it searchable.

    Args:
        config: Resolved Markdown Vault instance configuration; ``vault_path`` is
            the trusted filesystem boundary.
        metadata: Complete Knowledge metadata including stable identity, target
            path, source fingerprint, tenant, and attachment declarations.
        content: UTF-8 Knowledge body supplied by the provider HTTP layer.
        attachments: Binary parts matched one-to-one with metadata declarations.
        converter: Attachment converter required when non-text content is present;
            callers may pass ``None`` when there are no attachments.

    Returns:
        Safe aggregate metadata and generated Markdown with ``created=True``.

    Raises:
        KnowledgeRuntimeError: If validation, path safety, conversion, storage, or
            uniqueness checks fail. Failed creation does not publish a partial target.
    """
    validated = _validate_snapshot(config, metadata, content, attachments)
    async with _locked_vault(validated["vault_path"]):
        _recover_interrupted_transactions(validated["vault_path"])
        existing = _find_document_path(
            validated["vault_path"],
            metadata["knowledgeId"],
        )
        if existing is not None:
            raise KnowledgeRuntimeError(409, "knowledge_exists", "Knowledge document already exists")
        if _find_unpublished_path(validated["vault_path"], metadata["knowledgeId"]) is not None:
            raise KnowledgeRuntimeError(
                409,
                "knowledge_unpublished",
                "Knowledge document is unpublished; use update to publish it again",
            )
        target = _new_document_path(
            validated["vault_path"],
            metadata["targetPath"],
            metadata["knowledgeId"],
        )
        if target.exists():
            raise KnowledgeRuntimeError(409, "knowledge_path_exists", "Target Knowledge path already exists")
        await _build_and_replace(
            target,
            metadata,
            validated["content_text"],
            validated["attachments"],
            config,
            converter,
        )
        return _document_response(target, created=True)


async def update_document(
    config: dict[str, Any],
    metadata: dict[str, Any],
    content: bytes,
    attachments: list[dict[str, Any]],
    converter: Any,
) -> dict[str, Any]:
    """Replace an existing published or unpublished aggregate with a full snapshot.

    Args:
        config: Resolved Vault instance configuration and filesystem boundary.
        metadata: Complete replacement metadata; ``knowledgeId`` and the existing
            ``targetPath`` remain immutable.
        content: UTF-8 replacement body.
        attachments: Complete replacement binary set, not a partial patch.
        converter: Attachment converter, or ``None`` when no conversion is needed.

    Returns:
        Safe metadata and generated Markdown for the newly published snapshot.

    Raises:
        KnowledgeRuntimeError: If the aggregate is missing, metadata is invalid,
            the target path changes, conversion fails, or the filesystem swap fails.
    """
    validated = _validate_snapshot(config, metadata, content, attachments)
    async with _locked_vault(validated["vault_path"]):
        _recover_interrupted_transactions(validated["vault_path"])
        current = _find_document_path(
            validated["vault_path"],
            metadata["knowledgeId"],
        )
        unpublished = None
        if current is None:
            unpublished = _find_unpublished_path(
                validated["vault_path"],
                metadata["knowledgeId"],
            )
            current = unpublished
        if current is None:
            raise KnowledgeRuntimeError(404, "knowledge_not_found", "Knowledge document was not found")
        current_manifest = _read_manifest(current)
        current_target_path = str(current_manifest.get("targetPath") or "")
        requested_target_path = str(metadata.get("targetPath") or "")
        if requested_target_path and requested_target_path != current_target_path:
            raise KnowledgeRuntimeError(
                422,
                "knowledge_path_immutable",
                "targetPath cannot be changed by Knowledge update",
            )
        metadata["targetPath"] = current_target_path
        target = _new_document_path(
            validated["vault_path"],
            current_target_path,
            metadata["knowledgeId"],
        )
        await _build_and_replace(
            target,
            metadata,
            validated["content_text"],
            validated["attachments"],
            config,
            converter,
            reuse_source=current,
        )
        if unpublished is not None:
            _remove_document_path(unpublished, stop=validated["vault_path"])
        return _document_response(target, created=False)


async def get_document(config: dict[str, Any], knowledge_id: str) -> dict[str, Any]:
    """Read one published or unpublished Knowledge aggregate by stable identity.

    Args:
        config: Resolved Vault instance configuration and filesystem boundary.
        knowledge_id: Provider-owned stable aggregate identifier.

    Returns:
        Safe manifest fields and generated Markdown; original attachment binaries
        and internal transaction state are never returned.

    Raises:
        KnowledgeRuntimeError: If the identifier is invalid, the aggregate is absent,
            or managed paths/manifests fail integrity and symlink checks.
    """
    vault_path = _vault_path(config)
    async with _locked_vault(vault_path):
        _recover_interrupted_transactions(vault_path)
        target = _find_document_path(vault_path, knowledge_id)
        if target is None:
            target = _find_unpublished_path(vault_path, knowledge_id)
        if target is None:
            raise KnowledgeRuntimeError(404, "knowledge_not_found", "Knowledge document was not found")
        return _document_response(target, created=False)


async def unpublish_document(config: dict[str, Any], knowledge_id: str) -> dict[str, Any]:
    """Hide an aggregate from search while retaining its converted snapshot.

    Args:
        config: Resolved Vault instance configuration and filesystem boundary.
        knowledge_id: Stable identifier of the aggregate to hide.

    Returns:
        The retained aggregate with ``publicationStatus='UNPUBLISHED'``. Repeating
        the operation returns the existing unpublished representation.

    Raises:
        KnowledgeRuntimeError: If the identifier is invalid, no aggregate exists,
            or the provider-owned hidden path is unsafe or cannot be updated.

    Side Effects:
        Moves a published aggregate under ``.atlasclaw-unpublished`` so normal Vault
        scanning excludes it while update, get, and delete can still address it.
    """
    vault_path = _vault_path(config)
    normalized_id = _identifier(knowledge_id, "knowledgeId")
    async with _locked_vault(vault_path):
        _recover_interrupted_transactions(vault_path)
        target = _find_document_path(vault_path, normalized_id)
        unpublished = _find_unpublished_path(vault_path, normalized_id)
        if target is None:
            if unpublished is None:
                raise KnowledgeRuntimeError(404, "knowledge_not_found", "Knowledge document was not found")
            return _document_response(unpublished, created=False)
        if unpublished is not None:
            _remove_document_path(unpublished, stop=vault_path)
        unpublished_root = _validated_unpublished_root(vault_path, create=True)
        unpublished = unpublished_root / normalized_id
        if _contains_symlink(vault_path, unpublished):
            raise KnowledgeRuntimeError(
                500,
                "unsafe_vault_entry",
                "Unpublished Knowledge path is unsafe",
            )
        os.replace(target, unpublished)
        _fsync_directory(unpublished_root)
        _fsync_directory(target.parent)
        manifest = _read_manifest(unpublished)
        manifest["publicationStatus"] = "UNPUBLISHED"
        _write_manifest(unpublished, manifest)
        _prune_empty_parent(target.parent, stop=vault_path)
        return _document_response(unpublished, created=False)


async def delete_document(config: dict[str, Any], knowledge_id: str) -> dict[str, Any]:
    """Delete published and unpublished representations of one aggregate.

    Args:
        config: Resolved Vault instance configuration and filesystem boundary.
        knowledge_id: Stable identifier whose managed representations are removed.

    Returns:
        ``success=True`` and whether any representation existed. Repeated deletion
        is idempotent and reports ``deleted=False``.

    Raises:
        KnowledgeRuntimeError: If the identifier or a managed path is unsafe.
        OSError: If filesystem removal begins but cannot complete; callers receive
            the provider's mapped storage failure rather than a false success.
    """
    vault_path = _vault_path(config)
    async with _locked_vault(vault_path):
        _recover_interrupted_transactions(vault_path)
        targets = [
            target
            for target in (
                _find_document_path(vault_path, knowledge_id),
                _find_unpublished_path(vault_path, knowledge_id),
            )
            if target is not None
        ]
        existed = bool(targets)
        for target in targets:
            _remove_document_path(target, stop=vault_path)
        return {
            "success": True,
            "deleted": existed,
            "knowledgeId": _identifier(knowledge_id, "knowledgeId"),
        }


async def query_documents(
    config: dict[str, Any],
    *,
    query: str,
    keywords: list[str],
    limit: int,
    knowledge_id: str | None = None,
) -> dict[str, Any]:
    """Search published body and attachment Markdown under a bounded work budget.

    Args:
        config: Resolved Vault instance configuration and filesystem boundary.
        query: Free-text query already bounded by the HTTP contract.
        keywords: Optional terms combined with the query for direct Vault search.
        limit: Maximum result count accepted by the provider query contract.
        knowledge_id: Optional parent aggregate filter.

    Returns:
        Ranked snippets with citations that identify the parent Knowledge aggregate
        and, when applicable, the converted attachment and page/slide location.

    Raises:
        KnowledgeRuntimeError: If inputs exceed the work budget, managed content is
            unsafe, or the search/index contract fails.
    """
    _validate_search_work_budget(query, keywords)
    vault_path = _vault_path(config)
    async with _locked_vault(vault_path):
        _recover_interrupted_transactions(vault_path)
        return await _query_documents_locked(
            config,
            query=query,
            keywords=keywords,
            limit=limit,
            knowledge_id=knowledge_id,
        )


async def _query_documents_locked(
    config: dict[str, Any],
    *,
    query: str,
    keywords: list[str],
    limit: int,
    knowledge_id: str | None,
) -> dict[str, Any]:
    """Run a managed Knowledge query while the Vault snapshot is stable."""
    normalized_query = str(query or "").strip()
    if not normalized_query and not keywords:
        raise KnowledgeRuntimeError(422, "invalid_query", "query or keywords must be provided")
    normalized_knowledge = _identifier(knowledge_id, "knowledgeId") if knowledge_id else ""
    safe_limit = min(max(int(limit), 1), 50)
    search_config = build_markdown_vault_config(
        raw_config=config,
        instance_name=str(config.get("instance_name") or "default"),
        base_dir=Path.cwd(),
        provider_type=PROVIDER_TYPE,
    )
    managed_paths: list[Path]
    if normalized_knowledge:
        target = _find_document_path(search_config.vault_path, normalized_knowledge)
        if target is None:
            return {
                "success": True,
                "search_backend": "direct",
                "result_count": 0,
                "results": [],
                "providerType": PROVIDER_TYPE,
                "providerInstance": str(config.get("instance_name") or "default"),
            }
        managed_paths = [target]
    else:
        managed_paths = _find_document_paths(search_config.vault_path)
    if not managed_paths:
        return {
            "success": True,
            "search_backend": "direct",
            "result_count": 0,
            "results": [],
            "providerType": PROVIDER_TYPE,
            "providerInstance": str(config.get("instance_name") or "default"),
        }
    allowed_prefixes = [
        path.relative_to(search_config.vault_path).as_posix() for path in managed_paths
    ]
    result = await asyncio.to_thread(
        search_direct,
        search_config,
        normalized_query,
        keywords=[str(item).strip() for item in keywords if str(item).strip()],
        limit=safe_limit,
        path_filter=None,
        tag_filter=None,
        allowed_path_prefixes=allowed_prefixes,
    )
    verified_results: list[dict[str, Any]] = []
    for item in result.get("results", []):
        if not isinstance(item, dict):
            continue
        citation = _citation_for_result(search_config.vault_path, item)
        if citation is None:
            continue
        if normalized_knowledge and citation.get("knowledgeId") != normalized_knowledge:
            continue
        item["citation"] = citation
        verified_results.append(item)
    result["results"] = verified_results[:safe_limit]
    result["result_count"] = len(result["results"])
    result.update(
        {
            "providerType": PROVIDER_TYPE,
            "providerInstance": str(config.get("instance_name") or "default"),
        }
    )
    return result


def _validate_search_work_budget(query: str, keywords: list[str]) -> None:
    """Reject normalized term expansion before acquiring the exclusive Vault lock."""
    work_units = int(count_search_work_units(str(query or ""), keywords))
    if work_units > _MAX_SEARCH_WORK_UNITS:
        raise KnowledgeRuntimeError(
            422,
            "invalid_query",
            f"query exceeds {_MAX_SEARCH_WORK_UNITS} search scoring units",
        )


def _validate_snapshot(
    config: dict[str, Any],
    metadata: dict[str, Any],
    content: bytes,
    attachment_parts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate aggregate identity, multipart integrity, checksums, and file safety."""
    if not isinstance(metadata, dict):
        raise KnowledgeRuntimeError(422, "invalid_metadata", "metadata must be a JSON object")
    if "files" in metadata or "path" in metadata:
        raise KnowledgeRuntimeError(
            422,
            "invalid_metadata",
            "Use the canonical attachments and targetPath fields",
        )
    if str(metadata.get("sourceSystem") or "").strip().lower() != "smartcmp":
        raise KnowledgeRuntimeError(422, "invalid_source", "sourceSystem must be smartcmp")
    if str(metadata.get("providerType") or "").strip().lower() != PROVIDER_TYPE:
        raise KnowledgeRuntimeError(422, "invalid_provider", "providerType must be markdown-vault")

    knowledge_id = _identifier(metadata.get("knowledgeId"), "knowledgeId")
    title = str(metadata.get("title") or "").strip()
    if not title:
        raise KnowledgeRuntimeError(422, "invalid_metadata", "title is required")
    if len(title) > 500:
        raise KnowledgeRuntimeError(422, "invalid_metadata", "title exceeds 500 characters")
    fingerprint = str(metadata.get("sourceFingerprint") or "").strip()
    if not fingerprint:
        raise KnowledgeRuntimeError(422, "invalid_metadata", "sourceFingerprint is required")

    try:
        content_text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise KnowledgeRuntimeError(422, "invalid_content", "content must be UTF-8 Markdown") from exc
    max_content_bytes = _positive_int(config.get("max_file_bytes"), 1048576, "max_file_bytes")
    if len(content) > max_content_bytes:
        raise KnowledgeRuntimeError(413, "content_too_large", "Knowledge Markdown exceeds max_file_bytes")

    manifest_items = metadata.get("attachments", [])
    if not isinstance(manifest_items, list):
        raise KnowledgeRuntimeError(422, "invalid_manifest", "attachments must be a list")
    max_attachments = _positive_int(config.get("max_attachments"), 20, "max_attachments")
    if len(manifest_items) > max_attachments:
        raise KnowledgeRuntimeError(413, "too_many_attachments", "Attachment count exceeds max_attachments")

    parts_by_name: dict[str, dict[str, Any]] = {}
    for part in attachment_parts:
        part_name = str(part.get("part_name") or "").strip()
        if not part_name or part_name in parts_by_name:
            raise KnowledgeRuntimeError(422, "invalid_multipart", "Attachment part names must be unique")
        parts_by_name[part_name] = part

    validated_attachments: list[dict[str, Any]] = []
    expected_names: set[str] = set()
    total_bytes = 0
    max_attachment_bytes = _positive_int(
        config.get("max_attachment_bytes"), 25 * 1024 * 1024, "max_attachment_bytes"
    )
    max_total_bytes = _positive_int(
        config.get("max_total_attachment_bytes"), 100 * 1024 * 1024, "max_total_attachment_bytes"
    )
    for raw_item in manifest_items:
        if not isinstance(raw_item, dict):
            raise KnowledgeRuntimeError(422, "invalid_manifest", "Attachment entries must be objects")
        file_id = _identifier(raw_item.get("fileId"), "fileId")
        part_name = str(raw_item.get("partName") or "").strip()
        if part_name != f"attachment_{file_id}":
            raise KnowledgeRuntimeError(
                422,
                "invalid_manifest",
                f"Attachment {file_id} must use partName attachment_{file_id}",
            )
        if part_name in expected_names:
            raise KnowledgeRuntimeError(422, "invalid_manifest", f"Duplicate attachment {file_id}")
        expected_names.add(part_name)
        part = parts_by_name.get(part_name)
        if part is None:
            raise KnowledgeRuntimeError(422, "missing_attachment", f"Missing multipart part {part_name}")
        data = part.get("data")
        if not isinstance(data, bytes):
            raise KnowledgeRuntimeError(422, "invalid_multipart", f"Part {part_name} is not a file")
        declared_size = raw_item.get("size")
        if not isinstance(declared_size, int) or declared_size != len(data):
            raise KnowledgeRuntimeError(422, "size_mismatch", f"Attachment size mismatch for {file_id}")
        if len(data) > max_attachment_bytes:
            raise KnowledgeRuntimeError(413, "attachment_too_large", f"Attachment {file_id} is too large")
        total_bytes += len(data)
        if total_bytes > max_total_bytes:
            raise KnowledgeRuntimeError(413, "attachments_too_large", "Total attachment size exceeds limit")
        checksum = _checksum(raw_item.get("checksum"), file_id)
        actual_checksum = hashlib.sha256(data).hexdigest()
        if checksum.lower() != actual_checksum.lower():
            raise KnowledgeRuntimeError(422, "checksum_mismatch", f"Attachment checksum mismatch for {file_id}")

        file_name = _safe_file_name(raw_item.get("fileName"), file_id)
        content_type = str(raw_item.get("contentType") or part.get("content_type") or "").strip().lower()
        if str(part.get("content_type") or "").strip().lower() not in {"", content_type}:
            raise KnowledgeRuntimeError(422, "content_type_mismatch", f"Content type mismatch for {file_id}")
        file_kind = _validate_file_type(file_name, content_type, data)
        validated_attachments.append(
            {
                **raw_item,
                "fileId": file_id,
                "partName": part_name,
                "fileName": file_name,
                "contentType": content_type,
                "size": len(data),
                "checksum": f"sha256:{actual_checksum}",
                "kind": file_kind,
                "data": data,
            }
        )

    extras = sorted(set(parts_by_name) - expected_names)
    if extras:
        raise KnowledgeRuntimeError(422, "unexpected_attachment", f"Unexpected attachment parts: {', '.join(extras)}")

    metadata["knowledgeId"] = knowledge_id
    metadata["title"] = title
    metadata["targetPath"] = _target_path(metadata.get("targetPath"))
    metadata["attachments"] = [
        {key: value for key, value in item.items() if key not in {"data", "kind"}}
        for item in validated_attachments
    ]
    return {
        "vault_path": _vault_path(config),
        "content_text": content_text,
        "attachments": validated_attachments,
    }


def _validate_file_type(file_name: str, content_type: str, data: bytes) -> str:
    """Validate extension, declared MIME, and container magic for supported formats."""
    extension = Path(file_name).suffix.lower()
    accepted = {
        ".pdf": ("pdf", {"application/pdf"}),
        ".docx": (
            "docx",
            {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
        ),
        ".pptx": (
            "pptx",
            {"application/vnd.openxmlformats-officedocument.presentationml.presentation"},
        ),
        ".md": ("text", {"text/markdown", "text/plain"}),
        ".txt": ("text", {"text/plain"}),
        ".csv": ("csv", {"text/csv", "application/csv", "text/plain"}),
        ".xlsx": (
            "xlsx",
            {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        ),
        ".png": ("image", {"image/png"}),
        ".jpg": ("image", {"image/jpeg"}),
        ".jpeg": ("image", {"image/jpeg"}),
        ".gif": ("image", {"image/gif"}),
        ".webp": ("image", {"image/webp"}),
    }
    spec = accepted.get(extension)
    if spec is None:
        raise KnowledgeRuntimeError(422, "unsupported_attachment", f"Unsupported attachment type: {extension}")
    kind, mime_types = spec
    if content_type not in mime_types:
        raise KnowledgeRuntimeError(422, "unsupported_attachment", f"Unsupported MIME type for {file_name}")
    if kind == "pdf" and not data.startswith(b"%PDF-"):
        raise KnowledgeRuntimeError(422, "invalid_file_magic", f"Invalid PDF content for {file_name}")
    if kind in {"docx", "pptx", "xlsx"}:
        _validate_office_archive(data, kind, file_name)
    if kind == "image" and not _matches_image_magic(extension, data):
        raise KnowledgeRuntimeError(422, "invalid_file_magic", f"Invalid image content for {file_name}")
    return kind


def _validate_office_archive(data: bytes, kind: str, file_name: str) -> None:
    """Reject malformed Office containers, path traversal, and oversized expansion."""
    required_prefix = {"docx": "word/", "pptx": "ppt/", "xlsx": "xl/"}[kind]
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            if not any(member.filename.startswith(required_prefix) for member in members):
                raise KnowledgeRuntimeError(422, "invalid_office_file", f"Invalid Office content for {file_name}")
            total_size = 0
            for member in members:
                path = PurePosixPath(member.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise KnowledgeRuntimeError(422, "unsafe_archive", f"Unsafe archive path in {file_name}")
                total_size += member.file_size
                if total_size > 100 * 1024 * 1024:
                    raise KnowledgeRuntimeError(422, "archive_too_large", f"Expanded Office file is too large: {file_name}")
                lowered_name = member.filename.lower()
                if lowered_name.endswith("vbaproject.bin") or "/embeddings/" in lowered_name:
                    raise KnowledgeRuntimeError(
                        422,
                        "unsafe_office_content",
                        f"Macros and embedded objects are not accepted: {file_name}",
                    )
    except zipfile.BadZipFile as exc:
        raise KnowledgeRuntimeError(422, "invalid_office_file", f"Invalid Office content for {file_name}") from exc


def _matches_image_magic(extension: str, data: bytes) -> bool:
    """Return whether a supported image has the expected immutable signature."""
    if extension == ".png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if extension in {".jpg", ".jpeg"}:
        return data.startswith(b"\xff\xd8\xff")
    if extension == ".gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    if extension == ".webp":
        return len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    return False


async def _build_and_replace(
    target: Path,
    metadata: dict[str, Any],
    content_text: str,
    attachments: list[dict[str, Any]],
    config: dict[str, Any],
    converter: Any,
    *,
    reuse_source: Path | None = None,
) -> None:
    """Build and commit one snapshot through a durable, rollback-capable transaction."""
    target.parent.mkdir(parents=True, exist_ok=True)
    vault_path = _vault_path(config)
    transaction_root = vault_path / _TRANSACTION_DIR_NAME
    transaction_root.mkdir(mode=0o700, exist_ok=True)
    _fsync_directory(transaction_root.parent)
    transaction_id = uuid4().hex
    transaction = transaction_root / transaction_id
    transaction.mkdir(mode=0o700)
    _fsync_directory(transaction_root)
    temp_dir = transaction / "incoming"
    temp_dir.mkdir()
    backup = transaction / "previous"
    target_relative = PurePosixPath(target.relative_to(vault_path).as_posix())
    had_target = target.exists()
    previous_state = _snapshot_state(target) if had_target else None
    marker = {
        "transactionId": transaction_id,
        "targetRelative": target_relative.as_posix(),
        "knowledgeId": metadata["knowledgeId"],
        "targetPath": metadata.get("targetPath", ""),
        "hadTarget": had_target,
        "previousState": previous_state,
        "newSourceFingerprint": str(metadata.get("sourceFingerprint") or ""),
        "phase": "PREPARED",
    }
    _write_transaction_marker(transaction, marker)
    try:
        timeout_seconds = _positive_int(
            config.get("conversion_timeout_seconds"),
            180,
            "conversion_timeout_seconds",
        )
        try:
            async with asyncio.timeout(timeout_seconds):
                await _write_snapshot(
                    temp_dir,
                    metadata,
                    content_text,
                    attachments,
                    config,
                    converter,
                    target_relative=target_relative,
                    conversion_deadline=asyncio.get_running_loop().time() + timeout_seconds,
                    reuse_source=reuse_source,
                )
        except TimeoutError as exc:
            raise KnowledgeRuntimeError(
                504,
                "attachment_conversion_timeout",
                "Knowledge aggregate conversion exceeded the request deadline",
            ) from exc

        _assert_commit_target_unchanged(target, marker)
        if had_target:
            os.replace(target, backup)
            _fsync_directory(target.parent)
            _fsync_directory(transaction)
        _advance_transaction_phase(transaction, marker, "OLD_MOVED")

        if target.exists() or target.is_symlink():
            raise KnowledgeRuntimeError(
                409,
                "knowledge_path_changed",
                "Target Knowledge path changed while conversion was running",
            )
        os.replace(temp_dir, target)
        _fsync_directory(transaction)
        _fsync_directory(target.parent)
        _advance_transaction_phase(transaction, marker, "NEW_INSTALLED")
        _advance_transaction_phase(transaction, marker, "COMMITTED")
        try:
            shutil.rmtree(transaction)
            _fsync_directory(transaction_root)
        except OSError:
            logger.warning("Deferred cleanup for committed Knowledge transaction: %s", transaction)
    except BaseException:
        if transaction.exists() and marker.get("phase") != "COMMITTED":
            try:
                _rollback_transaction(target, transaction, marker)
            except Exception:
                logger.exception("Knowledge transaction rollback requires recovery: %s", transaction)
        raise


def _write_transaction_marker(transaction: Path, marker: dict[str, Any]) -> None:
    """Atomically publish and persist the current transaction phase."""
    marker_path = transaction / "transaction.json"
    marker_temporary_path = transaction / "transaction.json.tmp"
    with marker_temporary_path.open("w", encoding="utf-8") as marker_stream:
        json.dump(marker, marker_stream, ensure_ascii=False, sort_keys=True)
        marker_stream.flush()
        os.fsync(marker_stream.fileno())
    os.replace(marker_temporary_path, marker_path)
    _fsync_directory(transaction)


def _advance_transaction_phase(
    transaction: Path,
    marker: dict[str, Any],
    phase: str,
) -> None:
    """Publish a phase durably before updating the in-memory rollback state."""
    updated_marker = {**marker, "phase": phase}
    _write_transaction_marker(transaction, updated_marker)
    marker["phase"] = phase


def _snapshot_state(target: Path) -> dict[str, Any]:
    """Capture the managed version needed to detect external changes before commit."""
    manifest_path = target / "manifest.json"
    if target.is_symlink() or manifest_path.is_symlink():
        raise KnowledgeRuntimeError(500, "unsafe_vault_entry", "Knowledge snapshot uses a symlink")
    try:
        manifest_bytes = manifest_path.read_bytes()
        inode = target.stat().st_ino
    except OSError as exc:
        raise KnowledgeRuntimeError(500, "vault_read_failed", "Knowledge snapshot is unreadable") from exc
    return {
        "inode": inode,
        "manifestSha256": hashlib.sha256(manifest_bytes).hexdigest(),
    }


def _assert_commit_target_unchanged(target: Path, marker: dict[str, Any]) -> None:
    """Prevent Create/Update from overwriting a target changed during conversion."""
    if not marker["hadTarget"]:
        if target.exists() or target.is_symlink():
            raise KnowledgeRuntimeError(
                409,
                "knowledge_path_changed",
                "Target Knowledge path appeared while conversion was running",
            )
        return
    if not target.exists() or target.is_symlink() or _snapshot_state(target) != marker["previousState"]:
        raise KnowledgeRuntimeError(
            409,
            "knowledge_path_changed",
            "Target Knowledge snapshot changed while conversion was running",
        )


def _rollback_transaction(target: Path, transaction: Path, marker: dict[str, Any]) -> None:
    """Restore pre-transaction state after any failure before the COMMITTED phase."""
    backup = transaction / "previous"
    phase = str(marker.get("phase") or "PREPARED")
    if backup.exists() or backup.is_symlink():
        if not backup.is_dir() or backup.is_symlink():
            raise KnowledgeRuntimeError(500, "unsafe_transaction_state", "Previous snapshot is unsafe")
        if target.exists() or target.is_symlink():
            if not _is_expected_new_snapshot(target, marker):
                raise KnowledgeRuntimeError(
                    500,
                    "unsafe_transaction_state",
                    "Refusing to remove an unexpected target during rollback",
                )
            shutil.rmtree(target)
        os.replace(backup, target)
        _fsync_directory(transaction)
        _fsync_directory(target.parent)
    elif not marker["hadTarget"] and phase in {"OLD_MOVED", "NEW_INSTALLED"}:
        if target.exists() or target.is_symlink():
            if not _is_expected_new_snapshot(target, marker):
                raise KnowledgeRuntimeError(
                    500,
                    "unsafe_transaction_state",
                    "Refusing to remove an unexpected target during rollback",
                )
            shutil.rmtree(target)
            _fsync_directory(target.parent)
    elif phase == "PREPARED":
        pass
    elif marker["hadTarget"]:
        if not target.exists() or _snapshot_state(target) != marker["previousState"]:
            raise KnowledgeRuntimeError(500, "unsafe_transaction_state", "Previous snapshot was lost")
    shutil.rmtree(transaction)
    _fsync_directory(transaction.parent)


def _is_expected_new_snapshot(target: Path, marker: dict[str, Any]) -> bool:
    """Identify only the newly generated snapshot that this transaction may remove."""
    try:
        manifest = _read_manifest(target)
    except KnowledgeRuntimeError:
        return False
    return (
        str(manifest.get("providerType") or "") == PROVIDER_TYPE
        and str(manifest.get("sourceSystem") or "").strip().lower() == "smartcmp"
        and str(manifest.get("knowledgeId") or "") == marker["knowledgeId"]
        and str(manifest.get("targetPath") or "") == marker["targetPath"]
        and str(manifest.get("sourceFingerprint") or "") == marker["newSourceFingerprint"]
    )


def _recover_interrupted_transactions(vault_path: Path) -> None:
    """Run the same marker-validated recovery used by direct Chat Search/Get."""
    try:
        recover_vault_transactions(vault_path)
    except VaultTransactionError as exc:
        raise KnowledgeRuntimeError(500, "unsafe_transaction_state", str(exc)) from exc


async def _write_snapshot(
    root: Path,
    metadata: dict[str, Any],
    content_text: str,
    attachments: list[dict[str, Any]],
    config: dict[str, Any],
    converter: Any,
    *,
    target_relative: PurePosixPath,
    conversion_deadline: float,
    reuse_source: Path | None,
) -> None:
    """Write all generated files for one validated aggregate snapshot."""
    (root / "attachments").mkdir(parents=True)
    (root / "assets").mkdir(parents=True)
    attachment_links: list[str] = []
    manifest_attachments: list[dict[str, Any]] = []
    converted_characters = 0
    generated_asset_bytes = 0
    max_converted_characters = _positive_int(
        config.get("max_conversion_output_chars"),
        1_000_000,
        "max_conversion_output_chars",
    )
    max_generated_asset_bytes = _positive_int(
        config.get("max_total_attachment_bytes"),
        100 * 1024 * 1024,
        "max_total_attachment_bytes",
    )
    reusable_attachments = _reusable_attachment_index(reuse_source)
    conversion_context = {**metadata, "_atlasclawConversionDeadline": conversion_deadline}
    for attachment in attachments:
        file_id = attachment["fileId"]
        attachment_dir = root / "attachments" / file_id
        asset_dir = root / "assets" / file_id
        extension = Path(attachment["fileName"]).suffix.lower()
        reused = _reuse_attachment(
            reuse_source,
            reusable_attachments.get(file_id),
            attachment,
            attachment_dir,
            asset_dir,
        )
        if reused is None:
            attachment_dir.mkdir(parents=True)
            asset_dir.mkdir(parents=True)
            (attachment_dir / f"original{extension}").write_bytes(attachment["data"])
            converted, converted_assets = await _convert_attachment(
                {**attachment, "parentKnowledgeId": metadata["knowledgeId"]},
                conversion_context,
                converter,
            )
            _write_searchable_markdown(
                attachment_dir / "content.md",
                converted,
                target_relative=target_relative / "attachments" / file_id / "content.md",
                config=config,
            )
            asset_manifest = _write_conversion_assets(
                asset_dir,
                converted_assets,
                file_id=file_id,
                config=config,
            )
            manifest_attachment = {
                key: value
                for key, value in attachment.items()
                if key not in {"data", "kind"}
            } | {
                "conversionVersion": _ATTACHMENT_CONVERSION_VERSION,
                "markdownPath": f"attachments/{file_id}/content.md",
                "originalPath": f"attachments/{file_id}/original{extension}",
                "assetsPath": f"assets/{file_id}/",
                "assets": asset_manifest,
            }
            converted_length = len(converted)
            asset_bytes = sum(
                len(asset.get("data"))
                for asset in converted_assets
                if isinstance(asset, dict) and isinstance(asset.get("data"), bytes)
            )
        else:
            manifest_attachment, converted_length, asset_bytes = reused

        converted_characters += converted_length
        if converted_characters > max_converted_characters:
            raise KnowledgeRuntimeError(
                413,
                "attachment_markdown_too_large",
                "Aggregate converted attachment Markdown exceeds the configured size limit",
            )
        generated_asset_bytes += asset_bytes
        if generated_asset_bytes > max_generated_asset_bytes:
            raise KnowledgeRuntimeError(
                413,
                "generated_assets_too_large",
                "Aggregate generated assets exceed the configured size limit",
            )
        attachment_links.append(
            f"- [{_markdown_escape(attachment['fileName'])}](attachments/{file_id}/content.md)"
        )
        manifest_attachments.append(manifest_attachment)

    tags, group_frontmatter = _group_metadata(metadata.get("group"))
    tags = [f"cmp-knowledge/{metadata['knowledgeId']}", *tags]
    frontmatter = {
        "title": metadata["title"],
        "source_system": "smartcmp",
        "knowledge_id": metadata["knowledgeId"],
        "provider_type": PROVIDER_TYPE,
        "provider_instance": metadata.get("providerInstance", ""),
        "source_fingerprint": metadata.get("sourceFingerprint", ""),
        "tags": tags,
        **group_frontmatter,
    }
    index_text = _yaml_frontmatter(frontmatter)
    index_text += f"# {metadata['title']}\n\n{content_text.rstrip()}\n"
    if attachment_links:
        index_text += "\n## Attachments\n\n" + "\n".join(attachment_links) + "\n"
    _write_searchable_markdown(
        root / "index.md",
        index_text,
        target_relative=target_relative / "index.md",
        config=config,
    )

    persisted_metadata = dict(metadata)
    persisted_metadata["attachments"] = manifest_attachments
    persisted_metadata["documentPath"] = "index.md"
    persisted_metadata["publicationStatus"] = "PUBLISHED"
    _write_manifest(root, persisted_metadata)


def _reusable_attachment_index(reuse_source: Path | None) -> dict[str, dict[str, Any]]:
    """Index the prior conversion metadata when the current snapshot is safe to reuse."""
    if reuse_source is None:
        return {}
    manifest = _read_manifest(reuse_source)
    attachments = manifest.get("attachments", [])
    if not isinstance(attachments, list):
        return {}
    return {
        str(item.get("fileId")): item
        for item in attachments
        if isinstance(item, dict) and str(item.get("fileId") or "")
    }


def _reuse_attachment(
    reuse_source: Path | None,
    previous: dict[str, Any] | None,
    attachment: dict[str, Any],
    attachment_dir: Path,
    asset_dir: Path,
) -> tuple[dict[str, Any], int, int] | None:
    """Copy a checksum-identical conversion instead of invoking the attachment converter."""
    if reuse_source is None or previous is None:
        return None
    file_id = attachment["fileId"]
    extension = Path(attachment["fileName"]).suffix.lower()
    if (
        previous.get("conversionVersion") != _ATTACHMENT_CONVERSION_VERSION
        or previous.get("fileId") != file_id
        or previous.get("checksum") != attachment.get("checksum")
    ):
        return None
    previous_attachment_dir = reuse_source / "attachments" / file_id
    previous_asset_dir = reuse_source / "assets" / file_id
    previous_markdown = previous_attachment_dir / "content.md"
    if (
        not previous_attachment_dir.is_dir()
        or previous_attachment_dir.is_symlink()
        or not previous_asset_dir.is_dir()
        or previous_asset_dir.is_symlink()
        or not previous_markdown.is_file()
        or previous_markdown.is_symlink()
        or _directory_contains_symlink(previous_asset_dir)
    ):
        return None
    assets = previous.get("assets", [])
    if not isinstance(assets, list) or any(not isinstance(item, dict) for item in assets):
        return None
    attachment_dir.mkdir(parents=True)
    (attachment_dir / f"original{extension}").write_bytes(attachment["data"])
    shutil.copy2(previous_markdown, attachment_dir / "content.md")
    shutil.copytree(previous_asset_dir, asset_dir)
    converted_length = len(previous_markdown.read_text(encoding="utf-8"))
    asset_bytes = sum(
        int(item.get("size") or 0)
        for item in assets
        if isinstance(item.get("size"), int)
    )
    manifest_attachment = {
        key: value for key, value in attachment.items() if key not in {"data", "kind"}
    } | {
        "conversionVersion": _ATTACHMENT_CONVERSION_VERSION,
        "markdownPath": f"attachments/{file_id}/content.md",
        "originalPath": f"attachments/{file_id}/original{extension}",
        "assetsPath": f"assets/{file_id}/",
        "assets": assets,
    }
    return manifest_attachment, converted_length, asset_bytes


async def _convert_attachment(
    attachment: dict[str, Any],
    metadata: dict[str, Any],
    converter: Any,
) -> tuple[str, list[dict[str, Any]]]:
    """Convert one attachment through the Provider's local-or-visual conversion boundary."""
    convert = getattr(converter, "convert", None)
    if not callable(convert):
        raise KnowledgeRuntimeError(
            503,
            "attachment_converter_unavailable",
            "Attachment converter is unavailable",
        )
    try:
        converted = await convert(attachment, metadata)
    except Exception as exc:
        status_code = int(getattr(exc, "status_code", 422))
        code = str(getattr(exc, "code", "attachment_conversion_failed"))
        detail = str(
            getattr(
                exc,
                "detail",
                f"Attachment conversion failed for {attachment['fileName']}",
            )
        )
        raise KnowledgeRuntimeError(
            status_code,
            code,
            detail,
        ) from exc
    if isinstance(converted, dict):
        body = str(converted.get("markdown") or "")
        raw_assets = converted.get("assets", [])
        if not isinstance(raw_assets, list):
            raise KnowledgeRuntimeError(502, "invalid_converter_result", "Converter assets must be a list")
        assets = [item for item in raw_assets if isinstance(item, dict)]
        if len(assets) != len(raw_assets):
            raise KnowledgeRuntimeError(502, "invalid_converter_result", "Converter assets must be objects")
    else:
        body = str(converted or "")
        assets = []
    if not body.strip():
        raise KnowledgeRuntimeError(
            422,
            "unextractable_attachment",
            f"Attachment converter returned no Markdown for {attachment['fileName']}",
        )
    frontmatter = {
        "title": attachment["fileName"],
        "source_system": "smartcmp",
        "parent_knowledge_id": attachment.get("parentKnowledgeId", ""),
        "attachment_file_id": attachment["fileId"],
        "attachment_file_name": attachment["fileName"],
        "content_type": attachment["contentType"],
        "checksum": attachment["checksum"],
        "tags": [
            f"cmp-knowledge/{metadata['knowledgeId']}",
        ],
    }
    return _yaml_frontmatter(frontmatter) + body.rstrip() + "\n", assets


def _write_conversion_assets(
    asset_dir: Path,
    assets: list[dict[str, Any]],
    *,
    file_id: str,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Persist the validated direct-image asset returned by the Core converter."""
    if len(assets) > 1:
        raise KnowledgeRuntimeError(413, "too_many_generated_assets", "Generated asset count exceeds limit")
    max_asset_bytes = _positive_int(
        config.get("max_attachment_bytes"),
        25 * 1024 * 1024,
        "max_attachment_bytes",
    )
    total_limit = _positive_int(
        config.get("max_total_attachment_bytes"),
        100 * 1024 * 1024,
        "max_total_attachment_bytes",
    )
    total_bytes = 0
    persisted: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for raw_asset in assets:
        file_name = _safe_file_name(raw_asset.get("fileName"), file_id)
        if file_name in seen_names:
            raise KnowledgeRuntimeError(502, "invalid_converter_result", "Generated asset names must be unique")
        seen_names.add(file_name)
        content_type = str(raw_asset.get("contentType") or "").strip().lower()
        data = raw_asset.get("data")
        if not isinstance(data, bytes) or not data:
            raise KnowledgeRuntimeError(502, "invalid_converter_result", "Generated asset content is invalid")
        if len(data) > max_asset_bytes:
            raise KnowledgeRuntimeError(413, "generated_asset_too_large", f"Generated asset is too large: {file_name}")
        total_bytes += len(data)
        if total_bytes > total_limit:
            raise KnowledgeRuntimeError(413, "generated_assets_too_large", "Generated assets exceed total size limit")
        if _validate_file_type(file_name, content_type, data) != "image":
            raise KnowledgeRuntimeError(502, "invalid_converter_result", "Generated assets must be images")
        checksum = hashlib.sha256(data).hexdigest()
        (asset_dir / file_name).write_bytes(data)
        persisted.append(
            {
                "fileName": file_name,
                "contentType": content_type,
                "size": len(data),
                "checksum": f"sha256:{checksum}",
                "path": f"assets/{file_id}/{file_name}",
            }
        )
    return persisted


def _write_searchable_markdown(
    path: Path,
    text: str,
    *,
    target_relative: PurePosixPath,
    config: dict[str, Any],
) -> None:
    """Write generated Markdown only when the provider scan will include it."""
    relative_path = target_relative.as_posix()
    include_globs = _glob_values(config.get("include_globs"), ["**/*.md"])
    exclude_globs = _glob_values(
        config.get("exclude_globs"),
        [".obsidian/**", ".git/**", "**/.*/**", "**/node_modules/**"],
    )
    if not any(_matches_glob(relative_path, pattern) for pattern in include_globs) or any(
        _matches_glob(relative_path, pattern) for pattern in exclude_globs
    ):
        raise KnowledgeRuntimeError(
            422,
            "knowledge_path_not_searchable",
            f"Generated Markdown is excluded by the provider scan: {relative_path}",
        )
    max_file_bytes = _positive_int(config.get("max_file_bytes"), 1048576, "max_file_bytes")
    encoded = text.encode("utf-8")
    if len(encoded) > max_file_bytes:
        raise KnowledgeRuntimeError(
            413,
            "knowledge_markdown_too_large",
            f"Generated Markdown exceeds max_file_bytes: {relative_path}",
        )
    path.write_bytes(encoded)


def _glob_values(value: Any, default: list[str]) -> list[str]:
    """Normalize provider glob configuration using the direct-search list syntax."""
    if value is None:
        return list(default)
    if isinstance(value, list):
        items = [str(item).strip() for item in value]
    else:
        items = [item.strip() for item in str(value).replace("\n", ",").split(",")]
    return [item for item in items if item] or list(default)


def _document_response(target: Path, *, created: bool) -> dict[str, Any]:
    """Serialize safe aggregate state without reading or returning original binaries."""
    manifest_path = target / "manifest.json"
    document_markdown_path = target / "index.md"
    if target.is_symlink() or manifest_path.is_symlink() or document_markdown_path.is_symlink():
        raise KnowledgeRuntimeError(500, "unsafe_vault_entry", "Knowledge aggregate uses a symlink")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        markdown = document_markdown_path.read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        raise KnowledgeRuntimeError(500, "vault_read_failed", "Knowledge aggregate is incomplete") from exc
    return {
        "success": True,
        "created": created,
        "knowledgeId": manifest.get("knowledgeId"),
        "providerType": manifest.get("providerType"),
        "providerInstance": manifest.get("providerInstance"),
        "sourceFingerprint": manifest.get("sourceFingerprint"),
        "publicationStatus": manifest.get("publicationStatus", "PUBLISHED"),
        "title": manifest.get("title"),
        "group": manifest.get("group"),
        "attachments": manifest.get("attachments", []),
        "content": markdown,
    }


def _citation_for_result(vault_path: Path, item: dict[str, Any]) -> dict[str, Any] | None:
    """Build parent Knowledge and attachment citation metadata from a vault path."""
    raw_path = str(item.get("path") or "")
    citation: dict[str, Any] = {"path": raw_path, "headingPath": item.get("heading_path", [])}
    lexical_source = vault_path / PurePosixPath(raw_path)
    if _contains_symlink(vault_path, lexical_source):
        return None
    source_path = lexical_source.resolve()
    if vault_path != source_path and vault_path not in source_path.parents:
        return None
    document_root = _manifest_parent(vault_path, source_path)
    if document_root is None:
        return None
    manifest = _read_managed_manifest(vault_path, document_root / "manifest.json")
    knowledge_id = str(manifest.get("knowledgeId") or "")
    citation.update(
        {
            "knowledgeId": knowledge_id,
            "sourceType": "knowledge",
            "targetPath": str(manifest.get("targetPath") or ""),
        }
    )
    relative_source = source_path.relative_to(document_root)
    relative_parts = relative_source.parts
    if len(relative_parts) >= 3 and relative_parts[0] == "attachments":
        file_id = relative_parts[1]
        citation.update({"sourceType": "attachment", "attachmentFileId": file_id})
        for attachment in manifest.get("attachments", []):
            if isinstance(attachment, dict) and attachment.get("fileId") == file_id:
                citation["attachmentFileName"] = attachment.get("fileName")
                citation["checksum"] = attachment.get("checksum")
                break
    headings = item.get("heading_path")
    if isinstance(headings, list) and headings:
        location = str(headings[-1])
        if re.match(r"^(Page|Slide)\s+\d+$", location, flags=re.IGNORECASE):
            citation["location"] = location
    return citation


def _vault_path(config: dict[str, Any]) -> Path:
    """Resolve and validate the configured vault root, never a request-provided path."""
    value = str(config.get("vault_path") or "").strip()
    if not value:
        raise KnowledgeRuntimeError(500, "vault_not_configured", "vault_path is not configured")
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise KnowledgeRuntimeError(500, "vault_not_found", "Configured vault_path does not exist")
    return path


def _new_document_path(vault_path: Path, target_path: str, knowledge_id: str) -> Path:
    """Build a create target from a validated Vault-relative directory."""
    normalized_knowledge = _identifier(knowledge_id, "knowledgeId")
    parent = vault_path / PurePosixPath(target_path) if target_path else vault_path
    if _contains_symlink(vault_path, parent):
        raise KnowledgeRuntimeError(422, "invalid_target_path", "targetPath cannot use symlinks")
    target = (parent / normalized_knowledge).resolve()
    if vault_path not in target.parents:
        raise KnowledgeRuntimeError(422, "invalid_target_path", "targetPath escapes the Vault")
    return target


def _find_document_paths(
    vault_path: Path,
    knowledge_id: str | None = None,
) -> list[Path]:
    """Locate validated managed Knowledge directories by optional CMP identity."""
    normalized_knowledge = _identifier(knowledge_id, "knowledgeId") if knowledge_id else ""
    matches: list[Path] = []
    for manifest_path in vault_path.rglob("manifest.json"):
        relative = manifest_path.relative_to(vault_path)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if normalized_knowledge and manifest_path.parent.name != normalized_knowledge:
            continue
        try:
            manifest = _read_managed_manifest(vault_path, manifest_path)
        except KnowledgeRuntimeError:
            if normalized_knowledge:
                raise
            continue
        if not normalized_knowledge or str(manifest.get("knowledgeId") or "") == normalized_knowledge:
            matches.append(manifest_path.parent)
    if normalized_knowledge and len(matches) > 1:
        raise KnowledgeRuntimeError(409, "duplicate_knowledge", "Duplicate Knowledge identity in Vault")
    return sorted(matches)


def _find_document_path(vault_path: Path, knowledge_id: str) -> Path | None:
    """Locate one validated managed Knowledge directory by stable identity."""
    matches = _find_document_paths(vault_path, knowledge_id)
    return matches[0] if matches else None


def _find_unpublished_path(vault_path: Path, knowledge_id: str) -> Path | None:
    """Locate one unpublished aggregate in the provider-owned hidden state directory."""
    normalized_id = _identifier(knowledge_id, "knowledgeId")
    candidate = _validated_unpublished_root(vault_path, create=False) / normalized_id
    if _contains_symlink(vault_path, candidate):
        raise KnowledgeRuntimeError(500, "unsafe_vault_entry", "Unpublished Knowledge path is unsafe")
    if not candidate.exists() and not candidate.is_symlink():
        return None
    if candidate.is_symlink() or not candidate.is_dir():
        raise KnowledgeRuntimeError(500, "unsafe_vault_entry", "Unpublished Knowledge path is unsafe")
    try:
        resolved_candidate = candidate.resolve(strict=True)
        resolved_candidate.relative_to(vault_path)
    except (OSError, ValueError) as exc:
        raise KnowledgeRuntimeError(
            500,
            "unsafe_vault_entry",
            "Unpublished Knowledge path escapes the Vault",
        ) from exc
    manifest = _read_manifest(resolved_candidate)
    if (
        str(manifest.get("providerType") or "") != PROVIDER_TYPE
        or str(manifest.get("sourceSystem") or "").strip().lower() != "smartcmp"
        or str(manifest.get("knowledgeId") or "") != normalized_id
    ):
        raise KnowledgeRuntimeError(500, "invalid_manifest", "Unpublished Knowledge manifest is invalid")
    return resolved_candidate


def _validated_unpublished_root(vault_path: Path, *, create: bool) -> Path:
    """Return the provider-owned hidden root only when it stays inside the Vault."""
    unpublished_root = vault_path / _UNPUBLISHED_DIR_NAME
    if _contains_symlink(vault_path, unpublished_root):
        raise KnowledgeRuntimeError(500, "unsafe_vault_entry", "Unpublished root is unsafe")
    root_exists = unpublished_root.exists()
    if root_exists and not unpublished_root.is_dir():
        raise KnowledgeRuntimeError(500, "unsafe_vault_entry", "Unpublished root is unsafe")
    if create and not root_exists:
        unpublished_root.mkdir(mode=0o700, exist_ok=True)
    if not unpublished_root.exists():
        return unpublished_root
    if not unpublished_root.is_dir() or _contains_symlink(vault_path, unpublished_root):
        raise KnowledgeRuntimeError(500, "unsafe_vault_entry", "Unpublished root is unsafe")
    try:
        resolved_root = unpublished_root.resolve(strict=True)
        resolved_root.relative_to(vault_path)
    except (OSError, ValueError) as exc:
        raise KnowledgeRuntimeError(
            500,
            "unsafe_vault_entry",
            "Unpublished root escapes the Vault",
        ) from exc
    return resolved_root


def _read_managed_manifest(vault_path: Path, manifest_path: Path) -> dict[str, Any]:
    """Read and validate a non-symlink manifest and its stable directory identity."""
    if _contains_symlink(vault_path, manifest_path):
        raise KnowledgeRuntimeError(500, "unsafe_vault_entry", "Knowledge manifest uses a symlink")
    try:
        resolved_manifest = manifest_path.resolve(strict=True)
        resolved_manifest.relative_to(vault_path)
    except (OSError, ValueError) as exc:
        raise KnowledgeRuntimeError(500, "unsafe_vault_entry", "Knowledge manifest escapes the Vault") from exc
    manifest = _read_manifest(resolved_manifest.parent)
    if str(manifest.get("providerType") or "") != PROVIDER_TYPE:
        raise KnowledgeRuntimeError(500, "invalid_manifest", "Knowledge manifest providerType is invalid")
    if str(manifest.get("sourceSystem") or "").strip().lower() != "smartcmp":
        raise KnowledgeRuntimeError(500, "invalid_manifest", "Knowledge manifest sourceSystem is invalid")
    knowledge_id = str(manifest.get("knowledgeId") or "")
    try:
        _identifier(knowledge_id, "knowledgeId")
    except KnowledgeRuntimeError as exc:
        raise KnowledgeRuntimeError(500, "invalid_manifest", "Knowledge manifest identity is invalid") from exc
    document_root = resolved_manifest.parent
    if document_root.name != knowledge_id:
        raise KnowledgeRuntimeError(500, "invalid_manifest", "Knowledge directory does not match knowledgeId")
    relative_parent = document_root.parent.relative_to(vault_path).as_posix()
    expected_target_path = "" if relative_parent == "." else relative_parent
    if str(manifest.get("targetPath") or "") != expected_target_path:
        raise KnowledgeRuntimeError(500, "invalid_manifest", "Knowledge manifest targetPath is inconsistent")
    return manifest


def _directory_contains_symlink(path: Path) -> bool:
    """Return whether a managed directory contains a symlinked descendant."""
    return any(candidate.is_symlink() for candidate in path.rglob("*"))


def _read_manifest(document_root: Path) -> dict[str, Any]:
    """Read one managed manifest or raise a structured corruption error."""
    manifest_path = document_root / "manifest.json"
    if document_root.is_symlink() or manifest_path.is_symlink():
        raise KnowledgeRuntimeError(500, "unsafe_vault_entry", "Knowledge manifest uses a symlink")
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KnowledgeRuntimeError(500, "invalid_manifest", "Knowledge manifest is unreadable") from exc
    if not isinstance(value, dict):
        raise KnowledgeRuntimeError(500, "invalid_manifest", "Knowledge manifest must be an object")
    return value


def _write_manifest(document_root: Path, value: dict[str, Any]) -> None:
    """Atomically persist one managed manifest and its containing directory."""
    manifest_path = document_root / "manifest.json"
    temporary_path = document_root / "manifest.json.tmp"
    with temporary_path.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary_path, manifest_path)
    _fsync_directory(document_root)


def _manifest_parent(vault_path: Path, source_path: Path) -> Path | None:
    """Find the nearest managed Knowledge root containing a search result."""
    current = source_path.parent
    while current != vault_path and vault_path in current.parents:
        if (current / "manifest.json").is_file():
            return current
        current = current.parent
    return None


def _target_path(value: Any) -> str:
    """Normalize an optional Vault-relative directory selected at create time."""
    try:
        return normalize_target_path(value)
    except ValueError as exc:
        raise KnowledgeRuntimeError(422, "invalid_target_path", str(exc)) from exc


def _identifier(value: Any, name: str) -> str:
    try:
        return normalize_identifier(value, name)
    except ValueError as exc:
        raise KnowledgeRuntimeError(422, "invalid_identifier", str(exc)) from exc


def _checksum(value: Any, file_id: str) -> str:
    match = _SHA256.fullmatch(str(value or "").strip())
    if not match:
        raise KnowledgeRuntimeError(422, "invalid_checksum", f"Invalid SHA-256 checksum for {file_id}")
    return match.group(1)


def _safe_file_name(value: Any, file_id: str) -> str:
    name = str(value or "").strip()
    if not name or name != Path(name).name or any(char in name for char in ("/", "\\", "\x00")):
        raise KnowledgeRuntimeError(422, "invalid_filename", f"Invalid fileName for {file_id}")
    return name


def _positive_int(value: Any, default: int, name: str) -> int:
    try:
        result = int(value) if value not in (None, "") else default
    except (TypeError, ValueError) as exc:
        raise KnowledgeRuntimeError(500, "invalid_provider_config", f"{name} must be an integer") from exc
    if result <= 0:
        raise KnowledgeRuntimeError(500, "invalid_provider_config", f"{name} must be positive")
    return result


def _group_metadata(raw_group: Any) -> tuple[list[str], dict[str, Any]]:
    """Normalize SmartCMP Group ancestry into stable frontmatter and tags."""
    if not isinstance(raw_group, dict):
        return [], {}
    category_id = str(raw_group.get("categoryId") or raw_group.get("id") or "").strip()
    category_name = str(raw_group.get("categoryName") or raw_group.get("name") or "").strip()
    path_ids = [str(item) for item in raw_group.get("pathIds", []) if str(item).strip()]
    path_names = [str(item) for item in raw_group.get("pathNames", []) if str(item).strip()]
    tags = [f"cmp-group-tree/{item}" for item in path_ids]
    if category_id:
        tags.append(f"cmp-group-exact/{category_id}")
        if category_id not in path_ids:
            tags.append(f"cmp-group-tree/{category_id}")
    return tags, {
        "cmp_category_id": category_id,
        "cmp_category_name": category_name,
        "cmp_category_path_ids": path_ids,
        "cmp_category_path_names": path_names,
    }


def _yaml_frontmatter(values: dict[str, Any]) -> str:
    """Serialize deterministic YAML frontmatter for generated Markdown."""
    return "---\n" + yaml.safe_dump(values, allow_unicode=True, sort_keys=False) + "---\n\n"


def _markdown_escape(value: str) -> str:
    return str(value).replace("[", "\\[").replace("]", "\\]")


def _prune_empty_parent(path: Path, *, stop: Path) -> None:
    """Remove empty target directories without ever deleting the configured vault root."""
    current = path
    while current != stop and stop in current.parents:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _remove_document_path(target: Path, *, stop: Path) -> None:
    """Remove one managed aggregate and propagate any incomplete filesystem deletion."""
    if _contains_symlink(stop, target):
        raise KnowledgeRuntimeError(500, "unsafe_vault_entry", "Knowledge path is unsafe")
    try:
        resolved_target = target.resolve(strict=True)
        resolved_target.relative_to(stop)
    except (OSError, ValueError) as exc:
        raise KnowledgeRuntimeError(
            500,
            "unsafe_vault_entry",
            "Knowledge path escapes the Vault",
        ) from exc
    if resolved_target == stop:
        raise KnowledgeRuntimeError(500, "unsafe_vault_entry", "Knowledge path cannot be the Vault root")
    shutil.rmtree(resolved_target)
    _prune_empty_parent(resolved_target.parent, stop=stop)
