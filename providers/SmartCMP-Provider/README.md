# SmartCMP Provider

SmartCMP Provider is a service provider module for AtlasClaw, integrating with SmartCMP cloud management platform. It supports cloud resource provisioning, approval workflow management, alarm alert handling, data source queries, form schema design, and resource compliance analysis.

## Embedded Assistant Context

SmartCMP's AtlasClaw integration deterministically resolves five normalized page paths through
`assistant_context/routes.json`: pending approval detail, catalog request, My Application request
detail, cloud resource detail, and virtual-machine detail. The request-detail template is
`/main/new-process/myApplication/{application_type}/{request_id}`. The manifest maps each path to
one existing `smartcmp:*` Skill and declares one Provider-level Context entrypoint,
`assistant_context/resolve.py`. Adding or remapping a Skill requires only a route entry; it does not
add a Skill-specific resolver. The single resolver handles supported SmartCMP page-object APIs
independently of `skill_ref`, and a genuinely new SmartCMP object API extends that Provider-level
object boundary rather than a domain Skill. Context resolution requires the explicitly configured
Provider type/instance and accepts only the request-scoped Host
`CloudChef-Authenticate` Cookie for the explicitly selected Provider instance. It ignores Provider
tokens, user tokens, configured cookies, and username/password credentials, and never auto-logs in.
It returns minimal objects containing only approved display fields and does not introduce a separate login, token, credential,
role, menu, ACL, or database-permission flow.

Successful Context resolution also returns standard `object_actions` as display-only Chat intents. Pending
approval exposes Open, Analyze, Approve, and Reject; those prompts continue through the existing
`smartcmp:approval` conversation flow. Catalog Context exposes Open and Request, resource and
virtual-machine Context expose Open and Operations, and My Application request detail exposes Open
and Status. Resolver actions carry only the generic display, navigation, and Chat-prompt fields
consumed by AtlasClaw. Each prompt refers to the current page object; AtlasClaw supplies the resolved
object snapshot to the conversation. The matched existing Skill remains responsible for selecting
and running its own authorized capabilities under the current user's existing permissions.
Existing business Skill execution semantics remain unchanged.

Approval analysis is exposed through the standard Analyze object action. A matched route declares
exactly one existing domain Skill, while the manifest declares only one external resolver for the
Provider. Neither mapping redefines that Skill's capabilities, parameters, authentication,
authorization, or ordinary menu conversation behavior. The browser receives only the selected
display fields and generic actions, while AtlasClaw keeps the resolved object in its server-side
context snapshot.

Deployment configuration must reference:

- `route_manifest`: `assistant_context/routes.json`

Authentication cookies, tokens, and Provider credentials must remain in the existing runtime
configuration and must never be written into either manifest.

## Features

- **Resource Requests** - Submit cloud resource or application provisioning requests and query submitted request status by Request ID
- **Approval Management** - View pending approval tasks, approve requests, or reject requests
- **Alarm Management** - List alerts, analyze one alert, and run explicit alert status operations
- **Directory Queries** - List business-group scopes such as tenant/租户/部门/BU/项目, resource pools, resources, or cloud hosts from the same UI directory endpoints used by CMP
- **Resource Operations** - List current-user executable operations and run enabled no-parameter day2 operations on existing cloud resources
- **Data Queries** - Query service catalogs, applications, templates, images, and other reference data
- **Intelligent Agents** - Automated pre-approval and request decomposition capabilities
- **Cost Optimization** - Review optimization recommendations, analyze savings, execute SmartCMP-native fixes, and track remediation progress
- **Resource Compliance** - Resolve resources by exact name or visible list index, reuse the shared normalized resource view, and analyze lifecycle, patch, security, and configuration posture
- **Form Designer** - Generate, read, normalize, and refine SmartCMP Angular form schemas without saving changes to CMP

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

Browse, inspect, list current-user executable operations, and operate on SmartCMP resources or cloud hosts.

**Use Cases:**
- 查看我的云资源
- 查看所有资源
- 查看我的云主机
- 查看所有云主机
- 查看某个云主机详情
- 分析某个云主机属性
- 查看云主机可执行操作
- 执行云主机操作
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

# List current-user executable no-parameter operations
python skills/resource/scripts/list_resource_operations.py 'https://cmp/#/main/virtual-machines/res-1/details'

# Execute one no-parameter operation
python skills/resource/scripts/operate_resource.py res-1 --action create_snapshot
```

The resource list output includes each item's current status so users can tell
whether a start or stop action is needed.

The operation list comes from `GET /nodes/{category}/{id}/resource-actions`
with the current user's SmartCMP credentials. It does not use resource-type
definition endpoints as executable-operation fallback.

Resource operation output is intentionally concise. Successful operation results
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

Fetch one or more existing SmartCMP resources by exact resource name or visible
list selection, reuse the shared normalized resource view, and analyze
lifecycle, patch, security, and configuration posture.

**Workflow:**
1. Resolve the resource by visible name or latest resource-list index; keep SmartCMP UUIDs internal
2. Retrieve resource summary, full resource data, details, and the standard normalized `type + properties` view with `list_resource.py`
3. Reuse that normalized resource view (`type = componentType`) for analyzer routing
4. Route cloud/software/OS analyzers (Tomcat, MySQL, PostgreSQL, Redis, Elasticsearch, SQL Server, Linux, Windows, AliCloud OSS)
5. Perform best-effort live internet validation against authoritative sources when product/version evidence is sufficient
6. Emit readable output and a stable `##RESOURCE_COMPLIANCE_START##` JSON block

**Examples:**
```bash
# Show visible resource names and indexes
python skills/resource/scripts/list_all_resource.py --scope virtual_machines

# Analyze one resource by name
python skills/resource-compliance/scripts/analyze_resource.py --resource-name e2e-newrole-linux3-0501

# Analyze one resource selected from the latest resource list
python skills/resource-compliance/scripts/analyze_resource.py \
  --resource-index 2 \
  --resource-directory-json '[{"index":2,"id":"internal-id","name":"e2e-newrole-linux3-0501"}]'

# Analyze webhook-style input
python skills/resource-compliance/scripts/analyze_resource.py \
  --payload-json '{"resourceIds":["id-1","id-2"],"triggerSource":"webhook"}'
```

Interactive resource-compliance workflows should not ask users for SmartCMP
UUIDs. Resource IDs are internal API and webhook compatibility values only.

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

### form-designer - SmartCMP Form Schema Design

Generate new SmartCMP Angular form schemas or refine existing schemas from
SmartCMP form edit URLs. This skill is read-only with respect to CMP
persistence: it may call `GET /forms/{id}` to read source schema, but it never
saves, updates, publishes, submits, or deletes CMP data.

**Workflow:**
1. For existing forms, read the form URL with `read_form.py`
2. Generate or modify the schema JSON according to the user's requirements
3. Normalize the schema with `design_form.py`
4. Return the final schema JSON and a short change summary for manual copy/review

**Examples:**
```bash
# Read an existing form schema
python skills/form-designer/scripts/read_form.py \
  'https://cmp.example/#/main/service-model/forms/edit/42607f38-2c63-4649-a8de-efa031db4544'

# Normalize a new or modified schema draft
python skills/form-designer/scripts/design_form.py \
  --mode new \
  --schema-json '{"type":"object","properties":{}}' \
  --change-summary 'Generated a new form schema.'
```

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
│   ├── form-designer/               # SmartCMP Angular form schema design skill
│   │   ├── references/
│   │   ├── scripts/
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
8. **No Raw Day2 Dumps** - Resource operations should not print raw request payloads or raw SmartCMP response details after a successful submission.
9. **Form Designer Is Read-Only** - `form-designer` outputs schema JSON for manual review/copy only. It must not save or update CMP forms.

## Related Documentation

- [PROVIDER.md](PROVIDER.md) - Detailed connection parameters and configuration
- `SKILL.md` in each skill module - Skill usage guides
- `references/` directory in each skill module - Workflow and parameter documentation
