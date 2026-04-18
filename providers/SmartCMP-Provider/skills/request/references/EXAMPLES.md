# Request Body Examples

## Authoritative note

These examples use the refactored flow where cloud catalog cards already embed:

- `instructions.node`
- `instructions.type`
- optional `instructions.osType`

`list_components.py` is not part of these examples.

---

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
    "catalogId": "1c3872cc-3dcd-422a-b110-5596aa04d051",
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
| catalogId | CATALOG_META → id | Recommended |
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
  "catalogId": "BUILD-IN-CATALOG-LINUX-VM",
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
| catalogId | CATALOG_META → id |
| catalogName | CATALOG_META → name |
| businessGroupName | list_business_groups.py → user selection |
| resourceBundleName | selected catalog params → defaultValue, or list_resource_pools.py → user selection when the param explicitly requires a lookup |
| type | selected catalog instructions → type |
| cpu, memory, networkId | selected catalog params → defaultValue |
| logicTemplateName | selected catalog params → defaultValue, or list_os_templates.py → user selection when the param explicitly requires a lookup |
| templateId | selected catalog params → defaultValue, or list_images.py → user selection when the param explicitly requires a lookup |

---

## Suggested Confirmation Display

Show the user both a readable summary and the constructed request JSON before submit.

```text
Linux VM 配置确认：
- 业务组：我的业务组
- 资源名称：mysql-vm-2

JSON 预览
```json
{
  "catalogId": "BUILD-IN-CATALOG-LINUX-VM",
  "catalogName": "Linux VM",
  "userLoginId": "admin",
  "businessGroupName": "我的业务组",
  "resourceBundleName": "vsphere资源池",
  "name": "mysql-vm-2",
  "resourceSpecs": [
    {
      "type": "cloudchef.nodes.Compute",
      "node": "Compute",
      "cpu": 1,
      "memory": 1,
      "logicTemplateName": "CentOS",
      "templateId": "vm-551",
      "networkId": "network-18963",
      "credentialUser": "root",
      "credentialPassword": "******"
    }
  ]
}
```

请确认以上信息是否正确？（是/否）
```

---

## Field placement rules

| Location | Fields |
|----------|--------|
| Top-level | name, catalogId, catalogName, businessGroupName, userLoginId, resourceBundleName |
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
- A valid cloud request should preserve selected catalog metadata and usually carry both `catalogId` and `catalogName`
