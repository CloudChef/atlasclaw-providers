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
  - Preview and download the generated HTML audit report

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
- the `audit-report` skill under `skills/audit-report/`. The provider runs it as
  a deterministic pipeline: `extract_report.py` pre-extracts page text, small
  rule batches are judged by `context.host.agent.start_run()` (structured JSON,
  no tools), and `render_report.py` renders the final HTML report.

Documents and reports are stored in the provider data directory
(`<workspace>/.provider-data/audit-report/<tenant>/<user>/`); the provider owns
its own SQLite index and never writes to core tables.

## Audit pipeline

1. Extract text with `skills/audit-report/scripts/extract_report.py --no-images`.
2. Load `skills/audit-report/rules/builtin/rules.json` plus every active pack listed
   in `rules/config.json` (builtin 19 rules + customer/standard packs).
3. Split page text into bounded chunks and the enabled rules into three batches.
4. Ask the agent for one JSON verdict per rule per chunk (stateless runs, so a
   long document cannot exhaust one run or drift into tool loops).
5. Merge verdicts, mark missing judgements as `REVIEW`, and build the Markdown
   report plus `verification.json`.
6. Render `report.html` with `render_report.py --delivery` and store its path.
7. Attach up to three uploaded standard files (审核标准库) as extra judging
   criteria in every batch prompt; the report records them under 审核依据.

Rule packs are data, not code: add the rule document to
`skills/audit-report/rules/_inbox/`, run `rules_sync.py`, then
`rules_validate.py <pack.json> --activate`. Draft packs are not loaded by the
provider until activated.

Because the provider owns extraction, merging and rendering, an audit produces a
downloadable report whenever the document has a readable text layer. Reports
without a text layer fail fast with `no_text_layer` instead of looping.

## Contract

- Extension manifest version: 1
- Host API: `>=1.0 <2.0`
- Backend API prefix: `/api/providers/audit-report/default`
- No custom configuration fields; `extension_only` is enabled so AtlasClaw
  registers an implicit `default` instance.

## Runtime dependencies

`pymupdf`, `python-docx` (declared in `skills/audit-report/requirements.txt`).
