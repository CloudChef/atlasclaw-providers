# SmartCMP Provider

SmartCMP Provider is a service provider module for AtlasClaw, integrating with SmartCMP cloud management platform. It supports cloud resource provisioning, approval workflow management, alarm alert handling, data source queries, and resource compliance analysis.

## Features

- **Resource Requests** - Submit cloud resource or application provisioning requests and query submitted request status by Request ID
- **Approval Management** - View pending approval tasks, approve requests, or reject requests
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

Manage SmartCMP approval workflows including querying pending approval tasks,
approving requests, and rejecting requests.

**Use Cases:**
- View pending approval list
- Batch approve or reject requests
- Approval operations with reasons

**Boundary:**
- Use this skill only for pending approval tasks and approval actions.
- Do not use approval tools for a user's submitted request status or approval-result query.
- For "check my request status" or "has my submitted request been approved", use `request/scripts/status.py`.

**Examples:**
```bash
# List pending approvals
python skills/approval/scripts/list_pending.py

# Approve request
python skills/approval/scripts/approve.py <request_id> --reason "Approved per policy"

# Reject request
python skills/approval/scripts/reject.py <request_id> --reason "Budget exceeded"
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
python skills/datasource/scripts/list_services.py

# Show resource details and normalized resource view by ID
python skills/datasource/scripts/list_resource.py <resource_id>
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

### resource - Resource Browsing & Operations

Browse, inspect, and operate on SmartCMP resources or cloud hosts.

**Use Cases:**
- 查看我的云资源
- 查看所有资源
- 查看我的云主机
- 查看所有云主机
- 查看某个云主机详情
- 分析某个云主机属性
- 把某个云资源关机
- 把某个云主机开机
- Query resources or virtual machines by keyword without entering the request workflow

**Examples:**
```bash
# List all resources
python skills/resource/scripts/list_all_resource.py

# List all cloud hosts
python skills/resource/scripts/list_all_resource.py --scope virtual_machines

# Filter cloud hosts
python skills/resource/scripts/list_all_resource.py --scope virtual_machines --query-value production

# Refresh and analyze one cloud host
python skills/resource/scripts/resource_detail.py <resource_id>

# Stop one resource
python skills/resource/scripts/operate_resource.py res-1 --action stop

# Start multiple resources
python skills/resource/scripts/operate_resource.py res-1 res-2 --action start
```

The resource list output includes each item's current status so users can tell
whether a start or stop action is needed.

Power operation output is intentionally concise. Successful start/stop results
show only the action, resource ID(s), submitted flag, message, and verification
hint. Raw request payloads and raw SmartCMP response details are not printed.

### request - Resource Requests & Submitted Request Status

Submit cloud resource or application provisioning requests through SmartCMP
platform with interactive parameter collection. Also query the status of an
already submitted request by the SmartCMP Request ID returned from submission.

**Workflow:**
1. List available service catalogs
2. Select service and get component type
3. Use datasource business-group listing to determine whether the user has one or multiple available business groups
4. If datasource returns one business group, use it silently; if it returns multiple, ask the user to choose one
5. Collect the remaining parameters interactively (resource pool → OS template, etc.)
6. Build request body and confirm
7. Submit request

**Submitted Request Status:**
- Use `status.py` for questions such as "check my request status" or "has my request been approved?"
- Input is the user-visible Request ID returned by submission, such as `RES20260501000095` or `TIC20260316000001`.
- The script searches `/generic-request/search` for an exact request-number match, then fetches detail with `/generic-request/{id}`.
- The script returns structured fields such as `state`, `statusCategory`, `approvalPassed`, `currentStep`, `currentApprover`, `provisionState`, `error`, and `updatedAt`.
- The agent should explain those fields in the current user's message language; the script does not hard-code a localized approval sentence.

**Status Semantics:**
- `APPROVAL_PENDING` means approval has not passed yet.
- `APPROVAL_REJECTED` and `APPROVAL_RETREATED` mean approval did not pass.
- `STARTED`, `TASK_RUNNING`, `WAIT_EXECUTE`, and `FINISHED` mean approval passed or the request entered a later execution stage.
- `INITIALING`, `INITIALING_FAILED`, `FAILED`, and `CANCELED` should be reported as the current state without claiming approval or rejection.

**Examples:**
```bash
# List services
python skills/datasource/scripts/list_services.py

# Submit request
python skills/request/scripts/submit.py --file request_body.json

# Query submitted request status
python skills/request/scripts/status.py RES20260501000095
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

### Webhook Robot Execution

SmartCMP backend agents can be invoked by AtlasClaw webhooks with a scoped
robot profile. Use this for external-system automation where SmartCMP should
show a robot/admin account as the actor instead of the synthetic AtlasClaw
webhook user.

Recommended SmartCMP setup:

- Configure `robot_auth.<profile>` on the SmartCMP provider instance.
- Use a SmartCMP `cmp_tk_*` token as the robot `provider_token` when available.
- Add both `smartcmp:preapproval-agent` and
  `smartcmp:request-decomposition-agent` to the robot profile only if the same
  robot account is allowed to run both workflows.
- Send webhook payloads with `args.provider_instance` and
  `args.robot_profile`; do not use `args.instance` for robot execution.

When the selected token starts with `cmp_tk_`, SmartCMP scripts send it as
`Authorization: Bearer <token>`. Approval tools use the selected robot
credential. In webhook robot dispatches that do not forward SmartCMP user
cookies, request submission resolves the SmartCMP actor from that same robot
credential, so SmartCMP audit trails show the configured robot/admin account.

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
python skills/datasource/scripts/list_resource.py <resource_id>

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
│   ├── request/                     # Resource request and submitted-status skill
│   │   ├── scripts/                 # Submit and status scripts
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
│       └── scripts/                 # Shared authentication module
│           └── _common.py
├── test/                            # Provider test suite
├── PROVIDER.md                      # Provider configuration docs
└── README.md                        # This file
```

## Shared Scripts

The `shared/scripts/` directory contains the authentication module, while data query
scripts are located in `datasource/scripts/`:

| Script | Location | Description |
|--------|----------|-------------|
| `_common.py` | `shared/scripts/` | Authentication & URL normalization (used by all scripts) |
| `list_resource.py` | `datasource/scripts/` | Fetch resource summary, details, raw resource fields, and the shared normalized `type + properties` view by ID |
| `list_services.py` | `datasource/scripts/` | List published service catalogs |
| `list_all_business_groups.py` | `datasource/scripts/` | List standalone business-group scopes |

## Notes

1. **Environment Variables** - All scripts read connection info from `CMP_URL`, `CMP_COOKIE`, `CMP_USERNAME`, `CMP_PASSWORD`, and `CMP_AUTH_URL` environment variables
2. **Cookie Expiration** - If you encounter `401` errors, refresh and update the Cookie
3. **Output Format** - Script output includes named metadata blocks such as `##..._START## ... ##..._END##` for programmatic parsing
4. **Alarm Coverage** - Monitoring and alert workflows are supported directly by the `alarm` skill in this provider
5. **Error Handling** - On `[ERROR]` output, report to user immediately; do NOT self-debug
6. **Resource Compliance** - `resource-compliance` reuses the shared normalized resource view from `list_resource.py`, then attempts live external validation for lifecycle and support checks
7. **Localized Responses** - Scripts should return stable fields and metadata. Agents are responsible for explaining results in the current user's message language.
8. **No Raw Day2 Dumps** - Resource power operations should not print raw request payloads or raw SmartCMP response details after a successful submission.

## Related Documentation

- [PROVIDER.md](PROVIDER.md) - Detailed connection parameters and configuration
- `SKILL.md` in each skill module - Skill usage guides
- `references/` directory in each skill module - Workflow and parameter documentation
