---
name: request-decomposition-agent
description: "Request orchestration agent. Transform natural language infrastructure or application needs into structured, reviewable service request drafts."
provider_type: "smartcmp"
instance_required: "true"

# === LLM Context Fields ===
triggers:
  - infrastructure request
  - natural language request
  - decompose requirements
  - agent orchestrator
  - service request drafting

use_when:
  - User describes infrastructure or application needs in natural language
  - Requirements need to be decomposed into multiple service requests
  - User wants reviewable draft requests rather than direct submission
  - agent_identity is agent-request-orchestrator

avoid_when:
  - User has specific parameters ready for a single request (use request skill)
  - User only wants to browse resources (use datasource skill)
  - User wants to approve/reject requests (use approval skill)

examples:
  - "I need a web application environment with 3 VMs and a load balancer"
  - "Set up a development environment for our new project"
  - "Provision infrastructure for a microservices deployment"

related:
  - request
  - datasource
---

# Request Decomposition Agent

Orchestration agent for transforming descriptive demands into request candidates.

## Purpose

When receiving free-form infrastructure or application requirements:
1. Parse and decompose into executable sub-requests
2. Match each sub-request to available catalog services
3. Build structured request payloads with resolved/unresolved fields
4. Return draft requests for human review

Default behavior is draft-first. In webhook robot admin execution mode, this agent may submit the decomposed child requests only when the webhook selects an authorized robot profile and the input explicitly allows submission.

## Trigger Conditions

This skill activates when:
- Input is descriptive text (not a clean catalog request)
- `agent_identity` is `agent-request-orchestrator`
- `request_text` is provided

## Robot Admin Execution

For webhook-driven backend execution, run this agent against an explicitly selected SmartCMP provider instance with a robot/admin credential. Set `ATLASCLAW_PROVIDER_INSTANCE` to the intended instance name; if that instance is not configured, execution must fail closed rather than falling back to `prod` or another instance.

The AtlasClaw webhook user (`ATLASCLAW_USER_ID=webhook-*`) is the trigger identity, not the SmartCMP request actor. In robot execution, `../request/scripts/submit.py` resolves the SmartCMP actor from the selected robot credential, preferring `/users/current-user-details` over the synthetic webhook user id.

Use this mode only for robot profiles whose `allowed_skills` include `smartcmp:request-decomposition-agent`. The CMP side should then show the robot/admin account as the creator of the submitted child requests.

## Inputs

| Input | Type | Required | Description |
|-------|------|----------|-------------|
| `provider_instance` | string | Yes | CMP provider instance name (e.g., `cmp-prod`) |
| `robot_profile` | string | For webhook robot mode | Robot profile configured on the selected provider instance |
| `agent_identity` | string | Yes | Must be `agent-request-orchestrator` |
| `request_text` | string | Yes | Free-form requirement description |
| `request_title` | string | No | Short title for the request |
| `requester_context` | object | No | Metadata: application, BG, environment, urgency, budget |
| `submission_mode` | string | No | `draft` (default), `review_required`, or `submit` |

**Validation Rules:**
- If `request_text` is empty → **Stop immediately**
- If `agent_identity` ≠ `agent-request-orchestrator` → **Stop immediately**
- If `submission_mode=submit` but no robot profile is active → **Stop before submitting**

## Orchestrated Skills

This agent accesses SmartCMP only through the provider tools selected by AtlasClaw runtime:

| Skill | Purpose |
|-------|---------|
| `../datasource/scripts/list_services.py` | List available service catalogs |
| `../request/scripts/submit.py` | Submit assembled request (if mode allows) |

## Workflow

```
1. Parse Descriptive Demand
   └── Extract resource intents from request_text
         ↓
2. Extract Constraints
   ├── Environment (prod/dev/test)
   ├── Workload type
   ├── Expected scale
   ├── Availability/compliance hints
   └── Dependencies between resources
         ↓
3. Split into Sub-Requests
   └── One per CMP-executable unit
         ↓
4. Match to CMP Catalog
   └── ../datasource/scripts/list_services.py → Find suitable entries
         ↓
5. Fetch Target Schema
   └── Use catalog metadata to determine required fields
         ↓
6. Build Request Payloads
   ├── Resolved parameters
   ├── Assumptions made
   └── Fields requiring manual adjustment
         ↓
7. Execute Based on Mode
   ├── draft → Return candidates, stop
   ├── review_required → Create for human adjustment
   └── submit → Submit child requests using the selected robot/admin credential
         ↓
8. Return Decomposition Plan
```

## Decomposition Rules

**Prefer smaller, reviewable sub-requests over single oversized request.**

### Valid Decomposition Examples

| Component Type | Description |
|----------------|-------------|
| Compute | Application runtime VMs |
| Database | Database service instances |
| Storage | Storage capacity allocations |
| Load Balancer | Ingress/traffic distribution |
| Network | Connectivity dependencies |
| Monitoring | Operational components |

### Handling Unsupported Components

- If no suitable CMP catalog service → Mark as **unresolved** for manual handling
- Do NOT invent components unsupported by catalog

## Decision Style

> Be explicit about assumptions and uncertainty.

- Separate extracted facts from inferred assumptions
- Prefer leaving fields unresolved over fabricating values
- If requirement too vague → Return partial plan with clarification gaps
- Optimize for operator editability, not full automation

## Output Contract

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

| Scenario | Action |
|----------|--------|
| Catalog matching fails for all | Return structured failure with unresolved intents |
| Schema retrieval fails for one | Keep other valid sub-requests |
| Mode unsafe for execution | Return draft payloads only |
| Key fields guessed | Do NOT submit final requests |

## Example Decomposition

**Input:**
```
We need a web application environment with 2 frontend servers (4 CPU, 8GB RAM each),
a MySQL database with 100GB storage, and a load balancer for traffic distribution.
Production environment, high availability preferred.
```

**Output:**
```json
{
  "sub_requests": [
    {
      "service_name": "Linux VM",
      "quantity": 2,
      "resolved_fields": {"cpu": 4, "memory": 8192, "environment": "production"},
      "assumptions": ["Frontend servers use Linux OS"]
    },
    {
      "service_name": "MySQL Database",
      "resolved_fields": {"storage": 100, "environment": "production"},
      "unresolved_fields": ["ha_mode"],
      "assumptions": ["HA required based on 'high availability preferred'"]
    },
    {
      "service_name": "Load Balancer",
      "status": "unresolved",
      "reason": "No matching catalog service found"
    }
  ],
  "manual_followups": [
    "Confirm HA configuration for MySQL",
    "Manual setup required for load balancer"
  ]
}
```

## References

- [decomposition-guidelines.md](references/decomposition-guidelines.md) — Detailed decomposition rules
