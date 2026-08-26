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
tool_list_services_read_only: true
tool_list_services_auto_select_single_option: true
tool_list_services_description: "List available service catalog choices from SmartCMP. Call this tool ONLY ONCE at the beginning of a new request workflow. It returns compact catalog identity metadata, not request-field instructions. After receiving the list, check whether the user's original message clearly matches a specific catalog. If so, auto-select it; otherwise show the numbered list. Displayed numbers are conversation choices only. Resolve the selected number to the catalog metadata UUID, then call smartcmp_get_request_catalog before inspecting fields or calling any catalog-dependent lookup. Keep returned _internal metadata for workflow use only; do not show those fields to the user."
tool_list_services_entrypoint: "scripts/adapter.py:list_services"
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
tool_catalog_detail_read_only: true
tool_catalog_detail_description: "Load the normalized request-field instructions for exactly one catalog selected from smartcmp_list_services. catalog_id MUST be the selected catalog metadata UUID, never a displayed number or sourceKey. Call once immediately after catalog selection; it may share the same tool-call batch with smartcmp_list_available_bgs because that lookup depends only on the selected catalog UUID. Keep returned _internal metadata for workflow use only."
tool_catalog_detail_entrypoint: "scripts/adapter.py:get_request_catalog"
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
tool_submit_description: "Submit resource request to SmartCMP. RULES: (1) NEVER claim submitted without calling this tool. (2) Reuse resolved workflow lookup evidence, display a preview from the exact generated instruction contract with credential secrets masked, and wait for user confirmation BEFORE calling. The displayed masked preview is not the submit body. (3) json_body is REQUIRED and must contain the corresponding original secret values; never submit ***, ******, or another preview mask. If an original secret is unavailable, stop, collect it again, revalidate, and obtain fresh confirmation. (4) Pass resource_bundle_selections for every tag-only or internal pool resolution, keyed by resourceSpecs[].node, using the exact ID returned by smartcmp_list_resource_bundles. (5) catalogId MUST be UUID from catalog metadata id field. (6) Same-type multi-instance requests must use the selected catalog's declared count field, or top-level quantity when no such field exists, without duplicating resourceSpecs; per-instance differences belong in request-decomposition-agent. See Field Placement table in skill body for exact structure rules."
tool_submit_entrypoint: "scripts/adapter.py:submit"
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
        "description": "REQUIRED. The complete unmasked request JSON as a string. It must contain each corresponding original secret value and must never contain preview masks such as *** or ******. For cloud/resource requests: include catalogId, catalogName, businessGroupId, name, resourceSpecs built from generated Markdown instructions.resourceSpecs, and optional top-level params built from instructions.params. Put resourceBundleId at resourceSpecs[].resourceBundleId, resourceBundleTags at resourceSpecs[].resourceBundleTags, resourceBundleParams under resourceSpecs[].resourceBundleParams, resource-spec params under resourceSpecs[].params, resource-spec fields under resourceSpecs[] directly, and catalog form params under top-level params. For same-type multi-instance requests, use the selected catalog's declared quantity/count field in its declared location; when no catalog field exists, add top-level quantity. Do not duplicate resourceSpecs just to represent count. If both resourceBundleTags and resourceBundleId are declared, use tags only to filter pools and submit resourceBundleId; submit resourceBundleTags only when it is the sole declared pool selector. For tickets: build genericRequest.description and optional genericRequest.processForm from generated Markdown instructions.genericRequest; for tickets without Markdown, include catalogId, catalogName, businessGroupId, name, and genericRequest {description}. Do NOT include userLoginId (auto-injected by script). FORBIDDEN fields: never add priority, category, requestor, parameters, impactScope, urgency, contactName, or any field not listed above. DO NOT omit this parameter."
      },
      "resource_bundle_selections": {
        "type": "object",
        "additionalProperties": {"type": "string"},
        "description": "Trace-bound pool evidence for tag-only and internal selection. Key each exact resourceSpecs[].node to the resource pool ID returned by smartcmp_list_resource_bundles. Omit for requests without those selector modes."
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
tool_status_read_only: true
tool_status_description: "Query a submitted SmartCMP request status by user-facing Request ID, e.g. REQ20260501000095, RES20260501000095, TIC20260316000001, or CHG20260413000011. Use only for submitted request status or approval-result questions. For recent-submission follow-ups without an explicit ID, reuse the most recent Request ID from this conversation; if none exists, ask for it. Do NOT pass internal UUIDs, approve, or reject requests."
tool_status_entrypoint: "scripts/adapter.py:status"
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
tool_facets_read_only: true
tool_facets_auto_select_single_option: true
tool_facets_description: "List available resource pool tag facets from SmartCMP. REQUIRES businessGroupId — call this AFTER business group is selected whenever request Markdown declares active resourceBundleTags, with or without a default. After this tool returns, do not call datasource tools to interpret facets. Match or ask for a facet option, then build resourceBundleTags with facet key and option key (NOT display names). Never show raw facet metadata."
tool_facets_entrypoint: "scripts/adapter.py:list_facets"
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
tool_resource_bundles_read_only: true
tool_resource_bundles_auto_select_single_option: true
tool_resource_bundles_description: "List request-flow resource pools, optionally filtered by selected resource tags, and resolve active request fields for an exact selected pool. For an active resourceBundleId, omit resource_bundle_id on the initial candidate lookup even when a default exists, and preserve SmartCMP response order. Select a sole result; with multiple results, use an already-stated pool or platform intent only when it uniquely matches one returned item, otherwise show all names in order and wait. Pass the exact selected ID only for subsequent placement resolution. Use when generated Markdown declares an active resourceBundleId, resourceBundleTags, or runtime_fields.resolver. Always pass catalog_id and node_template_name as explicit context; placement_values contains business field selections only. Pass resource_bundle_tags as exact facet.key:option.key values whenever tags were selected. With resource_bundle_id, request options through placement_fields and follow the returned requestFields, targets, dependencies, missingRequiredFields, missingSelectionFields, and configurationErrors. Requires selected business_group_id, component_type from generated Markdown catalog/component metadata, and node_type from resourceSpecs[].type. Fixed API filters: strategy=RB_POLICY_STATIC, enabled=true, readOnly=false."
tool_resource_bundles_entrypoint: "scripts/adapter.py:list_resource_bundles"
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
      "catalog_id": {
        "type": "string",
        "description": "REQUIRED. Selected catalog UUID from smartcmp_get_request_catalog metadata."
      },
      "node_template_name": {
        "type": "string",
        "description": "REQUIRED. Literal generated resourceSpecs[].node for the current request spec."
      },
      "cloud_entry_type_id": {
        "type": "string",
        "description": "Optional cloud entry type id filter. Omit or pass empty string when not declared."
      },
      "resource_bundle_id": {
        "type": "string",
        "description": "Exact selected resource pool ID for placement resolution. Omit on the initial candidate lookup, including when resourceBundleId.defaultValue exists."
      },
      "resource_bundle_tags": {
        "type": "array",
        "items": {
          "type": "string"
        },
        "description": "Selected resource tag filters as exact facet.key:option.key values. Pass them while listing pools and on later exact-pool placement calls."
      },
      "placement_fields": {
        "type": "array",
        "items": {
          "type": "string"
        },
        "description": "Any request field declared by generated Markdown, in dependency order."
      },
      "placement_values": {
        "type": "object",
        "additionalProperties": {
          "type": "string"
        },
        "description": "Selected business field values only. For an option-backed lookup field, use the exact selected options[].id; options[].name is display-only. If current option IDs have not been loaded, request the field in placement_fields and omit it from placement_values, then resolve the user selection against exactly one returned option before using that value. Never guess or pass the display name. Encode boolean and number values as strings and array values as JSON array strings. Never include catalogId or node; retain every selected field value while resolving later fields."
      }
    },
    "required": ["business_group_id", "component_type", "node_type", "catalog_id", "node_template_name"]
  }
tool_bgs_name: "smartcmp_list_available_bgs"
tool_bgs_read_only: true
tool_bgs_auto_select_single_option: true
tool_bgs_description: "List available business groups for a specific service catalog. Call this AFTER selecting a catalog to get the list of business groups the user can choose from. catalog_id MUST be the selected catalog metadata UUID, never the displayed list number. Use the returned id or name (depending on the catalog parameter key) for the business group field in the request body."
tool_bgs_entrypoint: "scripts/adapter.py:list_available_bgs"
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
tool_flavors_read_only: true
tool_flavors_auto_select_single_option: true
tool_flavors_description: "Resolve the request flavor fields declared by generated Markdown. Without compute_profile_id, list requestable MACHINE compute profiles and use the selected id as computeProfileId. When flavorId is also active, call again with the selected compute_profile_id and resource_bundle_id unless the exact selected resource-pool item has cloudEntryTypeId equal to yacmp:cloudentry:type:vsphere. For that exact vSphere platform and only after computeProfileId is resolved, SmartCMP resolves flavorId from the compute profile: skip the cloud-flavor query and omit flavorId from preview and submit JSON. Never send an empty flavorId or copy computeProfileId into flavorId. A missing platform marker, a different platform, or an unresolved computeProfileId remains fail-closed. Pass catalog_id and node_template_name when known for the compute-profile query. Omit resource_bundle_id only for an intentional global compute-profile query; it is required for a cloud-flavor query. For any active field with multiple candidates and no explicit user selection, show the current filtered names and ask the user to identify the pending field and selected number instead of replying with a bare number or typed specification."
tool_flavors_entrypoint: "scripts/adapter.py:list_flavors"
tool_flavors_group: "cmp"
tool_flavors_capability_class: "provider:smartcmp"
tool_flavors_priority: 108
tool_flavors_use_when:
  - "Generated Markdown declares an active computeProfileId, with or without a default, after resource pool selection and before any template lookup"
  - "Generated Markdown declares an active flavorId, with or without a default, after computeProfileId and resource pool selection, and the exact selected resource-pool item is not identified as yacmp:cloudentry:type:vsphere"
tool_flavors_cli_flag_overrides:
  query: "--query"
  resource_bundle_id: "--resource-bundle-id"
  compute_profile_id: "--compute-profile-id"
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
        "description": "Selected resource pool ID. Required when compute_profile_id is provided; omit only for an intentional global compute-profile query."
      },
      "compute_profile_id": {
        "type": "string",
        "description": "Selected computeProfileId. Omit to list compute profiles; provide it to list mapped cloud flavors for flavorId only when the exact selected resource-pool item is not yacmp:cloudentry:type:vsphere."
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
tool_logical_templates_read_only: true
tool_logical_templates_auto_select_single_option: true
tool_logical_templates_description: "List logical OS templates for a SmartCMP request. Call only after resource-pool and all explicit flavor-field selections are complete when generated Markdown declares logicTemplateId. For an exact selected yacmp:cloudentry:type:vsphere resource pool, resolved computeProfileId completes flavor selection and flavorId remains omitted for platform resolution. Pass resource_bundle_id and the required catalog OS family as os_type; also pass catalog_id and node_template_name when known. Use the selected id as logicTemplateId. The request-projected tool presents multiple returned names as an explicit selection boundary; a sole candidate is resolved by the generic runtime contract."
tool_logical_templates_entrypoint: "../datasource/scripts/adapter.py:list_logical_templates"
tool_logical_templates_groups:
  - cmp
  - request
tool_logical_templates_capability_class: "provider:smartcmp"
tool_logical_templates_priority: 112
tool_logical_templates_result_mode: "llm"
tool_logical_templates_use_when:
  - "Generated Markdown declares an active logicTemplateId, with or without a default, after resource pool and all explicit flavor-field selections"
tool_logical_templates_avoid_when:
  - "An active computeProfileId or explicitly selectable flavorId has not been selected yet"
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
tool_physical_templates_read_only: true
tool_physical_templates_auto_select_single_option: true
tool_physical_templates_description: "List physical templates available to the selected SmartCMP resource pool and logical template. Use only when generated Markdown declares physicalTemplateId. Each result retains its logicTemplateId; use the selected physicalTemplateId together with logicTemplateId and omit templateId. If multiple results exist without an explicit user selection, present names and ask the user to identify the physical-template field and selected number."
tool_physical_templates_entrypoint: "scripts/adapter.py:list_physical_templates"
tool_physical_templates_groups:
  - cmp
  - request
tool_physical_templates_capability_class: "provider:smartcmp"
tool_physical_templates_priority: 114
tool_physical_templates_result_mode: "silent_ok"
tool_physical_templates_use_when:
  - "Generated Markdown declares an active physicalTemplateId, with or without a default, after resource pool and logicTemplateId selection"
tool_physical_templates_avoid_when:
  - "An active computeProfileId, explicitly selectable flavorId, or logicTemplateId has not been selected yet"
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
tool_images_read_only: true
tool_images_auto_select_single_option: true
tool_images_description: "List cloud images for a SmartCMP request. Call after resource-pool and logical-template selection only when generated Markdown declares templateId. Use the selected image id as templateId, never as physicalTemplateId. If multiple results exist without an explicit user selection, present image names and ask the user to identify the image field and selected number."
tool_images_entrypoint: "../datasource/scripts/adapter.py:list_images"
tool_images_groups:
  - cmp
  - request
tool_images_capability_class: "provider:smartcmp"
tool_images_priority: 113
tool_images_result_mode: "llm"
tool_images_use_when:
  - "Generated Markdown declares an active templateId, with or without a default, after resource pool and logicTemplateId selection"
tool_images_avoid_when:
  - "An active computeProfileId, explicitly selectable flavorId, or logicTemplateId has not been selected yet"
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
6. For every active selectable field, resolve its candidates even when it has a
   default. A default is only a suggestion in its declared or returned position:
   use a sole candidate, but require an explicit user choice among multiple
   candidates unless the user's existing intent uniquely identifies one. Use non-selectable defaults
   silently, and ask for other active required or `ask: true` fields without a
   value. The sole platform-resolved exception is `flavorId` after
   `computeProfileId` is selected when the exact selected resource-pool item has
   `cloudEntryTypeId` equal to
   `yacmp:cloudentry:type:vsphere`; omit that field instead of asking for it.
7. Reuse resolved workflow lookup evidence. For every resource spec with an
   active `resourceBundleTags`, active `resourceBundleId`, or
   `runtime_fields.resolver`, resolve its resource pool and dynamic request
   fields, then collect each unresolved active required, `ask: true`, or
   selectable value. Ticket/work-order `genericRequest` catalogs have no
   resource specs and skip this step. Use the exact returned option ID for
   option-backed fields. Once all declared fields have values, show a schema-exact JSON
   preview with credential secrets masked, ask for confirmation, and stop. Do
   not run a final resource-pool revalidation solely to authorize the preview.
8. After the user confirms, call `smartcmp_submit_request` with the corresponding
   unmasked request body. For tag-only and internal resource-pool modes, also pass
   `resource_bundle_selections` keyed by node with the exact pool ID already
   resolved for the preview. The displayed preview is presentation-only; restore
   each original secret value and never submit a preview mask.

Steps 1 through 3 are mandatory for every new request. Never ask the user to type a
business group before calling `smartcmp_list_available_bgs`.

When the service has a clear automatic match, steps 1 through 3 may continue in
the same turn. Stop after any step that requires a user selection;
`smartcmp_get_request_catalog` is an internal schema lookup, not a user-facing
question.

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
- After catalog selection, call `smartcmp_get_request_catalog` and
  `smartcmp_list_available_bgs` with the same UUID in one tool-call batch. The
  business-group lookup does not depend on the catalog-detail response.
- There is no catalog questionnaire/default-property/preview tool in this
  skill. Do not invent one.

### Tool sequencing

- Resolve resource-spec lookup fields in dependency order:
  active `resourceBundleTags` -> active `resourceBundleId` ->
  `computeProfileId` -> explicitly selectable `flavorId` when declared -> `logicTemplateId` ->
  `physicalTemplateId` or `templateId`. Do not call tools for two unresolved
  selectable fields in one model response. When tags are the sole pool
  selector, use the first filtered result in CMP response order only for
  internal dynamic-field resolution and do not submit its ID. Ticket/work-order
  `genericRequest` catalogs skip this resource-spec lookup sequence.
- After `resourceBundleId` is selected, `smartcmp_list_flavors` is the only
  valid next lookup while an active `computeProfileId` or explicitly selectable
  `flavorId` remains unresolved. Resolve `computeProfileId` first, then call the same tool with
  that value to resolve `flavorId`. Do not perform that second lookup when the
  exact selected resource-pool item has `cloudEntryTypeId` equal to
  `yacmp:cloudentry:type:vsphere`: after `computeProfileId` is resolved, omit
  `flavorId` from preview and submit JSON so SmartCMP resolves it from the
  compute profile. Never send an empty `flavorId`, never copy
  `computeProfileId` into it, and never infer this branch from an empty lookup
  result. A missing or different platform marker remains fail-closed. Do not
  call any logical-template,
  physical-template, or image lookup first.
- For each active generated selectable field, call only that field's lookup,
  regardless of whether it has a default. When the opted-in read-only tool
  returns one visible candidate, the generic runtime selects it and continues.
  When it returns multiple choices without an explicit user selection, present
  only those choices in returned order, ask the user to select one, and stop.
  Do not ask for later lookup fields or user-entered fields in the same reply.
- Every lookup-selection prompt must also state exactly one immediate workflow
  step that will follow the user's selection, without asking for that next step
  in the same reply. If another generated lookup remains, state that the next
  live lookup will run. If generated lookups are complete and an already-known
  active non-lookup field is missing, state that this field will be collected
  next. If no such field is missing, state that placement resolution or exact
  validation will run next. This immediate-next-step statement is mandatory
  and must match the current generated instructions and any applicable latest
  exact `requestFields`.
- After recording a lookup selection, continue the generated lookup sequence
  above while any active lookup field remains unresolved. Once that sequence is
  complete, but before starting `resource_bundle_placement` discovery or exact
  validation, collect the already-known active non-lookup fields in their
  declared order. A field belongs to this sequence when it is required,
  `ask: true`, or selectable, has satisfied dependencies, and has neither a real
  user value nor a usable non-selectable default. A selectable default is not a real user
  value when multiple candidates exist. A promise to provide a value later is not a value.
  Ask for exactly the first missing field and stop. After the user supplies it,
  re-evaluate the same already-known active non-lookup fields. If another field
  still meets these conditions, ask for that field next and do not state or
  imply that placement resolution or validation will run yet. Only when the
  current field is the last such missing field must the prompt state that
  placement resolution or validation follows after it is supplied. Apply this
  only to fields already proven active by generated instructions or the latest
  exact `requestFields`. Use an exact field only when its condition and
  dependency inputs have not changed since that result; never activate a
  conditional field by guessing.
- Phrase every multiple-choice reply with the pending field meaning and visible
  numbered options. A bare visible number or the exact visible option text is a
  valid generic continuation; do not require the user to repeat field names.
- Stop after a lookup whenever the user must choose among multiple unresolved
  options. Ask at most one concise question and wait for the answer.
- A sole visible candidate may auto-continue only when its read-only tool is
  explicitly marked `auto_select_single_option`. Multiple candidates remain a
  user selection boundary unless existing user intent uniquely matches one.
  Tools without that metadata never gain automatic-selection behavior.
- During mandatory catalog discovery, when the initial list has one clear
  automatic match, emit `smartcmp_get_request_catalog` and
  `smartcmp_list_available_bgs` in the same tool-call batch with the selected
  catalog UUID. The business-group query does not depend on the catalog-detail
  response. When the user must choose a catalog, stop after the list and issue
  that batch only after their selection.
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
- Do not include `userLoginId`; SmartCMP Provider resolves the acting
  SmartCMP user from the selected credential.
- Put root request fields declared in `instructions.params.<key>` under the
  top-level JSON object `params.<key>`. These are catalog form fields from
  `catalog.form_definition_id`, not resource spec fields.
- Root `instructions.params` fields follow the same active-field rules as
  resource fields: evaluate `when`, follow the selectable-default rule in
  Complete flow for static `options`, use non-selectable defaults silently, and
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
  evaluate `when`, follow the selectable-default rule in Complete flow, use
  non-selectable defaults silently, and omit inactive or empty optional fields.
- For each `instructions.resourceSpecs[]`, create one `resourceSpecs[]` item
  and copy `node` and `type` exactly when present.
- Treat field schemas declared directly on `instructions.resourceSpecs[]`,
  other than `node`, `type`, `resourceBundleId`, `resourceBundleTags`,
  `resourceBundleParams`, and `params`, as direct resource spec fields. Put each
  active value directly on the same `resourceSpecs[]` item as `<key>`. These
  fields are for special resources such as Compute/VM, where SmartCMP expects
  values like `computeProfileId`, `flavorId`, `logicTemplateId`, `templateId`,
  `physicalTemplateId`,
  `credentialUser`, `credentialPassword`, `networkId`, `subnetId`,
  `securityGroupIds`, or `systemDisk` at `resourceSpecs[]` level rather than
  under `params`.
- The exact vSphere `flavorId` exception above overrides direct-field
  serialization: when the selected resource-pool item identifies
  `yacmp:cloudentry:type:vsphere` and `computeProfileId` is resolved, omit
  `flavorId` entirely even when its generated schema is required or
  `ask: true`.
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
  `resourceBundleParams`, and `params` in Markdown. If it is active, call
  `smartcmp_list_facets` after business group selection with `node_type` from
  that spec's `type`, whether or not it has a default. Retain selected values as exact
  `"<facet.key>:<option.key>"` filters for the resource-pool step.
- When both `resourceBundleTags` and `resourceBundleId` are active, resolve tags
  first and pass them as `resource_bundle_tags` to
  `smartcmp_list_resource_bundles`, then apply the authoritative
  `resourceBundleId` selection rules below. Keep both the selected tags and
  `resourceBundleId` in the Provider Tool `json_body` so the Provider can
  revalidate the same placement. The Provider removes
  `resourceBundleTags` before submitting to SmartCMP, so the upstream request
  contains only `resourceBundleId`.
- When only `resourceBundleTags` is active, pass the selected tags to
  `smartcmp_list_resource_bundles`. The Provider returns only the first matching
  pool in CMP response order for subsequent lookups; do not expose or ask the
  user to choose that pool. Submit only `resourceBundleTags`; the Provider
  verifies and submits the same pool ID from `resource_bundle_selections`. An
  empty filtered result is an error and must not be retried without the selected
  tags.
- The `resourceBundleId` rules here apply the generic selectable-default rule
  and override optional-field, preview-readiness, and submit-readiness rules
  elsewhere in this skill.
- For every active `resourceBundleId`—required, `ask: true`, or optional; with
  or without a default—call `smartcmp_list_resource_bundles` after business
  group and tag selection without `resource_bundle_id`. A default is only a
  suggestion, never a usable selection. Preserve the
  complete SmartCMP response order and never reorder candidates.
- Select a sole returned pool automatically. With multiple pools, an
  already-stated pool or platform intent is an existing user selection only
  when it uniquely matches one returned item; otherwise show every returned
  name in order and wait. Never silently select the default from multiple
  results.
- After resource-pool selection is complete, use the selected bundle `id` at
  `resourceSpecs[].resourceBundleId`. Call `smartcmp_list_resource_bundles`
  again with that exact `resource_bundle_id` only when placement fields must be
  discovered or resolved for the selected pool. Until selection completes,
  preview and submit are not ready.
- If no pool selector is active but `runtime_fields.resolver` requires a pool,
  call `smartcmp_list_resource_bundles` without tags or a pool ID. The Provider
  returns only its internally selected first CMP-sorted pool for downstream
  lookups. Reuse that ID as lookup context and in
  `resource_bundle_selections`, but do not expose the pool to the user or
  serialize it in the preview body.
- For `smartcmp_list_resource_bundles`, pass `business_group_id` from the
  selected business group, `node_type` from `resourceSpecs[].type`, and
  `component_type` from `instructions.componentType` / catalog
  `component_type`, falling back to catalog `sourceKey` only when generated
  Markdown does not declare it.
- Put `resourceBundleParams.<key>` values under
  `resourceSpecs[].resourceBundleParams.<key>`.
- For every resource-pool call, pass the catalog UUID as `catalog_id` and the
  generated resource-spec node as `node_template_name`. Keep only business field
  selections in `placement_values`; never put `catalogId` or `node` there. Pass
  selected tags as `resource_bundle_tags` on both list and exact-pool calls, and
  pass any currently requested fields as `placement_fields`. The returned
  `requestFields` is the authoritative active field set for that pool and the
  current selections.
- When a spec declares `runtime_fields.resolver: resource_bundle_placement`,
  first collect the already-known active non-lookup fields required by Tool
  sequencing, then call the selected pool once with no `placement_fields` to
  discover its active fields and resolve the first dependency-ready missing
  lookup before collecting resolver-discovered values. Treat the top-level
  `selectionField` and `selectionCandidates` as the current dynamic input, and
  use the selected candidate `id` in `placement_values`. If exactly one
  candidate is returned, allow the runtime's generic single-option behavior to
  continue without asking the user. Re-resolve only when another unresolved
  field depends on the selected value; do not re-resolve after the last dynamic
  selection.
- Resolve fields in `dependsOn` order. Query only a field whose dependencies
  already have values, present its returned `options`, retain the selection in
  `placement_values`, and call the tool again only when another unresolved field
  depends on that selection. After the last dynamic field, continue to the
  preview without another resource-pool resolver call.
- Follow each returned field's `target` when constructing the request. Do not
  infer field names, dependencies, or request locations from a cloud platform
  or from another catalog.
- Put `params.<key>` values under `resourceSpecs[].params.<key>`.
- Collect every active required, `ask: true`, or selectable field, except the
  platform-resolved vSphere `flavorId` defined above. After the final dynamic
  value is selected, proceed directly to the request preview when all declared
  active fields have a real value or a usable non-selectable default. Do not
  call the pool resolver again before the preview.
- `logicTemplateId` is the independent logical OS-template field. When it is
  active, query logical templates with the selected
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
- Use `defaultValue` / `default_value` silently only for fields without a
  candidate set. For every active field with static options or live lookup
  candidates, preserve the declared or returned order: use a sole candidate,
  but require an explicit user choice among multiple candidates unless existing
  user intent uniquely matches one. Keep a default as a suggestion in its
  declared or returned position; never move it ahead of other candidates.
- Ask for an active required field with no usable value, a field marked
  `ask: true`, or a selectable field with multiple candidates and no explicit
  user selection. Resolve declared `resourceBundleParams` from the exact
  selected resource pool; omit only inactive or unmarked optional fields.
- Optional non-selectable fields without a user value or non-empty default are
  omitted.
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
      "resourceBundleId": "<selected resource pool id>",
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
`resourceBundleParams`. When tags are the only pool selector, replace
`resourceBundleId` with `resourceBundleTags`; when both selectors are declared,
submit only `resourceBundleId`. Do not serialize a `fields` wrapper. Serialize each active direct resource-spec
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

- `smartcmp_list_available_bgs` is authoritative. If a tenant / 租户 / 部门 /
  BU / 项目 already uniquely matches one returned group, use it; otherwise ask
  one concise numbered question with display names only.
- Put the selected group's `id` at top-level `businessGroupId`. If a request
  name is also missing, ask for the group selection and name together.

## Runtime Lookups

Generated Markdown determines which lookup fields are active; Tool sequencing
determines their order. Call only the lookup for the current active field with
or without a default, use its selected returned ID only for that declared
field, and keep display names user-facing.

- For `resourceBundleTags`, use `smartcmp_list_facets` with the spec node type.
  Pass selected `"<facet.key>:<option.key>"` values to the resource-pool lookup;
  serialize them only when tags are the sole pool selector.
- For resource-pool placement, pass the selected business group, component
  type, spec node, catalog UUID, node template name, exact pool ID when known,
  requested fields, and only business selections in `placement_values`. The
  returned `requestFields` is authoritative for the current selections.
- For template fields, follow the generated branch exactly: logical template,
  then physical template or cloud image. Keep their IDs internal; never ask a
  user to type a template UUID or substitute one field's ID for another.
- The vSphere flavor omission and all option-ID rules remain authoritative in
  Tool sequencing and Generated Markdown. Empty
  results, missing platform identity, or a missing declared template branch
  remain fail-closed.

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
- Store selected tags as `"<facet.key>:<option.key>"` strings. Submit them at
  `resourceSpecs[].resourceBundleTags` only when tags are the sole pool
  selector; otherwise use them only as pool lookup filters.

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

1. Verify that every active required, `ask: true`, or selectable field declared
   by generated instructions or resolved dynamic field metadata has a real
   value or usable non-selectable default. Do not perform a final resource-pool
   revalidation.
2. Show a short summary in the user's language.
3. Show `JSON 预览` / `JSON Preview` with a fenced JSON block. This block is a
   presentation-only copy, not the `json_body` passed to the submit tool.
4. Mask `credentialPassword` as `"******"` only in that displayed copy. Preserve
   the corresponding original value for the eventual request body.
5. Ask the user to confirm.
6. Stop. Do not call `smartcmp_submit_request` until the user confirms.

After confirmation:

- User says yes → call `smartcmp_submit_request` with the unmasked `json_body`
  corresponding to the confirmed preview. Never submit `***`, `******`, or any
  other preview mask as a secret value.
- If an original secret is unavailable after confirmation, fail closed: do not
  call submit. Collect the secret again, display a new masked preview, and ask
  for fresh confirmation.
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
