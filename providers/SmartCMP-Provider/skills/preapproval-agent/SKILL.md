---
name: preapproval-agent
description: >
  Use when UniClaw receives a CMP webhook for autonomous pre-review of a CMP
  application or approval item. This skill analyzes request reasonableness,
  decides whether the request should be approved or rejected, and then calls
  existing CMP Provider approval skills to execute the final decision. It does
  not call CMP APIs directly.
---

# CMP Request Preapproval Agent

Use this skill for backend, agent-driven approval only. This is not a human confirmation flow.

The webhook tells UniClaw to run this skill and includes the target request identifier. The skill must review the request content, judge whether the requested resources and scenario are reasonable, and then approve or reject by calling existing CMP Provider skills.

## Inputs

Expect these inputs from the webhook payload or runtime context:

- `instance`: CMP provider instance name, for example `cmp-prod`
- `agent_identity`: Must be `agent-approver`
- `approval_id`: Preferred identifier for approval execution
- `request_id`: Optional request identifier if upstream has not normalized to `approval_id`
- `trigger_source`: Optional source label such as `cmp-webhook`
- `policy_mode`: Optional policy preset, default `balanced`

If both `approval_id` and `request_id` are missing, stop immediately and return a failed result for manual handling.

If only `request_id` is present and no provider skill can resolve it to an `approval_id`, fail closed. Do not guess.

If `agent_identity` is not `agent-approver`, stop. This skill must run only under the dedicated CMP approval agent account.

## Provider Skills This Skill May Call

This skill must not access CMP directly. It should orchestrate existing provider skills only.

- `approval/list_pending.py` — Fetch pending approval details (use `##APPROVAL_META##` block for structured data)
- `approval/approve.py` — Execute approval with optional reason
- `approval/reject.py` — Execute rejection with reason

If the provider later exposes helper skills for ID resolution or enrichment, they may be used before review. Keep this skill focused on decisioning and orchestration.

## Workflow

1. Validate input identifiers and provider instance.
2. Fetch full approval context via `approval/list_pending.py` (filter by approval_id from META block).
3. Build a review summary from:
   - service or request name
   - requester notes
   - full parameters
   - cost estimate
   - approval history if present
4. Evaluate the request against the decision rubric below.
5. Choose one of three outcomes:
   - `approve`: request is reasonable and sufficiently justified
   - `reject_with_guidance`: request is not reasonable or not sufficiently justified
   - `manual_review_required`: evidence is incomplete, identifier cannot be resolved, or the case is high risk
6. Execute the decision:
   - for `approve`, call `approval/approve.py <approval_id> --reason "<comment>"`
   - for `reject_with_guidance`, call `approval/reject.py <approval_id> --reason "<comment>"`
   - for `manual_review_required`, prefer reject with a clear reason unless the surrounding workflow explicitly supports a non-terminal manual handoff
7. Return a structured result with decision, rationale, key signals, and the provider operation outcome.

## Decision Rubric

Judge reasonableness from the request description, requested content, and resource usage scenario. Use conservative defaults.

Approve only when most of the following are clearly satisfied:

- **Business purpose is explicit**: the requester explains what the resource is for.
- **Requested resources fit the scenario**: size, environment, and options are proportional to the stated use.
- **Configuration is internally consistent**: parameters do not conflict and are technically plausible.
- **Scope is least-necessary**: avoid excessive CPU, memory, storage, network exposure, or premium tiers without justification.
- **Environment choice is appropriate**: production requests need stronger rationale than development or testing requests.
- **Cost is acceptable for the described need**: if cost estimate exists, it should be proportionate to the scenario.
- **Requester notes are actionable**: the description is concrete enough to support approval.

Reject when any of the following is true:

- no meaningful business justification is provided
- requested resources are obviously oversized for the stated need
- production-grade resources are requested for vague or low-risk scenarios
- the request appears incomplete, contradictory, or copy-pasted without usable context
- the request asks for unusual or expensive resources without explanation
- the risk is material and the available data is insufficient

## Decision Style

Be strict, concise, and auditable.

- Do not invent facts missing from the request.
- Do not ask the requester follow-up questions in this backend workflow.
- Prefer rejection with concrete guidance over speculative approval.
- When rejecting, explain what would make the request approvable.
- Keep the final approval or rejection comment professional and specific.

## Comment Templates

Use short, direct comments. Adapt them to the actual request.

Approval comment pattern:

`Approved by agent pre-review. Business purpose is clear, requested resources match the described scenario, and no obvious overprovisioning or inconsistency was detected.`

Rejection comment pattern:

`Rejected by agent pre-review. The request does not provide sufficient justification for the requested resources or environment. Please clarify the business purpose, expected workload, target environment, and why the selected capacity is necessary.`

## Output Contract

Return a structured summary like:

```json
{
  "decision": "approve",
  "confidence": "high",
  "reasoning": [
    "Business purpose is explicit.",
    "Requested capacity is proportional to the described workload."
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

- If detail retrieval fails, return a failure result and do not approve.
- If approval execution fails, return the provider error as-is.
- If rejection execution fails, return the provider error as-is.
- If the case is ambiguous, expensive, or high-risk, reject with guidance rather than auto-approving.

## Invocation Notes

This skill is intended for webhook-triggered backend mode where the target skill is already specified by the caller. It should not rely on interactive clarification or human confirmation.
