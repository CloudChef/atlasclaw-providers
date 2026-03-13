# Provider Templates

Quick-copy templates for creating AtlasClaw providers.

## PROVIDER.md Template

```yaml
---
provider_type: my-provider
display_name: My Provider
version: "1.0.0"

keywords:
  - keyword1
  - keyword2

capabilities:
  - Create and manage resources
  - Query and search data

use_when:
  - User wants to interact with My Provider system
  - User mentions resource management

avoid_when:
  - User is asking about unrelated system (use other-provider)
---

# My Provider

Integration with My Provider API.

## Connection Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `base_url` | string | Yes | API base URL |
| `api_key` | string | Yes | API authentication key |

## Configuration Example

```json
{
  "service_providers": {
    "my-provider": {
      "default": {
        "base_url": "${MY_PROVIDER_URL}",
        "api_key": "${MY_PROVIDER_API_KEY}"
      }
    }
  }
}
```

## Provided Skills

| Skill | Description |
|-------|-------------|
| `my-provider-action` | Perform action |
```

---

## SKILL.md Template

```yaml
---
name: "my-provider-action"
description: "Perform action on My Provider. Use when user wants to do action."
category: "provider:my-provider"
provider_type: "my-provider"
instance_required: "true"

triggers:
  - do action
  - perform action

use_when:
  - User wants to perform action
  - User mentions action keywords

avoid_when:
  - User wants different action (use other-skill)

examples:
  - "Do the action for X"
  - "Perform action on Y"

related:
  - my-provider-other-skill
---

# my-provider-action

## Purpose

Performs action on My Provider system.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| target | string | Yes | Target resource |

## Usage

```bash
python scripts/handler.py --target "value"
```
```

---

## handler.py Template

```python
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import requests


def get_config() -> dict[str, Any]:
    with open("atlasclaw.json", "r", encoding="utf-8") as f:
        config = json.load(f)
    return config.get("service_providers", {}).get("my-provider", {}).get("default", {})


def handler(params: dict[str, Any]) -> dict[str, Any]:
    config = get_config()
    base_url = config.get("base_url", "").rstrip("/")
    api_key = config.get("api_key", "")
    
    try:
        response = requests.get(
            f"{base_url}/api/endpoint",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30
        )
        response.raise_for_status()
        return {"success": True, "message": "Done", "data": response.json()}
    except Exception as e:
        return {"success": False, "message": str(e), "error": {"code": "ERROR"}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    
    result = handler({"target": args.target})
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
```

---

## Directory Creation Script

PowerShell script to create provider structure:

```powershell
$provider = "my-provider"
$skill = "my-provider-action"
$base = ".atlasclaw/providers/$provider"

New-Item -ItemType Directory -Force -Path "$base/skills/$skill/scripts"
New-Item -ItemType Directory -Force -Path "$base/references"

# Create placeholder files
"" | Out-File "$base/PROVIDER.md"
"" | Out-File "$base/skills/$skill/SKILL.md"
"" | Out-File "$base/skills/$skill/scripts/handler.py"

Write-Host "Created provider structure at $base"
```

Bash equivalent:

```bash
provider="my-provider"
skill="my-provider-action"
base=".atlasclaw/providers/$provider"

mkdir -p "$base/skills/$skill/scripts"
mkdir -p "$base/references"

touch "$base/PROVIDER.md"
touch "$base/skills/$skill/SKILL.md"
touch "$base/skills/$skill/scripts/handler.py"

echo "Created provider structure at $base"
```
