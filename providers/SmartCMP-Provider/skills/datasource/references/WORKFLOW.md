# Datasource Workflow Reference

The datasource Skill exposes five read-only AtlasClaw Tools through
`scripts/adapter.py`.

| User intent | Tool |
|-------------|------|
| Business-group scopes | `smartcmp_list_all_business_groups` |
| Applications in a business group | `smartcmp_list_applications` |
| Components for a catalog source key | `smartcmp_list_components` |
| Logical/OS templates | `smartcmp_query_logical_templates` |
| Images for a resource pool/template | `smartcmp_query_images` |

Treat SmartCMP business groups as the organizational scope users may call
tenant, 租户, 部门, BU, Department, 项目, or Project.

## Ownership boundaries

- Catalog list/detail is owned by the `request` Skill.
- Resource list/detail is owned by the `resource` Skill.
- Resource-pool directory is owned by the `resource-pool` Skill.
- Request-projected logical-template and image Tools directly reference these
  owning datasource handlers; no forwarding Python is created.

## Execution rules

1. Use the exact Tool schema rather than constructing CLI arguments.
2. Keep IDs in `_internal` metadata unless they are required for the next Tool.
3. Stop on a normalized error; do not switch to another endpoint in the
   Adapter.
4. An image ID is a `templateId`, never a `physicalTemplateId`.
5. SmartCMP Provider owns authentication, HTTP, pagination, normalization,
   and any explicit compatibility fallback.
