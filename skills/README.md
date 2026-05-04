# Imported IT Operation Skills

This directory contains standalone IT Operation skills imported for use with AtlasClaw and the SmartCMP Provider. SmartCMP supplies optional context such as `resource.data`, `alarmContext`, and `costContext`; these skills remain loosely coupled and return their own structured analysis output.

## Source Inventory

| Skill | Upstream source | Upstream path | Imported assets | Notes |
|---|---|---|---|---|
| `senior-secops` | `https://github.com/alirezarezvani/claude-skills` | `engineering-team/skills/senior-secops/` | `SKILL.md` only | Upstream also provides `scripts/` and `references/`; local import is currently prompt-only until those assets are added. |
| `information-security-manager-iso27001` | `https://github.com/alirezarezvani/claude-skills` | `ra-qm-team/skills/information-security-manager-iso27001/` | `SKILL.md` only | Upstream also provides `risk_assessment.py`, `compliance_checker.py`, and ISO 27001 references. |
| `azure-policy` | `https://github.com/MicrosoftDocs/Agent-Skills` | `skills/azure-policy/` | `SKILL.md` | Microsoft documentation skill. Requires live docs access for freshest source grounding. |
| `azure-security` | `https://github.com/MicrosoftDocs/Agent-Skills` | `skills/azure-security/` | `SKILL.md` | Microsoft documentation skill. Requires live docs access for freshest source grounding. |
| `azure-cost-management` | `https://github.com/MicrosoftDocs/Agent-Skills` | `skills/azure-cost-management/` | `SKILL.md` | Microsoft documentation skill. Requires live docs access for freshest source grounding. |
| `google-cloud-waf-security` | `https://github.com/google/skills` | `skills/cloud/google-cloud-waf-security/` | `SKILL.md` | Google Cloud Well-Architected Framework security pillar skill. |
| `prometheus-analysis` | `https://github.com/evangelosmeklis/thufir` | `skills/prometheus-analysis/` | `SKILL.md` only | Upstream `SKILL.md` references `references/promql-cookbook.md`; add it if cookbook-backed RCA examples are required. |
| `prometheus` | `https://github.com/majiayu000/claude-skill-registry` | `skills/product/prometheus/` | `SKILL.md` | Prometheus configuration, alerting, and PromQL guidance skill. |

## Download Commands for Missing Upstream Assets

Use these commands only when the corresponding scripts or references are needed locally. Keep the downloaded files under the same skill directory so the paths referenced by `SKILL.md` remain valid.

### `senior-secops`

```bash
base="https://raw.githubusercontent.com/alirezarezvani/claude-skills/main/engineering-team/skills/senior-secops"

mkdir -p skills/senior-secops/scripts skills/senior-secops/references

curl -fsSL "$base/scripts/security_scanner.py" -o skills/senior-secops/scripts/security_scanner.py
curl -fsSL "$base/scripts/vulnerability_assessor.py" -o skills/senior-secops/scripts/vulnerability_assessor.py
curl -fsSL "$base/scripts/compliance_checker.py" -o skills/senior-secops/scripts/compliance_checker.py

curl -fsSL "$base/references/security_standards.md" -o skills/senior-secops/references/security_standards.md
curl -fsSL "$base/references/compliance_requirements.md" -o skills/senior-secops/references/compliance_requirements.md
curl -fsSL "$base/references/vulnerability_management_guide.md" -o skills/senior-secops/references/vulnerability_management_guide.md

chmod +x skills/senior-secops/scripts/*.py
```

### `information-security-manager-iso27001`

```bash
base="https://raw.githubusercontent.com/alirezarezvani/claude-skills/main/ra-qm-team/skills/information-security-manager-iso27001"

mkdir -p skills/information-security-manager-iso27001/scripts
mkdir -p skills/information-security-manager-iso27001/references

curl -fsSL "$base/scripts/risk_assessment.py" -o skills/information-security-manager-iso27001/scripts/risk_assessment.py
curl -fsSL "$base/scripts/compliance_checker.py" -o skills/information-security-manager-iso27001/scripts/compliance_checker.py

curl -fsSL "$base/references/iso27001-controls.md" -o skills/information-security-manager-iso27001/references/iso27001-controls.md
curl -fsSL "$base/references/risk-assessment-guide.md" -o skills/information-security-manager-iso27001/references/risk-assessment-guide.md
curl -fsSL "$base/references/incident-response.md" -o skills/information-security-manager-iso27001/references/incident-response.md

chmod +x skills/information-security-manager-iso27001/scripts/*.py
```

## Validation

These skills are standalone Markdown skills. Validate the active import set by loading the current `skills/` directory through the AtlasClaw skill registry and by checking the SmartCMP Provider's own resource, alarm, and cost tests. The SmartCMP Provider does not maintain a separate machine-readable operation-skill catalog.
