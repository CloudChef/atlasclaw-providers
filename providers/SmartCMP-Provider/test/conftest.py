"""Shared isolation fixtures for SmartCMP Provider tests."""

from __future__ import annotations

import inspect
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest
import requests

_PROVIDER_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_PROVIDER_SRC) not in sys.path:
    sys.path.insert(0, str(_PROVIDER_SRC))

_ATLASCLAW_ROOT = Path(__file__).resolve().parents[4] / "atlasclaw"
if str(_ATLASCLAW_ROOT) not in sys.path:
    sys.path.insert(0, str(_ATLASCLAW_ROOT))

_ADAPTER_HELPER_MODULES = {
    "_approval_context",
    "_approval_decision_adapter",
    "_approval_object_actions",
    "_approval_specs",
    "_approval_validation",
    "_common",
    "_object_actions_common",
    "_preapproval_analysis",
    "_provider_bootstrap",
    "_request_object_actions",
    "_resource_object_actions",
    "list_resource_operations",
}


def install_legacy_httpx_bridge(
    monkeypatch: pytest.MonkeyPatch,
    *,
    fake_get: Callable[..., Any],
    fake_post: Callable[..., Any],
) -> None:
    """Route SmartCMP Provider HTTPX calls through existing adapter test doubles.

    Step 3 intentionally removes runtime ``requests`` calls. This test-only
    bridge lets the established script assertions observe the same URL, headers,
    parameters, and JSON body at the new HTTPX transport boundary.
    """

    async def fake_request(
        _client: httpx.AsyncClient,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> Any:
        handler = fake_get if method.upper() == "GET" else fake_post
        legacy_kwargs = {
            "headers": kwargs.get("headers"),
            "params": kwargs.get("params"),
            "json": kwargs.get("json"),
            "verify": False,
            "timeout": kwargs.get("timeout"),
        }
        signature = inspect.signature(handler)
        accepts_kwargs = any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        if not accepts_kwargs:
            legacy_kwargs = {
                name: value
                for name, value in legacy_kwargs.items()
                if name in signature.parameters
            }
        try:
            return handler(str(url), **legacy_kwargs)
        except requests.Timeout as exc:
            raise httpx.ReadTimeout(
                str(exc),
                request=httpx.Request(method, str(url)),
            ) from exc
        except requests.RequestException as exc:
            raise httpx.ConnectError(
                str(exc),
                request=httpx.Request(method, str(url)),
            ) from exc

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)


@pytest.fixture
def isolated_provider_import_state() -> Iterator[None]:
    """Restore SmartCMP Provider modules and import paths after an adapter test.

    AtlasClaw entrypoints intentionally bootstrap the co-located ``src`` tree.
    Tests that import those scripts must not leave that process-local state
    behind for bootstrap or package-isolation tests that run later.
    """

    original_path = list(sys.path)
    original_modules = {
        name: module
        for name, module in sys.modules.items()
        if name in _ADAPTER_HELPER_MODULES
        or name == "smartcmp_provider"
        or name.startswith("smartcmp_provider.")
    }
    try:
        yield
    finally:
        for module_name in list(sys.modules):
            if (
                module_name in _ADAPTER_HELPER_MODULES
                or module_name == "smartcmp_provider"
                or module_name.startswith("smartcmp_provider.")
            ):
                sys.modules.pop(module_name, None)
        sys.modules.update(original_modules)
        sys.path[:] = original_path
