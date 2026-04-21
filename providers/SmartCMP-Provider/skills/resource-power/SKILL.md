---
name: "resource-power"
description: "SmartCMP cloud resource power operation skill. Use when the user asks to 开机、启动、关机、停止 an existing 云资源 or 云主机. Resolve concrete resource IDs first, then call the native `/nodes/resource-operations` endpoint with `operationId=start|stop`."
provider_type: "smartcmp"
instance_required: "true"

triggers:
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
  - start resource
  - stop resource
  - start vm
  - stop vm
  - power on vm
  - power off vm

use_when:
  - User wants to start an existing SmartCMP cloud resource or virtual machine
  - User wants to stop an existing SmartCMP cloud resource or virtual machine
  - User already knows the target resource ID, or can resolve it from the resource list before running the power action

avoid_when:
  - User only wants to browse resources or cloud hosts without taking action (use resource skill)
  - User wants detailed compliance, lifecycle, or security analysis (use resource-compliance skill)
  - User wants to provision a new resource instead of operating an existing one (use request skill)

examples:
  - "把 mysqlLinux2 云资源关机"
  - "启动这台云主机"
  - "Stop resource 3615d791-36b4-4fa1-be61-f8550c7fbcb8"
  - "Power on vm vm-prod-01"

related:
  - resource
  - resource-compliance
  - request

tool_power_name: "smartcmp_operate_resource_power"
tool_power_description: "Start or stop existing SmartCMP cloud resources through `POST /nodes/resource-operations`. RULES: (1) NEVER claim an operation was submitted without actually calling this tool — fabricating results is strictly forbidden. (2) Before calling, confirm the action with the user (e.g. '确认要关机 my-linux-vm 吗？'). (3) Always pass real SmartCMP resource UUIDs in resource_ids, not display names or list indexes."
tool_power_entrypoint: "scripts/operate_resource_power.py"
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

# resource-power

Operate on existing SmartCMP cloud resources or virtual machines by starting or stopping them.

## Purpose

Provide a focused day2 skill for immediate power operations on already-existing resources.

- Use the native `POST /nodes/resource-operations` endpoint
- Support `operationId=start` and `operationId=stop`
- Keep scheduling disabled for immediate execution
- Return a stable structured block after submission so follow-up status checks can reuse it

## Workflow

See [references/WORKFLOW.md](references/WORKFLOW.md) for the supported workflow and safety rules.

## Critical Rules

- **NEVER claim an operation was submitted or succeeded without actually calling `smartcmp_operate_resource_power`.** You must call the tool and receive a real response before telling the user the operation is done.
- **Before calling the tool, confirm with the user:** show the target resource name + action, ask "确认要执行吗？", and STOP. Only call the tool after user confirms.
- Resolve every target to a concrete SmartCMP resource UUID before calling `smartcmp_operate_resource_power`.
- When the user only provides a resource name, first use the `resource` skill to list resources or virtual machines and map the chosen item to its `id`.
- Use the visible resource status from the list output to avoid redundant actions. If a resource is already `started` and the user asks to start it again, explain that no power change is needed unless they explicitly want to retry.
- Do not guess between multiple resources that share the same display name. Ask the user to pick the correct one.
- Do not use this skill for provisioning or deleting resources.

## Script

| Script | Description |
|--------|-------------|
| `scripts/operate_resource_power.py` | Submit SmartCMP start/stop operations for one or more resource IDs |
