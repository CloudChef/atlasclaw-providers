---
name: "markdown-vault-query"
description: "Search and retrieve read-only local Markdown vault knowledge-base content with file and line citations."
category: "provider:markdown-vault"
provider_type: "markdown-vault"
instance_required: "true"

triggers:
  - markdown vault
  - obsidian vault
  - knowledge base
  - internal docs
  - team notes
  - runbook
  - design doc
  - wiki
  - 文档库
  - 知识库
  - 内部文档
  - 笔记库

use_when:
  - User asks a question that should be answered from a configured Markdown knowledge base.
  - User asks to search or cite local Markdown, Obsidian-style notes, internal docs, runbooks, or team notes.
  - User references a vault path, note name, heading, tag, or wikilink.

avoid_when:
  - User asks a general public factual question with no knowledge-base or document intent.
  - User wants to edit, create, move, or delete vault notes.
  - User asks to operate the Obsidian desktop app.

examples:
  - "Search the knowledge base for deployment rollback steps"
  - "What do our internal docs say about incident severity?"
  - "查一下知识库里关于发布审批的说明"
  - "Open the vault note docs/runbook.md lines 20-60"

related:
  - markdown
  - knowledge-base
  - obsidian

tool_search_name: "markdown_vault_search"
tool_search_description: "Search Markdown vault files directly. Use only for knowledge-base, internal-doc, runbook, wiki, or vault-note intent. Pass LLM-expanded keywords when available. Returns evidence only: cited file paths, heading paths, line ranges, snippets, bounded text, matched keywords, tags, and context-budget status. Never copy result blocks or Source lines into the final answer; synthesize them."
tool_search_entrypoint: "scripts/search.py:handler"
tool_search_groups:
  - markdown-vault
  - knowledge
tool_search_capability_class: "provider:markdown-vault"
tool_search_priority: 100
tool_search_parameters: |
  {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Original user question or natural-language query."
      },
      "keywords": {
        "type": "array",
        "description": "Optional LLM-expanded search keywords, including entities, synonyms, English/Chinese variants, and typo corrections.",
        "items": {
          "type": "string"
        },
        "default": []
      },
      "limit": {
        "type": "integer",
        "description": "Maximum result count. Defaults to 12 and is capped by the tool.",
        "default": 12
      },
      "path_filter": {
        "type": "string",
        "description": "Optional vault-relative path substring to narrow results. Omit for ordinary knowledge-base questions. Use only when the user explicitly names a vault-relative directory/file path or when narrowing from a previous search result's path field. Do not infer this from product names, provider names, instance names, knowledge-base names, or topic words."
      },
      "tag_filter": {
        "type": "string",
        "description": "Optional tag name without '#', or comma-separated tags, to narrow results."
      }
    },
    "required": ["query"]
  }

tool_get_name: "markdown_vault_get"
tool_get_description: "Read a safe line range from one Markdown vault file by vault-relative path. Use after search when the answer needs more surrounding context. The returned Markdown is evidence only; never paste retrieved headings, Source lines, or whole chunks as the final answer."
tool_get_entrypoint: "scripts/get.py:handler"
tool_get_groups:
  - markdown-vault
  - knowledge
tool_get_capability_class: "provider:markdown-vault"
tool_get_priority: 110
tool_get_parameters: |
  {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Vault-relative Markdown file path. Absolute paths and path traversal are rejected."
      },
      "start_line": {
        "type": "integer",
        "description": "Optional 1-based start line. Defaults to the first line."
      },
      "end_line": {
        "type": "integer",
        "description": "Optional 1-based inclusive end line. Defaults to a bounded window."
      }
    },
    "required": ["path"]
  }
---

# markdown-vault-query

Use this skill when the user wants answers grounded in a configured Markdown vault.

## Workflow

1. Analyze the question before searching. Extract useful `keywords`: product names, cloud/provider names, system names, aliases, English/Chinese variants, and likely typo corrections. Prefer domain terms over generic words; the provider down-weights vault-specific common tokens, but precise keywords still improve the top results.
2. Call `markdown_vault_search` for knowledge-base, internal-doc, wiki, runbook, or vault-note questions. Pass both the original `query` and the expanded `keywords`.
3. Read the returned `text`, `path`, `heading_path`, and line range as internal evidence. The returned text is not a final answer.
4. Do not pass `path_filter` for ordinary Q&A. It is only a vault-relative path constraint, in the same format as returned result `path` values.
5. Use `path_filter` only when the user explicitly gives a vault-relative directory/file path, or when a previous search result `path` should be used to narrow a follow-up search. Do not derive `path_filter` from product names, provider names, provider instance names, knowledge-base names, or topic words.
6. If the top results are too narrow or ambiguous, search again with clearer keywords first. Add `path_filter` only when the path is explicit or came from prior search evidence.
7. Call `markdown_vault_get` on the most relevant path and line range when surrounding context matters.
8. Answer with a natural-language synthesis: start with the conclusion or support judgment, then give the minimal supporting details and citations. If the evidence text already contains headings or bullet fields, paraphrase and compress them instead of copying the block.
9. Final answers must not contain the literal `Source:` label. Cite evidence in prose, for example `来源：path.md` or an inline parenthetical citation, and cite each path at most once.

## Evidence Rules

- Do not use this provider for every factual question. Use it only when the user intent is document or knowledge-base grounded.
- If no result is returned, say the current knowledge base has no matching evidence.
- Do not claim that an answer came from the vault unless it is supported by returned search or get output.
- Never return raw search results as the final answer. Do not concatenate result blocks, repeated `### ...` headings, `- Source:` sections, JSON payloads, or copied `text` fields. Use at most the most relevant citations needed to support the answer.
- Specifically, a block that starts with `### ...` and then `- Source: ...` is a vault evidence block, not a final answer format. Convert it into a concise conclusion and a few bullets; cite the source once instead of repeating source headings.
- If multiple search/get results point to the same file, merge them into one answer section. Do not create one section per returned chunk.
- Python retrieval only ranks and bounds Markdown evidence. The Agent LLM remains responsible for final answer synthesis and support judgment.
