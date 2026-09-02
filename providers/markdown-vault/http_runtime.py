"""Provider-owned HTTP adapter for Markdown Vault Knowledge aggregates."""

from __future__ import annotations

from collections.abc import AsyncGenerator
import json
import logging
from typing import Any

from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from .knowledge_attachment_converter import build_knowledge_attachment_converter
from .knowledge_runtime import (
    KnowledgeRuntimeError,
    create_document,
    delete_document,
    get_document,
    query_documents,
    unpublish_document,
    update_document,
)


logger = logging.getLogger(__name__)
_MAX_METADATA_BYTES = 1024 * 1024
_MAX_CONTENT_BYTES = 1024 * 1024
_MAX_JSON_BODY_BYTES = 1024 * 1024
_MULTIPART_OVERHEAD_BYTES = 2 * 1024 * 1024
_UPLOAD_CHUNK_BYTES = 1024 * 1024
_MAX_QUERY_CHARS = 4096
_MAX_KEYWORDS = 50
_MAX_KEYWORD_CHARS = 256
_MAX_KEYWORDS_TOTAL_CHARS = 4096


class _KnowledgeMultipartLimitError(MultiPartException):
    """Report a provider limit while the parser is receiving the offending part."""


class _KnowledgeMultipartParser(MultiPartParser):
    """Enforce field and attachment limits while multipart bytes are received."""

    def __init__(
        self,
        *args: Any,
        max_attachment_bytes: int,
        max_total_attachment_bytes: int,
        **kwargs: Any,
    ) -> None:
        """Create a parser with limits taken from the selected provider instance."""
        super().__init__(*args, **kwargs)
        self._max_attachment_bytes = max_attachment_bytes
        self._max_total_attachment_bytes = max_total_attachment_bytes
        self._current_part_bytes = 0
        self._total_attachment_bytes = 0

    def on_part_begin(self) -> None:
        """Reset the byte counter before receiving a new multipart part."""
        super().on_part_begin()
        self._current_part_bytes = 0

    def on_headers_finished(self) -> None:
        """Reject unknown fields and attachments that omit file disposition metadata."""
        super().on_headers_finished()
        part_name = self._current_part.field_name
        if part_name in {"metadata", "content"}:
            return
        if part_name.startswith("attachment_"):
            filename = str(
                getattr(self._current_part.file, "filename", "") or ""
            ).strip()
            if filename:
                return
        raise MultiPartException(f"Unexpected multipart part: {part_name}")

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        """Reject an oversized part before Starlette stores its current chunk."""
        message_size = end - start
        part_name = self._current_part.field_name
        if part_name == "metadata":
            part_limit = _MAX_METADATA_BYTES
        elif part_name == "content":
            part_limit = _MAX_CONTENT_BYTES
        elif part_name.startswith("attachment_"):
            part_limit = self._max_attachment_bytes
            self._total_attachment_bytes += message_size
            if self._total_attachment_bytes > self._max_total_attachment_bytes:
                raise _KnowledgeMultipartLimitError("Total attachment size exceeds limit")
        else:
            raise MultiPartException(f"Unexpected multipart part: {part_name}")
        self._current_part_bytes += message_size
        if self._current_part_bytes > part_limit:
            raise _KnowledgeMultipartLimitError(f"Multipart part is too large: {part_name}")
        super().on_part_data(data, start, end)


def _positive_config_int(config: dict[str, Any], name: str, default: int) -> int:
    """Read a positive provider limit or report an invalid instance configuration."""
    try:
        value = int(config.get(name, default))
    except (TypeError, ValueError) as exc:
        raise KnowledgeRuntimeError(
            500,
            "invalid_provider_config",
            f"{name} must be an integer",
        ) from exc
    if value <= 0:
        raise KnowledgeRuntimeError(
            500,
            "invalid_provider_config",
            f"{name} must be positive",
        )
    return value


async def _bounded_request_stream(request: Any, max_body_bytes: int) -> AsyncGenerator[bytes, None]:
    """Stop a chunked multipart request at the provider instance's aggregate limit."""
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_body_bytes:
            raise _KnowledgeMultipartLimitError("Multipart request body exceeds limit")
        yield chunk


async def _part_bytes(value: Any, name: str, max_bytes: int) -> bytes:
    """Read one multipart value within a provider-owned in-memory boundary."""
    if isinstance(value, UploadFile):
        chunks: list[bytes] = []
        total = 0
        try:
            while True:
                chunk = await value.read(_UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise KnowledgeRuntimeError(
                        413,
                        "multipart_part_too_large",
                        f"Multipart part is too large: {name}",
                    )
                chunks.append(chunk)
        finally:
            await value.close()
        return b"".join(chunks)
    if isinstance(value, str):
        encoded = value.encode("utf-8")
        if len(encoded) > max_bytes:
            raise KnowledgeRuntimeError(
                413,
                "multipart_part_too_large",
                f"Multipart part is too large: {name}",
            )
        return encoded
    raise KnowledgeRuntimeError(422, "invalid_multipart", f"Invalid multipart part: {name}")


async def _read_snapshot_parts(
    request: Any,
    config: dict[str, Any],
) -> tuple[dict[str, Any], bytes, list[dict[str, Any]]]:
    """Read one complete body-plus-attachments snapshot from multipart input."""
    max_attachments = _positive_config_int(config, "max_attachments", 20)
    max_attachment_bytes = _positive_config_int(
        config,
        "max_attachment_bytes",
        25 * 1024 * 1024,
    )
    max_total_attachment_bytes = _positive_config_int(
        config,
        "max_total_attachment_bytes",
        100 * 1024 * 1024,
    )
    max_body_bytes = (
        max_total_attachment_bytes
        + _MAX_METADATA_BYTES
        + _MAX_CONTENT_BYTES
        + _MULTIPART_OVERHEAD_BYTES
    )
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise KnowledgeRuntimeError(
                422,
                "invalid_content_length",
                "Invalid Content-Length header",
            ) from exc
        if declared_length > max_body_bytes:
            raise KnowledgeRuntimeError(
                413,
                "multipart_body_too_large",
                "Multipart request body exceeds limit",
            )
    try:
        parser = _KnowledgeMultipartParser(
            request.headers,
            _bounded_request_stream(request, max_body_bytes),
            max_files=max_attachments + 2,
            max_fields=8,
            # Starlette applies max_part_size to ordinary fields only. Attachments
            # are streamed to spooled files and enforced by our byte counters.
            max_part_size=max(_MAX_METADATA_BYTES, _MAX_CONTENT_BYTES),
            max_attachment_bytes=max_attachment_bytes,
            max_total_attachment_bytes=max_total_attachment_bytes,
        )
        form = await parser.parse()
    except _KnowledgeMultipartLimitError as exc:
        raise KnowledgeRuntimeError(413, "multipart_limit_exceeded", exc.message) from exc
    except MultiPartException as exc:
        message = str(exc.message or "Invalid multipart request")
        is_limit = message.startswith(("Too many files", "Too many fields", "Part exceeded"))
        raise KnowledgeRuntimeError(
            413 if is_limit else 422,
            "multipart_limit_exceeded" if is_limit else "invalid_multipart",
            message,
        ) from exc
    except KnowledgeRuntimeError:
        raise
    except Exception as exc:
        raise KnowledgeRuntimeError(422, "invalid_multipart", "Invalid multipart request") from exc

    try:
        metadata_value = form.get("metadata")
        content_value = form.get("content")
        if metadata_value is None or content_value is None:
            raise KnowledgeRuntimeError(
                422,
                "missing_multipart_part",
                "metadata and content parts are required",
            )
        metadata_bytes = await _part_bytes(metadata_value, "metadata", _MAX_METADATA_BYTES)
        content_bytes = await _part_bytes(content_value, "content", _MAX_CONTENT_BYTES)
        try:
            metadata = json.loads(metadata_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise KnowledgeRuntimeError(
                422,
                "invalid_metadata",
                "metadata must be UTF-8 JSON",
            ) from exc
        if not isinstance(metadata, dict):
            raise KnowledgeRuntimeError(422, "invalid_metadata", "metadata must be a JSON object")

        attachments: list[dict[str, Any]] = []
        total_attachment_bytes = 0
        for part_name, value in form.multi_items():
            if part_name in {"metadata", "content"}:
                continue
            if not part_name.startswith("attachment_") or not isinstance(value, UploadFile):
                raise KnowledgeRuntimeError(
                    422,
                    "unexpected_multipart_part",
                    f"Unexpected multipart part: {part_name}",
                )
            data = await _part_bytes(value, part_name, max_attachment_bytes)
            total_attachment_bytes += len(data)
            if total_attachment_bytes > max_total_attachment_bytes:
                raise KnowledgeRuntimeError(
                    413,
                    "attachments_too_large",
                    "Total attachment size exceeds limit",
                )
            attachments.append(
                {
                    "part_name": part_name,
                    "filename": value.filename or "",
                    "content_type": value.content_type or "",
                    "data": data,
                }
            )
        return metadata, content_bytes, attachments
    finally:
        await form.close()


async def _read_json_body(request: Any) -> dict[str, Any]:
    """Read a small provider JSON request without trusting Content-Length."""
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > _MAX_JSON_BODY_BYTES:
            raise KnowledgeRuntimeError(413, "json_body_too_large", "JSON request body exceeds limit")
        chunks.append(chunk)
    try:
        body = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KnowledgeRuntimeError(422, "invalid_json", "Request body must be UTF-8 JSON") from exc
    if not isinstance(body, dict):
        raise KnowledgeRuntimeError(422, "invalid_json", "Request body must be a JSON object")
    return body


def _prepare_metadata(
    metadata: dict[str, Any],
    context: Any,
    *,
    knowledge_id: str | None = None,
) -> str:
    """Validate request tenancy, then persist only Vault-owned Knowledge identity."""
    tenant_id = str(metadata.pop("tenantId", "") or "").strip()
    _ensure_tenant_access(context, tenant_id)
    metadata["providerType"] = context.provider_type
    metadata["providerInstance"] = context.provider_instance
    if knowledge_id is not None:
        metadata["knowledgeId"] = knowledge_id
    return tenant_id


def _tenant_id_from_query(request: Any) -> str:
    """Read the stable camelCase tenant query parameter used by the provider API."""
    return str(request.query_params.get("tenantId") or "").strip()


def _ensure_tenant_access(context: Any, tenant_id: str) -> None:
    """Allow a Vault owner or the cross-tenant ``-1`` owner for this request."""
    requested_tenant_id = str(tenant_id or "").strip()
    configured_owner_tenant_id = context.provider_config.get("tenant_id")
    owner_tenant_id = (
        "-1" if configured_owner_tenant_id is None else str(configured_owner_tenant_id).strip()
    )
    if not requested_tenant_id:
        raise KnowledgeRuntimeError(422, "tenant_required", "tenantId is required")
    if not context.is_admin and requested_tenant_id != str(context.tenant_id or "").strip():
        raise KnowledgeRuntimeError(403, "tenant_access_denied", "Tenant access denied")
    if owner_tenant_id not in {"-1", requested_tenant_id}:
        raise KnowledgeRuntimeError(403, "vault_tenant_access_denied", "Vault tenant access denied")


async def create_knowledge_document(request: Any, context: Any) -> dict[str, Any]:
    """Create a complete Knowledge aggregate through the selected Vault instance.

    Args:
        request: Core-bounded multipart request containing metadata, content, and
            attachment parts.
        context: Authorized Provider HTTP context with instance config and actor tenant.

    Returns:
        Provider-owned aggregate metadata and generated Markdown.

    Raises:
        KnowledgeRuntimeError: If request parsing, tenant authorization, snapshot
            validation, conversion, or Vault persistence fails.
    """
    metadata, content, attachments = await _read_snapshot_parts(
        request,
        context.provider_config,
    )
    tenant_id = _prepare_metadata(metadata, context)
    converter = (
        build_knowledge_attachment_converter(context, context.provider_config)
        if attachments
        else None
    )
    result = await create_document(
        context.provider_config,
        metadata,
        content,
        attachments,
        converter,
    )
    logger.info(
        "Knowledge created: tenant=%s knowledge=%s provider=%s.%s",
        tenant_id,
        metadata.get("knowledgeId"),
        context.provider_type,
        context.provider_instance,
    )
    return result


async def update_knowledge_document(request: Any, context: Any) -> dict[str, Any]:
    """Replace a complete Knowledge aggregate in the selected Vault.

    Args:
        request: Core-bounded multipart request containing the full replacement snapshot.
        context: Authorized context whose path parameter supplies the stable identity.

    Returns:
        Provider-owned metadata and generated Markdown for the published replacement.

    Raises:
        KnowledgeRuntimeError: If parsing, tenant authorization, immutable identity,
            conversion, or Vault replacement checks fail.
    """
    metadata, content, attachments = await _read_snapshot_parts(
        request,
        context.provider_config,
    )
    knowledge_id = str(context.path_params.get("knowledge_id") or "")
    tenant_id = _prepare_metadata(metadata, context, knowledge_id=knowledge_id)
    converter = (
        build_knowledge_attachment_converter(context, context.provider_config)
        if attachments
        else None
    )
    result = await update_document(
        context.provider_config,
        metadata,
        content,
        attachments,
        converter,
    )
    logger.info(
        "Knowledge updated: tenant=%s knowledge=%s provider=%s.%s",
        tenant_id,
        knowledge_id,
        context.provider_type,
        context.provider_instance,
    )
    return result


async def get_knowledge_document(request: Any, context: Any) -> dict[str, Any]:
    """Read one safe published or unpublished aggregate from the selected Vault.

    Args:
        request: Bounded request whose ``tenantId`` query parameter selects the owner.
        context: Authorized context containing instance config and ``knowledge_id``.

    Returns:
        Safe manifest metadata and generated Markdown without original binaries.

    Raises:
        KnowledgeRuntimeError: If tenant access is denied, the document is missing,
            or its managed filesystem state fails validation.
    """
    tenant_id = _tenant_id_from_query(request)
    _ensure_tenant_access(context, tenant_id)
    return await get_document(
        context.provider_config,
        str(context.path_params.get("knowledge_id") or ""),
    )


async def delete_knowledge_document(request: Any, context: Any) -> dict[str, Any]:
    """Idempotently delete one aggregate from the selected Vault.

    Args:
        request: Bounded request whose ``tenantId`` query parameter selects the owner.
        context: Authorized context containing instance config and ``knowledge_id``.

    Returns:
        Success metadata indicating whether a published or unpublished aggregate existed.

    Raises:
        KnowledgeRuntimeError: If tenant access or managed path validation fails.
        OSError: If filesystem deletion cannot complete.
    """
    tenant_id = _tenant_id_from_query(request)
    knowledge_id = str(context.path_params.get("knowledge_id") or "")
    _ensure_tenant_access(context, tenant_id)
    result = await delete_document(context.provider_config, knowledge_id)
    logger.info(
        "Knowledge deleted: tenant=%s knowledge=%s provider=%s.%s",
        tenant_id,
        knowledge_id,
        context.provider_type,
        context.provider_instance,
    )
    return result


async def unpublish_knowledge_document(request: Any, context: Any) -> dict[str, Any]:
    """Remove one aggregate from retrieval while retaining converted content.

    Args:
        request: Bounded request whose ``tenantId`` query parameter selects the owner.
        context: Authorized context containing instance config and ``knowledge_id``.

    Returns:
        Retained aggregate metadata with unpublished status.

    Raises:
        KnowledgeRuntimeError: If tenant access, identity, hidden-path safety, or
            storage operations fail.
    """
    tenant_id = _tenant_id_from_query(request)
    knowledge_id = str(context.path_params.get("knowledge_id") or "")
    _ensure_tenant_access(context, tenant_id)
    result = await unpublish_document(context.provider_config, knowledge_id)
    logger.info(
        "Knowledge unpublished: tenant=%s knowledge=%s provider=%s.%s",
        tenant_id,
        knowledge_id,
        context.provider_type,
        context.provider_instance,
    )
    return result


async def query_knowledge_documents(request: Any, context: Any) -> dict[str, Any]:
    """Query published body and attachment Markdown in the selected Vault.

    Args:
        request: Core-bounded JSON request containing tenant, query, keyword, limit,
            and optional Knowledge identity filters.
        context: Authorized Provider HTTP context with the selected instance config.

    Returns:
        Bounded ranked results with parent-aware attachment citations.

    Raises:
        KnowledgeRuntimeError: If tenant access, JSON shape, query limits, work budget,
            or managed Vault content validation fails.
    """
    body = await _read_json_body(request)
    tenant_id = str(body.get("tenantId") or "").strip()
    _ensure_tenant_access(context, tenant_id)
    raw_query = body.get("query", "")
    if not isinstance(raw_query, str) or len(raw_query) > _MAX_QUERY_CHARS:
        raise KnowledgeRuntimeError(
            422,
            "invalid_query",
            f"query must be a string of at most {_MAX_QUERY_CHARS} characters",
        )
    raw_keywords = body.get("keywords", [])
    if not isinstance(raw_keywords, list):
        raise KnowledgeRuntimeError(422, "invalid_query", "keywords must be a list")
    if len(raw_keywords) > _MAX_KEYWORDS:
        raise KnowledgeRuntimeError(
            422,
            "invalid_query",
            f"keywords must contain at most {_MAX_KEYWORDS} items",
        )
    keywords: list[str] = []
    total_keyword_chars = 0
    for item in raw_keywords:
        if not isinstance(item, str):
            raise KnowledgeRuntimeError(
                422,
                "invalid_query",
                "keywords entries must be strings",
            )
        keyword = item.strip()
        if len(keyword) > _MAX_KEYWORD_CHARS:
            raise KnowledgeRuntimeError(
                422,
                "invalid_query",
                f"each keyword must be at most {_MAX_KEYWORD_CHARS} characters",
            )
        total_keyword_chars += len(keyword)
        if total_keyword_chars > _MAX_KEYWORDS_TOTAL_CHARS:
            raise KnowledgeRuntimeError(
                422,
                "invalid_query",
                f"keywords must total at most {_MAX_KEYWORDS_TOTAL_CHARS} characters",
            )
        if keyword:
            keywords.append(keyword)
    try:
        limit = int(body.get("limit", 10))
    except (TypeError, ValueError) as exc:
        raise KnowledgeRuntimeError(422, "invalid_query", "limit must be an integer") from exc
    if limit < 1 or limit > 50:
        raise KnowledgeRuntimeError(422, "invalid_query", "limit must be between 1 and 50")
    knowledge_id = str(body.get("knowledgeId") or "").strip() or None
    return await query_documents(
        context.provider_config,
        query=raw_query,
        keywords=keywords,
        limit=limit,
        knowledge_id=knowledge_id,
    )
