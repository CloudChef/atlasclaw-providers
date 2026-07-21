# Resource Cost Analysis

Use these rules after `smartcmp_analyze_resource_cost` returns its deterministic evidence pack.

## Evidence order

1. Present active SmartCMP violations as platform-confirmed findings.
2. Present enabled applicable policy coverage and resource execution state separately.
3. Treat `COMPLIANCE` as clear only when `evidenceCompleteness=complete`.
4. Label every model-only opportunity as `llm_potential` and state its confidence.
5. Use exact amounts only from `financialEvidence`; never add overlapping violation estimates.
6. Return `indeterminate` when required billing, utilization, or policy evidence is unavailable.

For every potential opportunity, provide its evidence, missing evidence, operational risk, and the
next read-only validation step. Do not produce a remediation action from model-only evidence.

## VM profile

Consider these themes when the corresponding evidence exists:

- stopped but still allocated resources
- CPU and memory rightsizing over a representative observation period
- continuously running pay-as-you-go resources with stable long-term demand
- unnecessary runtime outside business hours
- attached capacity that is billed but unused

Do not recommend rightsizing from static CPU or memory allocation alone. Require utilization and
peak evidence, and account for workload seasonality before assigning medium or high confidence.

## AWS RDS profile

Consider these themes when the corresponding evidence exists:

- idle primary instances using connections, CPU, read IOPS, and write IOPS over a representative period
- instance-class rightsizing using CPU, freeable memory, connections, latency, and burst balance
- payment-model optimization for stable long-lived workloads
- storage optimization using allocated capacity, free space, growth, IOPS, and storage type
- read-replica, Multi-AZ, or topology changes only when workload and availability requirements are known

Do not infer that an RDS resource is idle from missing monitoring data. A small instance class does
not by itself prove that further downsizing is safe. Treat backup retention, deletion protection,
public accessibility, and similar settings as reliability or security context, not savings.

## Generic profile

For other cloud, software, hardware, and virtualization resources:

- identify cost drivers only from visible type, capacity, billing, lifecycle state, and utilization facts
- prefer active policy evidence over generic heuristics
- explain which usage, license, maintenance, purchase, or billing evidence is needed for quantification
- keep the financial impact amount `null` when SmartCMP supplies no amount

The absence of an applicable enabled policy means `not_covered`; it does not prove that the resource
is optimized.
