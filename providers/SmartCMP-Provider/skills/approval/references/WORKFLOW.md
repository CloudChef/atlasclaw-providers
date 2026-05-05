# Approval Workflow Reference

Detailed workflow for managing SmartCMP approvals.

---

## Setup (once per session)

```powershell
$env:CMP_URL = "https://<host>/platform-api"
$env:CMP_COOKIE = '<full cookie string>'   # MUST use single quotes
```

---

## Execution Rules

1. **Always list first** — Run `list_pending.py` before approve/reject operations.
2. **Confirm batch operations** — Ask user before approving/rejecting multiple items.
3. **NEVER create temp files** — Your context IS your memory.
4. **NEVER redirect output** — Run scripts directly, read stdout.
5. **Parse META blocks silently** — Do NOT display raw JSON to user.

### Request ID Contract

`approve.py` and `reject.py` accept only SmartCMP user-facing Request IDs from
`APPROVAL_META.requestId`, such as `RES20260505000010`, `TIC20260502000003`,
or `CHG20260413000011`. The scripts resolve those Request IDs to the SmartCMP
approval action identifiers internally before calling SmartCMP action APIs.

Do not pass display row numbers, UUID-shaped internal IDs, or placeholder values
such as `dummy-id-placeholder`.

---

## Full Workflow

### Step 1 — List pending approvals

```
ACTION: python scripts/list_pending.py
SHOW:   numbered list of pending items
PARSE:  ##APPROVAL_META_START## silently → cache {index, requestId, name, requester}
ASK:    "Would you like to approve or reject any of these?"
STOP → wait for user selection
```

**Optional filters:**
```bash
# Query last 7 days only
python scripts/list_pending.py --days 7
```

---

### Step 2a — Approve (single item)

When user says "approve #1", "approve the first one", "同意 1", or "批准 1":

```
LOOKUP: requestId from cached ##APPROVAL_META## by index
ACTION: python scripts/approve.py <requestId>
SHOW:   "[SUCCESS] Approval completed."
```

**With reason:**
```bash
python scripts/approve.py <requestId> --reason "Approved per policy"
```

---

### Step 2b — Approve (multiple items)

When user says "approve all" or "approve #1, #2, #3":

```
LOOKUP: requestIds from cached ##APPROVAL_META##
CONFIRM: "You are about to approve N items. Proceed? (yes/no)"
STOP → wait for confirmation
ACTION: python scripts/approve.py <requestId1> <requestId2> <requestId3>
SHOW:   "[SUCCESS] Approval completed."
```

---

### Step 3a — Reject (single item)

When user says "reject #2":

```
LOOKUP: requestId from cached ##APPROVAL_META## by index
ASK:    "Would you like to provide a rejection reason?"
STOP → wait for user input (optional)
ACTION: python scripts/reject.py <requestId> [--reason "..."]
SHOW:   "[SUCCESS] Rejection completed."
```

---

### Step 3b — Reject (multiple items)

When user says "reject all" or "reject #1 and #2":

```
LOOKUP: requestIds from cached ##APPROVAL_META##
CONFIRM: "You are about to reject N items. Proceed? (yes/no)"
STOP → wait for confirmation
ASK:    "Would you like to provide a rejection reason?"
STOP → wait for user input (optional)
ACTION: python scripts/reject.py <requestId1> <requestId2> [--reason "..."]
SHOW:   "[SUCCESS] Rejection completed."
```

---

## Script Reference

| Script | Purpose | Arguments |
|--------|---------|-----------|
| `list_pending.py` | List pending approvals | `[--days N]` |
| `approve.py` | Approve items | `<requestId1> [requestId2...] [--reason "..."]` |
| `reject.py` | Reject items | `<requestId1> [requestId2...] [--reason "..."]` |

---

## API Reference

### List pending approvals
```
GET /generic-request/current-activity-approval
    ?page=1&size=50&stage=pending&sort=updatedDate,desc
    &startAtMin=<timestamp>&startAtMax=<timestamp>
    &rangeField=updatedDate&states=
```

### Approve batch
```
POST /approval-activity/approve/batch
Body: {"reason": "<optional>"}
```

### Reject batch
```
POST /approval-activity/reject/batch
Body: {"reason": "<optional>"}
```

---

## Error Handling

| Error | Action |
|-------|--------|
| `Invalid SmartCMP Request ID(s)` | Re-list pending approvals, then resolve the selected row to `APPROVAL_META.requestId` |
| `401 Unauthorized` | Cookie expired → ask user to re-login |
| `404 Not Found` | Invalid or stale Request ID → re-run list_pending.py |
| `400 Bad Request` | Check API response for details |
| Network timeout | Retry or check connectivity |
