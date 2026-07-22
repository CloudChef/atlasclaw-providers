# Cost Optimization Workflow

## Purpose

This skill supports both SmartCMP-native recommendation handling and read-only resource-first cost analysis.

## Recommended Flow

### Recommendation flow

1. Run `list_recommendations.py` to discover candidate violations.
   - Add `--with-related-policies` to show count of related policies in the same category.
2. Run `analyze_recommendation.py --id <violation_id>` to get detailed insights.
   - If the violation exposes `resourceId`, silently call
     `../datasource/scripts/list_resource.py <resource_id>` via the datasource
     helper path.
   - Merge the returned normalized `type + properties` data into analysis
     facts before scoring recommendations and rendering output.
   - If datasource lookup fails, keep the violation/policy analysis and mark
     resource context as best-effort only.
   - Returns P0/P1/P2 priority recommendations
   - Includes risk level (high/medium/low) and warnings
   - Shows saving contribution percentage, policy history, and resource context
3. Run `execute_optimization.py --id <violation_id>` only when the finding is ready for SmartCMP-native remediation.
4. Run `track_execution.py --id <violation_id>` to check remediation status.

### Resource-first flow

1. Run `analyze_resource_cost.py` with an exact resource name or a recent resource-list index.
2. Resolve the resource internally and collect only bounded cost-relevant facts.
3. Match enabled cost policy configurations by resource type and supported scope fields.
4. Correlate active violations and the latest exact resource execution without running policies.
5. Pass the structured evidence to the LLM using the contract in
   [RESOURCE_ANALYSIS.md](RESOURCE_ANALYSIS.md).
6. If the result contains a platform violation, use the recommendation flow for detailed analysis;
   never remediate an `llm_potential` result.

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
- Resource enrichment reuses datasource's `list_resource.py` instead of a
  separate lookup implementation.
- Resource-first analysis does not invoke policy execution or day2 remediation endpoints.
- A policy result without explicit complete evidence is not treated as proof that no opportunity exists.
