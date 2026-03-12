---
name: "request"
description: "SmartCMP resource request. Create VM, provision cloud resources, deploy applications."
---

# request

Provider skill under `SmartCMP-Provider/skills/request`.

## Purpose

Submit cloud resource or application provisioning requests through SmartCMP platform with interactive parameter collection.

## Trigger Conditions

Use this skill when user intent is any of:
- Provision / deploy resources
- Create virtual machine / VM
- 创建虚拟机 / VM申请 / 申请虚拟机
- Request cloud resources
- 申请云资源 / 资源申请
- Deploy application
- 部署应用

## Script Entry Points

**Data collection scripts** (in `../shared/scripts/`):
- `list_services.py` — List published service catalogs
- `list_components.py` — Get component type (nodeType, osType)
- `list_business_groups.py` — List business groups for a catalog
- `list_applications.py` — List applications in a business group
- `list_resource_pools.py` — List resource pools
- `list_os_templates.py` — List OS templates (VM only)
- `list_cloud_entry_types.py` — Get cloud entry types (public/private)
- `list_images.py` — List images (private cloud only)

**Submit script** (in `scripts/`):
- `scripts/submit.py` — Submit the assembled request

## Invocation Guidance

When user asks "provision a Linux VM":

**Step 1**: List available services
```bash
python ../shared/scripts/list_services.py
```

**Step 2**: After user selects, silently get component type
```bash
python ../shared/scripts/list_components.py resource.iaas.machine.instance.abstract
```

**Step 3**: Collect parameters interactively (business group → resource pool → OS template → etc.)

**Step 4**: Build JSON body and show to user for confirmation

**Step 5**: Submit request
```bash
python scripts/submit.py --file request_body.json
```

Return Request ID and State to user.

## Environment Setup

```powershell
$env:CMP_URL = "https://<host>/platform-api"
$env:CMP_COOKIE = '<full cookie string>'
```

## References

- [WORKFLOW.md](references/WORKFLOW.md) — Detailed step-by-step workflow
- [PARAMS.md](references/PARAMS.md) — Parameter placement rules
- [EXAMPLES.md](references/EXAMPLES.md) — Request body examples

## Notes

**CRITICAL RULES:**
- **NEVER create temp files** — no `.py`, `.txt`, `.json`. Your context IS your memory.
- **NEVER redirect output** — no `>`, `>>`, `2>&1`. Run scripts directly, read stdout.
- **NEVER flatten request body** — VM fields MUST be inside `resourceSpecs[]` array.
- **NEVER pass JSON as command-line string** in PowerShell — use `--file`.

**General:**
- Scripts read SmartCMP connection from environment variables (`CMP_URL`, `CMP_COOKIE`).
- All `list_*.py` scripts are shared across skills (datasource, request).
- Follow the workflow in [WORKFLOW.md](references/WORKFLOW.md) for correct execution order.
