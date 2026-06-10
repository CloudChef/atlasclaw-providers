# SmartCMP Form Module Shapes

The Schema Form manual at `pageId=123109820` describes SmartCMP forms as a
family of JSON modules. The form-designer agent must identify the target
module first, then preserve that module's shape.

## Usage Scenarios

- Request extension attributes.
- Component creation parameters.
- Day2 operation parameters and display fields.
- Platform object extension attributes.
- Lifecycle forms.
- Visual form-designer output.

## Shape Selection

| Shape | Use When | Root Keys |
|-------|----------|-----------|
| `smartcmp_content` | Source or target already uses SmartCMP content | `model`, `schema`, optional `options` |
| `schema_only` / `angular2_schema` | Angular2 or expert-mode designer wants schema directly | `type`, `properties`, `required`, `fieldsets` or `columnsets`, `widget` |
| `angular1_schema_form_model` | Legacy AngularJS schema form | `schema`, `form`, optional `model`, `i18n` |
| `formio_components` | Visual designer component JSON is being edited | `components` |
| `day2_content` | Day2 operation uses current resource values | usually `model` plus `schema`, sometimes schema-only |

Do not force every module into `model/schema/options`. That shape is common,
but Angular2 examples may be schema-only, Angular1 needs `form`, and visual
designer internals may use Form.io `components`.

## Cross-Shape Field Rules

- Stable field ids/keys are backend parameter or extension-attribute names.
- Display labels and translations are not parameter identity.
- Angular2/ngx-schema-form requires `properties`; description-only forms need
  a hidden placeholder property such as `schemaFormValid`.
- Angular1 form arrays use `form[].key` to reference `schema.properties`.
- Required fields may use root `required` or field-level `required` /
  `isRequired`; preserve the source runtime's style.
- `defaultValue` takes priority over `default` when both exist.
- For Day2 echo fields, prefer current resource values over stale defaults.

## Output Contract

Return the selected shape as chat JSON text. The optional full entity may be
summarized separately for review, but it is not the universal paste target.

Also summarize parameter keys, required fields, widgets, data sources,
visibility/modification stages, and unresolved runtime assumptions when useful.
