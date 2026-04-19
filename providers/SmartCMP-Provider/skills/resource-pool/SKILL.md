---
name: "resource-pool"
description: "Standalone SmartCMP resource-pool directory skill. Use when user says 查询可用的资源池, 查询资源池, 列出所有的资源池, list resource pools, or show all resource pools. This skill is read-only and should query the UI directory endpoint directly without asking for businessGroupId, sourceKey, or nodeType."
provider_type: "smartcmp"
instance_required: "true"

triggers:
  - 查询可用的资源池
  - 查询资源池
  - 列出所有的资源池
  - 列出资源池
  - 查看资源池
  - list resource pools
  - show resource pools
  - show all resource pools

use_when:
  - User wants a standalone list of SmartCMP resource pools
  - User asks to browse all resource pools without entering the provisioning workflow
  - User wants to search resource pools by keyword through the SmartCMP directory endpoint

avoid_when:
  - User wants request-flow resource pools for a selected business group and component type (use request skill)
  - User wants to submit or modify a SmartCMP request (use request skill)

related:
  - datasource
  - request

tool_list_name: "smartcmp_list_all_resource_pools"
tool_list_description: "List SmartCMP resource pools from the standalone UI directory endpoint. Use directly for 查询可用的资源池 / 列出所有的资源池 style requests. `query_value` is optional."
tool_list_entrypoint: "scripts/list_all_resource_pools.py"
tool_list_groups:
  - cmp
  - datasource
tool_list_capability_class: "provider:smartcmp"
tool_list_priority: 95
tool_list_result_mode: "tool_only_ok"
tool_list_parameters: |
  {
    "type": "object",
    "properties": {
      "query_value": {
        "type": "string",
        "description": "Optional keyword used to filter resource pools. Omit or pass an empty string to list all resource pools."
      }
    }
  }
---

# resource-pool

List SmartCMP resource pools through the same standalone directory endpoint used
by the CMP UI.

## Purpose

Provide a precise, read-only skill for direct resource-pool browsing.

- Query `/resource-bundles`
- Default to listing all resource pools
- Support optional keyword filtering with `query_value`
- Return a numbered list for the user and a machine-readable metadata block for follow-up actions

## Critical Rules

- Do not ask for `businessGroupId`, `sourceKey`, or `nodeType` when the user only wants to browse resource pools.
- Do not switch to the request workflow unless the user is actually preparing a request.
- Keep the user-visible output to the numbered list of resource-pool names.
- Treat IDs and other metadata as hidden backend state unless the user explicitly asks for them.

## Script

| Script | Description |
|--------|-------------|
| `scripts/list_all_resource_pools.py` | Call the standalone resource-pool directory endpoint and emit `##RESOURCE_POOL_DIRECTORY_META_START## ... ##RESOURCE_POOL_DIRECTORY_META_END##` |
