---
name: "request"
description: "Self-service request skill. Request cloud resources, application environments, or ticket/work order services. Keywords: request, provision, deploy, create VM, apply resources, submit ticket, 申请资源, 创建虚拟机, 提交工单."
provider_type: "smartcmp"
instance_required: "true"
workflow_role: "request_parent"

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
  - "Create a new VM with 2c4g"
  - "Provision cloud resources for my project"
  - "Deploy a Linux VM in production environment"
  - "Submit a request for 3 virtual machines"
  - "提交一个问题工单"
  - "申请一个机房资源"
  - "申请2c4g的linux云主机"

related:
  - datasource
  - approval
  - request-decomposition-agent

# === Tool Registration ===
tool_list_services_name: "smartcmp_list_services"
tool_list_services_description: "List available service catalogs from SmartCMP. Call this tool ONLY ONCE at the beginning of the workflow. If you already have a catalogId from a previous call, do NOT call this tool again — proceed directly to building the request body and calling smartcmp_submit_request. After receiving the catalog list, check whether the user's original message clearly matches a specific catalog. If so, auto-select it and proceed without asking. Otherwise show the numbered list. Keep returned _internal metadata for workflow use only; do not show those fields to the user."
tool_list_services_entrypoint: "../datasource/scripts/list_services.py"
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
        "description": "REQUIRED. The complete request JSON as a string. For cloud: include catalogId, catalogName, business group field (key from params), name, resourceBundleName or resourceBundleTags (in resourceSpecs), and resourceSpecs array. For tickets: include catalogId, catalogName, business group field, name, and genericRequest {description}. Do NOT include userLoginId (auto-injected by script). FORBIDDEN fields: never add priority, category, requestor, parameters, impactScope, urgency, contactName, or any field not listed above. All field keys and values MUST come from instructions.parameters, not hardcoded. DO NOT omit this parameter."
      }
    },
    "required": ["json_body"]
  }
tool_submit_success_contract:
  type: "identifier_presence"
  fields:
    - "id"
    - "requestId"
    - "request_id"
    - "workflowId"
    - "workflow_id"
  text_labels:
    - "Request ID"
    - "Workflow ID"
tool_facets_name: "smartcmp_list_facets"
tool_facets_description: "List available resource bundle tag facets from SmartCMP. REQUIRES businessGroupId — call this AFTER business group is selected. Returns facet definitions with keys and selectable options. Use the returned facet key and option key (NOT display names) to build resourceBundleTags values."
tool_facets_entrypoint: "scripts/list_facets.py"
tool_facets_group: "cmp"
tool_facets_capability_class: "provider:smartcmp"
tool_facets_priority: 110
tool_facets_cli_positional:
  - business_group_id
tool_facets_parameters: |
  {
    "type": "object",
    "properties": {
      "business_group_id": {
        "type": "string",
        "description": "REQUIRED. UUID of the selected business group."
      },
      "node_type": {
        "type": "string",
        "description": "Node type filter. Default: cloudchef.nodes.Compute"
      }
    },
    "required": ["business_group_id"]
  }
tool_bgs_name: "smartcmp_list_available_bgs"
tool_bgs_description: "List available business groups for a specific service catalog. Call this AFTER selecting a catalog to get the list of business groups the user can choose from. Use the returned id or name (depending on the catalog parameter key) for the business group field in the request body."
tool_bgs_entrypoint: "scripts/list_available_bgs.py"
tool_bgs_group: "cmp"
tool_bgs_capability_class: "provider:smartcmp"
tool_bgs_priority: 105
tool_bgs_cli_positional:
  - catalog_id
tool_bgs_parameters: |
  {
    "type": "object",
    "properties": {
      "catalog_id": {
        "type": "string",
        "description": "REQUIRED. UUID of the service catalog to query available business groups for."
      }
    },
    "required": ["catalog_id"]
  }
tool_flavors_name: "smartcmp_list_flavors"
tool_flavors_description: "List available compute flavors (specifications) from SmartCMP. Call this to get available compute profiles. Match the user's spec (e.g. '2c4g') against the returned flavor name field. Use the matched flavor's name for computeProfileName or id for computeProfileId, depending on the catalog parameter key."
tool_flavors_entrypoint: "scripts/list_flavors.py"
tool_flavors_group: "cmp"
tool_flavors_capability_class: "provider:smartcmp"
tool_flavors_priority: 108
tool_flavors_parameters: |
  {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Optional search keyword to filter flavors"
      }
    }
  }
---

# request

Submit cloud resource, application environment, or ticket/work order requests through the service catalog.

## Flow

Five tools exist: `smartcmp_list_services`, `smartcmp_list_available_bgs`, `smartcmp_list_flavors`, `smartcmp_list_facets`, and `smartcmp_submit_request`.

### Complete flow

1. **Call `smartcmp_list_services`** → auto-select or ask user to select catalog
2. **Call `smartcmp_list_available_bgs`** (with catalogId) → if one BG, auto-select; if multiple, **MUST show list and WAIT for user to choose** (never auto-pick a default). **You MUST call this tool. Do NOT skip it. Do NOT ask the user to type a business group name. The tool returns the available options.**
3. **Check `instructions.parameters`** for `resourceBundleTags`:
   - If `resourceBundleTags` required AND `resourceBundleName` absent → **call `smartcmp_list_facets`** (with businessGroupId) → auto-match user's env keyword or ask user to select
   - Otherwise → use `resourceBundleName` from params `defaultValue`
4. **Check `instructions.parameters`** for `computeProfileName`:
   - If user provided a spec (e.g. "2c4g") → **call `smartcmp_list_flavors`** → match user spec against flavor `name` field → use matched `name` for `computeProfileName`
   - If no user spec and has `defaultValue` → use default
5. **Build request body** → show JSON preview → ask confirmation
6. **User confirms** → call `smartcmp_submit_request`

> **MANDATORY:** Steps 1–2 are NEVER optional. You MUST call `smartcmp_list_services` and then `smartcmp_list_available_bgs` in every request flow. Never skip the business group API call.

### Tool sequencing

Even when multiple lookups are logically independent, the runtime contract is
still one tool call per turn:
- After each tool call, stop and summarize the resolved result in natural
  language.
- Ask exactly one next question for the next missing field set, or move
  directly to preview/submission if no required fields remain.
- Do not batch `smartcmp_list_available_bgs`, `smartcmp_list_facets`, and
  `smartcmp_list_flavors` into one turn.

## Natural-Language Follow-up After Lookup Tools

Lookup tools are for resolving request context, not for exposing raw tool
output to the user.

- After any lookup tool call, summarize the resolved result in natural language.
- Ask exactly one next question for the next missing field, or move directly
  to preview/submission if no required fields remain.
- Do not paste raw tool output, JSON, or `_internal` metadata into the reply.
- Never chain multiple tool calls in one turn; one tool call per turn remains
  the hard limit.

## Terminology Mapping

SmartCMP uses `business group` as the platform field name, but users may
describe the same request scope as `tenant`, `租户`, `部门`, `BU`,
`Department`, `项目`, or `Project`.

- When the user uses one of these terms for request scope, resolve it to
  the business group field from `instructions.parameters`.
- Keep the request payload field name exactly as the param key even if
  you reply using the user's wording.
- If `tenant` clearly refers to AtlasClaw auth or platform tenancy rather than
  the SmartCMP request scope, clarify before using it in the request body.

## Business-Group Resolution

Business-group selection stays API-driven, but the follow-up must remain
concise and natural:

- Use `smartcmp_list_available_bgs` as the authoritative source of available
  business groups for the selected catalog.
- If the API returns exactly one business group, use it silently. Do not ask
  the user to fill it again.
- If the user already specified a tenant / 租户 / 部门 / BU / 项目 and it
  uniquely normalizes to one available business group, carry that resolved
  match forward instead of asking again.
- If multiple business groups remain after normalization, ask one concise
  numbered selection question before building the preview.
- Ask one concise selection question and wait for the user's choice.
- When asking the user to choose, do not repeat lookup scaffolding such as
  `Found N business group(s)` before the question.
## Service Selection

1. Call `smartcmp_list_services` (ONCE only, never again after getting catalogId).
2. **Auto-select when intent is clear:**
   - "linux" / "Linux VM" / "云主机" → select catalog named "Linux VM"
   - "windows" / "Windows VM" → select "Windows VM"
   - "工单" / "ticket" / "问题" → select `serviceCategory: "GENERIC_SERVICE"`
   - "k8s" / "容器" → select "App on Kubernetes"
   - "机房" → select "机房"
   - Ambiguous → show numbered list and ask
3. **When auto-selecting:** Output a concise natural-language confirmation such as "已为您自动选择 Linux VM". If required fields remain, ask exactly one natural-language question for the next missing field set. Do not echo raw tool output.

## Spec Matching: Compute Profile (API-driven, LLM semantic)

When the user mentions a compute spec in any form, the Agent must **call `smartcmp_list_flavors`** to get the available profiles, then use **LLM reasoning** to match the user's intent against the returned list.

### Workflow

1. **Call `smartcmp_list_flavors`** to get available compute profiles.
2. **LLM semantic matching** — the API returns flavors with `name` (e.g. "微型计算", "通用规格", "2c2g", "小型计算") and optional `description`. The Agent should:
   - Compare the user's wording against all returned flavor `name` and `description` fields
   - Use LLM reasoning to infer the best match (e.g. user says "小一点的" → "微型计算" or "小型计算")
   - If user says "2c4g" → match flavor named "2c4g" directly
   - If user says "微型" → match "微型计算"
3. **If exactly one flavor matches with high confidence** → auto-select and inform user
4. **If no match or ambiguous** → show numbered list of all available flavors and ask user to choose
5. **If user did not mention any spec:**
   - If `computeProfileName` has a `defaultValue` in params → use default
   - Otherwise → show flavor list from `smartcmp_list_flavors` and ask user to choose

### Key Rules

- **Always call `smartcmp_list_flavors`** to get the real list before matching
- **Do NOT hardcode or guess flavor names.** Flavor names are deployment-specific (could be "2c4g", "微型计算", "通用规格", etc.)
- Use LLM semantic inference, not rigid string parsing. The user may say "帮我申请微型计算" or "小的就行" or "2核4G" — all should be matched against the API-returned list
- Use the matched flavor's `name` for `computeProfileName` or `id` for `computeProfileId`, depending on which key exists in `instructions.parameters`. If both keys exist, prefer `computeProfileId`
- **Do NOT create separate `cpu` or `memory` fields.** The spec goes into the compute profile field only

> **CRITICAL — MUST include compute profile after matching:**
> After `smartcmp_list_flavors` returns a match, you MUST put either `computeProfileId` (flavor's `id`) or `computeProfileName` (flavor's `name`) into `resourceSpecs`. This is the #1 most common mistake: the Agent finds the flavor but forgets to add it to the JSON. A request without compute profile will fail with HTTP 400.
>
> Example: If flavor API returned `{"id": "abc-123", "name": "2c4g"}` and `instructions.parameters` has `computeProfileId`, then resourceSpecs MUST include `"computeProfileId": "abc-123"`.

## Field Placement (MUST follow)

Use the **EXACT parameter keys** from `instructions.parameters`. Do NOT rename, merge, invent field names, or use hardcoded values from this document's examples.

> **CRITICAL:** The parameter keys below (e.g. `businessGroupName` vs `businessGroupId`) are **illustrative only**. Different catalog configurations may use different keys. Always check `instructions.parameters` and use the actual `key` field from the catalog metadata.

| Field | Location | Value Source |
|-------|----------|-------------|
| `catalogId` | **top-level** | catalog metadata `id` field (**MUST be UUID**, never sourceKey) |
| `catalogName` | **top-level** | catalog metadata `name` field |
| `businessGroupId` | **top-level** | **Always use `businessGroupId`** as the key. Value is the `id` from `smartcmp_list_available_bgs` API response (the user's selected BG) |
| `userLoginId` | **top-level** | **OMIT from request body** — the submit script auto-fills it from the current session. Do NOT include this field in the JSON. |
| `name` | **top-level** | user input or auto-generate `vm-<timestamp>` |
| resource bundle field | **top-level** | `resourceBundleName` from params `defaultValue` (omit when using `resourceBundleTags`) |
| `node` | resourceSpecs | `instructions.node` (e.g. `"Compute"`) |
| `type` | resourceSpecs | `instructions.type` (e.g. `"cloudchef.nodes.Compute"`) |
| `resourceBundleTags` | resourceSpecs | **MUST be an array of strings**, format: `["<facet.key>:<option.key>"]`. NEVER use object format like `{"key": "value"}`. Values from `smartcmp_list_facets` API, see Tag-based Resource Bundle section |
| compute profile field | resourceSpecs | **matched from `smartcmp_list_flavors` API**. Use `name` for `computeProfileName` or `id` for `computeProfileId`, depending on param key. If both exist, prefer `computeProfileId`. **MUST NOT be omitted after a successful flavor match.** |
| `logicTemplateName` | resourceSpecs | Use user choice or explicit runtime lookup. If catalog metadata marks it `runtimeDefaultOnly`, omit it from the payload and let CMP runtime form apply the real default. |
| `templateId` | resourceSpecs | Use user choice or explicit runtime lookup. If catalog metadata marks it `runtimeDefaultOnly`, omit it from the payload. |
| `credentialUser` | resourceSpecs | user input or params `defaultValue` |
| `credentialPassword` | resourceSpecs | user input (ask if no default) |
| `networkId` | resourceSpecs | Use user choice or explicit runtime lookup. If catalog metadata marks it `runtimeDefaultOnly`, omit it from the payload. |
| `systemDisk` | resourceSpecs | **nested object** `{"size": N}`. If only a `runtimeDefaultOnly` catalog default exists, omit the field and let CMP runtime form choose. |

**FORBIDDEN inside resourceSpecs:** `name`, `businessGroupId`, `resourceBundleName`, `cpu`, `memory`
**FORBIDDEN top-level:** `description`, `serviceCategory`, `priority`, `category`, `requestor`, `parameters`, `resourceBundleTags`

> **CRITICAL placement rules:**
> - `name` goes ONLY at top-level. NEVER put `name` inside resourceSpecs.
> - `resourceBundleTags` goes ONLY inside resourceSpecs. NEVER put it at top-level.
> - `computeProfileName` or `computeProfileId` MUST appear inside resourceSpecs when a compute profile was matched. NEVER omit it after a successful flavor match. Missing compute profile will cause HTTP 400.

### Parameter Key Rule (CRITICAL)

**Every field in the request body MUST use the exact `key` from `instructions.parameters`.** Do NOT substitute with similar-sounding names from examples in this document.

**Exception:** Business group always uses `businessGroupId` with the `id` from the API, regardless of what `instructions.parameters` defines.

## Runtime Default Guard

Some SmartCMP catalogs expose stale or design-time `defaultValue` fields through
`/catalogs/published`, while the real submit form applies different runtime
defaults in the UI. Because of that:

- If a parameter is marked `runtimeDefaultOnly: true` in catalog metadata, do
  **NOT** serialize that value into the request body.
- Treat `runtimeDefaultOnly` values as UI hints only.
- For those fields, either:
  - omit them and let CMP runtime form apply the real default, or
  - ask the user to choose explicitly, or
  - resolve them through datasource/resource-pool/image lookups first.
- This guard especially applies to infrastructure selectors such as
  `resourceBundleName`, `computeProfileName`, `logicTemplateName`,
  `templateId`, `networkId`, and `systemDisk.size`.
- `userLoginId` is always auto-injected by the submit script; do NOT include it
  in the request body.

## Business Group Selection (API-driven)

After selecting a catalog, **always call `smartcmp_list_available_bgs`** with the catalogId to get the list of business groups available for that catalog.

> **IMPORTANT:** You MUST call the `smartcmp_list_available_bgs` tool. Do NOT ask the user "Which business group do you want?" without first calling the tool. The tool returns the actual list of available business groups. Without calling this tool, you do not know what options exist.

### Workflow

1. Call `smartcmp_list_available_bgs` with `catalog_id` = selected catalogId
2. API returns a list of business groups, each with `id` and `name`
3. If only one BG available → auto-select and inform user
4. If multiple BGs → **MUST show numbered list and ask user to choose. STOP and WAIT for user response. Do NOT auto-pick any default or "recommended" option.**
5. Use the selected BG's `id` as the value for `businessGroupId` in the request body

> **CRITICAL:** When multiple business groups are available, you MUST ask the user to choose. Never assume a default, never recommend one, never skip the selection. The workflow CANNOT proceed until the user explicitly picks one.
>
> **Do NOT use the `defaultValue` from params for business group.** Always call the API to get the actual available options.

## Tag-based Resource Bundle Matching (resourceBundleTags)

When `instructions.parameters` includes `resourceBundleTags` as **required** (`required: true`) and `resourceBundleName` is **absent**, use tag-based matching instead.

### Trigger Conditions

| Condition | Mode |
|-----------|------|
| `resourceBundleTags` required AND `resourceBundleName` absent | **Tag mode** — call `smartcmp_list_facets`, let user pick, build `resourceBundleTags` in resourceSpecs |
| `resourceBundleName` present (regardless of `resourceBundleTags`) | **Name mode** — use `resourceBundleName` at top-level as normal, ignore tags |

### Tag Mode Workflow

1. **Call `smartcmp_list_facets`** with `business_group_id` (the selected BG's id) to retrieve available facet definitions and options.
2. **Present options to user** using `nameZh` (Chinese) or `name` (English) from the response. Example:
   - "请选择资源环境：1) 开发  2) 测试  3) 生产"
3. **User selects** → build the tag string using the facet `key` and option `key` from API response.
4. Place the result in `resourceBundleTags` array inside resourceSpecs.

### API Response Structure

`smartcmp_list_facets` returns facet objects. The structure varies per deployment — **do NOT assume any specific key names**. Example of what the API *might* return:

```json
[
  {
    "key": "<facet_key>",
    "name": "<english_display_name>",
    "nameZh": "<chinese_display_name>",
    "optionMode": "SINGLE",
    "options": [
      { "key": "<option_key_1>", "name": "<EN_1>", "nameZh": "<ZH_1>" },
      { "key": "<option_key_2>", "name": "<EN_2>", "nameZh": "<ZH_2>" }
    ]
  }
]
```

All `key` values (`facet.key`, `option.key`) are **deployment-specific** and can only be known at runtime by calling the API.

### Building resourceBundleTags (CRITICAL)

Format: `["<facet.key>:<option.key>"]` — both parts come **directly from the runtime API response**, never hardcoded, never invented.

> **TYPE CONSTRAINT:** `resourceBundleTags` is ALWAYS an **array of strings**. Never an object, never a dict, never key-value pairs.
> - CORRECT: `"resourceBundleTags": ["FACET_ENV:test"]`
> - WRONG:  `"resourceBundleTags": {"FACET_ENV": "test"}` ← this will cause submission failure

**Step-by-step:**

1. Call `smartcmp_list_facets` with `business_group_id` → receive facet list
2. For each facet, read `facet.key` (e.g. the API might return `"FACET_ENV"`, `"FACET_REGION"`, etc.)
3. Present `facet.nameZh` / `facet.name` as label, and `option.nameZh` / `option.name` as choices to user
4. User picks an option → take that option's `key` field from the API response
5. Build tag string: `"<facet.key>:<selected_option.key>"`
6. Place in array: `"resourceBundleTags": ["<facet.key>:<selected_option.key>"]`

| API Field | Usage |
|-----------|-------|
| `facet.key` | Left side of colon — **read from API response at runtime** |
| `option.key` | Right side of colon — **read from API response at runtime** |
| `facet.nameZh` / `facet.name` | **Display only** — show to user, NEVER put in request body |
| `option.nameZh` / `option.name` | **Display only** — show to user, NEVER put in request body |

> **NEVER hardcode** any facet key or option key. Every deployment may have different keys. Always call `smartcmp_list_facets` first and use the returned values.

### Auto-matching from User Input

If the user mentions an environment keyword in their request (e.g. "测试", "生产", "开发"), the Agent should:

1. Call `smartcmp_list_facets` to get available options. **This requires `business_group_id`**, so business group must be resolved first.
2. Match user's keyword against option `nameZh` / `name` fields.
3. If exactly one option matches → auto-select and inform user (e.g. "已自动匹配资源环境: 测试").
4. If no match or ambiguous → show the full option list and ask user to choose.

### Correct Example (Tag-based, no resourceBundleName)

> The values below are illustrative only.
> In practice, use the **actual keys and defaultValues** from `instructions.parameters`,
> and the **actual facet/option keys** returned by `smartcmp_list_facets` at runtime.

```json
{
  "catalogId": "<UUID from catalog metadata id>",
  "catalogName": "<from catalog metadata name>",
  "businessGroupId": "<id from smartcmp_list_available_bgs>",
  "name": "test-linux-vm",
  "resourceSpecs": [
    {
      "resourceBundleTags": ["<facet.key>:<option.key>"],
      "computeProfileId": "<id from smartcmp_list_flavors>",
      "node": "Compute",
      "type": "cloudchef.nodes.Compute",
      "logicTemplateName": "<defaultValue from params>",
      "systemDisk": { "size": 60 }
    }
  ]
}
```

### WRONG — Tag Mistakes (DO NOT follow)

**Wrong 1: Using display name instead of API key**
```json
{ "resourceBundleTags": ["资源环境:测试"] }
```
Display names (`nameZh`) are for showing to user only. Must use `facet.key` and `option.key` from API response.

**Wrong 2: Using parameter field name as tag key**
```json
{ "resourceBundleTags": ["Resource Bundle Tags:test"] }
```
`"Resource Bundle Tags"` is the parameter name, not a facet key. Must use `facet.key` from API.

**Wrong 3: Hardcoding or inventing keys without calling API**
```json
{ "resourceBundleTags": ["env:test"] }
```
Tag key and value must come from `smartcmp_list_facets` API response, not invented or assumed.

**Wrong 4: Using both resourceBundleName and resourceBundleTags**
```json
{ "resourceBundleName": "pool", "resourceSpecs": [{ "resourceBundleTags": ["..."] }] }
```
When using tags, omit `resourceBundleName` from top-level.

**Wrong 5: resourceBundleTags placed at top-level**
```json
{ "resourceBundleTags": ["..."], "resourceSpecs": [...] }
```
`resourceBundleTags` belongs inside each resourceSpecs item, not at top-level.

**Wrong 6: resourceBundleTags as object instead of array**
```json
{ "resourceBundleTags": { "key": "value" } }
```
Must be array of strings: `["<facet.key>:<option.key>"]`

## Correct Example (vSphere Linux VM with user spec "2c4g")

> catalogId MUST be a UUID like `a1b2c3d4-...`, taken from catalog metadata `id` field.
> NEVER use sourceKey like `BUILD-IN-CATALOG-LINUX-VM` as catalogId.
> All field names and values below are **illustrative**. Always use the actual keys and defaultValues from `instructions.parameters`.

```json
{
  "catalogId": "<UUID from catalog metadata id>",
  "catalogName": "<from catalog metadata name>",
  "businessGroupId": "<id from smartcmp_list_available_bgs>",
  "name": "my-linux-vm",
  "resourceBundleName": "<defaultValue from params>",
  "resourceSpecs": [
    {
      "node": "Compute",
      "type": "cloudchef.nodes.Compute",
      "computeProfileId": "<id from smartcmp_list_flavors>",
      "logicTemplateName": "<defaultValue from params>",
      "templateId": "<defaultValue from params>",
      "credentialUser": "root",
      "credentialPassword": "P@ssw0rd",
      "networkId": "<defaultValue from params>",
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

**Wrong 2: separate cpu/memory fields instead of computeProfileName**
```json
{ "resourceSpecs": [{ "cpu": 2, "memory": 4, "computeProfileName": "test" }] }
```
User said "2c4g" → must call `smartcmp_list_flavors`, find the matching flavor, and use its `name`. Do NOT add `cpu` or `memory` fields.

**Wrong 3: top-level fields duplicated inside resourceSpecs**
```json
{ "resourceSpecs": [{ "name": "vm1", "businessGroupId": "xxx", "resourceBundleName": "pool" }] }
```
`name`, business group field, `resourceBundleName` belong at top-level ONLY.

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

**Wrong 6: hardcoding a flavor name without calling the API**
```json
{ "resourceSpecs": [{ "computeProfileName": "2c4g" }] }
```
Even if user said "2c4g", must call `smartcmp_list_flavors` first to verify the flavor exists and get the exact `name` from API.

## Parameter Resolution

Resolve parameters using API tools and `instructions.parameters`:

| # | Condition | Action |
|---|-----------|--------|
| 1 | Business group field exists in params | Call `smartcmp_list_available_bgs` → user selects → use `businessGroupId` with the selected BG's `id` |
| 2 | User provides spec (e.g. "2c4g", "微型计算", "小一点的") | Call `smartcmp_list_flavors` → LLM semantic match against returned flavor `name` list → set compute profile field |
| 3 | User does not provide spec, no `defaultValue` for compute profile | Call `smartcmp_list_flavors` → show list → ask user to choose |
| 4 | `resourceBundleTags` required AND `resourceBundleName` absent | Call `smartcmp_list_facets` (with `business_group_id`) → match/select → set `resourceBundleTags` in resourceSpecs using API keys; omit `resourceBundleName` |
| 5 | Parameter has non-empty `defaultValue` (except business group) and is **not** marked `runtimeDefaultOnly` | Use default silently |
| 6 | Parameter is marked `runtimeDefaultOnly: true` | Omit it from payload unless user explicitly chose it or runtime lookup resolved it |
| 7 | `name` not provided | Generate or ask user |
| 8 | `credentialUser/Password` required, no default | Ask user |
| 9 | `resourceBundleTags` required but user didn't mention env and no match from facets | Show facet options list (from `smartcmp_list_facets` with `business_group_id`) and ask user to choose |
| 10 | Everything else, no default | Omit from request body |

## Concrete Flow Expectations

- "我要申请工单": after the ticket service is auto-selected and the business
  group is resolved or chosen, keep the resolved context and continue with a
  natural-language prompt for the remaining ticket fields instead of stopping
  at raw tool output.
- If the user did not specify a business group for the ticket flow and the
  datasource returns multiple choices, ask only the short business-group
  selection question using the available names. Do not echo the lookup
  preamble or dump the full tool output.
- "我要申请测试部门的 2C4G 的 Linux VM": recognize Linux VM, the business
  group `测试部门`, and `cpu=2` plus `memory=4`; carry those values forward and
  ask only for the remaining required fields, minimizing follow-up rounds.
- In that Linux VM flow, if business-group lookup returns `测试`, treat it as
  the resolved match for user wording `测试部门` only when it is the unique
  normalized datasource match; otherwise ask the user to choose. When it is a
  unique match, continue directly to the remaining VM fields. Do not show the
  business-group list or the lookup preamble to the user.
- In both flows, do not re-ask for already resolved service, business group,
  CPU, or memory values.

## Ticket / Work Order Rules

When `serviceCategory` is `"GENERIC_SERVICE"`:
- top level: `catalogId`, `catalogName`, `businessGroupId`, `name`
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
- `smartcmp_list_available_bgs` at most ONCE per conversation (after catalog selection).
- `smartcmp_list_flavors` at most ONCE per conversation (when compute profile needed).
- `smartcmp_list_facets` at most ONCE per conversation (only when tag mode detected).
- ONE tool call per turn. After any tool call, STOP and summarize the resolved result in natural language, then ask at most one next question. Never dump raw tool output.
- When auto-selecting (single option), do NOT echo raw tool output.
- Never claim submitted unless `smartcmp_submit_request` actually executed.
- Never display raw `_internal` metadata to user.
