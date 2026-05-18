from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "skills" / "markdown-vault-query" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from _config import build_markdown_vault_config
from _index import SQLiteIndexStore
from _parser import collect_current_file_state, parse_vault, read_markdown_lines


def _config(tmp_path: Path):
    """Build a SQLite-backed test config for a temporary vault."""

    vault = tmp_path / "vault"
    vault.mkdir()
    return build_markdown_vault_config(
        raw_config={
            "vault_path": str(vault),
            "index_backend": "sqlite",
            "index_path": str(tmp_path / "index.sqlite3"),
            "max_chunk_chars": 400,
        },
        instance_name="team",
        base_dir=tmp_path,
    )


def _refresh(config) -> SQLiteIndexStore:
    """Refresh the SQLite test index and return the store."""

    store = SQLiteIndexStore(config)
    store.replace_index(parse_vault(config))
    return store


def test_search_reports_index_not_built_before_refresh(tmp_path: Path) -> None:
    """Verify search fails clearly when index tables do not exist."""

    config = _config(tmp_path)
    (config.vault_path / "note.md").write_text("# Note\ncontent", encoding="utf-8")
    store = SQLiteIndexStore(config)

    payload = store.search(
        "content",
        limit=5,
        path_filter=None,
        tag_filter=None,
        current_state=collect_current_file_state(config),
    )

    assert payload["success"] is False
    assert payload["error_code"] == "index_not_built"
    assert payload["index_built"] is False


def test_sqlite_refresh_search_get_and_multilingual_matching(tmp_path: Path) -> None:
    """Verify refresh indexes documents and search returns cited English and Chinese matches."""

    config = _config(tmp_path)
    (config.vault_path / "release.md").write_text(
        "---\nowner: platform\n---\n# Deployment\nRollback alpha release with #release tag.\n审批流程 requires two reviewers.\n",
        encoding="utf-8",
    )
    (config.vault_path / "database.md").write_text(
        "# Database\nBackup policy and restore windows.\n",
        encoding="utf-8",
    )
    store = _refresh(config)
    current_state = collect_current_file_state(config)

    rollback = store.search("rollback release", limit=3, path_filter=None, tag_filter=None, current_state=current_state)
    chinese = store.search("审批流程", limit=3, path_filter=None, tag_filter=None, current_state=current_state)
    tagged = store.search("release", limit=3, path_filter=None, tag_filter="release", current_state=current_state)
    database = store.search("database backup", limit=3, path_filter="database", tag_filter=None, current_state=current_state)
    property_match = store.search("platform", limit=3, path_filter=None, tag_filter=None, current_state=current_state)
    read_payload = read_markdown_lines(config, "release.md", start_line=1, end_line=2)

    assert rollback["success"] is True
    assert rollback["stale"] is False
    assert rollback["results"][0]["path"] == "release.md"
    assert rollback["results"][0]["heading_path"] == ["Deployment"]
    assert rollback["results"][0]["start_line"] == 4
    assert chinese["results"][0]["path"] == "release.md"
    assert tagged["results"][0]["path"] == "release.md"
    assert database["results"][0]["path"] == "database.md"
    assert property_match["results"][0]["path"] == "release.md"
    assert read_payload["text"] == "---\nowner: platform"


def test_sqlite_status_detects_changed_and_deleted_files(tmp_path: Path) -> None:
    """Verify stale detection for changed files and cleanup after refresh."""

    config = _config(tmp_path)
    release = config.vault_path / "release.md"
    database = config.vault_path / "database.md"
    release.write_text("# Release\nrollback steps\n", encoding="utf-8")
    database.write_text("# Database\nbackup windows\n", encoding="utf-8")
    store = _refresh(config)

    fresh_status = store.status(collect_current_file_state(config))
    assert fresh_status.stale is False
    assert fresh_status.indexed_documents == 2

    release.write_text("# Release\nrollback steps changed\n", encoding="utf-8")
    changed_status = store.status(collect_current_file_state(config))
    assert changed_status.stale is True
    assert changed_status.changed_paths == ["release.md"]

    database.unlink()
    deleted_status = store.status(collect_current_file_state(config))
    assert deleted_status.stale is True
    assert deleted_status.deleted_paths == ["database.md"]

    store.replace_index(parse_vault(config))
    refreshed_status = store.status(collect_current_file_state(config))
    assert refreshed_status.stale is False
    assert refreshed_status.indexed_documents == 1
    search_payload = store.search(
        "backup",
        limit=3,
        path_filter=None,
        tag_filter=None,
        current_state=collect_current_file_state(config),
    )
    assert search_payload["results"] == []


def test_sqlite_search_applies_path_and_tag_filters_before_candidate_limit(tmp_path: Path) -> None:
    """Verify filters do not miss matches ranked below the broad unfiltered window."""

    config = _config(tmp_path)
    for index in range(60):
        (config.vault_path / f"decoy-{index:02d}.md").write_text(
            "# Decoy\ncommon searchable text\n",
            encoding="utf-8",
        )
    (config.vault_path / "target.md").write_text(
        "---\ntags: [target]\n---\n# Target\ncommon searchable text\n",
        encoding="utf-8",
    )
    store = _refresh(config)
    current_state = collect_current_file_state(config)

    by_path = store.search("common", limit=1, path_filter="target", tag_filter=None, current_state=current_state)
    by_tag = store.search("common", limit=1, path_filter=None, tag_filter="target", current_state=current_state)

    assert by_path["result_count"] == 1
    assert by_path["results"][0]["path"] == "target.md"
    assert by_tag["result_count"] == 1
    assert by_tag["results"][0]["path"] == "target.md"


def test_admin_refresh_script_and_runtime_search_script_smoke(tmp_path: Path) -> None:
    """Verify offline refresh and runtime search work through the documented CLI boundary."""

    vault = tmp_path / "vault"
    vault.mkdir()
    index_path = tmp_path / "index.sqlite3"
    raw_config = {
        "vault_path": str(vault),
        "index_backend": "sqlite",
        "index_path": str(index_path),
        "max_chunk_chars": 400,
    }
    (vault / "ops.md").write_text("# Ops\nRollback from the CLI smoke test.\n", encoding="utf-8")
    config_file = tmp_path / "atlasclaw.json"
    config_file.write_text(
        json.dumps({"provider_config": {"markdown-vault": {"team": raw_config}}}),
        encoding="utf-8",
    )

    refresh = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "manage_index.py"),
            "refresh",
            "--config",
            str(config_file),
            "--instance",
            "team",
        ],
        cwd=SCRIPTS_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    assert refresh.returncode == 0, refresh.stderr
    refresh_payload = json.loads(refresh.stdout)
    assert refresh_payload["success"] is True
    assert refresh_payload["indexed_documents"] == 1

    env = os.environ.copy()
    env["ATLASCLAW_PROVIDER_CONFIG"] = json.dumps({"markdown-vault": {"team": raw_config}})
    env["ATLASCLAW_PROVIDER_TYPE"] = "markdown-vault"
    env["ATLASCLAW_PROVIDER_INSTANCE"] = "team"
    search = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "search.py"), "--query", "rollback", "--limit", "3"],
        cwd=SCRIPTS_DIR,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert search.returncode == 0, search.stderr
    search_payload = json.loads(search.stdout)
    assert search_payload["success"] is True
    assert search_payload["results"][0]["path"] == "ops.md"
