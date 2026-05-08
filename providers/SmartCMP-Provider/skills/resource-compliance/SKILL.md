---
name: "resource-compliance"
description: "Resource compliance skill. Analyze one or more SmartCMP resources with componentType-driven cloud/software/OS analyzers."
provider_type: "smartcmp"
instance_required: "true"

triggers:
  - resource compliance
  - compliance analysis
  - security analysis
  - analyze resource
  - resource risk
  - mysql version
  - windows patch
  - linux security
  - tomcat lifecycle
  - alicloud oss security
  - 资源合规
  - 合规分析
  - 合规检查
  - 安全分析
  - 资源风险
  - 版本检查
  - 生命周期分析
  - 补丁检查

use_when:
  - User wants to analyze one or more resources by resource name or selected list index for compliance or security risk
  - User wants to check whether a resource version is outdated, unsupported, or risky
  - Webhook payload includes resource IDs that need review as an internal compatibility path

avoid_when:
  - User wants to browse general catalog data only (use datasource skill)
  - User wants to browse a resource list, virtual-machine list, or cloud-host detail/attribute view only (use resource skill)
  - User wants to submit a provisioning request (use request skill)
  - User wants to approve or reject requests (use approval skill)

related:
  - datasource
  - resource

tool_analyze_name: "smartcmp_analyze_resource_compliance"
tool_analyze_description: "Analyze one or more SmartCMP resources by exact resource name or by a selected numbered list item for compliance, security risk, lifecycle, and configuration posture. Prefer resource_name or resource_index with recent smartcmp_list_all_resource metadata; resource IDs are internal compatibility inputs only and should not be requested from or shown to users."
tool_analyze_entrypoint: "scripts/analyze_resource.py"
tool_analyze_groups:
  - cmp
  - compliance
tool_analyze_capability_class: "provider:smartcmp"
tool_analyze_priority: 110
tool_analyze_cli_split:
  - resource_ids
tool_analyze_parameters: |
  {
    "type": "object",
    "properties": {
      "resource_name": {
        "type": "string",
        "description": "Exact visible SmartCMP resource name selected by the user. Prefer this over UUIDs."
      },
      "resource_index": {
        "type": "integer",
        "description": "Visible list index from the latest smartcmp_list_all_resource result, for example 1 or 2."
      },
      "resource_directory_json": {
        "type": "string",
        "description": "Hidden JSON metadata from the latest smartcmp_list_all_resource result or Current Workflow Context. Pass this when resolving a visible list index or validating a listed resource name."
      },
      "trigger_source": {
        "type": "string",
        "description": "Source of this analysis request. Default: user.",
        "default": "user"
      },
      "payload_json": {
        "type": "string",
        "description": "Webhook-style JSON payload. Compatibility path for backend events."
      },
      "resource_ids": {
        "type": "string",
        "description": "Compatibility-only SmartCMP resource IDs for backend/webhook flows. Do not ask users for this value and do not show it in replies."
      }
    }
  }
---

# resource-compliance

Analyze one or more SmartCMP resources for lifecycle, patch, security, and configuration posture by resource name or visible list selection.

## Purpose

This skill fetches resource facts from SmartCMP, consumes the shared
normalized `type + properties` view from `list_resource.py`, routes analysis by
`componentType`, and then performs explainable checks with optional live
internet validation.

## Scripts

| Script | Description | Location |
|--------|-------------|----------|
| `analyze_resource.py` | Analyze one or more resources by name, selected list index, or internal compatibility ID | `scripts/` |

## Examples

```bash
python scripts/analyze_resource.py --resource-name e2e-newrole-linux3-0501
python scripts/analyze_resource.py --resource-index 2 --resource-directory-json '[{"index":2,"id":"internal-id","name":"e2e-newrole-linux3-0501"}]'
python scripts/analyze_resource.py --payload-json '{"resourceIds":["id-1"],"triggerSource":"webhook"}'
```

## Notes

- User and Agent interaction should be name-first: use `resource_name` or a visible `resource_index` from the latest resource list.
- Use recent `smartcmp_list_all_resource` metadata to resolve list indexes and validate selected names.
- Never ask users for SmartCMP UUIDs and never show UUIDs in the final user-facing reply.
- Supports webhook-style resource IDs as an internal compatibility path.
- Emits human-readable output plus `##RESOURCE_COMPLIANCE_START##` metadata.
- Routes analyzers by normalized `type` (`componentType`) and emits `analysisTargets`.
- Supports cloud/software/OS analyzer families (including AliCloud OSS, Tomcat, MySQL, PostgreSQL, Redis, Elasticsearch, SQL Server, Linux, Windows).
- Performs best-effort live internet validation and degrades conservatively when validation is unavailable.

## Workflow

See [references/WORKFLOW.md](references/WORKFLOW.md) for the supported workflow.
