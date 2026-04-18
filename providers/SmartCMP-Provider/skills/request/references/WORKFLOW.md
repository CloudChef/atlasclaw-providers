# Request Workflow Reference

Detailed step-by-step workflow for submitting requests to SmartCMP.

---

## Authoritative Flow

This section supersedes any later legacy mention of `list_components.py` in this file.

### Ticket Flow

```text
list_services
  -> select catalog
  -> list_business_groups
  -> collect ticket fields
  -> confirm
  -> submit
```

### Cloud Resource Flow

```text
list_services
  -> select catalog
  -> read instructions.node / instructions.type / instructions.osType silently
  -> list_business_groups (if requested by params)
  -> list_resource_pools (if requested by params)
  -> list_os_templates (if requested by params)
  -> list_images (if requested by params)
  -> collect remaining manual fields
  -> confirm
  -> submit
```

Rules:

1. `instructions.type` replaces the old component lookup and is the `nodeType` input for `list_resource_pools.py`.
2. `instructions.osType` is preferred for OS-template lookup; derive `Linux` or `Windows` only when `osType` is absent.
3. If a cloud catalog card is missing `instructions.node` or `instructions.type`, fix the catalog card. Do not bring back `list_components.py`.
4. Before the final submit step, always show a short summary plus `JSON 预览` with the constructed request body in a fenced `json` block, then ask `请确认以上信息是否正确？（是/否）`.
5. Mask preview secrets such as `credentialPassword` as `"******"` unless the user explicitly asks to reveal them.

---

## Prerequisites

Set environment variables before running any script:

```powershell
# PowerShell
$env:CMP_URL = "<your-cmp-host>"
$env:CMP_COOKIE = '<full cookie string>'

# Or use auto-login (recommended)
$env:CMP_URL = "<your-cmp-host>"
$env:CMP_USERNAME = "<username>"
$env:CMP_PASSWORD = "<password>"
```

```bash
# Bash
export CMP_URL="<your-cmp-host>"
export CMP_COOKIE="<full cookie string>"

# Or use auto-login (recommended)
export CMP_URL="<your-cmp-host>"
export CMP_USERNAME="<username>"
export CMP_PASSWORD="<password>"
```

---

## Dependency Chain (CRITICAL)

> **Before submitting any request, you MUST gather all required IDs in order.**

### Ticket Flow Dependencies

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TICKET SUBMISSION DEPENDENCY CHAIN               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  [1] list_services.py                                               │
│       │                                                             │
│       ├── Output: catalogId, catalogName, serviceCategory          │
│       │                                                             │
│       ▼                                                             │
│  [2] list_business_groups.py <catalogId>    ◄── REQUIRES catalogId │
│       │                                                             │
│       ├── Output: businessGroupId, businessGroupName                │
│       │                                                             │
│       ▼                                                             │
│  [3] submit.py --file request.json                                  │
│       │                                                             │
│       └── Request Body REQUIRES:                                    │
│           • catalogName     (from step 1)                           │
│           • userId          (UUID, NOT email)                       │
│           • businessGroupId (from step 2)                           │
│           • name            (user input)                            │
│           • genericRequest.description (user input)                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Cloud Resource Flow Dependencies

```
┌─────────────────────────────────────────────────────────────────────┐
│               CLOUD RESOURCE SUBMISSION DEPENDENCY CHAIN            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  [1] list_services.py                                               │
│       │                                                             │
│       ├── Output: catalogId, sourceKey, serviceCategory            │
│       │                                                             │
│       ▼                                                             │
│  [2] list_business_groups.py <catalogId>                            │
│       │                                                             │
│       ├── Output: businessGroupId                                   │
│       │                                                             │
│       ▼                                                             │
│  [3] read selected catalog instructions.type / node / osType        │
│       │                                                             │
│       ├── Output: embedded component metadata                        │
│       │                                                             │
│       ▼                                                             │
│  [4] list_resource_pools.py <businessGroupId> <sourceKey> <type>    │
│       │                                                             │
│       ├── Output: resourceBundleId, resourceBundleName              │
│       │                                                             │
│       ▼                                                             │
│  [5] list_os_templates.py <osType> <resourceBundleId>               │
│       │                                                             │
│       ├── Output: logicTemplateId, logicTemplateName                │
│       │                                                             │
│       ▼                                                             │
│  [6] submit.py --file request.json                                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Quick Reference: Required Inputs for Each Script

| Script | Required Input | Source |
|--------|----------------|--------|
| `list_services.py` | (none) | - |
| `list_business_groups.py` | `catalogId` | `list_services.py` output |
| `list_resource_pools.py` | `businessGroupId`, `sourceKey`, `nodeType` | Previous outputs |
| `list_os_templates.py` | `osType`, `resourceBundleId` | Previous outputs |
| `submit.py` | JSON file with all collected IDs | All above |

---

## Execution rules

| Rule | Description |
|------|-------------|
| ONE action per turn | After showing output or asking user, STOP and wait |
| NO temp files | Parse script output directly from stdout |
| NO output redirect | Never use `>`, `>>`, `2>&1` |
| NO guessing | Only use values from script outputs or user inputs |
| Always confirm | Show summary before submit, wait for user approval |
| Show JSON preview | Show the constructed request body in a fenced `json` block before asking for confirmation |

---

## Complete workflow diagram

```
[Start]
    ↓
[Step 1] list_services.py → Show list → STOP
    ↓
[User selects service]
    ↓
[Step 2] Check serviceCategory
    ↓
┌───────────────────────────────────────────────────┐
│  serviceCategory === "GENERIC_SERVICE"?           │
│    YES → Ticket Flow (Section A)                  │
│    NO  → Cloud Resource Flow (Section B)          │
└───────────────────────────────────────────────────┘
```

---

## Section A: Ticket flow (GENERIC_SERVICE)

```
[A1] list_business_groups.py → Show list → STOP
    ↓
[User selects business group]
    ↓
[A2] Ask for ticket name and description → STOP
    ↓
[User provides info]
    ↓
[A3] Build genericRequest JSON → Show summary → STOP
    ↓
[User confirms]
    ↓
[A4] submit.py → Show result → [End]
```

### A1: Get business groups

```bash
python ../shared/scripts/list_business_groups.py <catalogId>
```

Output:
```
Available business groups:

  [1] 业务组A
  [2] 业务组B

##BG_META_START##
[{"index":1,"id":"xxx","name":"业务组A"},...]
##BG_META_END##
```

**Ask:** "请选择业务组（输入编号）"  
**STOP.**

### A2: Collect ticket info

**Ask:**
```
请提供工单信息：
1. 工单名称：
2. 工单描述：
```

**STOP.**

### A3: Build and confirm

Build JSON:
```json
{
    "catalogName": "<from CATALOG_META>",
    "userId": "<current user ID>",
    "businessGroupId": "<from A1>",
    "name": "<from A2>",
    "genericRequest": {
        "description": "<from A2>"
    }
}
```

**Show summary:**
```
=== 工单申请确认 ===
服务名称: 问题工单
业务组: 业务组A
工单名称: xxx
工单描述: xxx
```

**Ask:** "请确认以上信息（输入 yes 提交，no 取消）"  
**STOP.**

### A4: Submit

```bash
python scripts/submit.py --file request.json
```

**Show result:**
```
提交成功！
Request ID: xxx
Status: INITIALING
```

---

## Section B: Cloud resource flow

```
[B1] Read selected catalog instructions (silent) → Record type, node, osType
    ↓
[B2] Parse description JSON → Determine required params
    ↓
[B3a] list_business_groups.py (if needed) → STOP
    ↓
[B3b] list_resource_pools.py (if needed) → STOP
    ↓
[B3c] list_os_templates.py (if needed) → STOP
    ↓
[B3d] Ask remaining required fields → STOP
    ↓
[B4] Build resourceSpecs JSON → Show summary → STOP
    ↓
[B5] submit.py → Show result → [End]
```

### B1: Read embedded component metadata (silent)

There is no `list_components.py` step in the refactored workflow.

Read the selected catalog instructions silently and record:
- `instructions.type` → request `type`
- `instructions.node` → request `node`
- `instructions.osType` → OS template lookup `osType`
- `instructions.cloudEntryTypeIds` → if explicitly empty, set `"useResourceBundle": false`

If `instructions.osType` is absent:
- derive `Windows` when `instructions.type` or `instructions.node` contains `windows`
- otherwise derive `Linux`

**Do NOT show this metadata to the user. Continue immediately.**

### B2: Parse description

The `description` field contains parameter definitions:

```json
{
  "parameters": [
    {"key": "businessGroupId", "source": "list:business_groups", "defaultValue": null},
    {"key": "cpu", "source": null, "defaultValue": 2},
    {"key": "name", "source": null, "defaultValue": null, "required": true}
  ]
}
```

**Decision table:**

| source | defaultValue | Action |
|--------|--------------|--------|
| `list:business_groups` | null | → B3a |
| `list:resource_pools` | null | → B3b |
| `list:os_templates` | null | → B3c |
| null | has value | Use default, skip asking |
| null | null + required | → B3d |

### B3a: Business group

```bash
python ../shared/scripts/list_business_groups.py <catalogId>
```

**Ask:** "请选择业务组"  
**STOP.**

### B3b: Resource pool

```bash
python ../shared/scripts/list_resource_pools.py <businessGroupId> <sourceKey> <nodeType>
```

Arguments:
- `businessGroupId`: from B3a
- `sourceKey`: from CATALOG_META
- `nodeType`: from selected catalog `instructions.type`

**Ask:** "请选择资源池"  
**STOP.**

### B3c: OS template

```bash
python ../shared/scripts/list_os_templates.py <osType> <resourceBundleId>
```

Arguments:
- `osType`: from selected catalog `instructions.osType`, or derived from selected catalog `instructions.type`
- `resourceBundleId`: from B3b

**Ask:** "请选择操作系统模板"  
**STOP.**

### B3d: Other required fields

**Ask:**
```
请提供以下信息：
1. 资源名称：
2. [其他必填字段]
```

**STOP.**

### B4: Build and confirm

**Key rules for building request body:**

1. `type` = selected catalog `instructions.type`
2. `node` = selected catalog `instructions.node`
3. If `cloudEntryTypeIds` is empty string → Add `"useResourceBundle": false`

Build JSON:
```json
{
  "name": "<from B3d>",
  "catalogName": "<from CATALOG_META>",
  "businessGroupName": "<from B3a>",
  "userLoginId": "admin",
  "resourceSpecs": [
    {
      "useResourceBundle": false,
      "node": "<node from selected catalog instructions>",
      "type": "<type from selected catalog instructions>",
      "params": {
        "<param_key>": "<param_value from description or user>"
      }
    }
  ]
}
```

**Example (机房 service):**
```json
{
  "catalogName": "机房",
  "userLoginId": "admin",
  "businessGroupName": "我的业务组",
  "name": "机房222",
  "resourceSpecs": [
    {
      "useResourceBundle": false,
      "node": "server_room",
      "type": "resource.infra.server_room",
      "params": {
        "infra_brand": "111",
        "maintenance_phone_number": "232323"
      }
    }
  ]
}
```

**Example (VM with resource bundle):**
```json
{
  "name": "my-linux-vm",
  "catalogName": "Linux VM",
  "businessGroupName": "开发组",
  "userLoginId": "admin",
  "resourceBundleName": "开发资源池",
  "resourceSpecs": [
    {
      "type": "cloudchef.nodes.Compute",
      "node": "Compute",
      "cpu": 4,
      "memory": 8192,
      "logicTemplateName": "CentOS 7.9"
    }
  ]
}
```

**Show summary and ask for confirmation.**  
**STOP.**

### B5: Submit

```bash
python scripts/submit.py --file request.json
```

**Show result.**

---

## Script quick reference

| Script | Args | Returns |
|--------|------|---------|
| `list_services.py` | `[keyword]` | catalogId, name, sourceKey, serviceCategory |
| `list_business_groups.py` | `<catalogId>` | businessGroupId, name |
| `list_resource_pools.py` | `<bgId> <sourceKey> <nodeType>` | resourceBundleId, name |
| `list_os_templates.py` | `<osType> <rbId>` | logicTemplateId, name |
| `submit.py` | `--file <json>` | requestId, state |

---

## Error handling

| Error | Action |
|-------|--------|
| Empty description | Show message, ask user for guidance |
| HTTP 401 | Token expired, ask user to refresh CMP_COOKIE |
| Script error | Show error message to user, do not retry |
