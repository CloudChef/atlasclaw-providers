# SmartCMP Form Designer Workflow

This skill produces SmartCMP Angular form schema JSON only. It is deliberately separate from the SmartCMP request workflow: no service request payloads are created, no forms are saved to CMP, and no request submission tools are called.

## Existing Form URLs

Accept only current-instance SmartCMP UI edit/design URLs in these shapes:

```text
https://cmp.example/#/main/service-model/forms/edit/<uuid>
https://cmp.example/#/main/service-model/forms/design/<uuid>
```

The UUID maps to the read-only platform API:

```text
GET /platform-api/forms/<uuid>
```

The source schema is read from `content.schema`. The reader also exposes `content.model`, `content.designMode`, and component counts as diagnostics because visual-designer state and stale model values can explain why a schema-only JavaScript edit appears ineffective after the form is mounted to a service catalog. These fields are source context only and must not be written back by this skill.

When the user asks to change a form from a URL, start with a read step. If the requested change alters the field set, field schema shape, layout, visibility, or custom JavaScript behavior, use the source schema only to understand the existing form and the user's reference point, then generate a fresh complete replacement schema with `design_form.py --mode regenerate` from the user's latest requirements. Do not splice partial changes into the old JSON, do not preserve old fields or JavaScript by default, and do not ask the LLM to hand-copy a long existing schema.

If the requested URL-based change is a deterministic projection/composition update, such as filling one target field from service-catalog values, call `design_form.py --mode modify --form-url <url> --value-expressions-json <array-json>`. The tool loads the source schema, replaces the target expression, and emits warnings when the source form includes visual-designer components or stale `content.model` keys.

`design_form.py --mode modify` requires either complete `schema_json` or a source `form_url`. Do not call modify mode with only insertion/update JSON; an insertion without a source schema is not a complete form replacement.

When the source form already has legacy JavaScript warnings, URL-based changes must not copy or regenerate another legacy expression such as `function(formInRet, schemas, widget, injection) { return ... }`. SmartCMP request pages submit `model`, so generated catalog/model value expressions must use `function(model, sourceParams, schema, unused, cfg)` and write the target `model[fieldKey]`. For deterministic value rewrites, prefer `value_expressions_json` so the script generates that runtime-safe expression.

## Output

User-visible output should contain:

1. A short change summary.
2. The final normalized `schema` JSON. For URL-based changes, describe it as a replacement schema for manual review and copying.

Scripts may also emit machine-readable metadata blocks for warnings, assumptions, and source form identifiers. Agents should not expose internal metadata unless it helps the user resolve a form design issue.

## Normalization Scope

The normalizer may repair deterministic SmartCMP schema structure for new, regenerated, or deterministic modify-mode schemas:

- root `type: object`
- root `properties`
- root `widget.id`
- top-level field `id`
- top-level field `index`
- field `type`
- field `widget.id`
- top-level `config.visibility.allowInRequest`
- top-level `config.visibility.allowInApproval`
- table-array `items.properties`, `items.fieldsets`, and table widgets
- hidden SmartCMP `schemaFormValid` technical control in root `properties` and `fieldsets`
- root fieldset id `fieldset-default` and catalog-request-compatible business field ordering/indexes

The normalizer must preserve unknown keys and user-provided JavaScript expressions. It must not invent business fields, infer catalog request semantics from expression substrings, auto-hide matched fields, add companion submit fields, create request payloads, or perform CMP persistence behavior. `schemaFormValid` is a hidden SmartCMP technical control, not a user-requested business field.

## JavaScript Form Extensions

When a user asks for dynamic form behavior, generate the field-level JavaScript from that request and put it under `config.value.expression` or the appropriate SmartCMP config key. The script layer should only validate syntax, normalize deterministic schema structure, preserve unknown keys, and warn about generic risky JavaScript patterns. The script layer is not the source of business semantics, and it should not rewrite expressions based on business labels, expression substrings, or familiar helper variable names.

`value_expressions_json` remains available as a deterministic compatibility helper for existing projection/composition workflows. Do not use it as the default path for general JavaScript extension work, and do not translate custom JavaScript requirements into this helper unless the requested output exactly fits its limited data shape.

## Common Widget Contracts

- Selects use `type: "string"`, `format: "uiselect"`, `widget.id: "select"`, and `default: null` when the placeholder should render.
- Multi-selects use `widget.id: "select"` plus `selectMode: "multiple"` with `type: "array"` or `type: "string"` depending on the backend value.
- Tables use `type: "array"` with `widget.id: "table-head"` and row columns under `items.properties` plus `items.fieldsets`.
- User-facing titles, placeholders, and descriptions should use `i18nTitle`, `i18nPlaceholder`, and `i18nDescription` when bilingual rendering matters.
- Required fields use `required`/`isRequired`; keep root `schema.required` aligned when the target renderer uses root required lists.
- Description-only Angular2 schemas still need a hidden placeholder property.

## Catalog Standard Fields

Standard service-catalog fields are catalog context, not universal form requirements. They are reference/catalog metadata for explicit field generation or JavaScript expressions, not an implicit auto-sync mechanism. Add them only when the user asks for that context.

| User wording | Schema field | Source meaning |
| --- | --- | --- |
| business group / 业务组 | `businessGroup` | verified request UI key |
| application / app / project / 应用系统 | `projects` | verified request UI key |
| owner / 所有者 | `owners` | verified request UI key |
| name / 名称 | `name` | verified request UI key |

When a supported catalog context field is explicitly requested as a visible or hidden form field, `catalog_fields_json` can insert it and omit duplicate hand-written fields from `schema_json`. Do not rely on `catalog_fields_json` to satisfy catalog context needs for JavaScript; service-catalog fields are reference metadata unless the user asks to insert/display them. JavaScript that depends on standard service-catalog values must be generated through `value_expressions_json` with catalog aliases, not by hand-writing direct `sourceParams` keys or label guesses. `value_expressions_json` can still be used for deterministic compatibility cases unless the user explicitly provided complete custom JavaScript that reads verified paths. The generator resolves both field ids such as `projects` and display names such as `Projects`. A custom `fieldKey` on a catalog insertion is preserved, but the tool should warn because CMP backend standard-field handling may not recognize custom keys. User-defined fields belong in `schema_json` and can use their own field keys normally.

If the user asks to read a catalog value and fill another field, generate that target field and pass the corresponding `value_expressions_json` request. For URL-based deterministic projection/composition changes, read the source and use `mode=modify` with `form_url` plus `value_expressions_json`; for broader schema changes, use `mode=regenerate` with a complete replacement schema plus `value_expressions_json`. The generated expression must update the target `model[fieldKey]` as well as return the computed value after source values resolve, and return an empty string until at least one source value resolves; otherwise CMP may submit a stale value or valid-looking empty JSON from the form model. Value-expression target fields must remain executable scalar controls and listed in root `fieldsets`; use `valueType` for raw object/array submitted values instead of changing the schema field into an object/array container. Do not default them to hidden, titleless, or non-editable; pass `hidden` only when the user explicitly asks for a visibility change. Use `field`/`$field` for known catalog aliases with fallback candidate paths. Use `path`/`$path` only for exact model paths, and keep source marker objects to a single marker key.

Do not guess unverified runtime containers or treat display labels as current-form model keys for service-catalog context. Those guesses can produce empty submitted values on service-catalog request pages. Use the catalog aliases in `value_expressions_json` so the generated expression reads verified catalog context paths and writes the requested target field.

When the target field should contain one formatted string with surrounding literal punctuation or labels, build `compose` as one top-level `$concat` with literal text and source marker leaves. Do not model that final string as an object unless the user asks for JSON object output.

When the backend requires a typed submitted value, set `valueType` on the value-expression request. Use `object` or `array` for raw structured `model[fieldKey]` values, `jsonString` for valid serialized JSON text, and `string` for human-formatted text. The schema field still stays `type: "string"` with `widget.id: "string"` so the renderer calls the value expression.

Final answers must copy the complete schema returned by the design tool as immutable JSON. Treat every returned string as opaque; do not summarize, abbreviate, rewrite, move, add, or remove returned properties or values.
