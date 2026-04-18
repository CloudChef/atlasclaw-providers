# Parameter Placement Reference

## Authoritative rule

For cloud requests:

- `resourceSpecs[0].node` must come from selected catalog `instructions.node`
- `resourceSpecs[0].type` must come from selected catalog `instructions.type`
- lookup `nodeType` for resource pools must use selected catalog `instructions.type`
- do not use `list_components.py` to populate these values

---

## Field locations in request body

| Field | Location |
|-------|----------|
| `catalogId` / `catalogName` | top-level |
| `businessGroupId` / `businessGroupName` | top-level |
| `userLoginId` | top-level |
| `resourceBundleId` / `resourceBundleName` | **top-level** (NOT inside resourceSpecs) |
| `name`, `count`, `projectId` / `projectName` | top-level |
| `type`, `node` | **inside resourceSpecs** (required) |
| `computeProfileId` / `computeProfileName` | **inside resourceSpecs** (NOT top-level) |
| `cpu`, `memory` (GB) | inside resourceSpecs |
| `logicTemplateId` / `logicTemplateName` / `templateId` | inside resourceSpecs |
| `networkId` / `networkName`, `subnetId` / `subnetName` | inside resourceSpecs |
| `systemDisk`, `dataDisks` | inside resourceSpecs |
| `imageId` / `imageName` | inside resourceSpecs |

**VM `type` field:**
- Prefer the selected catalog `instructions.type`
- Typical examples are `cloudchef.nodes.Compute` and `cloudchef.nodes.WindowsCompute`

**Memory unit:** always GB (e.g. "2c4g" → `cpu: 2, memory: 4`)

---

## Cloud-specific extra params

| Cloud | Extra params |
|-------|-------------|
| Azure | `params: { "resource_group_name": "xx", "storage_account": "xx" }` |
| Aliyun | `resourceBundleParams: { "available_zone_id": "xx" }`, `params: { "v_switch_id": "xx" }` |
| vSphere | `systemDisk.volume_type` = datastore ID (e.g. `datastore-350`) |

---

## Track / Cancel

```
GET  {CMP_URL}/generic-request/{id}          # INITIALING → STARTED → TASK_RUNNING → FINISHED/FAILED
POST {CMP_URL}/generic-request/{id}/cancel
```
