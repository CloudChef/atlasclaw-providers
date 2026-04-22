---
name: "cost-optimization"
description: "Cost optimization skill. Review FinOps and optimization recommendations, analyze savings opportunities with multi-dimensional insights plus datasource-enriched resource context, risk assessment, and best practices guidance. Execute native day2 remediation and track remediation state."
provider_type: "smartcmp"
instance_required: "true"

triggers:
  - cost optimization
  - optimization recommendations
  - savings recommendations
  - resource usage analysis
  - finops
  - rightsize
  - execute optimization
  - 费用优化
  - 成本优化
  - 优化建议
  - 节省建议
  - 降配
  - 空闲资源
  - 资源利用率
  - 查看优化建议

use_when:
  - User wants to list optimization or FinOps recommendations
  - User wants to analyze cost optimization opportunities with detailed insights, resource context, and risk assessment
  - User wants to understand saving contribution and priority in global context
  - User wants to execute native remediation for an optimization finding
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
tool_list_entrypoint: "scripts/list_recommendations.py"
tool_list_groups:
  - cmp
  - finops
tool_list_capability_class: "provider:smartcmp"
tool_list_priority: 100
tool_analyze_name: "smartcmp_analyze_cost_recommendation"
tool_analyze_description: "Analyze one SmartCMP cost optimization recommendation with multi-dimensional insights, datasource-enriched resource context, risk assessment, saving priority, and best practice guidance."
tool_analyze_entrypoint: "scripts/analyze_recommendation.py"
tool_analyze_groups:
  - cmp
  - finops
tool_analyze_capability_class: "provider:smartcmp"
tool_analyze_priority: 120
tool_execute_name: "smartcmp_execute_cost_optimization"
tool_execute_description: "Execute SmartCMP-native day2 remediation for a violation."
tool_execute_entrypoint: "scripts/execute_optimization.py"
tool_execute_groups:
  - cmp
  - finops
tool_execute_capability_class: "provider:smartcmp"
tool_execute_priority: 150
tool_track_name: "smartcmp_track_cost_optimization"
tool_track_description: "Track SmartCMP cost optimization remediation execution."
tool_track_entrypoint: "scripts/track_execution.py"
tool_track_groups:
  - cmp
  - finops
tool_track_capability_class: "provider:smartcmp"
tool_track_priority: 130
---

# cost-optimization

Use this skill to work through cost optimization recommendations from
discovery to remediation tracking.

## Workflow

1. List recommendations with `list_recommendations.py`
   - Optional: `--with-related-policies` to show related policy counts
2. Analyze a recommendation with `analyze_recommendation.py`
   - Silently resolve the related `resourceId` through datasource
     `../datasource/scripts/list_resource.py`
   - Merge normalized resource `type + properties` into the analysis facts
   - Returns multi-dimensional recommendations (P0/P1/P2 priority)
   - Includes risk assessment and best practice guidance
   - Shows saving contribution, policy history, and resource operational context
3. Execute a native day2 fix with `execute_optimization.py`
4. Track remediation state with `track_execution.py`

## Analysis Output Enhancement

The `analyze_recommendation.py` now provides:

- **P0 Primary Action**: Core recommendation (execute_fix / configure_platform_policy / manual_review)
- **P1 Risk Assessment**: Risk level (high/medium/low) with specific warnings
- **P1 Configuration Guide**: When fixType is missing, explains how to configure day2 repair
- **P1 Saving Priority**: Contribution percentage to global optimizable amount
- **P2 Policy History**: Compliance rate trend and violation recurrence count
- **Resource Context**: Resource type, component type, status, OS, and normalized datasource facts

## Safety Boundary

The skill only executes platform-native remediation through:

- `POST /compliance-policies/violations/day2/fix/{id}`

It does not call AWS or Azure APIs directly.

## Resource Enrichment

This skill should internally reuse the datasource skill's shared
`../datasource/scripts/list_resource.py` helper whenever a recommendation includes
`resourceId`.

- Pull resource details before rendering the final analysis output.
- Merge resource status/type/OS and normalized facts into `facts` and
  downstream recommendations.
- If resource lookup is unavailable, continue with policy/violation analysis as
  a best-effort degradation path.
