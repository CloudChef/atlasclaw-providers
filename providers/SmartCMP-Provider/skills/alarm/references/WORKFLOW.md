# Alarm Workflow

Use this skill for SmartCMP-native alarm retrieval, analysis, and alert status
operations.

## Recommended Flow

1. Run `scripts/list_alerts.py` to inspect current alerts and capture
   `##ALARM_META_START##` output.
2. Run `scripts/analyze_alert.py <alert_id>` to fetch the alert, its alarm
   policy, optional overview context, and a structured assessment block.
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
- Status operations use English action names and map them to SmartCMP alert
  statuses.
