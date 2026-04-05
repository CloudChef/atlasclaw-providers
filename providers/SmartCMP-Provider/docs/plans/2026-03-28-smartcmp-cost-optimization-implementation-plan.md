# SmartCMP Cost Optimization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add SmartCMP-native cost optimization listing, analysis, execution, and execution tracking to the SmartCMP provider, and tighten SmartCMP SaaS auth host detection to avoid misrouting private deployments.

**Architecture:** Introduce a new `cost-optimization` skill under `SmartCMP-Provider`, reuse shared SmartCMP auth and request helpers, and split the capability into list, analyze, execute, and track scripts plus deterministic helper modules. Update shared auth inference so only `console.smartcmp.cloud` and `account.smartcmp.cloud` are treated as SaaS, with explicit `auth_url` override support.

**Tech Stack:** Python 3 scripts, requests, SmartCMP REST APIs, Markdown skill docs, pytest tests, existing SmartCMP E2E runner.

---

### Task 1: Fix SmartCMP auth inference and add coverage

**Files:**
- Modify: `atlasclaw-providers/providers/SmartCMP-Provider/skills/shared/scripts/_common.py`
- Modify: `atlasclaw-providers/providers/SmartCMP-Provider/PROVIDER.md`
- Modify: `atlasclaw-providers/providers/SmartCMP-Provider/README.md`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/test/test_smartcmp_auth_inference.py`

**Step 1: Write the failing test**

Add `test/test_smartcmp_auth_inference.py` to verify:
- `console.smartcmp.cloud` maps to `https://account.smartcmp.cloud/bss-api/api/authentication`
- `account.smartcmp.cloud` remains SaaS auth-aware
- `democmp.smartcmp.cloud:1443` maps to `{host}/platform-api/login`
- explicit `auth_url` overrides host inference

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_smartcmp_auth_inference.py -q`
Expected: FAIL because `_infer_auth_url` still uses broad suffix matching and provider docs do not mention `auth_url`.

**Step 3: Write minimal implementation**

Update `_common.py` so that:
- SaaS business hosts are matched exactly, not by suffix
- provider config may include `auth_url`
- legacy `CMP_AUTH_URL` still works
- private deployment remains `{scheme}://{host}/platform-api/login`

Update docs to explain:
- only `https://console.smartcmp.cloud/` is treated as SaaS business endpoint
- only `https://account.smartcmp.cloud/#/login` is treated as SaaS auth endpoint
- all other hosts default to private deployment auth unless `auth_url` is set explicitly

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_smartcmp_auth_inference.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git -C atlasclaw-providers add providers/SmartCMP-Provider/skills/shared/scripts/_common.py providers/SmartCMP-Provider/PROVIDER.md providers/SmartCMP-Provider/README.md providers/SmartCMP-Provider/test/test_smartcmp_auth_inference.py
git -C atlasclaw-providers commit -m "fix(SmartCMP): tighten SaaS auth host detection"
```

### Task 2: Scaffold the cost-optimization skill

**Files:**
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/skills/cost-optimization/SKILL.md`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/skills/cost-optimization/references/WORKFLOW.md`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/skills/cost-optimization/scripts/_cost_common.py`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/skills/cost-optimization/scripts/_analysis.py`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/skills/cost-optimization/scripts/list_recommendations.py`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/skills/cost-optimization/scripts/analyze_recommendation.py`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/skills/cost-optimization/scripts/execute_optimization.py`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/skills/cost-optimization/scripts/track_execution.py`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/test/test_cost_optimization_layout.py`

**Step 1: Write the failing test**

Add `test/test_cost_optimization_layout.py` to assert:
- the `cost-optimization` skill directory exists
- `SKILL.md` contains `name`, `description`, `provider_type`, and tool registrations
- the four user-facing scripts and two helper modules exist

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_cost_optimization_layout.py -q`
Expected: FAIL because the skill files do not exist yet.

**Step 3: Write minimal implementation**

Create the skill scaffold with:
- trigger phrases for optimization suggestions, savings, cost recommendations, and execute fix
- workflow reference that documents list → analyze → execute → track
- placeholder scripts that import cleanly

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_cost_optimization_layout.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git -C atlasclaw-providers add providers/SmartCMP-Provider/skills/cost-optimization providers/SmartCMP-Provider/test/test_cost_optimization_layout.py
git -C atlasclaw-providers commit -m "feat(SmartCMP): scaffold cost optimization skill"
```

### Task 3: Add common cost optimization helpers

**Files:**
- Modify: `atlasclaw-providers/providers/SmartCMP-Provider/skills/cost-optimization/scripts/_cost_common.py`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/test/test_cost_common.py`

**Step 1: Write the failing test**

Add `test/test_cost_common.py` to verify:
- violation lists are extracted from `content`, `data.content`, and raw arrays
- money values normalize to floats or `None`
- timestamps normalize to stable ISO-like strings
- search query defaults include pageable and query request structures

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_cost_common.py -q`
Expected: FAIL because helper functions are not implemented yet.

**Step 3: Write minimal implementation**

Implement `_cost_common.py` with:
- request helpers that reuse `skills/shared/scripts/_common.py`
- `build_pageable_request(page=0, size=20)`
- `build_query_request(query_value="")`
- violation response extraction helpers
- numeric and timestamp normalization helpers
- execution result extraction helpers

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_cost_common.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git -C atlasclaw-providers add providers/SmartCMP-Provider/skills/cost-optimization/scripts/_cost_common.py providers/SmartCMP-Provider/test/test_cost_common.py
git -C atlasclaw-providers commit -m "test(SmartCMP): add cost optimization helper coverage"
```

### Task 4: Implement recommendation listing

**Files:**
- Modify: `atlasclaw-providers/providers/SmartCMP-Provider/skills/cost-optimization/scripts/list_recommendations.py`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/test/test_list_recommendations.py`

**Step 1: Write the failing test**

Add `test/test_list_recommendations.py` with fixture payloads that assert:
- the script formats a numbered human-readable summary
- the script emits `##COST_RECOMMENDATION_META_START## ... ##COST_RECOMMENDATION_META_END##`
- each meta item includes `violationId`, `policyId`, `resourceName`, `status`, `monthlySaving`, and `savingOperationType`

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_list_recommendations.py -q`
Expected: FAIL because listing and meta serialization are incomplete.

**Step 3: Write minimal implementation**

Implement `list_recommendations.py` so it:
- queries `GET /compliance-policies/violations/search`
- supports `status`, `severity`, `category`, `query`, `page`, and `size`
- prints concise recommendation summaries
- emits normalized metadata in English keys

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_list_recommendations.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git -C atlasclaw-providers add providers/SmartCMP-Provider/skills/cost-optimization/scripts/list_recommendations.py providers/SmartCMP-Provider/test/test_list_recommendations.py
git -C atlasclaw-providers commit -m "feat(SmartCMP): add cost optimization listing"
```

### Task 5: Implement deterministic analysis helpers

**Files:**
- Modify: `atlasclaw-providers/providers/SmartCMP-Provider/skills/cost-optimization/scripts/_analysis.py`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/test/test_cost_analysis_helpers.py`

**Step 1: Write the failing test**

Add `test/test_cost_analysis_helpers.py` to assert:
- normalized facts combine violation and policy fields
- `savingOperationType` maps to stable optimization themes
- recommendation objects always include `action`, `confidence`, `reason`, `evidence`, and `platformExecutable`
- execution readiness becomes `ready`, `manual_review`, or `skip` using deterministic rules

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_cost_analysis_helpers.py -q`
Expected: FAIL because the analysis helper logic does not exist yet.

**Step 3: Write minimal implementation**

Implement `_analysis.py` with deterministic helpers for:
- fact normalization
- theme classification
- execution readiness rules
- recommendation assembly
- best-practice explanation snippets for AWS and Azure aligned themes

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_cost_analysis_helpers.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git -C atlasclaw-providers add providers/SmartCMP-Provider/skills/cost-optimization/scripts/_analysis.py providers/SmartCMP-Provider/test/test_cost_analysis_helpers.py
git -C atlasclaw-providers commit -m "feat(SmartCMP): add cost optimization analysis helpers"
```

### Task 6: Implement recommendation analysis output

**Files:**
- Modify: `atlasclaw-providers/providers/SmartCMP-Provider/skills/cost-optimization/scripts/analyze_recommendation.py`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/test/test_analyze_recommendation.py`

**Step 1: Write the failing test**

Add `test/test_analyze_recommendation.py` with fixture-driven expectations that:
- the script returns a human summary
- the script emits `##COST_ANALYSIS_START## ... ##COST_ANALYSIS_END##`
- the structured output includes `facts`, `assessment`, `recommendations`, and `suggestedNextStep`
- `facts` stay limited to platform fields while best-practice explanations remain in inference fields

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_analyze_recommendation.py -q`
Expected: FAIL because the analysis script does not yet assemble the full payload.

**Step 3: Write minimal implementation**

Implement `analyze_recommendation.py` so it:
- loads one violation by ID
- loads the related compliance policy
- optionally enriches with saving summary and operation-type summary
- uses `_analysis.py` to build deterministic facts and recommendations
- falls back gracefully when overview enrichment is unavailable

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_analyze_recommendation.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git -C atlasclaw-providers add providers/SmartCMP-Provider/skills/cost-optimization/scripts/analyze_recommendation.py providers/SmartCMP-Provider/test/test_analyze_recommendation.py
git -C atlasclaw-providers commit -m "feat(SmartCMP): add recommendation analysis"
```

### Task 7: Implement SmartCMP-native fix execution

**Files:**
- Modify: `atlasclaw-providers/providers/SmartCMP-Provider/skills/cost-optimization/scripts/execute_optimization.py`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/test/test_execute_optimization.py`

**Step 1: Write the failing test**

Add `test/test_execute_optimization.py` to verify:
- the script accepts a violation ID
- the script calls the day2 fix endpoint path for that violation
- the result block uses `executionSubmitted` rather than claiming completion
- invalid or empty IDs fail with a clear error

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_execute_optimization.py -q`
Expected: FAIL because the execution path is not implemented yet.

**Step 3: Write minimal implementation**

Implement `execute_optimization.py` so it:
- validates a single violation ID
- calls `POST /compliance-policies/violations/day2/fix/{id}`
- prints a human-readable submission result
- emits `##COST_EXECUTION_START## ... ##COST_EXECUTION_END##`

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_execute_optimization.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git -C atlasclaw-providers add providers/SmartCMP-Provider/skills/cost-optimization/scripts/execute_optimization.py providers/SmartCMP-Provider/test/test_execute_optimization.py
git -C atlasclaw-providers commit -m "feat(SmartCMP): add day2 cost fix execution"
```

### Task 8: Implement execution tracking

**Files:**
- Modify: `atlasclaw-providers/providers/SmartCMP-Provider/skills/cost-optimization/scripts/track_execution.py`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/test/test_track_execution.py`

**Step 1: Write the failing test**

Add `test/test_track_execution.py` to verify:
- violation-instance and resource-execution responses are normalized together
- overall status collapses to `SUCCESS`, `FAILED`, `EXECUTING`, or `PARTIAL`
- failure messages are surfaced in the structured result

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_track_execution.py -q`
Expected: FAIL because tracking normalization is not implemented yet.

**Step 3: Write minimal implementation**

Implement `track_execution.py` so it:
- queries `GET /compliance-policies/violation-instances/search`
- optionally queries `GET /compliance-policies/resource-executions/search`
- produces a normalized execution summary block

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_track_execution.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git -C atlasclaw-providers add providers/SmartCMP-Provider/skills/cost-optimization/scripts/track_execution.py providers/SmartCMP-Provider/test/test_track_execution.py
git -C atlasclaw-providers commit -m "feat(SmartCMP): add cost fix execution tracking"
```

### Task 9: Update provider docs and E2E coverage

**Files:**
- Modify: `atlasclaw-providers/providers/SmartCMP-Provider/PROVIDER.md`
- Modify: `atlasclaw-providers/providers/SmartCMP-Provider/README.md`
- Modify: `atlasclaw-providers/providers/SmartCMP-Provider/test/run_e2e_tests.py`

**Step 1: Write the failing validation note**

Document the missing coverage:
- provider docs do not mention `cost-optimization`
- provider docs do not clearly document the SaaS host guardrails
- E2E runner does not know about the new cost optimization scripts

**Step 2: Run current validations**

Run: `python3 atlasclaw-providers/providers/SmartCMP-Provider/test/run_e2e_tests.py --help`
Expected: PASS, but with no cost optimization coverage.

**Step 3: Write minimal implementation**

Update docs and E2E runner so they:
- list the new `cost-optimization` skill
- explain exact SaaS host handling and `auth_url`
- syntax-check the new scripts
- optionally run the new scripts in live mode when credentials are present

**Step 4: Run focused verification**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_smartcmp_auth_inference.py atlasclaw-providers/providers/SmartCMP-Provider/test/test_cost_optimization_layout.py atlasclaw-providers/providers/SmartCMP-Provider/test/test_cost_common.py atlasclaw-providers/providers/SmartCMP-Provider/test/test_list_recommendations.py atlasclaw-providers/providers/SmartCMP-Provider/test/test_cost_analysis_helpers.py atlasclaw-providers/providers/SmartCMP-Provider/test/test_analyze_recommendation.py atlasclaw-providers/providers/SmartCMP-Provider/test/test_execute_optimization.py atlasclaw-providers/providers/SmartCMP-Provider/test/test_track_execution.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git -C atlasclaw-providers add providers/SmartCMP-Provider/PROVIDER.md providers/SmartCMP-Provider/README.md providers/SmartCMP-Provider/test/run_e2e_tests.py
git -C atlasclaw-providers commit -m "docs(SmartCMP): document cost optimization capability"
```

### Task 10: Run live smoke validation

**Files:**
- Modify if needed: `atlasclaw-providers/providers/SmartCMP-Provider/test/run_e2e_tests.py`

**Step 1: Configure real credentials**

Set either:

```bash
export CMP_URL="https://democmp.smartcmp.cloud:1443"
export CMP_AUTH_URL="https://democmp.smartcmp.cloud:1443/platform-api/login"
export CMP_USERNAME="..."
export CMP_PASSWORD="..."
```

or:

```bash
export CMP_URL="https://democmp.smartcmp.cloud:1443"
export CMP_COOKIE="CloudChef-Authenticate=...; ..."
```

**Step 2: Run the live scripts in order**

Run:

```bash
python3 atlasclaw-providers/providers/SmartCMP-Provider/skills/cost-optimization/scripts/list_recommendations.py --size 5
python3 atlasclaw-providers/providers/SmartCMP-Provider/skills/cost-optimization/scripts/analyze_recommendation.py --id <violation_id>
python3 atlasclaw-providers/providers/SmartCMP-Provider/skills/cost-optimization/scripts/execute_optimization.py --id <violation_id>
python3 atlasclaw-providers/providers/SmartCMP-Provider/skills/cost-optimization/scripts/track_execution.py --id <violation_id>
```

Expected:
- list returns recommendation metadata
- analyze returns structured facts and recommendations
- execute submits SmartCMP-native day2 fix
- track returns normalized execution state

**Step 3: Run the full focused test suite again**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_smartcmp_auth_inference.py atlasclaw-providers/providers/SmartCMP-Provider/test/test_cost_optimization_layout.py atlasclaw-providers/providers/SmartCMP-Provider/test/test_cost_common.py atlasclaw-providers/providers/SmartCMP-Provider/test/test_list_recommendations.py atlasclaw-providers/providers/SmartCMP-Provider/test/test_cost_analysis_helpers.py atlasclaw-providers/providers/SmartCMP-Provider/test/test_analyze_recommendation.py atlasclaw-providers/providers/SmartCMP-Provider/test/test_execute_optimization.py atlasclaw-providers/providers/SmartCMP-Provider/test/test_track_execution.py -q`
Expected: PASS

**Step 4: Commit**

```bash
git -C atlasclaw-providers add providers/SmartCMP-Provider
git -C atlasclaw-providers commit -m "feat(SmartCMP): add cost optimization workflow"
```
