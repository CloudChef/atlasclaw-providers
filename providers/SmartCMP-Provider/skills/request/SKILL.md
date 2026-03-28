---
name: "request"
description: "Self-service request skill. Request cloud resources, application environments, or ticket/work order services. Keywords: request, provision, deploy, create VM, apply resources, submit ticket, 申请资源, 创建虚拟机, 提交工单."
provider_type: "smartcmp"
instance_required: "true"

# === LLM Context Fields ===
triggers:
  - create VM
  - provision resources
  - deploy application
  - request cloud
  - new virtual machine
  - 申请资源
  - 创建虚拟机
  - 提交工单
  - 申请机房
  - 申请服务

use_when:
  - User wants to request a VM, cloud resource, database, or application environment
  - User wants to submit a self-service request through the service catalog
  - User wants to create a ticket or work order
  - User already knows the service they want and is ready to provide request parameters

avoid_when:
  - User only wants to browse available resources (use datasource skill)
  - User wants to approve or reject requests (use approval skill)
  - User describes requirements in natural language without specific parameters (use request-decomposition-agent)

examples:
  - "Create a new VM with 4 CPU and 8GB RAM"
  - "Provision cloud resources for my project"
  - "Deploy a Linux VM in production environment"
  - "Submit a request for 3 virtual machines"
  - "提交一个问题工单"
  - "申请一个机房资源"

related:
  - datasource
  - approval
  - request-decomposition-agent

# === Tool Registration ===
tool_list_services_name: "smartcmp_list_services"
tool_list_services_description: "List available service catalogs from SmartCMP."
tool_list_services_entrypoint: "../shared/scripts/list_services.py"
tool_list_business_groups_name: "smartcmp_list_business_groups"
tool_list_business_groups_description: "List business groups for a catalog. Use when user needs to select business group."
tool_list_business_groups_entrypoint: "../shared/scripts/list_business_groups.py"
tool_list_resource_pools_name: "smartcmp_list_resource_pools"
tool_list_resource_pools_description: "List resource pools. Get resourceBundleId for request."
tool_list_resource_pools_entrypoint: "../shared/scripts/list_resource_pools.py"
tool_list_os_templates_name: "smartcmp_list_os_templates"
tool_list_os_templates_description: "List OS templates for VM provisioning."
tool_list_os_templates_entrypoint: "../shared/scripts/list_os_templates.py"
tool_list_components_name: "smartcmp_list_components"
tool_list_components_description: "Get component type info including typeName, node, cloudEntryTypeIds."
tool_list_components_entrypoint: "../shared/scripts/list_components.py"
tool_submit_name: "smartcmp_submit_request"
tool_submit_description: "Submit resource request to SmartCMP."
tool_submit_entrypoint: "scripts/submit.py"
---

# request

Submit cloud resource, application environment, or ticket/work order requests through the service catalog.

---

## Workflow Overview

```
[Trigger] User expresses intent to "request resources"
    |
    v
[Step 1] Execute list_services.py -> Display service list -> STOP wait for user selection
    |
    v
[Step 2] User selects service -> Check serviceCategory field
    |
    +---> serviceCategory === "GENERIC_SERVICE" ---> [Ticket Flow]
    |
    +---> serviceCategory !== "GENERIC_SERVICE" ---> [Cloud Resource Flow]
```

---

## Step 1: List Available Services [Execute]

```bash
python ../shared/scripts/list_services.py
```

**Output Example:**
```
Found 3 published catalog(s):

  [1] Linux VM
  [2] Issue Ticket
  [3] Server Room

##CATALOG_META_START##
[{"index":1,"id":"xxx","name":"Linux VM","sourceKey":"resource.iaas...","serviceCategory":"VM","description":"..."},
 {"index":2,"id":"yyy","name":"Issue Ticket","sourceKey":"...","serviceCategory":"GENERIC_SERVICE","description":"..."},
 {"index":3,"id":"zzz","name":"Server Room","sourceKey":"resource.infra.server_room","serviceCategory":"RESOURCE","description":"..."}]
##CATALOG_META_END##
```

**Action:** Display numbered list to user, ask: "Please select the service you want to request (enter number)"

**STOP - Wait for user input**

---

## Step 2: Determine Service Type [Decision]

After user selection, find the corresponding item from `##CATALOG_META##` and check `serviceCategory` field:

| serviceCategory Value | Service Type | Flow |
|----------------------|--------------|------|
| `GENERIC_SERVICE` | Ticket/Manual Request | [Ticket Flow](#ticket-flow-generic_service) |
| Any other value | Cloud Resource | [Cloud Resource Flow](#cloud-resource-flow) |

---

## Ticket Flow (GENERIC_SERVICE)

Use this flow when `serviceCategory === "GENERIC_SERVICE"`.

### T1: Get Business Groups [Execute]

```bash
python ../shared/scripts/list_business_groups.py <catalogId>
```

**Action:** Display business group list, ask: "Please select a business group"

**STOP - Wait for user selection**

### T2: Collect Ticket Info [Ask]

Ask user:
```
Please provide the following information:
1. Ticket name:
2. Ticket description:
```

**STOP - Wait for user input**

### T3: Build Request Body [Build]

```json
{
    "catalogName": "<name from CATALOG_META>",
    "userLoginId": "<current user login ID>",
    "businessGroupId": "<from T1 selection>",
    "name": "<from T2 user input>",
    "genericRequest": {
        "description": "<from T2 user input>"
    }
}
```

**Action:** Display confirmation to user, ask: "Please confirm if the above information is correct? (yes/no)"

**STOP - Wait for user confirmation**

### T4: Submit [Execute]

```bash
python scripts/submit.py --file request.json
```

**Complete** - Display request ID and status to user.

---

## Cloud Resource Flow

Use this flow when `serviceCategory !== "GENERIC_SERVICE"`.

### Cloud Resource Flow Decision Tree

```
[R1] Get component info (list_components.py)
    |
    v
[R2] Check cloudEntryTypeIds
    |
    +---> cloudEntryTypeIds is empty ("") ---> Path A: No resource pool needed
    |                                          Set useResourceBundle: false
    |                                          Skip resource pool selection
    |
    +---> cloudEntryTypeIds not empty ---> [R3] Check description config
                                               |
                                               +---> description empty/invalid ---> Path B: Must select resource pool
                                               |                                    Execute list_resource_pools.py
                                               |                                    Let user select resource pool
                                               |
                                               +---> description valid ---> [R4] Check resource pool config
                                                                                |
                                                                                +---> Has default pool ---> Path C: Use default pool
                                                                                |     (resourceBundleName/Id has defaultValue)
                                                                                |     No user selection needed
                                                                                |
                                                                                +---> No default pool ---> Path D: Need to select pool
                                                                                      (source: "list:resource_pools")
                                                                                      Execute list_resource_pools.py
                                                                                      Let user select resource pool
```

### Resource Pool Decision Summary

| Scenario | cloudEntryTypeIds | description | Pool Config | Action |
|----------|-------------------|-------------|-------------|--------|
| **Path A** | Empty `""` | Any | - | `useResourceBundle: false`, no pool needed |
| **Path B** | Not empty | Empty/Invalid | - | **Must** query pool for user selection |
| **Path C** | Not empty | Valid | Has default | Use default pool, no user selection |
| **Path D** | Not empty | Valid | No default | Query pool for user selection |

---

### R1: Get Component Info [Silent Execute]

```bash
python ../shared/scripts/list_components.py <sourceKey>
```

**Output Example:**
```
##COMPONENT_META_START##
{"sourceKey":"resource.infra.server_room","typeName":"resource.infra.server_room","id":"xxx","name":"Server Room","node":"server_room","cloudEntryTypeIds":""}
##COMPONENT_META_END##
```

**Key Fields:**

| Field | Purpose | Example |
|-------|---------|---------|
| `typeName` | For `type` field in request body | `resource.infra.server_room` |
| `node` | For `node` field in request body | `server_room` |
| `cloudEntryTypeIds` | **Resource pool requirement indicator** | `""` or `"yacmp:cloudentry:type:..."` |

**Note:** This step executes silently, do not display to user, proceed to next step directly.

---

### R2: Determine Resource Pool Requirement [Silent Decision]

Determine resource pool requirement based on `cloudEntryTypeIds` value:

```
IF cloudEntryTypeIds === "" (empty string)
    THEN needResourcePool = false
         useResourceBundle = false
    GOTO R4 (skip resource pool related steps)

ELSE (cloudEntryTypeIds not empty)
    THEN needResourcePool = true (preliminary)
    GOTO R3 (continue checking description config)
```

---

### R3: Parse Service Card Description [Silent Analysis]

Parse parameter definitions from `description` field in `##CATALOG_META##`.

#### Scenario 1: description empty or invalid JSON (Path B)

```
IF description is empty OR description is not valid JSON
    AND cloudEntryTypeIds not empty
THEN
    Must execute list_resource_pools.py for user selection
    needUserSelectResourcePool = true
```

#### Scenario 2: description is valid JSON

Parse `parameters` array, look for resource pool related config:

```json
{
  "parameters": [
    {"key": "businessGroupId", "source": "list:business_groups", "defaultValue": null, "required": true},
    {"key": "resourceBundleName", "source": "list:resource_pools", "defaultValue": "Default Pool", "required": true},
    {"key": "cpu", "source": null, "defaultValue": 2, "required": true}
  ]
}
```

**Resource Pool Config Check Rules:**

| Check | Condition | Result |
|-------|-----------|--------|
| Has default pool (Path C) | `key` is `resourceBundleName`/`resourceBundleId` AND `defaultValue` has value | `needUserSelectResourcePool = false` |
| Need pool selection (Path D) | `key` is `resourceBundleName`/`resourceBundleId` AND `source: "list:resource_pools"` AND `defaultValue` is null | `needUserSelectResourcePool = true` |
| No pool param configured | No pool related field in `parameters`, but `cloudEntryTypeIds` not empty | `needUserSelectResourcePool = true` (fallback to Path B) |

**Other Parameter Handling Rules:**

| Condition | Action |
|-----------|--------|
| `defaultValue` has value | Use default, don't ask user |
| `source: "list:business_groups"` | Execute `list_business_groups.py` -> Ask user to select |
| `source: "list:resource_pools"` with no default | Execute `list_resource_pools.py` -> Ask user to select |
| `source: "list:os_templates"` | Execute `list_os_templates.py` -> Ask user to select |
| `source: null` AND `required: true` | Ask user for input |
| `source: null` AND `required: false` | Skip (optional parameter) |

---

### R4: Collect Parameters Step by Step

Based on R2/R3 analysis results, collect parameters step by step:

**R4a: Business Group** (always required)
```bash
python ../shared/scripts/list_business_groups.py <catalogId>
```
Display list, ask user to select. **STOP**

**R4b: Resource Pool** (conditional)

```
IF needUserSelectResourcePool === true (Path B or Path D)
THEN execute:
```

```bash
python ../shared/scripts/list_resource_pools.py <businessGroupId> <sourceKey> <typeName>
```

Display list, ask user to select. **STOP**

```
ELSE IF useResourceBundle === false (Path A)
THEN skip this step

ELSE IF has default pool (Path C)
THEN use default value, skip this step
```

**R4c: OS Template** (if needed)
```bash
python ../shared/scripts/list_os_templates.py <osType> <resourceBundleId>
```
Display list, ask user to select. **STOP**

**R4d: Other Required Fields**
Ask user to input remaining required fields (e.g., resource name). **STOP**

---

### R5: Build Request Body [Build]

**Core Rules (Very Important):**

1. `type` = complete `typeName` (from R1)
2. `node` = last segment after the last dot in `typeName` (from R1's `node` field)
3. Resource pool handling:
   - **Path A** (cloudEntryTypeIds empty): Add `"useResourceBundle": false`, no resourceBundleName
   - **Path B/C/D** (cloudEntryTypeIds not empty): Must add `resourceBundleName`

**Request Body Example - Path A (No Resource Pool):**

```json
{
    "catalogName": "Server Room",
    "userLoginId": "admin",
    "businessGroupName": "My Business Group",
    "name": "server-room-222",
    "resourceSpecs": [
        {
            "useResourceBundle": false,
            "node": "server_room",
            "type": "resource.infra.server_room",
            "params": {
                "infra_brand": "111"
            }
        }
    ]
}
```

**Request Body Example - Path B/C/D (Resource Pool Required):**

```json
{
    "catalogName": "VPC Service",
    "userLoginId": "admin",
    "businessGroupName": "My Business Group",
    "resourceBundleName": "ResourcePool for Test",
    "name": "vpc-001",
    "resourceSpecs": [
        {
            "node": "testvpc",
            "type": "resource.iaas.network.network.testvpc",
            "params": {}
        }
    ]
}
```

**Field Mapping:**

| Request Field | Data Source | Applicable Path |
|---------------|-------------|-----------------|
| `catalogName` | `name` from CATALOG_META | All |
| `userLoginId` | Current user login ID | All |
| `businessGroupName` | Business group name from R4a | All |
| `resourceBundleName` | User selection or default from R4b | B/C/D |
| `name` | Resource name from R4d user input | All |
| `resourceSpecs[0].type` | `typeName` from R1 | All |
| `resourceSpecs[0].node` | `node` from R1 | All |
| `resourceSpecs[0].useResourceBundle` | Only set to `false` for Path A | A |
| `resourceSpecs[0].params` | Other params collected in R4d | All |

**Action:** Display confirmation to user, ask: "Please confirm if the above information is correct? (yes/no)"

**STOP - Wait for user confirmation**

---

### R6: Submit [Execute]

```bash
python scripts/submit.py --file request.json
```

**Complete** - Display request ID and status to user.

---

## No Description Handling (Path B Details)

When `description` field is empty or invalid JSON, but `cloudEntryTypeIds` is not empty:

1. **Do not stop the flow**, continue execution
2. **Must query resource pool** for user selection:
   ```bash
   python ../shared/scripts/list_resource_pools.py <businessGroupId> <sourceKey> <typeName>
   ```
3. Collect basic required fields: business group, resource pool, resource name
4. Build request body and submit

> **Note:** Only prompt user to contact administrator for service card configuration when `cloudEntryTypeIds` is also empty.

---

## Scripts Reference

| Script | Purpose | Parameters |
|--------|---------|------------|
| `../shared/scripts/list_services.py` | List service catalogs | `[keyword]` |
| `../shared/scripts/list_business_groups.py` | List business groups | `<catalogId>` |
| `../shared/scripts/list_resource_pools.py` | List resource pools | `<bgId> <sourceKey> <nodeType>` |
| `../shared/scripts/list_os_templates.py` | List OS templates | `<osType> <resourceBundleId>` |
| `../shared/scripts/list_components.py` | Get component type info | `<sourceKey>` |
| `scripts/submit.py` | Submit request | `--file <json_file>` |

---

## Critical Rules

1. **Execute only one action per turn.** After displaying output or asking question, MUST STOP and wait for user response.
2. **Never fabricate data.** Only use values from script output or user input.
3. **Never skip steps.** Strictly follow the workflow.
4. **Never auto-submit.** Must get user confirmation before submission.
5. **Set node and type correctly.** `type` = complete typeName, `node` = last segment of typeName.
6. **Resource pool decision rules (Very Important):**
   - `cloudEntryTypeIds` empty -> `useResourceBundle: false`, no pool needed
   - `cloudEntryTypeIds` not empty + `description` empty -> **Must** query pool for user selection
   - `cloudEntryTypeIds` not empty + has default pool config -> Use default, no user selection
   - `cloudEntryTypeIds` not empty + no default pool -> Query pool for user selection
7. **resourceBundleName required:** When `cloudEntryTypeIds` is not empty, request body top level **must** include `resourceBundleName` field.

---

## PowerShell Environment Notes

> **Important:** PowerShell encoding and parameter passing may cause request failures.

### Use Python to Write JSON Files (Avoid BOM)

```powershell
# [Wrong] PowerShell adds BOM
$body | ConvertTo-Json | Out-File -FilePath request.json -Encoding utf8

# [Correct] Use Python to write JSON
python -c "import json; data = {...}; open('request.json', 'w', encoding='utf-8').write(json.dumps(data, ensure_ascii=False, indent=2))"
```

### Always Use --file Parameter

```powershell
# [Wrong] JSON will be corrupted
python submit.py --json '{"name": "test"}'

# [Correct] Use file input
python submit.py --file request.json
```

---

## References

- [WORKFLOW.md](references/WORKFLOW.md) - Detailed step-by-step workflow
- [PARAMS.md](references/PARAMS.md) - Parameter placement rules
- [EXAMPLES.md](references/EXAMPLES.md) - Request body examples
