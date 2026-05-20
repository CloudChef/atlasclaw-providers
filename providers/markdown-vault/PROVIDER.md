---
# === Provider Identity ===
provider_type: markdown-vault
display_name: Markdown Vault
version: "1.0.0"

# === LLM Context Fields (for Skill Discovery) ===
keywords:
  - markdown
  - vault
  - obsidian
  - knowledge base
  - notes
  - documentation
  - runbook
  - wiki

capabilities:
  - Search a configured Markdown vault through a provider-owned SQLite or MySQL index
  - Retrieve read-only cited line ranges from indexed Markdown notes
  - Parse Obsidian-style frontmatter, headings, tags, wikilinks, embeds, callouts, and Markdown links

use_when:
  - User asks about a configured Markdown or Obsidian-style knowledge base
  - User asks for answers grounded in internal notes, runbooks, internal docs, or team documentation
  - User needs citations with vault-relative paths, heading paths, and line ranges

avoid_when:
  - User asks a general factual question that should not be answered from the vault
  - User wants to edit, create, move, or delete vault files
  - User wants to automate the Obsidian desktop app or run Obsidian CLI commands
---

# Markdown Vault Provider

## Purpose

`markdown-vault` exposes a read-only Markdown knowledge base to AtlasClaw agents. It is designed for provider instances backed by Markdown content that follows common Markdown and Obsidian-style conventions such as frontmatter, nested headings, inline tags, wikilinks, embeds, and callouts.

## Use When

- The user asks about internal documentation, team notes, runbooks, design records, or other configured knowledge-base content.
- The user asks a question that should be answered from a configured Markdown vault instead of from general model knowledge.
- The user wants cited evidence from a known document collection.

## Avoid When

- The question is a general public fact question and does not mention a knowledge base, vault, internal docs, or repository documentation.
- The user wants to automate the Obsidian desktop app or run Obsidian-specific commands.
- The user wants to edit, create, move, or delete vault files. V1 is read-only.

## Runtime Boundary

Agents may call only:

- `markdown_vault_search(query, limit, path_filter, tag_filter)`
- `markdown_vault_get(path, start_line, end_line)`

Index refresh and status checks are administrative operations. They are intentionally provided only by the offline script `scripts/manage_index.py` and are not registered as Agent tools.

## Answering Rules

- Search before answering knowledge-base questions unless the user already supplied enough cited vault content.
- Cite the vault-relative path, heading path, and line range when available.
- If search returns no matches, say that the current knowledge base has no matching evidence.
- If search reports `stale=true`, answer from the returned indexed evidence and mention that an admin refresh is recommended.
- If the index is missing, report the clear index-not-built error and do not fabricate evidence.
