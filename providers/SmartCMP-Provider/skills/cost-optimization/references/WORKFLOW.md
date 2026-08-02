# Cost Optimization Workflow

## Recommendation flow

1. Call `smartcmp_list_cost_recommendations`.
2. Call `smartcmp_analyze_cost_recommendation` for one violation ID.
3. Call `smartcmp_execute_cost_optimization` only when the user explicitly
   requests remediation of an existing SmartCMP finding.
4. Call `smartcmp_track_cost_optimization` to read remediation status.

SmartCMP Provider resolves related resource evidence and keeps missing
evidence explicit. The Adapter does not call datasource scripts or duplicate
resource analysis.

## Resource-first flow

1. Call `smartcmp_analyze_resource_cost` with an exact visible resource name,
   recent list index, or authorized compatibility ID.
2. Correlate enabled applicable policies, the latest exact-resource execution,
   active violations, billing facts, and missing evidence.
3. Keep platform-confirmed findings separate from `llm_potential`.
4. Never execute remediation for an `llm_potential` result.

See [RESOURCE_ANALYSIS.md](RESOURCE_ANALYSIS.md) for the LLM evidence contract.

## Execution boundary

- Execution uses SmartCMP native remediation only.
- Resource-first analysis is read-only.
- A policy result without complete evidence is not proof that no optimization
  opportunity exists.
- The Skill does not call public-cloud APIs directly.

`../scripts/_cost_object_actions.py` remains separate because the embedded
assistant Context resolver also calls it; it is not a Tool forwarding module.
