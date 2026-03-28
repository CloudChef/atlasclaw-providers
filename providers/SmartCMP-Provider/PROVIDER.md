---
# === Provider Identity ===
provider_type: smartcmp
display_name: SmartCMP
version: "1.0.0"

# === LLM Context Fields (for Skill Discovery) ===
keywords:
  - cloud
  - vm
  - virtual machine
  - provisioning
  - resource
  - approval
  - alarm
  - alert
  - monitoring
  - request
  - cost optimization
  - infrastructure
  - cmp
  - CMP

capabilities:
  - Query cloud service catalogs and resource pools
  - Submit cloud resource provisioning requests
  - Manage approval workflows (approve/reject)
  - List, analyze, and operate on SmartCMP alarm alerts
  - Autonomous approval pre-review agent
  - Transform natural language demands into cloud requests
  - List and analyze cost optimization recommendations
  - Execute SmartCMP-native remediation for cost optimization findings
  - Track cost optimization remediation progress

use_when:
  - User wants to provision cloud resources or virtual machines
  - User asks about cloud service catalogs or resource pools
  - User needs to approve or reject provisioning requests
  - User wants to check pending approvals
  - User wants to inspect, analyze, or operate on SmartCMP alarms
  - User describes infrastructure needs in natural language
  - User wants to review cost optimization recommendations or remediation progress
  - User wants to execute a SmartCMP-native day2 fix for a cost finding

avoid_when:
  - User is asking about issue tracking (use Jira provider)
  - User wants to manage code or repositories (use Git provider)
---

# SmartCMP Service Provider

SmartCMP cloud management platform service for resource provisioning, approval workflow management, alarm alert handling, cost optimization remediation, and data source queries. Supports enterprise hybrid cloud environments.

## Quick Start

1. Configure authentication (choose one):
   - **Option 1**: Extract session cookie from SmartCMP web console (see [Cookie Extraction](#cookie-extraction))
   - **Option 2**: Set up auto-login credentials (recommended)
2. Set environment variables (see [Environment Variables](#environment-variables))
3. Use skills: `datasource` → `request` → `approval` → `alarm` → `cost-optimization`

## Connection Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `base_url` | string | Yes | SmartCMP platform API URL (e.g., `https://cmp.corp.com/platform-api`) |
| `cookie` | string | Option 1 | Full authentication cookie string. Use `${CMP_COOKIE}` env var |
| `username` | string | Option 2 | Username for auto-login authentication |
| `password` | string | Option 2 | Password for auto-login authentication |
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
| `datasource` | Data Query | Read-only reference data queries | `list_services`, `list_business_groups`, `list_resource_pools` |
| `request` | Provisioning | Cloud resource provisioning requests | `list_components`, `submit` |
| `approval` | Workflow | Approval workflow management | `list_pending`, `approve`, `reject` |
| `alarm` | Monitoring | Alarm alert listing, analysis, and status operations | `list_alerts`, `analyze_alert`, `operate_alert` |
| `preapproval-agent` | Agent | Autonomous approval pre-review | Webhook-triggered, policy-based decisions |
| `request-decomposition-agent` | Agent | Transform demands into CMP requests | NL parsing, multi-skill orchestration |
| `cost-optimization` | Optimization | Analyze savings opportunities and execute SmartCMP-native fixes | `list_recommendations`, `analyze_recommendation`, `execute_optimization`, `track_execution` |

### Core Skills

#### datasource

Query SmartCMP reference data (read-only). Use before `request` skill to discover available resources.

```bash
python ../shared/scripts/list_services.py                          # List service catalogs
python ../shared/scripts/list_business_groups.py <catalogId>       # Business groups
python ../shared/scripts/list_resource_pools.py <bgId> <key> <type>  # Resource pools
python ../shared/scripts/list_applications.py <bgId>               # Applications
python ../shared/scripts/list_os_templates.py <poolId>             # OS templates
python ../shared/scripts/list_images.py <poolId>                   # Images
```

#### request

Submit cloud resource provisioning requests.

```bash
python ../shared/scripts/list_services.py          # 1. Discover services
python ../shared/scripts/list_components.py <key>  # 2. Get component schema
python scripts/submit.py --file request_body.json  # 3. Submit request
```

#### approval

Manage approval workflows.

```bash
python scripts/list_pending.py                              # List pending approvals
python scripts/approve.py <id> --reason "Approved"          # Approve
python scripts/reject.py <id> --reason "Budget exceeded"    # Reject
```

#### alarm

Inspect and analyze SmartCMP alarm alerts, and optionally operate on alert
status when appropriate.

```bash
python scripts/list_alerts.py                               # List current alerts
python scripts/analyze_alert.py <alert_id>                  # Analyze one alert
python scripts/operate_alert.py <alert_id> --action mute    # Change alert status
```

### Agent Skills

#### preapproval-agent

Autonomous agent for CMP approval pre-review. Triggered by webhooks, analyzes request reasonableness, executes approve/reject decisions.

| Input | Type | Required | Description |
|-------|------|----------|-------------|
| `instance` | string | Yes | CMP provider instance name |
| `agent_identity` | string | Yes | Must be `agent-approver` |
| `approval_id` | string | Yes | Target approval identifier |
| `policy_mode` | string | No | Policy preset (default: `balanced`) |

#### request-decomposition-agent

Orchestration agent that transforms descriptive infrastructure demands into structured CMP request candidates.

| Input | Type | Required | Description |
|-------|------|----------|-------------|
| `instance` | string | Yes | CMP provider instance name |
| `agent_identity` | string | Yes | Must be `agent-request-orchestrator` |
| `request_text` | string | Yes | Free-form requirement description |
| `submission_mode` | string | No | `draft` or `review_required` |

#### cost-optimization

Analyze SmartCMP optimization recommendations from discovery through remediation tracking. The analysis layer can explain common public-cloud best practices for AWS, Azure, and similar environments, but execution stays within SmartCMP and only uses the native day2 fix endpoint.

**Workflow:**
1. List recommendations with `list_recommendations.py`
2. Analyze one finding with `analyze_recommendation.py --id <violation_id>`
3. Execute the SmartCMP-native fix with `execute_optimization.py --id <violation_id>`
4. Track the remediation with `track_execution.py --id <violation_id>`

**Safety Boundary:**
- Public-cloud best-practice guidance is advisory only
- Execution uses `POST /compliance-policies/violations/day2/fix/{id}`
- Do not expect direct AWS or Azure API calls from this skill

## Shared Scripts Reference

Located in `skills/shared/scripts/`, used by `datasource` and `request` skills:

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

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| `401` / Token expired | Session cookie invalid | Refresh `CMP_COOKIE` env var |
| `[ERROR]` output | Script execution failed | Report to user; do NOT self-debug |

> All scripts output structured data with `##META##` blocks for programmatic parsing.
