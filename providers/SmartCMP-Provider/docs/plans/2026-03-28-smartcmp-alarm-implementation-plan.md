# SmartCMP Alarm Capability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add SmartCMP-native alarm retrieval, rule-aware analysis, and alert status operations to the existing SmartCMP provider.

**Architecture:** Introduce a new `alarm` skill under `SmartCMP-Provider`, keep SmartCMP as the only data source, reuse shared auth helpers from `_common.py`, and split logic into list, analyze, and operate scripts with a small alarm-specific helper layer. Analysis should normalize SmartCMP alert, policy, and overview data first, then generate evidence-backed recommendations from those normalized facts.

**Tech Stack:** Python 3 scripts, requests, SmartCMP REST APIs, Markdown skill docs, pytest fixture tests, existing SmartCMP E2E runner.

---

### Task 1: Scaffold the alarm skill and baseline validation

**Files:**
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/skills/alarm/SKILL.md`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/skills/alarm/references/WORKFLOW.md`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/skills/alarm/scripts/_alarm_common.py`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/skills/alarm/scripts/list_alerts.py`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/skills/alarm/scripts/analyze_alert.py`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/skills/alarm/scripts/operate_alert.py`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/test/test_alarm_layout.py`

- [ ] **Step 1: Write the failing test**

Add `test/test_alarm_layout.py` to assert:
- the `alarm` skill directory exists
- `SKILL.md` includes `name:` and `description:`
- the three new scripts exist

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_alarm_layout.py -q`
Expected: FAIL because the alarm skill files do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Create the alarm skill scaffold with:
- a top-level `alarm` skill description
- a workflow reference
- script placeholders that import cleanly

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_alarm_layout.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C atlasclaw-providers add providers/SmartCMP-Provider/skills/alarm providers/SmartCMP-Provider/test/test_alarm_layout.py
git -C atlasclaw-providers commit -m "feat(SmartCMP): scaffold alarm skill"
```

### Task 2: Add common SmartCMP alarm helpers

**Files:**
- Modify: `atlasclaw-providers/providers/SmartCMP-Provider/skills/alarm/scripts/_alarm_common.py`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/test/test_alarm_common.py`

- [ ] **Step 1: Write the failing test**

Add `test/test_alarm_common.py` to verify:
- alert action names map to the expected SmartCMP status values
- timestamp normalization returns stable ISO-like strings
- list/overview response extraction tolerates `content`, `data`, and raw arrays

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_alarm_common.py -q`
Expected: FAIL because helper functions are not implemented yet.

- [ ] **Step 3: Write minimal implementation**

Implement `_alarm_common.py` with:
- `ACTION_STATUS_MAP = {"mute": "ALERT_MUTED", "resolve": "ALERT_RESOLVED", "reopen": "ALERT_FIRING"}`
- response extractors for alert/policy payloads
- timestamp and argument helpers
- SmartCMP request helpers that reuse `skills/shared/scripts/_common.py`

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_alarm_common.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C atlasclaw-providers add providers/SmartCMP-Provider/skills/alarm/scripts/_alarm_common.py providers/SmartCMP-Provider/test/test_alarm_common.py
git -C atlasclaw-providers commit -m "test(SmartCMP): add alarm helper coverage"
```

### Task 3: Implement triggered alert listing

**Files:**
- Modify: `atlasclaw-providers/providers/SmartCMP-Provider/skills/alarm/scripts/list_alerts.py`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/test/test_list_alerts.py`

- [ ] **Step 1: Write the failing test**

Add `test/test_list_alerts.py` with fixture payloads that assert:
- `list_alerts.py` formats a numbered human-readable summary
- the script emits `##ALARM_META_START## ... ##ALARM_META_END##`
- each meta item includes `alertId`, `alarmPolicyId`, `status`, `level`, and resource identifiers

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_list_alerts.py -q`
Expected: FAIL because the listing logic and meta serializer are incomplete.

- [ ] **Step 3: Write minimal implementation**

Implement `list_alerts.py` so it:
- queries `/alarm-alert`
- supports status, days, level, and deployment/resource filters
- prints concise text output
- emits normalized alarm metadata in English keys

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_list_alerts.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C atlasclaw-providers add providers/SmartCMP-Provider/skills/alarm/scripts/list_alerts.py providers/SmartCMP-Provider/test/test_list_alerts.py
git -C atlasclaw-providers commit -m "feat(SmartCMP): add alarm alert listing"
```

### Task 4: Implement deterministic analysis normalization

**Files:**
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/skills/alarm/scripts/_analysis.py`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/test/test_alarm_analysis_helpers.py`

- [ ] **Step 1: Write the failing test**

Add `test/test_alarm_analysis_helpers.py` to assert:
- normalized facts include both alert and rule fields
- heuristic pattern classification distinguishes persistent vs noisy fixture cases
- recommendation objects always include `action`, `confidence`, `reason`, and `evidence`

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_alarm_analysis_helpers.py -q`
Expected: FAIL because the analysis helper module does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Create `_analysis.py` with deterministic helpers for:
- fact normalization
- pattern classification
- risk labeling
- recommendation assembly

Keep all keys and action names in English.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_alarm_analysis_helpers.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C atlasclaw-providers add providers/SmartCMP-Provider/skills/alarm/scripts/_analysis.py providers/SmartCMP-Provider/test/test_alarm_analysis_helpers.py
git -C atlasclaw-providers commit -m "feat(SmartCMP): add alarm analysis helpers"
```

### Task 5: Implement rule-aware alert analysis output

**Files:**
- Modify: `atlasclaw-providers/providers/SmartCMP-Provider/skills/alarm/scripts/analyze_alert.py`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/test/test_analyze_alert.py`

- [ ] **Step 1: Write the failing test**

Add `test/test_analyze_alert.py` with fixture-driven expectations that:
- the script returns a human summary
- the script emits `##ALARM_ANALYSIS_START## ... ##ALARM_ANALYSIS_END##`
- the structured output includes `facts`, `assessment`, `recommendations`, and `suggested_status_operation`
- facts and recommendations remain English-only in key names

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_analyze_alert.py -q`
Expected: FAIL because `analyze_alert.py` does not yet assemble the full payload.

- [ ] **Step 3: Write minimal implementation**

Implement `analyze_alert.py` so it:
- loads alert instances
- fetches `AlarmPolicy` by `alarmPolicyId`
- enriches with overview/stat context when available
- runs recommendation generation on normalized facts
- falls back to fact-only output when enrichment is partial

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_analyze_alert.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C atlasclaw-providers add providers/SmartCMP-Provider/skills/alarm/scripts/analyze_alert.py providers/SmartCMP-Provider/test/test_analyze_alert.py
git -C atlasclaw-providers commit -m "feat(SmartCMP): add rule-aware alarm analysis"
```

### Task 6: Implement alert status operations

**Files:**
- Modify: `atlasclaw-providers/providers/SmartCMP-Provider/skills/alarm/scripts/operate_alert.py`
- Create: `atlasclaw-providers/providers/SmartCMP-Provider/test/test_operate_alert.py`

- [ ] **Step 1: Write the failing test**

Add `test/test_operate_alert.py` to verify:
- `mute`, `resolve`, and `reopen` map to the expected SmartCMP statuses
- batch IDs are serialized correctly into the operation payload
- invalid actions fail with a clear error

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_operate_alert.py -q`
Expected: FAIL because the operation payload builder is not implemented yet.

- [ ] **Step 3: Write minimal implementation**

Implement `operate_alert.py` so it:
- accepts one or more alert IDs
- accepts the English action names `mute`, `resolve`, `reopen`
- calls `/alarm-alert/operation`
- emits a structured operation result block

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_operate_alert.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git -C atlasclaw-providers add providers/SmartCMP-Provider/skills/alarm/scripts/operate_alert.py providers/SmartCMP-Provider/test/test_operate_alert.py
git -C atlasclaw-providers commit -m "feat(SmartCMP): add alarm status operations"
```

### Task 7: Update provider docs and live smoke coverage

**Files:**
- Modify: `atlasclaw-providers/providers/SmartCMP-Provider/PROVIDER.md`
- Modify: `atlasclaw-providers/providers/SmartCMP-Provider/README.md`
- Modify: `atlasclaw-providers/providers/SmartCMP-Provider/test/run_e2e_tests.py`

- [ ] **Step 1: Write the failing test or validation note**

Document the missing coverage:
- provider docs still say monitoring/alerts should use another provider
- E2E does not know about the new alarm scripts

- [ ] **Step 2: Run targeted validation to confirm the gap**

Run:
- `rg -n "monitoring or alerts|alarm" atlasclaw-providers/providers/SmartCMP-Provider/PROVIDER.md atlasclaw-providers/providers/SmartCMP-Provider/README.md`
- `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_alarm_layout.py -q`

Expected:
- docs still show outdated capability text
- alarm layout tests already pass, but no live smoke references exist yet

- [ ] **Step 3: Write minimal implementation**

Update docs and E2E so they:
- document the new `alarm` skill
- describe SmartCMP-native alarm retrieval, analysis, and status operations
- include syntax/live smoke coverage for `list_alerts.py` and `analyze_alert.py`
- keep destructive status operations skipped by default in E2E

- [ ] **Step 4: Run verification to confirm it works**

Run:
- `python3 -m pytest atlasclaw-providers/providers/SmartCMP-Provider/test/test_alarm_layout.py atlasclaw-providers/providers/SmartCMP-Provider/test/test_alarm_common.py atlasclaw-providers/providers/SmartCMP-Provider/test/test_list_alerts.py atlasclaw-providers/providers/SmartCMP-Provider/test/test_alarm_analysis_helpers.py atlasclaw-providers/providers/SmartCMP-Provider/test/test_analyze_alert.py atlasclaw-providers/providers/SmartCMP-Provider/test/test_operate_alert.py -q`
- `python3 atlasclaw-providers/providers/SmartCMP-Provider/test/run_e2e_tests.py --url 'https://192.168.86.164/platform-api' --cookie '<valid-cookie>'`

Expected:
- pytest suite PASS
- E2E reports syntax/live success for alarm list/analyze and skips status mutations

- [ ] **Step 5: Commit**

```bash
git -C atlasclaw-providers add providers/SmartCMP-Provider/PROVIDER.md providers/SmartCMP-Provider/README.md providers/SmartCMP-Provider/test/run_e2e_tests.py
git -C atlasclaw-providers commit -m "docs(SmartCMP): document alarm capability"
```
