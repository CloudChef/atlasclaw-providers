---
name: form-designer-agent
description: "Use when a SmartCMP user needs generate form, form generation, request form generation, or create, rewrite, review, or modify Schema Form JSON for request extension attributes, component creation, Day2 parameter display, platform object extension attributes, or visual form-designer output."
provider_type: "smartcmp"
instance_required: "true"
tool_prepare_name: "smartcmp_prepare_request_form"
tool_prepare_description: "Prepare read-only metadata for generating SmartCMP Schema Form JSON from form module requirements. Never submits, saves, mounts, or calls request workflow tools."
tool_prepare_entrypoint: "scripts/prepare_request_form.py"
tool_prepare_groups:
  - cmp
  - form
  - designer
tool_prepare_capability_class: "provider:smartcmp"
tool_prepare_priority: 159
tool_prepare_result_mode: "llm"
tool_prepare_cli_positional:
  - instruction
tool_prepare_parameters: |
  {
    "type": "object",
    "properties": {
      "instruction": {
        "type": "string",
        "description": "Natural-language SmartCMP form module requirements. Do not pass a submitted request URL here."
      }
    },
    "required": ["instruction"]
  }
tool_catalog_context_name: "smartcmp_generate_catalog_context_form"
tool_catalog_context_description: "Generate canonical schema-only JSON for a hidden-submitted backend field composed from catalog-specific request fields after exact keys have been scanned. The submitted backend value is a JSON object string. Read-only."
tool_catalog_context_entrypoint: "scripts/generate_catalog_context_form.py"
tool_catalog_context_groups: [cmp, form, designer]
tool_catalog_context_capability_class: "provider:smartcmp"
tool_catalog_context_priority: 161
tool_catalog_context_result_mode: "llm"
tool_catalog_context_cli_positional: [backend_key, title, fields, fieldset_title, hide_submit_field]
tool_catalog_context_parameters: |
  {"type":"object","properties":{"backend_key":{"type":"string"},"title":{"type":"string"},"fields":{"type":"string","description":"Comma-separated label=key pairs from scanned catalog instructions. Left side is the user's output label in the user's language; right side is the resolved backend key from catalog evidence. Preserve the user's labels; never pass key=key for translated labels."},"fieldset_title":{"type":"string"},"hide_submit_field":{"type":"boolean","description":"Defaults true; keep true unless the user explicitly asks to show the composed backend key/value."},"allow_backend_labels":{"type":"boolean","description":"Default false. Use true only when the user explicitly wants JSON labels identical to backend keys."}},"required":["backend_key","title","fields"]}
tool_catalog_field_resolver_name: "smartcmp_form_designer_resolve_catalog_fields"
tool_catalog_field_resolver_description: "Resolve requested catalog field labels to exact label=key pairs from one smartcmp_form_designer_get_catalog_detail result. Read-only; never submits a request."
tool_catalog_field_resolver_entrypoint: "scripts/resolve_catalog_fields.py"
tool_catalog_field_resolver_groups: [cmp, form, designer]
tool_catalog_field_resolver_capability_class: "provider:smartcmp"
tool_catalog_field_resolver_priority: 162
tool_catalog_field_resolver_result_mode: "llm"
tool_catalog_field_resolver_cli_positional: [catalog_detail_json, labels]
tool_catalog_field_resolver_parameters: |
  {"type":"object","properties":{"catalog_detail_json":{"type":"string","description":"JSON detail metadata returned by smartcmp_form_designer_get_catalog_detail."},"labels":{"type":"string","description":"Comma-separated exact user output labels to resolve from the user's phrase or template. Do not replace requested labels with resolved backend keys before calling this tool."}},"required":["catalog_detail_json","labels"]}
tool_fetch_name: "smartcmp_fetch_request_form_source"
tool_fetch_description: "Recognize a same-host SmartCMP service-model form URL as source context for Schema Form JSON generation. Read-only; never saves, mounts, publishes, or submits."
tool_fetch_entrypoint: "scripts/fetch_request_form_source.py"
tool_fetch_groups: [cmp, form, designer]
tool_fetch_capability_class: "provider:smartcmp"
tool_fetch_priority: 158
tool_fetch_result_mode: "llm"
tool_fetch_cli_positional: [source_request_url]
tool_fetch_parameters: |
  {
    "type": "object",
    "properties": {
      "source_request_url": {
        "type": "string",
        "description": "Same-host SmartCMP service-model form list, design, or edit URL used as source context for Schema Form JSON generation."
      }
    },
    "required": ["source_request_url"]
  }
tool_validate_name: "smartcmp_validate_request_form_json"
tool_validate_description: "Validate generated Schema Form JSON for renderability and known dynamic-field failure modes. Read-only; never saves or submits."
tool_validate_entrypoint: "scripts/validate_request_form_json.py"
tool_validate_groups: [cmp, form, designer]
tool_validate_capability_class: "provider:smartcmp"
tool_validate_priority: 155
tool_validate_result_mode: "llm"
tool_validate_cli_positional: [form_json]
tool_validate_parameters: |
  {"type":"object","properties":{"form_json":{"type":"string","description":"Generated SmartCMP Schema Form JSON text to validate before returning it."}},"required": ["form_json"]}
tool_catalogs_name: "smartcmp_form_designer_list_services"
tool_catalogs_description: "List published SmartCMP service catalogs for the form designer and expose generated Markdown Request Parameter Instructions for catalog field mapping. Read-only; never submits a request."
tool_catalogs_entrypoint: "../datasource/scripts/list_services.py"
tool_catalogs_groups: [cmp, form, designer, datasource]
tool_catalogs_capability_class: "provider:smartcmp"
tool_catalogs_priority: 157
tool_catalogs_result_mode: "llm"
tool_catalogs_cli_positional: [keyword]
tool_catalogs_parameters: |
  {
    "type": "object",
    "properties": {
      "keyword": {
        "type": "string",
        "description": "Optional service catalog name keyword. Use the catalog name when available; omit or pass an empty string when resolving by catalog UUID from a URL."
      }
    }
  }
tool_catalog_detail_name: "smartcmp_form_designer_get_catalog_detail"
tool_catalog_detail_description: "Fetch one SmartCMP service catalog by catalog UUID and expose exact Request Parameter Instructions, catalog payload fields, and field keys for form designer mapping. Read-only; never submits a request."
tool_catalog_detail_entrypoint: "../shared/scripts/get_catalog_detail.py"
tool_catalog_detail_groups: [cmp, form, designer, datasource]
tool_catalog_detail_capability_class: "provider:smartcmp"
tool_catalog_detail_priority: 156
tool_catalog_detail_result_mode: "llm"
tool_catalog_detail_cli_positional: [catalog_id]
tool_catalog_detail_parameters: |
  {
    "type": "object",
    "properties": {
      "catalog_id": {
        "type": "string",
        "description": "UUID of the SmartCMP service catalog to inspect exactly. Extract it from service catalog request URLs when present."
      }
    },
    "required": ["catalog_id"]
  }
triggers:
  - schema form
  - service catalog form
  - service-model form
  - catalog parameter form
  - request extension attributes
  - component creation form
  - day2 form
  - platform object extension attributes
  - visual form designer
  - backend parameters
  - form designer
  - agent form designer
  - service catalog URL
  - service catalog name
  - composed backend fields
  - dynamic catalog context
  - processForm payload
  - changeEvent script
use_when:
  - User wants a SmartCMP form created from extension attribute, component, Day2, lifecycle, or object-attribute requirements
  - User wants a SmartCMP Schema Form modified or rewritten
  - User provides a same-host SmartCMP service-model form list, design, or edit URL as source context
  - User provides a service catalog URL or service catalog name and wants catalog context fields used in generated form parameters
  - User pastes existing SmartCMP form JSON for review or modification
  - agent_identity is agent-form-designer
avoid_when:
  - User wants to submit a service request immediately
  - User wants request status, approval, rejection, or provisioning
  - User only wants to browse catalogs, resources, resource pools, or reference data
  - User wants multi-resource decomposition before parameter collection
  - User wants a generic HTML form, YAML file, or Form.io component definition

---

# Form Designer Agent

Design SmartCMP Schema Form JSON for review or designer paste only. This is
not a service request, approval, or provisioning action.
The final deliverable is always the complete JSON text in the chat interface,
inside one fenced `json` block. Never create a local `.json` file, workspace
artifact, attachment, or download link as the answer, even when the JSON is
long.

Use the single Schema Form manual page
`/pages/viewpage.action?pageId=123109820` through the compact local reference.
Read `references/form-guidelines.md` first; read
`references/form-module-shapes.md` only when preserving a source or target
shape. Do not crawl child pages or older page trees for ordinary form
generation.

## Workflow

1. Identify the target form module and preserve its shape; do not force every
   form into model/schema/options.
2. For a same-host SmartCMP service-model form URL, call `smartcmp_fetch_request_form_source`; for edit/design paste, output schema-only root JSON, not outer `model/schema`.
3. For a new visual-designer or expert-mode form, call
   `smartcmp_prepare_request_form` and output schema-only JSON.
4. For service-catalog dynamic fields, call catalog tools before
    `smartcmp_prepare_request_form`; run `smartcmp_form_designer_resolve_catalog_fields`
    with the user's exact output labels to resolve label=key pairs, then call
    `smartcmp_generate_catalog_context_form`; it writes a JSON.stringify object string to a hidden-submitted backend field and does not create visible source fields. Do not guess keys from display labels or call
   `smartcmp_prepare_request_form` repeatedly to discover catalog fields.
   If `smartcmp_prepare_request_form` returns `catalogLookupGate`, stop JSON
   generation and follow that gate first.
5. For a service catalog URL with a UUID, call `smartcmp_form_designer_get_catalog_detail`; use Request Parameter Instructions when present. When they are missing, use `catalogPayloadFields`/`catalogFieldKeys.payloadFields` from the detail result before asking or guessing.
## Key Rules

Do not special-case department, project, owner, or name. If the user says a
form field should be read from a service catalog, the user must provide the
specific service catalog by name or URL first; then use catalog list/detail
tools and `smartcmp_form_designer_resolve_catalog_fields` to find exact keys
from Request Parameter Instructions or catalog payload fields. If the user only
asks for ordinary user-entered fields named department, project, owner, or name,
generate normal visible input fields from the user's requirements.
Generated composed backend fields are hidden from the requester but still submitted by default. Do not set those business fields to `hidden`, `widget.id: hidden`, `condition: 1 === 2`, `display:none`, `hidden`, or `d-none`; those can remove the rendered input/ngModel path and the backend may not receive the value. The generators use an off-screen runtime hide that keeps the input/model submission path alive. Show the composed key/value only if the user explicitly asks for it.
User-filled fields do not need a service catalog name or URL. Ask for a
service catalog only when a field must be dynamic from service catalog context.
For any named service catalog, first run catalog lookup/detail and `smartcmp_form_designer_resolve_catalog_fields` to map requested labels to exact keys from Request Parameter Instructions or catalog payload fields before generating JSON. Preserve English output labels from phrases/templates; when the user uses non-English common labels, translate them to concise English labels such as `business group`, `owner`, `compute specification`, `billing type`, or `bandwidth` instead of emitting non-ASCII labels or escaped characters. Do not replace requested labels with resolved backend keys. After resolver success, call `smartcmp_generate_catalog_context_form` immediately; do not ask whether the composed field should be visible. Then use `smartcmp_generate_catalog_context_form`, never guessed display labels alone; its composed backend value must be a hidden-submitted JSON object string, not `{label:value}` display text. If the user asks for one field or provides a template such as `{A:A value,B:B value}`, generate only that hidden composed backend field; resolved catalog keys are sources, not extra visible inputs. If the form also has user-entered custom fields such as priority, keep only those custom fields visible.
For new previewable forms, output schema-only JSON with root `type`,
`properties`, `required`, `fieldsets`, and `widget.id: "object"`. Field config
belongs under `properties.<fieldKey>`, not `options.fields`. Include hidden
`schemaFormValid`; visible fields need id/type/widget/inputClass/index/title,
request visibility, and request modification.
Editable string inputs should use `widget.id: "string"`, not
`widget.id: "text"`, unless a fetched source already uses `text` successfully.
Dynamic runtime values need field-level hooks such as `config.changeEvent`
with signature `function(itemId, schema, model, sourceParams)`, positional
arguments, one-line strings, and direct model assignment.
Any composed backend value must be a JSON.stringify object string, including
hand-written `changeEvent` or `customFunction`; never return `{label:value}`
display text.
For `config.value.expression` mock watcher, use `function(model, sourceParams, schema, ...)`; do not use the changeEvent signature there.
JavaScript cannot call Atlas agent tools at request-page runtime. Runtime
patterns derived from successful forms are: rendered backend field plus visible
trigger field, rendered backend field with field-level changeEvent, or rendered backend field with config.value mock expression watcher. The generators may hide the rendered composed field off-screen while keeping submission alive. Hidden computed target plus customFunction is forbidden.
customFunction must also assign `model[backendKey] = value`; do not infer
service-catalog field keys from local names such as `name` or `owner`.
`changeEvent` runs only when its owning field changes, and that field must
allow request modification; provide a visible non-common editable trigger
field for refresh, return the computed value, and dispatch `input`/`change`
when updating a different visible field.
Use `config.value.customFunction` only when an existing source proves the renderer executes it; do not add `_trigger_*` fields solely for refresh. Do not put
`config.value.customFunction` on hidden computed fields or set dynamic hook fields to readOnly/`allowInRequest: false`.
Do not use hidden fields as refresh trigger fields because hidden fields
cannot be changed by the requester.

Validate the final JSON with `JSON.parse`, compile every generated function string with `new Function`, ensure every try block must have `catch` or `finally`, and run `smartcmp_validate_request_form_json` before returning. Do not hardcode successful form URLs or UUIDs; extract reusable rules into `references/form-guidelines.md`.

Return the generated JSON as chat text in one fenced `json` code block. The block must contain the complete paste JSON itself; do not return a path, summary, truncated JSON, or instructions to open a local file. Do not wrap schema-only output in `designerPasteJson`. Do not create, write, attach, or mention a `.json` file; do not use workspace artifacts or download links; never say the file has been written to the workspace. Do not save, mount, publish, or submit anything in CMP.
