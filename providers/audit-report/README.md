# 文件审核 Provider

Provider-owned document workspace for third-party inspection reports.

- Left navigation entry: **文件审核** (`/ext/audit-report/file-audit`)
- UI: `ui/` (iframe page served by AtlasClaw)
- Backend API: `runtime-api.json` → `api/handlers.py`
- Skill: `skills/audit-report/` (rule references + rule packs + extract/render scripts)
- Rules: `skills/audit-report/rules/` (builtin 19 + active packs from `config.json`)
- Pipeline: `api/audit_service.py` → skill `scripts/run_document_audit.py`
- Legacy `api/batch_audit.py` utilities remain for existing rule-pack and
  historical-result compatibility; new audits use the skill workflow above.

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
| GET | `/documents/{id}/desensitized` | Prepared PDF (inline preview) |
| GET | `/documents/{id}/desensitized/download` | Prepared PDF (attachment) |
| GET | `/documents/{id}/report` | Audit PDF, or legacy HTML (inline preview) |
| GET | `/documents/{id}/report/download` | Audit PDF, or legacy HTML (attachment) |
| DELETE | `/documents/{id}` | Delete record and files |
| GET | `/standards` | List uploaded audit standards |
| POST | `/standards` | Upload shared references (PDF/DOCX/MD/TXT/Excel) for local reading |
| POST | `/standards/{id}/refresh` | Read a shared reference again |
| POST | `/standards/{id}/recompile` | Recompile one standard into a rule pack |
| GET | `/standards/{id}/file` | Download a standard file |
| DELETE | `/standards/{id}` | Delete a standard, its pack and config entry |

## Storage

- Per-user default data: `context.host.data_dir` containing `audit.db` and `documents/<id>/`
- With `reports_dir`: `<reports_dir>/<tenant>/<user>/` containing `audit.db` and `documents/<id>/`
- Prepared PDF: `documents/<id>/prepared/desensitized.pdf`
- Each new attempt: `documents/<id>/runs/<attempt-id>/` containing the private
  library snapshot, model originals, workflow manifests, screenshots, and PDF.
- Historical `documents/<id>/report.html` and legacy results remain readable.
- Shared library: `context.host.shared_data_dir` by default, or the configured `standards_dir`
  - `standards/<id>/original.*` + `standard.json` (reference, read state, and optional legacy compile state)
  - `rules/config.json` (active packs) and `rules/packs/<pack>/` (compiled rules)
  - With a configured shared root, `rules/builtin/rules.json` stores the builtin 19 rules; an existing file is kept.
- The shared library is visible to every user who can open the provider; it is
  never stored under a user directory.

To store provider documents and standards outside the workspace, set these optional
absolute paths on the `default` instance in `/opt/atlasclaw/atlasclaw.json`:

```json
{
  "service_providers": {
    "audit-report": {
      "default": {
        "reports_dir": "/opt/atlasclaw/documents/provider/audit-report/reports",
        "standards_dir": "/opt/atlasclaw/documents/provider/audit-report/standards"
      }
    }
  }
}
```

Blank values preserve the Host Services storage locations. The service account must
have read/write access. Configured reports storage partitions the entire per-user
workspace, including `audit.db`, as `reports/<tenant>/<user>/...`. Configured shared
storage keeps the existing `standards/<id>/` plus `rules/` layout.
Changing these settings does not migrate existing data or rewrite stored file paths;
stop AtlasClaw and migrate the provider index and files before enabling new roots.

## Dependencies

Python dependencies (`pymupdf`, `python-docx`, `openpyxl`, `httpx`, and
`python-dotenv`) come from AtlasClaw's runtime/build. LibreOffice converts Word;
CJK fonts support Chinese PDF output. The Provider does not install packages.

## Notes

- Single audit per user at a time; concurrent requests return `409`.
- In a deployment with one AtlasClaw worker per workspace, interrupted audits are
  marked `failed` with `host_restarted` when viewed or when the user starts another audit.
- Every audit first desensitizes the report and snapshots all shared references
  and enabled rule packs. Excel is parsed locally. All business checking is done
  by the LLM, including measurements, dates, standards, and ledger comparisons.
- The skill identifies projects from complete extracted text, audits each project
  with its full native text, preceding text, parsed materials, and all enabled
  rules, then requests a global Markdown report. Every accepted project original
  is appended. Numeric and other business judgments remain with the LLM.
- LLM requests use the configured Core model. The audit sends text and parsed
  source positions only; it does not submit report-page images. Findings that
  require visual evidence are marked as evidence-limited, without claiming the
  original lacks content merely because it was redacted or not extracted.
  Incomplete or failed calls prevent report publication; no page or rule is
  silently skipped to produce a pass.
- Each uploaded standard owns its compiled pack. A failed recompile preserves the
  previously active pack. Recompile legacy same-name uploads to restore their
  individual rule sets if an earlier upload overwrote the original pack.
- Rule packs: drop a rule document into `skills/audit-report/rules/_inbox/`,
  run `rules_sync.py` then `rules_validate.py <pack.json> --activate`. Only
  packs listed in `rules/config.json` are loaded; draft packs stay inactive.
  Ordinary shared references do not need compilation. An unreadable enabled
  source or missing shared file fails snapshot preparation explicitly.
- Evidence screenshots use model-cited physical PDF pages, including listed
  page ranges and continuation headers. Failed quote positioning falls back to
  the cited full page. Local code inserts screenshots and converts Markdown to
  PDF without changing the model's business findings.
- The prepared PDF remains downloadable after a later audit failure. A re-audit
  clears the prior report reference and publishes only its own successful PDF.
