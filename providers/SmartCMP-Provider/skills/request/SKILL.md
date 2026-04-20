---
name: "request"
description: "Self-service request skill. Request cloud resources, application environments, or ticket/work order services. Keywords: request, provision, deploy, create VM, apply resources, submit ticket, 申请资源, 创建虚拟机, 提交工单."
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
  - 申请工单
  - 申请机房
  - 申请服务
  - 提工单
  - 报工单
  - 问题工单
  - 事件工单
  - 申请云主机
  - 申请linux
  - 申请windows

use_when:
  - User wants to request a VM, cloud resource, database, or application environment
  - User wants to submit a self-service request through the service catalog
  - User wants to create a ticket or work order
  - User already knows the service they want and is ready to provide request parameters

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
tool_list_services_description: "List available service catalogs from SmartCMP. Call this tool ONLY ONCE at the beginning of the workflow. If you already have a catalogId from a previous call, do NOT call this tool again — proceed directly to building the request body and calling smartcmp_submit_request. After receiving the catalog list, check whether the user's original message clearly matches a specific catalog. If so, auto-select it and proceed without asking. Otherwise show the numbered list. Keep returned _internal metadata for workflow use only; do not show those fields to the user."
tool_list_services_entrypoint: "../shared/scripts/list_services.py"
tool_list_services_group: "cmp"
tool_list_services_capability_class: "provider:smartcmp"
tool_list_services_priority: 100
tool_list_services_parameters: |
  {
    "type": "object",
    "properties": {
      "keyword": {
        "type": "string",
        "description": "Optional keyword to filter services"
      }
    }
  }
tool_submit_name: "smartcmp_submit_request"
tool_submit_description: "Submit resource request to SmartCMP. RULES: (1) NEVER claim submitted without calling this tool. (2) Show JSON preview and wait for user confirmation BEFORE calling. (3) json_body is REQUIRED. (4) catalogId MUST be UUID from catalog metadata id field. See Field Placement table in skill body for exact structure rules."
tool_submit_entrypoint: "scripts/submit.py"
tool_submit_groups:
  - cmp
  - request
tool_submit_capability_class: "provider:smartcmp"
tool_submit_priority: 160
tool_submit_result_mode: "tool_only_ok"
tool_submit_cli_positional: []
tool_submit_cli_flag_overrides:
  json_body: "--json"
tool_submit_parameters: |
  {
    "type": "object",
    "properties": {
      "json_body": {
        "type": "string",
        "description": "REQUIRED. The complete request JSON as a string. For cloud: include catalogId, catalogName, userLoginId, businessGroupName, name, and resourceSpecs array [{node, type, cpu, memory, ...}]. For tickets: include catalogId, catalogName, userLoginId, businessGroupName, name, and genericRequest {description}. FORBIDDEN fields: never add priority, category, requestor, parameters, impactScope, urgency, contactName, or any field not listed above. DO NOT omit this parameter."
      }
    },
    "required": ["json_body"]
  }
---

# request

Submit cloud resource, application environment, or ticket/work order requests through the service catalog.

## Flow (3 turns max)

Only two tools exist: `smartcmp_list_services` and `smartcmp_submit_request`.

1. **Turn 1:** Call `smartcmp_list_services` → auto-select catalog → tell user what was selected
2. **Turn 2:** Build request body from catalog defaults + user specs → show JSON preview → ask confirmation
3. **Turn 3:** User confirms → call `smartcmp_submit_request`

## Service Selection

1. Call `smartcmp_list_services` (ONCE only, never again after getting catalogId).
2. **Auto-select when intent is clear:**
   - "linux" / "Linux VM" / "云主机" → select catalog named "Linux VM"
   - "windows" / "Windows VM" → select "Windows VM"
   - "工单" / "ticket" / "问题" → select `serviceCategory: "GENERIC_SERVICE"`
   - "k8s" / "容器" → select "App on Kubernetes"
   - "机房" → select "机房"
   - Ambiguous → show numbered list and ask
3. **When auto-selecting:** Output brief confirmation like "已为您自动选择 Linux VM" and STOP.

## Field Placement (MUST follow)

Use the EXACT parameter keys from catalog metadata. Do NOT rename, merge, or invent field names.

| Field | Location | Value Source |
|-------|----------|-------------|
| `catalogId` | **top-level** | catalog metadata `id` field (**MUST be UUID**, never sourceKey) |
| `catalogName` | **top-level** | catalog metadata `name` field |
| `businessGroupName` | **top-level** | params `defaultValue` |
| `userLoginId` | **top-level** | params `defaultValue` |
| `name` | **top-level** | user input or auto-generate `vm-<timestamp>` |
| `resourceBundleName` | **top-level** | params `defaultValue` |
| `node` | resourceSpecs | `instructions.node` (e.g. `"Compute"`) |
| `type` | resourceSpecs | `instructions.type` (e.g. `"cloudchef.nodes.Compute"`) |
| `computeProfileName` | resourceSpecs | params `defaultValue` |
| `cpu` | resourceSpecs | user input or params `defaultValue` |
| `memory` | resourceSpecs | user input or params `defaultValue`. **MUST be integer GB, NEVER convert to MB** (e.g. "8g" → `8`, NOT `8192`) |
| `logicTemplateName` | resourceSpecs | params `defaultValue` (OS template name) |
| `templateId` | resourceSpecs | params `defaultValue` (image ID, e.g. `"vm-531"`) |
| `credentialUser` | resourceSpecs | user input or params `defaultValue` |
| `credentialPassword` | resourceSpecs | user input (ask if no default) |
| `networkId` | resourceSpecs | params `defaultValue` |
| `systemDisk` | resourceSpecs | **nested object** `{"size": N}` |

**FORBIDDEN inside resourceSpecs:** `name`, `businessGroupName`, `resourceBundleName`
**FORBIDDEN top-level:** `description`, `serviceCategory`, `priority`, `category`, `requestor`, `parameters`

## Correct Example (vSphere Linux VM)

> catalogId MUST be a UUID like `a1b2c3d4-...`, taken from catalog metadata `id` field.
> NEVER use sourceKey like `BUILD-IN-CATALOG-LINUX-VM` as catalogId.

```json
{
  "catalogId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "catalogName": "Linux VM",
  "businessGroupName": "我的业务组",
  "userLoginId": "admin",
  "name": "my-linux-vm",
  "resourceBundleName": "Vsphere资源池",
  "resourceSpecs": [
    {
      "node": "Compute",
      "type": "cloudchef.nodes.Compute",
      "computeProfileName": "微型计算",
      "cpu": 2,
      "memory": 4,
      "logicTemplateName": "CentOS",
      "templateId": "vm-551",
      "credentialUser": "root",
      "credentialPassword": "P@ssw0rd",
      "networkId": "network-18963",
      "systemDisk": { "size": 50 }
    }
  ]
}
```

## WRONG — Common Mistakes (DO NOT follow)

**Wrong 1: catalogId uses sourceKey instead of UUID**
```json
{ "catalogId": "BUILD-IN-CATALOG-LINUX-VM" }
```
Must be: `"catalogId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"`

**Wrong 2: fields flattened to top-level**
```json
{ "catalogName": "Linux VM", "cpu": 1, "memory": 1, "computeProfileName": "test" }
```
`cpu`, `memory`, `computeProfileName` MUST be inside `resourceSpecs[]`.

**Wrong 3: top-level fields duplicated inside resourceSpecs**
```json
{ "resourceSpecs": [{ "name": "vm1", "businessGroupName": "ABI", "resourceBundleName": "pool" }] }
```
`name`, `businessGroupName`, `resourceBundleName` belong at top-level ONLY.

**Wrong 4: systemDisk uses dot notation**
```json
{ "resourceSpecs": [{ "systemDisk.size": 50 }] }
```
Must be: `"systemDisk": { "size": 50 }`

**Wrong 5: field names renamed or merged**
```json
{ "resourceSpecs": [{ "logicTemplateId": "vm-531" }] }
```
Use EXACT keys from catalog metadata: `"logicTemplateName"` + `"templateId"` (two separate fields).

**Wrong 6: memory converted to MB**
```json
{ "resourceSpecs": [{ "cpu": 4, "memory": 8192 }] }
```
User said "8g" → must be `"memory": 8` (raw GB integer), NOT 8192.

## Parameter Resolution (No Lookup Tools)

Resolve ALL parameters from `instructions.parameters` without calling lookup tools:

| # | Condition | Action |
|---|-----------|--------|
| 1 | User specifies value (e.g. "2c4g" → cpu=2, memory=4) | Use user value |
| 2 | Parameter has non-empty `defaultValue` | Use default silently |
| 3 | `name` not provided | Generate or ask user |
| 4 | `credentialUser/Password` required, no default | Ask user |
| 5 | Everything else, no default | Omit from request body |

**Spec parsing:** "2c4g" → cpu=2, memory=4. "4c8g" → cpu=4, memory=8. "8核16G" → cpu=8, memory=16. **memory value is ALWAYS the raw GB integer. NEVER multiply by 1024.** `memory: 8` is correct, `memory: 8192` is WRONG.

## Ticket / Work Order Rules

When `serviceCategory` is `"GENERIC_SERVICE"`:
- top level: `catalogId`, `catalogName`, `userLoginId`, `businessGroupName`, `name`
- nested: `genericRequest` with only `description` field
- Do NOT add `impactScope`, `expectedResolutionTime`, `priority`, `urgency`, `contactName`,
  `contactPhone`, `email` or any other invented fields. Put extra info in `description` text.

## Submit Contract

### Step 1: Show preview

1. Short Chinese summary of request
2. `JSON 预览` heading with fenced json block
3. Mask `credentialPassword` as `"******"`
4. Ask `请确认以上信息是否正确？（是/否）`
5. **STOP — do NOT call submit yet**

### Step 2: After confirmation

- User says yes → immediately call `smartcmp_submit_request` with `json_body`
- User says no → ask what to change

## Interaction Rules

- `smartcmp_list_services` at most ONCE per conversation.
- ONE tool call per turn. After any tool call, STOP and respond.
- When auto-selecting, do NOT echo raw tool output.
- Never claim submitted unless `smartcmp_submit_request` actually executed.
- Never display raw `_internal` metadata to user.