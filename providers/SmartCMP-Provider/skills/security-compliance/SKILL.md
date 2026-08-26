---
name: "security-compliance"
description: "SmartCMP Security compliance posture and policy-violation skill. Use it to view the overall Security compliance state, list Security violations, analyze one selected Security violation, or mark an already-remediated active violation FIXED after explicit confirmation. This skill owns CMP policy violations; resource-first LLM posture analysis belongs to the resource skill."
provider_type: "smartcmp"
instance_required: "true"

triggers:
  - security compliance overview
  - security compliance status
  - list security compliance
  - list security violations
  - show security violations
  - analyze security violation
  - mark security violation fixed
  - security policy violation
  - 安全合规总览
  - 安全合规情况
  - 查看所有安全合规
  - 查看安全违规
  - 查看所有安全违规
  - 查看全部安全违规
  - 分析安全违规
  - 分析第一个违规
  - 分析第 1 条违规
  - 标记安全违规已修复
  - 安全策略违规

use_when:
  - User wants the overall SmartCMP Security policy, execution, compliance, severity, violation, or trend state
  - User wants to browse all or filtered Security compliance violations
  - User selects a Security violation by its real metadata-backed ID or recent visible table index for analysis
  - User explicitly confirms marking an ACTIVED Security violation FIXED after manual remediation

avoid_when:
  - User asks whether a named or selected resource is secure or has violations (use resource skill)
  - User wants resource configuration, patch, lifecycle, exposure, or LLM posture analysis (use resource skill)
  - User wants Cost Optimization recommendations, savings, or Day-2 remediation (use cost-optimization skill)
  - User wants to edit or execute a compliance policy definition

related:
  - resource
  - cost-optimization
  - alarm

tool_overview_name: "smartcmp_get_security_overview"
tool_overview_description: "Get the SmartCMP Security compliance overview using the root SECURITY category. Aggregate compliance and violation summaries, Security policy and latest evaluation state, active violation severity, and compliance/violation trends. When start_time and end_time are omitted, use the latest 30 days. Never use SECURITY.* as a search category and never mix Cost Optimization findings into this result."
tool_overview_entrypoint: "scripts/adapter.py:get_security_overview"
tool_overview_groups:
  - cmp
  - security
  - compliance
tool_overview_capability_class: "provider:smartcmp"
tool_overview_priority: 108
tool_overview_result_mode: "llm"
tool_overview_parameters: |
  {
    "type": "object",
    "properties": {
      "start_time": {
        "type": "integer",
        "description": "Optional trend start in Unix epoch milliseconds. Omit with end_time for the latest 30 days."
      },
      "end_time": {
        "type": "integer",
        "description": "Optional trend end in Unix epoch milliseconds. Omit with start_time for the latest 30 days."
      }
    }
  }

tool_list_name: "smartcmp_list_security_violations"
tool_list_description: "List SmartCMP Security compliance violations. Always query the root category SECURITY so SECURITY subcategories are included; never send SECURITY.*. Requests use one-based pages. Preserve total, scanned_pages, has_more, next_page, coverage, and truncated, and retain each real violation ID in hidden object metadata. List rows expose Analyze only; they must not expose Mark Fixed before a fresh single-violation analysis."
tool_list_entrypoint: "scripts/adapter.py:list_security_violations"
tool_list_groups:
  - cmp
  - security
  - compliance
tool_list_capability_class: "provider:smartcmp"
tool_list_priority: 112
tool_list_result_mode: "llm"
tool_list_cli_split:
  - severities
tool_list_parameters: |
  {
    "type": "object",
    "properties": {
      "status": {
        "type": "string",
        "enum": ["ACTIVED", "FIXED", "ALL"],
        "description": "Violation state. Default: ACTIVED. Use ALL to omit the state filter.",
        "default": "ACTIVED"
      },
      "severities": {
        "type": "string",
        "description": "Optional comma- or whitespace-separated severity values."
      },
      "query_value": {
        "type": "string",
        "description": "Optional CMP free-text filter."
      },
      "page": {
        "type": "integer",
        "description": "One-based first page. Default: 1.",
        "default": 1,
        "minimum": 1
      },
      "size": {
        "type": "integer",
        "description": "Page size. Default: 20.",
        "default": 20,
        "minimum": 1,
        "maximum": 100
      },
      "max_pages": {
        "type": "integer",
        "description": "Maximum pages to scan. Default: 1.",
        "default": 1,
        "minimum": 1,
        "maximum": 50
      }
    }
  }

tool_analyze_name: "smartcmp_analyze_security_violation"
tool_analyze_description: "Required first phase before Mark Fixed. Re-read one authoritative SmartCMP Security violation by its real ID, validate category SECURITY or SECURITY.*, and enrich current policy/resource facts best-effort. Present the latest violation, resource, policy, evidence gaps, manual remediation, validation steps, and the fact that Mark Fixed will not modify the resource; then stop and wait for explicit confirmation. Do not call Mark Fixed in the same turn or return Cost/Day-2 semantics."
tool_analyze_entrypoint: "scripts/adapter.py:analyze_security_violation"
tool_analyze_groups:
  - cmp
  - security
  - compliance
tool_analyze_capability_class: "provider:smartcmp"
tool_analyze_priority: 125
tool_analyze_result_mode: "llm"
tool_analyze_cli_positional:
  - violation_id
tool_analyze_parameters: |
  {
    "type": "object",
    "properties": {
      "violation_id": {
        "type": "string",
        "description": "Real SmartCMP Security violation ID from trusted list or page metadata. Never pass the visible table index."
      }
    },
    "required": ["violation_id"]
  }

tool_mark_fixed_name: "smartcmp_mark_security_violation_fixed"
tool_mark_fixed_description: "Second phase only, after the immediately preceding fresh analysis displayed the exact ACTIVED violation, resource, policy, and status-only effect and the user explicitly confirmed those latest facts. Re-read the violation and mark only its status FIXED; do not modify the resource. Submit at most once, do not retry an unknown timeout/5xx outcome, then report before/after status with resource_remediated=false."
tool_mark_fixed_entrypoint: "scripts/adapter.py:mark_security_violation_fixed"
tool_mark_fixed_groups:
  - cmp
  - security
  - compliance
tool_mark_fixed_capability_class: "provider:smartcmp"
tool_mark_fixed_priority: 145
tool_mark_fixed_result_mode: "tool_only_ok"
tool_mark_fixed_cli_positional:
  - violation_id
tool_mark_fixed_parameters: |
  {
    "type": "object",
    "properties": {
      "violation_id": {
        "type": "string",
        "description": "Real SmartCMP Security violation ID shown during confirmation."
      },
      "confirmed": {
        "type": "boolean",
        "description": "True only after the user explicitly confirms this status-only change. This argument must be supplied explicitly and has no default."
      }
    },
    "required": ["violation_id", "confirmed"]
  }
---

# security-compliance

Use this Skill for CMP policy-derived Security compliance state and violations.
Use the `resource` Skill when the request starts from a resource and asks for
its security posture or associated violations.

## Workflow

- Call `smartcmp_get_security_overview` for the overall Security posture.
- Call `smartcmp_list_security_violations` for collection browsing. Keep real
  violation IDs in metadata and resolve “第 N 条” through the latest list result.
  Collection rows expose Analyze only.
- Phase 1: call `smartcmp_analyze_security_violation`. Re-read and display the
  latest violation status, resource, policy, evidence, manual guidance, and the
  fact that Mark Fixed will not modify the resource. Stop and wait for explicit
  confirmation; never mark it FIXED in this turn.
- Phase 2: only in the next confirmed turn, call
  `smartcmp_mark_security_violation_fixed` for the exact freshly analyzed
  `ACTIVED` object. This is a status write, not resource remediation.

## Evidence and safety rules

- Treat CMP violation and policy facts as confirmed evidence. Label model
  interpretation as inference and unavailable enrichment as missing evidence.
- Accept only `SECURITY` and `SECURITY.*` violation categories.
- Never infer native remediation from `remedie`, `executeParameters`, or null
  task fields. Provide manual guidance and post-change validation only.
- Do not equate `FIXED` with a repaired resource. A later policy evaluation may
  recreate the violation.
- Continue analysis when policy or resource enrichment is unavailable, while
  reporting the missing evidence explicitly.

Read [references/WORKFLOW.md](references/WORKFLOW.md) before handling a status
change or when pagination and evidence coverage affect the conclusion.
