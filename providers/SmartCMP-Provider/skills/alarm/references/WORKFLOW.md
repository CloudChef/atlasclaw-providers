# Alarm Workflow

Use this skill for SmartCMP-native alarm retrieval, analysis, and alert status
operations.

## Recommended Flow

1. Run `scripts/list_alerts.py` to inspect current alerts and capture
   `##ALARM_META_START##` output.
2. Run `scripts/analyze_alert.py <alert_id>` to fetch the alert, its alarm
   policy, optional overview context, and a structured assessment block.
   - If the alert exposes `entityInstanceId` or `nodeInstanceId`, silently call
     `../shared/scripts/list_resource.py <resource_id ...>` through the shared
     datasource helper path.
   - Merge normalized resource facts into the alert's `facts[].resource`
     section before generating assessment and recommendations.
   - If datasource lookup fails, continue with core alert + policy analysis and
     treat resource context as optional enrichment.
3. If needed, run `scripts/operate_alert.py <alert_id> --action <mute|resolve|reopen>`
   to apply a validated status operation through SmartCMP.

## Output Contracts

- `list_alerts.py` prints a short human summary and emits
  `##ALARM_META_START## ... ##ALARM_META_END##`.
- `analyze_alert.py` prints a short human summary and emits
  `##ALARM_ANALYSIS_START## ... ##ALARM_ANALYSIS_END##`.
- `operate_alert.py` prints a short human summary and emits
  `##ALARM_OPERATION_START## ... ##ALARM_OPERATION_END##`.

## Notes

- Alert analysis recommendations are deterministic and evidence-backed.
- Optional overview/stat context is best-effort and should not block core
  alert + policy analysis.
- Resource enrichment reuses the datasource skill's shared `list_resource.py`
  implementation instead of maintaining a separate resource lookup path.
- Status operations use English action names and map them to SmartCMP alert
  statuses.
