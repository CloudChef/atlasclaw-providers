# Cost Optimization Workflow

## Purpose

This skill manages SmartCMP-native cost optimization findings end to end, providing multi-dimensional analysis with risk assessment and best practice guidance.

## Recommended Flow

1. Run `list_recommendations.py` to discover candidate violations.
   - Add `--with-related-policies` to show count of related policies in the same category.
2. Run `analyze_recommendation.py --id <violation_id>` to get detailed insights.
   - If the violation exposes `resourceId`, silently call
     `../shared/scripts/list_resource.py <resource_id>` via the shared
     datasource helper path.
   - Merge the returned normalized `type + properties` data into analysis
     facts before scoring recommendations and rendering output.
   - If datasource lookup fails, keep the violation/policy analysis and mark
     resource context as best-effort only.
   - Returns P0/P1/P2 priority recommendations
   - Includes risk level (high/medium/low) and warnings
   - Shows saving contribution percentage, policy history, and resource context
3. Run `execute_optimization.py --id <violation_id>` only when the finding is ready for SmartCMP-native remediation.
4. Run `track_execution.py --id <violation_id>` to check remediation status.

## Analysis Output Format

The `analyze_recommendation.py` output includes:

```
Violation {id}: {executionReadiness}
Theme: {optimizationTheme} ({violationType})
Resource: {resourceName}
Estimated monthly saving: ${saving} ({pct}% of total optimizable)
Policy compliance: {complianceRate}% | Occurrences: {times}
Risk level: {riskLevel}

[P0] Primary Action: {action} - {reason}
[P1] Risk Assessment: Level {risk} - {riskNotes}
[P1] Configuration Guide: (only when fixType is missing)
[P1] Saving Priority: {savingPriority}
[P2] Policy History: {policyHistory}

Best Practice:
  {bestPracticeGuidance}
```

## Execution Boundary

- Execution uses SmartCMP remediation only.
- The implementation targets `POST /compliance-policies/violations/day2/fix/{id}`.
- Best-practice guidance is provided for user reference before execution.
- Resource enrichment reuses datasource's shared `list_resource.py` instead of a
  separate lookup implementation.
