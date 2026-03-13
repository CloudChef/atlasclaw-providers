---
name: preapproval-agent
description: >
  Autonomous pre-review agent for CMP approval workflows. Triggered by webhooks,
  analyzes request reasonableness, and executes approve/reject decisions.
  Does NOT access CMP APIs directly - orchestrates existing approval skills.
---

# CMP Preapproval Agent

Autonomous backend agent for SmartCMP approval pre-review. **Not a human confirmation flow.**

## Purpose

When triggered by CMP webhook:
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

This agent does NOT access CMP directly. It orchestrates:

| Skill | Purpose |
|-------|---------|
| `approval/list_pending.py` | Fetch pending approval details |
| `approval/approve.py` | Execute approval with reason |
| `approval/reject.py` | Execute rejection with reason |

## Workflow

```
1. Validate Inputs
   ├── Check instance, agent_identity
   └── Verify approval_id or request_id exists
         ↓
2. Fetch Approval Context
   └── approval/list_pending.py → Filter by approval_id from META
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
   ├── approve → approval/approve.py <id> --reason "<comment>"
   ├── reject  → approval/reject.py <id> --reason "<comment>"
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
    "skill": "approval/approve.py",
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
