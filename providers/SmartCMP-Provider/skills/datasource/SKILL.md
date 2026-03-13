---
name: "datasource"
description: "Query SmartCMP reference data (read-only). Trigger when user asks to view catalogs, list business groups, check resource pools, show applications. Does NOT submit requests."
---

# datasource

SmartCMP reference data query skill (read-only).

## Purpose

Query and browse SmartCMP reference data as standalone read-only operations. Use when user wants to explore or look up data WITHOUT submitting a request.

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

## Environment Setup

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
| `list_components.py` | `##COMPONENT_META_START## ... ##COMPONENT_META_END##` |
| `list_resource_pools.py` | `##RESOURCE_POOL_META_START## ... ##RESOURCE_POOL_META_END##` |
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
