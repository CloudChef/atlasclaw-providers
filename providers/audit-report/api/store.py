# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.
"""SQLite index for provider-owned audit documents."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_documents (
  id              TEXT PRIMARY KEY,
  user_id         TEXT NOT NULL,
  tenant_id       TEXT NOT NULL DEFAULT '',
  file_name       TEXT NOT NULL,
  file_path       TEXT NOT NULL,
  extension       TEXT NOT NULL,
  size            INTEGER NOT NULL,
  sha256          TEXT NOT NULL,
  pages           INTEGER,
  report_no       TEXT,
  status          TEXT NOT NULL,
  run_id          TEXT,
  progress        INTEGER NOT NULL DEFAULT 0,
  progress_text   TEXT NOT NULL DEFAULT '',
  findings_total  INTEGER NOT NULL DEFAULT 0,
  findings_review INTEGER NOT NULL DEFAULT 0,
  grade_summary   TEXT,
  report_path     TEXT,
  report_name     TEXT,
  error_code      TEXT,
  error_message   TEXT,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_audit_documents_owner
  ON audit_documents(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_audit_documents_status
  ON audit_documents(user_id, status);
"""


def _now() -> str:
    """Return a UTC ISO timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _row_to_document(row: sqlite3.Row) -> dict[str, Any]:
    """Convert one SQLite row into a JSON-safe document record."""
    document = dict(row)
    raw_summary = document.get("grade_summary")
    if raw_summary:
        try:
            document["grade_summary"] = json.loads(raw_summary)
        except (TypeError, ValueError):
            document["grade_summary"] = {}
    else:
        document["grade_summary"] = {}
    return document


class DocumentStore:
    """Provider-private document index stored next to the provider data files."""

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "audit.db"
        self._init()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _init(self) -> None:
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    def create(self, document: dict[str, Any]) -> dict[str, Any]:
        """Insert one document record and return it."""
        now = _now()
        record = {
            "id": document.get("id") or uuid.uuid4().hex,
            "user_id": document["user_id"],
            "tenant_id": document.get("tenant_id", ""),
            "file_name": document["file_name"],
            "file_path": document["file_path"],
            "extension": document["extension"],
            "size": int(document.get("size") or 0),
            "sha256": document["sha256"],
            "pages": document.get("pages"),
            "report_no": document.get("report_no") or "",
            "status": document.get("status") or "pending",
            "run_id": document.get("run_id") or "",
            "progress": int(document.get("progress") or 0),
            "progress_text": document.get("progress_text") or "",
            "findings_total": int(document.get("findings_total") or 0),
            "findings_review": int(document.get("findings_review") or 0),
            "grade_summary": json.dumps(document.get("grade_summary") or {}, ensure_ascii=False),
            "report_path": document.get("report_path") or "",
            "report_name": document.get("report_name") or "",
            "error_code": document.get("error_code") or "",
            "error_message": document.get("error_message") or "",
            "created_at": now,
            "updated_at": now,
        }
        columns = ", ".join(record.keys())
        placeholders = ", ".join("?" for _ in record)
        with self._connect() as connection:
            connection.execute(
                f"INSERT INTO audit_documents ({columns}) VALUES ({placeholders})",
                tuple(record.values()),
            )
        return self.get(record["id"], record["user_id"]) or record

    def get(self, document_id: str, user_id: str) -> Optional[dict[str, Any]]:
        """Return one document owned by the user."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM audit_documents WHERE id = ? AND user_id = ?",
                (document_id, user_id),
            ).fetchone()
        return _row_to_document(row) if row is not None else None

    def list(
        self,
        user_id: str,
        *,
        query: str = "",
        status: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """Return a filtered, paginated document list."""
        page = max(1, int(page or 1))
        page_size = max(1, min(int(page_size or 20), 100))
        where = ["user_id = ?"]
        params: list[Any] = [user_id]
        if status:
            where.append("status = ?")
            params.append(status)
        normalized_query = str(query or "").strip()
        if normalized_query:
            where.append("(file_name LIKE ? OR report_no LIKE ?)")
            like = f"%{normalized_query}%"
            params.extend([like, like])
        where_sql = " AND ".join(where)
        with self._connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM audit_documents WHERE {where_sql}",
                tuple(params),
            ).fetchone()[0]
            rows = connection.execute(
                f"SELECT * FROM audit_documents WHERE {where_sql} "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                tuple(params + [page_size, (page - 1) * page_size]),
            ).fetchall()
        return {
            "items": [_row_to_document(row) for row in rows],
            "total": int(total),
            "page": page,
            "page_size": page_size,
        }

    def update(self, document_id: str, **fields: Any) -> Optional[dict[str, Any]]:
        """Update mutable document fields."""
        if not fields:
            return None
        if "grade_summary" in fields and not isinstance(fields["grade_summary"], str):
            fields["grade_summary"] = json.dumps(fields["grade_summary"] or {}, ensure_ascii=False)
        fields["updated_at"] = _now()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE audit_documents SET {assignments} WHERE id = ?",
                tuple(list(fields.values()) + [document_id]),
            )
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM audit_documents WHERE id = ?", (document_id,),
            ).fetchone()
        return _row_to_document(row) if row is not None else None

    def has_running(self, user_id: str) -> bool:
        """Return whether the user already has a running audit."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM audit_documents WHERE user_id = ? AND status = 'running' LIMIT 1",
                (user_id,),
            ).fetchone()
        return row is not None

    def delete(self, document_id: str, user_id: str) -> bool:
        """Delete one owned document row."""
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM audit_documents WHERE id = ? AND user_id = ?",
                (document_id, user_id),
            )
            return cursor.rowcount > 0
