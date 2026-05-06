---
name: "resource"
description: "SmartCMP resource browsing, detail inspection, and user-scoped resource operation skill. Use when the user asks to list resources, list virtual machines, show VM details, list available/executable operations, execute resource operations, run day-2 changes, start, stop, restart, refresh, suspend, resume, create snapshot, restore snapshot, power on, power off, 查看云资源列表、查看云主机详情、查看可执行操作、执行资源操作、开机、关机. Use `/nodes/search` for list browsing with visible status, `PATCH /nodes/{id}/view` for one-host detail inspection until the CMP view API bug is fixed, `GET /nodes/{category}/{id}/resource-actions` for current-user executable operations, and `POST /nodes/resource-operations` for no-parameter resource operations."
provider_type: "smartcmp"
instance_required: "true"

triggers:
  - 查看云资源列表
  - 查看云资源
  - 查看所有资源
  - 查看我的资源
  - 查看云主机列表
  - 查看云主机
  - 查看所有云主机
  - 查看主机详情
  - 查看云主机详情
  - 分析云主机属性
  - 云资源开机
  - 云资源关机
  - 云主机开机
  - 云主机关机
  - 启动云资源
  - 停止云资源
  - 启动云主机
  - 停止云主机
  - 开机
  - 关机
  - 查询资源操作
  - 查看资源操作
  - 查看可执行操作
  - 查看云主机可执行操作
  - 执行资源操作
  - 执行云主机操作
  - list resources
  - show resources
  - list virtual machines
  - show virtual machines
  - show vm details
  - list resource operations
  - show resource operations
  - executable resource operations
  - execute resource operation
  - run resource operation
  - execute day-2 operation
  - run day-2 change
  - change resource state
  - start resource
  - stop resource
  - restart resource
  - refresh resource
  - suspend resource
  - resume resource
  - start vm
  - stop vm
  - restart vm
  - refresh vm
  - suspend vm
  - resume vm
  - power on vm
  - power off vm
  - create snapshot
  - take snapshot
  - restore snapshot

use_when:
  - User wants a standalone list of SmartCMP cloud resources with current status
  - User wants a standalone list of SmartCMP cloud hosts or virtual machines with current status
  - User wants to inspect one cloud host by resource ID and analyze its current properties
  - User wants to search resources or virtual machines by keyword through the CMP UI list endpoint
  - User wants to see which resource operations the current SmartCMP user can execute on a resource
  - User wants to execute an enabled no-parameter operation on an existing SmartCMP cloud resource or virtual machine

avoid_when:
  - User wants resource compliance, lifecycle, supportability, or security analysis (use resource-compliance skill)
  - User wants generic reference data browsing unrelated to resources (use datasource skill)
  - User wants to submit or modify a SmartCMP request (use request skill)

examples:
  - "List my virtual machines"
  - "Show all cloud resources"
  - "Show details for virtual machine <resource-id>"
  - "List executable operations for vm-a"
  - "Stop vm-a"
  - "Execute create_snapshot on this virtual machine"
  - "Start the first virtual machine"
  - "Stop resource 3615d791-36b4-4fa1-be61-f8550c7fbcb8"

related:
  - datasource
  - resource-compliance
  - resource-pool
  - request

tool_list_name: "smartcmp_list_all_resource"
tool_list_description: "List SmartCMP resources or virtual machines from the standalone CMP UI list endpoint and show each item's current status. Use `scope=all_resources` for 查看所有资源 and `scope=virtual_machines` for 查看所有云主机. `query_value` is optional. If the user only asked to browse resources, return the numbered list. If the user asked for a resource operation, use the list result as target-resolution evidence and continue to confirmation or clarification."
tool_list_entrypoint: "scripts/list_all_resource.py"
tool_list_groups:
  - cmp
  - datasource
tool_list_capability_class: "provider:smartcmp"
tool_list_priority: 98
tool_list_result_mode: "llm"
tool_list_parameters: |
  {
    "type": "object",
    "properties": {
      "scope": {
        "type": "string",
        "enum": ["all_resources", "virtual_machines"],
        "description": "Resource listing scope. Use `all_resources` for 云资源 and `virtual_machines` for 云主机."
      },
      "query_value": {
        "type": "string",
        "description": "Optional keyword used to filter resources."
      },
      "page": {
        "type": "integer",
        "description": "Page number. Default: 1.",
        "default": 1
      },
      "size": {
        "type": "integer",
        "description": "Page size. Default: 20.",
        "default": 20
      }
    }
  }
tool_detail_name: "smartcmp_resource_detail"
tool_detail_description: "Summarize one SmartCMP cloud host by resource ID using `PATCH /nodes/{id}/view` until the CMP view API bug is fixed. Use this for 查看云主机详情 or 分析云主机属性."
tool_detail_entrypoint: "scripts/resource_detail.py"
tool_detail_groups:
  - cmp
  - datasource
  - resource
tool_detail_capability_class: "provider:smartcmp"
tool_detail_priority: 108
tool_detail_result_mode: "tool_only_ok"
tool_detail_cli_positional:
  - resource_id
tool_detail_parameters: |
  {
    "type": "object",
    "properties": {
      "resource_id": {
        "type": "string",
        "description": "SmartCMP resource ID for the cloud host to inspect."
      }
    },
    "required": ["resource_id"]
  }
tool_operations_name: "smartcmp_list_resource_operations"
tool_operations_description: "List enabled no-parameter SmartCMP resource operations executable by the current user through `GET /nodes/{category}/{resource_id}/resource-actions`. Accepts a SmartCMP detail URL such as `#/main/virtual-machines/<id>/details` or a raw resource UUID. Do not use resource type definition or built-in action endpoints as fallback. If the user only asked what operations are available, return the numbered operation list. If the user asked to execute an operation, use this result as permission/operation validation evidence and continue to confirmation or clarification."
tool_operations_entrypoint: "scripts/list_resource_operations.py"
tool_operations_groups:
  - cmp
  - resource
  - day2
tool_operations_capability_class: "provider:smartcmp"
tool_operations_priority: 132
tool_operations_result_mode: "llm"
tool_operations_cli_positional:
  - resource_ref
tool_operations_parameters: |
  {
    "type": "object",
    "properties": {
      "resource_ref": {
        "type": "string",
        "description": "SmartCMP resource UUID or detail URL, for example `https://cmp/#/main/virtual-machines/<id>/details`."
      },
      "category": {
        "type": "string",
        "description": "Fallback resource category when resource_ref is a raw UUID. Default: virtual-machines.",
        "default": "virtual-machines"
      }
    },
    "required": ["resource_ref"]
  }
tool_power_name: "smartcmp_operate_resource"
tool_power_description: "Execute an enabled no-parameter SmartCMP resource operation through `POST /nodes/resource-operations`. RULES: (1) NEVER claim an operation was submitted without actually calling this tool — fabricating results is strictly forbidden. (2) Before calling, confirm the exact resource and operation with the user. (3) Always pass real SmartCMP resource UUIDs or detail URLs in resource_ids, not display names or list indexes. (4) The tool rechecks `GET /nodes/{category}/{id}/resource-actions` with the current user context before submission. (5) After success, keep the user response short; do not print raw request or response details."
tool_power_entrypoint: "scripts/operate_resource.py"
tool_power_groups:
  - cmp
  - resource
  - day2
tool_power_capability_class: "provider:smartcmp"
tool_power_priority: 140
tool_power_result_mode: "tool_only_ok"
tool_power_cli_positional:
  - resource_ids
tool_power_cli_split:
  - resource_ids
tool_power_parameters: |
  {
    "type": "object",
    "properties": {
      "resource_ids": {
        "type": "string",
        "description": "One or more SmartCMP resource IDs or detail URLs. Separate multiple IDs with spaces: 'id1 id2 id3'."
      },
      "category": {
        "type": "string",
        "description": "Fallback resource category when resource_ids contains raw UUIDs. Default: virtual-machines.",
        "default": "virtual-machines"
      },
      "action": {
        "type": "string",
        "description": "SmartCMP operation ID to execute. start/stop and 开机/关机 aliases are supported."
      }
    },
    "required": ["resource_ids", "action"]
  }
---

# resource

Browse SmartCMP resources, inspect cloud host details, list current-user executable operations, and execute enabled no-parameter resource operations.

## Purpose

Provide one skill for resource browsing, per-host property inspection, and day2 resource operations.

- Query `/nodes/search` for all-resource or virtual-machine lists
- Show each listed item's current status so users can decide whether to start or stop it
- Call `PATCH /nodes/{id}/view` for one cloud host detail snapshot until the CMP view API bug is fixed
- Present cloud-host detail in a compact CMP-style layout instead of dumping raw metadata
- Use `GET /nodes/{category}/{id}/resource-actions` to list enabled no-parameter operations executable by the current SmartCMP user
- Use `POST /nodes/resource-operations` for immediate no-parameter resource operations

## Scope Rules

- Use `smartcmp_list_all_resource` when the user asks for 云资源 or 云主机 lists.
- Use `smartcmp_resource_detail` when the user asks for one cloud host detail or property analysis by resource ID.
- Use `smartcmp_list_resource_operations` when the user asks what operations the current user can execute on a resource.
- Use `smartcmp_operate_resource` when the user wants to execute an enabled no-parameter operation on an existing cloud resource.
- Treat "我的" and "所有" the same for now because the provided UI URLs do not expose a separate owner-only filter; rely on SmartCMP access control and the current user's visible scope.

## Operation Workflow

An operation intent means the user wants to change an existing resource state, for example `stop 1 vm-a`, `restart vm-a`, `execute create_snapshot on this virtual machine`, `stop the second VM`, or `take a snapshot`.

When operation intent is present, a resource lookup is only a target-resolution step. Do not stop at the `smartcmp_list_all_resource` visible list output, and do not answer only with `Found N ...`. Use the returned metadata to continue to operation resolution, confirmation, or a clarification question.

1. Resolve the target resource.
   - If the user references a recent numbered list item, such as `1`, `第 1 台`, or `the first one`, use the matching item from the latest `smartcmp_list_all_resource` metadata.
   - If the user provides action + index + name, such as `stop 1 vm-a`, treat the index as the selection and the name as a safety check. If they match, use that resource UUID. If they conflict, ask the user to clarify.
   - If the user provides only a display name, call `smartcmp_list_all_resource` with `query_value`, then map an exact unique match to its UUID. If multiple resources remain plausible, ask the user to choose by numbered item.
   - Never pass a display name, list index, or natural-language phrase as `resource_id` to `smartcmp_resource_detail` or as `resource_ids` to `smartcmp_operate_resource`.
2. Resolve the operation.
   - Use `start`, `stop`, `开机`, and `关机` aliases directly.
   - Use exact operation IDs such as `restart`, `refresh`, or `create_snapshot` directly.
   - If the user gives a natural-language operation name, such as `take a snapshot`, first call `smartcmp_list_resource_operations` for the resolved resource and match only against the current user's executable no-parameter operations. If there is no unambiguous match, show the executable operation IDs and ask which one to run.
3. Confirm before submission.
   - Once both the resource UUID and operation ID are known, ask one concise confirmation using the resource name and operation ID/name, for example `Confirm stop on vm-a?`
   - Stop after asking for confirmation. Do not submit until the user explicitly confirms.
4. Submit after confirmation.
   - After explicit confirmation, call `smartcmp_operate_resource` with concrete resource UUIDs or detail URLs and the operation ID.
   - The latest explicit operation command supersedes older unfinished operation intent. For example, if the previous turn was about snapshots but the latest user message says `stop 1 vm-a`, handle `stop`.

## Critical Rules

- Do not switch to resource-compliance analysis unless the user explicitly asks for compliance, supportability, lifecycle, or security risk.
- Do not use the list endpoint when the user already provided a concrete resource ID for host detail analysis.
- `smartcmp_resource_detail` uses `PATCH /nodes/{id}/view` to fetch the host evidence view until the CMP view API bug is fixed. Do not use older resource/detail APIs as fallback in this interactive detail skill.
- Keep list-mode output to a numbered list of resource names plus current status.
- For host detail, present only grouped key facts. Do not dump raw properties, top-level keys, source endpoints, or every key/value returned by the API.
- `smartcmp_list_resource_operations` must only use `GET /nodes/{category}/{id}/resource-actions` with the current user context. Do not use `/resource-types/.../support-actions`, `/resource-types/.../resource-actions`, `/nodes/build-in-actions`, or other definition-level endpoints as executable-operation fallback.
- Only show enabled no-parameter operations as executable choices. Operations that are disabled, web-only, have `inputsForm`, or require non-empty `parameters` are outside this tool's execution scope.
- **NEVER claim a resource operation was submitted or succeeded without actually calling `smartcmp_operate_resource`.** You must call the tool and receive a real response before telling the user the operation is done.
- **Before calling the operation tool, confirm with the user:** show the target resource name + operation ID/name, ask `Confirm this operation?`, and STOP. Only call the tool after user confirms.
- After a resource operation succeeds, respond with only the action, resource ID(s), submitted status, message, and verification hint. Do not print raw request payloads or raw response details.
- Resolve every target to a concrete SmartCMP resource UUID before calling `smartcmp_operate_resource`.
- When the user only provides a resource name, first use `smartcmp_list_all_resource` to find the resource and map the chosen item to its `id`.
- Use the visible resource status from the list output to avoid redundant actions. If a resource is already `started` and the user asks to start it again, explain that no power change is needed.
- Do not guess between multiple resources that share the same display name. Ask the user to pick the correct one.
- Do not use this skill for provisioning new resources. For destructive or delete-like operations, show the exact operation and target and require explicit confirmation before execution.

## Preferred Detail Layout

When showing one cloud-host detail, keep the response concise and close to the CMP detail page:

1. One short overview block:
   - Name
   - Status
   - Compute
   - IP address
2. Then only the sections that actually have values:
   - Basic Information
   - Attributes
   - Service Information
   - Organization Information
   - Platform Information
   - IP Addresses
   - Disks
   - Physical Host Information
   - Resource Environment

Never show:

- Source endpoint paths
- Raw JSON blobs
- Flattened `properties` dumps
- “Top Level Keys”
- Repeated IDs or technical fields unless they are part of the compact detail view

## Scripts

| Script | Description |
|--------|-------------|
| `scripts/list_all_resource.py` | Call the standalone resource list endpoint and emit a numbered resource directory with visible status |
| `scripts/resource_detail.py` | Fetch one cloud host view and emit a compact grouped detail summary |
| `scripts/list_resource_operations.py` | List enabled no-parameter operations executable by the current SmartCMP user for one resource |
| `scripts/operate_resource.py` | Submit SmartCMP no-parameter resource operations for one or more resource IDs |
