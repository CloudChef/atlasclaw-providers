"""Provider-owned SQLite/MySQL index storage for Markdown vault search."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import sqlite3
from typing import Any, Protocol

from _config import MarkdownVaultConfig
from _parser import VaultDocument, normalize_terms


@dataclass(frozen=True)
class IndexStatus:
    """Current indexed-vs-vault status for one provider instance."""

    index_built: bool
    stale: bool
    indexed_documents: int
    indexed_chunks: int
    current_documents: int
    changed_paths: list[str]
    deleted_paths: list[str]


class IndexStore(Protocol):
    """Common storage contract used by runtime tools and the offline admin script."""

    def ensure_schema(self) -> None:
        """Create provider-owned index tables when they do not exist."""

    def is_index_built(self) -> bool:
        """Return whether index tables already exist without creating them."""

    def replace_index(self, documents: list[VaultDocument]) -> None:
        """Replace all indexed rows for one provider instance with parsed documents."""

    def status(self, current_state: dict[str, tuple[int, int, str]]) -> IndexStatus:
        """Compare indexed document state with the current vault file state."""

    def search(
        self,
        query: str,
        *,
        limit: int,
        path_filter: str | None,
        tag_filter: str | None,
        current_state: dict[str, tuple[int, int, str]],
    ) -> dict[str, Any]:
        """Search indexed terms and return cited Markdown chunks."""


def open_index_store(config: MarkdownVaultConfig) -> IndexStore:
    """Open the configured SQLite or MySQL index store."""

    if config.index_backend == "sqlite":
        return SQLiteIndexStore(config)
    return MySQLIndexStore(config)


def mysql_schema_statements(table_prefix: str = "markdown_vault_") -> list[str]:
    """Return MySQL DDL statements for provider-owned index tables."""

    tables = _TableNames(table_prefix)
    return [
        f"""
CREATE TABLE IF NOT EXISTS `{tables.documents}` (
  `instance_id` VARCHAR(191) NOT NULL,
  `document_id` CHAR(40) NOT NULL,
  `path` TEXT NOT NULL,
  `title` TEXT NOT NULL,
  `aliases_json` JSON NOT NULL,
  `tags_json` JSON NOT NULL,
  `links_json` JSON NOT NULL,
  `mtime_ns` BIGINT NOT NULL,
  `size_bytes` BIGINT NOT NULL,
  `content_hash` CHAR(40) NOT NULL,
  `indexed_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`instance_id`, `document_id`),
  KEY `idx_{tables.documents}_instance` (`instance_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""".strip(),
        f"""
CREATE TABLE IF NOT EXISTS `{tables.chunks}` (
  `instance_id` VARCHAR(191) NOT NULL,
  `chunk_id` CHAR(40) NOT NULL,
  `document_id` CHAR(40) NOT NULL,
  `path` TEXT NOT NULL,
  `heading_path_json` JSON NOT NULL,
  `start_line` INT NOT NULL,
  `end_line` INT NOT NULL,
  `text` MEDIUMTEXT NOT NULL,
  `content_hash` CHAR(40) NOT NULL,
  PRIMARY KEY (`instance_id`, `chunk_id`),
  KEY `idx_{tables.chunks}_document` (`instance_id`, `document_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""".strip(),
        f"""
CREATE TABLE IF NOT EXISTS `{tables.terms}` (
  `instance_id` VARCHAR(191) NOT NULL,
  `term` VARCHAR(191) NOT NULL,
  `chunk_id` CHAR(40) NOT NULL,
  `weight` DOUBLE NOT NULL,
  PRIMARY KEY (`instance_id`, `term`, `chunk_id`),
  KEY `idx_{tables.terms}_chunk` (`instance_id`, `chunk_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""".strip(),
    ]


class SQLiteIndexStore:
    """SQLite-backed implementation for local single-file Markdown vault indexes."""

    def __init__(self, config: MarkdownVaultConfig) -> None:
        self.config = config
        if config.index_path is None:
            raise ValueError("SQLite index_path is required.")
        self.index_path = config.index_path
        self.tables = _TableNames(config.table_prefix)

    def ensure_schema(self) -> None:
        """Create SQLite index tables when they do not exist."""

        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            for statement in _sqlite_schema_statements(self.tables):
                conn.execute(statement)
            conn.commit()

    def is_index_built(self) -> bool:
        """Return whether SQLite index tables already exist."""

        if not self.index_path.exists():
            return False
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN (?, ?, ?)",
                (self.tables.documents, self.tables.chunks, self.tables.terms),
            ).fetchall()
        return {row[0] for row in rows} == {
            self.tables.documents,
            self.tables.chunks,
            self.tables.terms,
        }

    def replace_index(self, documents: list[VaultDocument]) -> None:
        """Replace indexed SQLite rows for this provider instance in one transaction."""

        self.ensure_schema()
        with self._connect() as conn:
            conn.execute("BEGIN")
            for table in (self.tables.terms, self.tables.chunks, self.tables.documents):
                conn.execute(f"DELETE FROM {table} WHERE instance_id = ?", (self.config.instance_id,))
            _insert_documents(conn, self.tables, "?", self.config.instance_id, documents)
            conn.commit()

    def status(self, current_state: dict[str, tuple[int, int, str]]) -> IndexStatus:
        """Compare SQLite index metadata with the current vault state."""

        if not self.is_index_built():
            return IndexStatus(
                index_built=False,
                stale=False,
                indexed_documents=0,
                indexed_chunks=0,
                current_documents=len(current_state),
                changed_paths=[],
                deleted_paths=[],
            )
        with self._connect() as conn:
            documents = _fetch_document_state(conn, self.tables, "?", self.config.instance_id)
            chunk_count = _fetch_chunk_count(conn, self.tables, "?", self.config.instance_id)
        return _build_status(documents, current_state, chunk_count)

    def search(
        self,
        query: str,
        *,
        limit: int,
        path_filter: str | None,
        tag_filter: str | None,
        current_state: dict[str, tuple[int, int, str]],
    ) -> dict[str, Any]:
        """Search SQLite indexed terms and return ranked Markdown chunks."""

        if not self.is_index_built():
            return _index_not_built_response()
        index_status = self.status(current_state)
        terms = sorted(set(normalize_terms(query)))
        if not terms:
            return _search_response(index_status, [])
        with self._connect() as conn:
            chunk_scores = _query_chunk_scores(
                conn,
                self.tables,
                "?",
                self.config.instance_id,
                terms,
                max(limit * 8, 40),
                path_filter=path_filter,
                tag_filter=tag_filter,
            )
            results = _fetch_results_for_scores(
                conn,
                self.tables,
                "?",
                self.config.instance_id,
                chunk_scores,
                limit=limit,
                path_filter=path_filter,
                tag_filter=tag_filter,
            )
        return _search_response(index_status, results)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.index_path)
        conn.row_factory = sqlite3.Row
        return conn


class MySQLIndexStore:
    """MySQL-backed implementation for shared Markdown vault indexes."""

    def __init__(self, config: MarkdownVaultConfig) -> None:
        self.config = config
        self.tables = _TableNames(config.table_prefix)

    def ensure_schema(self) -> None:
        """Create MySQL index tables when they do not exist."""

        with self._connect() as conn:
            with conn.cursor() as cursor:
                for statement in mysql_schema_statements(self.config.table_prefix):
                    cursor.execute(statement)
            conn.commit()

    def is_index_built(self) -> bool:
        """Return whether MySQL index tables already exist."""

        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = %s AND table_name IN (%s, %s, %s)
                    """,
                    (
                        self.config.mysql_database,
                        self.tables.documents,
                        self.tables.chunks,
                        self.tables.terms,
                    ),
                )
                rows = cursor.fetchall()
        return {row[0] for row in rows} == {
            self.tables.documents,
            self.tables.chunks,
            self.tables.terms,
        }

    def replace_index(self, documents: list[VaultDocument]) -> None:
        """Replace indexed MySQL rows for this provider instance in one transaction."""

        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cursor:
                for table in (self.tables.terms, self.tables.chunks, self.tables.documents):
                    cursor.execute(f"DELETE FROM `{table}` WHERE instance_id = %s", (self.config.instance_id,))
                _insert_documents(cursor, self.tables, "%s", self.config.instance_id, documents, quote_names=True)
            conn.commit()

    def status(self, current_state: dict[str, tuple[int, int, str]]) -> IndexStatus:
        """Compare MySQL index metadata with the current vault state."""

        if not self.is_index_built():
            return IndexStatus(
                index_built=False,
                stale=False,
                indexed_documents=0,
                indexed_chunks=0,
                current_documents=len(current_state),
                changed_paths=[],
                deleted_paths=[],
            )
        with self._connect() as conn:
            with conn.cursor() as cursor:
                documents = _fetch_document_state(
                    cursor,
                    self.tables,
                    "%s",
                    self.config.instance_id,
                    quote_names=True,
                )
                chunk_count = _fetch_chunk_count(
                    cursor,
                    self.tables,
                    "%s",
                    self.config.instance_id,
                    quote_names=True,
                )
        return _build_status(documents, current_state, chunk_count)

    def search(
        self,
        query: str,
        *,
        limit: int,
        path_filter: str | None,
        tag_filter: str | None,
        current_state: dict[str, tuple[int, int, str]],
    ) -> dict[str, Any]:
        """Search MySQL indexed terms and return ranked Markdown chunks."""

        if not self.is_index_built():
            return _index_not_built_response()
        index_status = self.status(current_state)
        terms = sorted(set(normalize_terms(query)))
        if not terms:
            return _search_response(index_status, [])
        with self._connect() as conn:
            with conn.cursor() as cursor:
                chunk_scores = _query_chunk_scores(
                    cursor,
                    self.tables,
                    "%s",
                    self.config.instance_id,
                    terms,
                    max(limit * 8, 40),
                    path_filter=path_filter,
                    tag_filter=tag_filter,
                    quote_names=True,
                )
                results = _fetch_results_for_scores(
                    cursor,
                    self.tables,
                    "%s",
                    self.config.instance_id,
                    chunk_scores,
                    limit=limit,
                    path_filter=path_filter,
                    tag_filter=tag_filter,
                    quote_names=True,
                )
        return _search_response(index_status, results)

    def _connect(self) -> Any:
        try:
            import pymysql
        except ImportError as exc:
            raise RuntimeError(
                "MySQL backend requires PyMySQL, which is installed with the AtlasClaw aiomysql dependency."
            ) from exc
        ssl = {} if self.config.mysql_tls else None
        return pymysql.connect(
            host=self.config.mysql_host,
            port=self.config.mysql_port,
            user=self.config.mysql_user,
            password=self.config.mysql_password,
            database=self.config.mysql_database,
            charset=self.config.mysql_charset,
            ssl=ssl,
            autocommit=False,
        )


@dataclass(frozen=True)
class _TableNames:
    documents: str
    chunks: str
    terms: str

    def __init__(self, prefix: str) -> None:
        object.__setattr__(self, "documents", f"{prefix}documents")
        object.__setattr__(self, "chunks", f"{prefix}chunks")
        object.__setattr__(self, "terms", f"{prefix}terms")


def _sqlite_schema_statements(tables: _TableNames) -> list[str]:
    return [
        f"""
CREATE TABLE IF NOT EXISTS {tables.documents} (
  instance_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  path TEXT NOT NULL,
  title TEXT NOT NULL,
  aliases_json TEXT NOT NULL,
  tags_json TEXT NOT NULL,
  links_json TEXT NOT NULL,
  mtime_ns INTEGER NOT NULL,
  size_bytes INTEGER NOT NULL,
  content_hash TEXT NOT NULL,
  indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (instance_id, document_id)
)
""".strip(),
        f"""
CREATE TABLE IF NOT EXISTS {tables.chunks} (
  instance_id TEXT NOT NULL,
  chunk_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  path TEXT NOT NULL,
  heading_path_json TEXT NOT NULL,
  start_line INTEGER NOT NULL,
  end_line INTEGER NOT NULL,
  text TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  PRIMARY KEY (instance_id, chunk_id)
)
""".strip(),
        f"""
CREATE TABLE IF NOT EXISTS {tables.terms} (
  instance_id TEXT NOT NULL,
  term TEXT NOT NULL,
  chunk_id TEXT NOT NULL,
  weight REAL NOT NULL,
  PRIMARY KEY (instance_id, term, chunk_id)
)
""".strip(),
        f"CREATE INDEX IF NOT EXISTS idx_{tables.terms}_term ON {tables.terms} (instance_id, term)",
        f"CREATE INDEX IF NOT EXISTS idx_{tables.chunks}_doc ON {tables.chunks} (instance_id, document_id)",
    ]


def _insert_documents(
    executor: Any,
    tables: _TableNames,
    placeholder: str,
    instance_id: str,
    documents: list[VaultDocument],
    *,
    quote_names: bool = False,
) -> None:
    documents_table = _table_name(tables.documents, quote_names)
    chunks_table = _table_name(tables.chunks, quote_names)
    terms_table = _table_name(tables.terms, quote_names)
    for document in documents:
        document_id = _document_id(document.path)
        executor.execute(
            f"""
            INSERT INTO {documents_table}
            (instance_id, document_id, path, title, aliases_json, tags_json, links_json,
             mtime_ns, size_bytes, content_hash)
            VALUES ({_placeholders(10, placeholder)})
            """,
            (
                instance_id,
                document_id,
                document.path,
                document.title,
                json.dumps(document.aliases, ensure_ascii=False),
                json.dumps(document.tags, ensure_ascii=False),
                json.dumps([reference.__dict__ for reference in document.links], ensure_ascii=False),
                document.mtime_ns,
                document.size_bytes,
                document.content_hash,
            ),
        )
        for chunk in document.chunks:
            executor.execute(
                f"""
                INSERT INTO {chunks_table}
                (instance_id, chunk_id, document_id, path, heading_path_json,
                 start_line, end_line, text, content_hash)
                VALUES ({_placeholders(9, placeholder)})
                """,
                (
                    instance_id,
                    chunk.chunk_id,
                    document_id,
                    chunk.path,
                    json.dumps(chunk.heading_path, ensure_ascii=False),
                    chunk.start_line,
                    chunk.end_line,
                    chunk.text,
                    chunk.content_hash,
                ),
            )
            term_rows = [
                (instance_id, term, chunk.chunk_id, weight)
                for term, weight in chunk.terms.items()
            ]
            if term_rows:
                executor.executemany(
                    f"""
                    INSERT INTO {terms_table}
                    (instance_id, term, chunk_id, weight)
                    VALUES ({_placeholders(4, placeholder)})
                    """,
                    term_rows,
                )


def _fetch_document_state(
    executor: Any,
    tables: _TableNames,
    placeholder: str,
    instance_id: str,
    *,
    quote_names: bool = False,
) -> dict[str, tuple[int, int, str]]:
    table = _table_name(tables.documents, quote_names)
    rows = _execute_fetchall(
        executor,
        f"SELECT path, mtime_ns, size_bytes, content_hash FROM {table} WHERE instance_id = {placeholder}",
        (instance_id,),
    )
    return {str(row[0]): (int(row[1]), int(row[2]), str(row[3])) for row in rows}


def _fetch_chunk_count(
    executor: Any,
    tables: _TableNames,
    placeholder: str,
    instance_id: str,
    *,
    quote_names: bool = False,
) -> int:
    table = _table_name(tables.chunks, quote_names)
    row = _execute_fetchone(
        executor,
        f"SELECT COUNT(*) FROM {table} WHERE instance_id = {placeholder}",
        (instance_id,),
    )
    return int(row[0]) if row else 0


def _query_chunk_scores(
    executor: Any,
    tables: _TableNames,
    placeholder: str,
    instance_id: str,
    terms: list[str],
    candidate_limit: int,
    *,
    path_filter: str | None = None,
    tag_filter: str | None = None,
    quote_names: bool = False,
) -> list[tuple[str, float]]:
    terms_table = _table_name(tables.terms, quote_names)
    chunks_table = _table_name(tables.chunks, quote_names)
    documents_table = _table_name(tables.documents, quote_names)
    term_placeholders = ", ".join([placeholder] * len(terms))
    where_clauses = [
        f"t.instance_id = {placeholder}",
        f"t.term IN ({term_placeholders})",
    ]
    params: list[Any] = [instance_id, *terms]
    path_filter_normalized = (path_filter or "").strip().lower()
    if path_filter_normalized:
        where_clauses.append(f"LOWER(c.path) LIKE {placeholder} ESCAPE '\\'")
        params.append(_like_contains_param(path_filter_normalized))
    requested_tags = sorted(_parse_tag_filter(tag_filter))
    if requested_tags:
        where_clauses.append(
            "("
            + " OR ".join([f"LOWER(d.tags_json) LIKE {placeholder} ESCAPE '\\'" for _ in requested_tags])
            + ")"
        )
        params.extend(_like_contains_param(json.dumps(tag, ensure_ascii=False)) for tag in requested_tags)
    rows = _execute_fetchall(
        executor,
        f"""
        SELECT t.chunk_id, SUM(t.weight) AS score
        FROM {terms_table} t
        JOIN {chunks_table} c
          ON t.instance_id = c.instance_id AND t.chunk_id = c.chunk_id
        JOIN {documents_table} d
          ON c.instance_id = d.instance_id AND c.document_id = d.document_id
        WHERE {" AND ".join(where_clauses)}
        GROUP BY t.chunk_id
        ORDER BY score DESC
        LIMIT {int(candidate_limit)}
        """,
        tuple(params),
    )
    return [(str(row[0]), float(row[1])) for row in rows]


def _fetch_results_for_scores(
    executor: Any,
    tables: _TableNames,
    placeholder: str,
    instance_id: str,
    chunk_scores: list[tuple[str, float]],
    *,
    limit: int,
    path_filter: str | None,
    tag_filter: str | None,
    quote_names: bool = False,
) -> list[dict[str, Any]]:
    if not chunk_scores:
        return []
    chunks_table = _table_name(tables.chunks, quote_names)
    documents_table = _table_name(tables.documents, quote_names)
    scores = dict(chunk_scores)
    chunk_ids = [chunk_id for chunk_id, _ in chunk_scores]
    chunk_placeholders = ", ".join([placeholder] * len(chunk_ids))
    rows = _execute_fetchall(
        executor,
        f"""
        SELECT c.chunk_id, c.path, c.heading_path_json, c.start_line, c.end_line, c.text,
               d.title, d.tags_json
        FROM {chunks_table} c
        JOIN {documents_table} d
          ON c.instance_id = d.instance_id AND c.document_id = d.document_id
        WHERE c.instance_id = {placeholder} AND c.chunk_id IN ({chunk_placeholders})
        """,
        (instance_id, *chunk_ids),
    )
    rows_by_id = {str(row[0]): row for row in rows}
    results: list[dict[str, Any]] = []
    requested_tags = _parse_tag_filter(tag_filter)
    path_filter_normalized = (path_filter or "").strip().lower()
    for chunk_id in chunk_ids:
        row = rows_by_id.get(chunk_id)
        if row is None:
            continue
        path = str(row[1])
        tags = _json_list(row[7])
        if path_filter_normalized and path_filter_normalized not in path.lower():
            continue
        if requested_tags and not requested_tags.intersection({tag.lower() for tag in tags}):
            continue
        heading_path = _json_list(row[2])
        text = str(row[5])
        results.append(
            {
                "path": path,
                "title": str(row[6]),
                "heading_path": heading_path,
                "start_line": int(row[3]),
                "end_line": int(row[4]),
                "score": round(scores.get(chunk_id, 0.0), 4),
                "snippet": _snippet(text),
                "tags": tags,
            }
        )
        if len(results) >= limit:
            break
    return results


def _build_status(
    indexed_state: dict[str, tuple[int, int, str]],
    current_state: dict[str, tuple[int, int, str]],
    indexed_chunks: int,
) -> IndexStatus:
    changed_paths = sorted(
        path
        for path, state in current_state.items()
        if path not in indexed_state or indexed_state[path] != state
    )
    deleted_paths = sorted(path for path in indexed_state if path not in current_state)
    return IndexStatus(
        index_built=True,
        stale=bool(changed_paths or deleted_paths),
        indexed_documents=len(indexed_state),
        indexed_chunks=indexed_chunks,
        current_documents=len(current_state),
        changed_paths=changed_paths,
        deleted_paths=deleted_paths,
    )


def _search_response(index_status: IndexStatus, results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "success": True,
        "index_built": index_status.index_built,
        "stale": index_status.stale,
        "result_count": len(results),
        "results": results,
        "status": _status_payload(index_status),
    }


def _index_not_built_response() -> dict[str, Any]:
    return {
        "success": False,
        "error_code": "index_not_built",
        "error": "Markdown vault index is not built. Ask an admin to run manage_index.py refresh for this provider instance.",
        "index_built": False,
        "stale": False,
        "results": [],
    }


def _status_payload(index_status: IndexStatus) -> dict[str, Any]:
    return {
        "index_built": index_status.index_built,
        "stale": index_status.stale,
        "indexed_documents": index_status.indexed_documents,
        "indexed_chunks": index_status.indexed_chunks,
        "current_documents": index_status.current_documents,
        "changed_paths": index_status.changed_paths,
        "deleted_paths": index_status.deleted_paths,
    }


def _document_id(path: str) -> str:
    return hashlib.sha1(path.encode("utf-8")).hexdigest()


def _placeholders(count: int, placeholder: str) -> str:
    return ", ".join([placeholder] * count)


def _execute_fetchall(executor: Any, statement: str, params: tuple[Any, ...]) -> list[Any]:
    result = executor.execute(statement, params)
    if hasattr(result, "fetchall"):
        return list(result.fetchall())
    return list(executor.fetchall())


def _execute_fetchone(executor: Any, statement: str, params: tuple[Any, ...]) -> Any:
    result = executor.execute(statement, params)
    if hasattr(result, "fetchone"):
        return result.fetchone()
    return executor.fetchone()


def _like_contains_param(value: str) -> str:
    escaped = value.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _table_name(name: str, quote_names: bool) -> str:
    return f"`{name}`" if quote_names else name


def _json_list(value: Any) -> list[str]:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            return []
    else:
        payload = value
    if isinstance(payload, list):
        return [str(item) for item in payload]
    return []


def _parse_tag_filter(value: str | None) -> set[str]:
    if not value:
        return set()
    return {
        item.strip().lstrip("#").lower()
        for item in value.replace("\n", ",").split(",")
        if item.strip()
    }


def _snippet(text: str, max_chars: int = 360) -> str:
    compact = " ".join(line.strip() for line in text.splitlines() if line.strip())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "..."
