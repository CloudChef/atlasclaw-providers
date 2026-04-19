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
  - Browse available services, business groups, resource pools, resources, cloud hosts, host details, templates, and other reference data before making a request
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
  - User asks what services, business groups, resource pools, resources, or cloud hosts are available before making a request
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
3. Use skills: `business-group` / `resource-pool` / `resource` / `datasource` → `request` → `approval` → `alarm` → `cost-optimization` → `resource-compliance`

## Connection Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `base_url` | string | Yes | SmartCMP platform API URL (e.g., `https://cmp.corp.com/platform-api`) |
| `user_token` | string | Option 1 | User API token for token-based authe7[]R54ntication (e.g., `cmp_tk_v1_...`) |
| `cookie` | string | Option 2 | Full authentication cookie string. Use `${CMP_COOKIE}` env var |
| `username` | string | Option 3 | Username for auto-login authentication |
| `password` | string | Option 3 | Password for auto-login authentication (plaintext or MD5 hash) |
| `auth_url` | string | No | Explicit authentication URL override. Use for private deployments that should not follow host inference |
| `default_business_group` | string | No | Default business group ID for requests |
| `timeout` | number | No | API request timeout in seconds (default: 30) |

> **Note:** Auth URL inference is exact-match only:
> - `https://console.smartcmp.cloud/` → `https://account.smartcmp.cloud/bss-api/api/authentication`
> - `https://account.smartcmp.cloud/#/login` → `https://account.smartcmp.cloud/bss-api/api/authentication`
> - All other hosts default to `{host}/platform-api/login` unless `auth_url` is explicitly configured
>
> If your private deployment uses a `smartcmp.cloud` hostname or a non-standard
> login endpoint, set `auth_url` explicitly.

### Authentication Modes

| Mode | `auth_type` | Description | Required Config |
|------|-------------|-------------|-----------------|
| **SSO** | `cmp` | Embedded in CMP via Nginx reverse-proxy. Cookie auto-passed from browser. | `base_url` (hardcoded) |
| **User Token** | `user_token` | Platform-generated API token. Simplest standalone setup. | `base_url`, `user_token` |
| **Cookie** | `cookie` | Static cookie for server-to-server or testing. | `base_url`, `cookie` |
| **Credential** | `credential` | Username/password auto-login to CMP API. | `base_url`, `username`, `password` |
| **User Token** | `user_token` | Each user configures API token via AtlasClaw UI. | `base_url` |

> **Auto-detection:** The system detects mode by which fields are configured. No explicit `auth_type` needed in most cases.
> - SSO: Only `base_url` configured, no credentials in `.env`
> - User Token: `user_token` field present
> - Cookie: `cookie` field present
> - Credential: `username` + `password` fields present
> - User Token: Only `base_url` configured, user adds token in UI

## Configuration Examples

### Mode 1: SSO (CMP Embedded)

When AtlasClaw is deployed behind the same Nginx as CMP. No credentials in `.env`.

```json
{
  "service_providers": {
    "smartcmp": {
      "default": {
        "base_url": "https://172.16.0.81"
      }
    }
  }
}
```

> **Important:** `base_url` must be **hardcoded** (not `${CMP_URL}`). No CMP env vars in `.env`.

### Mode 2: User Token Authentication (Recommended for standalone)

Use a platform-generated user API token (e.g., `cmp_tk_v1_...`).

```json
{
  "service_providers": {
    "smartcmp": {
      "default": {
        "base_url": "${CMP_URL}",
        "user_token": "${CMP_API_TOKEN}"
      }
    }
  }
}
```

**`.env`:**
```bash
CMP_URL=https://cmp.example.com
CMP_API_TOKEN=cmp_tk_v1_2486ae574bd1020e6e72be503...
```

### Mode 3: Cookie Authentication

Use a pre-obtained CMP session cookie.

```json
{
  "service_providers": {
    "smartcmp": {
      "default": {
        "base_url": "${CMP_URL}",
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
        "base_url": "${CMP_URL}"
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
| `CMP_URL` | API Token, Cookie, Credential, User Token | SmartCMP platform URL. Auto-normalizes: adds `https://` and `/platform-api` if missing. |
| `CMP_API_TOKEN` | User Token | Platform-generated user API token (e.g., `cmp_tk_v1_...`). |
| `CMP_COOKIE` | Cookie | Full session cookie string from browser. |
| `CMP_USERNAME` | Credential | Login username. |
| `CMP_PASSWORD` | Credential | Login password (plaintext or MD5 hash). |

### Quick Setup by Mode

**SSO Mode:**
```bash
# No environment variables needed
```

**User Token Mode:**
```bash
CMP_URL=https://cmp.example.com
CMP_API_TOKEN=cmp_tk_v1_...
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
| `business-group` | Directory Query | Standalone listing of all business groups from the CMP UI directory endpoint | `smartcmp_list_all_business_groups` |
| `resource-pool` | Directory Query | Standalone listing of all resource pools from the CMP UI directory endpoint | `smartcmp_list_all_resource_pools` |
| `resource` | Directory Query | Standalone listing of all resources or all cloud hosts, plus one-host detail analysis via refresh-status | `smartcmp_list_resources`, `smartcmp_analyze_resource_detail` |
| `datasource` | Data Query | Read-only reference data queries and resource lookup by ID for service discovery and request workflows | `list_services`, `list_business_groups`, `list_resource_pools`, `list_resource` |
| `request` | Provisioning | Cloud resource provisioning requests | `list_components`, `submit` |
| `approval` | Workflow | Approval workflow management | `list_pending`, `approve`, `reject` |
| `alarm` | Monitoring | Alarm alert listing, analysis, and status operations | `list_alerts`, `analyze_alert`, `operate_alert` |
| `preapproval-agent` | Agent | Autonomous approval pre-review | Webhook-triggered, policy-based decisions |
| `request-decomposition-agent` | Agent | Transform natural-language requirements into request drafts | NL parsing, multi-skill orchestration |
| `cost-optimization` | Optimization | Analyze savings opportunities and execute platform-native fixes | `list_recommendations`, `analyze_recommendation`, `execute_optimization`, `track_execution` |
| `resource-compliance` | Analysis | Fetch resources by ID, normalize `type + properties`, and run componentType-driven cloud/software/OS compliance analysis | `list_resource`, `analyze_resource` |

### Core Skills

All example commands below assume your current directory is
`providers/SmartCMP-Provider/`.

#### business-group

List all business groups directly from the CMP UI directory endpoint. Use this
when the user says "查看所有业务组" or "列出所有业务组" and does not want to enter the
request workflow.

```bash
python skills/business-group/scripts/list_all_business_groups.py             # List all business groups
python skills/business-group/scripts/list_all_business_groups.py <keyword>   # Filter business groups
```

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
and inspect one cloud host by resource ID with the refresh-status endpoint.
Use this when the user says "查看我的云资源", "查看所有资源", "查看我的云主机",
"查看所有云主机", "查看某个云主机详情", or "分析某个云主机属性".

```bash
python skills/resource/scripts/list_resources.py                                     # List all resources
python skills/resource/scripts/list_resources.py --scope virtual_machines            # List all cloud hosts
python skills/resource/scripts/list_resources.py --scope virtual_machines --query-value production
python skills/resource/scripts/analyze_resource_detail.py <resource_id>              # Refresh and analyze one cloud host
```

#### datasource

Query reference data (read-only). Use before `request` skill to discover
available services, applications, templates, images, or resource details.
Standalone directory queries for all business groups and all resource pools now
have dedicated skills, and list-style resource browsing belongs to `resource`.

```bash
python skills/shared/scripts/list_services.py                         # List service catalogs
python skills/shared/scripts/list_business_groups.py <catalogId>      # Business groups
python skills/shared/scripts/list_resource_pools.py <bgId> <key> <type>  # Resource pools
python skills/shared/scripts/list_applications.py <bgId>              # Applications
python skills/shared/scripts/list_os_templates.py <osType> <resourceBundleId>  # OS templates
python skills/shared/scripts/list_images.py <resourceBundleId> <logicTemplateId> <cloudEntryTypeId>  # Images
python skills/shared/scripts/list_resource.py <resource_id>           # Resource details + normalized view
```

#### request

Submit cloud resource provisioning requests.

```bash
python skills/shared/scripts/list_services.py          # 1. Discover services
python skills/shared/scripts/list_components.py <key>  # 2. Get component schema
python skills/request/scripts/submit.py --file request_body.json  # 3. Submit request
```

#### approval

Manage approval workflows.

```bash
python skills/approval/scripts/list_pending.py                           # List pending approvals
python skills/approval/scripts/approve.py <id> --reason "Approved"       # Approve
python skills/approval/scripts/reject.py <id> --reason "Budget exceeded" # Reject
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
python skills/shared/scripts/list_resource.py <resource_id>             # Fetch resource details + normalized view
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

#### preapproval-agent

Autonomous agent for approval pre-review. Triggered by webhooks, analyzes request reasonableness, executes approve/reject decisions.

| Input | Type | Required | Description |
|-------|------|----------|-------------|
| `instance` | string | Yes | CMP provider instance name |
| `agent_identity` | string | Yes | Must be `agent-approver` |
| `approval_id` | string | Yes | Target approval identifier |
| `policy_mode` | string | No | Policy preset (default: `balanced`) |

#### request-decomposition-agent

Orchestration agent that transforms descriptive infrastructure demands into structured request candidates.

| Input | Type | Required | Description |
|-------|------|----------|-------------|
| `instance` | string | Yes | CMP provider instance name |
| `agent_identity` | string | Yes | Must be `agent-request-orchestrator` |
| `request_text` | string | Yes | Free-form requirement description |
| `submission_mode` | string | No | `draft` or `review_required` |

## Shared Scripts Reference

Located in `skills/shared/scripts/`, used across datasource, request, and
resource analysis workflows:

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

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| `401` / Token expired | Session cookie invalid | Refresh `CMP_COOKIE` env var |
| `[ERROR]` output | Script execution failed | Report to user; do NOT self-debug |

> All scripts output structured data with named metadata blocks such as `##..._START## ... ##..._END##` for programmatic parsing.
