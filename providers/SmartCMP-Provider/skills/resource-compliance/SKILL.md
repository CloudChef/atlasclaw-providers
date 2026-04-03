---
name: "resource-compliance"
description: "Resource compliance skill. Analyze one or more SmartCMP resources for lifecycle, patch, and security risk."
provider_type: "smartcmp"
instance_required: "true"

triggers:
  - resource compliance
  - compliance analysis
  - security analysis
  - analyze resource
  - resource risk
  - mysql version
  - windows patch
  - linux security

use_when:
  - User wants to analyze one or more resources by ID for compliance or security risk
  - User wants to check whether a resource version is outdated, unsupported, or risky
  - Webhook payload includes resource IDs that need review

avoid_when:
  - User wants to browse general catalog data only (use datasource skill)
  - User wants to submit a provisioning request (use request skill)
  - User wants to approve or reject requests (use approval skill)

related:
  - datasource
---

# resource-compliance

Analyze one or more SmartCMP resources for lifecycle, patch, and security posture.

## Purpose

This skill fetches resource facts from SmartCMP and then performs explainable
analysis with optional live internet validation against authoritative sources.

## Scripts

| Script | Description | Location |
|--------|-------------|----------|
| `analyze_resource.py` | Analyze one or more resources by ID | `scripts/` |

## Workflow

See [references/WORKFLOW.md](references/WORKFLOW.md) for the supported workflow.
