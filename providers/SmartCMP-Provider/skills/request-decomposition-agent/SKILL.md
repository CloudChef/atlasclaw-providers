---
name: request-decomposition-agent
description: "Request decomposition agent. Split broad natural-language infrastructure or application needs into structured, reviewable multi-service request drafts."
provider_type: "smartcmp"
instance_required: "true"

# === LLM Context Fields ===
triggers:
  - infrastructure request
  - natural language request
  - decompose requirements
  - agent orchestrator
  - service request drafting
  - mixed resource request
  - per-instance configuration differences
  - ordinal instance differences

use_when:
  - User describes infrastructure or application needs in natural language
  - Requirements need to be decomposed into multiple service requests
  - User wants reviewable draft requests rather than direct submission
  - agent_identity is agent-request-orchestrator
  - User asks for multiple resource types that should become separate CMP requests
  - User asks for multiple resources with distinct per-item configuration
  - User enumerates differences across instances or components using ordinal references such as first / second / third

avoid_when:
  - User has specific parameters ready for a single request (use request skill)
  - User wants multiple instances of the same resource type with the same parameters in one request flow (use request skill)
  - User only wants to browse resources (use datasource skill)
  - User wants to approve/reject requests (use approval skill)

examples:
  - "I need an application environment with compute, data, and traffic components"
  - "Set up a development environment for our new project"
  - "Provision infrastructure for a microservices deployment"
  - "Create several instances where the first needs a small profile and the second needs a larger profile"

related:
  - request
  - datasource
---

# Request Decomposition Agent

Orchestration agent for transforming descriptive demands into request candidates.

## Purpose

When receiving free-form infrastructure or application requirements:
1. Parse and decompose them into executable sub-requests
2. Match each sub-request to available catalog services
3. Build structured request payloads with resolved and unresolved fields
4. Return draft requests for human review

Default behavior is draft-first. In webhook robot admin execution mode, this
agent may submit the decomposed child requests only when the webhook selects an
authorized robot profile and the input explicitly allows submission.

## Trigger Conditions

This skill activates when:
- Input is descriptive text instead of a clean catalog request
- `agent_identity` is `agent-request-orchestrator`
- `request_text` is provided

For ordinary chat/runtime routing, this skill should be preferred whenever the
user asks for different resource types in one request, or when the user asks
for multiple resources with distinct per-item configuration. Do **not** route
here just because the user asks for quantity N of the same resource type with
the same parameters.

## Robot Admin Execution

For webhook-driven backend execution, run this agent against an explicitly
selected SmartCMP provider instance with a robot/admin credential. Set
`ATLASCLAW_PROVIDER_INSTANCE` to the intended instance name; if that instance
is not configured, execution must fail closed rather than falling back to
`prod` or another instance.

The robot provider instance should use a SmartCMP `cmp_tk_*` provider token
when available. The shared scripts send those tokens as
`Authorization: Bearer <token>` and keep non-`cmp_tk_*` session tokens on the
existing `CloudChef-Authenticate` header.

The AtlasClaw webhook user (`ATLASCLAW_USER_ID=webhook-*`) is the trigger
identity, not the SmartCMP request actor. In webhook robot dispatches without
forwarded SmartCMP user cookies, `../request/scripts/submit.py` resolves the
SmartCMP actor from the selected robot credential instead of the synthetic
webhook user id.

Use this mode only for robot profiles whose `allowed_skills` include
`smartcmp:request-decomposition-agent`. The same SmartCMP robot profile may
also allow `smartcmp:preapproval-agent` when the same robot/admin account is
approved for both workflows. In webhook robot dispatches without forwarded
SmartCMP user cookies, the CMP side should show the robot/admin account as the
creator of the submitted child requests.

## Inputs

| Input | Type | Required | Description |
|-------|------|----------|-------------|
| `provider_instance` | string | Yes | CMP provider instance name (e.g., `cmp-prod`) |
| `robot_profile` | string | For webhook robot mode | Robot profile configured on the selected provider instance |
| `agent_identity` | string | Yes | Must be `agent-request-orchestrator` |
| `request_text` | string | Yes | Free-form requirement description |
| `request_title` | string | No | Short title for the request |
| `requester_context` | object | No | Metadata such as application, BG, environment, urgency, or budget |
| `submission_mode` | string | No | `draft` (default), `review_required`, or `submit` |

**Validation Rules:**
- If `request_text` is empty -> **Stop immediately**
- If `agent_identity` != `agent-request-orchestrator` -> **Stop immediately**
- If `submission_mode=submit` but no robot profile is active -> **Stop before submitting**

## Orchestrated Skills

This agent accesses SmartCMP only through the provider tools selected by
AtlasClaw runtime:

| Skill | Purpose |
|-------|---------|
| `../datasource/scripts/list_services.py` | List available service catalogs |
| `../request/scripts/submit.py` | Submit assembled requests when the mode allows it |

## Workflow

```
1. Parse descriptive demand
   - Extract resource intents from request_text
2. Extract constraints
   - Environment (prod/dev/test)
   - Workload type
   - Expected scale
   - Availability/compliance hints
   - Dependencies between resources
3. Split into sub-requests
   - One per CMP-executable unit
4. Match to CMP catalog
   - Use ../datasource/scripts/list_services.py to find suitable entries
5. Fetch target schema
   - Use catalog metadata to determine required fields
6. Build request payloads
   - Resolved parameters
   - Assumptions made
   - Fields requiring manual adjustment
7. Execute based on mode
   - draft -> Return candidates, stop
   - review_required -> Create artifacts for human adjustment
   - submit -> Submit child requests using the selected robot/admin credential
8. Return decomposition plan
```

## Decomposition Rules

**Prefer smaller, reviewable sub-requests over one oversized request.**

### Valid Decomposition Patterns

| Component Type | Description |
|----------------|-------------|
| Compute | Application runtime components |
| Data | Database or data service components |
| Storage | Storage capacity allocations |
| Traffic | Ingress or distribution components |
| Network | Connectivity dependencies |
| Monitoring | Operational components |

### Distinct-configuration rule

When the user asks for multiple resources with distinct configurations, treat
each differently configured component as its own draft sub-request instead of
collapsing everything into one request body.

If the user wants multiple instances of the same resource type with the same
configuration under one service request, keep that request in the plain
`request` skill instead of decomposing it.

- Preserve the user-stated quantity.
- Preserve per-item differences such as CPU, memory, disk, OS, environment,
  and naming hints.
- If the user says "first", "second", or "third", keep those distinctions as
  separate sub-requests.
- If shared fields are mentioned once for all instances, copy them into each
  child draft as shared assumptions.
- If a field is missing for one instance, leave that field unresolved for that
  instance only.
- Treat ordinal references such as "first", "second", "third", "fifth", or
  "sixth" as evidence of per-item differences that must stay in decomposition
  mode rather than collapsing into one shared-parameter request.
- If the stated instance quantity conflicts with the referenced ordinal
  positions, stop and ask a focused clarification question before building
  sub-requests.
- Examples of conflicts that require clarification:
  - "request 4 instances, second ..., fifth ..., sixth ..."
  - "request 3 instances, first ... and fourth ..."
- For those conflicts, do not guess the missing instance count, do not renumber
  the user's intent silently, and do not submit anything.

### Handling Unsupported Components

- If no suitable CMP catalog service exists -> Mark that component as
  **unresolved** for manual handling
- Do not invent components unsupported by the catalog

## Decision Style

> Be explicit about assumptions and uncertainty.

- Separate extracted facts from inferred assumptions
- Prefer leaving fields unresolved over fabricating values
- If the requirement is too vague -> Return a partial plan with clarification gaps
- Optimize for operator editability, not full automation

## Output Contract

```json
{
  "decision": "decomposed_for_review",
  "summary": "Split the request into three CMP sub-requests.",
  "sub_requests": [
    {
      "service_name": "compute service",
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

| Scenario | Action |
|----------|--------|
| Catalog matching fails for all | Return structured failure with unresolved intents |
| Schema retrieval fails for one | Keep other valid sub-requests |
| Mode unsafe for execution | Return draft payloads only |
| Key fields guessed | Do not submit final requests |
| Instance quantity conflicts with ordinal references | Ask for clarification before decomposition |

## Example Decomposition

**Input:**
```
We need an application environment with 2 compute instances (4 CPU, 8 GB RAM each),
one data service with 100 GB storage, and one traffic component for ingress.
Production environment, high availability preferred.
```

**Output:**
```json
{
  "sub_requests": [
    {
      "service_name": "compute service",
      "quantity": 2,
      "resolved_fields": {"cpu": 4, "memory": 8192, "environment": "production"},
      "assumptions": ["Compute instances share the same operating profile"]
    },
    {
      "service_name": "data service",
      "resolved_fields": {"storage": 100, "environment": "production"},
      "unresolved_fields": ["ha_mode"],
      "assumptions": ["HA is likely required based on the request wording"]
    },
    {
      "service_name": "traffic component",
      "status": "unresolved",
      "reason": "No matching catalog service found"
    }
  ],
  "manual_followups": [
    "Confirm HA configuration for the data service",
    "Review whether the traffic component needs manual provisioning"
  ]
}
```

## References

- [decomposition-guidelines.md](references/decomposition-guidelines.md) - Detailed decomposition rules
