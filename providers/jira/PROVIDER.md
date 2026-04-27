---
# === Provider Identity ===
provider_type: jira
display_name: Jira
version: "1.0.0"

# === LLM Context Fields (for Skill Discovery) ===
keywords:
  - issue
  - story
  - sprint
  - project
  - backlog
  - epic
  - bug

capabilities:
  - Create and manage issues
  - Search issues with JQL queries
  - Track project progress and sprints
  - Manage worklogs and time tracking
  - Bulk operations on issues

use_when:
  - User mentions issue tracking or project management
  - User wants to create, search, update, or delete issues
  - User references Jira, JIRA, or Atlassian issue tracker
  - User asks about sprints, backlogs, or agile boards
  - User wants to track work time or worklogs

avoid_when:
  - User is asking about documentation or wikis (use Confluence provider)
  - User wants to manage code repositories (use Bitbucket/GitHub provider)
  - User is asking about CI/CD pipelines (use Jenkins/GitLab provider)
---

# JIRA Service Provider

JIRA project management and issue tracking service. Supports both JIRA Server/Data Center and Atlassian Cloud deployments.

## Connection Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `base_url` | string | Yes | JIRA instance URL (e.g., `http://jira.corp.com:8080` or `https://company.atlassian.net`) |
| `username` | string | Yes (Server/DC) | JIRA username for Server/DC Basic Auth |
| `password` | string | Yes | Password or PAT (Server/DC) or API Token (Cloud). Use `${JIRA_API_TOKEN}` env var |
| `api_version` | string | No | REST API version: `"2"` for Server/DC (default), `"3"` for Cloud |
| `default_project` | string | No | Default project key (e.g., `"PROJ"`) |
| `project_keys` | string[] | No | List of accessible project keys (e.g., `["PROJ", "OPS"]`) |

### Authentication Modes

| Deployment | Auth Method | Parameters |
|------------|------------|------------|
| **Server/DC** | Basic Auth (username + password/PAT) | `username` + `password`, `api_version: "2"` |
| **Cloud** | Email + API Token | `username` (email) + `password` (API Token), `api_version: "3"` |

`password` is the canonical credential field. For Jira Cloud, store the API
token value in `password`.

## Configuration Example

### JIRA Server/DC

```json
{
  "service_providers": {
    "jira": {
      "prod": {
        "base_url": "http://jira.corp.com:8080",
        "username": "admin",
        "password": "${JIRA_PROD_TOKEN}",
        "api_version": "2",
        "default_project": "PROJ"
      }
    }
  }
}
```

### Atlassian Cloud

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

## Environment Variables for `jira-as` CLI

The JIRA skills use the `jira-as` CLI which reads credentials from environment variables. Set these in `.env` or your shell profile:

**Server/DC:**
```bash
JIRA_SITE_URL=http://jira.corp.com:8080
JIRA_USERNAME=your-username
JIRA_PASSWORD=your-password
```

**Cloud:**
```bash
JIRA_SITE_URL=https://company.atlassian.net
JIRA_EMAIL=your-email@company.com
JIRA_API_TOKEN=your-api-token
```

## Provided Skills

| Skill | Description | Key Commands |
|-------|-------------|--------------|
| `jira-issue` | Core issue CRUD operations | `jira-as issue create`, `get`, `update`, `delete` |
| `jira-search` | JQL queries, saved filters, export | `jira-as search query`, `export`, `filter`, `bulk-update` |
| `jira-bulk` | Bulk transitions, assignments, cloning | `jira-as bulk transition`, `assign`, `clone`, `delete` |
| `jira-fields` | Custom field discovery, agile config | `jira-as fields list`, `check-project`, `configure-agile` |
| `jira-time` | Worklogs, estimates, time reports | `jira-as time log`, `worklogs`, `report`, `export` |
