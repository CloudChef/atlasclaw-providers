# Security Compliance Workflow

## Overall posture and listing

1. Use the root category `SECURITY`; never send `SECURITY.*` to CMP search APIs.
2. Use `smartcmp_get_security_overview` for policy, evaluation, compliance,
   violation, severity, and trend facts.
3. Use `smartcmp_list_security_violations` for the authoritative violation
   collection. Preserve the real CMP violation ID in object metadata so a later
   reference such as “analyze the first item” never treats the table index as an
   ID. Collection items expose Analyze only; they cannot skip directly to Mark
   Fixed.
4. Preserve pagination and coverage fields. A truncated or failed scan is not
   evidence that no additional violations exist.

## Single violation analysis

1. Call `smartcmp_analyze_security_violation` for the selected real violation
   ID. The Provider re-reads the detail on every call.
2. Accept only `SECURITY` or a `SECURITY.*` subcategory. Never route a Cost
   recommendation through this workflow.
3. Treat policy and resource enrichment as best-effort. Their failure must be
   reported as an evidence gap rather than replacing the violation facts.
4. Separate the final answer into CMP-confirmed facts, LLM inference, missing
   evidence, manual remediation guidance, and post-remediation validation.
5. Do not present saving, optimization, Day-2 repair, or remediation tracking.
   Null task fields mean CMP has not advertised a safe native repair contract.

## Mark fixed

1. Phase 1 always calls `smartcmp_analyze_security_violation` to refresh the
   exact violation. Show its current status, resource, policy, evidence gaps,
   and the fact that Mark Fixed changes only the violation status. Stop and wait
   for explicit user confirmation; do not perform the write in this turn.
2. Phase 2 starts only in the next confirmed turn for those latest object
   details. Call `smartcmp_mark_security_violation_fixed` with
   `confirmed=true`.
3. Submit once. A timeout or server error has an unknown outcome and must not be
   retried automatically.
4. Re-read the violation after submission. Always state
   `resource_remediated=false`; `FIXED` does not prove the resource was changed
   and a later policy evaluation may create another violation.

## Resource boundary

Questions about the security posture of a named or selected resource belong to
the `resource` Skill and its `smartcmp_analyze_resource_security` or
`smartcmp_list_resource_security_violations` Tools. This Skill owns the policy
violation collection and single-violation lifecycle.
