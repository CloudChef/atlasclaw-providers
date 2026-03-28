---
name: preapproval-agent
description: "Approval pre-review agent. Process webhook-driven approval items, analyze request reasonableness, and execute auditable approve/reject decisions."
provider_type: "smartcmp"
instance_required: "true"

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
- Valid `approval_id` or `request_id` is provided

## Inputs

| Input | Type | Required | Description |
|-------|------|----------|-------------|
| `instance` | string | Yes | CMP provider instance name (e.g., `cmp-prod`) |
| `agent_identity` | string | Yes | Must be `agent-approver` |
| `approval_id` | string | Yes* | Approval ID for execution |
| `request_id` | string | No | Alternative ID if `approval_id` not available |
| `trigger_source` | string | No | Source label (e.g., `cmp-webhook`) |
| `policy_mode` | string | No | Policy preset (default: `balanced`) |

**Validation Rules:**
- If both `approval_id` and `request_id` are missing → **Stop immediately**
- If only `request_id` and cannot resolve to `approval_id` → **Fail closed**
- If `agent_identity` ≠ `agent-approver` → **Stop immediately**

## Orchestrated Skills

This agent does NOT access the platform directly. It orchestrates:

| Skill | Purpose |
|-------|---------|
| `../approval/scripts/list_pending.py` | Fetch pending approval details |
| `../approval/scripts/approve.py` | Execute approval with reason |
| `../approval/scripts/reject.py` | Execute rejection with reason |

## Workflow

```
1. Validate Inputs
   ├── Check instance, agent_identity
   └── Verify approval_id or request_id exists
         ↓
2. Fetch Approval Context
   └── ../approval/scripts/list_pending.py → Filter by approval_id from META
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
   ├── approve → ../approval/scripts/approve.py <id> --reason "<comment>"
   ├── reject  → ../approval/scripts/reject.py <id> --reason "<comment>"
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

**Approval:**
```
Approved by agent pre-review. Business purpose is clear, requested resources 
match the described scenario, and no obvious overprovisioning detected.
```

**Rejection:**
```
Rejected by agent pre-review. The request does not provide sufficient 
justification for the requested resources or environment. Please clarify 
the business purpose, expected workload, target environment, and why the 
selected capacity is necessary.
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
