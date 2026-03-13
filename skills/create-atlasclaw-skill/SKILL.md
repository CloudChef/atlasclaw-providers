---
name: create-atlasclaw-skill
description: Create new AtlasClaw skills with proper structure, metadata, and documentation. Use when building executable skills, markdown skills, or provider skills for the AtlasClaw AI Agent.
---

# Create AtlasClaw Skill

Guide for creating new skills that extend the AtlasClaw AI Agent's capabilities.

## Quick Start Checklist

```
Skill Creation Progress:
- [ ] 1. Gather requirements (skill type, purpose, triggers)
- [ ] 2. Choose storage location (personal or project)
- [ ] 3. Create skill directory structure
- [ ] 4. Write SKILL.md with LLM context fields
- [ ] 5. Implement handler (for executable skills)
- [ ] 6. Test skill loading and execution
```

## Phase 1: Gather Requirements

Before creating a skill, determine:

| Question | Options |
|----------|---------|
| **Skill type** | `executable` (Python code), `markdown` (documentation), `hybrid` (both) |
| **Category** | `provider:<name>`, `system`, `utility`, `workflow` |
| **Associated provider** | Provider type (for provider skills) |
| **Storage location** | `~/.qoder/skills/` (personal) or `.qoder/skills/` (project) |
| **Target keywords** | Words users naturally say to trigger this skill |

## Phase 2: Directory Structure

Create skill at: `{location}/skills/{skill-name}/`

### Minimal Structure (Markdown Skill)

```
skills/{skill-name}/
└── SKILL.md              # Required - skill metadata and documentation
```

### Complete Structure (Executable Skill)

```
skills/{skill-name}/
├── SKILL.md              # Required - skill metadata
├── README.md             # Optional - extended documentation
├── scripts/              # Required for executable skills
│   ├── __init__.py
│   └── handler.py        # Main implementation
├── tests/                # Optional - test files
│   └── test_handler.py
└── references/           # Optional - reference docs
    └── api_reference.md
```

## Phase 3: SKILL.md Template

```yaml
---
name: "{skill-name}"
description: "Brief description. Trigger when user wants to {action}."
category: "{category}"
provider_type: "{provider}"           # For provider skills only
instance_required: "{true|false}"     # For provider skills only
version: "1.0.0"
author: "your@email.com"

# === LLM Context Fields (for Skill Discovery) ===
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

# === Tool Registration (for executable skills) ===
tool_name: "{skill_name}"
tool_entrypoint: "scripts/handler.py:handler"
---

# {skill-name}

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

Input:
```json
{
  "param1": "value1"
}
```

Output:
```json
{
  "success": true,
  "message": "Operation completed",
  "data": { "result": "value" }
}
```

## Error Handling

### Common Errors

| Error | Cause | Resolution |
|-------|-------|------------|
| INVALID_PARAM | Invalid input | Check parameter format |
| AUTH_FAILED | Authentication error | Check credentials |

## Related Skills

- `related-skill` - Description

## Notes

Additional information, limitations, or considerations.
```

## Phase 4: Handler Template (Executable Skills)

Create `scripts/handler.py`:

```python
# -*- coding: utf-8 -*-
"""
{Skill Name} Handler

Implements the {action} functionality.
"""
from __future__ import annotations

import argparse
import json
import os
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
        # Implement skill logic here
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

## Phase 5: Skill Types Reference

### 1. Markdown Skills (Documentation)

For providing knowledge without executable code:

```yaml
---
name: "coding-standards"
description: "Apply team coding standards and best practices. Use when reviewing code or discussing implementation approaches."
category: "utility"
---

# Coding Standards

## Python Style

- Use type hints on all functions
- Follow PEP 8 naming conventions
- Maximum line length: 100 characters

## Error Handling

- Use specific exception types
- Include context in error messages
- Return structured error responses
```

### 2. Executable Skills (Python)

For performing actions:

```yaml
---
name: "file-reader"
description: "Read and parse file contents. Trigger when user wants to read files."
category: "system"

triggers:
  - read file
  - parse file

use_when:
  - User wants to read file contents
  - User needs to parse a file

tool_name: "file_reader"
tool_entrypoint: "scripts/handler.py:handler"
---
```

### 3. Provider Skills

For integrating with external systems:

```yaml
---
name: "jira-issue"
description: "Jira issue skill for CRUD operations. Trigger when user wants to manage Jira issues."
category: "provider:jira"
provider_type: "jira"
instance_required: "true"

triggers:
  - create issue
  - update issue

use_when:
  - User wants to create or update Jira issues

tool_create_name: "jira_issue_create"
tool_create_entrypoint: "scripts/create_issue.py:handler"
---
```

## Phase 6: Verification

1. **Check file location**:
   ```bash
   ls -la {workspace}/skills/{skill-name}/
   ```

2. **Restart service** (or wait for hot reload)

3. **Check logs** for skill loading:
   ```
   [AtlasClaw] Skills loaded: X executable, Y markdown
   ```

4. **Test via API**:
   ```bash
   curl http://localhost:8000/api/skills | grep {skill-name}
   ```

## LLM Context Best Practices

### Triggers
- Use action-oriented phrases
- Include synonyms and variations
- Focus on user intent, not technical terms

**Good triggers:**
- `create issue`, `report bug`, `log incident`
- `read file`, `parse document`
- `analyze data`, `generate report`

### use_when
- Describe user scenarios, not technical capabilities
- Focus on business value
- Include common phrasings

**Good use_when:**
- "User wants to create a bug report"
- "User needs to read file contents"
- "User asks about incident details"

### avoid_when
- Critical for disambiguation
- Always suggest the correct alternative
- Include commonly confused scenarios

**Good avoid_when:**
- "User wants to search multiple issues (use jira-search skill)"
- "User wants bulk operations (use jira-bulk skill)"

### Examples
- Provide concrete, realistic examples
- Include variations in phrasing
- Show both simple and complex cases

**Good examples:**
- "Create a Jira issue for the login bug"
- "Get details for PROJ-123"
- "Update the priority of INC0012345 to High"

## Skill Categories

| Category | Use Case | Example |
|----------|----------|---------|
| `provider:<name>` | External system integration | `provider:jira`, `provider:servicenow` |
| `system` | OS-level operations | File operations, process management |
| `utility` | General-purpose tools | Data transformation, calculations |
| `workflow` | Multi-step processes | Approval workflows, onboarding |

## Common Skill Patterns

### File Operations
```yaml
triggers:
  - read file
  - parse file
  - analyze document

use_when:
  - User wants to read or parse file contents
  - User needs to extract data from files
```

### Data Analysis
```yaml
triggers:
  - analyze data
  - generate report
  - calculate metrics

use_when:
  - User wants to analyze data
  - User needs reports or metrics
```

### API Integration
```yaml
triggers:
  - create issue
  - update record
  - query data

use_when:
  - User wants to interact with external system
  - User needs to create or update records
```

## Additional Resources

- [SKILL_GUIDE.md](file:///c:/Projects/cmps/atlasclaw/docs/SKILL_GUIDE.md) - Full skill development guide
- [Jira Skill](file:///c:/Projects/cmps/atlasclaw/.atlasclaw/providers/jira/skills/jira-issue) - Reference implementation
- [create-atlasclaw-provider skill](file:///c:/Projects/cmps/atlasclaw/.qoder/skills/create-atlasclaw-provider) - For creating providers
