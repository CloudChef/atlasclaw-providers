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
  - User wants to analyze one or more resources by ID for compliance or security risk
  - User wants to check whether a resource version is outdated, unsupported, or risky
  - Webhook payload includes resource IDs that need review

avoid_when:
  - User wants to browse general catalog data only (use datasource skill)
  - User wants to browse a resource list, virtual-machine list, or cloud-host detail/attribute view only (use resource skill)
  - User wants to submit a provisioning request (use request skill)
  - User wants to approve or reject requests (use approval skill)

related:
  - datasource
  - resource

tool_analyze_name: "smartcmp_analyze_resource_compliance"
tool_analyze_description: "Analyze one or more SmartCMP resources by ID for compliance, security risk, lifecycle, and configuration posture with componentType-driven cloud/software/OS analyzers."
tool_analyze_entrypoint: "scripts/analyze_resource.py"
tool_analyze_groups:
  - cmp
  - compliance
tool_analyze_capability_class: "provider:smartcmp"
tool_analyze_priority: 110
---

# resource-compliance

Analyze one or more SmartCMP resources for lifecycle, patch, security, and configuration posture.

## Purpose

This skill fetches resource facts from SmartCMP, consumes the shared
normalized `type + properties` view from `list_resource.py`, routes analysis by
`componentType`, and then performs explainable checks with optional live
internet validation.

## Scripts

| Script | Description | Location |
|--------|-------------|----------|
| `analyze_resource.py` | Analyze one or more resources by ID | `scripts/` |

## Examples

```bash
python scripts/analyze_resource.py <resource_id>
python scripts/analyze_resource.py --payload-json '{"resourceIds":["id-1"],"triggerSource":"webhook"}'
```

## Notes

- Supports both direct user input and webhook-style payloads.
- Emits human-readable output plus `##RESOURCE_COMPLIANCE_START##` metadata.
- Routes analyzers by normalized `type` (`componentType`) and emits `analysisTargets`.
- Supports cloud/software/OS analyzer families (including AliCloud OSS, Tomcat, MySQL, PostgreSQL, Redis, Elasticsearch, SQL Server, Linux, Windows).
- Performs best-effort live internet validation and degrades conservatively when validation is unavailable.

## Workflow

See [references/WORKFLOW.md](references/WORKFLOW.md) for the supported workflow.
