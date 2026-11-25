# Provider Extension v1 + audit-report Provider — Implementation Tasks

> **For agentic workers:** REQUIRED: follow tasks in order. Steps use checkbox (`- [x]`) syntax.
> Spec: `<atlasclaw>/docs/PROVIDER-EXTENSION-STANDARD.md`
> Design: `<providers-repo>/docs/plans/2026-11-24-audit-report-provider-design.md`
> Scope: v1 only (`ui`, `api`, `agent`, binary responses). No `settings` / `jobs` / `events` / `widgets`.

**Goal:** Ship the provider extension standard (nav/page + static assets + bridge + provider API + Host Agent) and the first provider `audit-report` with a 文件审核 page.

**Architecture:** Provider packages declare `extensions` in `provider.schema.json`; core serves their `ui/` in a same-origin iframe and dispatches `runtime-api.json` routes under `/api/providers/{type}/{instance}`. Provider backends run agent turns through `context.host.agent` with explicit skill pinning.

**Repos:** `C:\Projects\atlas\atlasclaw` (core), `C:\Projects\atlas\atlasclaw-providers` (providers).

---

## Chunk 1: Core extension platform

### Task 1: Parse `extensions` manifest

**Files**
- Modify: `app/atlasclaw/api/service_provider_schemas.py`
- Test: `tests/atlasclaw/test_provider_extensions_manifest.py`

- [x] Add `ProviderUiNav` dataclass (`id,title,icon_path,entry,access,layout,order,permissions`).
- [x] Extend `ProviderSchemaDefinition` with `extension_only`, `extensions_version`, `requires_host`, `ui_assets_root`, `ui_nav`, `api_manifest`, `api_timeout_seconds`, `api_max_body_bytes`.
- [x] Validate: id pattern, entry/assets paths safe, access enum, layout enum, order int, unknown fields ignored.
- [x] Test: valid manifest parses; bad id/path/access skipped with warning; old manifest unchanged.
- [x] Run: `pytest tests/atlasclaw/test_provider_extensions_manifest.py -q`

### Task 2: Provider extension registry

**Files**
- Create: `app/atlasclaw/core/provider_extension_registry.py`
- Test: `tests/atlasclaw/test_provider_extension_registry.py`

- [x] Aggregate nav entries from all loaded provider schemas; namespace id as `<provider>.<nav>`.
- [x] `list_nav(authz, locale)` filters `access=admin` and sorts by order/type/id.
- [x] `resolve_nav(provider, nav_id)`.
- [x] `resolve_asset(provider, nav_id, path)` path-jail under `assets_root`; reject `..`, NUL, symlinks; default `index.html`.
- [x] `resolve_provider_asset(provider, path)` path-jail under `assets/` for icons.
- [x] Tests: traversal, symlink, missing entry, sorting, admin filtering.

### Task 3: UI extension API

**Files**
- Create: `app/atlasclaw/api/routes_ui_extensions.py`
- Modify: `app/atlasclaw/api/routes.py` (register before catch-all)
- Test: `tests/atlasclaw/test_ui_extensions_api.py`

- [x] `GET /api/ui/extensions` → `{host:{version,locale,theme}, items:[{id,provider_type,nav_id,title,route,entry_url,icon_url,access,order}]}`.
- [x] `GET /api/ui/extensions/{provider}/{nav}/{asset:path}` → file Response with MIME allowlist, `nosniff`, cache headers, HTML CSP `frame-ancestors 'self'`.
- [x] `GET /api/ui/extensions/{provider}/_assets/{path}` → provider `assets/` (icons only).
- [x] Auth: login required; admin filter; 404 for unknown.
- [x] Tests: list shape, filtering, traversal, content-type.

### Task 4: `extension_only` implicit instance

**Files**
- Modify: `app/atlasclaw/core/provider_registry.py`
- Test: `tests/atlasclaw/test_provider_extension_only_instance.py`

- [x] After loading a schema with `extension_only=true`, register `_instances[type]["default"]={}` when no instance configured.
- [x] `get_all_instance_configs` / `list_instances` include default.
- [x] Router resolution works for `/api/providers/<type>/default/...`.
- [x] Tests: implicit instance visible; explicit config wins.

### Task 5: runtime-api v1 + binary responses

**Files**
- Modify: `app/atlasclaw/core/provider_http_runtime.py`, `app/atlasclaw/api/provider_http_routes.py`
- Test: `tests/atlasclaw/test_provider_http_runtime_v1.py`

- [x] Route fields: `id, response(json|binary), timeout_seconds, max_body_bytes` (defaults from extensions.api).
- [x] Validate `response` enum, positive limits, handler async.
- [x] Dispatcher: per-route body limit; `asyncio.wait_for` timeout → 504 `provider_route_timeout`.
- [x] `_build_provider_http_response` accepts `Response`/`StreamingResponse`; adds `nosniff`; HTML adds `CSP: sandbox`.
- [x] Tests: binary passthrough headers, timeout, oversize 413.

### Task 6: Host Services + Agent Host

**Files**
- Create: `app/atlasclaw/core/provider_host_services.py`, `app/atlasclaw/core/provider_agent_host.py`
- Modify: `app/atlasclaw/core/provider_http_runtime.py` (context.host), `app/atlasclaw/api/provider_http_routes.py`, `app/atlasclaw/api/sse.py` (listener hook)
- Test: `tests/atlasclaw/test_provider_agent_host.py`

- [x] `ProviderHost`: `data_dir`, `workspace_path`, `user`, `get_config`, `agent`, `emit_event`.
- [x] `ProviderAgentHost.start_run/run_skill`: validate skills, pin via `selected_capability`, hidden session, copy files to `uploads/provider/<run_id>/`.
- [x] Wrap `init_run` + `execute_agent_run` in background task; record snapshot.
- [x] `stream_run` yields buffered+live events (`run_started/phase/assistant_delta/tool_*/run_finished/run_failed`).
- [x] `get_run`, `cancel_run`, `list_artifacts` (workspace_downloads → copy into `data_dir/runs/<run_id>/`).
- [x] RBAC: runs as `host.user`; skill unavailable → `skill_unavailable`.
- [x] Tests: skill pinning, hidden session, cancel, artifact copy, restart → `host_restarted`.

### Task 7: Frontend nav + iframe page + bridge

**Files**
- Create: `app/frontend/scripts/pages/provider-extension.js`, `app/frontend/scripts/components/provider-nav.js`
- Modify: `app/frontend/scripts/app.js`, `app/frontend/scripts/components/sidebar.js`, `app/frontend/styles/*.css`, `locales/*.json`
- Test: `tests/frontend/provider-nav.test.js`

- [x] Fetch `/api/ui/extensions` after auth; render items in left sidebar below primary actions.
- [x] Dynamic route `/ext/:provider/:nav` → page with full-height iframe + loader + failure panel.
- [x] Bridge: send init, listen ready/title/toast/navigate/close; origin check; 5s ready timeout.
- [x] Styles + i18n (`nav.*`, `ext.loadFailed`).
- [x] Tests: render/filter/active, bridge messages.

---

## Chunk 2: audit-report provider

### Task 8: Provider skeleton + manifests

**Files (providers repo)**
- Create: `providers/audit-report/{PROVIDER.md,provider.schema.json,runtime-api.json,README.md,assets/icon.svg,api/__init__.py,ui/*}`
- Move: `skills/audit-report` → `providers/audit-report/skills/audit-report`
- Test: `providers/audit-report/test/test_provider_layout.py`

- [x] Manifest: `extension_only`, `runtime_capabilities:["documents","audit"]`, `extensions.ui.nav`, `extensions.api`.
- [x] `runtime-api.json` routes per design (list/upload/detail/audit/file/report/delete).
- [x] Parse with core validator; layout test asserts files exist, handlers async, paths safe.

### Task 9: Provider store + document APIs

**Files**
- Create: `providers/audit-report/api/store.py`, `api/handlers.py` (documents part), `api/report_no.py`
- Test: `providers/audit-report/test/test_store.py`, `test_handlers_documents.py`

- [x] SQLite store in `host.data_dir` (WAL), schema per design.
- [x] `POST /documents` multipart: validate pdf/docx, size ≤20 MiB, hash, probe pages, extract report_no, save file, return record.
- [x] `GET /documents` q/status/page/page_size; `GET /documents/{id}`; `DELETE`.
- [x] `GET /file` and `/report` binary responses; ownership checks.
- [x] Tests: CRUD, pagination, ownership, traversal, 404/413.

### Task 10: Audit orchestration via Agent Host

**Files**
- Create: `providers/audit-report/api/audit_service.py`
- Modify: `api/handlers.py`
- Test: `providers/audit-report/test/test_audit_service.py`

- [x] `POST /documents/{id}/audit` → `host.agent.run_skill("audit-report", files=[...])`, store run_id, status `running`, 409 if already running.
- [x] Background consumer: map events → progress/phase; on finish copy artifacts, parse `verification.json` counts; status `completed`.
- [x] Failure/timeout/cancel → `failed` + stable code; retry allowed.
- [x] Tests with fake host.agent: success, failure, concurrent 409, artifact copy.

### Task 11: 文件审核 UI

**Files**
- Create: `providers/audit-report/ui/{index.html,app.js,style.css}`
- Test: `providers/audit-report/test/test_ui_contract.py` (DOM/strings)

- [x] Header, tabs, filters, table (6 columns), status badges, row actions, footer count per design screenshot.
- [x] Upload dialog (drag/drop, multi-file, progress), 3s polling while running, result panel with counts + evidence + open report.
- [x] Bridge init/ready/locale/theme/toast; relative asset URLs.
- [x] Tests: required elements/actions/labels; no absolute asset paths.

---

## Chunk 3: Integration & verification

### Task 12: Remove standalone skill & docs

- [x] Delete `skills/audit-report` from providers repo root (moved into provider).
- [x] Update `README.md`, `PROVIDER.md`, `requirements.txt` references.
- [x] Verify `SkillRegistry` loads exactly one `audit-report` from provider.

### Task 13: Deploy & E2E on 192.168.12.153

- [x] Package core + providers; deploy to `/opt/atlasclaw`; restart service.
- [x] Verify `/api/ui/extensions` returns 文件审核; nav renders; page loads.
- [x] Upload sample PDF → audit → completed → HTML report opens inline.
- [x] Record evidence (status, counts, report bytes) in the final report.

---

## Verification commands

```bash
# core
cd C:\Projects\atlas\atlasclaw
.\.venv\Scripts\python.exe -m pytest tests\atlasclaw\test_provider_extensions_manifest.py tests\atlasclaw\test_provider_extension_registry.py tests\atlasclaw\test_ui_extensions_api.py tests\atlasclaw\test_provider_http_runtime_v1.py tests\atlasclaw\test_provider_agent_host.py -q

# frontend
cd app\frontend && npm test -- --colors=false

# provider
cd C:\Projects\atlas\atlasclaw-providers
C:\Projects\atlas\atlasclaw\.venv\Scripts\python.exe -m pytest providers\audit-report\test -q
```

---

## Implementation notes (2026-11-24)

- `audit-report` skill declares `execution: standard` so it runs on the standard
  skill runtime instead of provider-bound routing; `provider_agent_host` resolves
  bare skill ids to registry names and pins the catalog capability entry.
- Extension-only providers are kept by `resolve_provider_instance_config` even
  without auth modes, so their implicit `default` instance reaches capability
  discovery.
- `ProviderAgentHost` passes the full provider instance catalog into the run so
  provider-bound capability entries are indexed.
- `audit_service` falls back to the newest HTML report in the shared work dir when
  the agent did not return a `download_path` artifact.
- Frontend iframe listener is registered before setting `src` to avoid missing a
  fast `atlasclaw:ready` message.

### UI refinements (user feedback)

- Provider nav renders as plain white text (no icon, no underline); stylesheet is now
  loaded globally instead of only on the extension route.
- Sidebar search is collapsed: a `Workspace` row with a search icon toggles the
  session search input.
- The provider page no longer shows redundant `Uploads` / `Audit results` tabs;
  one unified document list remains.
- Upload picker is triggered explicitly from the drop zone and the iframe sandbox
  now allows modals/downloads, fixing the file chooser in embedded mode.

### Deterministic audit pipeline (2026-11-24, later revision)

The single-agent "audit the whole document" run was unreliable: for a 66-page PDF
the model spent every turn probing extraction (`probe.py` ... `probe13.py`),
`skill_exec` timed out, and continuation runs accumulated a 150+ message
transcript (48% duplicates) before ending with `report_missing`.

Replaced it with a provider-driven pipeline:

- `api/batch_audit.py` parses the 19 rules from
  `skills/audit-report/references/audit-rules.md`, splits extracted page text
  into <=60k-character chunks (max 8, overflow is reported as 未执行项) and rules
  into three balanced batches.
- `api/audit_service.py` runs `extract_report.py --no-images` itself, then calls
  `agent.start_run()` per chunk/batch with no pinned skill and no tools. Each
  call must return one JSON verdict per rule; unparsable output is retried once
  and then recorded as `REVIEW`, so a report is always produced.
- The provider merges verdicts, writes `documents/<id>/audit-report.md` and
  `verification.json`, and renders `report.html` with
  `render_report.py --delivery`.
- Documents without a text layer fail fast with `no_text_layer` instead of
  looping; seal/signature/photo rules become `REVIEW` because the runtime has no
  OCR or vision path.
- `start_document_audit` clears `run_id` while preparing, otherwise a stale run id
  makes `reconcile_document` mark the fresh audit as `host_restarted`.

### Result view, standards library and column cleanup (2026-11-24)

- The document table dropped the 报告编号 column; search now targets the file name.
- `查看结果` and `下载报告` were two entry points to the same HTML. The row now has
  only `查看结果`, which opens an in-page 19-rule result table
  (`GET /documents/{id}/results`), and the download lives inside that dialog
  (`GET /documents/{id}/report/download`, attachment). `GET /report` stays as an
  inline preview.
- Page title renamed 文档处理 -> 文档审核.
- New 审核标准库 tab: `GET/POST /standards`, `GET /standards/{id}/file`,
  `DELETE /standards/{id}`, stored in `audit_standards` plus
  `standards/<id>/original.pdf`. Text is extracted lazily at audit time and the
  three newest standards (up to 6000 chars each) are embedded in every batch
  prompt; the generated report lists them under `审核依据`.

### Provider sessions hidden from the chat sidebar (2026-11-24)

Every batched audit run creates an ephemeral session
(`agent:main:user:<uid>:provider-audit-report-<run_id>`). Core deleted the
transcript but concurrent metadata saves could resurrect the entry, so the chat
sidebar listed dozens of conversations titled with the audit prompt.

- `GET /api/sessions` now filters any key containing `:provider-`
  (`_is_provider_internal_session`), which covers runs whose cleanup was skipped.
- Existing leftovers were pruned from `workspace/users/<uid>/sessions/sessions.json`
  on the 153 deployment.
- Verified: opening 文件审核 or running an audit no longer adds a sidebar entry.

### Rule packs and the shared standards library (2026-11-24)

- Adopted the rule-file skill layout (`skills/audit-report/rules/`): `builtin/rules.json`
  is the execution source for the 19 rules; `_rules.py`, `rules_compile.py`,
  `rules_validate.py` and `rules_sync.py` manage packs.
- `batch_audit.load_rule_set(skill_dir, rules_dir=...)` reads builtin plus every
  active pack, and `rule_batches` splits all rules into batches of seven, so every
  rule reaches the model exactly once per chunk.
- The standards library moved out of `<tenant>/<user>/` into
  `<workspace>/.provider-data/audit-report/_shared/`:
  - `standards/<id>/{original.*,standard.json}` shared by all provider users;
  - `rules/config.json` + `rules/packs/<pack>/` compiled from uploads.
- Uploading a rule document compiles it in a background task
  (`rules_compile.py` then `rules_validate.py --activate`); failures keep the file
  and expose the compiler error, and `POST /standards/{id}/recompile` retries.
- UI: 审核标准库 shows 规则数 / 编译状态 (编译中/已启用/编译失败), offers 重新编译,
  and polls while compilation is running.
- Verified on 153: a 3-rule md document compiled to `pack-*@1.0.0`, audit progress
  showed `R01-R07 ... X03`, `verification.json` contained R01-R19 plus X01-X03, and
  a second non-admin user saw the same shared library.
