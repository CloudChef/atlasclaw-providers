# SmartCMP Provider

SmartCMP Provider is a service provider module for AtlasClaw, integrating with SmartCMP cloud management platform. It supports cloud resource provisioning, approval workflow management, and data source queries.

## Features

- **Resource Requests** - Submit cloud resource or application provisioning requests via SmartCMP
- **Approval Management** - View pending approvals, approve or reject requests
- **Data Queries** - Query service catalogs, business groups, resource pools, and other reference data
- **Intelligent Agents** - Automated pre-approval and request decomposition capabilities

## Quick Start

### Environment Configuration

SmartCMP Provider supports two deployment modes. Configure in `.env` file at project root:

> **Note:** Auth URL is automatically inferred from `CMP_URL` - no manual configuration needed!
>
> | Environment | Auth URL (auto-inferred) |
> |-------------|--------------------------|
> | `console.smartcmp.cloud` | `account.smartcmp.cloud/bss-api/api/authentication` |
> | `account.smartcmp.cloud` | `account.smartcmp.cloud/bss-api/api/authentication` |
> | Private deployment | `{CMP_URL}/platform-api/login` |
>
> If your private deployment uses a non-standard login endpoint, set `CMP_AUTH_URL` explicitly to avoid host-based inference.

---

#### Mode 1: SaaS Environment (Auto-Login)

For SmartCMP SaaS platform:

```bash
# .env file

# Business API domain (auto-appends /platform-api)
CMP_URL=https://console.smartcmp.cloud

# Auto-login credentials (Cookie will be obtained automatically)
CMP_USERNAME=your_email@company.com
CMP_PASSWORD=your_password_md5_hash

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

# Option A: Auto-login (Recommended)
CMP_USERNAME=admin
CMP_PASSWORD=your_password_md5_hash

# Optional: Override login endpoint explicitly
# CMP_AUTH_URL=https://your-private-cmp/platform-api/login

# Option B: Direct Cookie (if auto-login fails)
# CMP_COOKIE=XXL_JOB_LOGIN_IDENTITY=xxx; CloudChef-Authenticate=xxx; tenant_id=xxx; ...
```

---

### Configuration Priority

1. If `CMP_COOKIE` is set → Use directly
2. If `CMP_COOKIE` is empty → Check local cache (`~/.atlasclaw/cache/smartcmp_session.json`)
3. If cache missing/expired → Auto-login using `CMP_USERNAME` + `CMP_PASSWORD`

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
# Run from project root
python -c "
import sys; sys.path.insert(0, '.atlasclaw/providers/SmartCMP-Provider/skills/shared/scripts')
from _common import get_cmp_config
url, cookie = get_cmp_config()
print(f'URL: {url}')
print(f'Cookie: {cookie[:50]}...' if len(cookie) > 50 else f'Cookie: {cookie}')
"

## Skill Modules

### approval - Approval Management

Manage SmartCMP approval workflows including querying pending approvals, approving requests, and rejecting requests.

**Use Cases:**
- View pending approval list
- Batch approve or reject requests
- Approval operations with reasons

**Examples:**
```bash
# List pending approvals
python scripts/list_pending.py

# Approve request
python scripts/approve.py <approval_id> --reason "Approved per policy"

# Reject request
python scripts/reject.py <approval_id> --reason "Budget exceeded"
```

### datasource - Data Source Queries

Read-only queries for SmartCMP reference data, used for browsing and discovering available resources.

**Supported Queries:**
- Service catalogs
- Business groups
- Resource pools
- Application lists
- OS templates
- Images

**Examples:**
```bash
# List service catalogs
python ../shared/scripts/list_services.py

# List business groups
python ../shared/scripts/list_business_groups.py <catalogId>

# List resource pools
python ../shared/scripts/list_resource_pools.py <bgId> <sourceKey> <nodeType>
```

### request - Resource Requests

Submit cloud resource or application provisioning requests through SmartCMP platform with interactive parameter collection.

**Workflow:**
1. List available service catalogs
2. Select service and get component type
3. Collect parameters interactively (business group → resource pool → OS template, etc.)
4. Build request body and confirm
5. Submit request

**Examples:**
```bash
# List services
python ../shared/scripts/list_services.py

# Get component type
python ../shared/scripts/list_components.py resource.iaas.machine.instance.abstract

# Submit request
python scripts/submit.py --file request_body.json
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

## Directory Structure

```
SmartCMP-Provider/
├── skills/
│   ├── approval/           # Approval management skill
│   │   ├── scripts/        # Approval scripts
│   │   ├── references/     # Reference docs
│   │   └── SKILL.md
│   ├── datasource/         # Data source query skill
│   │   ├── references/
│   │   └── SKILL.md
│   ├── request/            # Resource request skill
│   │   ├── scripts/        # Submit scripts
│   │   ├── references/
│   │   └── SKILL.md
│   ├── preapproval-agent/  # Pre-approval agent
│   │   ├── references/
│   │   └── SKILL.md
│   ├── request-decomposition-agent/  # Request decomposition agent
│   │   ├── references/
│   │   └── SKILL.md
│   └── shared/scripts/     # Shared scripts
│       ├── list_services.py
│       ├── list_business_groups.py
│       ├── list_components.py
│       ├── list_resource_pools.py
│       ├── list_applications.py
│       ├── list_os_templates.py
│       ├── list_cloud_entry_types.py
│       └── list_images.py
├── PROVIDER.md             # Provider configuration docs
└── README.md               # This file
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

## Notes

1. **Environment Variables** - All scripts read connection info from `CMP_URL` and `CMP_COOKIE` environment variables
2. **Cookie Expiration** - If you encounter `401` errors, refresh and update the Cookie
3. **Output Format** - Script output includes `##META##` blocks for programmatic parsing
4. **Error Handling** - On `[ERROR]` output, report to user immediately; do NOT self-debug

## Related Documentation

- [PROVIDER.md](PROVIDER.md) - Detailed connection parameters and configuration
- `SKILL.md` in each skill module - Skill usage guides
- `references/` directory in each skill module - Workflow and parameter documentation
