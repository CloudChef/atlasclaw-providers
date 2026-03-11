---
name: request-decomposition-agent
description: >
  Use when UniClaw receives a descriptive infrastructure or application demand
  instead of a ready-made CMP catalog request. This skill analyzes the request,
  decomposes it into CMP-executable sub-requests, and prepares draft or
  review-required request payloads through existing CMP Provider request and
  datasource skills. It does not approve requests and it does not access CMP
  APIs directly.
---

# CMP Descriptive Request Decomposition Agent

Use this skill when the input is a descriptive business or infrastructure need, not a clean service catalog request.

The goal is to turn vague or multi-resource demand into structured CMP request candidates that operations staff can review and adjust. This skill is an orchestration and planning skill, not an autonomous fulfillment skill.

## Inputs

Expect these inputs from the webhook payload or runtime context:

- `instance`: CMP provider instance name, for example `cmp-prod`
- `agent_identity`: Must be `agent-request-orchestrator`
- `request_text`: Free-form requirement description from user, ticket, or workflow
- `request_title`: Optional short title
- `requester_context`: Optional metadata such as application, business group, environment, urgency, owner, or budget hints
- `submission_mode`: Optional mode, default `draft`

If `request_text` is empty, stop and return a validation failure.

If `agent_identity` is not `agent-request-orchestrator`, stop. This skill must run only under the dedicated CMP request orchestration agent account.

## Provider Skills This Skill May Call

This skill must not access CMP directly. It should orchestrate existing provider skills only.

- `datasource/list_services.py` — List available service catalogs
- `datasource/list_components.py` — Get component type information (nodeType, osType)
- `datasource/list_business_groups.py` — List business groups for a catalog
- `datasource/list_resource_pools.py` — List available resource pools
- `request/submit.py` — Submit the assembled request

## Workflow

1. Parse the descriptive demand into candidate resource intents.
2. Extract explicit and implied constraints:
   - environment
   - workload type
   - expected scale
   - availability or compliance hints
   - likely dependencies between resources
3. Split the demand into CMP-executable sub-requests.
4. Match each sub-request to the most suitable CMP service catalog entry via datasource skills.
5. Fetch the target schema for each matched service.
6. Build structured request payloads with:
   - resolved parameters
   - assumptions made by the agent
   - fields that still require manual adjustment
7. Execute one of the following based on `submission_mode`:
   - `draft`: prepare request candidates and stop
   - `review_required`: create requests intended for human adjustment if the provider supports this safely
8. Return a decomposition plan and the generated sub-request payloads.

Never auto-approve or auto-fulfill the decomposed requests.

## Decomposition Rules

Prefer smaller, reviewable sub-requests over a single oversized request.

Examples of valid decomposition:

- application runtime compute
- database service
- storage capacity
- load balancer or ingress
- network connectivity dependencies
- monitoring or baseline operational components if CMP models them as services

Do not invent components that are unsupported by the CMP catalog. If no suitable service is found, mark that part as unresolved for manual handling.

## Decision Style

Be explicit about assumptions and uncertainty.

- Separate extracted facts from inferred assumptions.
- Prefer leaving fields unresolved rather than fabricating values.
- If the requirement is too vague, return a partial plan with clarification gaps for operations staff.
- Optimize for operator editability, not for full automation.

## Output Contract

Return a structured summary like:

```json
{
  "decision": "decomposed_for_review",
  "summary": "Split the request into three CMP sub-requests.",
  "sub_requests": [
    {
      "service_name": "Linux VM",
      "status": "draft",
      "resolved_fields": ["cpu", "memory", "environment"],
      "unresolved_fields": ["business_group_id"],
      "assumptions": ["Production deployment inferred from description."]
    }
  ],
  "manual_followups": [
    "Confirm target business group.",
    "Review whether database HA is required."
  ]
}
```

## Failure Handling

- If catalog matching fails for all sub-requests, return a structured failure with unresolved intents.
- If schema retrieval fails for one sub-request, keep other sub-requests if they remain valid.
- If request creation is unsupported or unsafe in the current mode, return draft payloads only.
- Never submit final executable requests when key fields are guessed.

## Invocation Notes

This skill is intended for backend orchestration or assisted intake workflows. It should terminate in a reviewable plan or draft requests for human operations staff to adjust.
