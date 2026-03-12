---
name: "approval"
description: "SmartCMP approval management. Use for: view pending approvals, check approval list, approve or reject requests. Keywords: approval, pending, approve, reject"
provider_type: "smartcmp"
instance_required: "true"
tool_list_name: "smartcmp_list_pending"
tool_list_description: "List pending approvals from SmartCMP. The system automatically selects and injects the provider instance configuration."
tool_list_entrypoint: "scripts/list_pending.py"
tool_approve_name: "smartcmp_approve"
tool_approve_description: "Approve requests in SmartCMP. The system automatically selects and injects the provider instance configuration."
tool_approve_entrypoint: "scripts/approve.py"
tool_reject_name: "smartcmp_reject"
tool_reject_description: "Reject requests in SmartCMP. The system automatically selects and injects the provider instance configuration."
tool_reject_entrypoint: "scripts/reject.py"
---

# approval

Provider skill under `SmartCMP-Provider/skills/approval`.

## Purpose

Manage SmartCMP approval workflows including querying pending approvals, approving requests, and rejecting requests.

## Trigger Conditions

Use this skill when user intent is any of:
- View pending approvals / list approvals / check what needs approval
- 查看待审批单据 / 查看审批 / 有哪些需要审批的
- Approve a request / approve all / batch approve
- 审批通过 / 同意申请
- Reject a request / deny request / batch reject
- 拒绝申请 / 驳回请求

## Script Entry Points

All scripts are in `scripts/`:

- `scripts/list_pending.py` — List pending approval items
- `scripts/approve.py` — Approve one or more requests
- `scripts/reject.py` — Reject one or more requests

## Execution Workflow (REQUIRED)

**CRITICAL: Follow these steps in order:**

1. **Select Provider Instance** (REQUIRED)
   - First, check if a provider instance is already selected in the conversation context
   - If not, use `list_provider_instances` to see available providers
   - Then use `select_provider_instance` tool with the appropriate provider_type and instance_name
   - This injects the provider configuration into deps.extra

2. **Execute Script with Environment Variables** (REQUIRED)
   - Change to skill directory: `cd <skill_location>`
   - Set environment variables from the selected provider instance:
     ```bash
     export CMP_URL=<provider_instance.cmp_url>
     export CMP_COOKIE=<provider_instance.cookie>
     ```
   - Run the script: `python scripts/list_pending.py`

### Query pending approvals

When user says "show me pending approvals", "what needs my approval", or "查看待审批单据":

1. Select provider instance (if not already selected): `select_provider_instance` with appropriate provider_type and instance_name
2. Execute: `cd <skill_location> && export CMP_URL=<cmp_url> && export CMP_COOKIE=<cookie> && python scripts/list_pending.py`

Output: numbered list of pending items with enhanced details:
- Priority indicator (🔴High/🟡Medium/🟢Low) with intelligent scoring
- Request name, workflow ID, catalog type
- Applicant name and email
- Description/justification (if provided)
- Creation time, update time, and wait duration
- Resource specifications (CPU, memory, storage, tags)
- Cost estimate (if available)
- Current approval step and assigned approver
- Priority factors explaining the score

The `##APPROVAL_META##` block contains structured JSON with full details for programmatic use.

### Approve requests

When user says "approve request #1" or "approve all":

```bash
# Approve single item (ID from list_pending.py output)
python scripts/approve.py <approval_id>

# Approve with reason
python scripts/approve.py <approval_id> --reason "Approved per policy"

# Approve multiple items
python scripts/approve.py <id1> <id2> <id3>
```

### Reject requests

When user says "reject request #1":

```bash
# Reject single item
python scripts/reject.py <approval_id>

# Reject with reason (recommended)
python scripts/reject.py <approval_id> --reason "Budget exceeded"

# Reject multiple items
python scripts/reject.py <id1> <id2> --reason "Not aligned with policy"
```

## Environment Setup

```powershell
$env:CMP_URL = "https://<host>/platform-api"
$env:CMP_COOKIE = '<full cookie string>'
```

## References

- [WORKFLOW.md](references/WORKFLOW.md) — Detailed approval workflow

## Notes

**CRITICAL RULES:**
- **NEVER create temp files** — no `.py`, `.txt`, `.json`. Your context IS your memory.
- **NEVER redirect output** — no `>`, `>>`, `2>&1`. Run scripts directly, read stdout.
- **Always show pending list first** before approve/reject operations.
- **Confirm with user** before batch operations affecting multiple items.

**General:**
- Scripts read SmartCMP connection from environment variables (`CMP_URL`, `CMP_COOKIE`).
- Approval IDs come from `list_pending.py` output's `##APPROVAL_META##` block.
- Default time range is last 30 days; adjustable via `--days` parameter.
