from __future__ import annotations

import os
from pathlib import Path
import sys
from urllib.parse import parse_qs, unquote, urlparse

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "skills" / "markdown-vault-query" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from _config import MarkdownVaultConfigError, build_markdown_vault_config
from _index import MySQLIndexStore, mysql_schema_statements
from _parser import collect_current_file_state, parse_vault


def test_mysql_schema_generation_uses_provider_owned_tables() -> None:
    """Verify MySQL DDL creates documents, chunks, and terms under the configured prefix."""

    ddl = "\n".join(mysql_schema_statements("mv_"))

    assert "CREATE TABLE IF NOT EXISTS `mv_documents`" in ddl
    assert "CREATE TABLE IF NOT EXISTS `mv_chunks`" in ddl
    assert "CREATE TABLE IF NOT EXISTS `mv_terms`" in ddl
    assert "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4" in ddl
    assert "`instance_id`" in ddl
    assert "`chunk_id`" in ddl


def test_config_rejects_unsafe_mysql_table_prefix(tmp_path: Path) -> None:
    """Verify table prefixes are constrained before being interpolated into SQL identifiers."""

    vault = tmp_path / "vault"
    vault.mkdir()

    for table_prefix in ("bad-prefix;", "123_"):
        with pytest.raises(MarkdownVaultConfigError):
            build_markdown_vault_config(
                raw_config={
                    "vault_path": str(vault),
                    "index_backend": "mysql",
                    "mysql_host": "127.0.0.1",
                    "mysql_database": "atlasclaw",
                    "mysql_user": "atlasclaw",
                    "mysql_password": "secret",
                    "mysql_table_prefix": table_prefix,
                },
                instance_name="mysql",
                base_dir=tmp_path,
            )


def test_mysql_integration_refresh_is_gated_by_dsn(tmp_path: Path) -> None:
    """Optionally verify MySQL refresh/search when MYSQL_TEST_DSN is explicitly provided."""

    dsn = os.getenv("MYSQL_TEST_DSN")
    if not dsn:
        pytest.skip("MYSQL_TEST_DSN is not set.")

    config = _mysql_config_from_dsn(tmp_path, dsn)
    (config.vault_path / "mysql.md").write_text("# MySQL\nShared vault search works.\n", encoding="utf-8")
    store = MySQLIndexStore(config)
    try:
        store.replace_index(parse_vault(config))
        payload = store.search(
            "shared vault",
            limit=3,
            path_filter=None,
            tag_filter=None,
            current_state=collect_current_file_state(config),
        )
        assert payload["success"] is True
        assert payload["results"][0]["path"] == "mysql.md"
    finally:
        _drop_mysql_test_tables(store, config.table_prefix)


def _mysql_config_from_dsn(tmp_path: Path, dsn: str):
    parsed = urlparse(dsn)
    query = parse_qs(parsed.query)
    vault = tmp_path / "vault"
    vault.mkdir()
    prefix = f"mv_test_{os.getpid()}_"
    return build_markdown_vault_config(
        raw_config={
            "vault_path": str(vault),
            "index_backend": "mysql",
            "mysql_host": parsed.hostname or "127.0.0.1",
            "mysql_port": parsed.port or 3306,
            "mysql_database": parsed.path.lstrip("/"),
            "mysql_user": unquote(parsed.username or ""),
            "mysql_password": unquote(parsed.password or ""),
            "mysql_charset": query.get("charset", ["utf8mb4"])[0],
            "mysql_tls": query.get("tls", ["false"])[0],
            "mysql_table_prefix": prefix,
        },
        instance_name="mysql",
        base_dir=tmp_path,
    )


def _drop_mysql_test_tables(store: MySQLIndexStore, prefix: str) -> None:
    conn = store._connect()
    try:
        with conn.cursor() as cursor:
            for suffix in ("terms", "chunks", "documents"):
                cursor.execute(f"DROP TABLE IF EXISTS `{prefix}{suffix}`")
        conn.commit()
    finally:
        conn.close()
