# Alarm Workflow

Use the four AtlasClaw alarm Tools. Their handlers are co-located in
`scripts/adapter.py`; SmartCMP Provider owns alert/resource resolution,
monitoring HTTP, pagination, and analysis evidence.

## Recommended flow

1. Call `smartcmp_list_alerts` and retain alert IDs from `_internal`.
2. Call `smartcmp_analyze_alert` for one exact alert. SmartCMP Provider
   enriches it with related resource evidence when available.
3. Call `smartcmp_operate_alert` only after the user explicitly requests
   `mute`, `resolve`, or `reopen`.

## Resource health flow

`analyze_resource_health` does not require an alert and does not use alarm
policy thresholds as a verdict:

1. Resolve one resource by exact visible name, recent resource-list index, or
   authorized object-action ID.
2. Load the effective monitoring model for its `componentType`.
3. Query only metrics that can be scoped to the resolved resource.
4. Return facts, coverage, compact samples, and a seven-day statistical
   baseline.
5. Let the AtlasClaw LLM decide `healthy`, `abnormal`, or `indeterminate` from
   those facts.

Disabled monitoring, unavailable endpoints, unresolved component type, and
empty time series are evidence gaps, not proof of health.

## Resource alert flow

For a comprehensive resource analysis, call `smartcmp_list_alerts` with the
exact resource selector and `resource_alert_scope=current_and_recent`.
SmartCMP Provider:

- queries current firing/muted alerts;
- queries currently resolved alerts whose `triggerAt` is within seven days;
- verifies exact `targetEntityId` association;
- preserves lifecycle races as partial evidence;
- distinguishes a complete empty result from incomplete association.

Never turn incomplete alert evidence into “no alerts”.

## Output

Handlers return a short visible summary plus `_internal` structured evidence.
Object actions remain in `_alarm_object_actions.py` because the embedded
assistant Context resolver also calls that helper.
