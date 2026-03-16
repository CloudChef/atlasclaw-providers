---
name: "request"
description: "SmartCMP resource provisioning and ticket requests. Create VM, provision cloud resources, deploy applications, or submit work orders/tickets. Keywords: request, provision, deploy, create VM, apply resources, submit ticket, 申请资源, 创建虚拟机, 提交工单."
provider_type: "smartcmp"
instance_required: "true"

# === LLM Context Fields ===
triggers:
  - create VM
  - provision resources
  - deploy application
  - request cloud
  - new virtual machine
  - 申请资源
  - 创建虚拟机
  - 提交工单
  - 申请机房
  - 申请服务

use_when:
  - User wants to create or provision cloud resources
  - User wants to deploy a virtual machine or application
  - User needs to submit a resource request to SmartCMP
  - User wants to create a ticket or work order

avoid_when:
  - User only wants to browse available resources (use datasource skill)
  - User wants to approve or reject requests (use approval skill)
  - User describes requirements in natural language without specific parameters (use request-decomposition-agent)

examples:
  - "Create a new VM with 4 CPU and 8GB RAM"
  - "Provision cloud resources for my project"
  - "Deploy a Linux VM in production environment"
  - "Submit a request for 3 virtual machines"
  - "提交一个问题工单"
  - "申请一个机房资源"

related:
  - datasource
  - approval
  - request-decomposition-agent

# === Tool Registration ===
tool_list_services_name: "smartcmp_list_services"
tool_list_services_description: "List available service catalogs from SmartCMP."
tool_list_services_entrypoint: "../shared/scripts/list_services.py"
tool_list_business_groups_name: "smartcmp_list_business_groups"
tool_list_business_groups_description: "List business groups for a catalog. Use when user needs to select business group."
tool_list_business_groups_entrypoint: "../shared/scripts/list_business_groups.py"
tool_list_resource_pools_name: "smartcmp_list_resource_pools"
tool_list_resource_pools_description: "List resource pools. Get resourceBundleId for request."
tool_list_resource_pools_entrypoint: "../shared/scripts/list_resource_pools.py"
tool_list_os_templates_name: "smartcmp_list_os_templates"
tool_list_os_templates_description: "List OS templates for VM provisioning."
tool_list_os_templates_entrypoint: "../shared/scripts/list_os_templates.py"
tool_list_components_name: "smartcmp_list_components"
tool_list_components_description: "Get component type info including typeName, node, cloudEntryTypeIds."
tool_list_components_entrypoint: "../shared/scripts/list_components.py"
tool_submit_name: "smartcmp_submit_request"
tool_submit_description: "Submit resource request to SmartCMP."
tool_submit_entrypoint: "scripts/submit.py"
---

# SmartCMP Request Skill

Submit cloud resource provisioning or ticket/work order requests through SmartCMP platform.

---

## Workflow Overview

```
[触发] 用户表达"申请资源"意图
    |
    v
[Step 1] 执行 list_services.py -> 展示服务列表 -> STOP 等待用户选择
    |
    v
[Step 2] 用户选择服务 -> 检查 serviceCategory 字段
    |
    +---> serviceCategory === "GENERIC_SERVICE" ---> [工单流程]
    |
    +---> serviceCategory !== "GENERIC_SERVICE" ---> [云资源流程]
```

---

## Step 1: List Available Services [执行]

```bash
python ../shared/scripts/list_services.py
```

**输出示例:**
```
Found 3 published catalog(s):

  [1] Linux VM
  [2] 问题工单
  [3] 机房

##CATALOG_META_START##
[{"index":1,"id":"xxx","name":"Linux VM","sourceKey":"resource.iaas...","serviceCategory":"VM","description":"..."},
 {"index":2,"id":"yyy","name":"问题工单","sourceKey":"...","serviceCategory":"GENERIC_SERVICE","description":"..."},
 {"index":3,"id":"zzz","name":"机房","sourceKey":"resource.infra.server_room","serviceCategory":"RESOURCE","description":"..."}]
##CATALOG_META_END##
```

**动作:** 向用户展示编号列表，询问: "请选择您要申请的服务（输入编号）"

**STOP - 等待用户输入**

---

## Step 2: Determine Service Type [判断]

用户选择后，从 `##CATALOG_META##` 中找到对应项，检查 `serviceCategory` 字段:

| serviceCategory 值 | 服务类型 | 跳转流程 |
|-------------------|---------|---------|
| `GENERIC_SERVICE` | 工单/手动请求 | [工单流程](#ticket-flow-generic_service) |
| 其他任意值 | 云资源 | [云资源流程](#cloud-resource-flow) |

---

## Ticket Flow (GENERIC_SERVICE)

当 `serviceCategory === "GENERIC_SERVICE"` 时使用此流程。

### T1: Get Business Groups [执行]

```bash
python ../shared/scripts/list_business_groups.py <catalogId>
```

**动作:** 展示业务组列表，询问: "请选择业务组"

**STOP - 等待用户选择**

### T2: Collect Ticket Info [询问]

向用户询问:
```
请提供以下信息：
1. 工单名称：
2. 工单描述：
```

**STOP - 等待用户输入**

### T3: Build Request Body [构建]

```json
{
    "catalogName": "<name from CATALOG_META>",
    "userLoginId": "<current user login ID>",
    "businessGroupId": "<from T1 selection>",
    "name": "<from T2 user input>",
    "genericRequest": {
        "description": "<from T2 user input>"
    }
}
```

**动作:** 向用户展示确认信息，询问: "请确认以上信息是否正确？(yes/no)"

**STOP - 等待用户确认**

### T4: Submit [执行]

```bash
python scripts/submit.py --file request.json
```

**完成** - 向用户展示请求ID和状态。

---

## Cloud Resource Flow

当 `serviceCategory !== "GENERIC_SERVICE"` 时使用此流程。

### R1: Get Component Info [静默执行]

```bash
python ../shared/scripts/list_components.py <sourceKey>
```

**输出示例:**
```
##COMPONENT_META_START##
{"sourceKey":"resource.infra.server_room","typeName":"resource.infra.server_room","id":"xxx","name":"机房","node":"server_room","cloudEntryTypeIds":""}
##COMPONENT_META_END##
```

**关键字段说明:**

| 字段 | 用途 | 示例值 |
|-----|------|--------|
| `typeName` | 用于请求体中的 `type` 字段 | `resource.infra.server_room` |
| `node` | 用于请求体中的 `node` 字段 | `server_room` |
| `cloudEntryTypeIds` | 若为空字符串，需设置 `useResourceBundle: false` | `""` |

**注意:** 此步骤静默执行，不向用户展示，直接继续下一步。

### R2: Parse Service Card Description [静默分析]

从 `##CATALOG_META##` 中的 `description` 字段解析参数定义:

```json
{
  "parameters": [
    {"key": "businessGroupId", "source": "list:business_groups", "defaultValue": null, "required": true},
    {"key": "infra_brand", "source": null, "defaultValue": null, "required": true},
    {"key": "maintenance_phone_number", "source": null, "defaultValue": null, "required": false}
  ]
}
```

**参数处理规则:**

| 条件 | 动作 |
|------|------|
| `defaultValue` 有值 | 使用默认值，不询问用户 |
| `source: "list:business_groups"` | 执行 `list_business_groups.py` -> 询问用户选择 |
| `source: "list:resource_pools"` | 执行 `list_resource_pools.py` -> 询问用户选择 |
| `source: "list:os_templates"` | 执行 `list_os_templates.py` -> 询问用户选择 |
| `source: null` 且 `required: true` | 询问用户输入 |
| `source: null` 且 `required: false` | 跳过（可选参数） |

### R3: Collect Parameters Step by Step

根据 R2 分析结果，逐步收集参数:

**R3a: Business Group** (如需要)
```bash
python ../shared/scripts/list_business_groups.py <catalogId>
```
展示列表，询问用户选择。**STOP**

**R3b: Resource Pool** (如需要)
```bash
python ../shared/scripts/list_resource_pools.py <businessGroupId> <sourceKey> <typeName>
```
展示列表，询问用户选择。**STOP**

**R3c: OS Template** (如需要)
```bash
python ../shared/scripts/list_os_templates.py <osType> <resourceBundleId>
```
展示列表，询问用户选择。**STOP**

**R3d: Other Required Fields**
询问用户输入剩余必填字段。**STOP**

### R4: Build Request Body [构建]

**核心规则 (非常重要):**

1. `type` = 完整的 `typeName` (来自 R1)
2. `node` = `typeName` 最后一个点号后的部分 (来自 R1 的 `node` 字段)
3. 若 `cloudEntryTypeIds` 为空字符串 -> 添加 `"useResourceBundle": false`

**请求体示例:**

```json
{
    "catalogName": "机房",
    "userLoginId": "admin",
    "businessGroupName": "我的业务组",
    "name": "机房222",
    "resourceSpecs": [
        {
            "useResourceBundle": false,
            "node": "server_room",
            "type": "resource.infra.server_room",
            "params": {
                "infra_brand": "111",
                "maintenance_phone_number": "232323"
            }
        }
    ]
}
```

**字段对应关系:**

| 请求体字段 | 数据来源 |
|-----------|---------|
| `catalogName` | CATALOG_META 中的 `name` |
| `userLoginId` | 当前用户登录ID |
| `businessGroupName` | R3a 用户选择的业务组名称 |
| `name` | R3d 用户输入的资源名称 |
| `resourceSpecs[0].type` | R1 输出的 `typeName` |
| `resourceSpecs[0].node` | R1 输出的 `node` |
| `resourceSpecs[0].useResourceBundle` | 若 `cloudEntryTypeIds` 为空则设为 `false` |
| `resourceSpecs[0].params` | R3d 收集的其他参数 |

**动作:** 向用户展示确认信息，询问: "请确认以上信息是否正确？(yes/no)"

**STOP - 等待用户确认**

### R5: Submit [执行]

```bash
python scripts/submit.py --file request.json
```

**完成** - 向用户展示请求ID和状态。

---

## No Description Handling

如果 `description` 字段为空或无效 JSON:

> 该服务「{name}」暂未配置参数说明。
>
> 如果您了解该服务的参数要求，可以直接告诉我。否则请联系管理员配置服务卡片的 instructions 字段。

**不要继续执行，等待用户指导。**

---

## Scripts Reference

| 脚本 | 用途 | 参数 |
|-----|------|------|
| `../shared/scripts/list_services.py` | 列出服务目录 | `[keyword]` |
| `../shared/scripts/list_business_groups.py` | 列出业务组 | `<catalogId>` |
| `../shared/scripts/list_resource_pools.py` | 列出资源池 | `<bgId> <sourceKey> <nodeType>` |
| `../shared/scripts/list_os_templates.py` | 列出操作系统模板 | `<osType> <resourceBundleId>` |
| `../shared/scripts/list_components.py` | 获取组件类型信息 | `<sourceKey>` |
| `scripts/submit.py` | 提交请求 | `--file <json_file>` |

---

## Critical Rules

1. **每轮只执行一个动作。** 展示输出或提问后，必须 STOP 等待用户响应。
2. **绝不编造数据。** 只使用脚本输出或用户输入的值。
3. **绝不跳过步骤。** 严格按照工作流执行。
4. **绝不自动提交。** 提交前必须获得用户确认。
5. **正确设置 node 和 type。** `type` = 完整 typeName，`node` = typeName 最后一段。
6. **检查 cloudEntryTypeIds。** 为空时必须添加 `useResourceBundle: false`。

---

## PowerShell Environment Notes

> **重要:** PowerShell 的编码和参数传递可能导致请求失败。

### 使用 Python 写入 JSON 文件 (避免 BOM)

```powershell
# [错误] PowerShell 会添加 BOM
$body | ConvertTo-Json | Out-File -FilePath request.json -Encoding utf8

# [正确] 使用 Python 写入 JSON
python -c "import json; data = {...}; open('request.json', 'w', encoding='utf-8').write(json.dumps(data, ensure_ascii=False, indent=2))"
```

### 始终使用 --file 参数

```powershell
# [错误] JSON 会被破坏
python submit.py --json '{"name": "test"}'

# [正确] 使用文件输入
python submit.py --file request.json
```

---

## References

- [WORKFLOW.md](references/WORKFLOW.md) - 详细步骤工作流
- [PARAMS.md](references/PARAMS.md) - 参数放置规则
- [EXAMPLES.md](references/EXAMPLES.md) - 请求体示例
