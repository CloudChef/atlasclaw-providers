# SmartCMP Provider

SmartCMP Provider is a service provider module for AtlasClaw, integrating with SmartCMP cloud management platform. It supports cloud resource provisioning, approval workflow management, alarm alert handling, data source queries, and resource compliance analysis.

## Features

- **Resource Requests** - Submit cloud resource or application provisioning requests via SmartCMP
- **Approval Management** - View pending approvals, approve or reject requests
- **Alarm Management** - List alerts, analyze one alert, and run explicit alert status operations
- **Directory Queries** - List business-group scopes such as tenant/租户/部门/BU/项目, resource pools, resources, or cloud hosts from the same UI directory endpoints used by CMP
- **Resource Power Operations** - Start or stop existing cloud resources and virtual machines through the SmartCMP day2 endpoint
- **Data Queries** - Query service catalogs, applications, templates, images, and other reference data
- **Intelligent Agents** - Automated pre-approval and request decomposition capabilities
- **Cost Optimization** - Review optimization recommendations, analyze savings, execute SmartCMP-native fixes, and track remediation progress
- **Resource Compliance** - Fetch resources by ID, reuse the shared normalized resource view, and analyze lifecycle, patch, security, and configuration posture

## Quick Start

### Environment Configuration

SmartCMP Provider supports two deployment modes. Configure in `.env` file at project root:

> **Note:** Auth URL is automatically inferred from `CMP_URL` - no manual configuration needed!
>
> SmartCMP SaaS auth handling is exact-match only:
> - `https://console.smartcmp.cloud/` uses `https://account.smartcmp.cloud/bss-api/api/authentication`
> - `https://account.smartcmp.cloud/#/login` uses `https://account.smartcmp.cloud/bss-api/api/authentication`
> - All other hosts default to `{CMP_URL}/platform-api/login` unless `CMP_AUTH_URL` is set explicitly
>
> | Environment | Auth URL (auto-inferred) |
> |-------------|--------------------------|
> | `console.smartcmp.cloud` | `account.smartcmp.cloud/bss-api/api/authentication` |
> | `account.smartcmp.cloud` | `account.smartcmp.cloud/bss-api/api/authentication` |
> | Private deployment | `{CMP_URL}/platform-api/login` |
>
> If your private deployment uses a `smartcmp.cloud` hostname or a non-standard
> login endpoint, set `CMP_AUTH_URL` explicitly to avoid host-based inference.

---

#### Mode 1: SaaS Environment (Auto-Login)

For SmartCMP SaaS platform:

```bash
# .env file

# Business API domain (auto-appends /platform-api)
CMP_URL=https://console.smartcmp.cloud

# Auto-login credentials (Cookie will be obtained automatically)
CMP_USERNAME=your_email@company.com
CMP_PASSWORD=your_password_or_md5_hash

# Optional: Override login endpoint explicitly
# CMP_AUTH_URL=https://cmp.example.com/platform-api/login

# Optional: Skip auto-login if you have a valid Cookie
# CMP_COOKIE=your_cookie_string
```

---

#### Mode 2: Private Deployment (Auto-Login or Cookie)

For on-premise SmartCMP installations:

```bash
# .env file

# Single IP/domain (auto-appends /platform-api)
CMP_URL=https://your-cmp-server-ip

# Optional: Override login endpoint explicitly
# CMP_AUTH_URL=https://your-private-cmp/platform-api/login

# Option A: Auto-login (Recommended)
CMP_USERNAME=admin
CMP_PASSWORD=your_password_or_md5_hash

# Option B: Direct Cookie (if auto-login fails)
# CMP_COOKIE=XXL_JOB_LOGIN_IDENTITY=xxx; CloudChef-Authenticate=xxx; tenant_id=xxx; ...
```

---

### Configuration Priority

1. If `CMP_COOKIE` is set → Use directly
2. If `CMP_COOKIE` is empty → Check local cache (`.atlasclaw/users/default/sessions/smartcmp_cookie_cache.json`)
3. If cache missing/expired → Auto-login using `CMP_USERNAME` + `CMP_PASSWORD`

The local `.atlasclaw/users/default/sessions/` cache is a runtime artifact and
should not be committed.

---

### Obtaining Cookie Manually

1. Log into SmartCMP web console
2. Open browser Developer Tools (F12)
3. Go to Network tab
4. Refresh the page, click any `/platform-api/*` request
5. Copy the full `Cookie` header value

---

### Quick Verification

Test your configuration:

```bash
# Run from providers/SmartCMP-Provider/
python -c "
import sys; sys.path.insert(0, 'skills/shared/scripts')
from _common import get_cmp_config
url, auth_token, _ = get_cmp_config()
print(f'URL: {url}')
print(f'Auth: {auth_token[:50]}...' if auth_token and len(auth_token) > 50 else f'Auth: {auth_token}')
"
```

## Skill Modules

All example commands below assume your current directory is
`providers/SmartCMP-Provider/`.

### approval - Approval Management

Manage SmartCMP approval workflows including querying pending approvals, approving requests, and rejecting requests.

**Use Cases:**
- View pending approval list
- Batch approve or reject requests
- Approval operations with reasons

**Examples:**
```bash
# List pending approvals
python skills/approval/scripts/list_pending.py

# Approve request
python skills/approval/scripts/approve.py <approval_id> --reason "Approved per policy"

# Reject request
python skills/approval/scripts/reject.py <approval_id> --reason "Budget exceeded"
```

### alarm - Alarm Alert Management

Inspect and analyze SmartCMP alarms directly in this provider. Use
`operate_alert.py` only when an explicit status action is intended.

**Use Cases:**
- List current alarm alerts
- Analyze a specific alert with structured recommendations
- Operate on alert status using English actions such as `mute`, `resolve`, or `reopen`

**Examples:**
```bash
# List alerts
python skills/alarm/scripts/list_alerts.py

# Analyze one alert
python skills/alarm/scripts/analyze_alert.py <alert_id>

# Operate on one or more alerts
python skills/alarm/scripts/operate_alert.py <alert_id> --action mute
```

### datasource - Data Source Queries

Read-only queries for SmartCMP reference data, used for browsing, discovering
available resources, and looking up existing resources by ID. Standalone
business-group scope discovery belongs here, while standalone resource-pool and
resource browsing still use their dedicated skills.

**Supported Queries:**
- Business-group scopes such as tenant / 租户 / 部门 / BU / Project
- Service catalogs
- Application lists
- OS templates
- Images
- Resource details by resource ID with `list_resource.py`
- Shared normalized resource view (`type + properties`) from `list_resource.py`

**Examples:**
```bash
# List standalone business-group scopes
python skills/datasource/scripts/list_all_business_groups.py

# Filter business-group scopes
python skills/datasource/scripts/list_all_business_groups.py production

# List service catalogs
python skills/shared/scripts/list_services.py

# List catalog business groups
python skills/shared/scripts/list_business_groups.py <catalogId>

# List resource pools
python skills/shared/scripts/list_resource_pools.py <bgId> <sourceKey> <nodeType>

# Show resource details and normalized resource view by ID
python skills/shared/scripts/list_resource.py <resource_id>
```

### resource-pool - Resource Pool Directory

Read-only listing of all SmartCMP resource pools through the standalone CMP UI
directory endpoint.

**Use Cases:**
- 查询可用的资源池
- 查询资源池
- 列出所有的资源池
- Query resource pools by keyword without entering the request workflow

**Examples:**
```bash
# List all resource pools
python skills/resource-pool/scripts/list_all_resource_pools.py

# Filter resource pools
python skills/resource-pool/scripts/list_all_resource_pools.py production
```

### resource - Resource Directory

Read-mostly listing and inspection of SmartCMP resources or cloud hosts through
the standalone CMP UI list endpoints.

**Use Cases:**
- 查看我的云资源
- 查看所有资源
- 查看我的云主机
- 查看所有云主机
- 查看某个云主机详情
- 分析某个云主机属性
- Query resources or virtual machines by keyword without entering the request workflow

**Examples:**
```bash
# List all resources
python skills/resource/scripts/list_resources.py

# List all cloud hosts
python skills/resource/scripts/list_resources.py --scope virtual_machines

# Filter cloud hosts
python skills/resource/scripts/list_resources.py --scope virtual_machines --query-value production

# Refresh and analyze one cloud host
python skills/resource/scripts/analyze_resource_detail.py <resource_id>
```

The resource list output includes each item's current status so users can tell
whether a start or stop action is needed.

### resource-power - Resource Power Operations

Focused day2 start/stop operations for existing SmartCMP cloud resources or
virtual machines.

**Use Cases:**
- 把某个云资源关机
- 把某个云主机开机
- Stop a resource after confirming it is currently running
- Start a VM after confirming it is currently stopped

**Workflow:**
1. Use `resource` to list matching resources and review their current status
2. Map the chosen item to the SmartCMP `resource_id`
3. Submit the native power operation with `start` or `stop`

**Examples:**
```bash
# Stop one resource
python skills/resource-power/scripts/operate_resource_power.py res-1 --action stop

# Start multiple resources
python skills/resource-power/scripts/operate_resource_power.py res-1 res-2 --action start
```

### request - Resource Requests

Submit cloud resource or application provisioning requests through SmartCMP platform with interactive parameter collection.

**Workflow:**
1. List available service catalogs
2. Select service and get component type
3. Use datasource business-group listing to determine whether the user has one or multiple available business groups
4. If datasource returns one business group, use it silently; if it returns multiple, ask the user to choose one
5. Collect the remaining parameters interactively (resource pool → OS template, etc.)
6. Build request body and confirm
7. Submit request

**Examples:**
```bash
# List services
python skills/shared/scripts/list_services.py

# Get component type
python skills/shared/scripts/list_components.py resource.iaas.machine.instance.abstract

# Submit request
python skills/request/scripts/submit.py --file request_body.json
```

### preapproval-agent - Pre-approval Agent

Automated approval agent triggered by webhooks, analyzes request reasonableness and executes approval decisions.

**Features:**
- Rule-based auto-approve/reject
- Multiple policy modes (balanced, strict, etc.)
- Structured decision reports

**Decision Criteria:**
- Business purpose clarity
- Resource configuration appropriateness
- Cost alignment with requirements
- Environment selection suitability

### request-decomposition-agent - Request Decomposition Agent

Transforms descriptive infrastructure or application demands into executable CMP request candidates.

**Features:**
- Parse free-text requirements
- Auto-match service catalogs
- Generate draft requests for human review
- Mark unresolved fields

**Output Modes:**
- `draft` - Generate drafts only, no submission
- `review_required` - Create requests pending human adjustment

### cost-optimization - Cost Optimization

List SmartCMP optimization recommendations, analyze savings opportunities, execute SmartCMP-native day2 fixes, and track remediation progress.

**Workflow:**
1. Discover recommendations with `list_recommendations.py`
2. Inspect a finding with `analyze_recommendation.py --id <violation_id>`
3. Execute a SmartCMP-native fix with `execute_optimization.py --id <violation_id>`
4. Check remediation state with `track_execution.py --id <violation_id>`

**Safety Boundary:**
- Public-cloud best-practice guidance is advisory only
- Execution uses `POST /compliance-policies/violations/day2/fix/{id}`
- No direct AWS or Azure API calls are made by this skill

### resource-compliance - Resource Compliance

Fetch one or more existing SmartCMP resources by ID, reuse the shared
normalized resource view, and analyze lifecycle, patch, security, and
configuration posture.

**Workflow:**
1. Retrieve resource summary, full resource data, details, and the standard normalized `type + properties` view with `list_resource.py`
2. Reuse that normalized resource view (`type = componentType`) for analyzer routing
3. Route cloud/software/OS analyzers (Tomcat, MySQL, PostgreSQL, Redis, Elasticsearch, SQL Server, Linux, Windows, AliCloud OSS)
4. Perform best-effort live internet validation against authoritative sources when product/version evidence is sufficient
5. Emit readable output and a stable `##RESOURCE_COMPLIANCE_START##` JSON block

**Examples:**
```bash
# Fetch raw resource facts
python skills/shared/scripts/list_resource.py <resource_id>

# Analyze one or more resources directly
python skills/resource-compliance/scripts/analyze_resource.py <resource_id>

# Analyze webhook-style input
python skills/resource-compliance/scripts/analyze_resource.py \
  --payload-json '{"resourceIds":["id-1","id-2"],"triggerSource":"webhook"}'
```

Representative output fields:
```json
{
  "type": "resource.software.app.tomcat",
  "analysisTargets": ["software:tomcat"]
}
```

**Safety Boundary:**
- Analysis is advisory and evidence-driven
- External validation is best-effort and degrades conservatively when unavailable
- No remediation APIs are called by this skill

## Directory Structure

```
SmartCMP-Provider/
├── skills/
│   ├── approval/                    # Approval management skill
│   │   ├── scripts/                 # Approval scripts
│   │   ├── references/              # Reference docs
│   │   └── SKILL.md
│   ├── alarm/                       # Alarm alert skill
│   │   ├── scripts/                 # Alarm listing, analysis, and operations
│   │   ├── references/
│   │   └── SKILL.md
│   ├── cost-optimization/           # Cost optimization skill
│   │   ├── references/
│   │   ├── scripts/
│   │   └── SKILL.md
│   ├── datasource/                  # Data source query skill
│   │   ├── scripts/                 # Datasource-owned standalone business-group directory helper
│   │   ├── references/
│   │   └── SKILL.md
│   ├── preapproval-agent/           # Pre-approval agent
│   │   ├── references/
│   │   └── SKILL.md
│   ├── request/                     # Resource request skill
│   │   ├── scripts/                 # Submit scripts
│   │   ├── references/
│   │   └── SKILL.md
│   ├── request-decomposition-agent/ # Request decomposition agent
│   │   ├── references/
│   │   └── SKILL.md
│   ├── resource/                    # Standalone resource directory skill
│   │   ├── scripts/
│   │   └── SKILL.md
│   ├── resource-pool/               # Standalone resource-pool directory skill
│   │   ├── scripts/
│   │   └── SKILL.md
│   ├── resource-compliance/         # Resource compliance analysis skill
│   │   ├── references/
│   │   ├── scripts/
│   │   └── SKILL.md
│   └── shared/
│       └── scripts/                 # Shared SmartCMP data-access scripts
│           ├── _common.py
│           ├── list_services.py
│           ├── list_business_groups.py
│           ├── list_components.py
│           ├── list_resource_pools.py
│           ├── list_applications.py
│           ├── list_os_templates.py
│           ├── list_cloud_entry_types.py
│           ├── list_images.py
│           └── list_resource.py
├── test/                            # Provider test suite
├── PROVIDER.md                      # Provider configuration docs
└── README.md                        # This file
```

## Shared Scripts

The `shared/scripts/` directory contains data query scripts shared across multiple skills:

| Script | Description |
|--------|-------------|
| `list_services.py` | List published service catalogs |
| `list_business_groups.py` | List business groups for a catalog |
| `list_components.py` | Get component type information |
| `list_resource_pools.py` | List available resource pools |
| `list_applications.py` | List applications in a business group |
| `list_os_templates.py` | List OS templates (VM only) |
| `list_cloud_entry_types.py` | Get cloud entry types |
| `list_images.py` | List images (private cloud only) |
| `list_resource.py` | Fetch resource summary, details, raw resource fields, and the shared normalized `type + properties` view by ID |

## Notes

1. **Environment Variables** - All scripts read connection info from `CMP_URL`, `CMP_COOKIE`, `CMP_USERNAME`, `CMP_PASSWORD`, and `CMP_AUTH_URL` environment variables
2. **Cookie Expiration** - If you encounter `401` errors, refresh and update the Cookie
3. **Output Format** - Script output includes named metadata blocks such as `##..._START## ... ##..._END##` for programmatic parsing
4. **Alarm Coverage** - Monitoring and alert workflows are supported directly by the `alarm` skill in this provider
5. **Error Handling** - On `[ERROR]` output, report to user immediately; do NOT self-debug
6. **Resource Compliance** - `resource-compliance` reuses the shared normalized resource view from `list_resource.py`, then attempts live external validation for lifecycle and support checks

## Related Documentation

- [PROVIDER.md](PROVIDER.md) - Detailed connection parameters and configuration
- `SKILL.md` in each skill module - Skill usage guides
- `references/` directory in each skill module - Workflow and parameter documentation
