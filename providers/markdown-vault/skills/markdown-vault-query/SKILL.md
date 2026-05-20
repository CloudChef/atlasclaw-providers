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
tool_search_description: "Search Markdown vault files directly. Use only for knowledge-base, internal-doc, runbook, wiki, or vault-note intent. Pass LLM-expanded keywords when available. Returns cited file paths, heading paths, line ranges, snippets, bounded text, matched keywords, tags, and context-budget status."
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
        "description": "Optional vault-relative path substring or glob-like fragment to narrow results."
      },
      "tag_filter": {
        "type": "string",
        "description": "Optional tag name without '#', or comma-separated tags, to narrow results."
      }
    },
    "required": ["query"]
  }

tool_get_name: "markdown_vault_get"
tool_get_description: "Read a safe line range from one Markdown vault file by vault-relative path. Use after search when the answer needs more surrounding context."
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
3. Read the returned `text`, `path`, `heading_path`, and line range. The returned text is intentionally bounded so the LLM can analyze it directly.
4. If the top results are too narrow or ambiguous, search again with clearer keywords or a `path_filter`.
5. Call `markdown_vault_get` on the most relevant path and line range when surrounding context matters.
6. Answer with citations that include the vault-relative path, heading path, and line range when available.

## Evidence Rules

- Do not use this provider for every factual question. Use it only when the user intent is document or knowledge-base grounded.
- If no result is returned, say the current knowledge base has no matching evidence.
- Do not claim that an answer came from the vault unless it is supported by returned search or get output.
- Python retrieval only ranks and bounds Markdown evidence. The Agent LLM remains responsible for final answer synthesis and support judgment.
