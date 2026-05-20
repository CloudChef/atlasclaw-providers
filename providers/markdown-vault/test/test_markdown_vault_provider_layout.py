from __future__ import annotations

import json
from pathlib import Path


PROVIDER_ROOT = Path(__file__).resolve().parents[1]


def test_markdown_vault_provider_package_layout() -> None:
    """Verify that the provider package has the expected manifest, docs, icon, and skill."""

    assert (PROVIDER_ROOT / "PROVIDER.md").is_file()
    assert (PROVIDER_ROOT / "README.md").is_file()
    assert (PROVIDER_ROOT / "provider.schema.json").is_file()
    assert (PROVIDER_ROOT / "assets" / "icon.svg").is_file()
    assert (PROVIDER_ROOT / "skills" / "markdown-vault-query" / "SKILL.md").is_file()


def test_markdown_vault_provider_context_frontmatter() -> None:
    """Verify provider discovery metadata is present in PROVIDER.md."""

    provider_text = (PROVIDER_ROOT / "PROVIDER.md").read_text(encoding="utf-8")
    frontmatter = provider_text.split("---", 2)[1]

    assert "provider_type: markdown-vault" in frontmatter
    assert "display_name: Markdown Vault" in frontmatter
    assert "version:" in frontmatter
    assert "keywords:" in frontmatter
    assert "capabilities:" in frontmatter
    assert "use_when:" in frontmatter
    assert "avoid_when:" in frontmatter


def test_markdown_vault_manifest_declares_config_contract() -> None:
    """Verify the provider config fields required for SQLite and MySQL indexing."""

    manifest = json.loads((PROVIDER_ROOT / "provider.schema.json").read_text(encoding="utf-8"))
    fields = {field["name"]: field for field in manifest["config_schema"]["fields"]}

    assert manifest["schema_version"] == 1
    assert manifest["provider_type"] == "markdown-vault"
    assert manifest["catalog"]["icon_path"] == "assets/icon.svg"
    assert manifest["config_schema"]["default_auth_type"] == "app_credentials"
    assert manifest["config_schema"]["auth_modes"]["app_credentials"]["required_fields"] == []
    assert fields["vault_path"]["required"] is True
    assert fields["index_backend"]["default"] == "sqlite"
    assert fields["index_path"]["label"] == "SQLite Index Path"
    assert fields["mysql_password"]["sensitive"] is True
    assert fields["mysql_charset"]["default"] == "utf8mb4"
    assert fields["mysql_tls"]["default"] == "false"
    assert fields["mysql_table_prefix"]["default"] == "markdown_vault_"
    assert fields["include_globs"]["default"] == "**/*.md"
    assert fields["exclude_globs"]["default"]
    assert fields["max_file_bytes"]["default"] > 0
    assert fields["max_chunk_chars"]["default"] >= 200


def test_markdown_vault_manifest_stays_with_supported_runtime_contract() -> None:
    """Verify the manifest avoids runtime metadata not consumed by AtlasClaw."""

    manifest = json.loads((PROVIDER_ROOT / "provider.schema.json").read_text(encoding="utf-8"))

    assert "agent_skill_overlays" not in manifest
    assert "auto_select" not in json.dumps(manifest)
    assert "tool_graph_name" not in json.dumps(manifest)
    assert "smartcmp" not in json.dumps(manifest).lower()


def test_markdown_vault_skill_registers_only_read_runtime_tools() -> None:
    """Verify refresh and status are not registered as Agent tools."""

    skill_text = (PROVIDER_ROOT / "skills" / "markdown-vault-query" / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = skill_text.split("---", 2)[1]

    assert 'tool_search_name: "markdown_vault_search"' in frontmatter
    assert 'tool_get_name: "markdown_vault_get"' in frontmatter
    assert "tool_graph_name" not in frontmatter
    assert "tool_refresh_name" not in frontmatter
    assert "tool_status_name" not in frontmatter
    assert "manage_index.py" not in frontmatter
