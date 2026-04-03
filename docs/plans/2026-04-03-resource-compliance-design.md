# SmartCMP Resource Compliance Design

**Date:** 2026-04-03

## Goal

Add a new SmartCMP capability that accepts one or more CMP resource IDs, fetches resource details from SmartCMP, analyzes compliance and security posture, and returns a human-readable plus machine-readable result. The same capability must support both direct user invocation and webhook-driven invocation.

## Approved Scope

- Add a datasource capability to fetch resource details by resource ID.
- Add one new `resource-compliance` skill as the analysis entrypoint.
- Support both user-triggered and webhook-triggered inputs in the same skill.
- Use live internet validation during analysis when the resource facts identify a product/version that can be checked against authoritative external sources.
- Do not build or maintain a local lifecycle or vulnerability rule database in this first version.
- Do not implement automatic remediation in this first version.
- Do not finalize the webhook callback/return contract in this first version; stabilize the internal structured output first.

## Existing Provider Context

The current `SmartCMP-Provider` already has:

- Shared data-access helpers in `skills/shared/scripts/_common.py`
- Read-oriented skills such as `datasource`
- Analysis-oriented skills such as `alarm` and `cost-optimization`
- Agent-style webhook-oriented skills such as `preapproval-agent` and `request-decomposition-agent`

This new work should reuse the same patterns:

- shared script for provider API access
- analysis skill with structured JSON payload blocks
- separate data retrieval and analysis responsibilities

## API Basis

The SmartCMP API documentation at `https://192.168.86.164:8443/doc.html#/All/Cloud%20Resource%20Management/searchResources` and `/v3/api-docs` confirms the following endpoints:

- `POST /nodes/search`
  - supports `ResourceSearchRequest.ids`
  - returns paged `SimpleResource` data
- `GET /nodes/{id}`
  - returns full `Resource`
- `GET /nodes/{id}/details`
  - returns additional detail as string key/value pairs

This is sufficient for a first version of resource-detail retrieval without introducing a new provider integration path.

## Architecture

### 1. Shared resource retrieval

Add a new shared script:

- `providers/SmartCMP-Provider/skills/shared/scripts/list_resource.py`

Responsibilities:

- Accept one or more resource IDs
- Call `POST /nodes/search` with `ids`
- For each matched resource, enrich with:
  - `GET /nodes/{id}`
  - `GET /nodes/{id}/details`
- Normalize the merged payload into a stable structure that downstream skills can consume
- Emit both readable summary text and a machine-readable metadata block

This script belongs in `skills/shared/scripts` instead of under `datasource/scripts` because it is a cross-skill primitive. `datasource/SKILL.md` should advertise this new capability.

### 2. Single analysis skill

Add a new analysis skill:

- `providers/SmartCMP-Provider/skills/resource-compliance/SKILL.md`
- `providers/SmartCMP-Provider/skills/resource-compliance/scripts/analyze_resource.py`
- `providers/SmartCMP-Provider/skills/resource-compliance/scripts/_analysis.py`
- `providers/SmartCMP-Provider/skills/resource-compliance/references/WORKFLOW.md`

The first version will use one skill for both direct-user and webhook-driven use. It should accept resource IDs from either source, normalize them to the same internal request shape, and run one analysis path.

### 3. Separation of concerns

- `list_resource.py`
  - provider API retrieval
  - response normalization
  - partial-failure handling for resource fetch
- `analyze_resource.py`
  - input parsing
  - call `list_resource.py` logic
  - aggregate multi-resource results
  - render final text plus structured JSON
- `_analysis.py`
  - extract analysis facts
  - identify technology/product/version candidates
  - perform external validation lookups
  - build findings, uncertainties, and recommendations

## Input Model

The skill must support two input modes:

### Direct user mode

Input includes one or more `resource_id` values provided by the user.

### Webhook mode

Input includes one or more resource IDs and optional trigger metadata such as:

- `trigger_source`
- `request_id`
- `event_id`
- `payload_id`

### Internal normalized shape

Both modes are normalized to:

```json
{
  "resourceIds": ["id-1", "id-2"],
  "triggerContext": {
    "triggerSource": "user|webhook",
    "rawMetadata": {}
  }
}
```

## Data Flow

1. Validate input contains at least one resource ID.
2. Call `list_resource.py` to fetch base resource data from `/nodes/search`.
3. For each resolved resource, enrich with `/nodes/{id}` and `/nodes/{id}/details`.
4. Normalize raw resource data into analysis facts.
5. Detect analyzable technologies and versions, including at least:
   - MySQL
   - Windows
   - Linux distribution/version
6. Perform live internet validation against authoritative external sources when enough product/version evidence is available.
7. Produce per-resource findings and a batch-level summary.
8. Emit:
   - readable narrative output
   - structured JSON payload for downstream consumption

## Analysis Strategy

### Fact-first analysis

The model must separate:

- `observations`: facts directly visible in CMP resource data
- `assessment`: model judgment based on those facts and external validation
- `uncertainties`: what could not be confirmed from available data

This prevents the analysis from presenting model inference as provider fact.

### Initial target checks

The first version should focus on:

- MySQL lifecycle/support risk
- Windows version and patch/compliance risk
- Linux distribution/version support and security risk

### Live internet validation

The first version may use live internet checks during analysis. Source selection should prefer authoritative and primary sources:

- MySQL: Oracle/MySQL official lifecycle and release pages
- Windows: Microsoft lifecycle and update documentation
- Linux: official distribution lifecycle/security pages
- Vulnerability/security references: NVD and vendor security advisories

The analysis should only escalate to strong conclusions when:

- the resource facts clearly identify product and version
- external validation confirms lifecycle or security status

If the product is identified but the version is missing or ambiguous, the result should prefer `needs_review` over a hard conclusion.

## Output Model

Each resource should produce a structured result similar to:

```json
{
  "resourceId": "xxx",
  "resourceName": "mysql-prod-01",
  "resourceType": "cloudchef.nodes.Compute",
  "analysisStatus": "analyzed",
  "observations": [],
  "findings": [],
  "summary": {
    "overallRisk": "high",
    "overallCompliance": "non_compliant",
    "confidence": "medium"
  },
  "recommendations": [],
  "uncertainties": []
}
```

Each finding should include:

- `category`
- `severity`
- `status`
- `title`
- `evidence`
- `reasoning`
- `recommendation`
- `confidence`
- `externalEvidence`
- `sourceLinks`
- `checkedAt`
- `inferenceNote`

The batch output should also include:

- `triggerSource`
- `requestedResourceIds`
- `analyzedCount`
- `failedCount`
- `generatedAt`

## Failure and Degradation Rules

The design favors partial success over all-or-nothing failure.

### Input failure

- No resource IDs: fail fast with structured error

### Resource retrieval failure

- Unknown resource ID: mark that resource as `not_found`
- Base search succeeds but detail lookup fails: keep the resource and record missing detail in `uncertainties`
- One resource fails in a batch: continue processing the rest

### External validation failure

- Internet unavailable
- authority site unreachable
- page format changes
- source does not expose the needed version mapping

In these cases:

- do not fail the whole skill
- degrade to fact-only assessment when possible
- mark the result with an external-validation warning such as `external_validation_unavailable`
- lower confidence or return `needs_review`

## Testing Strategy

### Resource retrieval tests

Add tests for:

- single and multiple resource IDs
- `/nodes/search` paged response extraction
- merge behavior across `search`, `GET /nodes/{id}`, and `GET /nodes/{id}/details`
- partial failure for one resource in a multi-resource batch

### Analysis tests

Add tests for:

- MySQL version recognized with lifecycle risk output
- Windows version recognized with patch/compliance risk output
- Linux distribution/version recognized with support/security risk output
- insufficient version evidence resulting in `needs_review`
- batch output with mixed success/failure states
- external validation unavailable causing graceful degradation

### Test isolation

Unit tests should not depend on live internet or a live CMP environment. External validation and CMP responses should be mockable so tests stay deterministic.

## Documentation Updates

Update the following docs:

- `providers/SmartCMP-Provider/skills/datasource/SKILL.md`
  - advertise resource-detail retrieval by resource ID
- `providers/SmartCMP-Provider/PROVIDER.md`
  - add `resource-compliance` to provider capabilities and provided skills
- `providers/SmartCMP-Provider/README.md`
  - document the new skill and its intended use

## Deferred Items

The following are intentionally deferred:

- dedicated webhook wrapper skill or agent
- automatic remediation or repair execution
- local lifecycle/security rule database
- stable upstream webhook callback contract
- broad technology coverage beyond the initial MySQL/Windows/Linux focus

## Recommended Implementation Direction

Implement the first version as:

1. shared `list_resource.py` data retrieval primitive
2. `datasource` skill docs update to expose it
3. `resource-compliance` skill for both user and webhook invocation
4. structured output with readable text plus machine-readable JSON
5. external validation that prefers authoritative sources and degrades safely
