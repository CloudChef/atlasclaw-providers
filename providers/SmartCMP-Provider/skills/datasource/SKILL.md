---
name: "datasource"
description: "Discovery skill. Browse SmartCMP reference data such as service catalogs, business groups, tenant/租户/部门/BU/项目 scopes, applications, OS templates, images, and generic resource details before submitting a request. Standalone business-group discovery belongs here; standalone resource-pool and resource browsing still use their dedicated skills."
provider_type: "smartcmp"
instance_required: "true"

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
tool_list_all_business_groups_entrypoint: "scripts/list_all_business_groups.py"
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
| View catalogs | "show catalogs", "list services", "available services" |
| View business-group scopes | "show business groups", "show tenants", "查看租户", "查看部门", "查看项目" |
| List applications | "list applications", "show apps" |
| List OS templates | "list OS templates", "available OS" |
| List images | "list images", "available images" |
| Show resource details | "resource details", "show resource", "analyze resource data" |

**NOT for**: Resource provisioning -> use `request` skill instead.
**NOT for**: Direct "查询资源池", "查看所有资源", "查看所有云主机", or
"查看某个云主机详情" requests -> use `resource-pool` or `resource`.

## Scripts

Most scripts are located in `scripts/`.

| Script | Description | Arguments |
|--------|-------------|-----------|
| `scripts/list_all_business_groups.py` | List all business-group scopes (tenant / 租户 / 部门 / BU / 项目) from the standalone UI directory endpoint | `[QUERY_VALUE]` |
| `scripts/list_services.py` | List published service catalogs | `[KEYWORD]` |
| `scripts/list_resource.py` | List resource details by resource ID | `<RESOURCE_ID> [RESOURCE_ID ...]` |

`scripts/list_resource.py` also emits a normalized `type + properties` view per
resource as part of its standard output. That normalized view is shared across
discovery, troubleshooting, automation, and compliance analysis.

## Environment Setup

### Option 1: Direct Cookie

```powershell
# PowerShell - CMP_URL auto-normalizes (adds /platform-api if missing)
$env:CMP_URL = "<your-cmp-host>"           # e.g., "cmp.example.com" or "https://cmp.example.com/platform-api"
$env:CMP_COOKIE = '<full cookie string>'
```

```bash
# Bash
export CMP_URL="<your-cmp-host>"
export CMP_COOKIE="<full cookie string>"
```

### Option 2: Auto-Login (Recommended)

Automatically obtains and caches cookies (30-minute TTL). Auth URL is auto-inferred.

```powershell
# PowerShell
$env:CMP_URL = "<your-cmp-host>"
$env:CMP_USERNAME = "<username>"
$env:CMP_PASSWORD = "<password>"
```

```bash
# Bash
export CMP_URL="<your-cmp-host>"
export CMP_USERNAME="<username>"
export CMP_PASSWORD="<password>"
```

## Workflow Examples

### Example 1: List Business-Group Scopes

**User:** "Show available tenants or projects"

```bash
python scripts/list_all_business_groups.py
```

**Output:** Numbered list + `##BUSINESS_GROUP_DIRECTORY_META_START## ... ##BUSINESS_GROUP_DIRECTORY_META_END##`

### Example 2: List Available Catalogs

**User:** "Show available catalogs"

```bash
python scripts/list_services.py
```

**Output:** Numbered list + `##CATALOG_META_START## ... ##CATALOG_META_END##`

### Example 3: Show Resource Details

**User:** "Show resource details for ID X"

```bash
python scripts/list_resource.py <resource_id>
```

## Data Flow

```
scripts/list_all_business_groups.py [query_value]
  -> standalone business-group scope discovery

scripts/list_services.py [keyword]
  -> (catalogId, sourceKey)
```

## Output Meta Blocks

| Script | Meta Block |
|--------|------------|
| `scripts/list_all_business_groups.py` | `##BUSINESS_GROUP_DIRECTORY_META_START## ... ##BUSINESS_GROUP_DIRECTORY_META_END##` |
| `scripts/list_services.py` | `##CATALOG_META_START## ... ##CATALOG_META_END##` |

## Critical Rules

> All operations are **read-only** - no data is created or modified.

> Scripts are shared with the `request` skill.

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
