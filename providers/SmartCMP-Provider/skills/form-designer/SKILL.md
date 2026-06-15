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
  - 表单 schema
  - 生成表单
  - 修改表单
  - 完善表单
  - 设计表单

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
tool_design_description: "Normalize and return a SmartCMP Angular form schema JSON draft generated or modified by the LLM. For new forms, pass the generated schema_json. For existing forms, first call smartcmp_read_form_schema, then pass the modified schema_json. This tool never writes to CMP."
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
2. Modify the returned schema JSON according to the user's request.
3. Call `smartcmp_design_form_schema` with `mode=modify`, the modified
   `schema_json`, the source `form_url`, and a short `change_summary`.
4. Return the normalized schema JSON and the short change summary.

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
