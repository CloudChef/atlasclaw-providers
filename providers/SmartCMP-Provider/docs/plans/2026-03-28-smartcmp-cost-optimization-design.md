# SmartCMP Cost Optimization Capability Design

## Background

The SmartCMP provider already supports resource requests, approvals, and
reference-data queries, but it does not yet support SmartCMP-native cost
optimization workflows. The SmartCMP platform exposes a cost optimization and
remediation surface through compliance policy APIs, including:

- optimization recommendation listing
- recommendation detail lookup
- saving overview and trend summaries
- SmartCMP-native remediation execution through violation day2 fix
- remediation execution tracking

The user requirement is to extend the existing SmartCMP provider so AtlasClaw
can query optimization recommendations, analyze them with cloud best-practice
context, recommend next steps, and execute SmartCMP-native fixes.

## User Requirements

- Add a SmartCMP provider skill for cost optimization.
- Support recommendation query from SmartCMP.
- Support recommendation analysis that separates platform facts from inference.
- Include public cloud best-practice guidance for AWS and Azure where relevant.
- Execute fixes only through SmartCMP-native remediation.
- Use `POST /compliance-policies/violations/day2/fix/{id}` as the only first
  version execution path.
- Avoid authentication misrouting between SmartCMP SaaS and private deployment.

## Existing SmartCMP API Surface

The local SmartCMP OpenAPI dump shows the relevant compliance policy APIs:

- `GET /compliance-policies/violations/search`
  Search policy violations with category, status, and severity filters.
- `GET /compliance-policies/violations/{id}`
  Retrieve a single violation record.
- `POST /compliance-policies/violations/day2/fix/{id}`
  Trigger a SmartCMP-native day2 remediation for one violation.
- `GET /compliance-policies/violation-instances/search`
  Query violation remediation task instances by violation ID and status.
- `GET /compliance-policies/resource-executions/search`
  Query resource execution results by execution ID and status.
- `GET /compliance-policies/search`
  Query compliance policies for enrichment.
- `GET /compliance-policies/{id}`
  Retrieve a single compliance policy.
- `GET /compliance-policies/overview/saving-summary`
  Get aggregate saving amount statistics.
- `GET /compliance-policies/overview/saving-trend`
  Get historical saving trend.
- `GET /compliance-policies/overview/saving-operation-type-summary`
  Get distribution of optimization operation types.
- `GET /compliance-policies/overview/saving-resource-top`
  Get top saving resources.
- `GET /compliance-policies/policy-executions/search`
  Query policy execution history for compliance-rate enrichment.

The important schemas are:

- `PolicyViolation`
- `PolicyViolationInstance`
- `PolicyResourceExecution`
- `CompliancePolicy`
- `TaskDefinition`

## Authentication Correction

The current SmartCMP provider infers SaaS login from a broad domain suffix
match. That is unsafe because some private deployments may use domains that
contain `smartcmp.cloud` while still authenticating against their own private
`/platform-api/login` endpoint.

The new rule must be:

- Only `console.smartcmp.cloud` is a SmartCMP SaaS business endpoint.
- Only `account.smartcmp.cloud` is a SmartCMP SaaS authentication endpoint.
- All other hosts, including hosts that merely contain `smartcmp.cloud`, must
  be treated as private deployment by default.

The provider auth behavior should become:

1. Use explicit `auth_url` from provider config when present.
2. Else, if host is exactly `console.smartcmp.cloud`, use
   `https://account.smartcmp.cloud/bss-api/api/authentication`.
3. Else, default to private deployment auth:
   `{scheme}://{host}/platform-api/login`.

Backward compatibility:

- Keep supporting legacy `CMP_AUTH_URL` environment variable.
- Add provider-level `auth_url` documentation and config example.
- Keep auto-login and cookie cache behavior unchanged apart from URL selection.

This change is part of the cost optimization effort because live verification
depends on reaching the correct login endpoint.

## Goals

- Add first-class SmartCMP-native cost optimization capability.
- Preserve the provider's current script-oriented architecture.
- Keep execution limited to SmartCMP-native day2 fix.
- Separate platform facts from inferred recommendations.
- Provide practical AWS and Azure best-practice explanations without claiming
  those explanations are SmartCMP-native facts.
- Fix SmartCMP auth endpoint inference to reduce operational risk.

## Non-Goals

- Direct calls to AWS or Azure APIs.
- Arbitrary resource reconfiguration outside SmartCMP remediation.
- Custom remediation workflow generation.
- Broad FinOps dashboards beyond SmartCMP APIs.
- Automatic execution of recommendations without an explicit execute step.

## Chosen Solution

Add a new `cost-optimization` skill under `SmartCMP-Provider` and keep
recommendation listing, analysis, execution, and execution tracking as separate
scripts behind one user-facing skill. Update shared SmartCMP auth logic so only
the two canonical SaaS subdomains are treated as SaaS.

This matches the current provider style:

- shared auth and common HTTP behavior stay in `skills/shared/scripts/_common.py`
- cost optimization logic stays inside a dedicated skill directory
- risky write operations remain explicit and separately invokable

## Skill Structure

Add:

- `providers/SmartCMP-Provider/skills/cost-optimization/SKILL.md`
- `providers/SmartCMP-Provider/skills/cost-optimization/references/WORKFLOW.md`
- `providers/SmartCMP-Provider/skills/cost-optimization/scripts/_cost_common.py`
- `providers/SmartCMP-Provider/skills/cost-optimization/scripts/_analysis.py`
- `providers/SmartCMP-Provider/skills/cost-optimization/scripts/list_recommendations.py`
- `providers/SmartCMP-Provider/skills/cost-optimization/scripts/analyze_recommendation.py`
- `providers/SmartCMP-Provider/skills/cost-optimization/scripts/execute_optimization.py`
- `providers/SmartCMP-Provider/skills/cost-optimization/scripts/track_execution.py`

The skill should advertise four user-facing capabilities:

- list optimization recommendations
- analyze one recommendation
- execute SmartCMP-native optimization fix
- track remediation execution state

## Script Responsibilities

### `_cost_common.py`

Own SmartCMP cost optimization helper logic:

- request helpers that reuse `skills/shared/scripts/_common.py`
- pageable and query request defaults
- response extraction helpers
- money normalization
- timestamp normalization
- violation status helpers
- execution response helpers

### `_analysis.py`

Own deterministic analysis helpers:

- fact normalization from violation and policy payloads
- mapping `savingOperationType` to optimization themes
- readiness heuristics for execution
- recommendation assembly
- best-practice explanation helpers for AWS and Azure aligned patterns

### `list_recommendations.py`

Purpose:

- query optimization recommendations from violations search
- expose high-signal filters
- print concise human-readable summaries
- emit machine-readable metadata

### `analyze_recommendation.py`

Purpose:

- fetch violation detail and policy detail
- enrich with saving overview and policy-execution context when available
- generate structured assessment and next-step recommendations

### `execute_optimization.py`

Purpose:

- accept one violation ID at a time in first version
- call `POST /compliance-policies/violations/day2/fix/{id}`
- clearly distinguish submitted execution from completed remediation

### `track_execution.py`

Purpose:

- query violation fix instances
- query resource execution results
- summarize final or in-progress remediation state

## Output Contracts

### Recommendation Listing

`list_recommendations.py` should emit:

- a short numbered summary
- `##COST_RECOMMENDATION_META_START## ... ##COST_RECOMMENDATION_META_END##`

Each meta item should include at least:

```json
{
  "violationId": "...",
  "policyId": "...",
  "policyName": "...",
  "resourceId": "...",
  "resourceName": "...",
  "status": "...",
  "severity": "...",
  "category": "...",
  "monthlyCost": 123.45,
  "monthlySaving": 67.89,
  "savingOperationType": "...",
  "fixType": "...",
  "taskInstanceId": "...",
  "lastExecuteDate": "2026-03-28T12:00:00Z"
}
```

### Recommendation Analysis

`analyze_recommendation.py` should emit:

- a short human-readable summary
- `##COST_ANALYSIS_START## ... ##COST_ANALYSIS_END##`

The structured result should follow this shape:

```json
{
  "violationId": "...",
  "facts": {
    "policyName": "...",
    "resourceName": "...",
    "status": "...",
    "monthlyCost": 123.45,
    "monthlySaving": 67.89,
    "savingOperationType": "RIGHTSIZE",
    "remedie": "...",
    "fixType": "...",
    "taskDefinitionPresent": true
  },
  "assessment": {
    "optimizationTheme": "rightsizing",
    "cloudBestPractice": "Reduce over-provisioned compute for low-utilization workloads",
    "expectedBenefit": "medium",
    "executionReadiness": "ready"
  },
  "recommendations": [
    {
      "action": "execute_fix",
      "confidence": "high",
      "reason": "...",
      "evidence": ["monthlySaving > 0", "fixType present", "policy has remedie"],
      "bestPractice": "AWS/Azure rightsizing guidance aligns with this recommendation",
      "platformExecutable": true
    }
  ],
  "suggestedNextStep": "execute_fix"
}
```

Rules:

- `facts` contain only SmartCMP platform facts
- `assessment` and `recommendations` may contain inference
- best-practice explanation must not be presented as confirmed platform fact

### Execution Submission

`execute_optimization.py` should emit:

- a short human-readable submission result
- `##COST_EXECUTION_START## ... ##COST_EXECUTION_END##`

The structured result should include:

```json
{
  "violationId": "...",
  "requested": true,
  "executionSubmitted": true,
  "executionMode": "smartcmp_day2_fix",
  "message": "...",
  "followUpRequired": true
}
```

### Execution Tracking

`track_execution.py` should emit:

- a short human-readable status summary
- `##COST_EXECUTION_TRACK_START## ... ##COST_EXECUTION_TRACK_END##`

The structured result should include:

- violation ID
- latest violation-instance records
- resource execution records when available
- normalized overall status such as `SUCCESS`, `FAILED`, `EXECUTING`, or
  `PARTIAL`
- failure reason summary when available

## Analysis Rules

The analysis rules should be deterministic before any free-form reasoning:

- If `monthlySaving <= 0`, do not recommend execution by default.
- If violation already represents a completed or fixed state, recommend observe
  or review rather than execute.
- Mark `platformExecutable=true` only when remediation indicators are present,
  such as `fixType`, `taskDefinition`, or `remedie`, and execution is not
  already complete.
- Map `savingOperationType` into normalized themes such as:
  - `rightsizing`
  - `idle_shutdown`
  - `orphan_cleanup`
  - `storage_optimization`
- Only allow `execute_fix` as a recommendation when `platformExecutable=true`.
- Otherwise recommend `manual_review` or `observe`.

## AWS and Azure Best-Practice Layer

The first version can enrich recommendations with cloud best-practice context
using the normalized optimization theme:

- `rightsizing`
  - AWS EC2 rightsizing
  - Azure VM rightsizing
- `idle_shutdown`
  - AWS stop or schedule idle instances
  - Azure stop or deallocate low-usage virtual machines
- `orphan_cleanup`
  - AWS unattached EBS or idle Elastic IP cleanup
  - Azure unattached managed disk or idle public IP cleanup
- `storage_optimization`
  - AWS storage tiering and right-sizing
  - Azure storage access tier optimization

These enrichments are explanatory only. They must not cause direct public cloud
API actions in this provider.

## Workflow

The default operator flow should be:

1. `list_recommendations.py`
2. `analyze_recommendation.py`
3. `execute_optimization.py`
4. `track_execution.py`

This keeps risky execution gated behind a separate explicit step.

## Testing Strategy

The implementation should be verified at three layers:

### Unit Tests

- auth host classification and auth URL inference
- response extraction and normalization helpers
- recommendation object generation
- execution payload and status parsing

### Fixture Integration Tests

- violation search payload formatting
- violation detail and policy enrichment
- execution submission result formatting
- execution tracking result normalization

### Live Smoke Validation

- authenticate against a real SmartCMP environment using valid credentials or
  cookie
- query recommendations
- analyze one recommendation
- submit one day2 fix for a clearly executable violation
- track the submitted execution

## Risks and Mitigations

### Authentication Risk

Risk:
Wrongly routing private deployment auth to SaaS auth endpoints.

Mitigation:
Use exact host matching for SaaS and explicit `auth_url` override support.

### Overclaiming Analysis

Risk:
Presenting inferred AWS or Azure best practices as SmartCMP facts.

Mitigation:
Keep facts and inference in separate output sections.

### Execution Ambiguity

Risk:
Treating submission as completion.

Mitigation:
Require explicit tracking step and structured follow-up status.

### Live Validation Availability

Risk:
Some provided environments may require browser cookie auth or may reject
 password-based login.

Mitigation:
Support cookie-based auth and preserve manual-cookie execution path.

## Decision Summary

Build a dedicated `cost-optimization` skill, keep execution strictly limited to
`POST /compliance-policies/violations/day2/fix/{id}`, and fix SmartCMP auth
host classification so only `console.smartcmp.cloud` and
`account.smartcmp.cloud` are treated as SaaS.
