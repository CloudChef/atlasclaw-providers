# Alarm Workflow

Use this skill for SmartCMP-native alarm retrieval and operations, plus resource
health analysis based on component-specific monitoring evidence.

## Recommended Flow

1. Run `scripts/list_alerts.py` to inspect current alerts and capture
   `##ALARM_META_START##` output.
2. Run `scripts/analyze_alert.py <alert_id>` to fetch the alert, its alarm
   policy, optional overview context, and a structured assessment block.
   - If the alert exposes `entityInstanceId` or `nodeInstanceId`, silently call
     `../datasource/scripts/list_resource.py <resource_id ...>` through the
     datasource helper path.
   - Merge normalized resource facts into the alert's `facts[].resource`
     section before generating assessment and recommendations.
   - If datasource lookup fails, continue with core alert + policy analysis and
     treat resource context as optional enrichment.
3. If needed, run `scripts/operate_alert.py <alert_id> --action <mute|resolve|reopen>`
   to apply a validated status operation through SmartCMP.

## Resource Health Flow

Resource health analysis does not require an alert and does not evaluate alarm
rules:

1. Resolve one resource by exact visible name, a recent resource-list index, or
   an internal object-action ID.
2. Fetch the datasource normalized resource view and use its `componentType` to
   load `/alarm-policies/alarm-metric-groups` as the component monitoring-model
   catalog. Do not replace the model with a generic VM metric list.
3. Fetch `/nodes/{id}/monitor` for exporter identity and `/monitor/api_url` for
   the CMP-managed Prometheus endpoint.
4. Query every enabled metric definition that can be safely scoped through the
   model's labels and the resolved exporter/resource identity.
5. Emit `##RESOURCE_HEALTH_CONTEXT_START##` facts, coverage, compact current
   samples, and a seven-day statistical baseline. The AtlasClaw LLM must then
   decide `healthy`, `abnormal`, or `indeterminate` with cited evidence.

Disabled monitoring, unavailable endpoints, an unresolved component type, and
empty time series are evidence gaps. None of them proves that a resource is
healthy, and no remediation is executed from this flow.
Model templates that do not declare a bindable resource label are also reported
as unavailable evidence; the provider does not guess a label or run an
unscoped cross-resource query.

## Output Contracts

- `list_alerts.py` prints a short human summary and emits
  `##ALARM_META_START## ... ##ALARM_META_END##`.
- `analyze_alert.py` prints a short human summary and emits
  `##ALARM_ANALYSIS_START## ... ##ALARM_ANALYSIS_END##`.
- `operate_alert.py` prints a short human summary and emits
  `##ALARM_OPERATION_START## ... ##ALARM_OPERATION_END##`.
- `analyze_resource_health.py` prints a collection summary and emits
  `##RESOURCE_HEALTH_CONTEXT_START## ... ##RESOURCE_HEALTH_CONTEXT_END##`.

## Notes

- Alert analysis recommendations are deterministic and evidence-backed.
- Optional overview/stat context is best-effort and should not block core
  alert + policy analysis.
- Resource enrichment reuses the datasource skill's shared `list_resource.py`
  implementation instead of maintaining a separate resource lookup path.
- Status operations use English action names and map them to SmartCMP alert
  statuses.
- For Prometheus-oriented analysis, pass `alarmContext` as the primary input and
  treat `resource.data` as optional related context. See the provider-level
  [IT operation skill usage](../../../references/IT_OPERATION_SKILLS_USAGE.md).
