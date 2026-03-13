---
name: "approval"
description: "SmartCMP approval management. Use for: view pending approvals, check approval list, approve or reject requests. Keywords: approval, pending, approve, reject"
provider_type: "smartcmp"
instance_required: "true"
tool_list_name: "smartcmp_list_pending"
tool_list_description: "Query pending approvals from SmartCMP/CMP. Use for: view pending approvals, check approval list, see what needs approval, view CMP approves, check SmartCMP pending items. Automatically uses configured CMP connection."
tool_list_entrypoint: "scripts/list_pending.py"
tool_approve_name: "smartcmp_approve"
tool_approve_description: "Approve requests in SmartCMP. The system automatically selects and injects the provider instance configuration."
tool_approve_entrypoint: "scripts/approve.py"
tool_reject_name: "smartcmp_reject"
tool_reject_description: "Reject requests in SmartCMP. The system automatically selects and injects the provider instance configuration."
tool_reject_entrypoint: "scripts/reject.py"
---

# approval

SmartCMP approval workflow management skill.

## Purpose

Manage SmartCMP approval workflows:
- Query pending approval items with priority analysis
- Approve one or more requests with optional reason
- Reject one or more requests with reason

## Trigger Conditions

Use this skill when user intent is any of:
- View pending approvals / list approvals / check what needs approval
- 查看待审批单据 / 查看审批 / 有哪些需要审批的
- Approve a request / approve all / batch approve
- 审批通过 / 同意申请
- Reject a request / deny request / batch reject
- 拒绝申请 / 驳回请求

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

```powershell
# PowerShell - CMP_URL auto-normalizes (adds /platform-api if missing)
$env:CMP_URL = "<your-cmp-host>"           # e.g., "cmp.example.com" or "https://cmp.example.com/platform-api"
$env:CMP_COOKIE = '<full cookie string>'
```

```bash
# Bash
export CMP_URL="<your-cmp-host>"
export CMP_COOKIE="<full cookie string>"
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
| `id` | Approval ID for approve/reject operations |
| `name` | Request name |
| `catalogName` | Service catalog type |
| `applicant` | Requester name |
| `waitHours` | Hours since creation |
| `priorityScore` | Priority score (higher = more urgent) |

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
  "id": "abc123",
  "requestId": "req-456",
  "name": "Linux VM Request",
  "workflowId": "WF-2024-001",
  "catalogName": "Linux 虚拟机",
  "applicant": "张三",
  "waitHours": 24.5,
  "priorityScore": 75,
  "priorityFactors": ["等待超1天", "有成本预估"],
  "approvalStep": "运维审批",
  "currentApprover": "李四"
}
```

## Critical Rules

> **NEVER create temp files** — no `.py`, `.txt`, `.json`. Your context IS your memory.

> **NEVER redirect output** — no `>`, `>>`, `2>&1`. Run scripts directly, read stdout.

> **Always show pending list first** before approve/reject operations.

> **Confirm with user** before batch operations affecting multiple items.

## Error Handling

| Error | Resolution |
|-------|------------|
| `401` / Token expired | Refresh `CMP_COOKIE` environment variable |
| `[ERROR]` output | Report to user immediately; do NOT self-debug |

## References

- [WORKFLOW.md](references/WORKFLOW.md) — Detailed approval workflow documentation
