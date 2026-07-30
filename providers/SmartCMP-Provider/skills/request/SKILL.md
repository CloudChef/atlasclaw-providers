---
name: "request"
description: "Self-service request skill. Start and continue cloud-resource requests, including numbered or named follow-up selections that require the next live SmartCMP lookup. VM catalogs select a resource pool, flavor, logical OS template, and either a physical template or cloud image. Also handles application environments, ticket and work-order services, and submitted request status."
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
  - 申请状态
  - 查询申请状态
  - 是否审批通过
  - 是否被批准
  - request status

use_when:
  - User wants to request a VM, cloud resource, database, or application environment
  - User wants to submit a self-service request through the service catalog
  - User wants to create a ticket or work order
  - User already knows the service they want and is ready to provide request parameters
  - User is provisioning from a catalog that requires a logical template, physical template, or cloud image
  - User replies with a number or name to continue an active request choice; continue with the next required live SmartCMP lookup
  - User wants multiple instances of the same resource type under one service request with the same parameters
  - User wants to check the status of a submitted SmartCMP request by Request ID
  - User asks whether their submitted request has been approved

avoid_when:
  - User only wants to browse available resources (use datasource skill)
  - User wants to approve or reject requests (use approval skill)
  - User describes requirements in natural language without specific parameters (use request-decomposition-agent)
  - User asks for different resource types that should become separate CMP requests (use request-decomposition-agent)
  - User gives per-instance differences such as first/second/third configurations or different specs per instance (use request-decomposition-agent)
  - User wants to list approval tasks waiting for them or perform approval actions (use approval skill)

examples:
  - "Create a new VM with 2c4g"
  - "Request multiple Linux virtual machines with the same specification"
  - "Provision cloud resources for my project"
  - "Deploy a Linux VM in production environment"
  - "Submit a request for 3 virtual machines"
  - "提交一个问题工单"
  - "申请一个机房资源"
  - "申请2c4g的linux云主机"
  - "帮我查一下我的申请 RES20260501000095 的状态"
  - "帮我查一下我的申请 RES20260501000095 是否已经审批通过"
  - "我刚才提交的申请是否已经被批准了"

related:
  - datasource
  - approval
  - request-decomposition-agent

# === Tool Registration ===
tool_list_services_name: "smartcmp_list_services"
tool_list_services_description: "List available service catalog choices from SmartCMP. Call this tool ONLY ONCE at the beginning of a new request workflow. It returns compact catalog identity metadata, not request-field instructions. After receiving the list, check whether the user's original message clearly matches a specific catalog. If so, auto-select it; otherwise show the numbered list. Displayed numbers are conversation choices only. Resolve the selected number to the catalog metadata UUID, then call smartcmp_get_request_catalog before inspecting fields or calling any catalog-dependent lookup. Keep returned _internal metadata for workflow use only; do not show those fields to the user."
tool_list_services_entrypoint: "scripts/list_request_catalogs.py"
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
tool_catalog_detail_name: "smartcmp_get_request_catalog"
tool_catalog_detail_description: "Load the normalized request-field instructions for exactly one catalog selected from smartcmp_list_services. catalog_id MUST be the selected catalog metadata UUID, never a displayed number or sourceKey. Call once immediately after catalog selection and before smartcmp_list_available_bgs or request-field assembly. Keep returned _internal metadata for workflow use only."
tool_catalog_detail_entrypoint: "scripts/get_request_catalog.py"
tool_catalog_detail_group: "cmp"
tool_catalog_detail_capability_class: "provider:smartcmp"
tool_catalog_detail_priority: 105
tool_catalog_detail_cli_positional:
  - catalog_id
tool_catalog_detail_parameters: |
  {
    "type": "object",
    "properties": {
      "catalog_id": {
        "type": "string",
        "description": "REQUIRED. Selected catalog UUID from smartcmp_list_services metadata."
      }
    },
    "required": ["catalog_id"]
  }
tool_submit_name: "smartcmp_submit_request"
tool_submit_description: "Submit resource request to SmartCMP. RULES: (1) NEVER claim submitted without calling this tool. (2) Reuse resolved workflow lookup evidence, build the preview from the exact generated instruction contract, mask credential secrets, and wait for user confirmation BEFORE calling. (3) json_body is REQUIRED. (4) catalogId MUST be UUID from catalog metadata id field. (5) Same-type multi-instance requests must use the selected catalog's declared count field, or fallback top-level quantity when no such field exists, without duplicating resourceSpecs; per-instance differences belong in request-decomposition-agent. See Field Placement table in skill body for exact structure rules."
tool_submit_entrypoint: "scripts/submit.py"
tool_submit_groups:
  - cmp
  - request
  - mutation
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
        "description": "REQUIRED. The complete request JSON as a string. For cloud/resource requests: include catalogId, catalogName, businessGroupId, name, resourceSpecs built from generated Markdown instructions.resourceSpecs, and optional top-level params built from instructions.params. Put resourceBundleId at resourceSpecs[].resourceBundleId, resourceBundleTags at resourceSpecs[].resourceBundleTags, resourceBundleParams under resourceSpecs[].resourceBundleParams, resource-spec params under resourceSpecs[].params, resource-spec fields under resourceSpecs[] directly, and catalog form params under top-level params. For same-type multi-instance requests, use the selected catalog's declared quantity/count field in its declared location; when no catalog field exists, add top-level quantity. Do not duplicate resourceSpecs just to represent count. If resourceBundleTags is used, omit resourceBundleId for the same resource spec. For tickets: build genericRequest.description and optional genericRequest.processForm from generated Markdown instructions.genericRequest; for tickets without Markdown, include catalogId, catalogName, businessGroupId, name, and genericRequest {description}. Do NOT include userLoginId (auto-injected by script). FORBIDDEN fields: never add priority, category, requestor, parameters, impactScope, urgency, contactName, or any field not listed above. DO NOT omit this parameter."
      }
    },
    "required": ["json_body"]
  }
tool_submit_success_contract:
  type: "identifier_presence"
  fields:
    - "requestId"
  text_labels:
    - "Request ID"
  note: "Only user-facing SmartCMP Request IDs count as successful submit identifiers. Normalize source aliases to a single user-facing Request ID and never expose UUID-shaped internal identifiers as the submitted Request ID."
tool_status_name: "smartcmp_get_request_status"
tool_status_description: "Query a submitted SmartCMP request status by user-facing Request ID, e.g. REQ20260501000095, RES20260501000095, TIC20260316000001, or CHG20260413000011. Use only for submitted request status or approval-result questions. For recent-submission follow-ups without an explicit ID, reuse the most recent Request ID from this conversation; if none exists, ask for it. Do NOT pass internal UUIDs, approve, or reject requests."
tool_status_entrypoint: "scripts/status.py"
tool_status_groups:
  - cmp
  - request
tool_status_capability_class: "provider:smartcmp"
tool_status_priority: 155
tool_status_result_mode: "silent_ok"
tool_status_cli_positional:
  - request_id
tool_status_use_when:
  - "User asks for submitted request status or approval result"
  - "User provides a Request ID, or the current conversation contains a recent submitted Request ID"
tool_status_avoid_when:
  - "User wants to approve or reject a request (use approval skill)"
  - "User wants to list pending approval tasks waiting for them (use approval skill)"
tool_status_parameters: |
  {
    "type": "object",
    "properties": {
      "request_id": {
        "type": "string",
        "description": "SmartCMP user-facing Request ID returned by submit, e.g. REQ20260501000095, RES20260501000095, TIC20260316000001, or CHG20260413000011. Do not pass internal UUIDs."
      }
    },
    "required": ["request_id"]
  }
tool_facets_name: "smartcmp_list_facets"
tool_facets_description: "List available resource pool tag facets from SmartCMP. REQUIRES businessGroupId — call this AFTER business group is selected and ONLY when request Markdown declares active resourceBundleTags without a default. After this tool returns, do not call datasource tools to interpret facets. Match or ask for a facet option, then build resourceBundleTags with facet key and option key (NOT display names). Never show raw facet metadata."
tool_facets_entrypoint: "scripts/list_facets.py"
tool_facets_group: "cmp"
tool_facets_capability_class: "provider:smartcmp"
tool_facets_priority: 110
tool_facets_result_mode: "silent_ok"
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
tool_resource_bundles_name: "smartcmp_list_resource_bundles"
tool_resource_bundles_description: "List request-flow resource pools from SmartCMP. Use when generated Markdown declares an active resourceBundleId field without a default and no active resourceBundleTags field. Requires selected business_group_id, component_type from generated Markdown catalog/component metadata, and node_type from resourceSpecs[].type. Fixed API filters: strategy=RB_POLICY_STATIC, enabled=true, readOnly=false. If resourceBundleId has ask:true, present the returned names and wait for the user's selection even when only one result exists. Ask the user to identify the resource-pool field and selected number when replying; never suggest that a bare number is sufficient."
tool_resource_bundles_entrypoint: "scripts/list_resource_bundles.py"
tool_resource_bundles_group: "cmp"
tool_resource_bundles_capability_class: "provider:smartcmp"
tool_resource_bundles_priority: 112
tool_resource_bundles_cli_positional:
  - business_group_id
  - component_type
  - node_type
tool_resource_bundles_cli_flag_overrides:
  cloud_entry_type_id: "--cloud-entry-type-id"
tool_resource_bundles_parameters: |
  {
    "type": "object",
    "properties": {
      "business_group_id": {
        "type": "string",
        "description": "REQUIRED. UUID of the selected business group."
      },
      "component_type": {
        "type": "string",
        "description": "REQUIRED. Component resource type from generated Markdown catalog.component_type, falling back to the selected catalog sourceKey only when catalog.component_type is absent."
      },
      "node_type": {
        "type": "string",
        "description": "REQUIRED. Node type from generated Markdown resourceSpecs[].type."
      },
      "cloud_entry_type_id": {
        "type": "string",
        "description": "Optional cloud entry type id filter. Omit or pass empty string when not declared."
      }
    },
    "required": ["business_group_id", "component_type", "node_type"]
  }
tool_bgs_name: "smartcmp_list_available_bgs"
tool_bgs_description: "List available business groups for a specific service catalog. Call this AFTER selecting a catalog to get the list of business groups the user can choose from. catalog_id MUST be the selected catalog metadata UUID, never the displayed list number. Use the returned id or name (depending on the catalog parameter key) for the business group field in the request body."
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
tool_flavors_description: "List requestable MACHINE compute flavors from SmartCMP. Pass resource_bundle_id after resource-pool selection so SmartCMP filters by pool; also pass catalog_id and node_template_name when known so catalog alternatives apply. node_template_name is the literal resourceSpecs[].node value such as Compute, never resourceSpecs[].type. Omit resource_bundle_id only for an intentional global flavor query. Match the user's spec (for example 2c4g) against the returned name and use the selected id as computeProfileId. If computeProfileId has ask:true, show the filtered flavor names and ask the user to identify the flavor field and selected number instead of replying with a bare number or typed specification."
tool_flavors_entrypoint: "scripts/list_flavors.py"
tool_flavors_group: "cmp"
tool_flavors_capability_class: "provider:smartcmp"
tool_flavors_priority: 108
tool_flavors_use_when:
  - "Generated Markdown declares an active computeProfileId without a default, after resource pool selection and before any template lookup"
tool_flavors_cli_flag_overrides:
  query: "--query"
  resource_bundle_id: "--resource-bundle-id"
  catalog_id: "--catalog-id"
  node_template_name: "--node-template-name"
tool_flavors_parameters: |
  {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Optional search keyword to filter flavors"
      },
      "resource_bundle_id": {
        "type": "string",
        "description": "Optional selected resource pool ID. Provide it during request provisioning; omit it only for a global flavor query."
      },
      "catalog_id": {
        "type": "string",
        "description": "Optional selected catalog UUID."
      },
      "node_template_name": {
        "type": "string",
        "description": "Optional literal resourceSpecs[].node, for example Compute; never pass resourceSpecs[].type."
      }
    }
  }
tool_logical_templates_name: "smartcmp_list_logical_templates"
tool_logical_templates_description: "List logical OS templates for a SmartCMP request. Call only after resource-pool and compute-profile selection when generated Markdown declares logicTemplateId. Pass resource_bundle_id and the required catalog OS family as os_type; also pass catalog_id and node_template_name when known. Use the selected id as logicTemplateId. The request-projected tool always presents the names as an explicit selection boundary, even when one result exists or generated ask is false."
tool_logical_templates_entrypoint: "../datasource/scripts/list_logical_templates.py"
tool_logical_templates_groups:
  - cmp
  - request
tool_logical_templates_capability_class: "provider:smartcmp"
tool_logical_templates_priority: 112
tool_logical_templates_result_mode: "llm"
tool_logical_templates_use_when:
  - "Generated Markdown declares an active logicTemplateId without a default, after resource pool and compute-profile selection"
tool_logical_templates_avoid_when:
  - "An active computeProfileId without a default has not been selected yet"
tool_logical_templates_cli_positional:
  - query
tool_logical_templates_cli_flag_overrides:
  resource_bundle_id: "--resource-bundle-id"
  catalog_id: "--catalog-id"
  node_template_name: "--node-template-name"
  os_type: "--os-type"
tool_logical_templates_parameters: |
  {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Optional logical-template-name filter."
      },
      "resource_bundle_id": {
        "type": "string",
        "description": "REQUIRED during provisioning. Selected resource pool ID."
      },
      "catalog_id": {
        "type": "string",
        "description": "Optional selected catalog UUID."
      },
      "node_template_name": {
        "type": "string",
        "description": "Optional resourceSpecs[].node."
      },
      "os_type": {
        "type": "string",
        "description": "REQUIRED. Catalog OS family inferred from the selected catalog and user request, for example Linux or Windows."
      }
    },
    "required": ["resource_bundle_id", "os_type"]
  }
tool_physical_templates_name: "smartcmp_list_physical_templates"
tool_physical_templates_description: "List physical templates available to the selected SmartCMP resource pool and logical template. Use only when generated Markdown declares physicalTemplateId. Each result retains its logicTemplateId; use the selected physicalTemplateId together with logicTemplateId and omit templateId. If physicalTemplateId has ask:true, present names and ask the user to identify the physical-template field and selected number even when one result exists."
tool_physical_templates_entrypoint: "scripts/list_physical_templates.py"
tool_physical_templates_groups:
  - cmp
  - request
tool_physical_templates_capability_class: "provider:smartcmp"
tool_physical_templates_priority: 114
tool_physical_templates_result_mode: "silent_ok"
tool_physical_templates_use_when:
  - "Generated Markdown declares an active physicalTemplateId without a default, after resource pool and logicTemplateId selection"
tool_physical_templates_avoid_when:
  - "An active computeProfileId or logicTemplateId without a default has not been selected yet"
tool_physical_templates_cli_positional:
  - resource_bundle_id
  - logic_template_id
tool_physical_templates_parameters: |
  {
    "type": "object",
    "properties": {
      "resource_bundle_id": {
        "type": "string",
        "description": "REQUIRED. Selected resource pool ID."
      },
      "logic_template_id": {
        "type": "string",
        "description": "REQUIRED. Selected logicTemplateId from the resource-pool-filtered logical-template lookup."
      }
    },
    "required": ["resource_bundle_id", "logic_template_id"]
  }
tool_images_name: "smartcmp_list_images"
tool_images_description: "List cloud images for a SmartCMP request. Call after resource-pool and logical-template selection only when generated Markdown declares templateId. Use the selected image id as templateId, never as physicalTemplateId. If templateId has ask:true, present image names and ask the user to identify the image field and selected number even when one result exists."
tool_images_entrypoint: "../datasource/scripts/list_images.py"
tool_images_groups:
  - cmp
  - request
tool_images_capability_class: "provider:smartcmp"
tool_images_priority: 113
tool_images_result_mode: "llm"
tool_images_use_when:
  - "Generated Markdown declares an active templateId without a default, after resource pool and logicTemplateId selection"
tool_images_avoid_when:
  - "An active computeProfileId or logicTemplateId without a default has not been selected yet"
tool_images_cli_positional:
  - resource_bundle_id
  - logic_template_id
  - cloud_entry_type
tool_images_parameters: |
  {
    "type": "object",
    "properties": {
      "resource_bundle_id": {
        "type": "string",
        "description": "REQUIRED. Selected resource pool ID."
      },
      "logic_template_id": {
        "type": "string",
        "description": "REQUIRED. Selected logicTemplateId."
      },
      "cloud_entry_type": {
        "type": "string",
        "description": "REQUIRED. Selected resource pool cloudEntryTypeId."
      }
    },
    "required": ["resource_bundle_id", "logic_template_id", "cloud_entry_type"]
  }
---

# request

Submit cloud resource, application environment, or ticket/work order requests through the service catalog.

## Flow

The request workflow owns request-projected
`smartcmp_list_logical_templates` and `smartcmp_list_images` tools. They reuse
the same read-only scripts as the datasource global-query tools, but remain
visible when AtlasClaw projects only the `cmp.request` capability.

### Multi-resource routing boundary

This skill is for one CMP request flow at a time. That single flow may still
represent one service catalog / one resource type / one shared parameter set
with quantity N.

Keep the request in this skill when the user wants multiple instances of the
same resource type with the same configuration, for example:

- "several identical Linux VMs for one project"
- "multiple instances of the same database service with shared parameters"
- "quantity N of one resource type with one shared parameter set"

Route to `request-decomposition-agent` only when the request needs to be split
into distinct sub-requests, especially when the user gives:

- multiple resource types in one ask
- per-instance differences such as "first ..., second ..., third ..."
- different specs per instance
- mixed roles/components that should become separate CMP requests

Quantity by itself is **not** a decomposition signal. The request workflow and
submit tool should interpret same-type quantity from the user's original
language without requiring AtlasClaw core to pre-structure `resource_count`.

When this boundary is hit, do not continue with the single-catalog parameter
collection flow in this skill.

### Single-instance vs shared-quantity contract

This skill supports two request shapes, and they are not interchangeable:

- **Single-instance request**: one resource type, one instance, one
  `resourceSpecs` item, and no top-level count field unless the selected
  catalog explicitly requires one.
- **Same-type multi-instance request**: one resource type, one shared
  parameter set, one explicit quantity value from the selected catalog schema
  or fallback `quantity`, with `resourceSpecs` following the selected catalog
  schema.

For same-type multi-instance requests:

- Read the selected catalog instructions before choosing the quantity key. If
  an active field in `instructions.topLevelFields` or `instructions.params`
  clearly declares instance quantity, use that exact key and location. Do not
  choose from a fixed alias list.
- If the selected catalog does not declare a quantity/count field, use fallback
  top-level `quantity`.
- When the selected catalog has one `instructions.resourceSpecs` item, keep one
  shared `resourceSpecs` item for the shared parameter set.
- When the selected catalog declares multiple `instructions.resourceSpecs`
  items, build each declared item exactly once; do not treat the number of
  specs as the requested instance count.
- Do **not** duplicate identical `resourceSpecs` entries just to represent
  quantity N.
- Do **not** invent per-instance names, hostnames, IPs, disk sizes, or other
  per-instance overrides when the user asked for shared parameters.
- If the user supplies per-instance differences, separate names for each
  instance, or mixed component roles, stop using this skill and route to
  `request-decomposition-agent`.

Do not infer decomposition solely from `resourceSpecs` length. A single catalog
can legitimately declare multiple resource specs. Decomposition is driven by
user semantics, such as separate CMP requests or per-instance differences, not
by a submit-script spec-count heuristic.

### Submitted request status flow

Use `smartcmp_get_request_status` only for submitted request status or
approval-result checks. Pass an explicit Request ID when present. For "刚才提交的
申请", reuse the most recent `smartcmp_submit_request` Request ID in this
conversation; if none exists, ask for the Request ID. Request IDs are
user-facing values such as `REQ20260501000095`, `RES20260501000095`,
`TIC20260316000001`, or `CHG20260413000011`. Never pass UUID-shaped internal
identifiers to the status tool.

The status script returns structured fields only. Treat the tool output as
lookup data, not final user-facing text. Explain the result in the current user's message language using
`state`, `statusCategory`, `approvalPassed`, `currentStep`, `currentApprover`,
`provisionState`, `error`, and `updatedAt`.

Status semantics:
- `APPROVAL_PENDING`: not approved yet; approval is still pending.
- `APPROVAL_REJECTED` / `APPROVAL_RETREATED`: not approved; rejected or returned.
- `STARTED` / `TASK_RUNNING` / `WAIT_EXECUTE` / `FINISHED`: approval has passed or the request has entered later execution.
- `INITIALING` / `INITIALING_FAILED` / `FAILED` / `CANCELED`: report the current state as initialization, failure, or cancellation; do not claim approval or rejection.

### Complete flow

1. Call `smartcmp_list_services` once. Auto-select a catalog only when the
   user's wording clearly matches one returned catalog; otherwise ask a
   numbered catalog-selection question.
2. Call `smartcmp_get_request_catalog` once with the selected catalog UUID to
   load only that catalog's generated request instructions.
3. Call `smartcmp_list_available_bgs` with the selected catalog UUID. If one
   business group is returned, use it. If multiple are returned, ask a concise
   numbered question using display names only and wait for the user's
   selection. Do not show business group IDs to the user.
4. Before asking for request fields, check the selected catalog metadata. If a
   ticket/work-order catalog (`serviceCategory: "GENERIC_SERVICE"`) has
   `instructions.genericRequest`, build from that metadata. If a cloud/resource
   catalog has no `instructions.resourceSpecs` but its selected catalog metadata
   has `type: "cloudchef.nodes.Compute"`, use the Compute fallback below. If it
   has no Markdown and is not Compute, stop and explain that the catalog is
   missing generated Markdown instructions.
5. Build the request from the selected catalog's generated Markdown metadata:
   `instructions.resourceSpecs`, `instructions.genericRequest`, and
   `instructions.topLevelFields`.
6. Ask only for active required fields with no default, plus fields explicitly
   marked `ask: true`. Defaults are used silently.
7. Reuse resolved workflow lookup evidence, show a schema-exact JSON preview
   with credential secrets masked, ask for confirmation, and stop.
8. After the user confirms, call `smartcmp_submit_request` with the preview JSON.

Steps 1 through 3 are mandatory for every new request. Never ask the user to type a
business group before calling `smartcmp_list_available_bgs`.

### Catalog identity contract

- Displayed service list numbers are conversation choices only. Resolve them
  against the latest `smartcmp_list_services` result.
- Preserve each returned `index` when displaying a filtered subset; never
  renumber catalog choices in the assistant response.
- A catalog-selection question MUST show the exact returned `index` at the
  start of every option line, for example `3. LinuxOS`. Never ask the user to
  reply with a number unless those numbers are visible in the response.
- `catalogId` must be the selected catalog metadata UUID, never the displayed
  list number and never `sourceKey`.
- After catalog selection, the next tool call must be
  `smartcmp_get_request_catalog` with that UUID. After the selected catalog
  detail returns, call `smartcmp_list_available_bgs` with the same UUID.
- There is no catalog questionnaire/default-property/preview tool in this
  skill. Do not invent one.

### Tool sequencing

- Resolve request lookup fields in dependency order:
  `resourceBundleId` -> compute profile -> `logicTemplateId` ->
  `physicalTemplateId` or `templateId`. Do not call tools for two unresolved
  `ask: true` fields in one model response.
- After `resourceBundleId` is selected, `smartcmp_list_flavors` is the only
  valid next lookup while an active `computeProfileId` remains unresolved. Do
  not call any logical-template, physical-template, or image lookup first.
- For each active generated field with `ask: true`, call only that field's
  lookup, present only its current choices, ask the user to select one, and
  stop. Do not ask for later lookup fields, request name, or credentials in the
  same reply. A numbered or named answer paired with the pending field meaning
  requires the next live lookup.
- Phrase every selection reply with the pending field meaning so AtlasClaw
  routes the follow-up back to this live workflow. Ask the user to identify the
  resource pool, flavor, logical template, physical template, or image field
  together with the selected number and intent to continue. Do not tell the
  user that a bare number alone is sufficient.
- Stop after a lookup whenever the user must choose among multiple unresolved
  options. Ask at most one concise question and wait for the answer.
- When all required choices already have one unambiguous match from the user's
  wording, or a single returned option for a field that is not marked
  `ask: true`, noninteractive request lookups may
  chain in dependency order in the same turn. This includes
  `smartcmp_list_resource_bundles`, `smartcmp_list_flavors`,
  `smartcmp_list_physical_templates`, and `smartcmp_list_images`. A field marked
  `ask: true` must show its choices and wait even when the lookup returns one
  option. The request-projected `smartcmp_list_logical_templates` is a
  deliberate stricter boundary: it always ends the turn with a displayed list
  so logical-template IDs cannot be silently confused with flavor or image IDs.
- During mandatory catalog discovery, when the initial list has one
  clear automatic match, `smartcmp_list_services` may be followed by
  `smartcmp_get_request_catalog` and then `smartcmp_list_available_bgs` in the
  same user turn. When the user must choose a catalog, stop after the list and
  continue with detail plus business-group lookup after their selection.
- `smartcmp_get_request_catalog` is a schema-loading step, not a user-facing
  lookup. It may be followed by `smartcmp_list_available_bgs` in the same turn
  so catalog selection does not create an empty conversational round trip.
- After a lookup result that needs user input, summarize the selectable result
  in natural language and ask at most one next question. When no user choice is
  needed, preserve the compact lookup evidence and continue the resolver chain.
- Do not paste raw tool output, `_internal` metadata, UUID dumps, or JSON meta
  blocks into the reply.
- If the previous assistant message asked the user to choose a business group
  and the user replies with a bare number or group name, treat it as a business
  group selection, never as an unsupported operation.
- In a tool-required turn after a business group selection, call
  `smartcmp_list_available_bgs` again with the same selected catalog UUID to
  refresh the business group list, resolve the user's selection against that
  result, then continue with generated Markdown, Compute fallback, or the JSON
  preview.
- During request building, do not call unrelated discovery tools such as
  `smartcmp_list_components` or `smartcmp_list_applications`. Use the
  request-projected logical-template and image tools declared above.

## User Response Language

- Use the current user's language for user-facing replies.
- Keep JSON keys, API fields, catalog names, provider names, and tool names
  unchanged.
- In Chinese user-facing text, always call SmartCMP resource pools `资源池`.
  Never call them `资源包`. Keep API field names such as `resourceBundleId` and
  `resourceBundleTags` unchanged inside JSON or code.

## Generated Markdown Instructions

Catalog `instructions` is expected to be the Markdown generated by the Java
catalog instruction builder. For request building, only these sections are in
scope:

- `# Request Parameter Instructions`: YAML parameter contract.
- `# Request Instructions`: optional request-building guidance.

`smartcmp_get_request_catalog` exposes the selected catalog's parsed
`# Request Parameter Instructions` YAML as metadata:

- `instructions.topLevelFields`
- `instructions.topLevelRequired`
- `instructions.params`
- `instructions.genericRequest`
- `instructions.resourceSpecs`
- `instructions.requestInstructions` from exactly `# Request Instructions`,
  when that section exists

Ignore old JSON instruction payloads. Do not use `instructions.parameters` or
legacy raw `params` as the request schema. Use `instructions.params` only when
it is parsed from `# Request Parameter Instructions`.

### Instruction section boundary

The catalog Markdown body may contain multiple instruction sections, such as
`# Request Parameter Instructions`, `# Request Instructions`,
`# Preapproval Instructions`, or other future sections. For this request skill,
only `# Request Parameter Instructions` and `# Request Instructions` are in
scope.

- Read `# Request Parameter Instructions` first; it is the authoritative schema
  contract.
- The `# Request Instructions` section is optional. If it is absent, use
  `# Request Parameter Instructions` only.
- For free-form Markdown instructions, read only the content under exactly
  `# Request Instructions`.
- Stop reading request instructions at the next same-level heading that starts
  with `# `, such as `# Preapproval Instructions`.
- Never fall through to `# Preapproval Instructions` or any other section when
  `# Request Instructions` is missing.
- Ignore all other sections for request building. They must not change required
  fields, defaults, `when` behavior, resource tag handling, payload shape, or
  submit/preview behavior.
- A catalog body with only `# Preapproval Instructions` has no request-body
  instructions. It is still requestable only if `# Request Parameter
  Instructions` contains enough request schema metadata.

### Markdown field rules

- Top-level JSON always includes `catalogId`, `catalogName`,
  `businessGroupId`, and `name`.
- For same-type multi-instance requests with shared parameters, fill the
  selected catalog's declared quantity field in its exact declared location. If
  none exists, use fallback top-level `quantity`. Keep `resourceSpecs` aligned
  to the selected catalog schema; for a single-spec catalog, use one shared
  `resourceSpecs[]` item.
- Quantity alone does not require decomposition; per-instance differences do.
- Generated field attributes belong in `# Request Parameter Instructions`, not
  in the `# Request Instructions` prose. Keep field metadata such as `type`,
  `required`, `defaultValue`, `default_value`, `when`, `ask`, `label`,
  `description`, `source`, lookup hints, and selectable values on the declared
  field itself.
- If an active field declares static `options`, use option `id` as the payload
  value and display option labels only as user-facing help.
- Do not add a second field-property list after body text such as "Do not
  invent fields that are not declared in `# Request Parameter Instructions`."
  Treat the body as generic request guidance only.
- If `topLevelFields.name.ask: true` and the user has not supplied a name, ask
  for the request/resource name. Do not auto-generate it. For a resource request
  with unresolved live lookup fields, defer this question until the generated
  `resourceSpecs[]` lookup sequence is complete; in particular, never ask for
  `name` before an unresolved `resourceBundleId`.
- Do not include `userLoginId`; `submit.py` injects it.
- Put root request fields declared in `instructions.params.<key>` under the
  top-level JSON object `params.<key>`. These are catalog form fields from
  `catalog.form_definition_id`, not resource spec fields.
- Root `instructions.params` fields follow the same active-field rules as
  resource fields: evaluate `when`, use defaults silently, show static
  `options`, ask only for active required/no-default or `ask: true` fields, and
  omit inactive or empty optional fields.
- Do not put root `instructions.params` fields into
  `resourceSpecs[].params`. Do not put `resourceSpecs[].params` fields into the
  top-level `params` object.
- For ticket/work-order catalogs (`serviceCategory: "GENERIC_SERVICE"`) with
  `instructions.genericRequest`, build a `genericRequest` object instead of
  `resourceSpecs`. Put `instructions.genericRequest.description` at
  `genericRequest.description`. Put fields declared under
  `instructions.genericRequest.processForm.<key>` at
  `genericRequest.processForm.<key>`. Follow the same active-field rules:
  evaluate `when`, use defaults silently, ask only for active required/no-default
  or `ask: true` fields, and omit inactive or empty optional fields.
- For each `instructions.resourceSpecs[]`, create one `resourceSpecs[]` item
  and copy `node` and `type` exactly when present.
- Treat field schemas declared directly on `instructions.resourceSpecs[]`,
  other than `node`, `type`, `resourceBundleId`, `resourceBundleTags`,
  `resourceBundleParams`, and `params`, as direct resource spec fields. Put each
  active value directly on the same `resourceSpecs[]` item as `<key>`. These
  fields are for special resources such as Compute/VM, where SmartCMP expects
  values like `computeProfileId`, `flavorId`, `logicTemplateId`, `templateId`,
  `physicalTemplateId`,
  `credentialUser`, `credentialPassword`, `networkId`, `securityGroupIds`, or
  `systemDisk` at `resourceSpecs[]` level rather than under `params`.
- Preserve each direct field's declared type from Markdown. In particular,
  serialize Compute `securityGroupIds` as a JSON array of security group id
  strings, even when only one security group is selected; never serialize it as
  a single string or comma-separated string.
- Direct resource spec fields declared with `type: "object"` must be serialized
  as JSON objects at `resourceSpecs[]` level. For Compute `systemDisk`, preserve
  the object shape from Markdown or user input, for example
  `"systemDisk": {"size": <disk size>}`. Never serialize `systemDisk` as a raw
  number or string, and never move it under `params`.
- For direct Compute fields, use the exact field names declared by generated
  Markdown, such as `computeProfileName`, `cpu`, and `memory`. Do not replace
  them with alternate fields such as `computeProfileId` unless the selected
  catalog declares those alternate fields.
- Do not create or consume a literal `fields` object. Direct resource spec
  fields must be declared directly on `instructions.resourceSpecs[]`.
- Put `resourceBundleTags` at the same level as `resourceBundleId`,
  `resourceBundleParams`, and `params` in Markdown. If it is active and has no
  `defaultValue` / `default_value`, call `smartcmp_list_facets` after
  business group selection with `node_type` from that spec's `type`, then ask
  the user to choose resource tags. Serialize selected values at
  `resourceSpecs[].resourceBundleTags` as `["<facet.key>:<option.key>"]`.
- `resourceBundleTags` and `resourceBundleId` are mutually exclusive for the
  same `resourceSpecs[]` item. If both are declared and active, use
  `resourceBundleTags` and omit both `resourceBundleId` and
  `resourceBundleParams`.
- If `resourceBundleId.defaultValue` exists and no active `resourceBundleTags`
  is used for that spec, put that value at `resourceSpecs[].resourceBundleId`.
- If an active `resourceBundleId` has no default and no active
  `resourceBundleTags`, call `smartcmp_list_resource_bundles` after business
  group selection and ask the user to choose one. Use the selected bundle `id`
  at `resourceSpecs[].resourceBundleId`.
- For `smartcmp_list_resource_bundles`, pass `business_group_id` from the
  selected business group, `node_type` from `resourceSpecs[].type`, and
  `component_type` from `instructions.componentType` / catalog
  `component_type`, falling back to catalog `sourceKey` only when generated
  Markdown does not declare it.
- Put `resourceBundleParams.<key>` values under
  `resourceSpecs[].resourceBundleParams.<key>`.
- `resourceBundleParams` is only for defaulted resource-pool placement fields
  declared there, such as `available_zone_id` and `resource_group_id`. Include
  those fields only when they already have a non-empty default value. Do not ask
  the user for missing `resourceBundleParams`; omit them instead. VPC, VSwitch,
  subnet, security group, and other network configuration fields must be under
  `resourceSpecs[].params` unless generated Markdown declares them directly on
  the resource spec, such as Compute `networkId` and `securityGroupIds`.
- Put `params.<key>` values under `resourceSpecs[].params.<key>`.
- External API lookup fields such as VPC, VSwitch, subnet, security group, and
  table-async selections should appear in generated Markdown only when they
  already have a non-empty default. If old Markdown still declares one of
  these lookup fields without a default, omit it and do not ask the user for an
  internal id.
- `logicTemplateId` is the independent logical OS-template field. When it is
  active without a default, query logical templates with the selected
  `resourceBundleId` plus catalog/node/OS filters and serialize the selected
  logical-template `id` as `resourceSpecs[].logicTemplateId`.
- `physicalTemplateId` and `templateId` are alternative concrete-template
  branches, not aliases. Follow only fields declared by generated Markdown:
  select a physical template for an active `physicalTemplateId`, or select a
  cloud image for an active `templateId`.
- The physical branch serializes `logicTemplateId + physicalTemplateId` and
  omits `templateId`. The image branch serializes
  `logicTemplateId + templateId` and omits `physicalTemplateId`. Never
  serialize both concrete-template fields and never put a cloud-image ID in
  `physicalTemplateId`.
- When generated Markdown declares both concrete-template branches, prefer a
  configured physical template. If none exists, use the image branch only when
  `templateId` is also active. When only `physicalTemplateId` is active and no
  physical template exists, stop and report the catalog/resource-pool
  configuration issue.
- Use `defaultValue` / `default_value` silently. Do not ask the user whether to
  modify a default.
- When an active field has static `options`, always show the option labels and
  ids as user-facing help when collecting remaining fields or showing the
  preview summary. This applies even when the field has a default. Do not ask a
  blocking question only for that defaulted field, but make alternatives clear
  so the user can override the default before confirmation.
- Format defaulted static options like:
  `地址类型: 默认 internet（公网）；可选：internet=公网，intranet=私网`.
- Ask only when an active required field has no default, or when a field has
  `ask: true`, except missing `resourceBundleParams` values, which are omitted.
- Optional fields without a user value or non-empty default are omitted.
- Never serialize metadata keys such as `type`, `required`, `defaultValue`,
  `default_value`, `when`, `source`, `label`, `ask`, or `options`.

### `when` rules

- Evaluate `when` before asking or serializing a field.
- If `when` is false, the field is inactive: do not ask for it and do not
  include its default.
- Evaluate from already resolved values in the same spec.
- Treat unquoted right-hand words as string literals:
  `AddressType == intranet` means `AddressType == "intranet"`.
- Boolean values use `true` and `false`.
- If the user explicitly provides a value for a field with a default, use the
  user value and re-evaluate dependent `when` fields.

### Request shape

```json
{
  "catalogId": "<selected catalog UUID>",
  "catalogName": "<selected catalog name>",
  "businessGroupId": "<selected business group id>",
  "name": "<user-provided request name>",
  "quantity": 3,
  "resourceSpecs": [
    {
      "node": "<from instructions.resourceSpecs[].node>",
      "type": "<from instructions.resourceSpecs[].type>",
      "resourceBundleId": "<from resourceBundleId default or selected resource pool id>",
      "resourceBundleTags": ["<facet.key>:<option.key>"],
      "resourceBundleParams": {
        "<key>": "<active value>"
      },
      "<directResourceSpecKey>": "<active value>",
      "params": {
        "<key>": "<active value>"
      }
    }
  ],
  "params": {
    "<key>": "<active value from instructions.params>"
  }
}
```

Omit empty objects. Do not move `resourceBundleId` into either top-level
`params` or `resourceSpecs[].params`, do not put declared `resourceBundleParams`
fields inside any `params`, and do not put network fields inside
`resourceBundleParams`. Never include `resourceBundleId` or
`resourceBundleParams` when `resourceBundleTags` is used in the same spec. Do
not serialize a `fields` wrapper. Serialize each active direct resource-spec
field schema as `resourceSpecs[].<key>`. Same-type multi-instance requests must
use the catalog-declared quantity field or fallback `quantity`; never duplicate
identical `resourceSpecs[]` entries just to represent quantity. Catalogs that
declare multiple `resourceSpecs` should include each declared item once.
For Compute, `securityGroupIds` must be an array, for example
`"securityGroupIds": ["sg-xxxxxxxx"]`.
For Compute, `systemDisk` must be an object, for example
`"systemDisk": {"size": <disk size>}`.

Ticket/work-order generated Markdown request shape:

```json
{
  "catalogId": "<selected catalog UUID>",
  "catalogName": "<selected catalog name>",
  "businessGroupId": "<selected business group id>",
  "name": "<user-provided request name>",
  "genericRequest": {
    "description": "<active value from instructions.genericRequest.description>",
    "processForm": {
      "<key>": "<active value from instructions.genericRequest.processForm>"
    }
  }
}
```

Omit `genericRequest.processForm` when no form fields are declared or active.

## Business-Group Resolution

- Use `smartcmp_list_available_bgs` as the authoritative source.
- If the user already specified a tenant / 租户 / 部门 / BU / 项目 and it
  uniquely matches an available business group, use that business group.
- If multiple groups remain, ask one concise numbered question with group names
  only. Do not display business group UUIDs.
- Use the selected business group's `id` as top-level `businessGroupId`.
- If a request name is still missing when asking for business group selection,
  ask for both in the same sentence, for example: `请回复业务组编号和资源名称，例如：2 slbtest01`.

## Service Selection

- Call `smartcmp_list_services` once at the start of a new request.
- Match user wording against the returned catalog name and service category.
- If the result contains zero catalogs, report that no matching published
  catalog exists and stop the request workflow.
- If multiple catalogs could match, ask a numbered catalog-selection question.
- When the user selects by number, resolve the number to the selected catalog
  metadata UUID, then call `smartcmp_get_request_catalog` with that UUID before
  any catalog-dependent lookup or request-field assembly.

## Runtime Lookups

Use extra lookup tools only when generated Markdown requires or explicitly asks
for a value that cannot be taken from the user or a default.

- `smartcmp_list_facets`: use only when generated Markdown declares an active
  `resourceBundleTags` field without a default. Pass `node_type` from
  `resourceSpecs[].type`. Build tag values as `["<facet.key>:<option.key>"]`
  from the API response.
- `smartcmp_list_resource_bundles`: use only when generated Markdown declares
  an active `resourceBundleId` field without a default and no active
  `resourceBundleTags` field. Pass the selected business group id,
  `component_type`, and `node_type`. The tool applies fixed
  `strategy=RB_POLICY_STATIC`, `enabled=true`, and `readOnly=false` filters.
- `smartcmp_list_flavors`: use only when generated Markdown declares an active
  required compute-profile field without a default and the value must be chosen
  from SmartCMP flavor data, or when the selected catalog is a no-Markdown
  Compute fallback and the user provided a spec such as `2c4g`. During normal
  provisioning, pass the selected `resource_bundle_id`, selected `catalog_id`,
  and `resourceSpecs[].node`; omit the pool only for an intentional global
  query. If the compute-profile field has `ask: true`, show the filtered choices
  and wait even when only one is returned.
- `smartcmp_list_logical_templates`: use after an explicit
  `resourceBundleId` is selected when generated Markdown declares an active
  `logicTemplateId` without a default. Pass the resource pool ID, catalog ID,
  resourceSpecs node, and catalog OS type when known. Omit the resource pool
  only for an intentional global directory query. Use the selected `id` as
  `logicTemplateId`.
- `smartcmp_list_physical_templates`: use only after `logicTemplateId` is
  resolved and generated Markdown declares an active `physicalTemplateId`
  without a default. Pass both selected IDs. Each returned choice retains the
  same `logicTemplateId`; use its `physicalTemplateId` in the physical branch.
  If no physical template exists and `templateId` is active, continue with the
  image lookup. Otherwise stop and report that the selected logical template
  and resource pool have no requestable physical template.
- `smartcmp_list_images`: use only after `logicTemplateId` is resolved and
  generated Markdown declares an active `templateId` without a default. Pass
  the selected resource pool ID and logical-template ID. Use
  `cloudEntryTypeId` from the selected resource-pool metadata as
  `cloud_entry_type`. If that metadata is absent, stop and report the invalid
  resource-pool data. Use the selected image `id` as `templateId`.
- Do not call request lookup tools for fields that already have active,
  usable defaults.

Never ask the user to type `logicTemplateId`, `templateId`,
`physicalTemplateId`, or any template UUID. Present logical-template,
physical-template, and image display names while keeping their IDs as internal
lookup evidence. Serialize the exact branch declared by generated Markdown.

### Facet lookup result handling

After `smartcmp_list_facets` returns, treat the result as selectable resource
tag data only:

- Do not call `smartcmp_list_components` or any other datasource tool to
  interpret facet results.
- Do not display raw facet records, `id`, `aspects`, `createdBy`, timestamps,
  lock versions, deleted flags, or JSON meta blocks.
- Use the compact `FACET_META` data from the tool result. The payload shape is
  `[{ "key": "<facet key>", "label": "<display label>", "options": [{ "key": "<option key>", "label": "<display label>" }] }]`.
- If the user already supplied a tag/environment word, match it against facet
  option `key` or `label`. If exactly one option matches, use it.
- If exactly one active facet and one option are available, use that option.
- Otherwise ask one concise numbered question using display labels only, for
  example: `请选择资源环境：1. 开发 2. 测试 3. 生产`.
- When asking the facet question, stop and wait for the user's answer. Do not
  show a JSON preview in the same reply.
- Store selected tags only as `"<facet.key>:<option.key>"` strings in
  `resourceSpecs[].resourceBundleTags`.

## Missing Markdown

If a cloud/resource catalog has no `instructions.resourceSpecs`, use Compute
fallback only when the selected catalog metadata explicitly has
`type: "cloudchef.nodes.Compute"`. For other cloud/resource catalogs, do not
guess provider-specific request fields and do not submit. Explain that the
catalog is missing generated Markdown instructions.

### Compute fallback

This fallback keeps legacy Linux VM / Windows VM catalogs usable while newer
cloud component catalogs use generated Markdown.

Use Compute fallback only when all of these are true:

- The selected catalog has no `instructions.resourceSpecs`.
- The selected catalog metadata has `type: "cloudchef.nodes.Compute"`.
- Business group has already been resolved through `smartcmp_list_available_bgs`.

Compute fallback sequence:

1. Ask for missing request `name` and `description`, plus VM login user/password
   if they were not provided. Mask `credentialPassword` in previews.
2. Call `smartcmp_list_facets` with the selected `businessGroupId` to choose
   resource pool tags. Use returned `facet.key` and option key, not display
   labels.
3. Call `smartcmp_list_flavors` when the user supplied a spec such as `2c4g`
   only if the active workflow does not already contain an unambiguous flavor
   match. Ask the user to choose a flavor if no unambiguous match exists. Use
   the flavor `id` as `computeProfileId`.
4. Build one `resourceSpecs[]` item using selected catalog `node` and `type`
   when present.

Compute fallback JSON shape:

```json
{
  "catalogId": "<selected catalog UUID>",
  "catalogName": "<selected catalog name>",
  "businessGroupId": "<selected business group id>",
  "name": "<user-provided request name>",
  "description": "<user-provided request description>",
  "resourceSpecs": [
    {
      "node": "<selected catalog node, when present>",
      "type": "cloudchef.nodes.Compute",
      "resourceBundleTags": ["<facet.key>:<option.key>"],
      "computeProfileId": "<flavor id>",
      "credentialUser": "<user-provided login user>",
      "credentialPassword": "<user-provided login password>"
    }
  ]
}
```

For ticket/work-order catalogs (`serviceCategory: "GENERIC_SERVICE"`) without
generated `instructions.genericRequest` Markdown, submit only this minimal shape
after collecting `name` and description:

```json
{
  "catalogId": "<selected catalog UUID>",
  "catalogName": "<selected catalog name>",
  "businessGroupId": "<selected business group id>",
  "name": "<user-provided request name>",
  "genericRequest": {
    "description": "<user-provided description>"
  }
}
```

## Submit Contract

Before submit:

1. Show a short summary in the user's language.
2. Show `JSON 预览` / `JSON Preview` with a fenced JSON block.
3. Mask `credentialPassword` as `"******"`.
4. Ask the user to confirm.
5. Stop. Do not call `smartcmp_submit_request` until the user confirms.

After confirmation:

- User says yes → call `smartcmp_submit_request` with `json_body`.
- User says no → ask what to change.
- Any field added or changed after a preview or failed submission changes the
  request payload and invalidates every earlier confirmation. Show the updated
  summary and JSON preview, then ask for fresh confirmation before the next
  submit attempt.
- A bare number is a selection for the latest displayed list unless the
  immediately previous assistant message displayed a JSON preview and asked for
  confirmation.

## Interaction Rules

- `smartcmp_list_services` at most once per request conversation.
- `smartcmp_get_request_catalog` once after catalog selection and before
  catalog-dependent lookups or request-field assembly.
- `smartcmp_list_available_bgs` is normally called once after catalog
  selection. It may be called one extra time only to resolve a user's business
  group selection in a tool-required turn.
- Never claim submitted unless `smartcmp_submit_request` actually executed.
- Never display raw internal metadata to the user.
