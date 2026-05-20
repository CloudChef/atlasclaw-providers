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
    """Verify the provider config fields required for direct Markdown retrieval."""

    manifest = json.loads((PROVIDER_ROOT / "provider.schema.json").read_text(encoding="utf-8"))
    fields = {field["name"]: field for field in manifest["config_schema"]["fields"]}

    assert manifest["schema_version"] == 1
    assert manifest["provider_type"] == "markdown-vault"
    assert manifest["catalog"]["icon_path"] == "assets/icon.svg"
    assert manifest["config_schema"]["default_auth_type"] == "app_credentials"
    assert manifest["config_schema"]["auth_modes"]["app_credentials"]["required_fields"] == []
    assert fields["vault_path"]["required"] is True
    assert "index_backend" not in fields
    assert "index_path" not in fields
    assert "mysql_password" not in fields
    assert fields["include_globs"]["default"] == "**/*.md"
    assert fields["exclude_globs"]["default"]
    assert fields["max_file_bytes"]["default"] > 0
    assert fields["max_chunk_chars"]["default"] >= 200
    assert fields["max_context_chars"]["default"] == 24576
    assert fields["max_result_chars"]["default"] == 3072


def test_markdown_vault_manifest_stays_with_supported_runtime_contract() -> None:
    """Verify the manifest avoids runtime metadata not consumed by AtlasClaw."""

    manifest = json.loads((PROVIDER_ROOT / "provider.schema.json").read_text(encoding="utf-8"))

    assert "agent_skill_overlays" not in manifest
    assert "auto_select" not in json.dumps(manifest)
    assert "tool_graph_name" not in json.dumps(manifest)
    assert "smartcmp" not in json.dumps(manifest).lower()


def test_markdown_vault_skill_registers_only_read_runtime_tools() -> None:
    """Verify only read tools are registered as Agent tools."""

    skill_text = (PROVIDER_ROOT / "skills" / "markdown-vault-query" / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = skill_text.split("---", 2)[1]

    assert 'tool_search_name: "markdown_vault_search"' in frontmatter
    assert 'tool_get_name: "markdown_vault_get"' in frontmatter
    assert "tool_graph_name" not in frontmatter
    assert "tool_refresh_name" not in frontmatter
    assert "tool_status_name" not in frontmatter
    assert "manage_index.py" not in frontmatter


def test_markdown_vault_provider_removes_database_index_contract() -> None:
    """Verify direct retrieval has no database index scripts, config fields, or error codes."""

    searchable_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in PROVIDER_ROOT.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and "test" not in path.parts
        and path.suffix in {".md", ".json", ".py"}
    ).lower()

    for forbidden in (
        "sqlite",
        "mysql",
        "index_backend",
        "index_path",
        "manage_index.py",
        "index_not_built",
        "indexed_documents",
    ):
        assert forbidden not in searchable_text
