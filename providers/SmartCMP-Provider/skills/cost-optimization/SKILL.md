---
name: "cost-optimization"
description: "SmartCMP cost optimization skill. List optimization recommendations, analyze savings opportunities, execute SmartCMP-native day2 fixes, and track remediation state."
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

use_when:
  - User wants to list SmartCMP optimization recommendations
  - User wants to analyze cost optimization opportunities
  - User wants to execute SmartCMP-native remediation for an optimization finding
  - User wants to track cost optimization remediation progress

avoid_when:
  - User wants to provision new resources (use request skill)
  - User wants read-only catalog or pool discovery (use datasource skill)
  - User wants approval workflow actions (use approval skill)

related:
  - datasource
  - approval

tool_list_name: "smartcmp_list_cost_recommendations"
tool_list_description: "List SmartCMP cost optimization recommendations."
tool_list_entrypoint: "scripts/list_recommendations.py"
tool_analyze_name: "smartcmp_analyze_cost_recommendation"
tool_analyze_description: "Analyze one SmartCMP cost optimization recommendation."
tool_analyze_entrypoint: "scripts/analyze_recommendation.py"
tool_execute_name: "smartcmp_execute_cost_optimization"
tool_execute_description: "Execute SmartCMP-native day2 remediation for a violation."
tool_execute_entrypoint: "scripts/execute_optimization.py"
tool_track_name: "smartcmp_track_cost_optimization"
tool_track_description: "Track SmartCMP cost optimization remediation execution."
tool_track_entrypoint: "scripts/track_execution.py"
---

# SmartCMP Cost Optimization Skill

Use this skill to work through SmartCMP optimization recommendations from
discovery to remediation tracking.

## Workflow

1. List recommendations with `list_recommendations.py`
2. Analyze a recommendation with `analyze_recommendation.py`
3. Execute a SmartCMP-native day2 fix with `execute_optimization.py`
4. Track remediation state with `track_execution.py`

## Safety Boundary

The first version only executes SmartCMP-native remediation through:

- `POST /compliance-policies/violations/day2/fix/{id}`

It does not call AWS or Azure APIs directly.
