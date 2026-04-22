---
name: "approval"
description: "Approval workflow skill. View pending approvals and approve or reject service requests."
provider_type: "smartcmp"
instance_required: "true"

# === LLM Context Fields ===
triggers:
  - pending approvals
  - list approvals
  - request detail
  - approval detail
  - request status
  - approve request
  - reject request
  - approval workflow
  - 待审批
  - 查看待审批
  - 请求详情
  - 工单详情
  - 审批详情
  - 请求状态
  - 查看详情
  - 审批通过
  - 审批拒绝

use_when:
  - User wants to view pending approval items
  - User wants to inspect one pending SmartCMP request or approval item in detail
  - User needs to approve or reject service requests
  - User asks about approval status, approval queue, or approval workflow
  - User asks for the detail or status of a SmartCMP request by ticket/workflow/request/task/process identifier
  - User asks for SmartCMP 待审批、工单详情、审批详情、请求状态

avoid_when:
  - User wants to provision new resources (use request skill)
  - User wants to query reference data (use datasource skill)
  - User describes infrastructure needs in natural language (use request-decomposition-agent)

examples:
  - "Show me pending approvals"
  - "Show me the detail of TIC20260316000001"
  - "查看TIC20260316000001的详情"
  - "看下这个工单的审批详情"
  - "查下请求状态"
  - "Approve request #12345"
  - "Reject the VM request with reason budget exceeded"
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
tool_detail_description: "Get detail of an existing SmartCMP pending approval item. ONLY use when user explicitly asks for the detail/status of a SPECIFIC request by its ticket ID or workflow ID (e.g. TIC20260316000001). Do NOT use during resource provisioning or request submission workflows."
tool_detail_entrypoint: "scripts/get_request_detail.py"
tool_detail_aliases:
  - "approval detail"
  - "审批详情"
  - "工单详情"
tool_detail_keywords:
  - "detail"
  - "status"
  - "workflow"
  - "approval detail"
  - "ticket detail"
  - "详情"
  - "审批"
  - "TIC"
tool_detail_use_when:
  - "User asks for the detail or current status of an EXISTING SmartCMP request by its ticket/workflow ID"
  - "User provides a specific ticket ID like TIC20260316000001 and asks for its detail"
tool_detail_avoid_when:
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
        "description": "The single lookup identifier. Put workflow ID, approval ID, request ID, task ID, or process instance ID into this `identifier` field."
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
tool_approve_description: "Approve requests in SmartCMP. The system automatically selects and injects the provider instance configuration."
tool_approve_entrypoint: "scripts/approve.py"
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
        "description": "Approval ID(s) to approve. For multiple IDs, separate with space: 'id1 id2 id3'"
      },
      "reason": {
        "type": "string",
        "description": "Optional approval reason"
      }
    },
    "required": ["ids"]
  }
tool_reject_name: "smartcmp_reject"
tool_reject_description: "Reject requests in SmartCMP. The system automatically selects and injects the provider instance configuration."
tool_reject_entrypoint: "scripts/reject.py"
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
        "description": "Approval ID(s) to reject. For multiple IDs, separate with space: 'id1 id2 id3'"
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
| Approve | "approve request", "approve #1", "approve all", "batch approve" |
| Reject | "reject request", "deny request", "batch reject" |

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
- Human-readable: Numbered list with priority indicators (High/Medium/Low)
- Machine-readable: `##APPROVAL_META_START## ... ##APPROVAL_META_END##`

**META Fields:**
| Field | Description |
|-------|-------------|
| `id` | **Approval ID** — USE THIS for approve/reject operations |
| `index` | Display index (1, 2, 3...) — for user selection only |
| `name` | Request name |
| `workflowId` | Ticket number (e.g., TIC20260313000007) — for display only |
| `catalogName` | Service catalog type |
| `applicant` | Requester name |
| `waitHours` | Hours since creation |
| `priorityScore` | Priority score (higher = more urgent) |
| `taskId` | Workflow task ID — **DO NOT USE** for approve/reject |
| `requestId` | Original request ID — **DO NOT USE** for approve/reject |
| `processInstanceId` | Process instance ID — **DO NOT USE** for approve/reject |

---

## CRITICAL: ID Field Selection

> **MUST USE `id` field for approve.py and reject.py**
>
> The APPROVAL_META contains multiple ID fields. Only the `id` field works with approve/reject scripts.

| Field | Format Example | Can Use for Approve/Reject? |
|-------|----------------|----------------------------|
| `id` | `20fef12e-5015-4df5-822b-e1e87c4f64fd` | **YES — USE THIS** |
| `taskId` | `38982580-1ecd-11f1-94d0-ba3859030815` | **NO — Will fail with 400 error** |
| `requestId` | `00df4234-3934-4c85-a07e-3a5cd8bd3cfa` | **NO — Wrong endpoint** |
| `processInstanceId` | `3897fe5d-1ecd-11f1-94d0-ba3859030815` | **NO — Internal use only** |

**Mapping user selection to correct ID:**
```
User says "1" or "approve 1"
  |
  v
Find item with index=1 in APPROVAL_META
  |
  v
Extract the "id" field (NOT taskId, NOT requestId)
  |
  v
Pass to approve.py or reject.py
```

### Step 2: Approve Requests

**Command:**
```bash
# Single approval
python scripts/approve.py <approval_id>

# With reason
python scripts/approve.py <approval_id> --reason "Approved per policy"

# Batch approval
python scripts/approve.py <id1> <id2> <id3>
```

### Step 3: Reject Requests

**Command:**
```bash
# Single rejection
python scripts/reject.py <approval_id>

# With reason (recommended)
python scripts/reject.py <approval_id> --reason "Budget exceeded"

# Batch rejection
python scripts/reject.py <id1> <id2> --reason "Not aligned with policy"
```

## Output Parsing

### Approval META Block

```json
{
  "index": 1,
  "id": "20fef12e-5015-4df5-822b-e1e87c4f64fd",      // <- USE THIS for approve/reject
  "requestId": "00df4234-3934-4c85-a07e-3a5cd8bd3cfa", // <- DO NOT USE
  "taskId": "38982580-1ecd-11f1-94d0-ba3859030815",    // <- DO NOT USE
  "processInstanceId": "3897fe5d-1ecd-11f1-94d0-ba3859030815", // <- DO NOT USE
  "name": "Test Request",
  "workflowId": "TIC20260313000007",
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
[OK]    approve.py <id>     <- Use "id" field:      20fef12e-5015-4df5-822b-e1e87c4f64fd
[OK]    reject.py <id>      <- Use "id" field:      20fef12e-5015-4df5-822b-e1e87c4f64fd

[FAIL]  approve.py <taskId>      <- 38982580-1ecd-11f1-94d0-ba3859030815 (400 error)
[FAIL]  approve.py <requestId>   <- 00df4234-3934-4c85-a07e-3a5cd8bd3cfa (not found)
```

## Critical Rules

> **ONLY use `id` field for approve/reject** — NOT taskId, NOT requestId, NOT processInstanceId. Using wrong ID causes 400 errors.

> **NEVER create temp files** — no `.py`, `.txt`, `.json`. Your context IS your memory.

> **NEVER redirect output** — no `>`, `>>`, `2>&1`. Run scripts directly, read stdout.

> **Always show pending list first** before approve/reject operations.

> **Confirm with user** before batch operations affecting multiple items.

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| `400` + `activity is null` | Used wrong ID field (taskId/requestId instead of id) | Re-read APPROVAL_META, use `id` field only |
| `401` / Token expired | Session timeout | Refresh `CMP_COOKIE` or re-login |
| `404` / Not found | Invalid approval ID | Verify ID from latest list_pending.py output |
| `[ERROR]` output | Various | Report to user immediately; do NOT self-debug |

## References

- [WORKFLOW.md](references/WORKFLOW.md) — Detailed approval workflow documentation
