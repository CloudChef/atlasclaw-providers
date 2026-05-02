---
name: "resource"
description: "SmartCMP resource browsing, detail inspection, and power operations skill. Use when the user asks to 查看云资源列表、查看云主机列表、查看云主机详情、分析云主机属性、启动云主机、停止云主机、开机、关机. Use `/nodes/search` for list browsing with visible status, `PATCH /nodes/{id}/refresh-status` for one-host detail inspection, and `POST /nodes/resource-operations` for start/stop power actions."
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
  - list resources
  - show resources
  - list virtual machines
  - show virtual machines
  - show vm details
  - start resource
  - stop resource
  - start vm
  - stop vm
  - power on vm
  - power off vm

use_when:
  - User wants a standalone list of SmartCMP cloud resources with current status
  - User wants a standalone list of SmartCMP cloud hosts or virtual machines with current status
  - User wants to inspect one cloud host by resource ID and analyze its current properties
  - User wants to search resources or virtual machines by keyword through the CMP UI list endpoint
  - User wants to start an existing SmartCMP cloud resource or virtual machine
  - User wants to stop an existing SmartCMP cloud resource or virtual machine

avoid_when:
  - User wants resource compliance, lifecycle, supportability, or security analysis (use resource-compliance skill)
  - User wants generic reference data browsing unrelated to resources (use datasource skill)
  - User wants to submit or modify a SmartCMP request (use request skill)

examples:
  - "查看我的云主机"
  - "查看所有资源"
  - "查看云主机详情"
  - "把 mysqlLinux2 云资源关机"
  - "启动这台云主机"
  - "Stop resource 3615d791-36b4-4fa1-be61-f8550c7fbcb8"

related:
  - datasource
  - resource-compliance
  - resource-pool
  - request

tool_list_name: "smartcmp_list_all_resource"
tool_list_description: "List SmartCMP resources or virtual machines from the standalone CMP UI list endpoint and show each item's current status. Use `scope=all_resources` for 查看所有资源 and `scope=virtual_machines` for 查看所有云主机. `query_value` is optional."
tool_list_entrypoint: "scripts/list_all_resource.py"
tool_list_groups:
  - cmp
  - datasource
tool_list_capability_class: "provider:smartcmp"
tool_list_priority: 98
tool_list_result_mode: "tool_only_ok"
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
tool_detail_description: "Refresh and summarize one SmartCMP cloud host by resource ID using `PATCH /nodes/{id}/refresh-status`. Use this for 查看云主机详情 or 分析云主机属性."
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
tool_power_name: "smartcmp_operate_resource"
tool_power_description: "Start or stop existing SmartCMP cloud resources through `POST /nodes/resource-operations`. RULES: (1) NEVER claim an operation was submitted without actually calling this tool — fabricating results is strictly forbidden. (2) Before calling, confirm the action with the user (e.g. '确认要关机 my-linux-vm 吗？'). (3) Always pass real SmartCMP resource UUIDs in resource_ids, not display names or list indexes. (4) After success, keep the user response short; do not print raw request or response details."
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
        "description": "One or more SmartCMP resource IDs. Separate multiple IDs with spaces: 'id1 id2 id3'."
      },
      "action": {
        "type": "string",
        "enum": ["start", "stop"],
        "description": "Power action to perform on the target resource IDs."
      }
    },
    "required": ["resource_ids", "action"]
  }
---

# resource

Browse SmartCMP resources, inspect cloud host details, and perform power operations (start/stop).

## Purpose

Provide one skill for resource browsing, per-host property inspection, and day2 power operations.

- Query `/nodes/search` for all-resource or virtual-machine lists
- Show each listed item's current status so users can decide whether to start or stop it
- Call `PATCH /nodes/{id}/refresh-status` for one cloud host detail snapshot
- Present cloud-host detail in a compact CMP-style layout instead of dumping raw metadata
- Use `POST /nodes/resource-operations` for immediate start/stop power actions

## Scope Rules

- Use `smartcmp_list_all_resource` when the user asks for 云资源 or 云主机 lists.
- Use `smartcmp_resource_detail` when the user asks for one cloud host detail or property analysis by resource ID.
- Use `smartcmp_operate_resource` when the user wants to start or stop an existing cloud resource.
- Treat "我的" and "所有" the same for now because the provided UI URLs do not expose a separate owner-only filter; rely on SmartCMP access control and the current user's visible scope.

## Critical Rules

- Do not switch to resource-compliance analysis unless the user explicitly asks for compliance, supportability, lifecycle, or security risk.
- Do not use the list endpoint when the user already provided a concrete resource ID for host detail analysis.
- `smartcmp_resource_detail` uses `PATCH /nodes/{id}/refresh-status` to fetch the latest host state. This may trigger a backend refresh in SmartCMP.
- Keep list-mode output to a numbered list of resource names plus current status.
- For host detail, present only grouped key facts. Do not dump raw properties, top-level keys, source endpoints, or every key/value returned by the API.
- **NEVER claim a power operation was submitted or succeeded without actually calling `smartcmp_operate_resource`.** You must call the tool and receive a real response before telling the user the operation is done.
- **Before calling the power tool, confirm with the user:** show the target resource name + action, ask "确认要执行吗？", and STOP. Only call the tool after user confirms.
- After a power operation succeeds, respond with only the action, resource ID(s), submitted status, message, and verification hint. Do not print raw request payloads or raw response details.
- Resolve every target to a concrete SmartCMP resource UUID before calling `smartcmp_operate_resource`.
- When the user only provides a resource name, first use `smartcmp_list_all_resource` to find the resource and map the chosen item to its `id`.
- Use the visible resource status from the list output to avoid redundant actions. If a resource is already `started` and the user asks to start it again, explain that no power change is needed.
- Do not guess between multiple resources that share the same display name. Ask the user to pick the correct one.
- Do not use this skill for provisioning or deleting resources.

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
| `scripts/resource_detail.py` | Refresh one cloud host and emit a compact grouped detail summary |
| `scripts/operate_resource.py` | Submit SmartCMP start/stop operations for one or more resource IDs |
