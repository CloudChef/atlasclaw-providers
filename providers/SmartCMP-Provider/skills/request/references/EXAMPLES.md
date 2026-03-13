# Request Body Examples

## User Identification (userId vs userLoginId)

> **CRITICAL:** Ticket and Cloud Resource requests use DIFFERENT user fields!

| Request Type | Field | Format | Example |
|--------------|-------|--------|---------|
| **Ticket (GENERIC_SERVICE)** | `userId` | UUID | `"afe5251b-1d72-49ce-babe-5b8563b7b947"` |
| **Cloud Resource (VM, etc.)** | `userLoginId` | Email/Login ID | `"admin"` or `"user@example.com"` |

**Why the difference?**
- Ticket API requires internal user UUID for tracking
- Cloud Resource API accepts login identifier for flexibility

**How to get userId:**
- From previous approval list: `applicant` field in `##APPROVAL_META##`
- From BG_META response: often included in business group context
- From session context: current authenticated user's UUID

---

## Ticket (GENERIC_SERVICE)

When `serviceCategory === "GENERIC_SERVICE"`:

```json
{
    "catalogName": "问题工单",
    "userId": "afe5251b-1d72-49ce-babe-5b8563b7b947",
    "businessGroupId": "f3ecaf5f-d86c-46fc-89d4-3636a169d5d5",
    "name": "加急工单",
    "manualRequest": {
        "description": "工单描述内容"
    }
}
```

| Field | Source | Required |
|-------|--------|----------|
| catalogName | CATALOG_META → name | Yes |
| **userId** | **UUID format** (NOT email) | **Yes** |
| businessGroupId | list_business_groups.py → user selection | Yes |
| name | User input | Yes |
| manualRequest.description | User input | Yes |

> **WARNING:** Using `userLoginId` instead of `userId` will fail with error:  
> `"Missing argument:userId or userLoginId"`  
> Despite the error message, only `userId` (UUID) works for tickets!

---

## Cloud Resource (VM)

When `serviceCategory` is NOT `GENERIC_SERVICE`:

```json
{
  "name": "my-linux-vm",
  "catalogName": "Linux VM",
  "businessGroupName": "我的业务组",
  "userLoginId": "admin",
  "resourceBundleName": "Vsphere资源池",
  "resourceSpecs": [
    {
      "type": "cloudchef.nodes.Compute",
      "node": "Compute",
      "cpu": 1,
      "memory": 1,
      "logicTemplateName": "CentOS",
      "templateId": "vm-551",
      "networkId": "network-18963"
    }
  ]
}
```

| Field | Source |
|-------|--------|
| name | User input |
| catalogName | CATALOG_META → name |
| businessGroupName | list_business_groups.py → user selection |
| resourceBundleName | list_resource_pools.py → user selection |
| type | list_components.py → typeName |
| cpu, memory, networkId | description JSON → defaultValue |
| logicTemplateName | list_os_templates.py → user selection |
| templateId | list_images.py → user selection (private cloud) |

---

## Field placement rules

| Location | Fields |
|----------|--------|
| Top-level | name, catalogName, businessGroupName, userLoginId, resourceBundleName |
| Inside resourceSpecs[] | type, node, cpu, memory, logicTemplateName, templateId, networkId |

---

## WRONG (DO NOT USE)

```json
{
  "catalogId": "xxx",
  "businessGroupId": "xxx",
  "cpu": 1,
  "memory": 1
}
```

**Why wrong:** 
- VM fields (cpu, memory) must be inside `resourceSpecs[]`, not top-level
- Use `catalogName` not `catalogId` (unless API specifically requires ID)
