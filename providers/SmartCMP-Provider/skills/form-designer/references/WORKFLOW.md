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
