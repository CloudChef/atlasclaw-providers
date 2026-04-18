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
tool_list_services_description: "List available service catalogs from SmartCMP. Show only the numbered catalog list to the user. Treat returned _internal metadata such as id, sourceKey, serviceCategory, instructions, and params as hidden backend state only; never display or narrate those fields."
tool_list_services_entrypoint: "../shared/scripts/list_services.py"
tool_list_services_group: "cmp"
tool_list_services_capability_class: "provider:smartcmp"
tool_list_services_priority: 100
tool_list_services_result_mode: "tool_only_ok"
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
tool_list_business_groups_name: "smartcmp_list_business_groups"
tool_list_business_groups_description: "List business groups for a catalog. IMPORTANT: You MUST pass catalog_id from the previous list_services output (e.g. BUILD-IN-CATALOG-LINUX-VM)."
tool_list_business_groups_entrypoint: "../shared/scripts/list_business_groups.py"
tool_list_business_groups_groups:
  - cmp
  - request
tool_list_business_groups_capability_class: "provider:smartcmp"
tool_list_business_groups_priority: 105
tool_list_business_groups_result_mode: "tool_only_ok"
tool_list_business_groups_cli_positional:
  - catalog_id
tool_list_business_groups_parameters: |
  {
    "type": "object",
    "properties": {
      "catalog_id": {
        "type": "string",
        "description": "Catalog ID from list_services output (e.g. BUILD-IN-CATALOG-LINUX-VM)"
      }
    },
    "required": ["catalog_id"]
  }
tool_list_resource_pools_name: "smartcmp_list_resource_pools"
tool_list_resource_pools_description: "List resource pools for VM provisioning. Requires business_group_id from list_business_groups, source_key from the selected catalog metadata, and node_type from the selected catalog instructions.type field."
tool_list_resource_pools_entrypoint: "../shared/scripts/list_resource_pools.py"
tool_list_resource_pools_groups:
  - cmp
  - request
tool_list_resource_pools_capability_class: "provider:smartcmp"
tool_list_resource_pools_priority: 110
tool_list_resource_pools_result_mode: "tool_only_ok"
tool_list_resource_pools_cli_positional:
  - business_group_id
  - source_key
  - node_type
tool_list_resource_pools_parameters: |
  {
    "type": "object",
    "properties": {
      "business_group_id": {
        "type": "string",
        "description": "Business group ID from list_business_groups output"
      },
      "source_key": {
        "type": "string",
        "description": "Service source key from list_services CATALOG_META (e.g. resource.iaas.machine.instance.abstract)"
      },
      "node_type": {
        "type": "string",
        "description": "Selected catalog instructions.type value (for example cloudchef.nodes.Compute)"
      }
    },
    "required": ["business_group_id", "source_key", "node_type"]
  }
tool_list_os_templates_name: "smartcmp_list_os_templates"
tool_list_os_templates_description: "List OS templates. IMPORTANT: os_type MUST be 'Linux' or 'Windows' from selected catalog instructions.osType, or derived from the selected catalog instructions.type when osType is absent. resource_bundle_id comes from list_resource_pools metadata."
tool_list_os_templates_entrypoint: "../shared/scripts/list_os_templates.py"
tool_list_os_templates_groups:
  - cmp
  - request
tool_list_os_templates_capability_class: "provider:smartcmp"
tool_list_os_templates_priority: 115
tool_list_os_templates_result_mode: "tool_only_ok"
tool_list_os_templates_cli_positional:
  - os_type
  - resource_bundle_id
tool_list_os_templates_parameters: |
  {
    "type": "object",
    "properties": {
      "os_type": {
        "type": "string",
        "description": "OS type: must be exactly 'Linux' or 'Windows' (from selected catalog instructions.osType, or derived from instructions.type)"
      },
      "resource_bundle_id": {
        "type": "string",
        "description": "Resource bundle ID from list_resource_pools output"
      }
    },
    "required": ["os_type", "resource_bundle_id"]
  }
tool_list_applications_name: "smartcmp_list_applications"
tool_list_applications_description: "List applications/projects for a business group. Returns application IDs for request submission."
tool_list_applications_entrypoint: "../shared/scripts/list_applications.py"
tool_list_applications_groups:
  - cmp
  - request
tool_list_applications_capability_class: "provider:smartcmp"
tool_list_applications_priority: 125
tool_list_applications_result_mode: "tool_only_ok"
tool_list_applications_cli_positional:
  - business_group_id
  - keyword
tool_list_applications_parameters: |
  {
    "type": "object",
    "properties": {
      "business_group_id": {
        "type": "string",
        "description": "Business group ID from list_business_groups output"
      },
      "keyword": {
        "type": "string",
        "description": "Optional keyword to filter applications by name"
      }
    },
    "required": ["business_group_id"]
  }
tool_list_images_name: "smartcmp_list_images"
tool_list_images_description: "List available VM images for the selected resource pool and OS template. IMPORTANT: pass resource_bundle_id from the selected resource pool, logic_template_id from the selected OS template, and cloud_entry_type_id from the same selected resource pool's cloudEntryTypeId. Build the lookup from the actual selected platform value; never hardcode vSphere or any single cloud platform."
tool_list_images_entrypoint: "../shared/scripts/list_images.py"
tool_list_images_groups:
  - cmp
  - request
tool_list_images_capability_class: "provider:smartcmp"
tool_list_images_priority: 130
tool_list_images_result_mode: "tool_only_ok"
tool_list_images_cli_positional:
  - resource_bundle_id
  - logic_template_id
  - cloud_entry_type_id
tool_list_images_parameters: |
  {
    "type": "object",
    "properties": {
      "resource_bundle_id": {
        "type": "string",
        "description": "Resource bundle ID from list_resource_pools output"
      },
      "logic_template_id": {
        "type": "string",
        "description": "Logic template ID from list_os_templates output"
      },
      "cloud_entry_type_id": {
        "type": "string",
        "description": "Cloud entry type ID from list_resource_pools RESOURCE_POOL_META (cloudEntryTypeId)"
      }
    },
    "required": ["resource_bundle_id", "logic_template_id", "cloud_entry_type_id"]
  }
tool_submit_name: "smartcmp_submit_request"
tool_submit_description: "Submit resource request to SmartCMP. Pass the complete request JSON body as the 'json_body' parameter. Reuse the selected catalog metadata, including catalogId and catalogName when they are available."
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
        "description": "Complete request body as a JSON string. Reuse the selected catalog metadata from list_services. Include catalogId and catalogName when available, plus userLoginId, businessGroupName or businessGroupId, name, and resourceSpecs (for cloud) or genericRequest (for ticket)."
      }
    },
    "required": ["json_body"]
  }
---

# request

Submit cloud resource, application environment, or ticket/work order requests through the service catalog.

## Authoritative Workflow

This section overrides any legacy mention of `list_components.py` later in this file.

### Cloud request metadata source

For cloud requests, use the selected catalog card metadata from `list_services` as the source of truth:

- `instructions.node` -> request `node`
- `instructions.type` -> request `type` and resource-pool lookup `node_type`
- `instructions.osType` -> OS template lookup `os_type`
- if `instructions.osType` is absent, derive `Windows` when `type` or `node` contains `windows`; otherwise derive `Linux`
- selected catalog `id` -> request `catalogId`
- selected catalog `name` -> request `catalogName`

Before every follow-up decision, reread the saved selected catalog metadata from the earlier
`list_services` `_internal` payload. If earlier assistant prose conflicts with the selected
catalog `instructions` or `params`, the catalog metadata wins.

Do not call `list_components.py`.

### Parameter processing rules

Process `params` in order and apply only these rules:

- `source` exists and `defaultValue` is empty -> call the mapped lookup tool and wait for user selection
- `source` exists and `defaultValue` is non-empty -> use the default silently
- `source` is empty and `defaultValue` is non-empty -> use the default silently
- `source` is empty, `defaultValue` is empty, `required=true` -> ask the user
- `source` is empty, `defaultValue` is empty, `required=false` -> skip it

Enforcement:

- Only the current parameter's explicit `source` may trigger a lookup tool.
- If a parameter does not declare `source: "list:applications"`, do NOT call
  `smartcmp_list_applications`.
- If `resourceBundleName`, `logicTemplateName`, `templateId`, or any other parameter has a
  non-empty `defaultValue`, use that value silently and do NOT call another list tool for it.

Mapped lookups:

- `list:business_groups` -> `smartcmp_list_business_groups(catalog_id=<selected catalog id>)`
- `list:applications` -> `smartcmp_list_applications(business_group_id=<selected business group id>)`
- `list:resource_pools` -> `smartcmp_list_resource_pools(business_group_id=<selected business group id>, source_key=<selected sourceKey>, node_type=<instructions.type>)`
- `list:os_templates` -> `smartcmp_list_os_templates(os_type=<instructions.osType or derived value>, resource_bundle_id=<selected resource pool id>)`
- `list:list_images` / `list:images` -> `smartcmp_list_images(resource_bundle_id=<selected resource pool id>, logic_template_id=<selected os template id>, cloud_entry_type_id=<selected resource pool cloudEntryTypeId>)`

### Submit contract

The submit tool now accepts `json_body`.

When building a cloud request:

- put `catalogId`, `catalogName`, `userLoginId`, `businessGroupName` or `businessGroupId`, `resourceBundleName`, and `name` at the top level
- put `node`, `type`, and all collected cloud parameters inside `resourceSpecs[0]`
- never auto-submit before showing a final summary and asking `请确认以上信息是否正确？（是/否）`

Before any submit call, always show the constructed request body to the user.

Display order:

1. a short Chinese summary
2. a heading `JSON 预览`
3. a fenced `json` code block containing the constructed request body
4. the confirmation question `请确认以上信息是否正确？（是/否）`

The preview must reflect the real structure and resolved values that will be submitted, including applied defaults, selected list values, nested `resourceSpecs` placement, and top-level request fields.

For sensitive fields such as `credentialPassword`, mask the preview value as `"******"` by default, but keep the real value in the actual `json_body` sent to `smartcmp_submit_request`.

---

## Legacy Workflow Notes (Deprecated)

```
[Trigger] User expresses intent to "request resources"
    |
    v
[Step 1] Execute list_services.py -> Display service list -> STOP wait for user selection
    |
    v
[Step 2] User selects service -> Check serviceCategory field
    |
    +---> serviceCategory === "GENERIC_SERVICE" ---> [Ticket Flow]
    |
    +---> serviceCategory !== "GENERIC_SERVICE" ---> [Cloud Resource Flow]
```

---

## Step 1: List Available Services [Execute]

```bash
python ../shared/scripts/list_services.py
```

**Output Example:**

The tool returns a JSON result with two key fields:
- `output`: The user-visible text (numbered list + selection prompt)
- `_internal`: Machine-readable metadata (catalog IDs, params, etc.)

The `output` field looks like:
```
Found 3 published catalog(s):

  [1] Linux VM
  [2] Issue Ticket
  [3] Server Room

请选择您要申请的服务（输入编号）：
```

When presenting service cards to the user:
- Show only the numbered catalog names from the `output` field.
- Do NOT display `_internal` metadata such as `id`, `sourceKey`, `serviceCategory`,
  `instructions`, or `params`.

The `_internal` field contains JSON like:
```json
[{
  "index": 1,
  "id": "xxx",
  "name": "Linux VM",
  "sourceKey": "resource.iaas...",
  "serviceCategory": "VM",
  "instructions": {
    "parameters": [
      {
        "key": "name",
        "label": "Resource Name",
        "source": null,
        "defaultValue": null,
        "required": true
      }
    ]
  },
  "params": [
    {
      "key": "name",
      "label": "Resource Name",
      "source": null,
      "defaultValue": null,
      "required": true
    }
  ]
}]
```

**IMPORTANT:** The `_internal` field is for your reference ONLY. Parse it silently to extract IDs, params, serviceCategory. NEVER display `_internal` content to the user.

**Action:** Display ONLY the numbered list and the selection prompt to user. Ask user to select.

**STOP - Wait for user input**

---

## Step 2: Determine Service Type [Decision]

After user selection, find the corresponding item from the `_internal` metadata and check `serviceCategory` field:

Immediately save the selected service card metadata into working variables for the
rest of the workflow, including:
- `selected_catalog_id` = selected card `id`
- `selected_source_key` = selected card `sourceKey`
- `selected_service_category` = selected card `serviceCategory`
- `selected_params` = selected card `params`

Do this silently. Do NOT display these metadata fields to the user.

| serviceCategory Value | Service Type | Flow |
|----------------------|--------------|------|
| `GENERIC_SERVICE` | Ticket/Manual Request | [Ticket Flow](#ticket-flow-generic_service) |
| Any other value | Cloud Resource | [Cloud Resource Flow](#cloud-resource-flow) |

---

## Ticket Flow (GENERIC_SERVICE)

Use this flow when `serviceCategory === "GENERIC_SERVICE"`.

### T1: Get Business Groups [Execute]

```bash
python ../shared/scripts/list_business_groups.py <catalogId>
```

**Action:** Display business group list, ask: "Please select a business group"

**STOP - Wait for user selection**

### T2: Collect Ticket Info [Ask]

Ask user:
```
Please provide the following information:
1. Ticket name:
2. Ticket description:
```

**STOP - Wait for user input**

### T3: Build Request Body [Build]

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

**Action:** Display confirmation to user, ask: "Please confirm if the above information is correct? (yes/no)"

**STOP - Wait for user confirmation**

### T4: Submit [Execute]

```bash
python scripts/submit.py --file request.json
```

**Complete** - Display request ID and status to user.

---

## Cloud Resource Flow

Use this flow when `serviceCategory !== "GENERIC_SERVICE"`.

This flow is **strictly driven by the `params` array** from the selected service's `_internal` metadata. That `params` array is a normalized copy of `instructions.parameters`, and each item preserves the original `key`, `label`, `source`, `defaultValue`, and `required` fields.

### Overview

```
[R1] Read embedded component metadata from selected catalog instructions
    |
    v
[R2] Process params array in order:
    For each param:
      - source = "list:xxx" -> call corresponding tool, ask user to select
      - source = null, defaultValue != null -> use default silently
      - source = null, defaultValue = null, required = true -> ask user to input
      - required = false, defaultValue = null -> skip
    |
    v
[R3] Build request body with all collected values
    |
    v
[R4] Confirm with user -> Submit
```

---

### R1: Get Component Info [Silent Execute]

There is no backend component-lookup tool in the new workflow.

Read the selected catalog instructions silently and extract:

- `instructions.type` → request `type` and resource-pool lookup `node_type`
- `instructions.node` → request `node`
- `instructions.osType` → OS template lookup `os_type`
- `instructions.cloudEntryTypeIds` → if explicitly empty and the catalog does not use resource pools, set `useResourceBundle: false`

If `instructions.osType` is absent, derive it from `instructions.type` or `instructions.node`:

- contains `windows` → `Windows`
- otherwise → `Linux`

Proceed to R2 directly without user interaction.

---

### R2: Process Params Array Step by Step

Read the `params` array from the selected service's `_internal` metadata. Process each parameter **in order**. For each parameter, follow these rules:

#### Source-to-Tool Mapping

| `source` value | Tool to call | Parameters needed |
|---------------|-------------|------------------|
| `list:business_groups` | `smartcmp_list_business_groups` | catalog_id (from selected service id) |
| `list:applications` | `smartcmp_list_applications` | business_group_id (from selected business group), keyword (optional) |
| `list:resource_pools` | `smartcmp_list_resource_pools` | business_group_id, source_key, node_type (from selected catalog instructions.type) |
| `list:os_templates` | `smartcmp_list_os_templates` | os_type (from selected catalog instructions.osType; fallback: infer from selected catalog instructions.type), resource_bundle_id (from selected pool) |
| `list:list_images` or `list:images` | `smartcmp_list_images` | resource_bundle_id (from selected pool), logic_template_id (from selected OS template), cloud_entry_type_id (from the same selected pool's `cloudEntryTypeId`; use the actual selected value, never hardcode a platform) |

#### Parameter Decision Rules

| Condition | Action | Example |
|-----------|--------|--------|
| `source: "list:xxx"` AND `defaultValue: null` | Call the mapped tool, show list to user, ask to select. **STOP and wait.** | businessGroupId, projectId |
| `source: "list:xxx"` AND `defaultValue` has value | Use default value silently. Do NOT call tool. | - |
| `source: null` AND `defaultValue` has value | Use default value silently. Do NOT ask user. | computeProfileName="微型计算", cpu=1, memory=1 |
| `source: null` AND `defaultValue: null` AND `required: true` | **Ask user to input this value.** Show prompt: "请输入{label}". **STOP and wait.** | name, credentialUser, credentialPassword |
| `source: null` AND `defaultValue: null` AND `required: false` | Skip this parameter. Do not ask user. | dataDisks, subnetId, securityGroupIds |

#### Example: Linux VM params processing

Given this params array:

> IMPORTANT: this example is illustrative only. On every real run, the currently selected
> catalog card wins. If the selected catalog already gives `resourceBundleName`,
> `logicTemplateName`, `templateId`, or similar fields a non-empty `defaultValue`, use that
> default silently and do not call the related lookup tool.

```
name           -> source=null, default=null, required=true   → ASK user: "请输入资源名称"
businessGroupId -> source=list:business_groups, default=null → CALL list_business_groups, show list, ask user to select
resourceBundleName -> source=list:resource_pools, default=null → CALL list_resource_pools, show list, ask user to select
computeProfileName -> source=null, default="微型计算"       → USE default silently
logicTemplateName -> source=list:os_templates, default=null  → CALL list_os_templates, show list, ask user to select
templateId     -> source=list:list_images, default=null      → CALL list_images, show list, ask user to select
credentialUser -> source=null, default=null, required=true   → ASK user: "请输入用户名"
credentialPassword -> source=null, default=null, required=true → ASK user: "请输入密码"
networkId      -> source=null, default="network-79"          → USE default silently
cpu            -> source=null, default=1                     → USE default silently
memory         -> source=null, default=1                     → USE default silently
systemDisk.size -> source=null, default=50, required=false   → USE default silently
dataDisks      -> required=false, default=null               → SKIP
subnetId       -> required=false, default=null               → SKIP
securityGroupIds -> required=false, default=null             → SKIP
```

For the current built-in Linux VM card, it is valid for:

- `resourceBundleName` to come from a silent default such as `vsphere资源池`
- `logicTemplateName` to come from a silent default such as `Centos`
- `templateId` to come from a silent default such as `vm-121`

When the actual selected card has those defaults, do not ask the user and do not call
`smartcmp_list_resource_pools`, `smartcmp_list_os_templates`, `smartcmp_list_images`, or
`smartcmp_list_applications` unless the current parameter explicitly declares the matching
`source` value.

**CRITICAL RULES:**
- **ONLY call tools that appear in the params `source` field.** Do NOT call tools not listed.
- **Process parameters one at a time.** After each tool call or user input request, STOP and wait.
- **You CAN batch multiple user-input questions** into one prompt (e.g., ask name + username + password together).
- If a param has `source: "list:applications"`, call `smartcmp_list_applications` after `businessGroupId` is known, show the numbered list, and STOP for user selection.
- Use selected catalog `instructions.type` as the `node_type` argument for `smartcmp_list_resource_pools`.
- For `smartcmp_list_images`, always pass the saved `cloudEntryTypeId` from the user's selected resource pool. Do not invent, omit, or hardcode the platform identifier.

---

### R3: Build Request Body [Build]

**Core Rules:**

1. `type` = selected catalog `instructions.type`
2. `node` = selected catalog `instructions.node`
3. If `cloudEntryTypeIds` is explicitly empty: add `"useResourceBundle": false`, do NOT include `resourceBundleName`
4. If a resource pool is selected or defaulted: include `resourceBundleName` at top level

**Request Body Template:**

```json
{
    "catalogId": "<service id from CATALOG_META>",
    "catalogName": "<service name from CATALOG_META>",
    "userLoginId": "<current user login ID>",
    "businessGroupName": "<selected business group name>",
    "resourceBundleName": "<selected resource pool name, omit if useResourceBundle=false>",
    "name": "<user-provided resource name>",
    "resourceSpecs": [
        {
            "node": "<selected catalog instructions.node>",
            "type": "<selected catalog instructions.type>",
            "useResourceBundle": false,  // only when cloudEntryTypeIds is explicitly empty
            "cpu": 2,
            "memory": 4096
        }
    ]
}
```

**Action:** Display confirmation to user in Chinese. Ask: "请确认以上信息是否正确？（是/否）"

**STOP - Wait for user confirmation**

---

### R4: Submit [Execute]

```bash
python scripts/submit.py --file request.json
```

**Complete** - Display request ID and status to user.

---

## Scripts Reference

| Script | Purpose | Parameters |
|--------|---------|------------|
| `../shared/scripts/list_services.py` | List service catalogs | `[keyword]` |
| `../shared/scripts/list_business_groups.py` | List business groups | `<catalogId>` |
| `../shared/scripts/list_applications.py` | List applications/projects | `<bgId> [keyword]` |
| `../shared/scripts/list_resource_pools.py` | List resource pools | `<bgId> <sourceKey> <nodeType>` |
| `../shared/scripts/list_os_templates.py` | List OS templates | `<osType> <resourceBundleId>` |
| `scripts/submit.py` | Submit request | `--file <json_file>` |

---

## Critical Rules

1. **Display rules (MOST IMPORTANT):**
   - When showing tool output to user, ONLY display the numbered list and the selection prompt (e.g. "请选择...").
   - NEVER display `_internal` field content, META data, Index, Id, Source Key, Service Category, Params, cloudEntryTypeId, or any JSON/technical data to the user.
   - The `_internal` field in tool results contains metadata for your reference only. Parse it silently to extract IDs for subsequent tool calls.
   - After each list, ALWAYS ask user to select with a clear Chinese prompt like "请选择您要申请的服务（输入编号）".
   - STOP and wait for user response after showing each list. Do NOT proceed automatically.
2. **Params-driven workflow:** The `params` array from the selected service's `_internal` metadata is the ONLY source of truth for what tools to call and what to ask the user. Do NOT call tools not declared in params.
3. **Execute only one action per turn.** After displaying output or asking question, MUST STOP and wait for user response.
4. **Never fabricate data.** Only use values from script output or user input.
5. **Ask for required manual input.** If a param has `source: null`, `defaultValue: null`, and `required: true`, you MUST ask the user for that value and STOP.
6. **Never skip required list selections.** If a param has `source: "list:xxx"` and `defaultValue: null`, you MUST call the mapped tool and STOP for user selection.
7. **Never auto-submit.** Must get user confirmation before submission.
8. **Set node and type correctly.** `type` must come from selected catalog `instructions.type`, and `node` must come from selected catalog `instructions.node`.
9. **resourceBundleName required:** When the request uses a selected or defaulted resource pool, the request body top level **must** include `resourceBundleName`.
10. **Preserve selected card metadata.** Once the user selects a service card, keep using that card's saved `sourceKey`, `id`, `name`, `serviceCategory`, `instructions`, and `params` throughout the whole request flow.
11. **No component lookup step.** For cloud-resource requests, use the selected catalog instructions metadata directly. Do not call `smartcmp_list_components`.
12. **Always prefer explicit catalog defaults.** If the selected catalog `params` already provide a non-empty `defaultValue`, use that value silently instead of asking the user or calling another list tool.

---

## PowerShell Environment Notes

> **Important:** PowerShell encoding and parameter passing may cause request failures.

### Use Python to Write JSON Files (Avoid BOM)

```powershell
# [Wrong] PowerShell adds BOM
$body | ConvertTo-Json | Out-File -FilePath request.json -Encoding utf8

# [Correct] Use Python to write JSON
python -c "import json; data = {...}; open('request.json', 'w', encoding='utf-8').write(json.dumps(data, ensure_ascii=False, indent=2))"
```

### Always Use --file Parameter

```powershell
# [Wrong] JSON will be corrupted
python submit.py --json '{"name": "test"}'

# [Correct] Use file input
python submit.py --file request.json
```

---

## References

- [WORKFLOW.md](references/WORKFLOW.md) - Detailed step-by-step workflow
- [PARAMS.md](references/PARAMS.md) - Parameter placement rules
- [EXAMPLES.md](references/EXAMPLES.md) - Request body examples
