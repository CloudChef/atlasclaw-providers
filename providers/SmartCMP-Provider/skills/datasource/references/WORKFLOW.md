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

### 1. List business-group scopes

Treat SmartCMP business groups as a flexible organizational scope. User wording
such as tenant, 租户, 部门, BU, Department, 项目, or Project should be resolved
through this same directory flow unless the context clearly refers to another
tenant system.

```bash
python scripts/list_all_business_groups.py
python scripts/list_all_business_groups.py <KEYWORD>   # filter by name
```

Output: numbered list of business-group names.
`##BUSINESS_GROUP_DIRECTORY_META##` block contains `{id, name, code}` - parse silently.

**Trigger**: "查看业务组" / "查看租户" / "查看部门" / "查看项目" / "show tenants"

---

### 2. List service catalogs

```bash
python scripts/list_services.py
python scripts/list_services.py <KEYWORD>   # filter by name
```

Output: numbered list of catalog names.
`##CATALOG_META##` block contains `{id, sourceKey, description}` — parse silently.

**Trigger**: "查看服务目录" / "show catalogs"

---

### 3. List resource details by ID

```bash
python scripts/list_resource.py <RESOURCE_ID> [RESOURCE_ID ...]
```

Output: summary lines plus `##RESOURCE_META_START## ... ##RESOURCE_META_END##`

Specific resource evidence comes from `PATCH /nodes/{resourceId}/view` first.
This is a temporary SmartCMP API compatibility behavior; switch back to GET
after the CMP API bug is fixed. `resource.data` is the canonical JSON evidence
pack. If `/view` fails or returns no data, fallback to `GET /nodes/{resourceId}`
and `GET /nodes/{resourceId}/details`. If fallback provides resource data, keep
`fetchStatus=ok`, set `fallbackUsed=true`, and preserve the primary `/view`
error. If both primary and fallback paths fail, the output must expose
`fetchStatus=error` and `missingEvidence=["resource.data"]`.

**Trigger**: "show resource details" / "按资源ID查看详情"

---

## Typical Query Flows

| User Intent | Script Sequence |
|-------------|-----------------|
| "查看业务组 / 查看租户 / 查看部门 / 查看项目" | `scripts/list_all_business_groups.py [keyword]` |
| "查看服务目录" | `scripts/list_services.py` |
| "查看资源详情" | `scripts/list_resource.py <resourceId>` |
| "查看应用" | `../shared/scripts/list_applications.py <businessGroupId>` |
| "查看组件 / 模板元数据" | `../shared/scripts/list_components.py <sourceKey>` |
| "查看镜像" | `../shared/scripts/list_images.py <resourceBundleId> <logicTemplateId> <cloudEntryType>` |

---

## Notes

- All scripts are **read-only** — no data is modified.
- Scripts are **shared** with the request skill.
- Standalone business-group scope discovery is owned by `datasource`.
- Always parse `##BLOCK##` markers silently, do NOT display raw JSON to user.
