# Approval Workflow Reference

Use the five AtlasClaw approval Tools. Their handlers are co-located in
`scripts/adapter.py`; do not run the file as a command-line program.

## Execution rules

1. Call `smartcmp_list_pending` before approve or reject so the current
   `request_id` is known.
2. When the user explicitly selects a displayed row, resolve that row to the
   latest list result's `_internal.items[].request_id`. A supplied ID that
   happens to be numeric remains an exact ID, not an implicit row selection.
3. Treat Request IDs as opaque; never pass a display index or invent a value.
4. Ask for confirmation before a batch approval or rejection.
5. Parse `_internal` metadata silently; do not display raw workflow JSON.

## Request ID contract

`smartcmp_approve` and `smartcmp_reject` accept the exact SmartCMP user-facing
Request ID returned in `request_id`. The value has no required prefix,
character set, or fixed-length pattern. SmartCMP Provider resolves it to the
current internal approval action identifier.

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
