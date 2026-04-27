# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

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


def test_extract_meta_list_supports_catalog_envelope():
    payload = {
        "internal_request_trace_id": "trace-1",
        "catalogs": [
            {"index": 1, "id": "catalog-1", "name": "LinuxOS"},
            {"index": 2, "id": "catalog-2", "name": "工单"},
        ],
    }

    catalogs = run_e2e_tests.extract_meta_list(payload, "catalogs")

    assert len(catalogs) == 2
    assert catalogs[0]["id"] == "catalog-1"


def test_extract_meta_list_preserves_raw_list_payload():
    payload = [{"id": "item-1"}, {"id": "item-2"}]

    items = run_e2e_tests.extract_meta_list(payload, "catalogs")

    assert len(items) == 2
    assert items[1]["id"] == "item-2"


def test_collect_skill_python_files_discovers_current_layout(tmp_path, monkeypatch):
    provider_root = tmp_path / "provider"
    (provider_root / "skills" / "datasource" / "scripts").mkdir(parents=True)
    (provider_root / "skills" / "request" / "scripts").mkdir(parents=True)
    (provider_root / "skills" / "datasource" / "scripts" / "a.py").write_text("", encoding="utf-8")
    (provider_root / "skills" / "request" / "scripts" / "b.py").write_text("", encoding="utf-8")

    monkeypatch.setattr(run_e2e_tests, "PROVIDER_ROOT", provider_root)

    assert run_e2e_tests.collect_skill_python_files() == [
        "skills/datasource/scripts/a.py",
        "skills/request/scripts/b.py",
    ]


def test_collect_reference_markdown_files_discovers_existing_refs(tmp_path, monkeypatch):
    provider_root = tmp_path / "provider"
    (provider_root / "skills" / "alarm" / "references").mkdir(parents=True)
    (provider_root / "skills" / "request").mkdir(parents=True)
    (provider_root / "skills" / "alarm" / "references" / "WORKFLOW.md").write_text(
        "# workflow",
        encoding="utf-8",
    )
    (provider_root / "skills" / "request" / "SKILL.md").write_text("# skill", encoding="utf-8")

    monkeypatch.setattr(run_e2e_tests, "PROVIDER_ROOT", provider_root)

    assert run_e2e_tests.collect_reference_markdown_files() == [
        "skills/alarm/references/WORKFLOW.md",
    ]
