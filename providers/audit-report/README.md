# 文件审核 Provider

Provider-owned document workspace for third-party inspection reports.

- Left navigation entry: **文件审核** (`/ext/audit-report/file-audit`)
- UI: `ui/` (iframe page served by AtlasClaw)
- Backend API: `runtime-api.json` → `api/handlers.py`
- Skill: `skills/audit-report/` (rule references + rule packs + extract/render scripts)
- Rules: `skills/audit-report/rules/` (builtin 19 + active packs from `config.json`)
- Pipeline: `api/audit_service.py` + `api/batch_audit.py`

## API

Prefix: `/api/providers/audit-report/default`

| Method | Path | Purpose |
|---|---|---|
| GET | `/documents` | List (`q`, `status`, `page`, `page_size`) |
| POST | `/documents` | Upload PDF/DOCX (`multipart/form-data`, field `file`) |
| GET | `/documents/{id}` | Detail, progress, result summary |
| POST | `/documents/{id}/audit` | Start or retry the audit |
| GET | `/documents/{id}/file` | Original file |
| GET | `/documents/{id}/results` | Per-rule verdicts for in-page result view |
| GET | `/documents/{id}/evidence/{name}` | Rendered evidence screenshot for one finding |
| GET | `/documents/{id}/report` | Generated HTML report (inline preview) |
| GET | `/documents/{id}/report/download` | Generated HTML report (attachment) |
| DELETE | `/documents/{id}` | Delete record and files |
| GET | `/standards` | List uploaded audit standards |
| POST | `/standards` | Upload a rule document (PDF/DOCX/MD/TXT) and compile it |
| POST | `/standards/{id}/recompile` | Recompile one standard into a rule pack |
| GET | `/standards/{id}/file` | Download a standard file |
| DELETE | `/standards/{id}` | Delete a standard, its pack and config entry |

## Storage

- Per-user data: `<workspace>/.provider-data/audit-report/<tenant>/<user>/`
- Per-user index: `audit.db` (provider-owned SQLite)
- Per-user files: `documents/<id>/original.pdf`, `documents/<id>/report.html`,
  `documents/<id>/evidence/F-*.png` (one rendered page crop per finding)
- Shared library: `<workspace>/.provider-data/audit-report/_shared/`
  - `standards/<id>/original.*` + `standard.json` (rule document and compile state)
  - `rules/config.json` (active packs) and `rules/packs/<pack>/` (compiled rules)
- The shared library is visible to every user who can open the provider; it is
  never stored under a user directory.

## Dependencies

`pymupdf`, `python-docx` — declared in `skills/audit-report/requirements.txt` and
installed in the AtlasClaw runtime virtualenv.

## Notes

- Single audit per user at a time; concurrent requests return `409`.
- Interrupted runs (core restart) are marked `failed` with `host_restarted`.
- An audit loads `rules/builtin/rules.json` (19 rules) plus every active pack
  from the shared `rules/config.json`, and passes every rule to the model in
  batches of seven; packs come from standards uploaded in the 审核标准库 page.
- Audits are stateless batched runs (`agent.start_run`, no pinned skill), so
  long documents cannot exhaust one agent loop; each batch is retried once and
  unparseable or missing verdicts become `REVIEW` instead of a lost report.
- Rule packs: drop a rule document into `skills/audit-report/rules/_inbox/`,
  run `rules_sync.py` then `rules_validate.py <pack.json> --activate`. Only
  packs listed in `rules/config.json` are loaded; draft packs stay inactive.
  A broken or duplicate pack is logged and skipped instead of failing the audit.
- Documents without a readable text layer fail fast with `no_text_layer`
  (no OCR in the runtime); seal/signature/photo rules are text-only and are
  reported as `REVIEW` when the evidence is visual.
- Evidence screenshots: after the verdicts are merged, PDF findings are rendered
  to `documents/<id>/evidence/F-*.png` (quote region, falling back to the full
  page), embedded as base64 in the HTML report and shown as thumbnails in the
  in-page result view. DOCX findings keep text-only evidence because the runtime
  has no page renderer for Word documents.
