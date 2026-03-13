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
  - request
  - infrastructure
  - cmp
  - CMP

capabilities:
  - Query cloud service catalogs and resource pools
  - Submit cloud resource provisioning requests
  - Manage approval workflows (approve/reject)
  - Autonomous approval pre-review agent
  - Transform natural language demands into cloud requests

use_when:
  - User wants to provision cloud resources or virtual machines
  - User asks about cloud service catalogs or resource pools
  - User needs to approve or reject provisioning requests
  - User wants to check pending approvals
  - User describes infrastructure needs in natural language

avoid_when:
  - User is asking about issue tracking (use Jira provider)
  - User wants to manage code or repositories (use Git provider)
  - User is asking about monitoring or alerts (use monitoring provider)
---

# SmartCMP Service Provider

SmartCMP cloud management platform service for resource provisioning, approval workflow management, and data source queries. Supports enterprise hybrid cloud environments.

## Quick Start

1. Configure authentication (choose one):
   - **Option 1**: Extract session cookie from SmartCMP web console (see [Cookie Extraction](#cookie-extraction))
   - **Option 2**: Set up auto-login credentials (recommended)
2. Set environment variables (see [Environment Variables](#environment-variables))
3. Use skills: `datasource` → `request` → `approval`

## Connection Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `base_url` | string | Yes | SmartCMP platform API URL (e.g., `https://cmp.corp.com/platform-api`) |
| `cookie` | string | Option 1 | Full authentication cookie string. Use `${CMP_COOKIE}` env var |
| `username` | string | Option 2 | Username for auto-login authentication |
| `password` | string | Option 2 | Password for auto-login authentication |
| `default_business_group` | string | No | Default business group ID for requests |
| `timeout` | number | No | API request timeout in seconds (default: 30) |

> **Note:** Auth URL is automatically inferred from `base_url`:
> - SaaS (`*.smartcmp.cloud`) → `account.smartcmp.cloud/bss-api/api/authentication`
> - Private deployment → `{host}/platform-api/login`

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
| `preapproval-agent` | Agent | Autonomous approval pre-review | Webhook-triggered, policy-based decisions |
| `request-decomposition-agent` | Agent | Transform demands into CMP requests | NL parsing, multi-skill orchestration |

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
