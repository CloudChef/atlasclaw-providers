---
name: create-provider
description: Create new AtlasClaw providers with proper structure, documentation, and skills. Use when building integrations with external systems like APIs, ITSM, CRM, or custom services.
---

# Create AtlasClaw Provider

Guide for creating new providers that integrate external systems with the AtlasClaw AI Agent.

## Quick Start Checklist

```
Provider Creation Progress:
- [ ] 1. Gather requirements (system type, auth method, capabilities)
- [ ] 2. Create provider directory structure
- [ ] 3. Write PROVIDER.md with LLM context fields
- [ ] 4. Create skills for each capability
- [ ] 5. Add configuration to atlasclaw.json
- [ ] 6. Test provider loading and skill execution
```

## Phase 1: Gather Requirements

Before creating a provider, determine:

| Question | Example Answer |
|----------|----------------|
| **Provider type** | `servicenow`, `github`, `datadog` |
| **Display name** | ServiceNow, GitHub, Datadog |
| **Authentication method** | Basic Auth, API Token, OAuth 2.0, Cookie |
| **Base URL pattern** | `https://instance.service-now.com` |
| **Key capabilities** | CRUD incidents, manage users, query metrics |
| **Target keywords** | incident, ticket, alert, deployment |

## Phase 2: Directory Structure

Create provider at: `{workspace}/providers/{provider-name}/`

```
providers/{provider-name}/
├── PROVIDER.md           # Required - provider metadata and documentation
├── README.md             # Optional - human documentation
├── skills/               # Required - at least one skill
│   └── {skill-name}/
│       ├── SKILL.md      # Required - skill metadata
│       └── scripts/      # Required for executable skills
│           └── handler.py
└── references/           # Optional - API docs, mappings
    └── api_mapping.md
```

## Phase 3: PROVIDER.md Template

```yaml
---
# === Required Fields ===
provider_type: {provider-name}        # Must match directory name
display_name: {Display Name}
version: "1.0.0"

# === LLM Context Fields (for Skill Discovery) ===
keywords:
  - keyword1                          # Domain-specific terms users might say
  - keyword2
  - keyword3

capabilities:
  - Capability description 1
  - Capability description 2

use_when:
  - User intent scenario 1
  - User intent scenario 2

avoid_when:
  - Scenario when other provider is better (suggest alternative)
---

# {Display Name} Provider

Brief description of what this provider integrates with.

## Connection Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `base_url` | string | Yes | API base URL |
| `username` | string | Conditional | Username for auth |
| `password` | string | Conditional | Password or token |
| `api_key` | string | Conditional | API key if applicable |

## Authentication Modes

| Mode | Parameters | Notes |
|------|------------|-------|
| Basic Auth | `username` + `password` | Standard HTTP Basic |
| API Token | `api_key` | Bearer token auth |

## Configuration Example

```json
{
  "service_providers": {
    "{provider-name}": {
      "default": {
        "base_url": "${PROVIDER_URL}",
        "api_key": "${PROVIDER_API_KEY}"
      }
    }
  }
}
```

## Environment Variables

```bash
PROVIDER_URL=https://api.example.com
PROVIDER_API_KEY=your-api-key
```

## Provided Skills

| Skill | Description |
|-------|-------------|
| `{provider}-{action}` | Brief description |
```

## Phase 4: SKILL.md Template

```yaml
---
name: "{provider}-{action}"
description: "Brief description. Trigger when user wants to {action}."
category: "provider:{provider-name}"
provider_type: "{provider-name}"
instance_required: "true"

# === LLM Context Fields ===
triggers:
  - action phrase 1
  - action phrase 2

use_when:
  - User intent scenario 1
  - User intent scenario 2

avoid_when:
  - Scenario when other skill is better

examples:
  - "Example user input 1"
  - "Example user input 2"

related:
  - related-skill-1
  - related-skill-2

# === Tool Registration ===
tool_name: "{provider}_{action}"
tool_entrypoint: "scripts/handler.py:handler"
---

# {provider}-{action}

## Purpose

What this skill does and when to use it.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| param1 | string | Yes | Description |
| param2 | integer | No | Description (default: 10) |

## Usage Examples

**Example 1**: Basic usage
```bash
python scripts/handler.py --param1 "value"
```

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| AUTH_FAILED | Invalid credentials | Check API key |
```

## Phase 5: Handler Template

Create `scripts/handler.py`:

```python
# -*- coding: utf-8 -*-
"""
{Skill Name} Handler

Implements the {action} functionality for {Provider} provider.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Optional

import requests


def get_provider_config() -> dict[str, Any]:
    """Load provider configuration from atlasclaw.json."""
    config_path = os.environ.get("ATLASCLAW_CONFIG", "atlasclaw.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    provider_config = config.get("service_providers", {}).get("{provider-name}", {})
    instance = os.environ.get("PROVIDER_INSTANCE", "default")
    return provider_config.get(instance, {})


def handler(params: dict[str, Any]) -> dict[str, Any]:
    """
    Main handler function.
    
    Args:
        params: Input parameters
        
    Returns:
        Result dictionary with success, message, and data
    """
    config = get_provider_config()
    base_url = config.get("base_url", "").rstrip("/")
    api_key = config.get("api_key", "")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        # Implement API call here
        response = requests.get(
            f"{base_url}/api/endpoint",
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        
        return {
            "success": True,
            "message": "Operation completed successfully",
            "data": response.json()
        }
    except requests.RequestException as e:
        return {
            "success": False,
            "message": f"API request failed: {str(e)}",
            "error": {"code": "API_ERROR", "details": str(e)}
        }


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="{Skill description}")
    parser.add_argument("--param1", required=True, help="Parameter 1")
    parser.add_argument("--param2", type=int, default=10, help="Parameter 2")
    
    args = parser.parse_args()
    
    result = handler({
        "param1": args.param1,
        "param2": args.param2
    })
    
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
```

## Phase 6: Configuration

Add to `atlasclaw.json`:

```json
{
  "service_providers": {
    "{provider-name}": {
      "default": {
        "base_url": "${PROVIDER_URL}",
        "api_key": "${PROVIDER_API_KEY}"
      },
      "production": {
        "base_url": "${PROVIDER_PROD_URL}",
        "api_key": "${PROVIDER_PROD_API_KEY}"
      }
    }
  }
}
```

Add to `.env`:

```bash
PROVIDER_URL=https://api.example.com
PROVIDER_API_KEY=your-api-key
```

## Phase 7: Verification

1. **Restart service** (or wait for hot reload)
2. **Check logs** for provider loading:
   ```
   [AtlasClaw] Provider loaded: {provider-name}
   [AtlasClaw] Skills loaded: X from {provider-name}
   ```
3. **Test via API**:
   ```bash
   curl http://localhost:8000/api/skills | grep {provider-name}
   ```

## LLM Context Best Practices

### Keywords
- Use domain-specific terms users naturally say
- Avoid generic terms like "create", "update", "manage"
- Include abbreviations and synonyms

### use_when
- Describe user intent, not technical actions
- Focus on business scenarios
- Include common phrasings

### avoid_when
- Critical for disambiguation between similar providers
- Always suggest the correct alternative
- Include commonly confused scenarios

## Common Provider Types

| Type | Examples | Typical Keywords |
|------|----------|------------------|
| ITSM | ServiceNow, Jira | incident, ticket, issue, sprint |
| Monitoring | Datadog, Prometheus | alert, metric, dashboard |
| Communication | Slack, Teams | message, channel, notification |
| Version Control | GitHub, GitLab | repository, PR, merge, commit |
| CRM | Salesforce | lead, opportunity, account |
| Cloud | AWS, Azure | instance, resource, deployment |

## Additional Resources

- [PROVIDER_GUIDE.md](file:///c:/Projects/cmps/atlasclaw/docs/PROVIDER_GUIDE.md) - Full documentation
- [SKILL_GUIDE.md](file:///c:/Projects/cmps/atlasclaw/docs/SKILL_GUIDE.md) - Skill development guide
- [Jira Provider](file:///c:/Projects/cmps/atlasclaw/.atlasclaw/providers/jira) - Reference implementation
