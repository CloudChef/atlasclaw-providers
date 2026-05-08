# Resource Compliance Workflow

1. Receive an exact SmartCMP resource name or a visible index from the latest resource list.
2. Resolve that name/index through recent `smartcmp_list_all_resource` metadata when available; otherwise query SmartCMP by exact resource name.
3. Use the resolved internal resource ID only for SmartCMP API calls, then retrieve resource summary, full resource fields, resource details, and the shared normalized `type + properties` view.
4. Reuse that normalized view (`type` comes from `componentType`) for analyzer routing.
5. Route analyzer families by `type` (cloud/software/OS), then analyze lifecycle, patch, security, and configuration posture.
6. Emit human-readable output plus a structured JSON block. Human-readable output must use resource names, not UUIDs.

## Direct invocation

```bash
python scripts/analyze_resource.py --resource-name e2e-newrole-linux3-0501
python scripts/analyze_resource.py \
  --resource-index 2 \
  --resource-directory-json '[{"index":2,"id":"internal-id","name":"e2e-newrole-linux3-0501"}]'
```

## Webhook-style invocation

```bash
python scripts/analyze_resource.py \
  --payload-json '{"resourceIds":["id-1","id-2"],"triggerSource":"webhook"}'
```

Webhook resource IDs are a backend compatibility path. Do not ask users for
UUIDs when an interactive name or list-index workflow is available.

## Output contract

- `##RESOURCE_COMPLIANCE_START## ... ##RESOURCE_COMPLIANCE_END##`
- top-level keys:
  - `triggerSource`
  - `requestedResourceIds`
  - `requestedResources`
  - `resolvedResources`
  - `analyzedCount`
  - `failedCount`
  - `generatedAt`
  - `results`

Representative result fields:

```json
{
  "type": "resource.software.app.tomcat",
  "analysisTargets": ["software:tomcat"]
}
```
