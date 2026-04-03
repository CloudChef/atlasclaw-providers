# SmartCMP Resource Compliance Expansion Design

**Date:** 2026-04-04

## Goal

Evolve the existing SmartCMP `resource-compliance` skill from a narrow MySQL/Windows/Linux detector into a generic analysis framework that can evaluate cloud resources, software resources, and operating-system resources by using the SmartCMP `componentType` as the primary type identifier.

## Approved Design Decisions

- Keep the analysis input model to two layers only:
  - `type`
  - `properties`
- Use SmartCMP `componentType` as `type`.
- Treat `componentType` as the required, globally unique routing key.
- Aggregate resource facts into a single flattened `properties` object.
- Do not build a complex normalization schema in the first expansion; keep the aggregation simple and stable.
- When duplicate property names appear during aggregation, keep the first value and ignore later duplicates.
- Split analyzers into three first-class families:
  - cloud analyzers
  - software analyzers
  - OS analyzers
- Treat Linux and Windows as independent resource types, not just inferred sidecar signals.
- Continue to use live internet validation against authoritative sources when version/configuration evidence is sufficient.

## Why The Current Version Needs Expansion

The existing first version is intentionally narrow:

- it extracts ad-hoc facts from raw SmartCMP resource payloads
- it recognizes only a small set of technologies
- it is optimized around MySQL/Windows/Linux heuristics

That is good enough for initial value, but it does not scale cleanly to:

- Tomcat
- PostgreSQL
- Redis
- Elasticsearch
- SQL Server
- independent Linux and Windows resource objects
- cloud configuration resources such as AliCloud OSS

The expansion should preserve the current skill entrypoint and shared retrieval path while replacing the internals with a more generic routing and analyzer model.

## Canonical Analysis Model

All resources should be normalized for analysis into this shape:

```json
{
  "type": "resource.software.app.tomcat",
  "properties": {
    "name": "Tomcat_dn0myj",
    "status": "started",
    "softwareName": "Tomcat",
    "softwareVersion": "9.0.0.M10",
    "osType": "linux",
    "port": 8080,
    "machine": "SVR_aCloud_259_200.200.167.111"
  }
}
```

Notes:

- `type` is always the SmartCMP `componentType`
- `properties` is a flat merged attribute bag
- analyzers should depend on `type` first and `properties` second

## Property Aggregation Rules

The first expansion should avoid fragile, over-designed remapping. Instead, it should flatten provider facts into one property bag.

### Primary aggregation order

Populate `properties` in this order:

1. top-level resource fields that are analysis-relevant
2. `resourceInfo`
3. `RuntimeProperties`
4. `customProperties`
5. `details`
6. `extra`

### Duplicate handling

- First write wins
- If a key already exists, later values with the same key are ignored
- This matches the assumption that SmartCMP does not intentionally allow conflicting duplicate keys for the same logical property

### Practical implication

The first expansion should not attempt to force all resources into a strict common schema like `productVersion`, `backupEnabled`, `publicAccess`, and so on. Instead:

- keep the property bag broad
- let analyzers look for the keys that matter to them
- only add small helper accessors when repeated extraction logic becomes noisy

## Analyzer Families

### 1. Cloud analyzers

These evaluate cloud-resource configuration and exposure posture.

Examples:

- object storage
- compute instances
- network/security constructs
- load balancers
- managed databases

Initial target:

- `resource.iaas.storage.object.alicloud_oss_v2`

Typical findings:

- public access
- missing encryption
- missing versioning
- missing monitoring
- configuration exposure

### 2. Software analyzers

These evaluate installed or managed software products.

Initial targets:

- Tomcat
- MySQL
- PostgreSQL
- Redis
- Elasticsearch
- SQL Server

Typical findings:

- lifecycle status
- patch/compliance posture
- vulnerability exposure
- upgrade guidance

### 3. OS analyzers

These evaluate operating systems as first-class resource types.

Initial targets:

- Linux
- Windows

Typical findings:

- support/EOL posture
- missing patch evidence
- build/kernel risk
- advisory/CVE exposure

Linux and Windows are independent routing targets. They are no longer just inferred from other resources.

## Routing Model

### Primary routing

The main analyzer route is determined by `type`, which is `componentType`.

Examples:

- `resource.software.app.tomcat` -> Tomcat software analyzer
- `resource.iaas.storage.object.alicloud_oss_v2` -> OSS cloud analyzer
- Linux component type -> Linux OS analyzer
- Windows component type -> Windows OS analyzer

### Optional sidecar analyzers

Some resources may contain strong secondary signals in `properties`. For example:

- a software resource may expose host OS details
- a cloud host may expose installed software details

The framework may attach secondary analyzers when the evidence is strong, but the main route always comes from `type`.

## Findings Model

Every analyzer family must emit the same finding structure:

```json
{
  "technology": "tomcat",
  "analyzerType": "software",
  "findingType": "vulnerability",
  "status": "potentially_vulnerable",
  "severity": "high",
  "title": "Tomcat version is exposed to known security fixes",
  "evidence": [],
  "externalEvidence": "",
  "sourceLinks": [],
  "recommendation": "",
  "confidence": "high",
  "detectedFrom": "type+properties"
}
```

Recommended `findingType` values:

- `configuration`
- `lifecycle`
- `patch`
- `vulnerability`
- `exposure`
- `coverage`

Recommended status vocabulary:

- `compliant`
- `patched`
- `supported`
- `needs_review`
- `at_risk`
- `potentially_vulnerable`
- `confirmed_vulnerable`
- `non_compliant`

The exact mapping can remain conservative in the first implementation as long as the status set is stable and documented.

## Output Model

Each analyzed resource should return:

```json
{
  "resourceId": "ba9ffc56-4d57-4b43-acc8-53d89f24fa9e",
  "type": "resource.software.app.tomcat",
  "properties": {},
  "analysisTargets": ["software:tomcat"],
  "findings": [],
  "summary": {
    "overallRisk": "high",
    "overallCompliance": "non_compliant",
    "confidence": "high"
  },
  "uncertainties": []
}
```

The output wrapper should continue to support:

- `triggerSource`
- `requestedResourceIds`
- `analyzedCount`
- `failedCount`
- `generatedAt`

## Source Strategy

Use primary and authoritative sources whenever possible.

### Software and OS sources

- Apache Tomcat official security pages
- Oracle/MySQL official lifecycle and advisory pages
- Microsoft lifecycle and Security Update Guide / CVRF sources
- PostgreSQL official release/support/security information
- Redis official release/security references where available
- Elastic official security advisories and release notes
- Microsoft SQL Server lifecycle/security references
- Ubuntu, Red Hat, Debian, and other distribution advisory sources
- NVD as a supplement, not the primary Linux authority

### Cloud configuration sources

Prefer vendor documentation and security baselines for the specific cloud service. For AliCloud OSS, checks should align with official OSS documentation and security guidance.

## Live Examples Used During Design

The following real SmartCMP resources informed this design:

- Tomcat software resource:
  - `ba9ffc56-4d57-4b43-acc8-53d89f24fa9e`
  - `componentType = resource.software.app.tomcat`
  - version evidence includes `softwareVersion = 9.0.0.M10`
- AliCloud OSS resource:
  - `ac43ce78-917e-43e9-bc13-51e3f6e350c7`
  - `componentType = resource.iaas.storage.object.alicloud_oss_v2`
  - configuration evidence includes `permission`, `storage_class`, `encryption_algorithm`, and endpoints
- Previously validated MySQL and VM resources remain useful for regression coverage:
  - `e8d97ded-f821-4060-9924-c4ed21333742`
  - `d9124f83-3613-4a6f-aeae-7daef865e745`

The user also confirmed that Linux and Windows exist as independent SmartCMP component models:

- Linux blueprint component edit page:
  - `ed801c12-2562-4543-9a5c-2b32cc9f738b`
- Windows blueprint component edit page:
  - `c4061b48-df90-498e-88d6-644978caff42`

These should drive the OS analyzer design, while live runtime validation should still use real resource IDs when available.

## Backward Compatibility

The expansion should preserve the current user-facing entrypoint:

- keep `skills/resource-compliance/scripts/analyze_resource.py`
- keep `skills/shared/scripts/list_resource.py`
- keep direct-user and webhook-style invocation

The implementation may extend internal payloads and result structures, but it should avoid breaking the basic CLI contract:

- readable summary text
- machine-readable JSON metadata block

## Testing Strategy

Testing should cover:

- property aggregation from current SmartCMP payload layouts
- routing by `componentType`
- software analyzer behavior for Tomcat, MySQL, PostgreSQL, Redis, Elasticsearch, SQL Server
- OS analyzer behavior for Linux and Windows
- cloud analyzer behavior for AliCloud OSS
- conservative degradation when version/configuration evidence is incomplete
- real-environment smoke validation against representative resources

## Non-Goals For This Expansion

- automatic remediation
- maintaining a local vulnerability database
- perfectly normalized cross-resource property schema
- solving every SmartCMP resource type in the first pass
- finalizing webhook callback contracts beyond preserving the existing structured output pattern
