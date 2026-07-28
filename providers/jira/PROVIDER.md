---
# === Provider Identity ===
provider_type: jira
display_name: Jira
version: "1.0.0"

# === LLM Context Fields (for Skill Discovery) ===
keywords:
  - issue
  - story
  - project
  - bug
  - incident

capabilities:
  - Create Jira issues
  - Read Jira issues by key
  - Update Jira issue fields
  - Delete Jira issues

use_when:
  - User wants to create, read, update, or delete a Jira issue
  - User references a Jira issue key
  - User wants to report a bug or incident as a Jira issue

avoid_when:
  - User is asking about documentation or wikis
  - User wants to manage code repositories
  - User wants Jira search, bulk, sprint, or worklog operations
---

# Jira Service Provider

The Jira provider connects AtlasClaw to Jira Server, Jira Data Center, or
Atlassian Cloud. The current provider exposes issue CRUD through the bundled
`jira-issue` skill and calls Jira REST APIs directly.

## Connection parameters

| Parameter | Required | Description |
| --- | --- | --- |
| `base_url` | Yes | Jira instance URL. |
| `username` | Yes | Server/DC username or Atlassian Cloud account email. |
| `password` | Yes | Server/Data Center password, or Atlassian Cloud API token. |
| `api_version` | No | REST API version: `2` for Server/DC, `3` for Cloud. |
| `default_project` | No | Default Jira project key. |
| `project_keys` | No | Project keys available to this provider instance. |

`password` is the canonical credential field. AtlasClaw resolves these values
from provider configuration and passes them to the skill runtime. The current
client uses HTTP Basic authentication and therefore does not support Jira Data
Center personal access tokens, which require Bearer authentication.

## Configuration example

```json
{
  "service_providers": {
    "jira": {
      "cloud": {
        "base_url": "https://company.atlassian.net",
        "username": "admin@company.com",
        "password": "${JIRA_API_TOKEN}",
        "api_version": "3",
        "default_project": "PROJ"
      }
    }
  }
}
```

## Provided skill

| Skill | Operations | Runtime |
| --- | --- | --- |
| `jira-issue` | Create, get, update, and delete one issue | Bundled Python handlers calling Jira REST APIs |

The provider does not depend on an external Jira CLI or a separately installed
Python package.
