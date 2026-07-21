---
name: "alarm"
description: "Alarm and resource health skill. List and analyze alerts, collect component-model-driven resource monitoring evidence for LLM health analysis, and perform alert status operations."
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
  - analyze resource health
  - check resource health
  - check vm health
  - resource monitoring analysis
  - 查看告警
  - 查看我的告警
  - 告警列表
  - 分析告警
  - 静默告警
  - 解决告警
  - 重新打开告警
  - 告警操作
  - 分析资源健康
  - 检查资源运行状态
  - 云主机是否正常
  - 分析资源监控指标

use_when:
  - User wants to inspect alarms or alerts
  - User needs rule-aware, resource-aware alarm analysis with remediation recommendations
  - User wants to mute, resolve, or reopen alerts
  - User wants to determine whether one resource is operating normally from its component monitoring model and current metric evidence

avoid_when:
  - User wants approval actions (use approval skill)
  - User wants resource requests (use request skill)
  - User only wants standalone reference data browsing without alarm analysis (use datasource skill)
  - User wants compliance, lifecycle, version, patch, or security analysis (use resource-compliance skill)

examples:
  - "Show current alarms"
  - "Analyze alert ALM-1001"
  - "Mute alert ALM-1001"
  - "Resolve alerts ALM-1001 and ALM-1002"
  - "查看我的告警"
  - "查看告警"
  - "分析告警 ALM-1001"
  - "静默告警 ALM-1001"
  - "Analyze resource health for aws-rds-prod"
  - "检查 vm-01 当前运行是否正常"

related:
  - approval
  - datasource
  - resource
  - resource-compliance

tool_list_name: "smartcmp_list_alerts"
tool_list_description: "List SmartCMP triggered alerts with optional filters for status, severity level, time range, deployment, entity instance, node instance, alarm type, alarm category, and keyword query."
tool_list_entrypoint: "scripts/list_alerts.py"
tool_list_groups:
  - cmp
  - alarm
tool_list_capability_class: "provider:smartcmp"
tool_list_priority: 100

tool_analyze_name: "smartcmp_analyze_alert"
tool_analyze_description: "Analyze one SmartCMP alert with rule context, datasource-enriched resource facts, assessment, and remediation guidance. Always pass a real SmartCMP alertId as alert_id. If the user refers to a numbered result from a prior alert list, resolve that display index from the previous smartcmp_list_alerts metadata and pass that item's alertId, not the display index."
tool_analyze_entrypoint: "scripts/analyze_alert.py"
tool_analyze_groups:
  - cmp
  - alarm
tool_analyze_capability_class: "provider:smartcmp"
tool_analyze_priority: 120
tool_analyze_cli_positional:
  - alert_id
tool_analyze_parameters: |
  {
    "type": "object",
    "properties": {
      "alert_id": {
        "type": "string",
        "description": "SmartCMP alertId to analyze. If the user references a numbered alert result, use the alertId from the matching previous smartcmp_list_alerts metadata item; do not pass the display index."
      },
      "days": {
        "type": "integer",
        "description": "Trend lookback window in days. Default: 7.",
        "default": 7
      }
    },
    "required": ["alert_id"]
  }

tool_resource_health_name: "analyze_resource_health"
tool_resource_health_description: "Collect resource facts and real Prometheus time-series evidence using the exact monitoring model defined for the resource componentType, then use the LLM to determine healthy, abnormal, or indeterminate. Use this for resource health or runtime-normality questions, including VM, database, software, hardware, and virtualization resources. Do not substitute generic VM metrics, do not use alert rules or absence of alerts as health evidence, and do not expose internal resource IDs. Prefer resource_name or a visible resource_index resolved from recent smartcmp_list_all_resource metadata. After the tool returns, explain the health conclusion with metric evidence, confidence, missing evidence, and recommended next steps; never execute remediation automatically."
tool_resource_health_entrypoint: "scripts/analyze_resource_health.py"
tool_resource_health_groups:
  - cmp
  - monitoring
  - resource
tool_resource_health_capability_class: "provider:smartcmp"
tool_resource_health_priority: 125
tool_resource_health_result_mode: "llm"
tool_resource_health_parameters: |
  {
    "type": "object",
    "properties": {
      "resource_name": {
        "type": "string",
        "description": "Exact visible SmartCMP resource name. Prefer this for interactive requests."
      },
      "resource_index": {
        "type": "integer",
        "description": "Visible table # value from the latest smartcmp_list_all_resource result."
      },
      "resource_directory_json": {
        "type": "string",
        "description": "Hidden JSON metadata from the latest smartcmp_list_all_resource result or Current Workflow Context. Pass this when resolving a visible table # value."
      },
      "resource_id": {
        "type": "string",
        "description": "Compatibility-only internal SmartCMP resource ID for object actions or backend flows. Do not request this from users or expose it in the final reply."
      },
      "window_hours": {
        "type": "integer",
        "description": "Current monitoring analysis window from 1 to 168 hours. Default: 24.",
        "default": 24,
        "minimum": 1,
        "maximum": 168
      }
    }
  }

tool_operate_name: "smartcmp_operate_alert"
tool_operate_description: "Perform validated status operations (mute, resolve, reopen) on one or more SmartCMP alerts. Always pass real SmartCMP alert IDs; resolve numbered result references from prior smartcmp_list_alerts metadata before calling."
tool_operate_entrypoint: "scripts/operate_alert.py"
tool_operate_groups:
  - cmp
  - alarm
tool_operate_capability_class: "provider:smartcmp"
tool_operate_priority: 150
tool_operate_cli_positional:
  - alert_ids
tool_operate_cli_split:
  - alert_ids
tool_operate_parameters: |
  {
    "type": "object",
    "properties": {
      "alert_ids": {
        "type": "string",
        "description": "One or more SmartCMP alert IDs separated by spaces. If the user references numbered alert results, first resolve each display index to its alertId from prior smartcmp_list_alerts metadata."
      },
      "action": {
        "type": "string",
        "enum": ["mute", "resolve", "reopen"],
        "description": "Status operation to perform on the target alert IDs."
      }
    },
    "required": ["alert_ids", "action"]
  }
---

# alarm

Alarm and resource-health workflow for triggered alert retrieval, rule-aware
alert analysis, component-model-driven resource health evidence, and status operations.

## Purpose

Provide alarm-management capabilities:
- List triggered alerts with machine-readable metadata
- Analyze one alert with normalized facts, datasource-enriched resource context, assessment, and remediation guidance
- Analyze one resource independently of alerts by handing component-specific monitoring evidence to the LLM
- Perform validated status operations (`mute`, `resolve`, `reopen`)

## Scripts

| Script | Description | Location |
|--------|-------------|----------|
| `list_alerts.py` | Query `/alarm-alert` and emit `##ALARM_META_START##` metadata | `scripts/` |
| `analyze_alert.py` | Fetch alert + rule context, enrich related resources via datasource `list_resource.py`, and emit `##ALARM_ANALYSIS_START##` output | `scripts/` |
| `analyze_resource_health.py` | Resolve one resource, load its component monitoring model, query scoped Prometheus series, and emit `##RESOURCE_HEALTH_CONTEXT_START##` evidence for LLM analysis | `scripts/` |
| `operate_alert.py` | Call `/alarm-alert/operation` for validated status changes | `scripts/` |

## Workflow

See [references/WORKFLOW.md](references/WORKFLOW.md) for the supported workflow.

## Resource Enrichment

During alert analysis, this skill should silently reuse the datasource skill's
shared `../datasource/scripts/list_resource.py` flow when the alert exposes
`entityInstanceId` or `nodeInstanceId`.

- Resolve related SmartCMP resources before finalizing the analysis narrative.
- Merge normalized `type + properties` resource facts into the alert analysis payload.
- If resource lookup is unavailable, continue the alert analysis with core alert
  and policy facts, and treat resource enrichment as best-effort context.

## Resource Health Analysis

Resource health analysis is independent of alert analysis:

- Resolve the resource through datasource resource helpers and use its normalized `componentType`.
- Load the effective monitoring model for that component; never substitute a generic VM metric list.
- Query only PromQL that can be scoped to the resolved resource through model-declared labels and exporter identity.
- Emit descriptive statistics and monitoring coverage, but leave `healthy`, `abnormal`, or `indeterminate` judgment to the AtlasClaw LLM.
- The final LLM response must include status, confidence, principal findings, metric evidence, missing evidence, and recommended actions.
- Treat disabled, unavailable, or missing monitoring as an evidence gap rather than proof that the resource is healthy or unhealthy.
- Do not read active alerts or alarm-policy thresholds for the resource-health conclusion.
