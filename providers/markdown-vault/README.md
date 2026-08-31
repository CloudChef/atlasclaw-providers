# Markdown Vault Provider

`markdown-vault` searches a configured Markdown vault directly so AtlasClaw agents can answer knowledge-base questions with citations and bounded source text. It also owns the HTTP adapter, attachment conversion, and storage runtime for Knowledge aggregate CRUD and query.

Chat tools remain read-only and do not depend on Obsidian at runtime. Administrator REST mutations are permission-gated by AtlasClaw Core and never become chat tools.

## Configuration

Minimum instance:

```json
{
  "tenant_id": "-1",
  "vault_path": "/Users/shared/knowledge-vault",
  "include_globs": "**/*.md",
  "exclude_globs": ".obsidian/**,.git/**,**/.*/**",
  "max_file_bytes": 1048576,
  "max_chunk_chars": 1800,
  "max_context_chars": 24576,
  "max_result_chars": 3072,
  "max_attachments": 20,
  "max_attachment_bytes": 26214400,
  "max_total_attachment_bytes": 104857600,
  "conversion_timeout_seconds": 180,
  "max_document_pages": 200,
  "max_conversion_output_chars": 1000000,
  "max_rendered_page_bytes": 20971520
}
```

`include_globs` and `exclude_globs` accept comma-separated glob patterns relative to `vault_path`.

`tenant_id` owns the complete Vault instance. A concrete CMP tenant ID limits discovery,
Chat access, and REST publication to that tenant; `-1` makes the Vault a CMP cross-tenant
knowledge base. Knowledge manifests do not repeat tenant ownership.

The provider has no credential fields. Access is controlled by the existing AtlasClaw provider instance and role permissions; Create, Update, Unpublish, and Delete additionally require an AtlasClaw administrator identity.

## Knowledge REST Runtime

`runtime-api.json` registers these routes automatically under the selected provider type and instance:

- `POST /api/providers/markdown-vault/{providerInstance}/knowledge/documents`
- `GET /api/providers/markdown-vault/{providerInstance}/knowledge/documents/{knowledgeId}`
- `PUT /api/providers/markdown-vault/{providerInstance}/knowledge/documents/{knowledgeId}`
- `PUT /api/providers/markdown-vault/{providerInstance}/knowledge/documents/{knowledgeId}/unpublish`
- `DELETE /api/providers/markdown-vault/{providerInstance}/knowledge/documents/{knowledgeId}`
- `POST /api/providers/markdown-vault/{providerInstance}/knowledge/query`

Provider identity comes from the URL and is not repeated in multipart metadata or query JSON. Core authenticates the caller, enforces provider-instance access and the manifest's `admin`/`provider_user` policy, then dispatches the request. This provider parses multipart/JSON input and owns all Knowledge-specific validation and behavior.

Multipart metadata and content fields are each limited to 1 MiB before buffering;
attachments must be real file parts and obey per-file plus aggregate limits. Query input
is bounded to 4096 query characters, 50 string keywords, 256 characters per keyword,
4096 keyword characters in total, and 256 actual phrase/token scoring work units per
Vault chunk so repeated terms across different keywords cannot amplify CPU work.

- Create stores `<vault>/<targetPath>/<knowledgeId>/` when a safe relative `targetPath` is supplied, otherwise `<vault>/<knowledgeId>/`.
- Read, Update, Delete, and Query locate the aggregate by `knowledgeId` inside the URL-selected Vault, so callers do not send filesystem paths.
- REST callers send `tenantId` only as request authorization context. The provider validates it against the Vault's `tenant_id` and does not persist it in Knowledge metadata.
- Unpublish moves the aggregate into provider-owned hidden state, so Chat and REST query cannot retrieve it. Updating the same Knowledge publishes it again and reuses attachment Markdown/assets when `fileId`, checksum, and conversion version are unchanged. Delete permanently removes either published or unpublished state.
- Update is a complete snapshot replacement and cannot implicitly move an existing aggregate.
- Each aggregate stores `index.md`, `manifest.json`, original binaries, attachment Markdown, and asset directories. The temporary snapshot replaces the live directory only after every attachment succeeds.
- PDF and validated DOCX/PPTX/XLSX text layers are extracted locally. Legacy DOC/PPT/XLS files are rejected. Images and textless scanned pages use the configured visual-capable Agent model for OCR and visual interpretation.

Local Office extraction requires LibreOffice (`soffice` or `libreoffice`), scanned-page rendering requires Poppler `pdftoppm`, and the provider runtime requires `pypdf`. Linux/macOS advisory file locking coordinates REST writes with read-only chat tools; cancelled lock waiters close their descriptors, and marker-validated transaction journals recover interrupted swaps. The deployment must provide these executables on `PATH`; image or scanned-page requests additionally require a model that accepts image input through Core's generic visual bridge.

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

- Chat-tool writes or edits
- Moving an existing aggregate to a different `targetPath`
- Canvas, Bases, Dataview execution
- Obsidian desktop automation
