# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.
"""Provider document store CRUD and filtering."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from store import DocumentStore  # noqa: E402


def _document(document_id: str = "doc-1", **overrides) -> dict:
    document = {
        "id": document_id,
        "user_id": "alice",
        "tenant_id": "default",
        "file_name": "RPT-2026-0214.pdf",
        "file_path": f"/tmp/{document_id}/original.pdf",
        "extension": ".pdf",
        "size": 2048,
        "sha256": "a" * 64,
        "pages": 3,
        "report_no": "RPT-2026-0214",
        "status": "pending",
    }
    document.update(overrides)
    return document


def test_create_get_and_ownership(tmp_path: Path) -> None:
    store = DocumentStore(tmp_path)
    created = store.create(_document())

    assert created["id"] == "doc-1"
    assert created["status"] == "pending"
    assert store.get("doc-1", "alice")["file_name"] == "RPT-2026-0214.pdf"
    assert store.get("doc-1", "bob") is None


def test_list_filters_and_pagination(tmp_path: Path) -> None:
    store = DocumentStore(tmp_path)
    store.create(_document("doc-1", report_no="RPT-2026-0001", status="completed"))
    store.create(_document("doc-2", file_name="word.docx", report_no="JC-2026-7654321A", status="running"))
    store.create(_document("doc-3", report_no="RPT-2026-0003", status="pending"))

    all_items = store.list("alice")
    assert all_items["total"] == 3
    assert len(all_items["items"]) == 3

    running = store.list("alice", status="running")
    assert running["total"] == 1
    assert running["items"][0]["id"] == "doc-2"

    searched = store.list("alice", query="JC-2026")
    assert searched["total"] == 1

    page = store.list("alice", page=2, page_size=2)
    assert page["page"] == 2
    assert len(page["items"]) == 1


def test_update_progress_and_result(tmp_path: Path) -> None:
    store = DocumentStore(tmp_path)
    store.create(_document())

    updated = store.update(
        "doc-1",
        status="completed",
        progress=100,
        findings_total=13,
        findings_review=4,
        grade_summary={"A": 9, "B": 4},
        report_path="/tmp/report.html",
    )

    assert updated["status"] == "completed"
    assert updated["findings_total"] == 13
    assert updated["grade_summary"] == {"A": 9, "B": 4}


def test_has_running_and_delete(tmp_path: Path) -> None:
    store = DocumentStore(tmp_path)
    store.create(_document("doc-1", status="running"))

    assert store.has_running("alice") is True
    assert store.has_running("bob") is False
    assert store.delete("doc-1", "bob") is False
    assert store.delete("doc-1", "alice") is True
    assert store.get("doc-1", "alice") is None
