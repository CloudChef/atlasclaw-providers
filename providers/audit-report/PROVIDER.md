---
provider_type: audit-report
display_name: 文件审核
version: "1.0.0"

keywords:
  - audit
  - report
  - pdf
  - docx
  - compliance
  - 审核
  - 检测报告
  - 报告复核

capabilities:
  - Upload PDF/Word inspection reports
  - Run the builtin 19-rule compliance audit plus any active rule packs through the audit-report skill
  - Track audit progress and review findings
  - Share locally parsed test standards and equipment ledgers
  - Preview and download the desensitized PDF and audit PDF

use_when:
  - User wants to upload or review third-party test/inspection reports
  - User asks for a document workspace with audit status and results
  - User references 文件审核, 报告审核, 报告复核

avoid_when:
  - User only wants to chat about a file that is not an inspection report
  - User wants to edit or convert Word/PDF documents
---

# 文件审核 Provider

Provider-owned document workspace for third-party inspection reports.

It contributes:

- a left-navigation entry **文件审核** (`/ext/audit-report/file-audit`);
- a self-contained UI under `ui/`, served by AtlasClaw as a provider extension;
- a backend HTTP API declared in `runtime-api.json`;
- the `audit-report` skill under `skills/audit-report/`. The provider prepares
  a desensitized PDF, snapshots the shared references and enabled rules, and
  calls the skill's `audit_prepared()` workflow. Scripted directory, project,
  and summary requests use the configured Core model through
  `context.run_text(prompt, system_prompt, timeout_seconds)`; the system prompt
  is loaded from `skills/audit-report/references/audit-system.md`. The workflow
  submits extracted text and parsed materials only, not page images. These
  internal callbacks do not go through the
  Agent Host capability selector. Ordinary Host agent runs and their user-enabled
  skills remain available to separate tool-using workflows. The Provider neither
  reads nor forwards model credentials.

The provider owns its SQLite index under its report data root and never writes
to core tables. By default, the report data root is `context.host.data_dir`.
An instance can set absolute `reports_dir` and `standards_dir` roots to place
the user index, document files, and shared standards library outside the
workspace. The report root is partitioned by tenant and user; standards remain
shared.

## Audit pipeline

1. Reuse local desensitization, convert Word to PDF, and make the prepared PDF
   independently available for download before any model submission.
2. Snapshot all shared files and enabled rule JSON; parse Excel locally with
   physical cell positions. Filenames containing 台账 identify ledgers;
   检测标准 identifies standards, and other files remain supplementary evidence.
3. Read extracted report text and ask the LLM to identify projects; long reports
   are scanned in text chunks of at most 32 formal pages and merged under
   page-coverage checks. This is a per-request directory batch size, not a total
   report-page limit; actual requests remain subject to the selected model/API's
   native context, output, and service limits and fail closed when exceeded.
4. For each project, submit its complete native text, preceding text, all parsed
   reference materials, and enabled rules for a complete LLM audit.
5. Ask the LLM for the global report and append every final project original.
   Business decisions, including dates, measurements, standards, and ledger
   comparisons, are made by the LLM. Local code validates structure and fixed
   rule metadata.
6. Capture the model-cited source pages locally, insert screenshots, and render a PDF.
   Markdown originals, provenance, and intermediate HTML stay available locally
   for traceability. Legacy HTML reports remain readable.

The standards library uses the provider-wide `context.host.shared_data_dir` by
default, or `standards_dir` when configured.
Ordinary reference uploads are read locally and do not automatically create
rule packs. Readability is separate from rule compilation and audit verdicts.

Rule packs are data, not code: add the rule document to
`skills/audit-report/rules/_inbox/`, run `rules_sync.py`, then
`rules_validate.py <pack.json> --activate`. Draft packs are not loaded by the
provider until activated.

Page images do not accompany the model request. For matters that cannot be
verified from text and parsed materials, the report states the evidence
limitation; desensitization or extraction gaps do not prove that the original
document is missing content. Missing, incomplete, or truncated model responses
fail the task; they are never published as a pass.

## Contract

- Extension manifest version: 1
- Host API: `>=1.0 <2.0`
- Backend API prefix: `/api/providers/audit-report/default`
- Optional instance settings `reports_dir` and `standards_dir` must be absolute
  paths when nonblank. Blank values retain Host Services defaults.
- `extension_only` is enabled so AtlasClaw registers an implicit `default`
  instance.

Example `atlasclaw.json` configuration:

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

The service account needs read/write access to both configured roots. The
report data root is `reports/<tenant>/<user>/` and contains `audit.db` plus
`documents/<id>/`. The shared root contains
`standards/<id>/` and `rules/`, including the provider's builtin rules at
`rules/builtin/rules.json`. Existing builtin files are preserved.
Changing either setting does not migrate existing files or rewrite persisted
paths; stop AtlasClaw and migrate the provider data before enabling new roots.

## Runtime dependencies

Python dependencies are supplied by the AtlasClaw runtime: `pymupdf`,
`python-docx`, `openpyxl`, `httpx`, and `python-dotenv`. Word conversion uses
LibreOffice; PDF rendering uses an installed CJK font or MuPDF's CJK fallback.
