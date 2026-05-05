---
# === Provider Identity ===
provider_type: smartcmp
display_name: SmartCMP
version: "1.0.0"

# === LLM Context Fields (for Skill Discovery) ===
keywords:
  - cloud management
  - multi-cloud
  - hybrid cloud
  - service catalog
  - self-service
  - vm
  - virtual machine
  - application deployment
  - resource request
  - ticket
  - work order
  - business group
  - tenant
  - department
  - project
  - 租户
  - 部门
  - 项目
  - resource pool
  - approval
  - alarm
  - alert
  - monitoring
  - self-healing
  - cost optimization
  - finops
  - resource compliance
  - lifecycle analysis
  - security posture
  - infrastructure
  - cmp
  - CMP

capabilities:
  - Browse available services, business-group scopes such as tenant/租户/部门/BU/项目, resource pools, resources, cloud hosts, host details, templates, and other reference data before making a request
  - Start or stop existing cloud resources or virtual machines after resolving their SmartCMP resource IDs
  - Submit self-service requests for virtual machines, cloud resources, application environments, or ticket/work order services
  - View pending approvals and approve or reject service requests
  - List alerts, analyze alert context, and update alert status with remediation guidance
  - Turn natural language infrastructure needs into structured request drafts
  - Run automated pre-review for approval workflows
  - Review cost optimization recommendations and savings opportunities
  - Execute and track native day2 remediation for cost optimization findings
  - Fetch resource details by ID, reuse the shared normalized resource view, and analyze lifecycle, patch, security, and configuration risk

use_when:
  - User wants to request a VM, database, application environment, or other service catalog item
  - User wants to submit a ticket or work order for infrastructure or support needs
  - User asks what services, business groups, tenants, departments, projects, resource pools, resources, or cloud hosts are available before making a request
  - User wants to start or stop an existing cloud resource or virtual machine
  - User needs to approve or reject a request
  - User wants to check pending approvals
  - User wants to inspect, analyze, or operate on resource alarms
  - User describes infrastructure needs in natural language and wants them translated into request drafts
  - User wants to review cost optimization recommendations, savings opportunities, or remediation progress
  - User wants to execute a native day2 fix for a cost finding
  - User wants to analyze one or more existing resources by ID for compliance or security risk

avoid_when:
  - User wants generic issue tracking outside cloud service requests (use Jira provider)
  - User wants to manage code or repositories (use Git provider)
---

# SmartCMP Service Provider

Cloud management platform provider for self-service resource requests, approvals, alarms, cost optimization, and resource compliance analysis across hybrid cloud environments.

## Quick Start

1. Configure authentication (choose one):
   - **Option 1**: Extract session cookie from SmartCMP web console (see [Cookie Extraction](#cookie-extraction))
   - **Option 2**: Set up auto-login credentials (recommended)
2. Set environment variables (see [Environment Variables](#environment-variables))
3. Use skills: `datasource` / `resource-pool` / `resource` → `request` → `approval` → `alarm` → `cost-optimization` → `resource-compliance`

## Connection Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `base_url` | string | Yes | SmartCMP platform API URL (e.g., `https://cmp.corp.com/platform-api`) |
| `provider_token` | string | Option 1 | Shared provider API token configured by the platform administrator for all users |
| `user_token` | string | Option 2 | User API token for token-based authentication (e.g., `cmp_tk_v1_...`) |
| `cookie` | string | Option 3 | Full authentication cookie string. Use `${CMP_COOKIE}` env var |
| `username` | string | Option 4 | Username for auto-login authentication |
| `password` | string | Option 4 | Password for auto-login authentication (plaintext or MD5 hash) |
| `auth_url` | string | No | Explicit authentication URL override. Use for private deployments that should not follow host inference |
| `timeout` | number | No | API request timeout in seconds (default: 30) |

> **Note:** Auth URL inference is exact-match only:
> - `https://console.smartcmp.cloud/` → `https://account.smartcmp.cloud/bss-api/api/authentication`
> - `https://account.smartcmp.cloud/#/login` → `https://account.smartcmp.cloud/bss-api/api/authentication`
> - All other hosts default to `{host}/platform-api/login` unless `auth_url` is explicitly configured
>
> If your private deployment uses a `smartcmp.cloud` hostname or a non-standard
> login endpoint, set `auth_url` explicitly.

### Authentication Modes

`base_url` is a provider instance connection field and is required for every SmartCMP instance. It is not part of auth mode selection.

| Mode | `auth_type` | Description | Auth-specific Required Config |
|------|-------------|-------------|-------------------------------|
| **Provider Token** | `provider_token` | Shared platform-generated API token configured once for all users. | `provider_token` |
| **User Token** | `user_token` | Each user configures their own API token in AtlasClaw UI. | `user_token` |
| **Cookie** | `cookie` | Current-request CMP cookie/token, or static cookie for server-to-server/testing. | request `CloudChef-Authenticate` cookie/token or `cookie` |
| **Credential** | `credential` | Username/password auto-login to CMP API. | `username`, `password` |

> **Fallback selection:** `auth_type` may be a single value or an ordered chain. The runtime selects the first mode whose auth-specific fields are available.
> - Provider Token: `provider_token` field present
> - User Token: user-owned `user_token` field present
> - Cookie: request-scoped `CloudChef-Authenticate` cookie/token or `cookie` field present
> - Credential: `username` + `password` fields present

## Configuration Examples

### Mode 1: Cookie Authentication (CMP Embedded)

When AtlasClaw is deployed behind the same Nginx as CMP. No credentials in `.env`.

```json
{
  "service_providers": {
    "smartcmp": {
      "default": {
        "base_url": "https://172.16.0.81",
        "auth_type": "cookie"
      }
    }
  }
}
```

> **Important:** `base_url` must be **hardcoded** (not `${CMP_URL}`). No CMP env vars in `.env`.

### Mode 2: Provider Token Authentication (Recommended for standalone shared access)

Use a platform-generated API token shared by all AtlasClaw users.

```json
{
  "service_providers": {
    "smartcmp": {
      "default": {
        "base_url": "${CMP_URL}",
        "auth_type": "provider_token",
        "provider_token": "${CMP_PROVIDER_TOKEN}"
      }
    }
  }
}
```

**`.env`:**
```bash
CMP_URL=https://cmp.example.com
CMP_PROVIDER_TOKEN=cmp_tk_v1_2486ae574bd1020e6e72be503...
```

### Mode 3: Cookie Authentication

Use a pre-obtained CMP session cookie.

```json
{
  "service_providers": {
    "smartcmp": {
      "default": {
        "base_url": "${CMP_URL}",
        "auth_type": "cookie",
        "cookie": "${CMP_COOKIE}"
      }
    }
  }
}
```

**`.env`:**
```bash
CMP_URL=https://cmp.example.com
CMP_COOKIE=eyJhbGciOiJIUzI1NiJ9...
```

### Mode 4: Credential Authentication

Auto-login with username/password.

```json
{
  "service_providers": {
    "smartcmp": {
      "default": {
        "base_url": "${CMP_URL}",
        "auth_type": "credential",
        "username": "${CMP_USERNAME}",
        "password": "${CMP_PASSWORD}"
      }
    }
  }
}
```

**`.env`:**
```bash
CMP_URL=https://cmp.example.com
CMP_USERNAME=admin
CMP_PASSWORD=your-password
```

> **Performance:** Credentials are cached at `.atlasclaw/users/default/sessions/smartcmp_cookie_cache.json` with 30-minute TTL.

### Mode 5: User Token

Each user configures their own API token in AtlasClaw UI.

```json
{
  "service_providers": {
    "smartcmp": {
      "default": {
        "base_url": "${CMP_URL}",
        "auth_type": "user_token"
      }
    }
  }
}
```

**`.env`:**
```bash
CMP_URL=https://cmp.example.com
```

> Users add their API tokens in **Settings > Provider Tokens** within the AtlasClaw UI.

## Environment Variables Reference

| Variable | Required By | Description |
|----------|-------------|-------------|
| `CMP_URL` | Provider Token, Cookie, Credential, User Token | SmartCMP platform URL. Auto-normalizes: adds `https://` and `/platform-api` if missing. |
| `CMP_PROVIDER_TOKEN` | Provider Token | Shared platform-generated API token for all AtlasClaw users. |
| `CMP_API_TOKEN` | Legacy User Token | Platform-generated API token used by legacy env fallback. |
| `CMP_COOKIE` | Cookie | Full session cookie string from browser. |
| `CMP_USERNAME` | Credential | Login username. |
| `CMP_PASSWORD` | Credential | Login password (plaintext or MD5 hash). |

### Quick Setup by Mode

**CMP Embedded Cookie Mode:**
```bash
# No environment variables needed
```

**Provider Token Mode:**
```bash
CMP_URL=https://cmp.example.com
CMP_PROVIDER_TOKEN=cmp_tk_v1_...
```

**Cookie Mode:**
```bash
CMP_URL=https://cmp.example.com
CMP_COOKIE=eyJhbGciOiJIUzI1NiJ9...
```

**Credential Mode:**
```bash
CMP_URL=https://cmp.example.com
CMP_USERNAME=admin
CMP_PASSWORD=your-password
```

**User Token Mode:**
```bash
CMP_URL=https://cmp.example.com
# User configures token in UI
```

### Cookie Extraction

1. Log into SmartCMP web console
2. Open browser Developer Tools (F12)
3. Go to **Network** tab → Refresh page
4. Click any `/platform-api/*` request
5. Copy the full `Cookie` header value

## Provided Skills

| Skill | Type | Description | Key Operations |
|-------|------|-------------|----------------|
| `resource-pool` | Directory Query | Standalone listing of all resource pools from the CMP UI directory endpoint | `smartcmp_list_all_resource_pools` |
| `resource` | Directory Query + Day2 Operation | Standalone listing of all resources or all cloud hosts, one-host detail analysis via `PATCH /nodes/{id}/view`, and start/stop power operations | `smartcmp_list_all_resource`, `smartcmp_resource_detail`, `smartcmp_operate_resource` |
| `datasource` | Data Query | Read-only reference data queries, standalone business-group scope discovery, request reference lookups, and resource lookup by ID for service discovery and analysis workflows | `smartcmp_list_all_business_groups`, `smartcmp_list_applications`, `smartcmp_list_components`, `smartcmp_list_images`, `list_services`, `list_resource` |
| `request` | Provisioning | Cloud resource provisioning requests that use datasource lookups for reference data before submission | `submit`, `status` |
| `approval` | Workflow | Approval workflow management | `list_pending`, `approve`, `reject` |
| `alarm` | Monitoring | Alarm alert listing, analysis, and status operations | `list_alerts`, `analyze_alert`, `operate_alert` |
| `preapproval-agent` | Agent | Autonomous approval pre-review | Webhook-triggered, policy-based decisions |
| `request-decomposition-agent` | Agent | Transform natural-language requirements into request drafts | NL parsing, multi-skill orchestration |
| `cost-optimization` | Optimization | Analyze savings opportunities and execute platform-native fixes | `list_recommendations`, `analyze_recommendation`, `execute_optimization`, `track_execution` |
| `resource-compliance` | Analysis | Fetch resources by ID, normalize `type + properties`, and run componentType-driven cloud/software/OS compliance analysis | `list_resource`, `analyze_resource` |

### Core Skills

All example commands below assume your current directory is
`providers/SmartCMP-Provider/`.

#### resource-pool

List all resource pools directly from the CMP UI directory endpoint. Use this
when the user says "查询可用的资源池", "查询资源池", or "列出所有的资源池" and does
not want to enter the request workflow.

```bash
python skills/resource-pool/scripts/list_all_resource_pools.py              # List all resource pools
python skills/resource-pool/scripts/list_all_resource_pools.py <keyword>    # Filter resource pools
```

#### resource

List all resources or all cloud hosts directly from the CMP UI list endpoint,
inspect one cloud host by resource ID with the `/nodes/{id}/view` evidence view, and
perform start/stop power operations on existing resources.
Use this when the user says "查看我的云资源", "查看所有资源", "查看我的云主机",
"查看所有云主机", "查看某个云主机详情", "分析某个云主机属性",
"云资源开机", "云资源关机", "启动云主机", or "停止云主机".

```bash
python skills/resource/scripts/list_all_resource.py                                     # List all resources
python skills/resource/scripts/list_all_resource.py --scope virtual_machines            # List all cloud hosts
python skills/resource/scripts/list_all_resource.py --scope virtual_machines --query-value production
python skills/resource/scripts/resource_detail.py <resource_id>              # Fetch and analyze one cloud host evidence view
python skills/resource/scripts/operate_resource.py <resource_id> --action stop
python skills/resource/scripts/operate_resource.py <resource_id> --action start
python skills/resource/scripts/operate_resource.py <id1> <id2> --action stop
```

The list output includes each resource's current status so power actions can
reuse the same browse step.

#### datasource

Query reference data (read-only). Use before `request` skill to discover
available services, business-group scopes, applications, templates, images, or
resource details. Treat SmartCMP `business group` as the same scope users may
call tenant, 租户, 部门, BU, Department, 项目, or Project. Standalone
resource-pool queries still belong to `resource-pool`, and list-style resource
browsing belongs to `resource`.

```bash
python skills/datasource/scripts/list_all_business_groups.py        # Standalone business-group scopes
python skills/datasource/scripts/list_services.py                    # List service catalogs
python skills/datasource/scripts/list_resource.py <resource_id>          # Resource details + normalized view
python skills/shared/scripts/list_applications.py <business_group_id>    # List applications
python skills/shared/scripts/list_components.py <source_key>             # List component metadata
python skills/shared/scripts/list_images.py <resource_bundle_id> <logic_template_id> <cloud_entry_type>
```

#### request

Submit cloud resource provisioning requests.

Business-group scope rule: if the user only has one available business group,
do not assume that directly. First determine the actual scope choices through
datasource business-group listing. If datasource returns one business group,
use it silently. Ask the user to choose only when datasource returns multiple
business groups for the request.

```bash
python skills/datasource/scripts/list_services.py          # 1. Discover services
python skills/request/scripts/submit.py --file request_body.json  # 2. Submit request
```

#### approval

Manage approval workflows.

```bash
python skills/approval/scripts/list_pending.py                           # List pending approvals
python skills/approval/scripts/approve.py <request_id> --reason "Approved"       # Approve
python skills/approval/scripts/reject.py <request_id> --reason "Budget exceeded" # Reject
```

#### alarm

Inspect and analyze alarm alerts, and optionally operate on alert
status when appropriate.

```bash
python skills/alarm/scripts/list_alerts.py                            # List current alerts
python skills/alarm/scripts/analyze_alert.py <alert_id>               # Analyze one alert
python skills/alarm/scripts/operate_alert.py <alert_id> --action mute # Change alert status
```

#### cost-optimization

Analyze optimization recommendations from discovery through remediation
tracking. The analysis layer can explain common public-cloud best practices for
AWS, Azure, and similar environments, but execution stays within the platform
and only uses the native day2 fix endpoint.

**Workflow:**
1. List recommendations with `list_recommendations.py`
2. Analyze one finding with `analyze_recommendation.py --id <violation_id>`
3. Execute the native fix with `execute_optimization.py --id <violation_id>`
4. Track the remediation with `track_execution.py --id <violation_id>`

**Safety Boundary:**
- Public-cloud best-practice guidance is advisory only
- Execution uses `POST /compliance-policies/violations/day2/fix/{id}`
- Do not expect direct AWS or Azure API calls from this skill

#### resource-compliance

Inspect one or more existing resources by ID and analyze lifecycle, patch,
security, and configuration posture with componentType-driven analyzers.

`list_resource.py` returns both the raw resource payloads and a shared
normalized `type + properties` view that can be reused beyond compliance.

```bash
python skills/datasource/scripts/list_resource.py <resource_id>         # Fetch resource details + normalized view
python skills/resource-compliance/scripts/analyze_resource.py <resource_id>                    # Analyze direct input
python skills/resource-compliance/scripts/analyze_resource.py --payload-json '{"resourceIds":["id-1"],"triggerSource":"webhook"}'
```

Representative output fields:

```json
{
  "type": "resource.software.app.tomcat",
  "analysisTargets": ["software:tomcat"]
}
```

### Agent Skills

#### Webhook robot execution

SmartCMP agent skills can run from AtlasClaw webhook dispatch with a scoped
robot profile. Configure the robot credential under the SmartCMP provider
instance and allowlist the exact provider-qualified skills that may use it.
Webhook payloads should pass `provider_instance` and `robot_profile`.

Use a SmartCMP `cmp_tk_*` token for the robot `provider_token` when available.
The shared scripts send those tokens as `Authorization: Bearer <token>`, and
SmartCMP audit trails should show the selected robot/admin account for approval
actions and for webhook request submissions that do not forward SmartCMP user
cookies.

#### preapproval-agent

Autonomous agent for approval pre-review. Triggered by webhooks, analyzes request reasonableness, executes approve/reject decisions.

| Input | Type | Required | Description |
|-------|------|----------|-------------|
| `provider_instance` | string | Yes | CMP provider instance name |
| `robot_profile` | string | For webhook robot mode | Robot profile configured on the selected provider instance |
| `agent_identity` | string | Yes | Must be `agent-approver` |
| `request_id` | string | Yes | Target SmartCMP Request ID |
| `policy_mode` | string | No | Policy preset (default: `balanced`) |

#### request-decomposition-agent

Orchestration agent that transforms descriptive infrastructure demands into structured request candidates.

| Input | Type | Required | Description |
|-------|------|----------|-------------|
| `provider_instance` | string | Yes | CMP provider instance name |
| `robot_profile` | string | For webhook robot mode | Robot profile configured on the selected provider instance |
| `agent_identity` | string | Yes | Must be `agent-request-orchestrator` |
| `request_text` | string | Yes | Free-form requirement description |
| `submission_mode` | string | No | `draft` or `review_required` |

## Shared Scripts Reference

Located in `skills/shared/scripts/` and `skills/datasource/scripts/`, used across
datasource, request, and resource analysis workflows:

| Script | Location | Description |
|--------|----------|-------------|
| `_common.py` | `shared/scripts/` | Authentication & URL normalization (used by all scripts) |
| `list_resource.py` | `datasource/scripts/` | Fetch resource summary, details, raw resource fields, and the shared normalized `type + properties` view by ID |
| `list_services.py` | `datasource/scripts/` | List published service catalogs |
| `list_all_business_groups.py` | `datasource/scripts/` | List standalone business-group scopes |

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| `401` / Token expired | Session cookie invalid | Refresh `CMP_COOKIE` env var |
| `[ERROR]` output | Script execution failed | Report to user; do NOT self-debug |

> All scripts output structured data with named metadata blocks such as `##..._START## ... ##..._END##` for programmatic parsing.
