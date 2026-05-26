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
  - Search a configured Markdown vault directly with Python full-text retrieval
  - Return bounded matching Markdown regions for LLM evidence analysis
  - Retrieve read-only cited line ranges from Markdown notes
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

Search runs directly against Markdown files at request time. The provider does not create a database or require an administrative refresh step. The Agent LLM should analyze the user question first, pass expanded `keywords` to the search tool, and then answer only from the bounded matching regions returned by the provider.

During each search, Python measures only the query and keyword tokens against the currently scanned chunks to down-weight vault-specific common terms. This is request-scoped and does not persist an index; exact multi-token keyword phrases remain available for full scoring.

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

- `markdown_vault_search(query, keywords, limit, path_filter, tag_filter)`
- `markdown_vault_get(path, start_line, end_line)`

The search tool scans configured Markdown files, scores matching regions, and returns bounded `text` for LLM analysis. The get tool reads a safe line range when the answer needs surrounding context beyond a search result.

`path_filter` is a vault-relative path constraint, not a topic or provider selector. Agents should omit it for ordinary knowledge-base Q&A. Use it only when the user explicitly provides a vault-relative directory/file path, or when a previous search result's `path` field should constrain a follow-up search.

Search and get outputs are evidence only, not user-facing answers. Agents must synthesize a concise natural-language answer from the evidence and cite only the most relevant vault paths. Never return raw search result blocks, repeated `### ...` source sections, JSON payloads, or copied `text` fields as the final reply.

A vault evidence block is not an answer. If tool output contains Markdown shaped like `### title` followed by `- Source: path.md`, treat that block as internal evidence and rewrite it into a conclusion, key points, and a short citation. Do not start the final reply with a source heading, do not list every returned result, and do not paste an entire returned chunk.

## Answering Rules

- Search before answering knowledge-base questions unless the user already supplied enough cited vault content.
- Before search, extract useful `keywords`: product names, component names, synonyms, English/Chinese variants, and typo corrections.
- Prefer domain-specific keywords over generic words. Python will down-weight terms that are common in the current vault, but precise LLM keyword expansion is still the main quality control.
- Do not infer `path_filter` from product names, provider names, provider instance names, knowledge-base names, or topic words. If no vault-relative path is explicit, search without `path_filter`.
- Start the final reply with the answer or support judgment. Summarize only the evidence needed for that answer; do not concatenate search results.
- Use citations sparingly. Prefer one or two relevant vault-relative citations after the synthesized point; avoid repeating `Source:` lines or one section per search hit.
- Do not use the literal label `Source:` in final answers. Use concise prose citations such as `来源：path.md` and cite each path at most once.
- Cite the vault-relative path, heading path, and line range when available.
- If search returns no matches, say that the current knowledge base has no matching evidence.
- Do not claim that an answer came from the vault unless it is supported by returned search or get output.
