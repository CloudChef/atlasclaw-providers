from __future__ import annotations

from pathlib import Path
import sys

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "skills" / "markdown-vault-query" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from _config import build_markdown_vault_config
from _parser import (  # noqa: E402
    VaultPathError,
    iter_markdown_files,
    normalize_terms,
    parse_markdown_file,
    read_markdown_lines,
    resolve_vault_markdown_path,
)


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
        instance_name="test",
        base_dir=tmp_path,
    )


def test_parse_markdown_file_extracts_obsidian_compatible_metadata(tmp_path: Path) -> None:
    """Verify frontmatter, headings, tags, wikilinks, callouts, embeds, and line ranges."""

    config = _config(tmp_path)
    note = config.vault_path / "runbooks" / "release.md"
    note.parent.mkdir()
    note.write_text(
        "\n".join(
            [
                "---",
                "title: Release Runbook",
                "aliases:",
                "  - 发布手册",
                "tags: [ops, release]",
                "owner: platform",
                "---",
                "# Rollback",
                "Use #deploy/runbook when rollback is needed.",
                "> [!note] Read [[Service Guide|service guide]] before changing traffic.",
                "![[architecture.png|traffic diagram]]",
                "See [manual](docs/manual.md).",
                "## Steps",
                "审批流程 requires two reviewers.",
            ]
        ),
        encoding="utf-8",
    )

    document = parse_markdown_file(config, note)

    assert document.path == "runbooks/release.md"
    assert document.title == "Release Runbook"
    assert document.properties["owner"] == "platform"
    assert document.aliases == ["发布手册"]
    assert set(document.tags) == {"deploy/runbook", "ops", "release"}
    assert {reference.kind for reference in document.links} == {"embed", "markdown", "wikilink"}
    assert any(reference.label == "service guide" for reference in document.links)
    assert any(reference.target == "architecture.png" for reference in document.links)
    assert any(chunk.heading_path == ["Rollback", "Steps"] for chunk in document.chunks)
    assert min(chunk.start_line for chunk in document.chunks) == 8
    assert any("审批流程" in chunk.text for chunk in document.chunks)
    assert {"审批", "流程"}.issubset(set(normalize_terms("审批流程")))


def test_read_markdown_lines_returns_safe_bounded_range(tmp_path: Path) -> None:
    """Verify `get` output shape and 1-based inclusive line ranges."""

    config = _config(tmp_path)
    note = config.vault_path / "note.md"
    note.write_text("# Title\nline 2\nline 3\nline 4\n", encoding="utf-8")

    payload = read_markdown_lines(config, "note.md", start_line=2, end_line=3)

    assert payload["path"] == "note.md"
    assert payload["start_line"] == 2
    assert payload["end_line"] == 3
    assert payload["text"] == "line 2\nline 3"
    assert payload["title"] == "Title"


def test_resolve_vault_markdown_path_rejects_traversal(tmp_path: Path) -> None:
    """Verify absolute paths, traversal, and non-Markdown paths cannot escape the vault."""

    config = _config(tmp_path)
    (config.vault_path / "safe.md").write_text("ok", encoding="utf-8")

    assert resolve_vault_markdown_path(config.vault_path, "safe.md").is_file()
    with pytest.raises(VaultPathError):
        resolve_vault_markdown_path(config.vault_path, "../outside.md")
    with pytest.raises(VaultPathError):
        resolve_vault_markdown_path(config.vault_path, str(config.vault_path / "safe.md"))
    with pytest.raises(VaultPathError):
        resolve_vault_markdown_path(config.vault_path, "safe.txt")


def test_read_markdown_lines_rejects_files_outside_scan_policy(tmp_path: Path) -> None:
    """Verify get cannot bypass include, exclude, or max-size policy."""

    vault = tmp_path / "vault"
    vault.mkdir()
    config = build_markdown_vault_config(
        raw_config={
            "vault_path": str(vault),
            "index_backend": "sqlite",
            "index_path": str(tmp_path / "index.sqlite3"),
            "include_globs": ["public/**/*.md"],
            "exclude_globs": ["public/private/**"],
            "max_file_bytes": 24,
            "max_chunk_chars": 400,
        },
        instance_name="test",
        base_dir=tmp_path,
    )
    (vault / "public").mkdir()
    (vault / "public" / "private").mkdir()
    (vault / "hidden.md").write_text("# Hidden\nnot indexed\n", encoding="utf-8")
    (vault / "public" / "private" / "secret.md").write_text("# Secret\nnot indexed\n", encoding="utf-8")
    (vault / "public" / "large.md").write_text("# Large\n" + ("x" * 40), encoding="utf-8")
    (vault / "public" / "ok.md").write_text("# OK\nincluded\n", encoding="utf-8")

    assert read_markdown_lines(config, "public/ok.md")["path"] == "public/ok.md"
    with pytest.raises(VaultPathError):
        read_markdown_lines(config, "hidden.md")
    with pytest.raises(VaultPathError):
        read_markdown_lines(config, "public/private/secret.md")
    with pytest.raises(VaultPathError):
        read_markdown_lines(config, "public/large.md")


def test_iter_markdown_files_skips_symlink_outside_vault(tmp_path: Path) -> None:
    """Verify out-of-vault symlinks do not break indexing scans."""

    config = _config(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\nsecret\n", encoding="utf-8")
    link = config.vault_path / "linked.md"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("filesystem does not support symlinks")
    (config.vault_path / "inside.md").write_text("# Inside\nindexed\n", encoding="utf-8")

    assert [path.name for path in iter_markdown_files(config)] == ["inside.md"]


def test_recursive_frontmatter_alias_does_not_crash_parser(tmp_path: Path) -> None:
    """Verify recursive YAML aliases cannot poison parsing or term extraction."""

    config = _config(tmp_path)
    note = config.vault_path / "recursive.md"
    note.write_text(
        "\n".join(
            [
                "---",
                "title: Recursive",
                "loop: &loop",
                "  self: *loop",
                "---",
                "# Body",
                "searchable content",
            ]
        ),
        encoding="utf-8",
    )

    document = parse_markdown_file(config, note)

    assert document.title == "Recursive"
    assert document.chunks
    assert any("searchable content" in chunk.text for chunk in document.chunks)
