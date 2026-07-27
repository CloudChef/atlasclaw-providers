---
name: "optimization-policy-designer"
description: "Use when reading or modifying the rule content and editable definition of the exact SmartCMP cost-optimization policy selected by an embedded policy-editor page Context."
provider_type: "smartcmp"
instance_required: "true"

triggers:
  - modify current optimization policy
  - improve cost optimization policy
  - update policy rule
  - 修改当前费用优化策略
  - 完善费用优化策略
  - 优化策略表达式

use_when:
  - User is interacting from a SmartCMP cost-optimization policy editor
  - User wants updated rule content or policy fields for manual copying into CMP

avoid_when:
  - User wants to execute remediation or apply a recommendation
  - User wants the Agent to save, enable, disable, publish, or delete a policy
  - The current page is a non-cost compliance policy editor

tool_current_name: "smartcmp_read_current_optimization_policy"
tool_current_description: "Read the exact saved cost-optimization policy bound to the active SmartCMP policy-editor Context. It validates the server-owned policy ID and cost-optimization category, uses the request user's session, and never writes to CMP."
tool_current_entrypoint: "scripts/read_current_policy.py:read_current_policy"
tool_current_groups:
  - cmp
  - optimization-policy-designer
tool_current_capability_class: "provider:smartcmp"
tool_current_priority: 115
tool_current_result_mode: "llm"
tool_current_parameters: |
  {
    "type": "object",
    "properties": {},
    "additionalProperties": false
  }
---

# optimization-policy-designer

Read the current saved cost-optimization policy and produce user-directed replacement content.

## Workflow

1. Always call `smartcmp_read_current_optimization_policy` first. Never ask for a policy ID already supplied by page Context.
2. Treat the returned rule, scope, resource types, severity, remediation text, notifications, and task definition as one policy contract.
3. Apply only the requested change. Preserve unrelated fields and the current expression language.
4. Return the complete updated `ruleContent` with no ellipses. If any other editor field changes, return a complete JSON object containing every changed field and its full replacement value.
5. Call out assumptions when the current policy or user request lacks metric, billing, resource-state, or remediation evidence. Never fabricate a metric or Provider field.
6. State that the output is for manual review and copying into CMP. Do not claim that the policy was saved, enabled, executed, or published.

## Safety

- No policy or remediation write APIs.
- No recommendation execution.
- Keep cost-optimization category and resource-type gates intact unless the user explicitly asks to change them.
