# Datasource Workflow Reference

Detailed reference for querying SmartCMP data sources.

---

## Setup (once per session)

```powershell
$env:CMP_URL = "https://<host>/platform-api"
$env:CMP_COOKIE = '<full cookie string>'   # MUST use single quotes
```

---

## Execution Rules

1. **Run scripts in sequence** — each script's output is input for the next.
2. **STOP on any error** — if script prints `[ERROR]`, report to user immediately.
3. **Never retry blindly** — ask user to fix environment before retrying.
4. **Cookie refresh** — if `401` or `token expired`, tell user to re-login.
5. **Network error** — if timeout, ask user to check network access.

---

## Scripts Reference

### 1. List service catalogs

```bash
python ../shared/scripts/list_services.py
python ../shared/scripts/list_services.py <KEYWORD>   # filter by name
```

Output: numbered list of catalog names.
`##CATALOG_META##` block contains `{id, sourceKey, description}` — parse silently.

**Trigger**: "查看服务目录" / "show catalogs"

---

### 2. List business groups

```bash
python ../shared/scripts/list_business_groups.py <CATALOG_ID>
```

Output: numbered list of business groups for the given catalog.

**Trigger**: "这个服务有哪些业务组" / "list BGs for catalog X"

---

### 3. Get component type

```bash
python ../shared/scripts/list_components.py <SOURCE_KEY>
```

Output: `##COMPONENT_META##` block with `typeName` (= model.typeName).

**Trigger**: Required before resource pools or OS templates.

---

### 4. List resource pools

**IMPORTANT: nodeType is REQUIRED for correct filtering.**

```bash
python ../shared/scripts/list_resource_pools.py <BG_ID> <SOURCE_KEY> <NODE_TYPE>
```

- `BG_ID` = businessGroupId from step 2
- `SOURCE_KEY` = sourceKey from step 1
- `NODE_TYPE` = **typeName from step 3** (e.g. `cloudchef.nodes.Compute`)

**Example:**
```bash
python ../shared/scripts/list_resource_pools.py \
  47673d8d-6b3f-41e1-8ec0-c37e082d9020 \
  resource.iaas.machine.instance.abstract \
  cloudchef.nodes.Compute
```

Output: numbered list with `##RESOURCE_POOL_META##` block containing `cloudEntryTypeId`.

> **WARNING**: If NODE_TYPE is omitted, the API may return incomplete or incorrect results.

**Trigger**: "有哪些资源池" / "list resource pools"

---

### 5. List applications

```bash
python ../shared/scripts/list_applications.py <BG_ID>
```

Output: numbered list of applications in the business group.

**Trigger**: "有哪些应用系统" / "list applications"

---

### 6. List OS templates (VM only)

**Pre-flight checks:**
1. `sourceKey.lower()` contains `"machine"` → continue; else STOP
2. `typeName.lower()` contains `"windows"` → osType = Windows; else Linux

```bash
python ../shared/scripts/list_os_templates.py <OS_TYPE> <RESOURCE_BUNDLE_ID>
```

**Trigger**: "有哪些操作系统" / "list OS templates"

---

### 7. List cloud entry types

```bash
python ../shared/scripts/list_cloud_entry_types.py
```

Output: `##CLOUD_ENTRY_TYPES_META##` with `group` (PUBLIC_CLOUD | PRIVATE_CLOUD).

**Trigger**: Before image queries to check cloud type.

---

### 8. List images (private cloud only)

**Pre-flight:**
1. Run `list_cloud_entry_types.py` silently
2. Match `cloudEntryTypeId` → if PUBLIC_CLOUD, tell user not supported

```bash
python ../shared/scripts/list_images.py <RB_ID> <LT_ID> <CLOUD_ENTRY_TYPE_ID>
```

**Trigger**: "有哪些镜像" / "list images" (private cloud only)

---

### 9. List resource details by ID

```bash
python ../shared/scripts/list_resource.py <RESOURCE_ID> [RESOURCE_ID ...]
```

Output: summary lines plus `##RESOURCE_META_START## ... ##RESOURCE_META_END##`

**Trigger**: "show resource details" / "按资源ID查看详情"

---

## Typical Query Flows

| User Intent | Script Sequence |
|-------------|-----------------|
| "查看服务目录" | `list_services.py` |
| "XX服务有哪些业务组" | `list_services.py` → `list_business_groups.py <catalogId>` |
| "XX业务组有哪些应用" | `list_applications.py <bgId>` |
| "XX业务组有哪些资源池" | `list_components.py` → `list_resource_pools.py <bgId> <sourceKey> <nodeType>` |
| "有哪些操作系统" | Pre-flight check → `list_os_templates.py <osType> <rbId>` |
| "有哪些镜像" | `list_cloud_entry_types.py` → `list_images.py <rbId> <ltId> <cloudEntryTypeId>` |
| "查看资源详情" | `list_resource.py <resourceId>` |

---

## Notes

- All scripts are **read-only** — no data is modified.
- Scripts are **shared** with the request skill.
- Always parse `##BLOCK##` markers silently, do NOT display raw JSON to user.
