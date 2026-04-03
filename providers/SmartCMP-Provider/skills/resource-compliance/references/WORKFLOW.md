# Resource Compliance Workflow

1. Receive one or more SmartCMP resource IDs from user input or webhook input.
2. Retrieve resource summary, full resource fields, and resource details.
3. Normalize facts for analysis.
4. Analyze lifecycle, patch, and security posture.
5. Emit human-readable output plus a structured JSON block.

## Direct invocation

```bash
python scripts/analyze_resource.py <resource_id>
```

## Webhook-style invocation

```bash
python scripts/analyze_resource.py \
  --payload-json '{"resourceIds":["id-1","id-2"],"triggerSource":"webhook"}'
```

## Output contract

- `##RESOURCE_COMPLIANCE_START## ... ##RESOURCE_COMPLIANCE_END##`
- top-level keys:
  - `triggerSource`
  - `requestedResourceIds`
  - `analyzedCount`
  - `failedCount`
  - `generatedAt`
  - `results`
