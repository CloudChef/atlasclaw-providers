# SmartCMP Provider

SmartCMP Provider is a service provider module for AtlasClaw, integrating with SmartCMP cloud
management platform. It supports context-aware page actions, cloud resource provisioning,
approval workflows, resource analysis and operations, alarm and health analysis, data queries,
cost optimization, form schema design, and resource compliance analysis.

## Embedded Assistant Context

SmartCMP's AtlasClaw integration dynamically follows SmartCMP navigation and deterministically matches
twelve normalized page patterns through `assistant_context/routes.json`:

- triggered alarm detail;
- cost optimization recommendation detail;
- pending approval detail;
- service catalog request;
- My Application request detail;
- cloud resource detail;
- virtual-machine detail;
- form definition edit;
- form definition design;
- script definition edit;
- cost-optimization policy edit;
- blueprint component edit.

The five editor routes bind one owning Domain Skill per page. Their current-object Tools read the
exact server-owned Context object with the request user's Cookie. Each owning Skill uses that
source to draft complete replacement content for manual copying. The Tools do not put editor
content into the Context object, and the workflow does not call SmartCMP write APIs.

The request-detail template is
`/main/new-process/myApplication/{application_type}/{request_id}`. Every newer SmartCMP page generation
is matched again, so the floating assistant clears stale Context and follows the current SmartCMP
object without using an LLM to guess the page. The manifest maps each path to one existing
`smartcmp:*` Skill and declares one Provider-level Context entrypoint,
`assistant_context/resolve.py:resolve_context`. AtlasClaw validates and caches this
explicit async callable when the Embed Integration loads, so page navigation does
not start a new Provider script process.

A new page for an existing object type needs only a route entry when it keeps that object's
existing owning Domain Skill. A genuinely new SmartCMP object API extends the Provider-level read
adapter and adds its dynamic action builder to the owning Domain Skill; it does not require changes
to AtlasClaw Core/UI or the Enterprise System integration. Routes must not remap an object to an unrelated Skill because the
Snapshot's executable Tools and the object's actions must share the same owner.

Context resolution requires the explicitly configured
Provider type/instance and accepts only the request-scoped
`CloudChef-Authenticate` Cookie for the explicitly selected Provider instance. It ignores Provider
tokens, user tokens, configured cookies, and username/password credentials, and never auto-logs in.
The resolver delegates Cookie semantics, URL normalization, timeout, HTTP,
SmartCMP object reads, and ACL checks to SmartCMP Provider; it has no separate
request-user transport or authentication implementation.
It returns minimal objects containing only approved display fields and does not introduce a separate login, token, credential,
role, menu, ACL, or database-permission flow.

Successful Context resolution returns the current page object plus Provider-declared
`object_actions`. The route's exact existing `skill_ref` still limits Agent execution to that
Skill's currently registered and authorized Tools, but the complete Tool inventory remains an
internal server-side capability and is never rendered as Context buttons. Each Domain Skill owns
the actions for the objects it returns and derives them from the current object state. Its Chat
Tool results and Context resolver reuse that same builder, so both surfaces present the same
labels, tones, prompts, and confirmation metadata. Adding another route for an existing object
type reuses its Domain Skill action definition; a new object type adds its action definition with
the Domain Skill rather than to a central object-type table. Returning no object actions is valid
and renders no action buttons. Existing business Skill execution and authorization semantics
remain unchanged.

SmartCMP Embedded mode exposes two independent UI surfaces. The menu surface is
the full AtlasClaw conversation and never attaches SmartCMP page Context. The
floating surface is compact and uses the routes above to follow SmartCMP
navigation. Both surfaces receive the same Enterprise System Cookie
authentication context, so they resolve the same signed-in SmartCMP user and
reuse that user's SmartCMP access and permissions. They can also share the AtlasClaw-origin active Chat
Session selected during bootstrap; neither surface is an expanded or collapsed
form of the other.

SmartCMP only needs to add and embed the menu Agent entry for the menu surface;
that path does not require a page-change bridge. To enable the floating
assistant and dynamic Context, SmartCMP additionally manages the
launcher/iframe, constructs the floating URL with its exact Origin and a fresh
nonce, and sends normalized router paths with monotonically increasing
generations. SmartCMP does not call AtlasClaw Context, Agent Run, or Tool APIs
for the iframe and does not duplicate AtlasClaw confirmation UI.

When AtlasClaw selects SmartCMP as its single default Embed Provider, AtlasClaw Core loads
`assistant_context/routes.json` by convention for the floating surface. The Provider package does
not declare a configurable manifest path, and SmartCMP embedding messages do not select a Provider
instance.

The browser Cookie remains request-scoped and runtime-only. Static credentials
used by other AtlasClaw or standalone MCP workflows stay in their configured
credential stores. Neither form of credential belongs in route manifests or
embedding messages.

### Embedded Cookie Configuration

Embedded mode uses the SmartCMP browser session rather than the standalone
credentials described later in this README. Configure all three bindings in
AtlasClaw:

```json
{
  "auth": {
    "provider": "host_cookie",
    "host_cookie": {
      "cookie_name": "CloudChef-Authenticate",
      "subject_cookie_name": "userLoginId"
    }
  },
  "service_providers": {
    "smartcmp": {
      "default": {
        "base_url": "https://smartcmp.example.com",
        "auth_type": "cookie"
      }
    }
  },
  "embed_integration": {
    "provider_type": "smartcmp",
    "provider_instance": "default"
  }
}
```

AtlasClaw `host_cookie` authentication resolves the signed-in user. The
configured SmartCMP HostApp Provider then receives the same request-scoped
Enterprise System Cookie through `auth_type: "cookie"` when it reads SmartCMP
objects or executes Domain Skills. See the [AtlasClaw Core Embedded integration
guide](https://github.com/CloudChef/atlasclaw/blob/main/docs/EMBED-INTEGRATION.md)
for the complete Cookie and message contract.

## Features

- **Resource Requests** - Submit cloud resource or application provisioning requests and query submitted request status by Request ID
- **Approval Management** - View pending approval tasks, approve requests, or reject requests
- **Alarm and Resource Health** - List and analyze alerts, collect component-specific resource monitoring evidence, and run explicit alert status operations
- **Directory Queries** - List business-group scopes such as tenant/租户/部门/BU/项目, resource pools, resources, or cloud hosts from the same UI directory endpoints used by CMP
- **Resource Analysis and Operations** - Dynamically analyze one resource across alerts, monitoring health, compliance risk, and cost optimization, or run current-user executable day2 operations
- **Data Queries** - Query service catalogs, applications, templates, images, and other reference data
- **Intelligent Agents** - Automated pre-approval and request decomposition capabilities
- **Cost Optimization** - Review optimization recommendations or directly analyze a resource's optimization potential, execute SmartCMP-native fixes for existing findings, and track remediation progress
- **Resource Compliance** - Resolve any CMP resource, build a bounded and redacted fact profile, and let the LLM perform one generic compliance analysis without configured CMP rules
- **Form Designer** - Generate, read, normalize, and refine SmartCMP Angular form schemas without saving changes to CMP
- **Script Designer** - Read the current script definition and return a complete same-language replacement for manual review
- **Optimization Policy Designer** - Read the current cost-optimization policy and return complete replacement fields and rule content
- **Component Script Designer** - Read one current component file, apply resource-type-specific rules, and return the complete file without changing the component

## AtlasClaw Provider configuration

Configure SmartCMP through the AtlasClaw Provider instance contract described
in [PROVIDER.md](PROVIDER.md). Supported modes are user token, provider token,
Cookie, and username/password credential. AtlasClaw selects the instance and
passes request-scoped Context to the Skill handler; SmartCMP Provider owns
credential interpretation, login, and API headers.

The Skill handler files are not supported as direct command-line programs and
do not implement a separate `.env` selection order or local Cookie cache.

### Quick Verification

Verify the co-located SmartCMP Provider package without connecting to CMP:

```bash
PYTHONPATH=src python -c "import smartcmp_provider; print(smartcmp_provider.__name__)"
python -m pytest -q
```

## Skill Modules

The names below are AtlasClaw Tools. Their `SKILL.md` entrypoints use
`file.py:method`; the handler files are not standalone CLI commands.

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
- For "check my request status" or "has my submitted request been approved",
  use `smartcmp_get_request_status`.

**Examples:**

- List: `smartcmp_list_pending`
- Approve: `smartcmp_approve`
- Reject: `smartcmp_reject`

### alarm - Alarm and Resource Health Management

Inspect and analyze SmartCMP alarms directly in this provider, or analyze one
resource independently from alerts using its component monitoring model. Use
`smartcmp_operate_alert` only when an explicit status action is intended.

**Use Cases:**
- List current alarm alerts
- Analyze a specific alert with structured recommendations
- Collect component-specific Prometheus evidence for LLM resource health analysis
- Operate on alert status using English actions such as `mute`, `resolve`, or `reopen`

**Tools:** `smartcmp_list_alerts`, `smartcmp_analyze_alert`,
`analyze_resource_health`, and `smartcmp_operate_alert`.

Resource health analysis uses the resolved resource `componentType` to load
the component's effective monitoring model and query its own Prometheus metric
definitions. It never substitutes a generic VM metric list. The handler returns
evidence only; the AtlasClaw LLM determines whether the observed resource is
healthy, abnormal, or indeterminate.

### datasource - Data Source Queries

Read-only queries for SmartCMP reference data. Standalone
business-group scope discovery belongs here, while standalone resource-pool and
resource browsing still use their dedicated skills.

**Supported Queries:**
- Business-group scopes such as tenant / 租户 / 部门 / BU / Project
- Application lists
- OS templates
- Images

**Examples:**

- `smartcmp_list_all_business_groups`
- `smartcmp_list_applications`
- `smartcmp_list_components`
- `smartcmp_query_logical_templates`
- `smartcmp_query_images`

Catalog discovery is owned by `request`; resource browsing is owned by
`resource`.

### resource-pool - Resource Pool Directory

Read-only listing of all SmartCMP resource pools through the standalone CMP UI
directory endpoint.

**Use Cases:**
- 查询可用的资源池
- 查询资源池
- 列出所有的资源池
- Query resource pools by keyword without entering the request workflow

Use `smartcmp_list_all_resource_pools`, optionally with `query_value`.

### resource - Resource Browsing, Analysis & Operations

Browse, inspect, comprehensively analyze, list current-user executable
operations, and operate on SmartCMP resources or cloud hosts.

**Use Cases:**
- 查看我的云资源
- 查看所有资源
- 查看我的云主机
- 查看所有云主机
- 查看某个云主机详情
- 分析某个云主机属性
- 综合分析一个资源的告警、运行健康、合规和费用优化
- 查看云主机可执行操作
- 执行云主机操作
- 把某个云资源关机
- 把某个云主机开机
- Query resources or virtual machines by keyword without entering the request workflow

**Tools:** `smartcmp_list_all_resource`, `smartcmp_resource_detail`,
`smartcmp_list_resource_operations`, and `smartcmp_operate_resource`.

The dynamic **Analyze** action on a resolved resource page uses the `resource`
Skill as a coordinator. It keeps one exact internal resource target and calls
the existing resource-scoped analyzers for current and recent alerts,
component-model-driven Prometheus health, generic compliance risk, and
resource-level cost optimization. It then synthesizes the four evidence sets
without changing the resource. A failure or evidence gap in one dimension does
not prevent the other read-only dimensions from completing.

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
- Use `smartcmp_get_request_status` for questions such as "check my request
  status" or "has my request been approved?"
- Input is the user-visible Request ID returned by submission, such as `RES20260501000095` or `TIC20260316000001`.
- SmartCMP Provider searches for an exact request-number match and fetches
  its detail.
- The Tool returns structured fields such as `state`, `statusCategory`,
  `approvalPassed`, `currentStep`, `currentApprover`, `provisionState`,
  `error`, and `updatedAt`.
- The agent should explain those fields in the current user's message language;
  the handler does not hard-code a localized approval sentence.

**Status Semantics:**
- `APPROVAL_PENDING` means approval has not passed yet.
- `APPROVAL_REJECTED` and `APPROVAL_RETREATED` mean approval did not pass.
- `STARTED`, `TASK_RUNNING`, `WAIT_EXECUTE`, and `FINISHED` mean approval passed or the request entered a later execution stage.
- `INITIALING`, `INITIALING_FAILED`, `FAILED`, and `CANCELED` should be reported as the current state without claiming approval or rejection.

**Main Tools:** `smartcmp_list_services`, `smartcmp_get_request_catalog`,
`smartcmp_submit_request`, and `smartcmp_get_request_status`.

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

When the selected token starts with `cmp_tk_`, SmartCMP Provider sends it as
`Authorization: Bearer <token>`. Approval tools use the selected robot
credential. In webhook robot dispatches that do not forward SmartCMP user
cookies, request submission resolves the SmartCMP actor from that same robot
credential, so SmartCMP audit trails show the configured robot/admin account.

### cost-optimization - Cost Optimization

List SmartCMP optimization recommendations, analyze savings opportunities, directly assess one
resource's optimization potential, execute SmartCMP-native day2 fixes for existing findings, and
track remediation progress.

**Workflow:**
1. For an existing recommendation, call
   `smartcmp_list_cost_recommendations`, then
   `smartcmp_analyze_cost_recommendation`
2. For any supported resource, call `smartcmp_analyze_resource_cost` even
   when no recommendation exists
3. Correlate enabled applicable policies, their latest exact resource executions, active
   violations, billing facts, and missing evidence
4. Keep platform-confirmed findings separate from `llm_potential`; no violation does not prove
   that the resource is already optimized
5. Execute `smartcmp_execute_cost_optimization` only for an existing SmartCMP
   finding
6. Check remediation state with `smartcmp_track_cost_optimization`

**Safety Boundary:**
- Public-cloud best-practice guidance is advisory only
- Resource-first analysis is read-only and never runs a policy or remediation
- Exact saving amounts are reported only when SmartCMP supplies them
- Model-only opportunities cannot create repair actions
- Execution uses `POST /compliance-policies/violations/day2/fix/{id}`
- No direct AWS or Azure API calls are made by this skill

### resource-compliance - Resource Compliance

Fetch one or more existing SmartCMP resources by exact resource name or visible
list selection, build one provider-neutral evidence profile, and let the LLM
analyze operational state and compliance risk.

**Workflow:**
1. Resolve the resource by visible name or latest resource-list index; keep SmartCMP UUIDs internal
2. Retrieve the canonical CMP resource view and its normalized `type + properties` evidence
3. Build a bounded, redacted `resourceProfile` for any component type
4. Emit `analysisTargets: ["llm:generic_cloud_resource"]` and the LLM contract
5. Let the LLM distinguish confirmed facts, inference, and missing evidence without using CMP compliance rules or external product adapters
6. Emit a non-judgmental summary and a stable `##RESOURCE_COMPLIANCE_START##` JSON block

Use `smartcmp_list_all_resource` to establish a visible selection and
`smartcmp_analyze_resource_compliance` to analyze the selected resource.

Interactive resource-compliance workflows should not ask users for SmartCMP
UUIDs. Resource IDs are internal API and webhook compatibility values only.

Representative output fields:
```json
{
  "results": [
    {
      "analysisTargets": ["llm:generic_cloud_resource"],
      "analysisStatus": "evidence_collected",
      "resourceProfile": {},
      "evidenceCoverage": {}
    }
  ]
}
```

**Safety Boundary:**
- The Tool collects evidence; the LLM provides the final advisory judgment
- CMP state, absence of findings, or absence of a product rule is not proof of compliance
- Patch, lifecycle, and CVE claims remain inferred or missing unless the payload contains authoritative evidence
- No remediation APIs are called by this skill

### form-designer - SmartCMP Form Schema Design

Generate new SmartCMP Angular form schemas or refine existing schemas from
SmartCMP form edit URLs. This skill is read-only with respect to CMP
persistence: it may call `GET /forms/{id}` to read source schema, but it never
saves, updates, publishes, submits, or deletes CMP data.

**Workflow:**
1. For existing forms, call `smartcmp_read_form_schema`
2. Generate or modify the schema JSON according to the user's requirements
3. Normalize the schema with `smartcmp_design_form_schema`
4. Return the final schema JSON and a short change summary for manual copy/review

## Directory Structure

```
SmartCMP-Provider/
├── pyproject.toml                   # smartcmp-provider distribution
├── src/
│   └── smartcmp_provider/          # Importable Provider auth, HTTP, models and operations
├── skills/
│   ├── approval/scripts/
│   │   ├── adapter.py               # Five approval Tool handlers
│   │   └── _approval_object_actions.py
│   ├── alarm/scripts/
│   │   ├── adapter.py               # Four alarm/health Tool handlers
│   │   └── _alarm_object_actions.py
│   ├── ...                          # Other Skill-local adapters/helpers
│   └── shared/
│       └── scripts/
│           ├── _provider_bootstrap.py
│           ├── _atlasclaw_adapter.py
│           ├── _current_page_object.py
│           └── _object_actions_common.py
├── test/                            # Provider test suite
├── PROVIDER.md                      # Provider configuration docs
└── README.md                        # This file
```

## Skill handler organization

Multi-command Skills co-locate thin entrypoint methods in their own
`scripts/adapter.py`. A Skill may still have multiple Python files when a
helper has an independent caller or responsibility, such as embedded object
actions or current-page resolution. Single-Tool Designer Skills may retain one
direct handler. There are no one-command forwarding modules and no
subprocess-based cross-Skill proxies.

## Notes

1. **Authentication** - AtlasClaw handlers pass the selected Instance and
   Cookie/user/robot Authentication Context to SmartCMP Provider.
2. **Cookie Expiration** - If you encounter `401` errors, refresh the selected
   SmartCMP session.
3. **Output Format** - Handlers return visible content plus `_internal`
   metadata for programmatic use.
4. **Alarm and Health Coverage** - Alert workflows and component-model-driven resource health analysis are supported directly by the `alarm` skill
5. **Error Handling** - On `[ERROR]` output, report to user immediately; do NOT self-debug
6. **Resource Compliance** - `resource-compliance` builds one bounded CMP fact profile for every resource type and hands it to the LLM; it does not use configured CMP policy results or product-specific external adapters
7. **Localized Responses** - Handlers return stable fields and metadata.
   Agents explain results in the current user's message language.
8. **No Raw Day2 Dumps** - Resource operations should not print raw request payloads or raw SmartCMP response details after a successful submission.
9. **Form Designer Is Read-Only** - `form-designer` outputs schema JSON for manual review/copy only. It must not save or update CMP forms.
10. **Editor Skills Are Read-Only** - Script, optimization-policy, and component-script designers read only the exact Context-bound saved object and return manual replacement content; they do not save, publish, execute, or deploy it.

## Related Documentation

- [PROVIDER.md](PROVIDER.md) - Detailed connection parameters and configuration
- `SKILL.md` in each skill module - Skill usage guides
- `references/` directory in each skill module - Workflow and parameter documentation
