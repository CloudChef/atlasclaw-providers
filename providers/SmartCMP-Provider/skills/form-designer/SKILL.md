---
name: "form-designer"
description: "Use when creating, reading, normalizing, regenerating, or modifying SmartCMP Angular form schema JSON, including dynamic JavaScript behavior, catalog context values, visibility, selects, tables, and form edit URLs."
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
  - 表单 schema
  - 生成表单
  - 修改表单
  - 完善表单
  - 设计表单
  - 表单 JavaScript
  - 动态表单

use_when:
  - User wants to create a new SmartCMP Angular form schema from natural language or a field list
  - User wants to inspect an existing SmartCMP form or regenerate a replacement form from a UI edit URL
  - User wants SmartCMP form JSON normalized before copying it into CMP manually
  - User asks for hidden fields, request visibility, approval visibility, labels, descriptions, selects, tables, or JavaScript behavior in a form

avoid_when:
  - User wants to submit a SmartCMP service request or ticket
  - User wants to check submitted request status
  - User wants to approve or reject a request
  - User wants to save, update, publish, or delete a form in CMP

examples:
  - "Generate a SmartCMP form with server name, CPU, memory, and approval-only cost fields"
  - "Use this form URL and add a hidden environment field"
  - "Normalize this SmartCMP Angular form schema"

related:
  - datasource

tool_read_name: "smartcmp_read_form_schema"
tool_read_description: "Read one existing SmartCMP form schema from a current-instance UI edit or design URL. This tool is read-only: it accepts URLs like #/main/service-model/forms/edit/<uuid> or #/main/service-model/forms/design/<uuid> and calls GET /forms/<uuid>. It also exposes source content.model/designMode/component counts as diagnostic context. It never saves, submits, updates, or deletes CMP data."
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
        "description": "SmartCMP UI form edit/design URL from the selected provider instance, for example https://cmp/#/main/service-model/forms/edit/<uuid> or https://cmp/#/main/service-model/forms/design/<uuid>. External hosts and non-form routes are rejected."
      }
    },
    "required": ["form_url"]
  }

tool_design_name: "smartcmp_design_form_schema"
tool_design_description: "Normalize and return a SmartCMP Angular form schema JSON draft. Use mode=new for new forms, regenerate after reading a URL source for full schema replacement, and modify for deterministic normalization, catalog insertions, or deterministic value-expression updates from a trusted complete JSON or form URL source. This tool never writes to CMP."
tool_design_entrypoint: "scripts/design_form.py"
tool_design_groups:
  - cmp
  - form-designer
tool_design_capability_class: "provider:smartcmp"
tool_design_priority: 110
tool_design_result_mode: "tool_only_ok"
tool_design_cli_flag_overrides:
  mode: "--mode"
  schema_json: "--schema-json"
  form_url: "--form-url"
  change_summary: "--change-summary"
  catalog_fields_json: "--catalog-fields-json"
  value_expressions_json: "--value-expressions-json"
  requested_fields_json: "--requested-fields-json"
tool_design_parameters: |
  {
    "type": "object",
    "properties": {
      "mode": {
        "type": "string",
        "enum": ["new", "modify", "regenerate"],
        "description": "new for a new schema; regenerate for a replacement based on a URL source; modify for trusted complete JSON or deterministic inserts."
      },
      "schema_json": {
        "type": "string",
        "description": "Complete SmartCMP Angular form schema JSON. Required for new/regenerate, and required for modify unless form_url is supplied. Include only the user-requested form fields. If the user constrains the exact field set or field count in any wording or language, schema.properties and fieldsets must match that field set exactly. Computed-value source reads must not become schema properties."
      },
      "form_url": {
        "type": "string",
        "description": "Optional source SmartCMP form edit/design URL for regenerate/modify mode. Required for modify when schema_json is omitted."
      },
      "change_summary": {
        "type": "string",
        "description": "Short user-facing description of what changed or what was generated."
      },
      "catalog_fields_json": {
        "type": "string",
        "description": "Optional JSON array of explicitly requested SmartCMP standard catalog field insertions."
      },
      "value_expressions_json": {
        "type": "string",
        "description": "Optional deterministic compatibility helper for existing projection/composition workflows. Prefer explicit field-level JavaScript in schema_json for new SmartCMP form extensions. This is a JSON string containing an array of request objects; even one target field must be wrapped as a one-element array. Source values are read-only dependencies, not added form fields. Each request has fieldKey plus exactly one value shape: fields for flat key/value JSON with unique labels, or compose for the target output structure. Add valueType when the backend requires a specific submitted type: string, jsonString, object, or array. valueType=object/array writes the raw composed structure to model[fieldKey] while keeping the target schema field as an executable string widget; valueType=jsonString writes valid JSON text; string is for formatted text. For formatted string targets, compose must be a top-level $concat object such as {\"$concat\":[\"{key：\",{\"$field\":\"名称\"},\"}\"]}; do not model the final string as a plain object. Use plain object compose only when the target value should be object/array or JSON object text. In compose, plain object keys are output keys; source leaf marker objects must contain exactly one marker: field/$field/path/$path/$literal/$concat. Do not invent extra DSL keys. Do not use value_expressions_json as the default path when the user asked for custom JavaScript."
      },
      "requested_fields_json": {
        "type": "string",
        "description": "Optional JSON array of the exact top-level form field keys requested by the user, in requested order. Every item must be a non-empty string. Use this whenever the user enumerates the form fields or gives a field count, for any number of fields. Do not include source/dependency values used only by value_expressions_json. The design tool rejects missing requested fields."
      }
    },
    "required": ["mode"]
  }
---

# form-designer

Design, read, and normalize SmartCMP Angular form schema JSON only. It does not submit requests or save changes.

## Boundaries

- No submit/approve/status workflows.
- No CMP form writes: no POST, PUT, PATCH, DELETE, publish, save, or delete.
- Form URLs are read-only source material.

## Workflow

- New form: if the user gave enough fields, do not read CMP or call datasource tools. Build complete `schema_json`, then call `smartcmp_design_form_schema` with `mode=new`.
- Bare form edit/design URL: inspect only. Call `smartcmp_read_form_schema`; do not design.
- URL plus full field-set or schema-shape changes: treat this as new-form generation with one extra read step. First call `smartcmp_read_form_schema` to understand the current form, then generate a fresh complete replacement schema from the user's latest requirements and call design with `mode=regenerate`. Use the old schema only as context; do not patch, splice, or preserve existing fields/JavaScript unless the user explicitly asks to keep them.
- URL plus deterministic projection/composition changes: after the read step, call `smartcmp_design_form_schema` with `mode=modify`, `form_url`, and `value_expressions_json`. This lets the tool load the source schema and replace the target expression with the hardened runtime expression instead of asking the LLM to hand-copy the old schema or JavaScript.
- `mode=modify` is only for complete caller-provided JSON, deterministic `catalog_fields_json` insertion, or deterministic `value_expressions_json` updates into a supplied `schema_json` or `form_url` source. Never call `mode=modify` with only `mode` or only insertion/update JSON; that would create an incomplete replacement schema.
- If a read result warns that a field expression is not `function(model, sourceParams, schema, unused, cfg)`, do not answer by hand-writing a replacement `schema_json` with another legacy signature such as `function(formInRet, schemas, widget, injection)`. For catalog/model value rewrites, use `value_expressions_json`; for custom JavaScript, provide a complete modern-signature expression that writes `model[fieldKey]`.
- If read/design output reports `designMode`, `modelKeys`, or `componentCount`, tell the user the source form has visual-designer/model state that can preserve stale runtime values even when the schema expression changes. The generated schema is still a manual replacement draft; SmartCMP persistence and visual designer state must be reviewed in CMP.

## General JavaScript Form Extensions

Use this skill for general SmartCMP form JavaScript extension work. The scripts provide generic validation, normalize structure, preserve unknown keys, and warn about JavaScript risk; they must not perform business semantic inference from field labels, expression substrings, or familiar variable names.

Prefer explicit field-level JavaScript for dynamic behavior. When the user asks for computed values, visibility, linkage, validation, or catalog/model reads, generate the requested JavaScript directly under the relevant SmartCMP key, usually `config.value.expression` with `source: "mock"` and `method: "mock"` for computed values. The LLM owns the business meaning of the generated JavaScript; the script layer is not the source of business semantics.

Catalog context is reference/catalog metadata for generating JavaScript, not a fixed synchronization feature. catalog-provided context values are read-only inputs to the generated expression. Do not add projection source values as form fields unless the user explicitly asks to show or edit them. Do not rely on catalog_fields_json to satisfy catalog context needs; use it only when the user explicitly asks to insert or display a SmartCMP standard catalog field.

`value_expressions_json` is an optional compatibility helper for deterministic projection/composition cases that already fit its limited data shape. In plain terms, value_expressions_json is an optional compatibility helper, not the default design path. Do not use value_expressions_json as the default path for general SmartCMP JavaScript work, and do not force a custom JavaScript request into this helper. When using this helper, keep these contracts:

- `value_expressions_json` is always a JSON array string. For one computed target, pass a one-element array.
- A form field is a user-facing/request parameter in `schema.properties`. A source value used only to compute another field is not a form field.
- When the user enumerates fields or gives a field count, pass `requested_fields_json` with exactly those top-level form field keys, in order. Every item must be a non-empty string. This is for any number of fields; do not include source/dependency values used only by `value_expressions_json`. The design tool rejects missing requested fields.
- Exact field-set constraints can be expressed in any wording or language. Infer them from the user's intended scope, not by matching a fixed keyword list. When the user constrains the exact field set or field count, `schema.properties` and `fieldsets` contain exactly those requested form fields.
- `fieldKey` is always the exact requested target field. There is no default target.
- Use `valueType` when the backend requires the submitted parameter type: `string`, `jsonString`, `object`, or `array`. `object`/`array` submit raw structured `model[fieldKey]` values while the schema field stays a `type: "string"` / `widget.id: "string"` control so SmartCMP executes `config.value.expression`; `jsonString` submits valid JSON text; `string` submits formatted text. If omitted, the tool infers `object` or `array` from an existing target field schema type before falling back to `string`.
- Choose exactly one value shape per request: top-level `fields` for a flat object, or `compose` for the exact nested object/array/string structure the target field should receive. Never send both `fields` and `compose` for the same `fieldKey`.
- `fields` maps unique output labels to source reads and is only a shorthand for flat JSON such as `{"名称":"..."}`. Each item uses a `label` plus either `field` for a catalog alias or `path` for an exact model path. Do not repeat `label` to imply a parent key or group.
- `compose` is the target output structure itself. Plain object keys become literal output keys; source reads must be single-key leaf markers using `field`/`$field`, `path`/`$path`, `$literal`, or `$concat`.
- For any nested, grouped, array, or complex concatenation request, copy the requested output structure into `compose` before resolving source reads. Decompose complex output into leaf source reads, then combine those leaves with the surrounding JSON structure or `$concat`.
- When the final target value is a single formatted string, use one top-level `$concat` containing literal text and source marker leaves. Do not model that final string as a plain object unless the user explicitly asks for JSON object output.
- Do not invent helper metadata, placeholders, or alternate mini-languages inside `value_expressions_json`; if a key is not one of the supported source markers, the tool treats it as output data.
- Source reads use `field`/`$field` for known catalog aliases with fallback candidate paths, or `path`/`$path` for exact model paths with no parent-path fallback.
- Do not add source/dependency values as form fields unless the user explicitly asks to show or edit those values.
- Preserve requested visibility and titles. Value-expression target fields stay executable scalar controls; use `valueType` for the runtime submitted value type instead of turning the schema field into an object or array container. Do not default value-expression target fields to hidden, titleless, or non-editable.
- Return an empty string until at least one source value resolves.

Only these catalog aliases are supported: `name`/`名称`, `owners`/`所有者`, `projects`/`应用系统`, `businessGroup`/`业务组`.

For custom JavaScript, provide a complete function string under `config.value.expression` with `source: "mock"` and `method: "mock"`. The design tool rejects literal ellipsis placeholder JavaScript. Keep Chinese labels as literal UTF-8 text, not Unicode escape sequences.

## Common Widget Contracts

Use the SmartCMP widget shape, not generic web-control names:

- Text input: `type: "string"` with `widget.id: "string"`.
- Number input: `type: "number"` with `widget.id: "number"` and range validation when known.
- Checkbox: `type: "boolean"` with `widget.id: "checkbox"`.
- Select: `type: "string"`, `format: "uiselect"`, `widget.id: "select"`, and `default: null` when a placeholder should show.
- Multi-select: `type: "array"` or `type: "string"`, `format: "uiselect"`, `widget.id: "select"`, plus `selectMode: "multiple"`.
- Static options: use field-level `selectDatas` with display labels and stored values; do not hide option data inside `widget`.
- Tables: top-level table fields use `type: "array"` with `widget.id: "table-head"`; row schema lives under `items.properties`, and `items.fieldsets` lists row columns.
- User-facing text should prefer `i18nTitle`, `i18nPlaceholder`, and `i18nDescription` when Chinese/English rendering matters.
- Required fields use `required`/`isRequired`; keep `schema.required` consistent when the target renderer expects root required lists.
- Description-only Angular2 schemas still need non-empty `properties`; add a hidden placeholder property instead of returning a schema with only description text.

## Schema Rules

- Root: `type: object` with `properties` and `widget.id: "object"`.
- `properties` and `fieldsets` must match the requested form-field set; computed-value dependencies do not expand that set.
- When adding fields through `catalog_fields_json` or `value_expressions_json`, the generated target fields must also be present in root `fieldsets`.
- Top-level fields: stable `id`, numeric `index`, matching `type`, and `widget.id` (`string`, not `text`, for string inputs).
- Include `config.visibility.allowInRequest` and `allowInApproval` unless the user supplied different visibility.
- Preserve unknown keys, `hidden`, `condition`, `fieldsets`, `selectDatas`, `value`, and `items`.

## Output

Return the exact normalized schema text from `smartcmp_design_form_schema` as a fenced `json` block. All string values inside the returned JSON are opaque. Do not add, remove, rename, move, summarize, or abbreviate any property or string value. Do not summarize, abbreviate, reorder, rename, or replace long JavaScript strings with `...`.

For URL-based regenerate or modify work, state that the result is a replacement schema for manual review and copying. Do not imply that the tool saved, updated, or published the CMP form.
