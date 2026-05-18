# Markdown Vault Provider

`markdown-vault` indexes a local Markdown vault into provider-owned SQLite or MySQL tables so AtlasClaw agents can answer knowledge-base questions with citations.

V1 is read-only and does not depend on Obsidian at runtime. Obsidian-compatible Markdown behavior is handled directly for frontmatter, headings, tags, wikilinks, embeds, Markdown links, and callout text.

## Configuration

Minimum SQLite instance:

```json
{
  "vault_path": "/Users/shared/knowledge-vault",
  "index_backend": "sqlite",
  "index_path": "/Users/shared/atlasclaw/markdown-vault.sqlite3",
  "include_globs": "**/*.md",
  "exclude_globs": ".obsidian/**,.git/**,**/.*/**",
  "max_file_bytes": 1048576,
  "max_chunk_chars": 1800
}
```

Minimum MySQL instance:

```json
{
  "vault_path": "/Users/shared/knowledge-vault",
  "index_backend": "mysql",
  "mysql_host": "127.0.0.1",
  "mysql_port": 3306,
  "mysql_database": "atlasclaw",
  "mysql_user": "atlasclaw",
  "mysql_password": "secret",
  "mysql_charset": "utf8mb4",
  "mysql_tls": "false",
  "mysql_table_prefix": "markdown_vault_"
}
```

`include_globs` and `exclude_globs` accept comma-separated glob patterns relative to `vault_path`.

The provider has no credential fields in V1. Access is controlled by the existing AtlasClaw provider instance and role permissions.

## Admin Indexing

Refresh the index from an AtlasClaw config file:

```bash
python providers/markdown-vault/skills/markdown-vault-query/scripts/manage_index.py \
  refresh \
  --config /path/to/atlasclaw.json \
  --instance team-notes
```

Check index status:

```bash
python providers/markdown-vault/skills/markdown-vault-query/scripts/manage_index.py \
  status \
  --config /path/to/atlasclaw.json \
  --instance team-notes
```

The script creates provider-owned `documents`, `chunks`, and `terms` tables. It does not require core database migrations.

## Runtime Tools

Agents receive only the read tools:

- `markdown_vault_search(query, limit, path_filter, tag_filter)`
- `markdown_vault_get(path, start_line, end_line)`

Provider instance RBAC is enforced by the existing AtlasClaw provider selection flow. Users can query only the configured vault instances their role can access.

Search returns `stale=true` when vault files differ from the last indexed state. Missing indexes return a clear `index_not_built` error.

## Out Of Scope

- Vault writes or edits
- Attachments and binary files
- Canvas, Bases, Dataview execution
- PDF/OCR extraction
- Obsidian desktop automation
