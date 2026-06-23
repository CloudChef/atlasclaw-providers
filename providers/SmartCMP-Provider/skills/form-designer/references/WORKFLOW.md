# SmartCMP Form Designer Workflow

This skill produces SmartCMP Angular form schema JSON only. It is deliberately
separate from the SmartCMP request workflow: no service request payloads are
created, no forms are saved to CMP, and no request submission tools are called.

## Existing Form URLs

Accept only current-instance SmartCMP UI edit URLs in this shape:

```text
https://cmp.example/#/main/service-model/forms/edit/<uuid>
```

The UUID maps to the read-only platform API:

```text
GET /platform-api/forms/<uuid>
```

The source schema is read from `content.schema`. The response may contain other
form metadata such as `name`, `description`, `enabled`, and `content.model`;
those fields are source context only and must not be written back by this skill.

When the user asks to change a form from a URL, use the source schema as
reference material and generate a complete replacement schema with
`design_form.py --mode regenerate`. Do not splice partial changes into the old
JSON, and do not ask the LLM to hand-copy a long existing schema.

## Output

User-visible output should contain:

1. A short change summary.
2. The final normalized `schema` JSON. For URL-based changes, describe it as a
   regenerated replacement schema for manual review and copying.

Scripts may also emit machine-readable metadata blocks for warnings,
assumptions, and source form identifiers. Agents should not expose internal
metadata unless it helps the user resolve a form design issue.

## Normalization Scope

The normalizer may repair deterministic SmartCMP schema structure for new,
regenerated, or deterministic modify-mode schemas:

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

The normalizer must preserve unknown keys. It must not invent business fields,
catalog request fields, approval rules, request payloads, or CMP persistence
behavior.

## Catalog Standard Fields

Standard service-catalog fields are catalog context, not universal form
requirements. Add them only when the user asks for that context.

| User wording | Schema field | Source meaning |
| --- | --- | --- |
| 业务组 / business group | `businessGroup` | business group UI field; semantic aliases include `businessGroup.id`, `businessGroup.name`, `businessGroup.code` |
| 应用 / application / app / project | `projects` | application UI field; semantic aliases include `application.id`, `application.name`, `application.code` |
| Owner / 负责人 | `owners` | owner UI field; semantic aliases include `owners.id`, `owners.name`, `owners.userName`, `owners.userLoginId` |
| name / description / number / execute time | `name`, `description`, `number`, `executeTime` | standard catalog name, description, number/count, and execution time |
| attachments / 附件 | `attachments` | catalog attachment list |
| Key-Value Tags | `keyValueTag` | catalog key-value tag list |
| Cloud Resource Tags | `cloudResourceTag` | catalog cloud resource tag list |

When a supported catalog context field is requested, use
`catalog_fields_json` for insertion and omit duplicate hand-written fields from
`schema_json`. JavaScript that depends on those values should reference the
inserted SmartCMP UI keys, for example `model.businessGroup` and
`model.projects`. A custom `fieldKey` on a catalog insertion is preserved, but
the tool should warn because CMP backend standard-field handling may not
recognize custom keys. User-defined fields belong in `schema_json` and can use
their own field keys normally.

This deterministic insertion path is the narrow case where `--mode modify` may
still read and preserve the source schema. For broader structure changes from a
URL, use `--mode regenerate` with a complete replacement schema.

For fields that synchronize service-catalog header display values into one JSON
string, use `catalog_context_sync_json`. That helper is intentionally narrow and
supports only the standard header display outputs documented in `SKILL.md`
(`业务组`, `应用系统`, `所有者`, and `名称`). Do not extend this workflow from a
single observed catalog route; read the relevant form or catalog metadata when
the requested context value is outside that fixed set.
