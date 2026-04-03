# SmartCMP Resource Compliance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add SmartCMP resource-detail retrieval plus a new `resource-compliance` skill that accepts one or more resource IDs, analyzes compliance/security posture, and supports both direct-user and webhook-driven invocation.

**Architecture:** Reuse the SmartCMP shared script pattern by adding `providers/SmartCMP-Provider/skills/shared/scripts/list_resource.py` as the data-retrieval primitive. Build `providers/SmartCMP-Provider/skills/resource-compliance/` as a single analysis skill that normalizes user/webhook inputs, fetches resource facts from SmartCMP, performs live external validation against authoritative internet sources when product/version evidence is sufficient, and emits readable text plus a stable JSON block.

**Tech Stack:** Python CLI scripts, `requests`, SmartCMP shared auth helpers in `skills/shared/scripts/_common.py`, Markdown `SKILL.md` docs, and pytest with monkeypatch-based API/network isolation.

---

### Task 1: Add the new skill and datasource layout tests first

**Files:**
- Create: `providers/SmartCMP-Provider/test/test_resource_compliance_layout.py`
- Modify: `providers/SmartCMP-Provider/test/test_cost_optimization_layout.py`
- Modify: `providers/SmartCMP-Provider/skills/datasource/SKILL.md`

**Step 1: Write the failing layout test for the new skill**

Create `providers/SmartCMP-Provider/test/test_resource_compliance_layout.py` with checks for the new directory and script layout:

```python
from pathlib import Path


PROVIDER_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = PROVIDER_ROOT / "skills" / "resource-compliance"
SHARED_SCRIPTS = PROVIDER_ROOT / "skills" / "shared" / "scripts"


def test_resource_compliance_skill_layout_exists():
    expected_files = [
        "SKILL.md",
        "references/WORKFLOW.md",
        "scripts/_analysis.py",
        "scripts/analyze_resource.py",
    ]

    assert SKILL_ROOT.is_dir()
    for relative_path in expected_files:
        assert (SKILL_ROOT / relative_path).exists(), relative_path

    assert (SHARED_SCRIPTS / "list_resource.py").exists()


def test_datasource_skill_mentions_resource_lookup():
    skill_text = (
        PROVIDER_ROOT / "skills" / "datasource" / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert "list_resource.py" in skill_text
    assert "resource details" in skill_text.lower()
```

**Step 2: Run the test to verify it fails**

Run:

```bash
pytest providers/SmartCMP-Provider/test/test_resource_compliance_layout.py -q
```

Expected: FAIL because the `resource-compliance` skill directory and `list_resource.py` do not exist yet.

**Step 3: Add the minimal layout scaffolding**

Create these files with minimal import-safe placeholders:

- `providers/SmartCMP-Provider/skills/resource-compliance/SKILL.md`
- `providers/SmartCMP-Provider/skills/resource-compliance/references/WORKFLOW.md`
- `providers/SmartCMP-Provider/skills/resource-compliance/scripts/_analysis.py`
- `providers/SmartCMP-Provider/skills/resource-compliance/scripts/analyze_resource.py`
- `providers/SmartCMP-Provider/skills/shared/scripts/list_resource.py`

Use minimal content like:

```python
def main(argv=None):
    return 0
```

and a frontmatter skeleton like:

```yaml
---
name: "resource-compliance"
description: "Resource compliance skill. Analyze one or more SmartCMP resources for lifecycle, patch, and security risk."
provider_type: "smartcmp"
instance_required: "true"
---
```

**Step 4: Update datasource docs enough to satisfy the test**

In `providers/SmartCMP-Provider/skills/datasource/SKILL.md`, add one new row to the scripts table:

```markdown
| `list_resource.py` | List resource details by resource ID | `<RESOURCE_ID> [RESOURCE_ID ...]` |
```

Also add one short example showing:

```bash
python ../shared/scripts/list_resource.py <resource_id>
```

**Step 5: Run the layout test again**

Run:

```bash
pytest providers/SmartCMP-Provider/test/test_resource_compliance_layout.py -q
```

Expected: PASS.

**Step 6: Commit**

```bash
git add \
  providers/SmartCMP-Provider/test/test_resource_compliance_layout.py \
  providers/SmartCMP-Provider/skills/datasource/SKILL.md \
  providers/SmartCMP-Provider/skills/resource-compliance/SKILL.md \
  providers/SmartCMP-Provider/skills/resource-compliance/references/WORKFLOW.md \
  providers/SmartCMP-Provider/skills/resource-compliance/scripts/_analysis.py \
  providers/SmartCMP-Provider/skills/resource-compliance/scripts/analyze_resource.py \
  providers/SmartCMP-Provider/skills/shared/scripts/list_resource.py
git commit -m "test(SmartCMP): add resource compliance skill layout"
```

### Task 2: Implement shared resource retrieval with deterministic tests

**Files:**
- Create: `providers/SmartCMP-Provider/test/test_list_resource.py`
- Modify: `providers/SmartCMP-Provider/skills/shared/scripts/list_resource.py`

**Step 1: Write the failing retrieval tests**

Create `providers/SmartCMP-Provider/test/test_list_resource.py` covering:

- single ID fetch
- multi-ID fetch
- merge of `/nodes/search`, `/nodes/{id}`, `/nodes/{id}/details`
- partial failure for one resource
- metadata block extraction

Use the existing script-test style from `test_analyze_alert.py`:

```python
def test_main_merges_search_resource_and_detail_calls(monkeypatch):
    module = load_module()

    def fake_request(method, path, *, payload=None, params=None):
        ...

    monkeypatch.setattr(module, "request_json", fake_request)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["res-1", "res-2"])

    output = stdout.getvalue()
    assert exit_code == 0
    assert "Found 2 resource(s)." in output
    payload = extract_payload(output)
    assert payload[0]["resourceId"] == "res-1"
    assert payload[0]["details"]["osVersion"] == "Ubuntu 20.04"
```

**Step 2: Run the retrieval test to verify it fails**

Run:

```bash
pytest providers/SmartCMP-Provider/test/test_list_resource.py -q
```

Expected: FAIL because `list_resource.py` does not yet implement request/normalization logic.

**Step 3: Implement `list_resource.py` with minimal complete behavior**

In `providers/SmartCMP-Provider/skills/shared/scripts/list_resource.py`:

- import `require_config` from `skills/shared/scripts/_common.py`
- implement a small request helper:

```python
def request_json(method: str, path: str, *, payload=None, params=None):
    response = requests.request(
        method,
        f"{base_url}{path}",
        headers=headers,
        json=payload,
        params=params,
        verify=False,
        timeout=30,
    )
    ...
```

- implement these functions:

```python
def extract_list_payload(payload) -> list: ...
def normalize_resource_summary(item: dict) -> dict: ...
def fetch_resource_record(resource_id: str) -> dict: ...
def render_output(items: list[dict]) -> str: ...
def main(argv=None) -> int: ...
```

Normalize to a stable output shape like:

```python
{
    "resourceId": resource_id,
    "summary": search_item,
    "resource": resource_item,
    "details": detail_map,
    "fetchStatus": "ok",
    "errors": [],
}
```

Emit a metadata block such as:

```text
##RESOURCE_META_START##
[...json...]
##RESOURCE_META_END##
```

**Step 4: Run the retrieval test again**

Run:

```bash
pytest providers/SmartCMP-Provider/test/test_list_resource.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add \
  providers/SmartCMP-Provider/test/test_list_resource.py \
  providers/SmartCMP-Provider/skills/shared/scripts/list_resource.py
git commit -m "feat(SmartCMP): add resource detail retrieval script"
```

### Task 3: Implement fact extraction and external-validation helpers

**Files:**
- Create: `providers/SmartCMP-Provider/test/test_resource_compliance_analysis.py`
- Modify: `providers/SmartCMP-Provider/skills/resource-compliance/scripts/_analysis.py`

**Step 1: Write failing analysis-helper tests**

Create `providers/SmartCMP-Provider/test/test_resource_compliance_analysis.py` with focused tests for:

- MySQL version extraction from resource facts
- Windows version detection and patch-risk fallback
- Linux distribution/version detection
- graceful downgrade when external validation is unavailable
- `needs_review` when version evidence is missing

Example:

```python
def test_builds_mysql_finding_from_version_and_external_check():
    facts = {
        "resourceId": "db-1",
        "softwares": "MySQL 5.7.22",
        "osDescription": "CentOS 7.9",
    }

    result = module.analyze_resource_facts(
        facts,
        external_checker=lambda product, version: {
            "status": "unsupported",
            "summary": "MySQL 5.7 is beyond standard support.",
            "links": ["https://example.invalid/mysql-support"],
        },
    )

    assert result["summary"]["overallCompliance"] == "non_compliant"
    assert result["findings"][0]["category"] == "mysql_lifecycle"
```

**Step 2: Run the helper tests to verify they fail**

Run:

```bash
pytest providers/SmartCMP-Provider/test/test_resource_compliance_analysis.py -q
```

Expected: FAIL because `_analysis.py` only contains a placeholder.

**Step 3: Implement `_analysis.py` with pure helper functions**

In `providers/SmartCMP-Provider/skills/resource-compliance/scripts/_analysis.py`, implement pure functions that are easy to test:

```python
def build_analysis_facts(resource_record: dict) -> dict: ...
def detect_mysql(facts: dict) -> dict | None: ...
def detect_windows(facts: dict) -> dict | None: ...
def detect_linux(facts: dict) -> dict | None: ...
def analyze_resource_facts(facts: dict, external_checker) -> dict: ...
def summarize_findings(findings: list[dict]) -> dict: ...
```

Keep the external lookup pluggable:

```python
def analyze_resource_facts(facts: dict, external_checker):
    ...
    external = external_checker(product, version)
```

Use conservative result statuses:

- `compliant`
- `at_risk`
- `non_compliant`
- `needs_review`

and confidence values:

- `high`
- `medium`
- `low`

**Step 4: Run the helper tests again**

Run:

```bash
pytest providers/SmartCMP-Provider/test/test_resource_compliance_analysis.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add \
  providers/SmartCMP-Provider/test/test_resource_compliance_analysis.py \
  providers/SmartCMP-Provider/skills/resource-compliance/scripts/_analysis.py
git commit -m "feat(SmartCMP): add resource compliance analysis helpers"
```

### Task 4: Implement the CLI entrypoint and stable output contract

**Files:**
- Create: `providers/SmartCMP-Provider/test/test_analyze_resource.py`
- Modify: `providers/SmartCMP-Provider/skills/resource-compliance/scripts/analyze_resource.py`
- Modify: `providers/SmartCMP-Provider/skills/resource-compliance/SKILL.md`
- Modify: `providers/SmartCMP-Provider/skills/resource-compliance/references/WORKFLOW.md`

**Step 1: Write the failing CLI tests**

Create `providers/SmartCMP-Provider/test/test_analyze_resource.py` covering:

- direct-user input via CLI IDs
- webhook-mode input via JSON metadata flag or payload file
- readable summary plus JSON block
- partial success when one resource fetch fails
- external-validation degradation marker when checker raises

Example:

```python
def test_main_emits_summary_and_analysis_block(monkeypatch):
    module = load_module()

    monkeypatch.setattr(module, "load_resources", lambda ids: [...])
    monkeypatch.setattr(module, "external_checker", fake_checker)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = module.main(["res-1", "res-2", "--trigger-source", "webhook"])

    output = stdout.getvalue()
    payload = extract_payload(output)
    assert exit_code == 0
    assert payload["requestedResourceIds"] == ["res-1", "res-2"]
    assert payload["triggerSource"] == "webhook"
```

**Step 2: Run the CLI tests to verify they fail**

Run:

```bash
pytest providers/SmartCMP-Provider/test/test_analyze_resource.py -q
```

Expected: FAIL because the CLI does not yet parse inputs or emit the expected structure.

**Step 3: Implement `analyze_resource.py`**

In `providers/SmartCMP-Provider/skills/resource-compliance/scripts/analyze_resource.py`:

- parse arguments:

```python
def parse_args(argv=None):
    parser.add_argument("resource_ids", nargs="*")
    parser.add_argument("--trigger-source", default="user")
    parser.add_argument("--payload-json")
```

- normalize direct/webhook input into one internal request
- call the retrieval layer
- call analysis helpers
- render readable output and emit a stable JSON block:

```text
##RESOURCE_COMPLIANCE_START##
{...json...}
##RESOURCE_COMPLIANCE_END##
```

Target top-level JSON keys:

```python
{
    "triggerSource": ...,
    "requestedResourceIds": ...,
    "analyzedCount": ...,
    "failedCount": ...,
    "generatedAt": ...,
    "results": [...],
}
```

**Step 4: Fill out `SKILL.md` and `WORKFLOW.md`**

Document:

- trigger wording for user and webhook-style input
- examples for direct invocation
- analysis boundaries
- external validation behavior
- degradation behavior when internet checks fail

Add short examples like:

```bash
python scripts/analyze_resource.py <resource_id>
python scripts/analyze_resource.py --payload-json '{"resourceIds":["id-1"],"triggerSource":"webhook"}'
```

**Step 5: Run the CLI tests again**

Run:

```bash
pytest providers/SmartCMP-Provider/test/test_analyze_resource.py -q
```

Expected: PASS.

**Step 6: Commit**

```bash
git add \
  providers/SmartCMP-Provider/test/test_analyze_resource.py \
  providers/SmartCMP-Provider/skills/resource-compliance/scripts/analyze_resource.py \
  providers/SmartCMP-Provider/skills/resource-compliance/SKILL.md \
  providers/SmartCMP-Provider/skills/resource-compliance/references/WORKFLOW.md
git commit -m "feat(SmartCMP): add resource compliance skill"
```

### Task 5: Wire provider discovery docs and datasource references

**Files:**
- Modify: `providers/SmartCMP-Provider/PROVIDER.md`
- Modify: `providers/SmartCMP-Provider/README.md`
- Modify: `providers/SmartCMP-Provider/skills/datasource/SKILL.md`
- Modify: `providers/SmartCMP-Provider/skills/datasource/references/WORKFLOW.md`

**Step 1: Add failing documentation expectations**

Extend `providers/SmartCMP-Provider/test/test_resource_compliance_layout.py` to require:

- `resource-compliance` appears in `PROVIDER.md`
- `README.md` mentions the new skill
- `datasource` workflow docs mention `list_resource.py`

Example assertions:

```python
provider_text = (PROVIDER_ROOT / "PROVIDER.md").read_text(encoding="utf-8")
assert "resource-compliance" in provider_text

readme_text = (PROVIDER_ROOT / "README.md").read_text(encoding="utf-8")
assert "resource-compliance" in readme_text
```

**Step 2: Run the layout test to verify it fails**

Run:

```bash
pytest providers/SmartCMP-Provider/test/test_resource_compliance_layout.py -q
```

Expected: FAIL because provider-level docs do not mention the new capability yet.

**Step 3: Update discovery docs**

In `providers/SmartCMP-Provider/PROVIDER.md`:

- add a capability line for resource compliance analysis
- add a `use_when` bullet for resource-ID-based compliance/security review
- add `resource-compliance` to the Provided Skills table

In `providers/SmartCMP-Provider/README.md`:

- add a new section describing the `resource-compliance` workflow

In `providers/SmartCMP-Provider/skills/datasource/references/WORKFLOW.md`:

- add one example for fetching resource details by ID

**Step 4: Run the layout test again**

Run:

```bash
pytest providers/SmartCMP-Provider/test/test_resource_compliance_layout.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add \
  providers/SmartCMP-Provider/PROVIDER.md \
  providers/SmartCMP-Provider/README.md \
  providers/SmartCMP-Provider/skills/datasource/SKILL.md \
  providers/SmartCMP-Provider/skills/datasource/references/WORKFLOW.md \
  providers/SmartCMP-Provider/test/test_resource_compliance_layout.py
git commit -m "docs(SmartCMP): document resource compliance workflow"
```

### Task 6: Run focused and full verification before completion

**Files:**
- No new files

**Step 1: Run focused tests for the new feature**

Run:

```bash
pytest \
  providers/SmartCMP-Provider/test/test_resource_compliance_layout.py \
  providers/SmartCMP-Provider/test/test_list_resource.py \
  providers/SmartCMP-Provider/test/test_resource_compliance_analysis.py \
  providers/SmartCMP-Provider/test/test_analyze_resource.py -q
```

Expected: all PASS.

**Step 2: Run nearby SmartCMP regression tests**

Run:

```bash
pytest \
  providers/SmartCMP-Provider/test/test_alarm_layout.py \
  providers/SmartCMP-Provider/test/test_cost_optimization_layout.py \
  providers/SmartCMP-Provider/test/test_analyze_alert.py -q
```

Expected: PASS with no regressions from shared-script or doc updates.

**Step 3: Review the final changed file set**

Run:

```bash
git status --short
git diff --stat
```

Expected: only the intended SmartCMP files are changed.

**Step 4: Run @verification-before-completion**

Verify:

- the new skill imports cleanly
- the new metadata blocks are stable
- the degradation path for internet failure is covered by tests

**Step 5: Commit the final verification checkpoint**

```bash
git add providers/SmartCMP-Provider
git commit -m "test(SmartCMP): verify resource compliance implementation"
```

### Task 7: Validate against the live SmartCMP environment and real resources

**Files:**
- No new product files
- Optional notes: local scratch notes only, do not commit secrets

**Step 1: Confirm the live validation target and credentials**

Use this SmartCMP UI environment for validation:

- UI root: `https://192.168.86.165/#/main/cloud-resource`
- Username: `admin`
- Password: `Passw0rd`

Validate these two real resource pages in the UI:

- `https://192.168.86.165/#/main/cloud-resource/e8d97ded-f821-4060-9924-c4ed21333742`
- `https://192.168.86.165/#/main/virtual-machines/d9124f83-3613-4a6f-aeae-7daef865e745/details`

Expected: both resources are reachable in the UI after login.

**Step 2: Configure SmartCMP script access for the same environment**

Run:

```bash
export CMP_URL="https://192.168.86.165"
export CMP_USERNAME="admin"
export CMP_PASSWORD="Passw0rd"
```

Optional sanity check:

```bash
python -c "
import sys
sys.path.insert(0, 'providers/SmartCMP-Provider/skills/shared/scripts')
from _common import get_cmp_config
url, auth_token, _ = get_cmp_config()
print(url)
print(bool(auth_token))
"
```

Expected: URL resolves to the SmartCMP API base and authentication succeeds.

**Step 3: Validate raw resource retrieval for the two real resource IDs**

Run:

```bash
python providers/SmartCMP-Provider/skills/shared/scripts/list_resource.py \
  e8d97ded-f821-4060-9924-c4ed21333742 \
  d9124f83-3613-4a6f-aeae-7daef865e745
```

Verify in the output:

- both resource IDs appear
- `##RESOURCE_META_START## ... ##RESOURCE_META_END##` is emitted
- each resource record has `fetchStatus: ok` or a clear per-resource error
- merged output includes SmartCMP summary/resource/details data

**Step 4: Cross-check retrieval output against the UI**

After logging in at `https://192.168.86.165/#/main/cloud-resource`, open the two resource URLs and compare the script output with what the UI shows for:

- resource name
- resource type or VM classification
- status and power state
- OS type / OS description
- image or template information if displayed
- agent/monitor/install state if displayed
- any version clues visible in details, software, or properties

Expected: the script output matches the visible UI facts closely enough that the analysis will be grounded in real CMP data.

**Step 5: Validate the new analysis skill against the same two resources**

Run:

```bash
python providers/SmartCMP-Provider/skills/resource-compliance/scripts/analyze_resource.py \
  e8d97ded-f821-4060-9924-c4ed21333742 \
  d9124f83-3613-4a6f-aeae-7daef865e745
```

Verify in the output:

- readable summary for both resources
- `##RESOURCE_COMPLIANCE_START## ... ##RESOURCE_COMPLIANCE_END##` is emitted
- top-level keys include `triggerSource`, `requestedResourceIds`, `analyzedCount`, `failedCount`, `generatedAt`, and `results`
- each resource result contains `observations`, `findings`, `summary`, `recommendations`, and `uncertainties`

**Step 6: Validate external internet checking behavior with real data**

For each of the two real resources:

- if product/version evidence is sufficient, confirm the result includes external evidence or source links
- if product/version evidence is insufficient, confirm the result stays conservative and returns `needs_review` or lower-confidence assessment
- if an external site is temporarily unavailable, confirm the skill degrades gracefully instead of failing the whole batch

Expected: no hard crash caused by external validation, and every conclusion is backed by resource evidence plus external links when available.

**Step 7: Validate webhook-style input using the same real resources**

Run:

```bash
python providers/SmartCMP-Provider/skills/resource-compliance/scripts/analyze_resource.py \
  --payload-json '{"resourceIds":["e8d97ded-f821-4060-9924-c4ed21333742","d9124f83-3613-4a6f-aeae-7daef865e745"],"triggerSource":"webhook","rawMetadata":{"event":"manual-validation"}}'
```

Verify:

- the same two resources are analyzed successfully
- `triggerSource` is `webhook`
- the output shape is the same as direct-user mode aside from trigger metadata

**Step 8: Record the live validation outcome in the final implementation summary**

When implementation is complete, include in the final notes:

- whether both real resource pages were accessible
- whether `list_resource.py` matched the UI
- whether `analyze_resource.py` returned stable structured output for both IDs
- whether external internet validation succeeded or degraded

Do not commit the username/password into source files, tests, fixtures, or documentation outside this implementation plan.
