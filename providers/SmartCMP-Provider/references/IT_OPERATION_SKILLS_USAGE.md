# SmartCMP and IT Operation Skills Usage

This document explains how the SmartCMP Provider works with external IT Operation standalone skills through loose coupling. The SmartCMP Provider only supplies context. Each operation skill performs its own domain-specific analysis and returns its own structured output. The output does not need to be converted into a CMP Finding and does not need to be written back to CMP.

## 1. Allow the Skills in the User Role First

These skills are loaded from `skills_root` and are standalone skills. The user's role must explicitly allow each skill before the runtime agent can see and select it.

Recommended skills for an IT operations analyst role:

| Skill | Purpose | Current status |
|---|---|---|
| `senior-secops` | General security baseline, vulnerability, and configuration-risk analysis | conditional; local scripts/references are missing |
| `information-security-manager-iso27001` | ISO 27001 risk, ISMS, and control analysis | conditional; local scripts/references are missing |
| `azure-policy` | Azure Policy compliance analysis | approved; prompt-only |
| `azure-security` | Azure security best-practice analysis | approved; prompt-only |
| `azure-cost-management` | Azure cost and utilization optimization | approved; prompt-only |
| `google-cloud-waf-security` | GCP Well-Architected Framework security-pillar analysis | approved; prompt-only |
| `prometheus-analysis` | Prometheus alert RCA and PromQL interpretation | conditional; `references/promql-cookbook.md` is missing |
| `prometheus` | Prometheus configuration, rule, and Alertmanager analysis | approved; prompt-only |

The required permission shape is:

```json
{
  "skill_id": "prometheus-analysis",
  "skill_name": "prometheus-analysis",
  "authorized": true,
  "enabled": true
}
```

If the `admin` or `user` role in the database has already initialized its skill permissions, newly added standalone skills might not be automatically appended to that existing role. Update the role permissions in the role management UI or through the corresponding role-management flow.

## 2. Context Provided by SmartCMP

The SmartCMP Provider does not bind external skills as internal APIs. The agent selects the appropriate context based on the user's request and passes that context to the selected skill.

| Scenario | SmartCMP input | Recommended skill |
|---|---|---|
| Resource security-attribute analysis | `resource.data` | `senior-secops`, `azure-security`, `google-cloud-waf-security` |
| Compliance controls and evidence analysis | `resource.data` | `information-security-manager-iso27001`, `azure-policy` |
| Alert and PromQL RCA | `alarmContext` | `prometheus-analysis`, `prometheus` |
| Cost and utilization analysis | `costContext` | `azure-cost-management` |

## 3. Prometheus Alert Analysis Example

The primary input for Prometheus analysis is `alarmContext`, not `resource.data`. Resource data is optional enrichment only.

Example input:

```json
{
  "alarmContext": {
    "alertId": "05769762-5e5d-456a-a98f-d107e878a535",
    "status": "ALERT_FIRING",
    "resource": "Computed827",
    "triggerCount": 79,
    "lastTriggerAt": "2025-07-14T07:13:41Z",
    "queryExpression": "avg_over_time(cloudchef:smartcmp:cpu_usage{tenant_id=\"default\",node_instance_id=\"Compute_xyrq6n\",fstype!=\"selinuxfs\"}[30m])",
    "ruleExpression": "avg_over_time(cloudchef:smartcmp:cpu_usage{tenant_id=\"default\"}[30m]) <= 80.0",
    "policyDescription": "CPU average greater than 80 over the last 30 minutes triggers the alert"
  }
}
```

Expected structured output from `prometheus-analysis`:

```json
{
  "finding": "CPU alarm rule has stale-state and threshold-direction risk",
  "severity": "high",
  "reasoning": [
    "SmartCMP reports ALERT_FIRING but lastTriggerAt is old.",
    "The policy description says CPU average greater than 80 triggers, while ruleExpression uses <= 80.0.",
    "Resource enrichment did not resolve a SmartCMP resource record."
  ],
  "recommendation": "Verify current Prometheus series, correct the rule operator if the description is authoritative, and reconcile stale alarm state before muting or resolving the alert.",
  "evidencePaths": [
    "alarmContext.status",
    "alarmContext.lastTriggerAt",
    "alarmContext.policyDescription",
    "alarmContext.ruleExpression",
    "alarmContext.resource"
  ],
  "confidence": "medium"
}
```

This example highlights three points:

- `ALERT_FIRING` with an old `lastTriggerAt` should first be checked as a possible stale alarm state.
- The alert description says CPU average greater than 80 should trigger, but the rule expression uses `<= 80.0`, so the threshold direction is inconsistent.
- If SmartCMP cannot resolve a resource ID, the analysis must not claim that the resource-level root cause has been confirmed.

## 4. Imported Skill Source Reference

The imported skill source inventory is maintained in:

```text
skills/README.md
```

That README is the source reference for upstream repositories, upstream paths, imported local assets, and optional download commands for missing scripts or reference files.

`conditional` does not mean unusable. It means local scripts or reference files are missing, or that the skill needs real cloud-platform, Prometheus, or API context to provide full value.
