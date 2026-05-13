﻿---
name: "request"
description: "Self-service request skill. Request cloud resources, application environments, ticket/work order services, or check submitted request status by Request ID. Keywords: request, provision, deploy, create VM, apply resources, submit ticket, request status, 申请资源, 创建虚拟机, 提交工单, 申请状态."
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
  - User wants to check the status of a submitted SmartCMP request by Request ID
  - User asks whether their submitted request has been approved

avoid_when:
  - User only wants to browse available resources (use datasource skill)
  - User wants to approve or reject requests (use approval skill)
  - User describes requirements in natural language without specific parameters (use request-decomposition-agent)
  - User wants to list approval tasks waiting for them or perform approval actions (use approval skill)

examples:
  - "Create a new VM with 2c4g"
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
tool_list_services_description: "List available service catalogs from SmartCMP. Call this tool ONLY ONCE at the beginning of the workflow. If you already have a catalogId from a previous call, do NOT call this tool again — proceed directly to building the request body and calling smartcmp_submit_request. After receiving the catalog list, check whether the user's original message clearly matches a specific catalog. If so, auto-select it and proceed without asking. Otherwise show the numbered list. Displayed numbers are conversation choices only; if the user replies with a number, resolve it to the selected catalog metadata UUID before calling any next tool. Keep returned _internal metadata for workflow use only; do not show those fields to the user."
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
        "description": "REQUIRED. The complete request JSON as a string. For cloud/resource requests: include catalogId, catalogName, businessGroupId, name, resourceSpecs built from generated Markdown instructions.resourceSpecs, and optional top-level params built from instructions.params. Put resourceBundleId at resourceSpecs[].resourceBundleId, resourceBundleTags at resourceSpecs[].resourceBundleTags, resourceBundleParams under resourceSpecs[].resourceBundleParams, resource-spec params under resourceSpecs[].params, resource-spec fields under resourceSpecs[] directly, and catalog form params under top-level params. If resourceBundleTags is used, omit resourceBundleId for the same resource spec. For tickets: build genericRequest.description and optional genericRequest.processForm from generated Markdown instructions.genericRequest; for tickets without Markdown, include catalogId, catalogName, businessGroupId, name, and genericRequest {description}. Do NOT include userLoginId (auto-injected by script). FORBIDDEN fields: never add priority, category, requestor, parameters, impactScope, urgency, contactName, or any field not listed above. DO NOT omit this parameter."
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
tool_resource_bundles_description: "List request-flow resource pools from SmartCMP. Use only when generated Markdown declares an active resourceBundleId field without a default and no active resourceBundleTags field. Requires selected business_group_id, component_type from generated Markdown catalog/component metadata, and node_type from resourceSpecs[].type. Fixed API filters: strategy=RB_POLICY_STATIC, enabled=true, readOnly=false."
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

Seven tools exist: `smartcmp_list_services`, `smartcmp_list_available_bgs`, `smartcmp_list_flavors`, `smartcmp_list_facets`, `smartcmp_list_resource_bundles`, `smartcmp_submit_request`, and `smartcmp_get_request_status`.

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
2. Call `smartcmp_list_available_bgs` with the selected catalog UUID. If one
   business group is returned, use it. If multiple are returned, ask a concise
   numbered question using display names only and wait for the user's
   selection. Do not show business group IDs to the user.
3. Before asking for request fields, check the selected catalog metadata. If a
   ticket/work-order catalog (`serviceCategory: "GENERIC_SERVICE"`) has
   `instructions.genericRequest`, build from that metadata. If a cloud/resource
   catalog has no `instructions.resourceSpecs` but its selected catalog metadata
   has `type: "cloudchef.nodes.Compute"`, use the Compute fallback below. If it
   has no Markdown and is not Compute, stop and explain that the catalog is
   missing generated Markdown instructions.
4. Build the request from the selected catalog's generated Markdown metadata:
   `instructions.resourceSpecs`, `instructions.genericRequest`, and
   `instructions.topLevelFields`.
5. Ask only for active required fields with no default, plus fields explicitly
   marked `ask: true`. Defaults are used silently.
6. Show a JSON preview and ask for confirmation.
7. After the user confirms, call `smartcmp_submit_request` with the preview JSON.

Steps 1 and 2 are mandatory for every new request. Never ask the user to type a
business group before calling `smartcmp_list_available_bgs`.

### Catalog identity contract

- Displayed service list numbers are conversation choices only. Resolve them
  against the latest `smartcmp_list_services` result.
- `catalogId` must be the selected catalog metadata UUID, never the displayed
  list number and never `sourceKey`.
- After catalog selection, the next tool call must be
  `smartcmp_list_available_bgs` with that UUID.
- There is no catalog questionnaire/default-property/preview tool in this
  skill. Do not invent one.

### Tool sequencing

- One lookup tool call per turn.
- After a lookup tool result, summarize the resolved result in natural language
  and ask at most one next question.
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
- During request building, do not call datasource-only tools such as
  `smartcmp_list_components`, `smartcmp_list_applications`, or
  `smartcmp_list_images`. The selected catalog metadata and generated Markdown
  are the request contract.

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

`smartcmp_list_services` exposes the parsed `# Request Parameter Instructions`
YAML as selected catalog metadata:

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
  for the request/resource name. Do not auto-generate it.
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
  `credentialUser`, `credentialPassword`, `networkId`, `securityGroupIds`, or
  `systemDisk` at `resourceSpecs[]` level rather than under `params`.
- Preserve each direct field's declared type from Markdown. In particular,
  serialize Compute `securityGroupIds` as a JSON array of security group id
  strings, even when only one security group is selected; never serialize it as
  a single string or comma-separated string.
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
  table-async selections, including direct Compute lookup fields, should appear
  in generated Markdown only when they already have a non-empty default. If old
  Markdown still declares one of these lookup fields without a default, omit it
  and do not ask the user for an internal id.
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
field schema as `resourceSpecs[].<key>`.
For Compute, `securityGroupIds` must be an array, for example
`"securityGroupIds": ["sg-xxxxxxxx"]`.

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
- Match user wording against returned catalog name, `sourceKey`, and service
  category.
- If multiple catalogs could match, ask a numbered catalog-selection question.
- When the user selects by number, resolve the number to the selected catalog
  metadata UUID before calling any next tool.

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
  Compute fallback and the user provided a spec such as `2c4g`.
- Do not call those tools for fields that already have active defaults.

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
3. Call `smartcmp_list_flavors` when the user supplied a spec such as `2c4g`,
   or ask the user to choose a flavor if no unambiguous match exists. Use the
   flavor `id` as `computeProfileId`.
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
- A bare number is a selection for the latest displayed list unless the
  immediately previous assistant message displayed a JSON preview and asked for
  confirmation.

## Interaction Rules

- `smartcmp_list_services` at most once per request conversation.
- `smartcmp_list_available_bgs` is normally called once after catalog
  selection. It may be called one extra time only to resolve a user's business
  group selection in a tool-required turn.
- Never claim submitted unless `smartcmp_submit_request` actually executed.
- Never display raw internal metadata to the user.

