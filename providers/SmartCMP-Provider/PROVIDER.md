# SmartCMP Service Provider

SmartCMP cloud management platform service for resource provisioning, approval workflow management, and data source queries. Supports enterprise hybrid cloud environments.

## Connection Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `base_url` | string | Yes | SmartCMP platform API URL (e.g., `https://cmp.corp.com/platform-api`) |
| `cookie` | string | Yes | Full authentication cookie string. Use `${CMP_COOKIE}` env var |
| `default_business_group` | string | No | Default business group ID for requests |
| `timeout` | number | No | API request timeout in seconds (default: 30) |

### Authentication Modes

| Deployment | Auth Method | Parameters |
|------------|-------------|------------|
| **Enterprise** | Cookie-based Session | `cookie` (full session cookie from browser) |

**Note:** SmartCMP uses session-based authentication. Obtain the cookie string by logging into the SmartCMP web console and extracting the cookie from browser developer tools.

## Configuration Example

### SmartCMP Enterprise

```json
{
  "service_providers": {
    "smartcmp": {
      "prod": {
        "base_url": "https://cmp.corp.com/platform-api",
        "cookie": "${CMP_COOKIE}",
        "default_business_group": "47673d8d-6b3f-41e1-8ec0-c37e082d9020"
      },
      "dev": {
        "base_url": "https://192.168.176.150/platform-api",
        "cookie": "${CMP_DEV_COOKIE}"
      }
    }
  }
}
```

## Environment Variables

The SmartCMP skills read credentials from environment variables. Set these in `.env` or your shell profile:

**PowerShell:**
```powershell
$env:CMP_URL = "https://cmp.corp.com/platform-api"
$env:CMP_COOKIE = "<full cookie string>"
```

**Bash:**
```bash
export CMP_URL="https://cmp.corp.com/platform-api"
export CMP_COOKIE="<full cookie string>"
```

### Cookie Extraction

To obtain the `CMP_COOKIE` value:

1. Log into SmartCMP web console
2. Open browser Developer Tools (F12)
3. Go to Network tab
4. Refresh the page
5. Click any API request to `/platform-api/*`
6. Copy the full `Cookie` header value

## Provided Skills

| Skill | Description | Key Scripts |
|-------|-------------|-------------|
| `approval` | Approval workflow management | `list_pending.py`, `approve.py`, `reject.py` |
| `datasource` | Read-only data source queries | `list_services.py`, `list_business_groups.py`, `list_resource_pools.py` |
| `request` | Cloud resource provisioning requests | `submit.py` + shared data scripts |
| `preapproval-agent` | Autonomous pre-review agent for approvals | Orchestrates approval skills |
| `request-decomposition-agent` | Decomposes descriptive demands into CMP requests | Orchestrates datasource/request skills |

### Skill Details

#### approval

Manage SmartCMP approval workflows including querying pending approvals, approving requests, and rejecting requests.

**Commands:**
```bash
# List pending approvals
python scripts/list_pending.py

# Approve request with reason
python scripts/approve.py <approval_id> --reason "Approved per policy"

# Reject request with reason
python scripts/reject.py <approval_id> --reason "Budget exceeded"
```

#### datasource

Query and browse SmartCMP reference data as standalone read-only operations.

**Commands:**
```bash
# List available service catalogs
python ../shared/scripts/list_services.py

# List business groups for a catalog
python ../shared/scripts/list_business_groups.py <catalogId>

# List resource pools
python ../shared/scripts/list_resource_pools.py <bgId> <sourceKey> <nodeType>

# List applications
python ../shared/scripts/list_applications.py <bgId>

# List OS templates
python ../shared/scripts/list_os_templates.py <resourcePoolId>

# List images
python ../shared/scripts/list_images.py <resourcePoolId>
```

#### request

Submit cloud resource or application provisioning requests through SmartCMP platform.

**Commands:**
```bash
# List services → select → collect parameters → submit
python ../shared/scripts/list_services.py
python ../shared/scripts/list_components.py <sourceKey>
python scripts/submit.py --file request_body.json
```

#### preapproval-agent

Autonomous agent for CMP approval pre-review. Triggered by webhooks, analyzes request reasonableness, and executes approve/reject decisions.

**Inputs:**
- `instance`: CMP provider instance name
- `agent_identity`: Must be `agent-approver`
- `approval_id`: Target approval identifier
- `policy_mode`: Policy preset (default: `balanced`)

#### request-decomposition-agent

Orchestration agent that transforms descriptive infrastructure demands into structured CMP request candidates.

**Inputs:**
- `instance`: CMP provider instance name
- `agent_identity`: Must be `agent-request-orchestrator`
- `request_text`: Free-form requirement description
- `submission_mode`: `draft` or `review_required`

## Shared Scripts

Located in `skills/shared/scripts/`, used by both `datasource` and `request` skills:

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

- On `401` / token expired: Refresh the `CMP_COOKIE` environment variable
- On `[ERROR]` output: Report to user immediately; do NOT self-debug
- All scripts output structured data with `##META##` blocks for programmatic parsing
