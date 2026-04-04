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
  - Browse available services, business groups, resource pools, templates, and other reference data before making a request
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
  - User asks what services, business groups, or resource pools are available before making a request
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
3. Use skills: `datasource` → `request` → `approval` → `alarm` → `cost-optimization` → `resource-compliance`

## Connection Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `base_url` | string | Yes | SmartCMP platform API URL (e.g., `https://cmp.corp.com/platform-api`) |
| `cookie` | string | Option 1 | Full authentication cookie string. Use `${CMP_COOKIE}` env var |
| `username` | string | Option 2 | Username for auto-login authentication |
| `password` | string | Option 2 | Password for auto-login authentication (plaintext or MD5 hash) |
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

| Mode | Auth Method | Required Parameters |
|------|-------------|---------------------|
| **Option 1** | Cookie-based Session (Manual) | `base_url`, `cookie` |
| **Option 2** | Auto-Login (Recommended) | `base_url`, `username`, `password` |

> **Note:** Option 1 requires manually extracting the cookie from browser. Option 2 automatically obtains and caches cookies with 30-minute TTL.
> The local `.atlasclaw/users/default/sessions/` cache is a runtime artifact and should not be committed.

## Configuration Example

### Option 1: Cookie-based Authentication

```json
{
  "service_providers": {
    "smartcmp": {
      "prod": {
        "base_url": "https://cmp.corp.com/platform-api",
        "auth_url": "https://cmp.corp.com/platform-api/login",
        "cookie": "${CMP_COOKIE}",
        "default_business_group": "47673d8d-6b3f-41e1-8ec0-c37e082d9020"
      }
    }
  }
}
```

### Option 2: Auto-Login Authentication (Recommended)

```json
{
  "service_providers": {
    "smartcmp": {
      "prod": {
        "base_url": "https://cmp.corp.com/platform-api",
        "auth_url": "https://cmp.corp.com/platform-api/login",
        "username": "${CMP_USERNAME}",
        "password": "${CMP_PASSWORD}",
        "default_business_group": "47673d8d-6b3f-41e1-8ec0-c37e082d9020"
      }
    }
  }
}
```

> **Note:** Auth URL is automatically inferred - no need to configure.

## Environment Variables

Set credentials in `.env` or shell profile. Two authentication options are supported:

### Option 1: Direct Cookie (Manual)

**PowerShell:**
```powershell
# CMP_URL auto-normalizes: adds https:// and /platform-api if missing
$env:CMP_URL = "<your-cmp-host>"
$env:CMP_COOKIE = "<full cookie string>"
```

**Bash:**
```bash
export CMP_URL="<your-cmp-host>"
export CMP_COOKIE="<full cookie string>"
```

### Option 2: Auto-Login (Recommended)

Automatically obtains and caches cookies (30-minute TTL). Auth URL is auto-inferred.

**PowerShell:**
```powershell
$env:CMP_URL = "<your-cmp-host>"
$env:CMP_USERNAME = "<username>"
$env:CMP_PASSWORD = "<password>"
```

**Bash:**
```bash
export CMP_URL="<your-cmp-host>"
export CMP_USERNAME="<username>"
export CMP_PASSWORD="<password>"
# Optional: override the inferred login endpoint
export CMP_AUTH_URL="<explicit-login-url>"
```

> **Performance Note:** Auto-login caches cookies at `.atlasclaw/users/default/sessions/smartcmp_cookie_cache.json` with 30-minute TTL. Subsequent executions reuse cached cookies, avoiding repeated login requests.

### Cookie Extraction

1. Log into SmartCMP web console
2. Open browser Developer Tools (F12)
3. Go to **Network** tab → Refresh page
4. Click any `/platform-api/*` request
5. Copy the full `Cookie` header value

## Provided Skills

| Skill | Type | Description | Key Operations |
|-------|------|-------------|----------------|
| `datasource` | Data Query | Read-only reference data queries and resource lookup by ID | `list_services`, `list_business_groups`, `list_resource_pools`, `list_resource` |
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

#### datasource

Query reference data (read-only). Use before `request` skill to discover available resources.

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
