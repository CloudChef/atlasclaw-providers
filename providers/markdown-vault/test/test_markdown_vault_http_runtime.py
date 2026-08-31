"""HTTP-boundary tests for Markdown Vault Knowledge request limits."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient


PROVIDER_ROOT = Path(__file__).resolve().parents[1]


def _load_http_runtime() -> ModuleType:
    """Load the provider HTTP adapter with the package context used by Core."""
    package_name = "markdown_vault_http_runtime_test"
    package = ModuleType(package_name)
    package.__path__ = [str(PROVIDER_ROOT)]  # type: ignore[attr-defined]
    sys.modules[package_name] = package
    module_name = f"{package_name}.http_runtime"
    spec = importlib.util.spec_from_file_location(module_name, PROVIDER_ROOT / "http_runtime.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


http_runtime = _load_http_runtime()


def _error_response(error: Exception) -> JSONResponse:
    """Expose the provider's structured error during boundary tests."""
    return JSONResponse(
        {"code": getattr(error, "code", "unexpected")},
        status_code=int(getattr(error, "status_code", 500)),
    )


def _multipart_client() -> TestClient:
    """Create a minimal Starlette app around the provider multipart parser."""

    async def parse_snapshot(request: Request) -> JSONResponse:
        try:
            await http_runtime._read_snapshot_parts(
                request,
                {
                    "max_attachments": 2,
                    "max_attachment_bytes": 2 * 1024 * 1024,
                    "max_total_attachment_bytes": 4 * 1024 * 1024,
                },
            )
        except Exception as error:
            return _error_response(error)
        return JSONResponse({"ok": True})

    return TestClient(Starlette(routes=[Route("/snapshot", parse_snapshot, methods=["POST"])]))


def test_multipart_rejects_oversized_ordinary_metadata_field() -> None:
    """Verify a non-file field cannot consume the configured attachment allowance."""
    with _multipart_client() as client:
        response = client.post(
            "/snapshot",
            files=[
                ("metadata", (None, "x" * (1024 * 1024 + 1))),
                ("content", (None, "body")),
            ],
        )

    assert response.status_code == 413
    assert response.json()["code"] == "multipart_limit_exceeded"


@pytest.mark.parametrize("attachment", [(None, "not-a-file"), ("", "empty-name")])
def test_multipart_rejects_attachment_without_filename_before_buffering(
    attachment: tuple[str | None, str],
) -> None:
    """Verify attachment fields require a non-empty file disposition filename."""
    with _multipart_client() as client:
        response = client.post(
            "/snapshot",
            files=[
                ("metadata", (None, json.dumps({"title": "sample"}))),
                ("content", (None, "body")),
                ("attachment_file-1", attachment),
            ],
        )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_multipart"


@pytest.mark.parametrize(
    "payload",
    [
        {"tenantId": "tenant-a", "query": "x" * 4097, "keywords": []},
        {"tenantId": "tenant-a", "query": "x", "keywords": ["k"] * 51},
        {"tenantId": "tenant-a", "query": "x", "keywords": [7]},
        {
            "tenantId": "tenant-a",
            "query": "".join(chr(0x4E00 + index) for index in range(300)),
            "keywords": [],
        },
        {
            "tenantId": "tenant-a",
            "query": "find",
            "keywords": [
                f"shared alpha beta gamma delta epsilon term{index}"
                for index in range(50)
            ],
        },
    ],
)
def test_query_rejects_unbounded_search_work(payload: dict[str, Any]) -> None:
    """Verify a small JSON body cannot amplify into unbounded Vault scoring work."""
    context = SimpleNamespace(
        is_admin=True,
        tenant_id="tenant-a",
        provider_config={"tenant_id": "tenant-a"},
        path_params={},
    )

    async def query(request: Request) -> JSONResponse:
        try:
            await http_runtime.query_knowledge_documents(request, context)
        except Exception as error:
            return _error_response(error)
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/query", query, methods=["POST"])])
    with TestClient(app) as client:
        response = client.post("/query", json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_query"


@pytest.mark.parametrize(
    ("owner_tenant_id", "requested_tenant_id"),
    [("tenant-a", "tenant-a"), ("-1", "tenant-a"), ("-1", "tenant-b")],
)
def test_vault_tenant_owner_accepts_own_or_cross_tenant_requests(
    owner_tenant_id: str,
    requested_tenant_id: str,
) -> None:
    """Verify Vault ownership, rather than Knowledge metadata, defines tenant scope."""
    context = SimpleNamespace(
        is_admin=True,
        tenant_id="agent-admin",
        provider_config={"tenant_id": owner_tenant_id},
    )

    http_runtime._ensure_tenant_access(context, requested_tenant_id)


def test_tenant_owned_vault_rejects_a_different_tenant() -> None:
    """Verify an administrator request cannot publish into another tenant's Vault."""
    context = SimpleNamespace(
        is_admin=True,
        tenant_id="agent-admin",
        provider_config={"tenant_id": "tenant-a"},
    )

    with pytest.raises(http_runtime.KnowledgeRuntimeError) as error:
        http_runtime._ensure_tenant_access(context, "tenant-b")

    assert error.value.status_code == 403
    assert error.value.code == "vault_tenant_access_denied"
