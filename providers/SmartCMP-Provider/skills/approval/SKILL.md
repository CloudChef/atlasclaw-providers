---
name: "approval"
description: "SmartCMP approval management. View pending approvals, approve or reject provisioning requests."
provider_type: "smartcmp"
instance_required: "true"

# === LLM Context Fields ===
triggers:
  - pending approvals
  - list approvals
  - approve request
  - reject request
  - approval workflow

use_when:
  - User wants to view pending approval items
  - User needs to approve or reject provisioning requests
  - User asks about approval status or workflow

avoid_when:
  - User wants to provision new resources (use request skill)
  - User wants to query reference data (use datasource skill)
  - User describes infrastructure needs in natural language (use request-decomposition-agent)

examples:
  - "Show me pending approvals"
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
tool_approve_name: "smartcmp_approve"
tool_approve_description: "Approve requests in SmartCMP. The system automatically selects and injects the provider instance configuration."
tool_approve_entrypoint: "scripts/approve.py"
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

SmartCMP approval workflow management skill.

## Purpose

Manage SmartCMP approval workflows:
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
Automatically obtains and caches cookies (30-minute TTL).

```powershell
# PowerShell
$env:CMP_URL = "<your-cmp-host>"
$env:CMP_USERNAME = "<username>"
$env:CMP_PASSWORD = "<password>"
$env:CMP_AUTH_URL = "<auth endpoint>"
```

```bash
# Bash
export CMP_URL="<your-cmp-host>"
export CMP_USERNAME="<username>"
export CMP_PASSWORD="<password>"
export CMP_AUTH_URL="<auth endpoint>"
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
  "catalogName": "Linux Virtual Machine",
  "applicant": "John Doe",
  "waitHours": 24.5,
  "priorityScore": 75,
  "priorityFactors": ["Waiting over 1 day", "Has cost estimate"],
  "approvalStep": "Operations Approval",
  "currentApprover": "Jane Smith"
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
