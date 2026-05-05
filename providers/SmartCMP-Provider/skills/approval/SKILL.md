---
name: "approval"
description: "Approval workflow skill. View pending approval tasks and approve or reject service requests."
provider_type: "smartcmp"
instance_required: "true"

# === LLM Context Fields ===
triggers:
  - pending approvals
  - list approvals
  - approval detail
  - approve request
  - reject request
  - approval
  - reject
  - 待审批
  - 查看待审批
  - 查看审批详情
  - 审批通过
  - 审批拒绝
  - 同意
  - 同意审批
  - 批准
  - 批准审批
  - 通过审批

use_when:
  - User wants to view pending approval items
  - User wants to inspect one pending SmartCMP approval item in detail
  - User needs to approve or reject service requests
  - User asks about their approval queue or approval workflow tasks
  - User asks for the detail of a pending approval task by ticket/workflow/request/task/process identifier
  - User asks for SmartCMP 待审批、工单详情、审批详情

avoid_when:
  - User wants to provision new resources (use request skill)
  - User wants to check the status of their own submitted request or whether it has been approved (use request skill `smartcmp_get_request_status`)
  - User wants to query reference data (use datasource skill)
  - User describes infrastructure needs in natural language (use request-decomposition-agent)

examples:
  - "Show me pending approvals"
  - "Show me the detail of TIC20260316000001"
  - "查看TIC20260316000001的详情"
  - "看下这个工单的审批详情"
  - "Approve request #12345"
  - "Approve CHG20260413000011"
  - "Agree RES20260505000010"
  - "Pass TIC20260502000003"
  - "同意 1"
  - "批准 1"
  - "Reject the VM request with reason budget exceeded"
  - "Reject CHG20260413000011"
  - "Deny TIC20260502000003"
  - "List all items waiting for my approval"

related:
  - request
  - preapproval-agent

# === Tool Registration ===
tool_list_name: "smartcmp_list_pending"
tool_list_description: "Query pending approvals from SmartCMP. Automatically uses configured CMP connection."
tool_list_entrypoint: "scripts/list_pending.py"
tool_list_group: "cmp"
tool_list_capability_class: "provider:smartcmp"
tool_list_priority: 100
tool_list_result_mode: "tool_only_ok"
tool_detail_name: "smartcmp_get_request_detail"
tool_detail_description: "Get detail of a SmartCMP pending approval task. ONLY use when user explicitly asks to view/show/inspect/check details by Request ID / 编号, e.g. 'show detail of CHG20260413000011' or '查看 CHG20260413000011 的详情'. Do NOT use this tool for action commands such as approve, agree, pass, reject, deny, refuse, 批准, 同意, 通过, 拒绝, or 驳回. For submitted request status or '是否审批通过/是否被批准', use smartcmp_get_request_status."
tool_detail_entrypoint: "scripts/get_request_detail.py"
tool_detail_aliases:
  - "approval detail"
  - "request detail"
  - "show request detail"
  - "审批详情"
  - "工单详情"
tool_detail_keywords:
  - "detail"
  - "details"
  - "view"
  - "show"
  - "inspect"
  - "check details"
  - "workflow"
  - "approval detail"
  - "ticket detail"
  - "request detail"
  - "查看"
  - "看下"
  - "详情"
tool_detail_use_when:
  - "User asks to view/show/inspect/check pending approval task detail by Request ID / 编号"
  - "User provides a specific Request ID / 编号 like RES20260505000010, TIC20260502000003, or CHG20260413000011 and explicitly asks for detail/详情"
  - "Use this for 'show detail of <Request ID>', 'view <Request ID> details', '查看 <Request ID> 详情', or '看下 <Request ID> 的详情'"
tool_detail_avoid_when:
  - "User asks to approve, agree, pass, or approve request, including 'approve <Request ID>', 'agree <Request ID>', 'pass <Request ID>', 'approve 1', or 'approve request 1' (use smartcmp_approve)"
  - "User asks to 批准, 同意, 通过, or 审批通过, including '批准 <Request ID>', '同意 <Request ID>', '通过 <Request ID>', '批准 1', or '同意 1' (use smartcmp_approve)"
  - "User asks to reject, deny, refuse, or reject request, including 'reject <Request ID>', 'deny <Request ID>', 'refuse <Request ID>', or 'reject 1' (use smartcmp_reject)"
  - "User asks to 拒绝 or 驳回, including '拒绝 <Request ID>', '驳回 <Request ID>', or '拒绝 1' (use smartcmp_reject)"
  - "User asks for their own submitted request status or whether it has been approved (use smartcmp_get_request_status)"
  - "User is in the middle of submitting a NEW resource request (use smartcmp_submit_request instead)"
  - "User is providing parameters (name, password, specs) for a new request"
tool_detail_groups:
  - cmp
  - approval
tool_detail_capability_class: "provider:smartcmp"
tool_detail_priority: 105
tool_detail_result_mode: "tool_only_ok"
tool_detail_cli_positional:
  - identifier
tool_detail_parameters: |
  {
    "type": "object",
    "properties": {
      "identifier": {
        "type": "string",
        "description": "The single lookup identifier. Use the SmartCMP user-facing Request ID only, such as RES20260505000010, TIC20260502000003, or CHG20260413000011."
      },
      "days": {
        "type": "integer",
        "description": "Lookback window in days when searching pending approvals",
        "default": 90
      }
    },
    "required": ["identifier"]
  }
tool_approve_name: "smartcmp_approve"
tool_approve_description: "Approve requests in SmartCMP. `ids` must be SmartCMP user-facing Request ID(s), e.g. RES20260505000010, TIC20260502000003, or CHG20260413000011. For user selections like 'approve 1', '同意 1', or '批准 1', resolve the row index to APPROVAL_META.requestId before calling. Never pass row numbers, UUID-shaped internal IDs, or placeholder/dummy values; the script resolves Request IDs internally."
tool_approve_entrypoint: "scripts/approve.py"
tool_approve_aliases:
  - "approve request"
  - "agree request"
  - "pass request"
  - "同意"
  - "批准"
  - "通过"
  - "审批通过"
tool_approve_keywords:
  - "approve"
  - "approved"
  - "agree"
  - "pass"
  - "approve request"
  - "批准"
  - "同意"
  - "通过"
  - "审批通过"
tool_approve_use_when:
  - "User asks to approve/agree/pass a Request ID, e.g. 'approve CHG20260413000011', 'agree RES20260505000010', or 'pass TIC20260502000003'"
  - "User asks to approve/agree/pass a row from the latest pending approval list, e.g. 'approve 1', 'agree 1', or 'pass request 1'"
  - "User asks to 批准/同意/通过/审批通过 a Request ID, e.g. '批准 CHG20260413000011', '同意 RES20260505000010', or '通过 TIC20260502000003'"
  - "User asks to 批准/同意/通过 a row from the latest pending approval list, e.g. '批准 1', '同意 1', or '通过第1个'"
tool_approve_avoid_when:
  - "User only asks to view/show/inspect/check request detail without an approval action verb (use smartcmp_get_request_detail)"
  - "User asks whether their own submitted request has already been approved (use smartcmp_get_request_status)"
tool_approve_groups:
  - cmp
  - approval
tool_approve_capability_class: "provider:smartcmp"
tool_approve_priority: 120
tool_approve_cli_positional:
  - ids
tool_approve_cli_split:
  - ids
tool_approve_parameters: |
  {
    "type": "object",
    "properties": {
      "ids": {
        "type": "string",
        "description": "SmartCMP user-facing Request ID(s) only, such as 'RES20260505000010', 'TIC20260502000003', or 'CHG20260413000011'. For multiple IDs, separate with space. Do not pass display indexes, UUID-shaped internal IDs, or placeholder/dummy values."
      },
      "reason": {
        "type": "string",
        "description": "Optional approval reason"
      }
    },
    "required": ["ids"]
  }
tool_reject_name: "smartcmp_reject"
tool_reject_description: "Reject requests in SmartCMP. `ids` must be SmartCMP user-facing Request ID(s), e.g. RES20260505000010, TIC20260502000003, or CHG20260413000011. For user selections like 'reject 1' or '拒绝 1', resolve the row index to APPROVAL_META.requestId before calling. Never pass row numbers, UUID-shaped internal IDs, or placeholder/dummy values; the script resolves Request IDs internally."
tool_reject_entrypoint: "scripts/reject.py"
tool_reject_aliases:
  - "reject request"
  - "deny request"
  - "refuse request"
  - "拒绝"
  - "驳回"
tool_reject_keywords:
  - "reject"
  - "rejected"
  - "deny"
  - "denied"
  - "refuse"
  - "reject request"
  - "拒绝"
  - "驳回"
tool_reject_use_when:
  - "User asks to reject/deny/refuse a Request ID, e.g. 'reject CHG20260413000011', 'deny RES20260505000010', or 'refuse TIC20260502000003'"
  - "User asks to reject/deny/refuse a row from the latest pending approval list, e.g. 'reject 1' or 'deny request 1'"
  - "User asks to 拒绝/驳回 a Request ID or row, e.g. '拒绝 CHG20260413000011', '驳回 RES20260505000010', or '拒绝 1'"
tool_reject_avoid_when:
  - "User only asks to view/show/inspect/check request detail without a rejection action verb (use smartcmp_get_request_detail)"
  - "User asks whether their own submitted request was rejected (use smartcmp_get_request_status)"
tool_reject_groups:
  - cmp
  - approval
tool_reject_capability_class: "provider:smartcmp"
tool_reject_priority: 130
tool_reject_cli_positional:
  - ids
tool_reject_cli_split:
  - ids
tool_reject_parameters: |
  {
    "type": "object",
    "properties": {
      "ids": {
        "type": "string",
        "description": "SmartCMP user-facing Request ID(s) only, such as 'RES20260505000010', 'TIC20260502000003', or 'CHG20260413000011'. For multiple IDs, separate with space. Do not pass display indexes, UUID-shaped internal IDs, or placeholder/dummy values."
      },
      "reason": {
        "type": "string",
        "description": "Rejection reason (recommended)"
      }
    },
    "required": ["ids"]
  }
---

# approval

Approval workflow management skill.

## Purpose

Manage approval workflows for service catalog requests:
- Query pending approval items with priority analysis
- Approve one or more requests with optional reason
- Reject one or more requests with reason

## Trigger Conditions

Use this skill when user intent is any of:
- View pending approvals / list approvals / check what needs approval
- Approve a request / approve all / batch approve
- Reject a request / deny request / batch reject

| Intent | Keywords |
|--------|----------|
| View pending | "show pending approvals", "list approvals", "what needs approval" |
| Approve | "approve request", "agree request", "pass request", "approve #1", "agree 1", "同意 1", "批准 1", "通过 1", "approve all", "batch approve" |
| Reject | "reject request", "deny request", "refuse request", "reject #1", "deny 1", "拒绝 1", "驳回 1", "batch reject" |

## Intent Priority

Action commands always win over detail lookup.

| User intent | Required tool |
|-------------|---------------|
| approve/agree/pass + Request ID or row number | `smartcmp_approve` |
| 批准/同意/通过/审批通过 + Request ID or row number | `smartcmp_approve` |
| reject/deny/refuse + Request ID or row number | `smartcmp_reject` |
| 拒绝/驳回 + Request ID or row number | `smartcmp_reject` |
| view/show/inspect/check detail + Request ID | `smartcmp_get_request_detail` |
| 查看/看下/详情 + Request ID | `smartcmp_get_request_detail` |

Examples:
- `approve CHG20260413000011` MUST call `smartcmp_approve`.
- `agree RES20260505000010` MUST call `smartcmp_approve`.
- `pass TIC20260502000003` MUST call `smartcmp_approve`.
- `批准 CHG20260413000011` MUST call `smartcmp_approve`.
- `reject CHG20260413000011` MUST call `smartcmp_reject`.
- `deny RES20260505000010` MUST call `smartcmp_reject`.
- `查看 CHG20260413000011 的详情` MUST call `smartcmp_get_request_detail`.
- `show detail of CHG20260413000011` MUST call `smartcmp_get_request_detail`.

## Scripts

| Script | Description | Location |
|--------|-------------|----------|
| `list_pending.py` | List pending approval items with priority | `scripts/` |
| `approve.py` | Approve one or more requests | `scripts/` |
| `reject.py` | Reject one or more requests | `scripts/` |

## Environment Setup

### Option 1: Direct Cookie
```powershell
# PowerShell - CMP_URL auto-normalizes (adds /platform-api if missing)
$env:CMP_URL = "<your-cmp-host>"
$env:CMP_COOKIE = '<full cookie string>'
```

```bash
# Bash
export CMP_URL="<your-cmp-host>"
export CMP_COOKIE="<full cookie string>"
```

### Option 2: Auto-Login (Recommended)
Automatically obtains and caches cookies (30-minute TTL). Auth URL is auto-inferred.

```powershell
# PowerShell
$env:CMP_URL = "<your-cmp-host>"
$env:CMP_USERNAME = "<username>"
$env:CMP_PASSWORD = "<password>"
```

```bash
# Bash
export CMP_URL="<your-cmp-host>"
export CMP_USERNAME="<username>"
export CMP_PASSWORD="<password>"
```

## Workflow

### Step 1: List Pending Approvals

**Command:**
```bash
python scripts/list_pending.py [--days N]
```

**Output Format:**
- Human-readable: Markdown table sorted by latest SmartCMP update first
- Machine-readable: `##APPROVAL_META_START## ... ##APPROVAL_META_END##` on stderr for internal tool use

**META Fields:**
| Field | Description |
|-------|-------------|
| `index` | Display index (1, 2, 3...) — for user selection only |
| `requestId` | **SmartCMP user-facing Request ID / request number** — use this for approve/reject tool input (e.g., RES20260505000010, TIC20260502000003, or CHG20260413000011) |
| `name` | Request name |
| `catalogName` | Service catalog type |
| `applicant` | Requester name |
| `waitHours` | Hours since creation |
| `priorityScore` | Priority score (higher = more urgent) |

---

## CRITICAL: Request ID Field Selection

> **MUST USE `requestId` field for approve.py and reject.py**
>
> The APPROVAL_META exposes one ID field to the agent: the user-facing `requestId`.
> The scripts resolve `requestId` to the SmartCMP approval action identifier internally before calling the CMP approval API.

| Field | Format Example | Can Use as approve/reject tool input? |
|-------|----------------|----------------------------|
| `requestId` | `RES20260505000010`, `TIC20260502000003`, `CHG20260413000011` | **YES — USE THIS** |
| display index | `1`, `2`, `3` | **NO — resolve row index to `requestId` first** |
| UUID-shaped internal ID | internal SmartCMP identifier | **NO — not exposed to the agent and not accepted by approve/reject** |

**Mapping user selection to correct ID:**
```
User says "1", "approve 1", "同意 1", or "批准 1"
  |
  v
Find item with index=1 in APPROVAL_META
  |
  v
Extract the "requestId" field
  |
  v
Pass to approve.py or reject.py
```

Never invent or pass placeholder values such as `dummy-id-placeholder`, `placeholder`, `example`, or `<request_id>`. If the latest APPROVAL_META is unavailable, list pending approvals again before calling approve/reject.

### Step 2: Approve Requests

**Command:**
```bash
# Single approval
python scripts/approve.py <request_id>

# With reason
python scripts/approve.py <request_id> --reason "Approved per policy"

# Batch approval
python scripts/approve.py <request_id1> <request_id2> <request_id3>
```

### Step 3: Reject Requests

**Command:**
```bash
# Single rejection
python scripts/reject.py <request_id>

# With reason (recommended)
python scripts/reject.py <request_id> --reason "Budget exceeded"

# Batch rejection
python scripts/reject.py <request_id1> <request_id2> --reason "Not aligned with policy"
```

## Output Parsing

### Approval META Block

```json
{
  "index": 1,
  "requestId": "RES20260505000010",                   // <- USE THIS for approve/reject
  "name": "Test Request",
  "catalogName": "Issue Ticket",
  "applicant": "TestUser",
  "email": "test@example.com",
  "waitHours": 0.5,
  "priority": "Low",
  "priorityScore": 50,
  "approvalStep": "Level 1 Approval",
  "currentApprover": "Pending"
}
```

### Quick Reference: Which ID to Use

```
[OK]    approve.py <requestId> <- Use "requestId" field: RES20260505000010
[OK]    reject.py <requestId>  <- Use "requestId" field: TIC20260502000003 or CHG20260413000011

[FAIL]  approve.py <uuid>        <- internal SmartCMP UUID, not accepted
[FAIL]  approve.py 1             <- display row number, resolve it to APPROVAL_META.requestId first
[FAIL]  approve.py dummy-id-placeholder <- placeholder, never send to CMP
```

## Critical Rules

> **ONLY use `requestId` field for approve/reject tool input**. The scripts convert requestId to the SmartCMP approval action ID internally.

> **NEVER create temp files** — no `.py`, `.txt`, `.json`. Your context IS your memory.

> **NEVER redirect output** — no `>`, `>>`, `2>&1`. Run scripts directly, read stdout.

> **Always show pending list first** before approve/reject operations.

> **Confirm with user** before batch operations affecting multiple items.

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| `400` + `activity is null` | Used an internal or stale identifier after Request ID resolution | Re-list pending approvals, verify the item is still pending, and retry with `requestId` |
| `Invalid SmartCMP Request ID(s)` | Used a display row number, UUID-shaped internal ID, or placeholder instead of `APPROVAL_META.requestId` | Re-list pending approvals and resolve the selected row to the `requestId` field |
| `401` / Token expired | Session timeout | Refresh `CMP_COOKIE` or re-login |
| `404` / Not found | Invalid or stale Request ID | Verify ID from latest list_pending.py output |
| `[ERROR]` output | Various | Report to user immediately; do NOT self-debug |

## References

- [WORKFLOW.md](references/WORKFLOW.md) — Detailed approval workflow documentation
