---
name: "alarm"
description: "SmartCMP alarm management. List alerts, analyze alert rules, and perform alert status operations."
provider_type: "smartcmp"
instance_required: "true"

# === LLM Context Fields ===
triggers:
  - list alarms
  - show alerts
  - analyze alert
  - mute alert
  - resolve alert
  - reopen alert
  - operate alert

use_when:
  - User wants to inspect SmartCMP alarms or alerts
  - User needs rule-aware alarm analysis with recommendations
  - User wants to mute, resolve, or reopen SmartCMP alerts

avoid_when:
  - User wants approval actions (use approval skill)
  - User wants resource requests (use request skill)
  - User wants reference data browsing (use datasource skill)

examples:
  - "Show current alarms"
  - "Analyze alert ALM-1001"
  - "Mute alert ALM-1001"
  - "Resolve alerts ALM-1001 and ALM-1002"

related:
  - approval
  - datasource
---

# alarm

SmartCMP alarm workflow for triggered alert retrieval, rule-aware analysis, and
status operations.

## Purpose

Provide SmartCMP-native alarm capabilities:
- List triggered alerts with machine-readable metadata
- Analyze one alert with normalized facts, assessment, and recommendations
- Perform validated status operations (`mute`, `resolve`, `reopen`)

## Scripts

| Script | Description | Location |
|--------|-------------|----------|
| `list_alerts.py` | Query `/alarm-alert` and emit `##ALARM_META_START##` metadata | `scripts/` |
| `analyze_alert.py` | Fetch alert + rule context and emit `##ALARM_ANALYSIS_START##` output | `scripts/` |
| `operate_alert.py` | Call `/alarm-alert/operation` for validated status changes | `scripts/` |

## Workflow

See [references/WORKFLOW.md](references/WORKFLOW.md) for the supported workflow.
