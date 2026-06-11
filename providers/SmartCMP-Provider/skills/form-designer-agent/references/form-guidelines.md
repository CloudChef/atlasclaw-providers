# Schema Form Guidelines

These notes are condensed from the single Confluence page
`/pages/viewpage.action?pageId=123109820` ("Schema Form manual"). Use this
page as the source reference and do not crawl child pages or older page trees
when generating ordinary form JSON.

## Purpose

The form-designer agent returns SmartCMP Schema Form JSON for review. It does
not submit requests, save form entities, mount forms, publish catalogs, or run
approval/request workflow tools.

Supported modes:
- New form: generate JSON from the user's requirements.
- Existing form URL: call `smartcmp_fetch_request_form_source`; for
  service-model edit/design paste, output `content.schema` as schema-only root
  JSON and modify only the requested parts.
- Existing pasted JSON: preserve the shape and modify only the requested
  parts.
Return the complete generated JSON as chat text in one fenced `json` code block,
and the fenced JSON block must contain the bare JSON value itself. Do not wrap schema-only output in
`designerPasteJson`, `content`, `metadata`, or another outer object unless the
user explicitly asks for a diagnostic envelope. Do not create, write, attach,
or mention a `.json` file. Do not use workspace artifacts or download links.
Never return a local path, truncated JSON with a file reference, or
instructions to open a generated file. Never say the file has been written to
the workspace. Output to chat only.

## Shape

Identify the target module shape before generating JSON. Preserve the target
module shape when a source form is supplied. Do not force every form into
model/schema/options.

Common shapes:
- `schema_only` / Angular2 schema: root `type`, `properties`, `required`,
  `fieldsets` or `columnsets`, and `widget`.
- `smartcmp_content`: `model`, `schema`, optional `options`.
- Angular1 schema form: `schema`, `form`, optional `model` and `i18n`.
- Form.io visual designer: `components`.

For new visual-designer expert mode or previewable forms, prefer schema-only
JSON. Root `widget.id` must be `object`. Add hidden `schemaFormValid` under
`properties` and include it in `fieldsets`:

For service-model edit/design paste, output schema-only root JSON (`type`,
`properties`, `required`, `fieldsets`, `widget`); do not wrap it in outer
`model`, `schema`, `options`, `content`, or `designerPasteJson`.

```json
{
  "hidden": true,
  "type": "boolean",
  "default": true,
  "condition": "1 === 2",
  "widget": { "id": "hidden" }
}
```

Field definitions belong in `properties.<fieldKey>` for schema-only output and
in `schema.properties.<fieldKey>` for `model/schema/options` output. Do not put
field definitions under `options.fields`; `options` carries external context
such as `sourceConfigParamter`, not widget configuration.

## Field Keys

Use stable backend parameter or extension-attribute keys. Labels, titles, and
translations are display text, not parameter identity.

Each visible schema-only field should include:

- `id`
- `type`
- `widget.id`
- `inputClass`
- `index`
- `title`
- `config.visibility.allowInRequest`
- `config.modification.allowInRequest`

Use zero-based sequential `index` values for visible fields. Do not put
`index` on `schemaFormValid`.

## Layout

Use `fieldsets` for grouped form sections. Use `columnsets` when the target
ng2 renderer expects column layout. Every referenced field key must exist in
`properties`.

## Widgets

Choose the simplest widget matching the backend value type:

- `string`, `textarea`, `password`, `richtext`, `text`, `description`
- `number`
- `checkbox`, `checkboxes`, `radios`
- `select`, `tree-select`, `cascade`
- `datetime`
- `upload`
- `table-like`, `table-async`, `tab-table`, `tab-set`
- `calculate`

Use `widget.id`; do not use `widget.type`, `templateOptions`, `formlyConfig`,
or `widget.formlyConfig` in schema-only expert-mode JSON.

Editable string request inputs should use `widget.id: "string"`. Do not use
`widget.id: "text"` for editable request input fields unless an existing
source form already uses it successfully for that renderer; in schema-only
designer JSON it can render as display text or fail to provide an editable
control.

## Data Sources

Option and value sources belong under `config.value`.

Supported source modes include API, model, static, and mock data. API sources
usually need `method`, `expression`, `body` when posting, result path such as
`resultPath` or `selectDatasPath`, and label/value mappings.

Use `${field}` for external `sourceConfigParamter` values and `{$.field}` for
current model values where the renderer supports expression replacement. Do
not place `${field}` or `{$.field}` in `default` or `defaultValue` for dynamic
submitted values; defaults are literal initialization values.

## Dynamic Values

Use dynamic runtime logic only when the user asks for a runtime context value
or a composed value. User-entered fields do not need dynamic lookup.

Successful existing form scripts use field-level SmartCMP hooks, not a
separate computed-field DSL. Put `config.changeEvent` under
`properties.<fieldKey>.config.changeEvent` for schema-only output, or under `schema.properties.<fieldKey>.config.changeEvent` for complete model/schema/options output. `config.value.customFunction` is also valid when
the field's value source runs it. For automatic service-catalog context sync, use a rendered backend field with `config.value.source: mock`, `method: mock`, and one-line `config.value.expression`; generators hide composed backend fields off-screen by default while preserving submission. Do not put dynamic logic in root-level changeEvent; do not put field definitions under `options.fields`.
For `config.value.expression` mock watcher, use `function(model, sourceParams, schema, ...)`; do not use the changeEvent signature there.

A change event string uses the parameter order
`function(itemId, schema, model, sourceParams)`. Short aliases such as
`function(v,s,m,p)` are acceptable only when the position is preserved. The
third argument is the submitted model, and the fourth argument is sourceParams.
The script must assign the submitted backend key, for example
`model[backendKey] = value`, and should return the computed value when the
renderer expects a return value.
If the backend value is composed from multiple fields, the assigned value must
be a JSON object string created with `JSON.stringify`, not display text.
customFunction must also assign `model[backendKey] = value`; do not generate
`model.name || ''` or `model.owner || ''` as shortcuts for service-catalog
fields, and do not generate direct-only `sourceParams.name` or
`sourceParams.owner` reads. Fields such as department, project, owner, and name
are normal requested fields unless the user says they come from a service
catalog; in that case resolve them from the specified catalog detail first.
Do not compose empty catalog context templates; use a non-empty unresolved marker instead.

Working runtime patterns are derived from successful forms, not hardcoded URLs
or UUIDs:

- Rendered backend field plus visible trigger field: the trigger owns
  `config.changeEvent`, assigns `model.<backendKey>`, and returns the value.
- Rendered backend field with field-level changeEvent: the backend field owns
  the hook, assigns its model key, and returns the value.
- Rendered backend field with config.value mock expression watcher: the field owns `config.value.source: mock`, `method: mock`, and `config.value.expression`; the expression starts one timer, assigns its model key, dispatches `input`/`change`, and returns the current value. Generated composed backend fields are hidden off-screen by default but still rendered/submitted. Their current value must be a JSON object string created with `JSON.stringify`, not display text.

Hidden computed target plus customFunction is forbidden. Do not put `config.value.customFunction` on hidden computed fields; hidden controls may not render or execute the value function reliably. Generated composed backend fields are hidden-submit by default; never use `hidden`, `widget.id: hidden`, `condition: 1 === 2`, `display:none`, `hidden`, or `d-none` on that business field because they can remove the input/ngModel submit path.

Keep JavaScript hook strings on one physical line so the surrounding JSON can
be parsed and pasted by the designer. Do not put runtime values in
`default`/`defaultValue`; defaults are literal initialization values. Do not
output pseudo fields or pseudo expressions such as `computed_values`, root-level `expression`, `concat(...)`, `context.project`, or `context.owner` as if they were SmartCMP runtime features.

Generated form JavaScript cannot call Atlas agent tools or `list_services` at
request-page runtime. Runtime JavaScript may read only hook arguments,
`sourceParams`, schema/source context, current model values,
browser-accessible SmartCMP APIs, and explicit DOM fallbacks. The known
no-manual-refresh hook is the field value mock expression on a visible backend
field. Other hooks still need an actual editable trigger field or known source
evidence.

For refresh behavior, remember that changeEvent runs only when its owning field changes, and the owning field must allow request modification. Do not
rely on submit to refresh computed values. If a value should be recomputed on demand, provide a visible editable trigger field. When no user-entered refresh field is wanted for service-catalog context, use a rendered backend field with a mock expression watcher and default `AUTO_SYNC_PENDING`; generated composed backend fields are hidden off-screen by default while still submitting. Generate from the requested backend key and catalog-resolved field list; do not hard-code example keys, labels, or field combinations. Composed backend values must be JSON.stringify object strings, not `{label:value}` display text. Retain the last non-empty value for each catalog field; guard `model[backendKey]` with `Object.defineProperty` so empty renderer writes are ignored; never overwrite a correct computed value with empty or unresolved context. Missing watcher is invalid; return the computed value instead of literal `AUTO_SYNC_PENDING`. Clear the previous interval before starting a new one, assign the model key, write the DOM input, call Angular ngModel `$setViewValue`/`$render`/`$applyAsync` when available, return the computed value, and dispatch `input` and `change` events on the target input so the rendered control and submitted model stay in sync.
Do not set fields that own dynamic hooks to `readOnly`, `readonly`, or
`config.modification.allowInRequest: false`; that prevents reliable change
events and request-time synchronization.

Do not use hidden fields as refresh trigger fields. Hidden fields cannot be
changed by the requester, so their `changeEvent` will not provide a manual
refresh path.
Use `config.value.customFunction` only when an existing source proves the
renderer executes it; do not add `_trigger_*` fields solely for refresh.

## Catalog Context

Do not special-case department, project, owner, or name. If a value should read
one of these fields from a service catalog, ask the user for the specific
service catalog name or URL, then read the catalog detail and resolve the exact
field key. If the user asks for these names as normal user-entered fields,
generate ordinary visible input fields from the requested form requirements.

User-filled fields do not need a service catalog name or URL. Examples
include CPU core count, IP address, environment text, tags, or other values the
applicant will type into the form. Use catalog lookup only when a field must be
dynamic from service catalog context.
For named service catalogs, first scan Request Parameter Instructions or catalog payload fields and run `smartcmp_form_designer_resolve_catalog_fields` with the user's requested output labels to map requested labels to exact keys and resolve requested labels to label=key pairs before generating dynamic JSON. Preserve English labels from the user's phrase or template; translate non-English common labels to concise English labels such as `business group`, `owner`, `compute specification`, `billing type`, or `bandwidth` instead of emitting non-ASCII labels or escaped characters. Do not replace requested labels with resolved backend keys. Do not guess keys from display labels; use only exact key/label/evidence matches from catalog detail. If the requested form has only one field or the user provides a template like `{A:A value,B:B value}`, resolved catalog keys are runtime sources only and must not become visible form fields. After resolver success, call `smartcmp_generate_catalog_context_form` immediately with `label=key` pairs and a hidden-submitted mock expression watcher; do not ask whether the composed field should be visible. Its submitted backend value is a JSON object string, not `{label:value}` display text. If the same form also has user-entered custom fields such as priority, show only those custom fields.

When the user provides a service catalog URL with a UUID, call
`smartcmp_form_designer_get_catalog_detail` and read exact Request Parameter
Instructions or `catalogPayloadFields` before mapping keys. When the user
provides only a catalog name, call `smartcmp_form_designer_list_services` first
and disambiguate if needed.

Do not call `smartcmp_prepare_request_form` repeatedly to discover catalog
fields. Do not ask the user for internal field keys when read-only catalog
tools can inspect them. Ask the user for the service catalog only when the
request requires a service-catalog field and no catalog name or URL was
provided. If prepare metadata returns `catalogLookupGate`, stop JSON generation
and resolve the catalog/detail key mapping first.

## JSON Validation

Validate the final JSON with `JSON.parse`, compile every generated function string with `new Function`, and ensure every try block must have `catch` or `finally` before returning it. The JSON must be
syntax-valid and must keep field parameters in the supported locations:
`properties.<fieldKey>` for schema-only output and
`schema.properties.<fieldKey>` for content or complete configurations.
Run `smartcmp_validate_request_form_json` before returning generated JSON; fix
any reported hidden dynamic fields, missing returns, model common-field reads,
direct-only local-name reads such as `sourceParams.name`/`sourceParams.owner`,
or empty catalog context templates.

## Review Checklist

- Target shape is identified and preserved.
- Backend keys are consistent in `model`, `schema.properties`,
  `properties`, `form[].key`, or `components[].key` as required by shape.
- Required fields, validation messages, defaults, visibility, and modification
  flags match the request.
- Data sources include source, method, expression, result path, label, and
  value mapping when needed.
- Dynamic submitted values use a runtime function that assigns the model key.
- Final JSON parses with `JSON.parse`.
- Secrets are masked in examples and summaries.
- The skill does not save, mount, publish, or submit anything in CMP.
