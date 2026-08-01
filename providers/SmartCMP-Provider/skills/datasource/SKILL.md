---
name: "datasource"
description: "Read-only discovery skill. Browse SmartCMP reference data such as service catalogs, business groups, tenant and project scopes, applications, OS templates, images, and generic resource details. Request, apply, create VM, or provisioning intent belongs to the request skill, whose request-projected aliases reuse the same logical-template and image scripts."
provider_type: "smartcmp"
instance_required: "true"
routing_visibility: "internal"

# === LLM Context Fields ===
triggers:
  - list services
  - list catalogs
  - list business groups
  - show business groups
  - show tenants
  - list tenants
  - tenant
  - 租户
  - 部门
  - BU
  - Department
  - 项目
  - Project
  - list applications
  - list OS templates
  - list images
  - resource details
  - 查看服务目录
  - 查看可用服务
  - 查看业务组
  - 查看租户
  - 查看部门
  - 查看项目

use_when:
  - User wants to browse or explore available options before taking action
  - User asks about available services, business-group scopes, tenants, departments, BUs, projects, applications, templates, images, or resource details
  - User needs reference data to prepare a request but does not want to submit yet
  - User wants a standalone list of SmartCMP business groups through the UI directory endpoint
  - User wants resource details by resource ID before analysis or troubleshooting

avoid_when:
  - User wants to submit a provisioning request (use request skill)
  - User wants to approve or reject requests (use approval skill)
  - User wants autonomous request processing (use request-decomposition-agent)
  - User wants a direct all-resource-pools, all-resources, all-virtual-machines, or cloud-host detail/attribute analysis flow (use resource-pool or resource)

examples:
  - "Show available service catalogs"
  - "Show available tenants or projects"
  - "List applications for business group X"
  - "List OS templates for VM provisioning"
  - "Show resource details for resource ID X"

related:
  - request
  - approval
  - resource-pool
  - resource

tool_list_all_business_groups_name: "smartcmp_list_all_business_groups"
tool_list_all_business_groups_description: "List SmartCMP business groups from the standalone UI directory endpoint. Treat 'business group' as the same scope concept users may call tenant, 租户, 部门, BU, Department, 项目, or Project. Use this for standalone discovery only; do not switch to the request workflow unless the user is actually preparing a request."
tool_list_all_business_groups_entrypoint: "scripts/adapter.py:list_all_business_groups"
tool_list_all_business_groups_groups:
  - cmp
  - datasource
tool_list_all_business_groups_capability_class: "provider:smartcmp"
tool_list_all_business_groups_priority: 90
tool_list_all_business_groups_result_mode: "tool_only_ok"
tool_list_all_business_groups_parameters: |
  {
    "type": "object",
    "properties": {
      "query_value": {
        "type": "string",
        "description": "Optional keyword used to filter business groups. Omit or pass an empty string to list all business groups."
      }
    }
  }
tool_list_applications_name: "smartcmp_list_applications"
tool_list_applications_description: "List SmartCMP applications for a selected business group. Use this as shared read-only reference data for request preparation or provider-native analysis workflows."
tool_list_applications_entrypoint: "scripts/adapter.py:list_applications"
tool_list_applications_groups:
  - cmp
  - datasource
tool_list_applications_capability_class: "provider:smartcmp"
tool_list_applications_priority: 95
tool_list_applications_result_mode: "tool_only_ok"
tool_list_applications_cli_positional:
  - business_group_id
tool_list_applications_parameters: |
  {
    "type": "object",
    "properties": {
      "business_group_id": {
        "type": "string",
        "description": "REQUIRED. UUID of the selected SmartCMP business group."
      }
    },
    "required": ["business_group_id"]
  }
tool_list_components_name: "smartcmp_list_components"
tool_list_components_description: "List SmartCMP component metadata for a catalog source key such as resource.windows. Use sourceKey, not catalogId. Do not use this tool for logical templates, OS templates, or cloud images."
tool_list_components_entrypoint: "scripts/adapter.py:list_components"
tool_list_components_groups:
  - cmp
  - datasource
tool_list_components_capability_class: "provider:smartcmp"
tool_list_components_priority: 95
tool_list_components_result_mode: "tool_only_ok"
tool_list_components_cli_positional:
  - source_key
tool_list_components_parameters: |
  {
    "type": "object",
    "properties": {
      "source_key": {
        "type": "string",
        "description": "REQUIRED. Catalog sourceKey or resource type, for example resource.windows. Do not pass BUILD-IN-CATALOG-* catalog IDs."
      }
    },
    "required": ["source_key"]
  }
tool_query_logical_templates_name: "smartcmp_query_logical_templates"
tool_query_logical_templates_description: "Query SmartCMP logical templates globally or filter them by resource pool, catalog node, OS type, or template name. Omit resource_bundle_id for a global query."
tool_query_logical_templates_entrypoint: "scripts/adapter.py:list_logical_templates"
tool_query_logical_templates_groups:
  - cmp
  - datasource
tool_query_logical_templates_capability_class: "provider:smartcmp"
tool_query_logical_templates_priority: 95
tool_query_logical_templates_result_mode: "tool_only_ok"
tool_query_logical_templates_use_when:
  - "User asks to list logical templates or OS templates"
tool_query_logical_templates_cli_positional:
  - query
tool_query_logical_templates_cli_flag_overrides:
  resource_bundle_id: "--resource-bundle-id"
  catalog_id: "--catalog-id"
  node_template_name: "--node-template-name"
  os_type: "--os-type"
tool_query_logical_templates_parameters: |
  {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Optional logical-template-name filter."
      },
      "resource_bundle_id": {
        "type": "string",
        "description": "Optional resource pool ID. Omit for a global query."
      },
      "catalog_id": {
        "type": "string",
        "description": "Optional catalog UUID."
      },
      "node_template_name": {
        "type": "string",
        "description": "Optional catalog node template name."
      },
      "os_type": {
        "type": "string",
        "description": "Optional OS type, for example Linux or Windows."
      }
    }
  }
tool_query_images_name: "smartcmp_query_images"
tool_query_images_description: "Query SmartCMP image options for a selected resource pool, logical template, and cloud entry type. A selected image id is a templateId, never a physicalTemplateId."
tool_query_images_entrypoint: "scripts/adapter.py:list_images"
tool_query_images_groups:
  - cmp
  - datasource
tool_query_images_capability_class: "provider:smartcmp"
tool_query_images_priority: 95
tool_query_images_result_mode: "tool_only_ok"
tool_query_images_use_when:
  - "User asks to list cloud images for a selected resource pool and logical template"
tool_query_images_cli_positional:
  - resource_bundle_id
  - logic_template_id
  - cloud_entry_type
tool_query_images_parameters: |
  {
    "type": "object",
    "properties": {
      "resource_bundle_id": {
        "type": "string",
        "description": "REQUIRED. Selected SmartCMP resource bundle ID."
      },
      "logic_template_id": {
        "type": "string",
        "description": "REQUIRED. Selected logic template ID."
      },
      "cloud_entry_type": {
        "type": "string",
        "description": "REQUIRED. Full cloudEntryTypeId from the selected resource pool, for example yacmp:cloudentry:type:vsphere."
      }
    },
    "required": ["resource_bundle_id", "logic_template_id", "cloud_entry_type"]
  }
---

# datasource

Reference data discovery skill (read-only).

## Purpose

Query and browse reference data as standalone read-only operations. Use when
user wants to explore available options without submitting a request. This
skill owns standalone business-group scope discovery. Dedicated
`resource-pool` and `resource` skills still handle standalone resource-pool
and resource browsing.

## Terminology Mapping

Treat SmartCMP `business group` as a generic organizational scope. Users may
describe the same concept as:

- tenant
- 租户
- 部门
- BU
- Department
- 项目
- Project

Resolve these terms against SmartCMP business-group data unless the user is
clearly referring to some other system-level tenant concept. Mirror the user's
wording in replies when it helps readability, but keep the SmartCMP field names
`businessGroupName` and `bgId` when calling scripts or building request data.

## Trigger Conditions

Activate this skill when user intent matches:

| Intent | Keywords |
|--------|----------|
| View business-group scopes | "show business groups", "show tenants", "查看租户", "查看部门", "查看项目" |
| List applications | "list applications", "show apps" |
| List OS templates | "list OS templates", "available OS" |
| List images | "list images", "available images" |

**NOT for**: Resource provisioning -> use `request` skill instead.
**NOT for**: Catalog discovery -> use `request`.
**NOT for**: Direct "查询资源池", "查看所有资源", "查看所有云主机", or
"查看某个云主机详情" requests -> use `resource-pool` or `resource`.

## Handlers

All five datasource Tool commands are co-located in `scripts/adapter.py`:

| Handler | Tool | Purpose |
|--------|------|---------|
| `list_all_business_groups` | `smartcmp_list_all_business_groups` | List standalone business-group scopes |
| `list_applications` | `smartcmp_list_applications` | List applications in a business group |
| `list_components` | `smartcmp_list_components` | List component metadata for a catalog source key |
| `list_logical_templates` | `smartcmp_query_logical_templates` | Query logical templates |
| `list_images` | `smartcmp_query_images` | Query cloud images |

Catalog list/detail belongs to the `request` Skill Adapter. Resource
list/detail belongs to the `resource` Skill Adapter. The request Skill's
logical-template and image Tools are aliases to the two owning datasource
handlers; they do not create forwarding Python files.

The Adapter receives the selected instance and Authentication Context from
AtlasClaw. SmartCMP Provider owns authentication, HTTP, pagination,
normalization, and resource/catalog domain rules.

## Workflow examples

- “Show available tenants or projects”: call
  `smartcmp_list_all_business_groups`.
- “List Linux logical templates”: call `smartcmp_query_logical_templates`
  with `os_type=Linux`.
- “List images for this pool and logical template”: call
  `smartcmp_query_images` with the exact three IDs/types required by the Tool
  schema.

Omit `resource_bundle_id` for a global logical-template directory query; pass
it to show only templates supported by one resource pool. A selected image
`id` is a `templateId`; it must never be serialized as `physicalTemplateId`.

## Critical Rules

> All operations are **read-only** - no data is created or modified.

> Request aliases reference the owning datasource handlers; no implementation
> is copied or proxied through another Python process.

> Standalone directory queries for all business-group scopes belong to
> `datasource`. Standalone resource-pool and resource browsing belong to
> `resource-pool` and `resource`.

> On error (`[ERROR]`), report to user immediately; do NOT self-debug.

## Error Handling

| Error | Resolution |
|-------|------------|
| `401` / Token expired | Ask user to refresh cookie |
| Missing arguments | Check script usage in docstring |

## References

- [WORKFLOW.md](references/WORKFLOW.md) - Detailed script usage and query flows
