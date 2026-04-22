---
name: "business-group"
description: "Standalone SmartCMP business-group directory skill. Use when user says 查看所有业务组, 列出所有业务组, 查询业务组, show business groups, or list all business groups. This skill is read-only and should query the UI directory endpoint directly without asking for catalogId."
provider_type: "smartcmp"
instance_required: "true"

triggers:
  - 查看所有业务组
  - 列出所有业务组
  - 查询业务组
  - 查看业务组
  - list business groups
  - show business groups
  - show all business groups

use_when:
  - User wants a standalone list of SmartCMP business groups
  - User asks to view all business groups without first selecting a service catalog
  - User wants to search business groups by keyword through the SmartCMP directory endpoint

avoid_when:
  - User wants business groups for a selected service catalog in the request workflow (use request skill)
  - User wants to submit or modify a SmartCMP request (use request skill)

related:
  - datasource
  - request

tool_list_name: "smartcmp_list_all_business_groups"
tool_list_description: "List SmartCMP business groups from the standalone UI directory endpoint. ONLY for standalone browsing when user explicitly asks to view business groups (查看所有业务组 / 列出所有业务组). NEVER call this tool during request or ticket submission workflows — the request skill uses smartcmp_list_available_bgs instead."
tool_list_entrypoint: "../datasource/scripts/list_all_business_groups.py"
tool_list_groups:
  - cmp
  - datasource
tool_list_capability_class: "provider:smartcmp"
tool_list_priority: 90
tool_list_result_mode: "tool_only_ok"
tool_list_parameters: |
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

# business-group

List SmartCMP business groups through the same standalone directory endpoint used
by the CMP UI.

## Purpose

Provide a precise, read-only skill for direct business-group browsing.

- Query `/business-groups/has-update-permission`
- Default to listing all business groups
- Support optional keyword filtering with `query_value`
- Return a numbered list for the user and a machine-readable metadata block for follow-up actions

## Critical Rules

- Do not ask for `catalogId` when the user only wants to view business groups.
- Do not switch to the request workflow unless the user is actually preparing a request.
- Keep the user-visible output to the numbered list of business-group names.
- Treat IDs and other metadata as hidden backend state unless the user explicitly asks for them.

## Script

| Script | Description |
|--------|-------------|
| `../datasource/scripts/list_all_business_groups.py` | Call the standalone business-group directory endpoint |
