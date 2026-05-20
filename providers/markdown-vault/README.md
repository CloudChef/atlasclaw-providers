# Markdown Vault Provider

`markdown-vault` searches a configured Markdown vault directly so AtlasClaw agents can answer knowledge-base questions with citations and bounded source text.

V1 is read-only and does not depend on Obsidian at runtime. Obsidian-compatible Markdown behavior is handled directly for frontmatter, headings, tags, wikilinks, embeds, Markdown links, and callout text.

## Configuration

Minimum instance:

```json
{
  "vault_path": "/Users/shared/knowledge-vault",
  "include_globs": "**/*.md",
  "exclude_globs": ".obsidian/**,.git/**,**/.*/**",
  "max_file_bytes": 1048576,
  "max_chunk_chars": 1800,
  "max_context_chars": 24576,
  "max_result_chars": 3072
}
```

`include_globs` and `exclude_globs` accept comma-separated glob patterns relative to `vault_path`.

The provider has no credential fields in V1. Access is controlled by the existing AtlasClaw provider instance and role permissions.

## Runtime Tools

Agents receive only the read tools:

- `markdown_vault_search(query, keywords, limit, path_filter, tag_filter)`
- `markdown_vault_get(path, start_line, end_line)`

Provider instance RBAC is enforced by the existing AtlasClaw provider selection flow. Users can query only the configured vault instances their role can access.

Search returns scored Markdown regions with `text`, `snippet`, vault-relative paths, heading paths, line ranges, matched keywords, tags, and a context-budget status. The Agent LLM is responsible for final answer synthesis and support judgment.

## Retrieval Flow

1. The Agent LLM analyzes the user question and builds `keywords` from product names, system names, aliases, English/Chinese variants, and likely typo corrections.
2. Python scans configured Markdown files directly, applies path/tag filters, parses metadata and headings, and splits content into bounded chunks.
3. Python measures only the current query/keyword tokens across the scanned chunks and down-weights tokens that are common in that vault slice.
4. Python scores each chunk with title, heading, alias, tag, path, phrase, and body matches.
5. Python returns the highest-scoring chunks within `max_context_chars` and `max_result_chars`.
6. The Agent LLM answers only from returned evidence, calling `markdown_vault_get` when more surrounding lines are needed.

## Out Of Scope

- Vault writes or edits
- Attachments and binary files
- Canvas, Bases, Dataview execution
- PDF/OCR extraction
- Obsidian desktop automation
