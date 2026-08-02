# Approval Workflow Reference

Use the five AtlasClaw approval Tools. Their handlers are co-located in
`scripts/adapter.py`; do not run the file as a command-line program.

## Execution rules

1. Call `smartcmp_list_pending` before approve or reject so the current
   `request_id` is known.
2. Resolve a displayed row number to the latest list result's `_internal.items[].request_id`.
3. Never pass a display index, internal UUID, or placeholder as a Request ID.
4. Ask for confirmation before a batch approval or rejection.
5. Parse `_internal` metadata silently; do not display raw workflow JSON.

## Request ID contract

`smartcmp_approve` and `smartcmp_reject` accept SmartCMP user-facing Request
IDs in `request_id`, such as `RES20260505000010`, `TIC20260502000003`, or
`CHG20260413000011`. SmartCMP Provider resolves those values to the internal
approval action identifiers.

## Flow

### List

Call `smartcmp_list_pending`, optionally with `days`. Show the visible table
and retain `{index, request_id, name, applicant}` from `_internal.items`.

### Inspect or analyze

- Use `smartcmp_get_request_detail` for an explicit detail request.
- Use `smartcmp_analyze_approval_request` for read-only review guidance.

Neither operation changes CMP state.

### Approve

After resolving every selected row to `request_id`, call `smartcmp_approve`
with `ids` and an optional `reason`.

### Reject

After resolving every selected row to `request_id`, call `smartcmp_reject`
with `ids` and a rejection `reason`.

## Error handling

| Error | Action |
|-------|--------|
| Invalid Request ID | Re-list pending approvals and resolve the selected row to `request_id` |
| `401 Unauthorized` | Refresh the selected SmartCMP session or credential |
| `404 Not Found` | Re-list because the approval may be stale or completed |
| Timeout or unknown write result | Report the normalized Provider result; do not retry a write blindly |
