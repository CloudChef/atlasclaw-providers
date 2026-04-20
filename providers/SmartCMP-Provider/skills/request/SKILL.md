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
  - 申请机房
  - 申请服务

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
tool_list_services_description: "List available service catalogs from SmartCMP. After receiving the catalog list, check whether the user's original message clearly matches a specific catalog. If so, auto-select it and proceed without asking. Otherwise show the numbered list. Keep returned _internal metadata for workflow use only; do not show those fields to the user."
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
tool_submit_description: "Submit resource request to SmartCMP. CRITICAL RULES: (1) NEVER claim a request was submitted or succeeded without actually calling this tool — fabricating submission results is strictly forbidden. (2) Before calling this tool, show the user a JSON preview and wait for confirmation. (3) The json_body parameter is REQUIRED — without it the tool WILL fail. (4) For tickets, json_body MUST follow this exact structure: {catalogId, catalogName, userLoginId, businessGroupName, name, genericRequest:{description}}. For cloud, use: {catalogId, catalogName, userLoginId, businessGroupName, name, resourceSpecs:[{node, type, cpu, memory, ...}]}. (5) FORBIDDEN top-level fields: description, serviceCategory, priority, category, requestor, parameters — never add these."
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
Never call any other tool during the request workflow.

1. **Turn 1:** Call `smartcmp_list_services` → auto-select catalog → tell user what was selected
2. **Turn 2:** Build complete request body using catalog defaults + user specs → show JSON
   preview → ask for confirmation
3. **Turn 3:** User confirms → call `smartcmp_submit_request`

## Service Selection

1. Call `smartcmp_list_services`.
2. **Auto-select when user intent is clear:** After receiving the catalog list, check whether
   the user's original message clearly indicates a specific service type:
   - User mentions "linux" / "Linux VM" / "linux云主机" / "云主机" (without "windows") →
     auto-select the catalog whose name contains "Linux VM" (not "Linux VM - 复制").
   - User mentions "windows" / "Windows VM" / "windows云主机" → auto-select "Windows VM".
   - User mentions "工单" / "ticket" / "问题" → auto-select the catalog whose
     `serviceCategory` is `"GENERIC_SERVICE"` (e.g. "问题工单").
   - User mentions "k8s" / "kubernetes" / "容器" → auto-select "App on Kubernetes".
   - User mentions "机房" → auto-select "机房".
   - User says only "申请云资源" / "申请资源" without specifying OS type → ambiguous, show the
     full list and ask.
   - **When auto-selecting: DO NOT show the raw catalog list.** Output a brief confirmation
     like "已为您自动选择 Linux VM，正在为您构建申请参数..." and STOP this turn.
   - If the intent is ambiguous or matches multiple catalogs, show the full numbered list and
     ask for selection.
3. After the catalog is selected, proceed to Parameter Resolution.

## Cloud Request Rules

For cloud requests, the selected catalog metadata from `smartcmp_list_services` is the source
of truth:

- selected catalog `id` -> `catalogId`
- selected catalog `name` -> `catalogName`
- `instructions.node` -> request `node`
- `instructions.type` -> request `type`
- `instructions.parameters` or `params` -> ordered request parameter list

### Parameter Resolution (No Lookup Tools)

After selecting a catalog, resolve ALL parameters directly from `instructions.parameters`
without calling any lookup tools. For each parameter, apply this rule:

| # | Condition | Action |
|---|-----------|--------|
| 1 | User's message specifies this value (e.g. "2c4g" → cpu=2, memory=4) | Use user value |
| 2 | Parameter has a non-empty `defaultValue` | Use the default silently |
| 3 | Parameter is `name` (resource name) AND not provided | Generate a reasonable name like `vm-<timestamp>` or ask user |
| 4 | Parameter is `credentialUsername` or `credentialPassword` AND required AND no default | Ask user for these |
| 5 | Everything else with empty default | Omit from request body, or use empty string |

**Spec parsing rules:**
- The `memory` parameter unit in SmartCMP is **GB** (not MB). Always use the GB number directly.
- "2c4g" → cpu=2, memory=4
- "4c8g" → cpu=4, memory=8
- "8核16G" → cpu=8, memory=16
- Do NOT convert to MB. The API expects the integer GB value as-is.

**Key principle:** Never call lookup tools for business groups, resource pools, OS templates,
or images. Use `defaultValue` from the catalog's `instructions.parameters` for all of these.
If a parameter has `source: "list:xxx"` but also has a `defaultValue`, use the default.
If a parameter has `source: "list:xxx"` but NO `defaultValue`, omit it from the request body.

### What to ask the user (at most)

Only ask the user if ALL of these are true:
- The parameter is required
- The parameter has no defaultValue
- The user's original message does not contain the answer

In practice, you should ask at most for:
- Resource name (`name`) — if not derivable from context
- Credentials (`credentialUsername`, `credentialPassword`) — if required and no defaults

Combine all questions into a single message. Do not ask one at a time.

## Ticket / Work Order Rules

When the selected catalog is a generic or problem-service request, collect only the fields
required by that catalog metadata. Do not reuse cloud-only fields such as `resourceSpecs`,
`node`, or `type` unless the selected catalog metadata explicitly requires them.

For ticket requests, ask only for:
- `description` — the user's problem description (can derive from their original message)
- `name` — request name (can auto-generate)

## Submit Contract

The submit tool accepts `json_body`.

### Step 1: Show preview and ask for confirmation

1. Show a short Chinese summary of the request.
2. Show a heading `JSON 预览`.
3. Show a fenced `json` block with the exact request body that will be submitted.
4. Mask sensitive values such as `credentialPassword` as `"******"` in the preview.
5. Ask `请确认以上信息是否正确？（是/否）`.
6. **STOP and wait for the user's answer. Do NOT call `smartcmp_submit_request` yet.**

### Step 2: After user confirms

When the user replies "是", "yes", "确认", or any affirmative answer:

- **Immediately call `smartcmp_submit_request`** with the constructed `json_body`.
- Do NOT show the summary or JSON preview again.
- Do NOT ask for confirmation again.

When the user replies "否", "no", or any negative answer:

- Ask what they want to change and go back to collecting that parameter.

### Cloud request structure

- top level: `catalogId`, `catalogName`, `userLoginId`, `businessGroupName` or
  `businessGroupId`, `resourceBundleName`, `name`
- nested: `resourceSpecs` **MUST be a JSON array** `[{...}]`, never a plain object.
  `resourceSpecs[0]` contains `node`, `type`, and collected cloud parameters.
  Example: `"resourceSpecs": [{"node": "Compute", "type": "cloudchef.nodes.Compute", ...}]`

### Ticket request structure

- top level: `catalogId`, `catalogName`, `userLoginId`, `businessGroupName` or
  `businessGroupId`, `name`
- nested: `genericRequest` with only `description` field
- **FORBIDDEN**: Do NOT invent or add any fields that are not defined in
  `instructions.parameters` or the examples above. Fields like `impactScope`,
  `expectedResolutionTime`, `additionalRequirements`, `priority`, `category`,
  `urgency`, `contactName`, `contactPhone`, `email` etc. must NOT appear in the
  JSON body unless they are explicitly listed in the catalog's
  `instructions.parameters`. If a user mentions extra info (e.g. urgency,
  timeline), include it naturally in the `description` text instead of
  fabricating new JSON fields.

## Interaction Rules

- **Execute only one tool call per turn.** After calling any tool, stop and generate your
  response. Do NOT chain multiple tool calls in a single turn.
- **When auto-selecting a catalog:** Do NOT echo or repeat the raw tool output. Write your
  own brief confirmation message and STOP.
- If the user provides all needed info upfront (e.g. "申请2c4g的linux云主机"), you should
  be able to complete the request in 3 turns: select catalog → show preview → submit.
- After the user confirms the JSON preview, immediately call `smartcmp_submit_request`.
- Never claim a request was submitted unless `smartcmp_submit_request` actually executed.
- Never display raw `_internal` metadata or hidden JSON to the user.


