---
name: "jira-issue"
description: "Jira issue skill for CRUD. Trigger when user asks to create, get, update, or delete Jira issues."
category: "provider:jira"
provider_type: "jira"
instance_required: "true"

# === LLM Context Fields (for Skill Discovery) ===
triggers:
  - create issue
  - get issue
  - update issue
  - delete issue
  - report bug
  - log incident

use_when:
  - User wants to create, read, update, or delete Jira issues
  - User mentions bug reports or incident logging
  - User asks about issue details by issue key

avoid_when:
  - User wants to search multiple issues (use jira-search skill)
  - User wants bulk operations (use jira-bulk skill)
  - User asks about worklogs or time tracking (use jira-time skill)

examples:
  - "Create a Jira issue for the login bug"
  - "Get details for PROJ-123"
  - "Update the priority of PROJ-456 to High"
  - "Delete issue PROJ-789"

related:
  - jira-search
  - jira-bulk

# === Tool Registration ===
tool_create_name: "jira_issue_create"
tool_create_entrypoint: "scripts/jira_issue_create.py:handler"
tool_create_groups:
  - jira
  - issue
tool_create_capability_class: "provider:jira"
tool_create_priority: 120
tool_get_name: "jira_issue_get"
tool_get_entrypoint: "scripts/jira_issue_get.py:handler"
tool_get_groups:
  - jira
  - issue
tool_get_capability_class: "provider:jira"
tool_get_priority: 100
tool_update_name: "jira_issue_update"
tool_update_entrypoint: "scripts/jira_issue_update.py:handler"
tool_update_groups:
  - jira
  - issue
tool_update_capability_class: "provider:jira"
tool_update_priority: 130
tool_delete_name: "jira_issue_delete"
tool_delete_entrypoint: "scripts/jira_issue_delete.py:handler"
tool_delete_groups:
  - jira
  - issue
tool_delete_capability_class: "provider:jira"
tool_delete_priority: 140
---

# jira-issue

This is a provider skill under `providers/jira/skills/jira-issue`.

## Purpose

Handle Jira Issue CRUD by orchestrating local scripts in `scripts/` that call Jira REST API.

## Trigger Conditions

Use this skill when user intent is any of:
- Create issue / report bug / log incident
- Get issue details
- Update issue fields
- Delete issue

## Script Entry Points

- `scripts/create_issue.py`
- `scripts/get_issue.py`
- `scripts/update_issue.py`
- `scripts/delete_issue.py`

## Invocation Guidance

When the user says:
- "Create a Jira issue for service startup failure"

Construct and run:

```bash
python app/atlasclaw/providers/jira/skills/jira-issue/scripts/create_issue.py \
  --summary "Service startup failure" \
  --description "Service failed to start due to a database connection timeout"
```

Then return created issue key to user.

## Notes

- Scripts read Jira connection from `atlasclaw.json` (`service_providers.jira`).
- API mappings are in `references/api_mapping.md`.
- Skill scripts are part of this skill package, not standalone global skills.
