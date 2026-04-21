---
name: "resource"
description: "Standalone SmartCMP resource browsing and cloud-host detail skill. Use when the user asks to 查看云资源列表、查看云主机列表、查看云主机详情、分析云主机属性. Use `/nodes/search` for list browsing with visible status and `PATCH /nodes/{id}/refresh-status` for one-host detail inspection."
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
  - list resources
  - show resources
  - list virtual machines
  - show virtual machines
  - show vm details

use_when:
  - User wants a standalone list of SmartCMP cloud resources with current status
  - User wants a standalone list of SmartCMP cloud hosts or virtual machines with current status
  - User wants to inspect one cloud host by resource ID and analyze its current properties
  - User wants to search resources or virtual machines by keyword through the CMP UI list endpoint

avoid_when:
  - User wants resource compliance, lifecycle, supportability, or security analysis (use resource-compliance skill)
  - User wants to start or stop an existing cloud resource (use resource-power skill after resolving the resource ID)
  - User wants generic reference data browsing unrelated to resources (use datasource skill)
  - User wants to submit or modify a SmartCMP request (use request skill)

related:
  - datasource
  - resource-compliance
  - resource-power
  - request

tool_list_name: "smartcmp_list_resources"
tool_list_description: "List SmartCMP resources or virtual machines from the standalone CMP UI list endpoint and show each item's current status. Use `scope=all_resources` for 查看所有资源 and `scope=virtual_machines` for 查看所有云主机. `query_value` is optional."
tool_list_entrypoint: "scripts/list_resources.py"
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
tool_detail_name: "smartcmp_analyze_resource_detail"
tool_detail_description: "Refresh and summarize one SmartCMP cloud host by resource ID using `PATCH /nodes/{id}/refresh-status`. Use this for 查看云主机详情 or 分析云主机属性."
tool_detail_entrypoint: "scripts/analyze_resource_detail.py"
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
---

# resource

Browse SmartCMP resources and inspect one cloud host by resource ID.

## Purpose

Provide one skill for both list-style browsing and per-host property inspection.

- Query `/nodes/search` for all-resource or virtual-machine lists
- Show each listed item's current status so users can decide whether to start or stop it
- Call `PATCH /nodes/{id}/refresh-status` for one cloud host detail snapshot
- Present cloud-host detail in a compact CMP-style layout instead of dumping raw metadata

## Scope Rules

- Use `smartcmp_list_resources` when the user asks for 云资源 or 云主机 lists.
- Use `smartcmp_analyze_resource_detail` when the user asks for one cloud host detail or property analysis by resource ID.
- Treat “我的” and “所有” the same for now because the provided UI URLs do not expose a separate owner-only filter; rely on SmartCMP access control and the current user's visible scope.

## Critical Rules

- Do not switch to resource-compliance analysis unless the user explicitly asks for compliance, supportability, lifecycle, or security risk.
- Do not use the list endpoint when the user already provided a concrete resource ID for host detail analysis.
- `smartcmp_analyze_resource_detail` uses `PATCH /nodes/{id}/refresh-status` to fetch the latest host state. This may trigger a backend refresh in SmartCMP.
- Keep list-mode output to a numbered list of resource names plus current status.
- For host detail, present only grouped key facts. Do not dump raw properties, top-level keys, source endpoints, or every key/value returned by the API.

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
| `scripts/list_resources.py` | Call the standalone resource list endpoint and emit a numbered resource directory with visible status |
| `scripts/analyze_resource_detail.py` | Refresh one cloud host and emit a compact grouped detail summary |
