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

## Output

User-visible output should contain:

1. A short change summary.
2. The final normalized `schema` JSON.

Scripts may also emit machine-readable metadata blocks for warnings,
assumptions, and source form identifiers. Agents should not expose internal
metadata unless it helps the user resolve a form design issue.

## Normalization Scope

The normalizer may repair deterministic SmartCMP schema structure:

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
| Key-Value Tags | `keyValueTag` | UI field `keyValueTag`, resource data `Compute.tags_copy` |
| Cloud Resource Tags | `cloudResourceTag` | catalog cloud resource tag list |

The Linux VM catalog route
`#/main/catalog-ui/request/f3a4149b-cfbf-446a-a340-512a304014f2` uses
`catalog.exts.field` and schema field `expansion.config.value.expression` to
synchronize catalog context values such as `businessGroupName` and `userName`.

Deterministic insertion templates support the displayable standard catalog field
set observed from the Linux VM catalog: `businessGroup.*`,
`application.*`/`projects.*`, `owners.*`, `name`, `description`, `number`,
`executeTime`, `attachments`, `keyValueTag`, and `cloudResourceTag`.

When a supported catalog context field is requested, use
`catalog_fields_json` for insertion and omit duplicate hand-written fields from
`schema_json`. JavaScript that depends on those values should reference the
inserted SmartCMP UI keys, for example `model.businessGroup` and
`model.projects`. A custom `fieldKey` on a catalog insertion is preserved, but
the tool should warn because CMP backend standard-field handling may not
recognize custom keys. User-defined fields belong in `schema_json` and can use
their own field keys normally.
