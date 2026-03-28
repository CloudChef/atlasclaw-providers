from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().with_name("run_e2e_tests.py")
SPEC = importlib.util.spec_from_file_location("run_e2e_tests", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
run_e2e_tests = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run_e2e_tests)


def test_default_cookie_fallback_does_not_enable_live_smoke(monkeypatch):
    for name in (
        "CMP_COOKIE",
        "CMP_USERNAME",
        "CMP_PASSWORD",
        "CMP_AUTH_URL",
        "ATLASCLAW_PROVIDER_CONFIG",
        "ATLASCLAW_COOKIES",
    ):
        monkeypatch.delenv(name, raising=False)

    fallback_cookie = run_e2e_tests.resolve_cookie(None)

    assert fallback_cookie == run_e2e_tests.DEFAULT_COOKIE
    assert run_e2e_tests.compute_live_smoke_available(None) is False


def test_username_and_password_enable_live_smoke(monkeypatch):
    monkeypatch.delenv("CMP_COOKIE", raising=False)
    monkeypatch.setenv("CMP_USERNAME", "admin")
    monkeypatch.setenv("CMP_PASSWORD", "secret")
    monkeypatch.delenv("ATLASCLAW_PROVIDER_CONFIG", raising=False)
    monkeypatch.delenv("ATLASCLAW_COOKIES", raising=False)

    assert run_e2e_tests.compute_live_smoke_available(None) is True


def test_explicit_cookie_enables_live_smoke(monkeypatch):
    for name in (
        "CMP_COOKIE",
        "CMP_USERNAME",
        "CMP_PASSWORD",
        "CMP_AUTH_URL",
        "ATLASCLAW_PROVIDER_CONFIG",
        "ATLASCLAW_COOKIES",
    ):
        monkeypatch.delenv(name, raising=False)

    assert run_e2e_tests.compute_live_smoke_available("CloudChef-Authenticate=test") is True
