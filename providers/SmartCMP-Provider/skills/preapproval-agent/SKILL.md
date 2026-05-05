---
name: preapproval-agent
description: "Approval pre-review agent. Process webhook-driven approval items, analyze request reasonableness, and execute auditable approve/reject decisions."
provider_type: "smartcmp"
instance_required: "true"

tool_detail_name: "smartcmp_preapproval_get_request_detail"
tool_detail_description: "Fetch a specific pending approval/request detail for the preapproval agent and return metadata for continued decision-making."
tool_detail_entrypoint: "../approval/scripts/get_request_detail.py"
tool_detail_groups:
  - cmp
  - approval
tool_detail_capability_class: "provider:smartcmp"
tool_detail_priority: 122
tool_detail_result_mode: "llm"
tool_detail_cli_positional:
  - identifier
tool_detail_parameters: |
  {
    "type": "object",
    "properties": {
      "identifier": {
        "type": "string",
        "description": "Request ID, approval ID, task ID, or process instance ID to inspect."
      },
      "days": {
        "type": "integer",
        "description": "Lookback window in days when searching pending approvals",
        "default": 90
      }
    },
    "required": ["identifier"]
  }

tool_approve_name: "smartcmp_preapproval_approve"
tool_approve_description: "Approve one or more pending SmartCMP Request IDs for the preapproval agent. Use user-facing IDs such as RES20260505000010, TIC20260502000003, or CHG20260413000011; the shared approval script resolves them to currentActivity.id internally."
tool_approve_entrypoint: "../approval/scripts/approve.py"
tool_approve_groups:
  - cmp
  - approval
tool_approve_capability_class: "provider:smartcmp"
tool_approve_priority: 124
tool_approve_result_mode: "llm"
tool_approve_cli_positional:
  - ids
tool_approve_cli_split:
  - ids
tool_approve_parameters: |
  {
    "type": "object",
    "properties": {
      "ids": {
        "type": "string",
        "description": "SmartCMP Request ID(s) to approve. For multiple IDs, separate with spaces. Do not pass approval activity UUIDs."
      },
      "reason": {
        "type": "string",
        "description": "Approval reason to record in SmartCMP."
      }
    },
    "required": ["ids"]
  }

tool_reject_name: "smartcmp_preapproval_reject"
tool_reject_description: "Reject one or more pending SmartCMP Request IDs for the preapproval agent. Use user-facing IDs such as RES20260505000010, TIC20260502000003, or CHG20260413000011; the shared rejection script resolves them to currentActivity.id internally."
tool_reject_entrypoint: "../approval/scripts/reject.py"
tool_reject_groups:
  - cmp
  - approval
tool_reject_capability_class: "provider:smartcmp"
tool_reject_priority: 126
tool_reject_result_mode: "llm"
tool_reject_cli_positional:
  - ids
tool_reject_cli_split:
  - ids
tool_reject_parameters: |
  {
    "type": "object",
    "properties": {
      "ids": {
        "type": "string",
        "description": "SmartCMP Request ID(s) to reject. For multiple IDs, separate with spaces. Do not pass approval activity UUIDs."
      },
      "reason": {
        "type": "string",
        "description": "Rejection reason to record in SmartCMP."
      }
    },
    "required": ["ids"]
  }

# === LLM Context Fields ===
triggers:
  - webhook approval
  - auto approve
  - preapproval review
  - agent approver

use_when:
  - Webhook payload targets approval pre-review
  - Automated approval decision is required for a service request
  - agent_identity is agent-approver

avoid_when:
  - User manually wants to approve/reject (use approval skill)
  - User wants to query approval status (use approval skill)
  - User wants to submit a new request (use request skill)

examples:
  - "Process approval webhook for request #12345"
  - "Run preapproval agent on pending item"

related:
  - approval
  - request
---

# Preapproval Agent

Autonomous backend agent for approval pre-review. **Not a human confirmation flow.**

## Purpose

When triggered by a webhook:
1. Fetch and analyze approval request details
2. Evaluate request reasonableness against decision rubric
3. Execute approve/reject via existing approval skills
4. Return structured decision summary

## Trigger Conditions

This skill activates when:
- Webhook payload targets approval pre-review
- `agent_identity` is `agent-approver`
- Valid `request_id` is provided

## Robot Admin Execution

For webhook-driven backend execution, run this agent against an explicitly selected SmartCMP provider instance with a robot/admin credential. Set `ATLASCLAW_PROVIDER_INSTANCE` to the intended instance name; if that instance is not configured, execution must fail closed rather than falling back to `prod` or another instance.

The robot provider instance should use a SmartCMP `cmp_tk_*` provider token when available. The shared scripts send those tokens as `Authorization: Bearer <token>` and keep non-`cmp_tk_*` session tokens on the existing `CloudChef-Authenticate` header.

Treat `ATLASCLAW_USER_ID=webhook-*` as the AtlasClaw trigger identity, not as a CMP actor. Approval execution uses `../approval/scripts/approve.py` and `../approval/scripts/reject.py`, which load the selected robot credential through `_common.require_config()`.

Use this mode only for robot profiles whose `allowed_skills` include `smartcmp:preapproval-agent`. The same SmartCMP robot profile may also allow `smartcmp:request-decomposition-agent` when the same robot/admin account is approved for both workflows.

## Inputs

| Input | Type | Required | Description |
|-------|------|----------|-------------|
| `provider_instance` | string | Yes | CMP provider instance name (e.g., `cmp-prod`) |
| `robot_profile` | string | For webhook robot mode | Robot profile configured on the selected provider instance |
| `agent_identity` | string | Yes | Must be `agent-approver` |
| `request_id` | string | Yes | SmartCMP Request ID for execution, e.g. `RES20260505000010`, `TIC20260502000003`, or `CHG20260413000011` |
| `trigger_source` | string | No | Source label (e.g., `cmp-webhook`) |
| `policy_mode` | string | No | Policy preset (default: `balanced`) |

**Validation Rules:**
- If `request_id` is missing → **Stop immediately**
- If `request_id` cannot resolve to a pending approval activity → **Fail closed**
- If `agent_identity` ≠ `agent-approver` → **Stop immediately**

## Orchestrated Skills

This agent does NOT access the platform directly. It orchestrates:

| Skill | Purpose |
|-------|---------|
| `smartcmp_preapproval_get_request_detail` | Fetch pending approval details |
| `smartcmp_preapproval_approve` | Execute approval with reason |
| `smartcmp_preapproval_reject` | Execute rejection with reason |

## Workflow

```
1. Validate Inputs
   ├── Check provider_instance, agent_identity
   └── Verify request_id exists
         ↓
2. Fetch Approval Context
   └── smartcmp_preapproval_get_request_detail → Verify request_id
         ↓
3. Build Review Summary
   ├── Service/request name
   ├── Requester notes
   ├── Full parameters
   ├── Cost estimate
   └── Approval history
         ↓
4. Evaluate Against Rubric
   └── Apply 7-factor decision criteria
         ↓
5. Choose Outcome
   ├── approve
   ├── reject_with_guidance
   └── manual_review_required
         ↓
6. Execute Decision
   ├── approve → smartcmp_preapproval_approve <request_id> --reason "<comment>"
   ├── reject  → smartcmp_preapproval_reject <request_id> --reason "<comment>"
   └── manual  → reject with clear reason
         ↓
7. Return Structured Result
```

## Decision Rubric

### Approve When (most satisfied):

| Factor | Criteria |
|--------|----------|
| **Business Purpose** | Requester explains what the resource is for |
| **Resource Fit** | Size, environment, options proportional to stated use |
| **Configuration** | Parameters don't conflict, technically plausible |
| **Least-Necessary** | No excessive CPU, memory, storage without justification |
| **Environment** | Production requests have stronger rationale |
| **Cost** | Proportionate to described scenario |
| **Actionable Notes** | Description concrete enough for approval |

### Reject When (any true):

- No meaningful business justification
- Resources obviously oversized for stated need
- Production resources for vague/low-risk scenarios
- Request incomplete, contradictory, or copy-pasted
- Unusual/expensive resources without explanation
- Material risk with insufficient data

## Decision Style

> Be strict, concise, and auditable.

- Do NOT invent facts missing from request
- Do NOT ask requester follow-up questions
- Prefer rejection with guidance over speculative approval
- Explain what would make request approvable

## Comment Templates

**Approval example:**
```
Approved by agent pre-review. Business purpose clear, resource specs reasonable.
```

**Rejection example:**
```
Rejected by agent pre-review. Missing business justification, resource specs, and target environment. Please resubmit with details.
```

## Output Contract

```json
{
  "decision": "approve",
  "confidence": "high",
  "reasoning": [
    "Business purpose is explicit.",
    "Requested capacity proportional to described workload."
  ],
  "improvement_suggestions": [],
  "provider_action": {
    "skill": "../approval/scripts/approve.py",
    "success": true
  }
}
```

For rejections, include `improvement_suggestions`.

## Failure Handling

| Scenario | Action |
|----------|--------|
| Detail retrieval fails | Return failure, do NOT approve |
| Approval execution fails | Return provider error as-is |
| Rejection execution fails | Return provider error as-is |
| Ambiguous/expensive/high-risk | Reject with guidance |

## References

- [review-guidelines.md](references/review-guidelines.md) — Detailed review criteria
