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
tool_submit_name: "smartcmp_submit_request"
tool_submit_description: "Submit resource request to SmartCMP."
tool_submit_entrypoint: "scripts/submit.py"
---

# SmartCMP Request Skill

Submit cloud resource provisioning or ticket/work order requests through SmartCMP platform.

## When to use this skill

- User wants to provision cloud resources (VM, container, etc.)
- User wants to create a ticket or work order
- Keywords: "申请资源", "创建虚拟机", "部署应用", "提交工单", "create VM", "deploy", "provision"

## Quick start

**Step 1:** Run `list_services.py` to show available services  
**Step 2:** User selects a service  
**Step 3:** Check `serviceCategory` in output to determine flow:
- `GENERIC_SERVICE` → Ticket flow
- Others → Cloud resource flow

---

## Workflow

### Step 1: List available services

```bash
python ../shared/scripts/list_services.py
```

**Output format:**
```
Found N published catalog(s):

  [1] Linux VM
  [2] 问题工单

##CATALOG_META_START##
[{"index":1,"id":"xxx","name":"Linux VM","sourceKey":"resource.iaas...","serviceCategory":"VM","description":"..."},
 {"index":2,"id":"yyy","name":"问题工单","sourceKey":"...","serviceCategory":"GENERIC_SERVICE","description":"..."}]
##CATALOG_META_END##
```

**Action:** Show numbered list to user. Ask: "请选择您要申请的服务（输入编号）"

**STOP and wait for user selection.**

---

### Step 2: Determine service type

After user selects (e.g., "1" or "问题工单"):

1. Find the selected item in `##CATALOG_META##`
2. Check `serviceCategory` field:

| serviceCategory | Type | Go to |
|-----------------|------|-------|
| `GENERIC_SERVICE` | Ticket/Work Order | [Ticket Flow](#ticket-flow-generic_service) |
| Others | Cloud Resource | [Cloud Resource Flow](#cloud-resource-flow) |

---

## Ticket Flow (GENERIC_SERVICE)

Use this flow when `serviceCategory === "GENERIC_SERVICE"`.

### T1: Get business groups

```bash
python ../shared/scripts/list_business_groups.py <catalogId>
```

**Action:** Show list to user. Ask: "请选择业务组"

**STOP and wait.**

### T2: Collect ticket info

Ask user:
```
请提供以下信息：
1. 工单名称：
2. 工单描述：
```

**STOP and wait.**

### T3: Build request body

```json
{
    "catalogName": "<name from CATALOG_META>",
    "userId": "<current user ID from session>",
    "businessGroupId": "<from T1 selection>",
    "name": "<from T2 user input>",
    "manualRequest": {
        "description": "<from T2 user input>"
    }
}
```

**Action:** Show summary to user. Ask: "请确认以上信息是否正确？(yes/no)"

**STOP and wait for confirmation.**

### T4: Submit

```bash
python scripts/submit.py --file request.json
```

**Done.** Show request ID and status to user.

---

## Cloud Resource Flow

Use this flow when `serviceCategory` is NOT `GENERIC_SERVICE`.

### R1: Get component type (silent)

```bash
python ../shared/scripts/list_components.py <sourceKey>
```

Parse output silently. Record:
- `typeName` (e.g., `cloudchef.nodes.Compute`)
- `osType` (Linux or Windows)

**Do NOT show to user. Continue immediately.**

### R2: Parse service card description

The `description` field in `##CATALOG_META##` contains a JSON with parameter definitions:

```json
{
  "parameters": [
    {"key": "businessGroupId", "source": "list:business_groups", "defaultValue": null, "required": true},
    {"key": "cpu", "source": null, "defaultValue": 2, "required": true},
    {"key": "name", "source": null, "defaultValue": null, "required": true}
  ]
}
```

**For each parameter:**

| Condition | Action |
|-----------|--------|
| `defaultValue` is set | Use it. DO NOT ask user. |
| `source: "list:business_groups"` | Run `list_business_groups.py` → Ask user to select |
| `source: "list:resource_pools"` | Run `list_resource_pools.py` → Ask user to select |
| `source: "list:os_templates"` | Run `list_os_templates.py` → Ask user to select |
| `source: null` AND `required: true` | Ask user to input |
| `source: null` AND `required: false` | Skip (optional) |

### R3: Collect parameters step by step

**R3a: Business group** (if needed)
```bash
python ../shared/scripts/list_business_groups.py <catalogId>
```
Show list. Ask user. **STOP.**

**R3b: Resource pool** (if needed)
```bash
python ../shared/scripts/list_resource_pools.py <businessGroupId> <sourceKey> <nodeType>
```
Show list. Ask user. **STOP.**

**R3c: OS template** (if needed)
```bash
python ../shared/scripts/list_os_templates.py <osType> <resourceBundleId>
```
Show list. Ask user. **STOP.**

**R3d: Other required fields**
Ask user for remaining required fields (name, etc.). **STOP.**

### R4: Build request body

```json
{
  "name": "<user input>",
  "catalogName": "<from CATALOG_META>",
  "businessGroupName": "<from R3a>",
  "userLoginId": "admin",
  "resourceBundleName": "<from R3b>",
  "resourceSpecs": [
    {
      "type": "<typeName from R1>",
      "node": "Compute",
      "cpu": <from description or user>,
      "memory": <from description or user>,
      "logicTemplateName": "<from R3c>",
      "networkId": "<from description default>"
    }
  ]
}
```

**Action:** Show summary. Ask for confirmation. **STOP.**

### R5: Submit

```bash
python scripts/submit.py --file request.json
```

**Done.** Show request ID and status.

---

## No description handling

If `description` field is empty or invalid JSON:

**Show to user:**
> 该服务「{name}」暂未配置参数说明。
>
> 如果您了解该服务的参数要求，可以直接告诉我。否则请联系管理员配置服务卡片的 instructions 字段。

**Do NOT proceed without user guidance.**

---

## Scripts reference

| Script | Purpose | Arguments |
|--------|---------|-----------|
| `../shared/scripts/list_services.py` | List service catalogs | `[keyword]` |
| `../shared/scripts/list_business_groups.py` | List business groups | `<catalogId>` |
| `../shared/scripts/list_resource_pools.py` | List resource pools | `<bgId> <sourceKey> <nodeType>` |
| `../shared/scripts/list_os_templates.py` | List OS templates | `<osType> <resourceBundleId>` |
| `../shared/scripts/list_components.py` | Get component type | `<sourceKey>` |
| `scripts/submit.py` | Submit request | `--file <json_file>` |

---

## Critical rules

1. **ONE action per turn.** After showing output or asking a question, STOP and wait.
2. **NEVER make up data.** Only use values from script outputs or user inputs.
3. **NEVER skip steps.** Follow the workflow exactly.
4. **NEVER create temp files.** Parse script output directly from stdout.
5. **NEVER auto-send.** Always confirm with user before submitting.

---

## PowerShell Environment Notes

> **IMPORTANT:** PowerShell has encoding and parameter passing quirks that can cause request failures.

### Problem 1: UTF-8 BOM in JSON Files

PowerShell's `Out-File` and `>` operators add a UTF-8 BOM (Byte Order Mark) by default, which causes JSON parsing errors:

```
[ERROR] Invalid JSON: Unexpected UTF-8 BOM (decode using utf-8-sig): line 1 column 1 (char 0)
```

**Solution:** Use Python to write JSON files (BOM-free):

```powershell
# [WRONG] PowerShell adds BOM
$body | ConvertTo-Json | Out-File -FilePath request.json -Encoding utf8

# [OK] Use Python to write JSON
python -c "import json; data = {'catalogName': '...', ...}; open('request.json', 'w', encoding='utf-8').write(json.dumps(data, ensure_ascii=False, indent=2))"
```

### Problem 2: Complex JSON in Command Line

PowerShell mangles JSON strings with special characters when passed via `-j` argument.

**Solution:** Always use `--file` argument with `submit.py`:

```powershell
# [WRONG] JSON gets corrupted
python submit.py --json '{"name": "test", "description": "special chars"}'

# [OK] Use file input
python submit.py --file request.json
```

### Problem 3: Environment Variable Encoding

Chinese characters in environment variables may cause issues.

**Solution:** Set UTF-8 output encoding before running scripts:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:CMP_URL = "https://console.smartcmp.cloud"
```

### Best Practice: Complete PowerShell Workflow

```powershell
# 1. Set encoding
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 2. Set environment
$env:CMP_URL = "https://console.smartcmp.cloud"
$env:CMP_USERNAME = "user@example.com"
$env:CMP_PASSWORD = "password"

# 3. Use Python to create JSON file (avoids BOM)
python -c "import json; data = {
    'catalogName': '问题工单',
    'userId': 'afe5251b-1d72-49ce-babe-5b8563b7b947',
    'businessGroupId': 'f3ecaf5f-d86c-46fc-89d4-3636a169d5d5',
    'name': '工单名称',
    'manualRequest': {'description': '工单描述'}
}; open('request.json', 'w', encoding='utf-8').write(json.dumps(data, ensure_ascii=False, indent=2))"

# 4. Submit using file
python scripts/submit.py --file request.json
```

---

## References

- [WORKFLOW.md](references/WORKFLOW.md) — Detailed step-by-step workflow
- [PARAMS.md](references/PARAMS.md) — Parameter placement rules  
- [EXAMPLES.md](references/EXAMPLES.md) — Request body examples
