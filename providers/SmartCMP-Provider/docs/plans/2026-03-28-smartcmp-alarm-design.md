# SmartCMP Alarm Capability Design

## Background

The SmartCMP provider currently supports resource requests, approval workflows,
and reference-data queries, but it explicitly avoids monitoring and alert use
cases. The SmartCMP platform itself already exposes alarm APIs for:

- triggered alert listing
- alarm rule retrieval
- overview and trend statistics
- alert status operations

The user requirement is to extend the existing SmartCMP provider so AtlasClaw
can retrieve alarms, analyze them, and execute status operations directly from
SmartCMP data. SmartCMP alarm data is implemented on top of Prometheus inside
the platform, but AtlasClaw should not add a separate Prometheus provider for
this feature.

## User Requirements

- Add alarm retrieval to the SmartCMP provider.
- Add alarm analysis that understands both the fired alert instance and the
  underlying alarm rule.
- Add extra recommendations, not just field-by-field restatement.
- Keep all provider-facing code and script interfaces in English.
- Only support alert status operations in the first version:
  - mute
  - resolve
  - reopen

## Existing SmartCMP API Surface

Relevant SmartCMP APIs already exist:

- `GET /alarm-alert`
  Query triggered alerts with filters such as status, trigger time, level,
  category, deployment, node instance, business group, and group.
- `PUT /alarm-alert/operation`
  Update alert status in batch through `AlarmAlertActionRequest`.
- `GET /alarm-alert/statuses`
  Return supported alert statuses.
- `GET /alarm-overview/today`
  Return current alarm overview counters.
- `GET /alarm-overview/recent`
  Return recent alarm list for contextual analysis.
- `GET /alarm-overview/alarm-trend`
  Return alarm trend over a day window.
- `GET /stats/alarm-alert/detail`
  Return alert detail summaries.
- `GET /alarm-policies/{id}`
  Return a single alarm policy by policy ID.
- `GET /alarm-policies/alarm-metrics`
  Return metrics by category.
- `GET /alarm-policies/alarm-metric-groups`
  Return metric groups by resource type.

The important platform schemas are:

- `AlarmAlert`
- `AlarmPolicy`
- `AlarmAlertActionRequest`
- `AlarmAlertDetail`

## Goals

- Extend `SmartCMP-Provider` with first-class alarm capability.
- Keep SmartCMP as the only data source for the first version.
- Produce analysis that separates facts from inference.
- Generate actionable recommendations with evidence and confidence.
- Preserve the provider's current script-oriented architecture and auth model.
- Keep all code identifiers, script names, action names, and structured output
  keys in English.

## Non-Goals

- Adding a Prometheus provider or direct Prometheus HTTP queries.
- Triggering remediation jobs or alarm operation tasks in the first version.
- Claiming root cause from incomplete data.
- Replacing SmartCMP's own alarm lifecycle semantics.

## Chosen Solution

Add a new `alarm` skill under `SmartCMP-Provider` and keep retrieval, analysis,
and status operation as separate scripts behind one user-facing skill.

This keeps the current provider style:

- `skills/shared/scripts/_common.py` continues to own authentication and shared
  request configuration.
- Alarm-specific normalization and helper logic lives under the new alarm skill.
- The provider remains SmartCMP-only, even when the analysis explains
  Prometheus-style rules.

## Skill Structure

Add:

- `providers/SmartCMP-Provider/skills/alarm/SKILL.md`
- `providers/SmartCMP-Provider/skills/alarm/references/WORKFLOW.md`
- `providers/SmartCMP-Provider/skills/alarm/scripts/_alarm_common.py`
- `providers/SmartCMP-Provider/skills/alarm/scripts/_analysis.py`
- `providers/SmartCMP-Provider/skills/alarm/scripts/list_alerts.py`
- `providers/SmartCMP-Provider/skills/alarm/scripts/analyze_alert.py`
- `providers/SmartCMP-Provider/skills/alarm/scripts/operate_alert.py`

The skill should advertise three user-facing capabilities:

- list triggered alerts
- analyze one alert
- update alert status

## Script Responsibilities

### `_alarm_common.py`

Owns SmartCMP alarm-specific helpers:

- standard alarm request headers via `_common.py`
- pagination defaults
- timestamp normalization
- response extraction helpers
- action-to-status mapping
- common argument parsing helpers

This avoids copying request and normalization logic across three scripts while
keeping generic auth code inside `skills/shared/scripts/_common.py`.

### `list_alerts.py`

Purpose:

- query triggered alerts from `/alarm-alert`
- expose high-signal filters
- print a human-readable summary
- emit machine-readable meta for downstream agents

Expected outputs:

- concise numbered list for people
- `##ALARM_META_START## ... ##ALARM_META_END##`

The meta block should include:

- alert ID
- policy ID
- status
- level
- trigger timestamps
- trigger count
- deployment and resource identity
- status-operation counters when available

### `analyze_alert.py`

Purpose:

- fetch alert instances
- fetch the corresponding alarm rules
- enrich with overview and alert-detail context
- build a structured analysis and recommendation result

It should support:

- single alert analysis by ID
- optional context windows such as recent days

### `operate_alert.py`

Purpose:

- expose a stable English action interface for AtlasClaw
- map actions to SmartCMP status values
- execute batch status changes through `/alarm-alert/operation`

Supported actions:

- `mute` -> `ALERT_MUTED`
- `resolve` -> `ALERT_RESOLVED`
- `reopen` -> `ALERT_FIRING`

## Analysis Pipeline

The analysis flow should be:

1. Resolve the target alert ID.
2. Query the alert instance through `GET /alarm-alert/{id}`.
3. Fetch the corresponding alarm rule through `/alarm-policies/{id}`.
4. Fetch short-horizon context from overview/stat endpoints:
   - `/alarm-overview/recent`
   - `/alarm-overview/alarm-trend`
   - `/stats/alarm-alert/detail`
5. Normalize all facts into a single analysis payload.
6. Run LLM reasoning on normalized facts only.
7. Emit human summary plus structured analysis JSON.

Metric metadata endpoints such as `/alarm-policies/alarm-metrics` and
`/alarm-policies/alarm-metric-groups` remain optional future enrichment and are
not part of the current implementation path.

## What The LLM Should Do

The LLM is valuable in the last stage, after facts are normalized.

It should:

- explain what the rule monitors in plain language
- interpret the alert pattern as persistent, repeated, noisy, or likely
  recovered
- estimate operational risk level from the available SmartCMP facts
- suggest next steps such as observe, investigate, mute, resolve, or reopen
- justify every recommendation with evidence from SmartCMP fields

It should not:

- invent missing metrics or unseen Prometheus samples
- claim direct root cause without supporting facts
- treat recommendations as confirmed platform facts

## Analysis Output Contract

`analyze_alert.py` should emit:

1. A short human-readable summary.
2. A structured block:

`##ALARM_ANALYSIS_START## ... ##ALARM_ANALYSIS_END##`

The structured result should follow this shape:

```json
{
  "alert_ids": ["..."],
  "facts": [
    {
      "alert_id": "...",
      "status": "ALERT_FIRING",
      "level": 3,
      "trigger_count": 12,
      "last_trigger_at": "2026-03-28T10:12:00Z",
      "resource": {
        "deployment_id": "...",
        "deployment_name": "...",
        "node_instance_id": "...",
        "resource_external_name": "..."
      },
      "rule": {
        "policy_id": "...",
        "name": "...",
        "description": "...",
        "category": "ALARM_CATEGORY_RESOURCE",
        "type": "ALARM_TYPE_METRIC",
        "metric": "...",
        "expression": "...",
        "resource_type": "..."
      }
    }
  ],
  "assessment": {
    "pattern": "persistent",
    "risk": "high",
    "reasoning": [
      "Repeated triggers without resolution indicate a sustained condition."
    ]
  },
  "recommendations": [
    {
      "action": "investigate",
      "applicability": "recommended",
      "confidence": "high",
      "reason": "The alert is still firing and has repeated recently.",
      "evidence": [
        "status=ALERT_FIRING",
        "trigger_count=12"
      ]
    }
  ],
  "suggested_status_operation": {
    "should_operate": false,
    "operation": "",
    "reason": "The alert is still active and should not be resolved yet."
  }
}
```

All field names and enum-like action names must remain English.

## Operation Output Contract

`operate_alert.py` should emit:

- human summary of the action taken
- `##ALARM_OPERATION_START## ... ##ALARM_OPERATION_END##`

The structured output should include:

- requested action
- mapped target status
- affected IDs
- SmartCMP response summary
- failures if any

## Error Handling

The scripts should fail fast and clearly when:

- SmartCMP auth is unavailable
- a target alert ID does not exist
- a rule ID cannot be resolved from an alert
- SmartCMP returns an unsupported status transition
- the analysis payload is missing required facts

Analysis should degrade safely:

- if overview data is unavailable, continue with alert + rule facts
- if metric metadata is unavailable, keep raw rule fields
- if LLM analysis fails, fall back to deterministic fact summary without
  recommendations

## Testing Strategy

The first implementation should add:

- unit tests for response normalization and action mapping
- unit tests for deterministic analysis helpers
- fixture-driven tests for structured JSON output shape
- live E2E smoke coverage in `test/run_e2e_tests.py` for:
  - `list_alerts.py`
  - `analyze_alert.py`
  - status operations kept non-destructive or skipped by default

## Documentation Changes

Update provider docs to reflect the new capability:

- `providers/SmartCMP-Provider/PROVIDER.md`
- `providers/SmartCMP-Provider/README.md`

The provider should no longer say alarm requests must use another monitoring
provider. Instead it should document SmartCMP-native alarm retrieval, analysis,
and status operations.

## Future Extension

If AtlasClaw later gains a Prometheus provider, the SmartCMP alarm analysis flow
can optionally enrich recommendations with Prometheus-native query evidence.
That future enhancement should plug into the analysis stage only. It should not
change the first-version SmartCMP-only provider boundary defined here.
