# SmartCMP Resource Compliance Expansion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expand the existing SmartCMP `resource-compliance` skill into a `componentType`-driven framework that normalizes each resource into `type + properties`, supports cloud/software/OS analyzer families, and adds first-pass analyzers for Tomcat, MySQL, PostgreSQL, Redis, Elasticsearch, SQL Server, Linux, Windows, and AliCloud OSS.

**Architecture:** Keep the existing `list_resource.py` and `analyze_resource.py` entrypoints, but extend retrieval to build a normalized `type + properties` projection from SmartCMP resource payloads. Refactor `_analysis.py` around analyzer routing by `componentType`, emit a generic finding structure, and keep live internet validation behind focused source adapters so the skill can grow by analyzer without rewiring the whole pipeline.

**Tech Stack:** Python CLI scripts, `requests`, SmartCMP shared auth helpers, pytest with monkeypatch-based network isolation, and SmartCMP live validation against `https://192.168.86.165`.

---

### Task 1: Add failing tests for the normalized `type + properties` projection

**Files:**
- Modify: `providers/SmartCMP-Provider/test/test_list_resource.py`
- Modify: `providers/SmartCMP-Provider/skills/shared/scripts/list_resource.py`

**Step 1: Write the failing tests**

Add tests that expect each resource record to expose a normalized projection for analysis:

```python
assert payload[0]["normalized"]["type"] == "resource.software.app.tomcat"
assert payload[0]["normalized"]["properties"]["softwareVersion"] == "9.0.0.M10"
assert payload[0]["normalized"]["properties"]["port"] == 8080
```

Add one test for duplicate keys so the first value wins:

```python
assert payload[0]["normalized"]["properties"]["status"] == "started"
```

even when the same key later appears in `details` or `extra`.

**Step 2: Run the tests to verify they fail**

Run:

```bash
pytest providers/SmartCMP-Provider/test/test_list_resource.py -q
```

Expected: FAIL because `list_resource.py` does not yet build `normalized.type` and `normalized.properties`.

**Step 3: Implement the minimal projection builder**

In `providers/SmartCMP-Provider/skills/shared/scripts/list_resource.py`, add helper functions similar to:

```python
def build_normalized_resource(record: dict) -> dict:
    return {
        "type": determine_component_type(record),
        "properties": build_flat_properties(record),
    }
```

Add a small flat-property merge helper:

```python
def merge_first_wins(target: dict, source: dict) -> None:
    for key, value in source.items():
        if key and key not in target and value not in (None, ""):
            target[key] = value
```

Attach the normalized projection to every returned record:

```python
record["normalized"] = build_normalized_resource(record)
```

**Step 4: Run the tests again**

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
git commit -m "feat(SmartCMP): add normalized resource projection"
```

### Task 2: Refactor analysis helpers around `componentType` routing and generic findings

**Files:**
- Modify: `providers/SmartCMP-Provider/test/test_resource_compliance_analysis.py`
- Modify: `providers/SmartCMP-Provider/skills/resource-compliance/scripts/_analysis.py`

**Step 1: Write failing helper tests for the new model**

Add tests that assert:

- the analysis input is taken from `record["normalized"]`
- routing is driven by `type`
- findings use the new generic fields

Example:

```python
assert result["type"] == "resource.software.app.tomcat"
assert result["analysisTargets"] == ["software:tomcat"]
assert result["findings"][0]["technology"] == "tomcat"
assert result["findings"][0]["analyzerType"] == "software"
```

Add one test for a resource that yields no analyzer:

```python
assert result["findings"][0]["findingType"] == "coverage"
assert result["summary"]["overallCompliance"] == "needs_review"
```

**Step 2: Run the helper tests to verify they fail**

Run:

```bash
pytest providers/SmartCMP-Provider/test/test_resource_compliance_analysis.py -q
```

Expected: FAIL because `_analysis.py` still uses narrow product detectors and the old finding shape.

**Step 3: Implement the routing skeleton**

Refactor `_analysis.py` to introduce:

```python
def analyze_normalized_resource(normalized: dict, external_checker) -> dict: ...
def route_analyzers(resource_type: str, properties: dict) -> list[str]: ...
def build_finding(...): ...
```

Return a resource-level payload like:

```python
{
    "type": normalized["type"],
    "properties": normalized["properties"],
    "analysisTargets": ["software:tomcat"],
    "findings": [...],
    "summary": {...},
    "uncertainties": [],
}
```

Keep the old helper names only if they are still needed for compatibility tests; otherwise remove dead paths cleanly.

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
git commit -m "refactor(SmartCMP): route compliance analysis by component type"
```

### Task 3: Update the CLI entrypoint to consume normalized records

**Files:**
- Modify: `providers/SmartCMP-Provider/test/test_analyze_resource.py`
- Modify: `providers/SmartCMP-Provider/skills/resource-compliance/scripts/analyze_resource.py`

**Step 1: Write failing CLI tests**

Add tests that assert:

- the final payload includes `type`, `properties`, and `analysisTargets`
- the CLI preserves direct-user and webhook input modes
- failed records still surface `type` when available from search results

Example:

```python
assert payload["results"][0]["type"] == "resource.software.app.tomcat"
assert "software:tomcat" in payload["results"][0]["analysisTargets"]
```

**Step 2: Run the CLI tests to verify they fail**

Run:

```bash
pytest providers/SmartCMP-Provider/test/test_analyze_resource.py -q
```

Expected: FAIL because `analyze_resource.py` still builds results around the old fact model.

**Step 3: Implement the minimal CLI changes**

Update `analyze_resource.py` to:

- read `record["normalized"]`
- pass the normalized projection into the new helper
- preserve top-level batch metadata
- keep readable summary output

If needed, add a small compatibility adapter:

```python
def normalize_record_for_analysis(record: dict) -> dict:
    return record.get("normalized") or legacy_projection(record)
```

**Step 4: Run the CLI tests again**

Run:

```bash
pytest providers/SmartCMP-Provider/test/test_analyze_resource.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add \
  providers/SmartCMP-Provider/test/test_analyze_resource.py \
  providers/SmartCMP-Provider/skills/resource-compliance/scripts/analyze_resource.py
git commit -m "feat(SmartCMP): analyze normalized component resources"
```

### Task 4: Add software analyzers for Tomcat, MySQL, PostgreSQL, Redis, Elasticsearch, and SQL Server

**Files:**
- Modify: `providers/SmartCMP-Provider/test/test_resource_compliance_analysis.py`
- Modify: `providers/SmartCMP-Provider/skills/resource-compliance/scripts/_analysis.py`
- Modify: `providers/SmartCMP-Provider/skills/resource-compliance/scripts/analyze_resource.py`

**Step 1: Write failing analyzer tests**

Add focused tests for:

- Tomcat lifecycle/vulnerability findings from `softwareVersion`
- MySQL lifecycle regression coverage
- PostgreSQL, Redis, Elasticsearch, SQL Server type routing and version extraction
- fallback to `needs_review` when version evidence is missing

Example:

```python
assert result["analysisTargets"] == ["software:postgresql"]
assert result["findings"][0]["technology"] == "postgresql"
assert result["findings"][0]["findingType"] == "lifecycle"
```

**Step 2: Run the tests to verify they fail**

Run:

```bash
pytest providers/SmartCMP-Provider/test/test_resource_compliance_analysis.py -q
```

Expected: FAIL because these analyzers and routes do not exist yet.

**Step 3: Implement the software analyzer registry**

In `_analysis.py`, add a registry structure similar to:

```python
SOFTWARE_ANALYZERS = {
    "resource.software.app.tomcat": analyze_tomcat,
    "resource.software.db.mysql": analyze_mysql,
    "resource.software.db.postgresql": analyze_postgresql,
    "resource.software.cache.redis": analyze_redis,
    "resource.software.search.elasticsearch": analyze_elasticsearch,
    "resource.software.db.sqlserver": analyze_sqlserver,
}
```

If the actual SmartCMP `componentType` strings differ, use the concrete strings from live resources and model definitions instead of inventing new aliases.

Add lightweight version helpers that inspect the flat `properties` bag for keys like:

- `softwareVersion`
- `version`
- `productVersion`
- `kernel`
- `build`
- `kb`

**Step 4: Run the tests again**

Run:

```bash
pytest providers/SmartCMP-Provider/test/test_resource_compliance_analysis.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add \
  providers/SmartCMP-Provider/test/test_resource_compliance_analysis.py \
  providers/SmartCMP-Provider/skills/resource-compliance/scripts/_analysis.py \
  providers/SmartCMP-Provider/skills/resource-compliance/scripts/analyze_resource.py
git commit -m "feat(SmartCMP): add software compliance analyzers"
```

### Task 5: Add Linux and Windows OS analyzers as first-class type routes

**Files:**
- Modify: `providers/SmartCMP-Provider/test/test_resource_compliance_analysis.py`
- Modify: `providers/SmartCMP-Provider/skills/resource-compliance/scripts/_analysis.py`

**Step 1: Write failing OS tests**

Add tests that cover:

- Linux type routes to `os:linux`
- Windows type routes to `os:windows`
- lifecycle and patch findings use OS-specific evidence
- missing version/build evidence degrades to `needs_review`

Example:

```python
assert result["analysisTargets"] == ["os:linux"]
assert result["findings"][0]["technology"] == "linux"
assert result["findings"][0]["analyzerType"] == "os"
```

**Step 2: Run the tests to verify they fail**

Run:

```bash
pytest providers/SmartCMP-Provider/test/test_resource_compliance_analysis.py -q
```

Expected: FAIL because Linux and Windows are not yet first-class routes.

**Step 3: Implement OS analyzers**

Use real SmartCMP component-type names from the environment and model definitions. The analyzer should:

- route directly by `type`
- extract distro/version/build/kernel/KB evidence from `properties`
- call the existing or refactored external source adapters
- emit generic findings with `analyzerType = "os"`

Where a software resource exposes strong OS evidence, optionally add sidecar analysis later, but keep direct OS routing as the main behavior.

**Step 4: Run the tests again**

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
git commit -m "feat(SmartCMP): add OS compliance analyzers"
```

### Task 6: Add the first cloud analyzer for AliCloud OSS

**Files:**
- Modify: `providers/SmartCMP-Provider/test/test_resource_compliance_analysis.py`
- Modify: `providers/SmartCMP-Provider/skills/resource-compliance/scripts/_analysis.py`

**Step 1: Write the failing cloud analyzer test**

Add a fixture based on `resource.iaas.storage.object.alicloud_oss_v2` and assert configuration findings such as:

- private/public exposure
- encryption presence
- monitor coverage

Example:

```python
assert result["analysisTargets"] == ["cloud:alicloud_oss_v2"]
assert result["findings"][0]["findingType"] in {"configuration", "exposure"}
```

Add one case where `publicAccess = private` but `encryptionAlgorithm = ""`, which should produce a configuration finding without claiming public exposure.

**Step 2: Run the test to verify it fails**

Run:

```bash
pytest providers/SmartCMP-Provider/test/test_resource_compliance_analysis.py -q
```

Expected: FAIL because no cloud analyzer exists yet.

**Step 3: Implement the OSS analyzer**

In `_analysis.py`, add a cloud analyzer route for:

```python
"resource.iaas.storage.object.alicloud_oss_v2": analyze_alicloud_oss
```

Use flat properties such as:

- `permission`
- `publicAccess`
- `encryptionAlgorithm`
- `monitorEnabled`
- `storage_class`
- `bucket_versioning_enabled`

Map them to conservative findings:

- missing encryption -> `configuration`
- public exposure -> `exposure`
- monitoring gaps -> `coverage` or `configuration`

**Step 4: Run the tests again**

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
git commit -m "feat(SmartCMP): add OSS configuration analyzer"
```

### Task 7: Update docs and skill guidance for the expanded framework

**Files:**
- Modify: `providers/SmartCMP-Provider/skills/resource-compliance/SKILL.md`
- Modify: `providers/SmartCMP-Provider/skills/resource-compliance/references/WORKFLOW.md`
- Modify: `providers/SmartCMP-Provider/skills/datasource/SKILL.md`
- Modify: `providers/SmartCMP-Provider/README.md`
- Modify: `providers/SmartCMP-Provider/PROVIDER.md`

**Step 1: Write the doc changes**

Update the skill docs so they describe:

- `componentType`-driven routing
- normalized `type + properties`
- cloud/software/OS analyzer families
- representative supported technologies

Add one short example showing a result payload that includes:

```json
{
  "type": "resource.software.app.tomcat",
  "analysisTargets": ["software:tomcat"]
}
```

**Step 2: Review the docs locally**

Run:

```bash
rg -n "componentType|analysisTargets|AliCloud OSS|Tomcat|Windows|Linux" \
  providers/SmartCMP-Provider/skills/resource-compliance \
  providers/SmartCMP-Provider/README.md \
  providers/SmartCMP-Provider/PROVIDER.md
```

Expected: Matches in all updated docs.

**Step 3: Commit**

```bash
git add \
  providers/SmartCMP-Provider/skills/resource-compliance/SKILL.md \
  providers/SmartCMP-Provider/skills/resource-compliance/references/WORKFLOW.md \
  providers/SmartCMP-Provider/skills/datasource/SKILL.md \
  providers/SmartCMP-Provider/README.md \
  providers/SmartCMP-Provider/PROVIDER.md
git commit -m "docs(SmartCMP): describe expanded compliance analyzers"
```

### Task 8: Run full automated verification and live SmartCMP validation

**Files:**
- No source changes required unless validation reveals defects

**Step 1: Run focused automated tests**

Run:

```bash
pytest \
  providers/SmartCMP-Provider/test/test_list_resource.py \
  providers/SmartCMP-Provider/test/test_resource_compliance_analysis.py \
  providers/SmartCMP-Provider/test/test_analyze_resource.py \
  providers/SmartCMP-Provider/test/test_resource_compliance_layout.py -q
```

Expected: PASS.

**Step 2: Run the existing broader SmartCMP regression set**

Run:

```bash
pytest \
  providers/SmartCMP-Provider/test/test_alarm_layout.py \
  providers/SmartCMP-Provider/test/test_cost_optimization_layout.py \
  providers/SmartCMP-Provider/test/test_analyze_alert.py \
  providers/SmartCMP-Provider/test/test_list_resource.py \
  providers/SmartCMP-Provider/test/test_resource_compliance_analysis.py \
  providers/SmartCMP-Provider/test/test_analyze_resource.py -q
```

Expected: PASS.

**Step 3: Validate live retrieval against representative resources**

Use the SmartCMP environment:

- URL: `https://192.168.86.165`
- Username: `admin`
- Password: `Passw0rd`

Run:

```bash
CMP_URL='https://192.168.86.165' CMP_USERNAME='admin' CMP_PASSWORD='Passw0rd' \
python providers/SmartCMP-Provider/skills/shared/scripts/list_resource.py \
  ba9ffc56-4d57-4b43-acc8-53d89f24fa9e \
  ac43ce78-917e-43e9-bc13-51e3f6e350c7 \
  e8d97ded-f821-4060-9924-c4ed21333742 \
  d9124f83-3613-4a6f-aeae-7daef865e745
```

Expected:

- Tomcat resource resolves with `type = resource.software.app.tomcat`
- OSS resource resolves with `type = resource.iaas.storage.object.alicloud_oss_v2`
- MySQL resource still resolves successfully
- VM resource still resolves successfully

**Step 4: Validate live analysis against representative resources**

Run:

```bash
CMP_URL='https://192.168.86.165' CMP_USERNAME='admin' CMP_PASSWORD='Passw0rd' \
python providers/SmartCMP-Provider/skills/resource-compliance/scripts/analyze_resource.py \
  ba9ffc56-4d57-4b43-acc8-53d89f24fa9e \
  ac43ce78-917e-43e9-bc13-51e3f6e350c7 \
  e8d97ded-f821-4060-9924-c4ed21333742
```

Expected:

- Tomcat produces software findings
- OSS produces cloud configuration findings
- MySQL still produces lifecycle/security findings

**Step 5: Locate and validate Linux and Windows live resource types if available**

Use SmartCMP search or the cloud-resource UI to identify one live Linux resource and one live Windows resource that map to the independent OS component types. If live runtime instances are not available, record that explicitly and keep the blueprint model pages as design references only:

- Linux model: `ed801c12-2562-4543-9a5c-2b32cc9f738b`
- Windows model: `c4061b48-df90-498e-88d6-644978caff42`

Do not claim live OS analyzer validation unless real resource IDs were analyzed successfully.

**Step 6: Commit any fixes from validation**

```bash
git add <files-fixed-during-validation>
git commit -m "fix(SmartCMP): address compliance expansion validation issues"
```

Only do this step if validation uncovers real defects.
