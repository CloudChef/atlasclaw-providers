# Cost Optimization Workflow

## Purpose

This skill manages SmartCMP-native cost optimization findings end to end.

## Recommended Flow

1. Run `list_recommendations.py` to discover candidate violations.
2. Run `analyze_recommendation.py --id <violation_id>` to inspect one finding.
3. Run `execute_optimization.py --id <violation_id>` only when the finding is
   ready for SmartCMP-native remediation.
4. Run `track_execution.py --id <violation_id>` to check remediation status.

## Execution Boundary

- Execution uses SmartCMP remediation only.
- The initial implementation targets `POST /compliance-policies/violations/day2/fix/{id}`.
- Public cloud best-practice guidance is explanatory only.
