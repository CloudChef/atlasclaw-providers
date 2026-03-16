# Request Body Examples

## User Identification

Both Ticket and Cloud Resource requests support `userLoginId` (login ID):

| Request Type | Field | Format | Example |
|--------------|-------|--------|---------|
| **Ticket (GENERIC_SERVICE)** | `userLoginId` | Login ID | `"admin"` |
| **Cloud Resource (VM, etc.)** | `userLoginId` | Login ID | `"admin"` |

> **Note:** Both request types accept `userLoginId` parameter for simplicity.

---

## Ticket (GENERIC_SERVICE)

When `serviceCategory === "GENERIC_SERVICE"`:

```json
{
    "catalogName": "问题工单",
    "userLoginId": "admin",
    "businessGroupId": "f3ecaf5f-d86c-46fc-89d4-3636a169d5d5",
    "name": "加急工单",
    "genericRequest": {
        "description": "工单描述内容"
    }
}
```

| Field | Source | Required |
|-------|--------|----------|
| catalogName | CATALOG_META → name | Yes |
| userLoginId | Current user's login ID | Yes |
| businessGroupId | list_business_groups.py → user selection | Yes |
| name | User input | Yes |
| genericRequest.description | User input | Yes |

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
