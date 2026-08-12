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
  - recycle bin
  - permanent removal
  - 回收站
  - 永久卸除
  - approval
  - alarm
  - alert
  - monitoring
  - self-healing
  - cost optimization
  - finops
  - security compliance
  - security violation
  - lifecycle analysis
  - security posture
  - form schema
  - form designer
  - Angular form
  - 表单
  - 表单设计
  - infrastructure
  - cmp
  - CMP

capabilities:
  - Browse available services, business-group scopes such as tenant/租户/部门/BU/项目, resource pools, resources, cloud hosts, host details, templates, and other reference data before making a request
  - Start, stop, tear down, delete metadata for, or permanently remove existing cloud resources or deployments after resolving one exact SmartCMP target
  - Submit self-service requests for virtual machines, cloud resources, application environments, or ticket/work order services
  - View pending approvals and approve or reject service requests
  - List alerts, analyze alert context, and update alert status with remediation guidance
  - Turn natural language infrastructure needs into structured request drafts
  - Run automated pre-review for approval workflows
  - Review cost optimization recommendations and savings opportunities
  - Execute and track native day2 remediation for cost optimization findings
  - Fetch resource details by ID, reuse the shared normalized resource view, and analyze lifecycle, patch, security, and configuration risk
  - View the overall Security compliance posture and policy violations, analyze one Security violation, and explicitly mark its status FIXED without changing the resource
  - Generate, read, normalize, and refine SmartCMP Angular form schema JSON without saving forms to CMP

use_when:
  - User wants to request a VM, database, application environment, or other service catalog item
  - User wants to submit a ticket or work order for infrastructure or support needs
  - User asks what services, business groups, tenants, departments, projects, resource pools, resources, or cloud hosts are available before making a request
  - User wants to start, stop, tear down, delete metadata for, or permanently remove an existing cloud resource, virtual machine, or recycled deployment
  - User needs to approve or reject a request
  - User wants to check pending approvals
  - User wants to inspect, analyze, or operate on resource alarms
  - User describes infrastructure needs in natural language and wants them translated into request drafts
  - User wants to review cost optimization recommendations, savings opportunities, or remediation progress
  - User wants to execute a native day2 fix for a cost finding
  - User wants to analyze one existing resource by exact name or visible list index for Security risk and associated violations
  - User wants to view Security compliance, list or analyze Security violations, or mark a manually remediated violation FIXED
  - User wants to create, inspect, normalize, or improve a SmartCMP Angular form schema

avoid_when:
  - User wants generic issue tracking outside cloud service requests (use Jira provider)
  - User wants to manage code or repositories (use Git provider)
---

# SmartCMP Service Provider

Cloud management platform provider for self-service resource requests, approvals, alarms, cost optimization, resource Security analysis, and Security compliance violations across hybrid cloud environments.

## Quick Start

1. Configure authentication (choose one):
   - **Option 1**: Extract session cookie from SmartCMP web console (see [Cookie Extraction](#cookie-extraction))
   - **Option 2**: Set up auto-login credentials (recommended)
2. Set environment variables (see [Environment Variables](#environment-variables))
3. Use skills: `datasource` / `resource-pool` / `resource` → `request` → `approval` → `alarm` → `cost-optimization` / `security-compliance`

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
| `timeout` | number | No | API request timeout in seconds (default: 60) |

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

> **Selection rule:** `auth_type` accepts exactly one mode. Lists, ordered
> chains, and unknown values are rejected. When `auth_type` is omitted only for
> compatibility with an existing instance, the Provider applies its documented
> deterministic credential precedence; new configuration should always set an
> explicit mode.

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

> **Runtime behavior:** Password login is resolved by SmartCMP Provider for
> the current invocation. This integration does not maintain a separate
> AtlasClaw cookie-cache file.

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
| `resource` | Query + Analysis + Day2 Operation | List and inspect resources, analyze one resource's Security posture and associated violations, discover current-user operations, browse recycle-bin resources, and execute confirmed resource or permanent-removal operations | `smartcmp_list_all_resource`, `smartcmp_resource_detail`, `smartcmp_analyze_resource_security`, `smartcmp_list_resource_security_violations`, `smartcmp_list_resource_operations`, `smartcmp_operate_resource`, `smartcmp_list_recycled_resources`, `smartcmp_permanently_remove_recycled_resource` |
| `datasource` | Data Query | Read-only business-group, application, component, template and image directories | `smartcmp_list_all_business_groups`, `smartcmp_list_applications`, `smartcmp_list_components`, `smartcmp_query_logical_templates`, `smartcmp_query_images` |
| `request` | Provisioning | Cloud resource provisioning requests that select a logical template, then follow the generated instruction's physical-template or cloud-image branch | `smartcmp_list_services`, `smartcmp_get_request_catalog`, `smartcmp_list_logical_templates`, `smartcmp_list_physical_templates`, `smartcmp_list_images`, `smartcmp_submit_request`, `smartcmp_get_request_status` |
| `approval` | Workflow | Approval workflow management | `smartcmp_list_pending`, `smartcmp_get_request_detail`, `smartcmp_analyze_approval_request`, `smartcmp_approve`, `smartcmp_reject` |
| `alarm` | Monitoring | Alarm workflows plus component-model-driven resource health evidence | `smartcmp_list_alerts`, `smartcmp_analyze_alert`, `analyze_resource_health`, `smartcmp_operate_alert` |
| `preapproval-agent` | Agent | Autonomous approval pre-review | Webhook-triggered, policy-based decisions |
| `request-decomposition-agent` | Agent | Transform natural-language requirements into request drafts | NL parsing, multi-skill orchestration |
| `cost-optimization` | Optimization | Analyze savings opportunities and execute platform-native fixes | `smartcmp_list_cost_recommendations`, `smartcmp_analyze_cost_recommendation`, `smartcmp_analyze_resource_cost`, `smartcmp_execute_cost_optimization`, `smartcmp_track_cost_optimization` |
| `security-compliance` | Analysis + Status Handling | View the Security posture and violations, analyze one violation, and explicitly mark its status FIXED without remediating the resource | `smartcmp_get_security_overview`, `smartcmp_list_security_violations`, `smartcmp_analyze_security_violation`, `smartcmp_mark_security_violation_fixed` |
| `form-designer` | Form Design | Generate, read, normalize, and refine SmartCMP Angular form schema JSON without saving CMP forms | `smartcmp_read_current_form_schema`, `smartcmp_read_form_schema`, `smartcmp_design_form_schema` |

### Provider Skills

The names below are AtlasClaw Tools. Their `SKILL.md` entrypoints use
`file.py:method`; handler files are not standalone CLI commands.

#### resource-pool

List all resource pools directly from the CMP UI directory endpoint. Use this
when the user says "查询可用的资源池", "查询资源池", or "列出所有的资源池" and does
not want to enter the request workflow.

Use `smartcmp_list_all_resource_pools`, optionally with `query_value`.

#### resource

List all resources or all cloud hosts directly from the CMP UI list endpoint,
inspect one cloud host by resource ID with the `/nodes/{id}/view` evidence view, and
list or execute current-user no-parameter operations on existing resources or
their recycled deployments.
Use this when the user says "查看我的云资源", "查看所有资源", "查看我的云主机",
"查看所有云主机", "查看某个云主机详情", "分析某个云主机属性",
"查看可执行操作", "执行资源操作", "云资源开机", "云资源关机", "启动云主机",
"停止云主机", "卸除资源", "删除资源元数据", or "从回收站永久卸除资源".

Use `smartcmp_list_all_resource`, `smartcmp_resource_detail`,
`smartcmp_analyze_resource_security`,
`smartcmp_list_resource_security_violations`,
`smartcmp_list_resource_operations`, `smartcmp_operate_resource`,
`smartcmp_list_recycled_resources`, and
`smartcmp_permanently_remove_recycled_resource`.

Resource Security analysis combines bounded resource facts, LLM posture
inference, and CMP-confirmed associated violations by default. It keeps those
evidence types separate. Association scans root-category `SECURITY` and
post-filters exact `resourceId` matches; incomplete coverage cannot prove the
resource has no violations.

The operation list comes from `GET /nodes/{category}/{id}/resource-actions`
with the current user's SmartCMP credentials. It does not use resource-type
definition endpoints as executable-operation fallback.

Removal follows three separate SmartCMP operations:

1. `tear_down_in_resource`: active → stopped or torn down;
2. `delete_metadata_in_resource`: node metadata deleted, node
   `status=deleted`, and owning deployment placed in the recycle bin;
3. `permanently_delete_deployment`: recycled deployment permanently removed.

The user may locate the target with `resource_id`, `resource_name`,
`deployment_id`, or `deployment_name`. A name must resolve to exactly one
visible object. Zero matches or ambiguous matches fail before any write. When a
resource is supplied for permanent removal, resolve and retain its owning
recycle-bin deployment; do not assume a deployment contains only that resource.

Automatic exact-locator resolution scans at most 2,000 recycled deployments
and fails closed beyond that bound. For list browsing, `total`, `page`, and
`size` describe deployments; expanded `items` are resource rows and may contain
several rows for one deployment.

Permanent removal is irreversible and applies to the entire deployment. Before
submission, show the resolved deployment, warn that every resource in it is in
scope, and require explicit confirmation of that impact. Bind the confirmed
deployment ID and complete resource-ID set to the write, and fail before POST
if the freshly resolved scope differs. After submission,
verify the deployment reaches `deleted=true` and `state=DELETED` and exposes no
recycled actions. It may remain listed until SmartCMP's retention period
expires, after which disappearance is also a valid completed outcome. Node
`status=deleted` is expected after metadata deletion and cannot establish that
permanent removal completed.

#### datasource

Query reference data (read-only). Use for business-group scopes, applications,
components, templates, and images. Treat SmartCMP `business group` as the same scope users may
call tenant, 租户, 部门, BU, Department, 项目, or Project. Standalone
resource-pool queries still belong to `resource-pool`, and list-style resource
browsing belongs to `resource`.

Use `smartcmp_list_all_business_groups`, `smartcmp_list_applications`,
`smartcmp_list_components`, `smartcmp_query_logical_templates`, and
`smartcmp_query_images`.

#### request

Submit cloud resource provisioning requests.

Business-group scope rule: if the user only has one available business group,
do not assume that directly. First determine the actual scope choices through
datasource business-group listing. If datasource returns one business group,
use it silently. Ask the user to choose only when datasource returns multiple
business groups for the request.

Use `smartcmp_list_services`, `smartcmp_get_request_catalog`, the request
choice Tools, and `smartcmp_submit_request`.

#### approval

Manage approval workflows.

Use `smartcmp_list_pending`, `smartcmp_get_request_detail`,
`smartcmp_analyze_approval_request`, `smartcmp_approve`, and
`smartcmp_reject`.

#### alarm

Inspect and analyze alarm alerts, collect component-specific monitoring
evidence for LLM resource health analysis, and optionally operate on alert
status when appropriate. Resource health analysis does not require an alert and
does not use alarm-policy thresholds as its verdict.

Use `smartcmp_list_alerts`, `smartcmp_analyze_alert`,
`analyze_resource_health`, and `smartcmp_operate_alert`.

`analyze_resource_health` resolves the resource `componentType`, loads its
effective monitoring model, and queries only model-defined Prometheus metrics
that can be scoped to that resource. AWS VM, AWS RDS, vSphere VM, software,
hardware, and other components therefore share one flow without sharing a
hard-coded metric list. The handler emits facts and time-series statistics; the
AtlasClaw LLM supplies the `healthy`, `abnormal`, or `indeterminate` judgment.

#### cost-optimization

Analyze optimization recommendations from discovery through remediation
tracking. The analysis layer can explain common public-cloud best practices for
AWS, Azure, and similar environments, but execution stays within the platform
and only uses the native day2 fix endpoint.

**Workflow:**
1. List recommendations with `smartcmp_list_cost_recommendations`
2. Analyze one finding with `smartcmp_analyze_cost_recommendation`
3. Execute the native fix with `smartcmp_execute_cost_optimization`
4. Track remediation with `smartcmp_track_cost_optimization`

**Safety Boundary:**
- Public-cloud best-practice guidance is advisory only
- Execution uses `POST /compliance-policies/violations/day2/fix/{id}`
- Do not expect direct AWS or Azure API calls from this skill

#### security-compliance

View the overall Security compliance posture, browse policy-derived Security
violations, analyze one selected violation, and explicitly update its status
after manual remediation.

Use `smartcmp_get_security_overview` for Security-only policy, evaluation,
compliance, severity, violation, and trend facts. Use
`smartcmp_list_security_violations` for the collection and retain its real CMP
IDs in hidden metadata. Use `smartcmp_analyze_security_violation` for a fresh
detail read with best-effort policy/resource enrichment and manual remediation
guidance.

`smartcmp_mark_security_violation_fixed` requires explicit confirmation and is
a status-only write. It does not change the resource, does not advertise a
Day-2 repair, is submitted at most once, and re-reads the violation afterward.
The result always distinguishes `FIXED` from actual resource remediation.

Questions that start from a named or selected resource belong to the
`resource` Skill. Interactive workflows must not ask users for SmartCMP UUIDs;
Resource IDs and Violation IDs come from trusted object or list metadata.

#### form-designer

Generate or improve SmartCMP Angular form schema JSON. Existing form URLs are
read with `GET /forms/{id}` from the selected SmartCMP instance, and final
schemas are returned to AtlasClaw only. This skill does not submit service
requests and does not save, publish, update, or delete forms in CMP.

Use `smartcmp_read_form_schema` and `smartcmp_design_form_schema`.

### Agent Skills

#### Webhook robot execution

SmartCMP agent skills can run from AtlasClaw webhook dispatch with a scoped
robot profile. Configure the robot credential under the SmartCMP provider
instance and allowlist the exact provider-qualified skills that may use it.
Webhook payloads should pass `provider_instance` and `robot_profile`.

Use a SmartCMP `cmp_tk_*` token for the robot `provider_token` when available.
SmartCMP Provider sends those tokens as `Authorization: Bearer <token>`, and
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

## Skill handler organization

Multi-command Skills co-locate thin entrypoint methods in their own
`scripts/adapter.py`. A Skill may still have multiple Python files when a
helper has an independent caller or responsibility, such as embedded object
actions or current-page resolution. Single-Tool Designer Skills may retain one
direct handler. Authentication, HTTP, models, operations, and analysis live in
`src/smartcmp_provider/`.

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| `401` / Token expired | Selected SmartCMP session is invalid | Refresh the selected SmartCMP session |
| Tool error | Handler or SmartCMP operation failed | Report the normalized error; do not invent a fallback |

> Handlers return user-visible content and `_internal` metadata through the
> AtlasClaw Tool result contract.
