---
name: "form-designer"
description: "SmartCMP form designer skill. Generate, read, normalize, and refine SmartCMP Angular form schema JSON without submitting requests or saving changes to CMP."
provider_type: "smartcmp"
instance_required: "true"

triggers:
  - form schema
  - design form
  - generate form
  - modify form
  - improve form
  - SmartCMP form
  - Angular form
  - JavaScript form logic
  - dynamic form interaction
  - business group code
  - application code
  - owner login id
  - Key-Value Tags
  - Cloud Resource Tags
  - attachments
  - 表单 schema
  - 生成表单
  - 修改表单
  - 完善表单
  - 设计表单
  - 表单 JavaScript
  - 动态表单
  - 业务组代码
  - 应用代码
  - 负责人
  - 附件

use_when:
  - User wants to create a new SmartCMP Angular form schema from natural language or a field list
  - User wants to inspect or modify an existing SmartCMP form from a UI edit URL
  - User wants SmartCMP form JSON normalized before copying it into CMP manually
  - User asks for hidden fields, request visibility, approval visibility, labels, descriptions, selects, or table-style array fields in a form

avoid_when:
  - User wants to submit a SmartCMP service request or ticket (use request skill)
  - User wants to check submitted request status (use request skill)
  - User wants to approve or reject a request (use approval skill)
  - User wants to browse service catalogs or resource data unrelated to form schema design (use datasource skill)
  - User wants to save, update, publish, or delete a form in CMP

examples:
  - "Generate a SmartCMP form with server name, CPU, memory, and approval-only cost fields"
  - "按照这些字段生成一个 SmartCMP 表单 schema"
  - "Use this form URL and add a hidden environment field"
  - "完善这个表单，让密码字段在申请和审批都可见"
  - "Normalize this SmartCMP Angular form schema"

related:
  - datasource

tool_read_name: "smartcmp_read_form_schema"
tool_read_description: "Read one existing SmartCMP form schema from a current-instance UI edit URL. This tool is read-only: it only accepts URLs like #/main/service-model/forms/edit/<uuid> and calls GET /forms/<uuid>. It never saves, submits, updates, or deletes CMP data."
tool_read_entrypoint: "scripts/read_form.py"
tool_read_groups:
  - cmp
  - form-designer
tool_read_capability_class: "provider:smartcmp"
tool_read_priority: 105
tool_read_result_mode: "llm"
tool_read_cli_positional:
  - form_url
tool_read_parameters: |
  {
    "type": "object",
    "properties": {
      "form_url": {
        "type": "string",
        "description": "SmartCMP UI form edit URL from the selected provider instance, for example https://cmp/#/main/service-model/forms/edit/<uuid>. External hosts and non-form-edit routes are rejected."
      }
    },
    "required": ["form_url"]
  }

tool_design_name: "smartcmp_design_form_schema"
tool_design_description: "Normalize and return a SmartCMP Angular form schema JSON draft generated or modified by the LLM. For new forms, pass the generated schema_json. For existing forms, pass either the complete modified schema_json or form_url plus catalog_fields_json for deterministic catalog field insertion. This tool never writes to CMP."
tool_design_entrypoint: "scripts/design_form.py"
tool_design_groups:
  - cmp
  - form-designer
tool_design_capability_class: "provider:smartcmp"
tool_design_priority: 110
tool_design_result_mode: "llm"
tool_design_cli_flag_overrides:
  mode: "--mode"
  schema_json: "--schema-json"
  form_url: "--form-url"
  change_summary: "--change-summary"
  catalog_fields_json: "--catalog-fields-json"
tool_design_parameters: |
  {
    "type": "object",
    "properties": {
      "mode": {
        "type": "string",
        "enum": ["new", "modify"],
        "description": "Use new for a brand-new form schema, or modify for a schema derived from an existing form URL."
      },
      "schema_json": {
        "type": "string",
        "description": "Complete SmartCMP Angular form schema JSON produced or modified by the LLM. The script will normalize structure and return the final schema."
      },
      "form_url": {
        "type": "string",
        "description": "Optional source SmartCMP form edit URL for modify mode. The tool validates this URL and may read the source schema when schema_json is omitted."
      },
      "change_summary": {
        "type": "string",
        "description": "Short user-facing description of what changed or what was generated."
      },
      "catalog_fields_json": {
        "type": "string",
        "description": "Optional JSON array of on-demand SmartCMP catalog field insertions, for example [{\"field\":\"businessGroup.code\"}, {\"field\":\"application.code\"}]. Prefer omitting fieldKey for SmartCMP standard fields when backend processing must recognize the UI key."
      }
    },
    "required": ["mode"]
  }
---

# form-designer

Design, read, and normalize SmartCMP Angular form schema JSON. This skill is
only for form schema authoring. It does not submit service requests and does not save
changes to CMP.

## Boundaries

- Never call request submission scripts or any request workflow tool.
- Never call CMP write methods such as POST, PUT, PATCH, or DELETE for forms.
- Existing form URLs are used only as read-only source material.
- Final changes are copied from the AtlasClaw response by the user; this skill
  does not persist them.

## Workflow

### New Form

1. Translate the user's field list or natural-language requirement into a
   complete SmartCMP Angular schema JSON object.
2. Preserve the language requested by the user. Generate bilingual
   `i18nTitle` or `i18nPlaceholder` only when the user asks for bilingual output.
3. Call `smartcmp_design_form_schema` with `mode=new` and the draft
   `schema_json`.
4. Return the normalized schema JSON and a short change summary.

### Modify Existing Form

1. Call `smartcmp_read_form_schema` with the SmartCMP form edit URL.
2. If the user only asks to add supported catalog context fields, call
   `smartcmp_design_form_schema` with `mode=modify`, the source `form_url`,
   `catalog_fields_json`, and a short `change_summary`; omit `schema_json` so
   the tool reads the source schema and inserts those fields deterministically.
3. For other schema edits, modify the complete schema JSON from the tool result
   metadata. Never pass truncated, summarized, or ellipsized JSON as
   `schema_json`.
4. Call `smartcmp_design_form_schema` with `mode=modify`, the complete modified
   `schema_json`, the source `form_url`, and a short `change_summary`.
5. Return the normalized schema JSON and the short change summary.

## Output Contract

- Final user-visible output must include the complete normalized schema as a
  fenced JSON block. Do not replace the schema JSON with only tables, summaries,
  or field descriptions.
- If `smartcmp_design_form_schema` returns a successful `Schema JSON` block,
  treat that tool output as authoritative. Do not replace a successful design
  result with a provider authentication error unless the tool output itself
  reports authentication failure, HTTP 401, or HTTP 403. New-form design is a
  local schema-authoring operation.
- A concise change summary may precede the JSON. Warnings may follow the summary
  when the script reports assumptions or risky JavaScript patterns.

## Schema Rules

- Root schema should be `type: object` with a `properties` object.
- Top-level fields should include stable `id`, numeric `index`, `type`, and
  `widget.id`.
- Top-level fields should include `config.visibility.allowInRequest` and
  `config.visibility.allowInApproval` unless the user explicitly provided a
  different visibility rule.
- Preserve `hidden`, `condition`, `fieldsets`, `selectDatas`, `value`, `items`,
  and unknown schema keys.
- Use warnings for ambiguous or unsupported structures instead of inventing CMP
  workflow behavior.

## Catalog Context Fields

- Standard service-catalog fields are not added to every form. Add known
  catalog fields only when the user asks for catalog context such as business
  group code, application code, owners, attachments, or tags.
- For supported catalog context fields, pass them through
  `catalog_fields_json` and do not also hand-write duplicate catalog fields in
  `schema_json`. Prefer SmartCMP UI keys such as `businessGroup`, `projects`,
  `owners`, `attachments`, `keyValueTag`, and `cloudResourceTag` when backend
  standard-field handling must recognize the field. If a custom `fieldKey` is
  supplied for a catalog field, the design tool keeps it and emits a warning
  because CMP backend standard-field handling may not recognize that custom key.
  User-defined non-catalog fields should stay in `schema_json` and may use the
  user's own field keys without this warning.
- In modify mode, prefer `form_url` plus `catalog_fields_json` with no
  `schema_json` when the requested change is only adding supported catalog
  context fields. This preserves existing JavaScript and unknown keys without
  requiring the LLM to copy a long schema.
- Known meanings:
  - `businessGroup.id`, `businessGroup.name`, `businessGroup.code`: business
    group context from the catalog route; generated schema id is
    `businessGroup`.
  - `application.id`, `application.name`, `application.code`: application
    context; generated schema id is the UI source key `projects`.
  - `owners`, `owners.id`, `owners.name`, `owners.userName`,
    `owners.userLoginId`: owner list and owner identity fields; generated
    schema id is `owners`.
  - `name`, `description`, `number`, `executeTime`: standard request/catalog
    name, description, number/count, and execution time fields.
  - `attachments`: attachment list.
  - `keyValueTag`: SmartCMP Key-Value Tags.
  - `cloudResourceTag`: SmartCMP Cloud Resource Tags.
  - The analyzed Linux VM catalog stores bottom Key-Value Tags resource data
    under `Compute.tags_copy`.
- Generated catalog fields should be marked with
  `x-smartcmp.builtinCatalogField`.

## JavaScript Field Logic

- For dynamic form behavior, generate field-level JavaScript under
  `config.value.expression`.
- Use `model`, `sourceParams`, `schema`, and `cfg` for form context. DOM probing
  is only a compatibility fallback for SmartCMP catalog context values.
- The skill and scripts must not execute generated JavaScript.

```json
{
  "config": {
    "value": {
      "source": "mock",
      "method": "mock",
      "expression": "function(model, sourceParams, schema, unused, cfg) { var bg = model.businessGroup || {}; var app = model.projects || {}; if (Array.isArray(app)) { app = app[0] || {}; } return [bg.code, app.code].filter(Boolean).join('-'); }"
    }
  }
}
```
