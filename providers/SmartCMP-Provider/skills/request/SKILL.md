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

## Workflow Contract

Use this skill only for self-service request submission. When this skill is selected for the
current turn, the runtime may attach a **Current Workflow Context** section above the loaded
skill body. That section contains structured metadata from recent lookup tools in the same
conversation.

Rules:

- Treat the current turn's workflow context as the authoritative source for previously selected
  catalog cards, business groups, resource pools, templates, images, and other hidden IDs.
- Never rely on stale prose summaries when the structured workflow context disagrees.
- Do not display raw workflow metadata, IDs, source keys, or internal JSON to the user.
- Do not call `list_components.py`.

## Service Selection

1. Call `smartcmp_list_services`.
2. Show only the numbered catalog names and the selection prompt.
3. After the user selects a catalog, use the selected catalog metadata from the current turn's
   workflow context to decide the next step.

## Cloud Request Rules

For cloud requests, the selected catalog metadata from `smartcmp_list_services` is the source
of truth:

- selected catalog `id` -> `catalogId`
- selected catalog `name` -> `catalogName`
- `instructions.node` -> request `node`
- `instructions.type` -> request `type`
- `instructions.osType` -> OS template lookup `os_type`
- if `instructions.osType` is absent, derive `Windows` when `type` or `node` contains
  `windows`; otherwise derive `Linux`
- `instructions.parameters` or `params` -> ordered request parameter list

### CRITICAL: Parameter-Driven Decision Table

**STOP and read before calling ANY lookup tool.** You MUST check each parameter's `source`
field in `instructions.parameters`. Only call a lookup tool when the parameter explicitly
declares a `source` value AND its `defaultValue` is empty. Never infer a lookup from field
names alone.

Process parameters in order. For each parameter, apply exactly one rule:

| # | Condition | Action |
|---|-----------|--------|
| 1 | `source` is non-empty AND `defaultValue` is empty | Call the mapped lookup tool, show result, wait for user selection |
| 2 | `source` is non-empty AND `defaultValue` is non-empty | Use the default silently, do NOT call the lookup tool |
| 3 | `source` is empty AND `defaultValue` is non-empty | Use the default silently |
| 4 | `source` is empty AND `defaultValue` is empty AND `required=true` | Ask the user for input |
| 5 | `source` is empty AND `defaultValue` is empty AND `required=false` | Skip this parameter |

**User-specified values override defaults.** If the user's initial message includes specs
(e.g. "2c4g" means cpu=2, memory=4GB), use those values instead of `defaultValue`.

### Forbidden actions

- If `instructions.parameters` does NOT contain any parameter with
  `source: "list:resource_pools"`, do NOT call `smartcmp_list_resource_pools`.
- If `instructions.parameters` does NOT contain any parameter with
  `source: "list:os_templates"`, do NOT call `smartcmp_list_os_templates`.
- If `instructions.parameters` does NOT contain any parameter with
  `source: "list:images"` or `source: "list:list_images"`, do NOT call `smartcmp_list_images`.
- If `instructions.parameters` does NOT contain any parameter with
  `source: "list:applications"`, do NOT call `smartcmp_list_applications`.
- If a parameter like `resourceBundleName`, `logicTemplateName`, `templateId`, `networkId`,
  `cpu`, `memory`, or any other field already has a non-empty `defaultValue` and no `source`,
  use that value silently. Do NOT call a related list tool.

### Mapped lookups (only when triggered by source field)

- `list:business_groups` -> `smartcmp_list_business_groups(catalog_id=<selected catalog id>)`
- `list:applications` -> `smartcmp_list_applications(business_group_id=<selected business group id>)`
- `list:resource_pools` -> `smartcmp_list_resource_pools(business_group_id=<selected business group id>, source_key=<selected sourceKey>, node_type=<instructions.type>)`
- `list:os_templates` -> `smartcmp_list_os_templates(os_type=<instructions.osType or derived value>, resource_bundle_id=<selected resource pool id>)`
- `list:list_images` or `list:images` -> `smartcmp_list_images(resource_bundle_id=<selected resource pool id>, logic_template_id=<selected os template id>, cloud_entry_type_id=<selected resource pool cloudEntryTypeId>)`

## Ticket / Work Order Rules

When the selected catalog is a generic or problem-service request, collect only the fields
required by that catalog metadata. Do not reuse cloud-only fields such as `resourceSpecs`,
`node`, or `type` unless the selected catalog metadata explicitly requires them.

## Submit Contract

The submit tool accepts `json_body`.

### Step 1: Show preview and ask for confirmation

1. Show a short Chinese summary.
2. Show a heading `JSON 预览`.
3. Show a fenced `json` block with the exact request body that will be submitted.
4. Ask `请确认以上信息是否正确？（是/否）`.
5. **STOP and wait for the user's answer. Do NOT call `smartcmp_submit_request` yet.**

### Step 2: After user confirms

When the user replies "是", "yes", "确认", or any affirmative answer:

- **Immediately call `smartcmp_submit_request`** with the constructed `json_body`.
- Do NOT show the summary or JSON preview again.
- Do NOT ask for confirmation again.
- The submit tool call is the ONLY correct action after user confirmation.

When the user replies "否", "no", or any negative answer:

- Ask what they want to change and go back to collecting that parameter.

### Preview rules

- The preview must reflect the real structure and resolved values that will be submitted.
- Mask sensitive values such as `credentialPassword` as `"******"` in the preview.
- Keep the real value in the actual `json_body` passed to `smartcmp_submit_request`.

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

- Execute only one user-facing step per turn.
- After showing a numbered list, stop and wait for the user's selection.
- After asking for manual input, stop and wait for the user's answer.
- **After the user confirms the JSON preview with "是", immediately call
  `smartcmp_submit_request`. Do NOT repeat the preview or ask again.**
- Never claim a request was submitted unless `smartcmp_submit_request` actually executed in the
  current turn.
- Never display raw `_internal` metadata or hidden JSON to the user.

