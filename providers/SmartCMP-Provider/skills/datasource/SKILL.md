---
name: "datasource"
description: "Discovery skill. Browse available services, business groups, resource pools, applications, OS templates, and images before submitting a request."
provider_type: "smartcmp"
instance_required: "true"

# === LLM Context Fields ===
triggers:
  - list services
  - list catalogs
  - show business groups
  - list resource pools
  - list applications
  - list OS templates
  - list images
  - resource details
  - show resource
  - analyze resource data

use_when:
  - User wants to browse or explore available options before taking action
  - User asks about available services, business groups, resource pools, applications, templates, or images
  - User needs reference data to prepare a request but does not want to submit yet
  - User wants resource details by resource ID before analysis or troubleshooting

avoid_when:
  - User wants to submit a provisioning request (use request skill)
  - User wants to approve or reject requests (use approval skill)
  - User wants autonomous request processing (use request-decomposition-agent)

examples:
  - "Show available service catalogs"
  - "List business groups for catalog X"
  - "What resource pools are available?"
  - "List OS templates for VM provisioning"

related:
  - request
  - approval
---

# datasource

Reference data discovery skill (read-only).

## Purpose

Query and browse reference data as standalone read-only operations. Use when user wants to explore available options without submitting a request.

## Trigger Conditions

Activate this skill when user intent matches:

| Intent | Keywords |
|--------|----------|
| View catalogs | "show catalogs", "list services", "available services" |
| List business groups | "list business groups", "show BGs", "available BGs" |
| Check resource pools | "list resource pools", "available pools" |
| List applications | "list applications", "show apps" |
| List OS templates | "list OS templates", "available OS" |
| List images | "list images", "available images" |

**NOT for**: Resource provisioning → use `request` skill instead.

## Scripts

All scripts are located in `../shared/scripts/`:

| Script | Description | Arguments |
|--------|-------------|-----------|
| `list_services.py` | List published service catalogs | `[KEYWORD]` |
| `list_business_groups.py` | List business groups for a catalog | `<CATALOG_ID>` |
| `list_components.py` | Get component type (nodeType) | `<SOURCE_KEY>` |
| `list_resource_pools.py` | List resource pools | `<BG_ID> <SOURCE_KEY> <NODE_TYPE>` |
| `list_applications.py` | List applications | `<BG_ID> [KEYWORD]` |
| `list_os_templates.py` | List OS templates (VM only) | `<OS_TYPE> <RESOURCE_BUNDLE_ID>` |
| `list_cloud_entry_types.py` | Get cloud entry types | (no args) |
| `list_images.py` | List images (private cloud) | `<RB_ID> <TEMPLATE_ID> <CLOUD_TYPE_ID>` |
| `list_resource.py` | List resource details by resource ID | `<RESOURCE_ID> [RESOURCE_ID ...]` |

`list_resource.py` also emits a normalized `type + properties` view per
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

### Example 1: List Available Catalogs

**User:** "Show available catalogs"

```bash
python ../shared/scripts/list_services.py
```

**Output:** Numbered list + `##CATALOG_META_START## ... ##CATALOG_META_END##`

### Example 2: List Business Groups

**User:** "List business groups for Linux VM"

```bash
# Get catalog ID from previous step
python ../shared/scripts/list_business_groups.py <catalogId>
```

### Example 3: List Resource Pools

**User:** "What resource pools are available?"

```bash
# Requires 3 arguments: bgId, sourceKey, nodeType
python ../shared/scripts/list_resource_pools.py \
  47673d8d-6b3f-41e1-8ec0-c37e082d9020 \
  resource.iaas.machine.instance.abstract \
  cloudchef.nodes.Compute
```

### Example 4: Show Resource Details

**User:** "Show resource details for ID X"

```bash
python ../shared/scripts/list_resource.py <resource_id>
```

## Data Flow

```
list_services.py
      ↓ (catalogId, sourceKey)
      ├── list_business_groups.py <catalogId>
      │         ↓ (bgId)
      │         └── list_applications.py <bgId>
      │
      └── list_components.py <sourceKey>
                ↓ (typeName = nodeType)
                └── list_resource_pools.py <bgId> <sourceKey> <nodeType>
                          ↓ (resourceBundleId, cloudEntryTypeId)
                          ├── list_os_templates.py <osType> <resourceBundleId>
                          └── list_images.py <rbId> <templateId> <cloudEntryTypeId>
```

## Output Meta Blocks

| Script | Meta Block |
|--------|------------|
| `list_services.py` | `##CATALOG_META_START## ... ##CATALOG_META_END##` |
| `list_business_groups.py` | `##BG_META_START## ... ##BG_META_END##` |
| `list_components.py` | `##COMPONENT_META_START## ... ##COMPONENT_META_END##` |
| `list_resource_pools.py` | `##RESOURCE_POOL_META_START## ... ##RESOURCE_POOL_META_END##` |
| `list_os_templates.py` | `##OS_TEMPLATE_META_START## ... ##OS_TEMPLATE_META_END##` |
| `list_cloud_entry_types.py` | `##CLOUD_ENTRY_TYPES_META_START## ... ##CLOUD_ENTRY_TYPES_META_END##` |

## Critical Rules

> All operations are **read-only** — no data is created or modified.

> Scripts are shared with the `request` skill.

> On error (`[ERROR]`), report to user immediately; do NOT self-debug.

## Error Handling

| Error | Resolution |
|-------|------------|
| `401` / Token expired | Ask user to refresh cookie |
| Missing arguments | Check script usage in docstring |

## References

- [WORKFLOW.md](references/WORKFLOW.md) — Detailed script usage and query flows
