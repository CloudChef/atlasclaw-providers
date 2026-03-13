# Skill Templates

Quick-copy templates for creating AtlasClaw skills.

## Markdown Skill Template

```yaml
---
name: my-skill
description: Brief description of what this skill does and when to use it
category: utility
version: "1.0.0"
author: your@email.com

triggers:
  - trigger phrase 1
  - trigger phrase 2

use_when:
  - User wants to do something
  - User mentions specific keywords

avoid_when:
  - User wants something else (use other-skill)

examples:
  - "Example user input 1"
  - "Example user input 2"

related:
  - related-skill-1
---

# my-skill

## Purpose

What this skill does and when to use it.

## Guidelines

1. Step one
2. Step two
3. Step three

## Examples

### Example 1

Description of example.

### Example 2

Description of example.

## Notes

Additional information or considerations.
```

---

## Executable Skill Template

```yaml
---
name: my-skill
description: Brief description. Trigger when user wants to perform action.
category: utility
version: "1.0.0"
author: your@email.com

triggers:
  - action phrase 1
  - action phrase 2

use_when:
  - User wants to perform action
  - User mentions specific keywords

avoid_when:
  - User wants different action (use other-skill)

examples:
  - "Example user input 1"
  - "Example user input 2"

related:
  - related-skill-1

tool_name: "my_skill"
tool_entrypoint: "scripts/handler.py:handler"
---

# my-skill

## Purpose

What this skill does and when to use it.

## Parameters

### Input

| Name | Type | Required | Description |
|------|------|----------|-------------|
| param1 | string | Yes | Description |
| param2 | integer | No | Description (default: 10) |

### Output

| Name | Type | Description |
|------|------|-------------|
| success | boolean | Whether operation succeeded |
| message | string | Human-readable result |
| data | object | Structured result data |

## Usage Examples

### Example 1: Basic Usage

```bash
python scripts/handler.py --param1 "value"
```

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| INVALID_PARAM | Invalid input | Check parameter format |
```

---

## Handler.py Template

```python
# -*- coding: utf-8 -*-
"""
Skill Handler

Implements the skill functionality.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def handler(params: dict[str, Any]) -> dict[str, Any]:
    """
    Main handler function.
    
    Args:
        params: Input parameters
        
    Returns:
        Result dictionary with success, message, and data
    """
    try:
        # Validate inputs
        if "required_param" not in params:
            raise ValueError("required_param is required")
        
        # Process request
        result = process_request(params)
        
        return {
            "success": True,
            "message": "Operation completed successfully",
            "data": result
        }
    except ValueError as e:
        return {
            "success": False,
            "message": f"Invalid input: {str(e)}",
            "error": {"code": "INVALID_PARAM", "details": str(e)}
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error: {str(e)}",
            "error": {"code": "EXECUTION_ERROR", "details": str(e)}
        }


def process_request(params: dict[str, Any]) -> dict[str, Any]:
    """Process the request and return result."""
    # Implement business logic here
    return {"result": "success"}


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Skill description")
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

---

## Provider Skill Template

```yaml
---
name: "provider-action"
description: "Provider action skill. Trigger when user wants to perform action on system."
category: "provider:my-provider"
provider_type: "my-provider"
instance_required: "true"
version: "1.0.0"

triggers:
  - create record
  - update record
  - get record

use_when:
  - User wants to create or update records
  - User needs to query system data

avoid_when:
  - User wants to search multiple records (use provider-search skill)
  - User wants bulk operations (use provider-bulk skill)

examples:
  - "Create a record for X"
  - "Get details for REC-123"
  - "Update priority of REC-456"

related:
  - provider-search
  - provider-bulk

tool_create_name: "provider_record_create"
tool_create_entrypoint: "scripts/create_record.py:handler"
tool_get_name: "provider_record_get"
tool_get_entrypoint: "scripts/get_record.py:handler"
tool_update_name: "provider_record_update"
tool_update_entrypoint: "scripts/update_record.py:handler"
---

# provider-action

## Purpose

Handle record operations on the external system.

## Operations

### Create Record

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| name | string | Yes | Record name |
| description | string | No | Record description |

**Example:**
```bash
python scripts/create_record.py --name "My Record" --description "Details"
```

### Get Record

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| id | string | Yes | Record ID |

### Update Record

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| id | string | Yes | Record ID |
| fields | object | Yes | Fields to update |

## Notes

- Scripts read configuration from `atlasclaw.json`
- Authentication uses provider credentials
```

---

## Directory Creation Script

PowerShell:

```powershell
$skill = "my-skill"
$location = ".qoder/skills"  # or "~/.qoder/skills"
$base = "$location/$skill"

New-Item -ItemType Directory -Force -Path "$base/scripts"
New-Item -ItemType Directory -Force -Path "$base/tests"
New-Item -ItemType Directory -Force -Path "$base/references"

# Create placeholder files
"" | Out-File "$base/SKILL.md"
"" | Out-File "$base/scripts/__init__.py"
"" | Out-File "$base/scripts/handler.py"

Write-Host "Created skill structure at $base"
```

Bash:

```bash
skill="my-skill"
location=".qoder/skills"  # or "~/.qoder/skills"
base="$location/$skill"

mkdir -p "$base/scripts"
mkdir -p "$base/tests"
mkdir -p "$base/references"

touch "$base/SKILL.md"
touch "$base/scripts/__init__.py"
touch "$base/scripts/handler.py"

echo "Created skill structure at $base"
```
