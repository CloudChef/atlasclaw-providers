---
name: "cost-optimization"
description: "Cost optimization skill. Review SmartCMP FinOps recommendations or analyze one cloud, software, hardware, virtualized, VM, or database resource for platform-confirmed and LLM-inferred savings opportunities. Use active policy evidence, bounded resource cost facts, risk assessment, and conservative saving estimates; remediate only existing findings through native day2 repair and track remediation state."
provider_type: "smartcmp"
instance_required: "true"

triggers:
  - cost optimization
  - optimization recommendations
  - savings recommendations
  - resource usage analysis
  - finops
  - rightsize
  - remediate optimization
  - 费用优化
  - 成本优化
  - 优化建议
  - 节省建议
  - 降配
  - 空闲资源
  - 资源利用率
  - 查看优化建议
  - 分析资源费用
  - 资源费用优化
  - RDS费用分析

use_when:
  - User wants to list optimization or FinOps recommendations
  - User wants to analyze cost optimization opportunities with detailed insights, resource context, and risk assessment
  - User wants to analyze whether one named or selected resource may have cost optimization potential even when no recommendation exists
  - User wants to understand saving contribution and priority in global context
  - User wants to remediate an optimization finding through native day2 repair
  - User wants to track cost optimization remediation progress

avoid_when:
  - User wants to provision new resources (use request skill)
  - User only wants standalone read-only resource browsing without optimization analysis (use datasource skill)
  - User wants approval workflow actions (use approval skill)

related:
  - datasource
  - approval

tool_list_name: "smartcmp_list_cost_recommendations"
tool_list_description: "List SmartCMP cost optimization recommendations with optional related policy counts."
tool_list_entrypoint: "scripts/adapter.py:list_recommendations"
tool_list_groups:
  - cmp
  - finops
tool_list_capability_class: "provider:smartcmp"
tool_list_priority: 100
tool_list_parameters: |
  {
    "type": "object",
    "properties": {
      "status": {"type": "string", "default": "ACTIVED"},
      "severity": {
        "type": "array",
        "items": {"type": "string"}
      },
      "category": {"type": "string", "default": "COST-OPTIMIZATION"},
      "query": {"type": "string"},
      "page": {"type": "integer", "default": 0, "minimum": 0},
      "size": {"type": "integer", "default": 20, "minimum": 1},
      "with_related_policies": {"type": "boolean", "default": false}
    }
  }
tool_analyze_name: "smartcmp_analyze_cost_recommendation"
tool_analyze_description: "Analyze one SmartCMP cost optimization recommendation with multi-dimensional insights, datasource-enriched resource context, risk assessment, saving priority, and best practice guidance."
tool_analyze_entrypoint: "scripts/adapter.py:analyze_recommendation"
tool_analyze_groups:
  - cmp
  - finops
tool_analyze_capability_class: "provider:smartcmp"
tool_analyze_priority: 120
tool_analyze_parameters: |
  {
    "type": "object",
    "properties": {
      "violation_id": {
        "type": "string",
        "description": "SmartCMP cost recommendation violation ID."
      }
    },
    "required": ["violation_id"]
  }
tool_resource_analyze_name: "smartcmp_analyze_resource_cost"
tool_resource_analyze_description: "Collect read-only SmartCMP cost evidence for one resource, correlate enabled applicable cost policies, latest resource executions, and active violations, then use the LLM to distinguish platform-confirmed findings from model-only optimization potential. Prefer resource_name or a visible resource_index with recent smartcmp_list_all_resource metadata; resource_id is an internal compatibility input only. Never claim that COMPLIANCE without explicit complete evidence means the resource has no optimization opportunity, never invent a saving amount, and never remediate from model-only evidence."
tool_resource_analyze_entrypoint: "scripts/adapter.py:analyze_resource_cost"
tool_resource_analyze_groups:
  - cmp
  - finops
  - resource
tool_resource_analyze_capability_class: "provider:smartcmp"
tool_resource_analyze_priority: 125
tool_resource_analyze_result_mode: "llm"
tool_resource_analyze_parameters: |
  {
    "type": "object",
    "properties": {
      "resource_name": {
        "type": "string",
        "description": "Exact visible SmartCMP resource name. Prefer this for interactive requests."
      },
      "resource_index": {
        "type": "integer",
        "description": "Visible table # value from the latest smartcmp_list_all_resource result."
      },
      "resource_directory_json": {
        "type": "string",
        "description": "Hidden JSON metadata from the latest smartcmp_list_all_resource result or Current Workflow Context. Pass this when resolving a visible table # value or validating a listed resource name."
      },
      "resource_id": {
        "type": "string",
        "description": "Compatibility-only internal SmartCMP resource ID. Do not request this from users or expose it in the final reply."
      }
    }
  }
tool_execute_name: "smartcmp_execute_cost_optimization"
tool_execute_description: "Remediate a SmartCMP cost optimization violation through its native day2 repair."
tool_execute_entrypoint: "scripts/adapter.py:execute_optimization"
tool_execute_groups:
  - cmp
  - finops
tool_execute_capability_class: "provider:smartcmp"
tool_execute_priority: 150
tool_execute_parameters: |
  {
    "type": "object",
    "properties": {
      "violation_id": {
        "type": "string",
        "description": "Confirmed SmartCMP violation ID to remediate."
      }
    },
    "required": ["violation_id"]
  }
tool_track_name: "smartcmp_track_cost_optimization"
tool_track_description: "Track SmartCMP cost optimization remediation progress."
tool_track_entrypoint: "scripts/adapter.py:track_execution"
tool_track_groups:
  - cmp
  - finops
tool_track_capability_class: "provider:smartcmp"
tool_track_priority: 130
tool_track_parameters: |
  {
    "type": "object",
    "properties": {
      "violation_id": {
        "type": "string",
        "description": "SmartCMP violation ID whose remediation status is requested."
      }
    },
    "required": ["violation_id"]
  }
---

# cost-optimization

Use this skill to work through cost optimization recommendations from
discovery to remediation tracking.

## Handlers and helpers

`scripts/adapter.py` contains all five Tool handlers for listing, analysis,
execution, and tracking. `scripts/_cost_object_actions.py` remains separate
because the embedded assistant Context resolver calls it to build resource
actions; it is not a one-command forwarding script.

## Workflow

Choose the entry path that matches the user's object:

1. Analyze an existing recommendation:
   - Call `smartcmp_list_cost_recommendations`
   - Optionally request related policy counts
   - Call `smartcmp_analyze_cost_recommendation`
   - Let SmartCMP Provider resolve the related `resourceId`
   - Merge normalized resource `type + properties` into the analysis facts
   - Returns multi-dimensional recommendations (P0/P1/P2 priority)
   - Includes risk assessment and best practice guidance
   - Shows saving contribution, policy history, and resource operational context
2. Analyze a resource directly:
   - Call `smartcmp_analyze_resource_cost` with an exact visible name or recent list `#` selection
   - Read resource facts, enabled applicable policy configurations, latest resource executions,
     and active violations without triggering policy execution
   - Use the returned `analysisContract` to keep platform facts separate from `llm_potential`
   - Read [references/RESOURCE_ANALYSIS.md](references/RESOURCE_ANALYSIS.md) for VM, AWS RDS,
     and generic resource reasoning rules
3. Call `smartcmp_execute_cost_optimization` for native day2 repair only after
   the user explicitly requests it
4. Track remediation state with `smartcmp_track_cost_optimization`

## Analysis Output Enhancement

`smartcmp_analyze_cost_recommendation` provides:

- **P0 Primary Action**: Provider recommendation (remediate / configure_platform_policy / manual_review)
- **P1 Risk Assessment**: Risk level (high/medium/low) with specific warnings
- **P1 Configuration Guide**: When fixType is missing, explains how to configure day2 repair
- **P1 Saving Priority**: Contribution percentage to global optimizable amount
- **P2 Policy History**: Compliance rate trend and violation recurrence count
- **Resource Context**: Resource type, component type, status, OS, and normalized datasource facts

## Safety Boundary

The skill only performs platform-native remediation through:

- `POST /compliance-policies/violations/day2/fix/{id}`

It does not call AWS or Azure APIs directly.

Resource-first analysis is read-only. It must not call:

- `POST /compliance-policies/execute`
- `POST /compliance-policies/violations/day2/fix/{id}`

Only an existing platform violation may enter the separate remediation flow. An
`llm_potential` result is never executable.

## Resource Enrichment

SmartCMP Provider resolves and reads resource evidence whenever a
recommendation includes `resourceId`.

- Pull resource details before rendering the final analysis output.
- Merge resource status/type/OS and normalized facts into `facts` and
  downstream recommendations.
- If resource lookup is unavailable, continue with policy/violation analysis as
  a best-effort degradation path.
