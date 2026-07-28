# Jira Provider

The Jira provider supplies Jira issue CRUD operations to AtlasClaw. It calls
the Jira REST API directly through the scripts bundled with the
`jira-issue` skill.

## Supported operations

- Create an issue.
- Read an issue by key.
- Update supported issue fields.
- Delete an issue after AtlasClaw obtains the required confirmation.

Search, bulk operations, sprint administration, and worklog management are not
currently exposed by this provider.

## Configuration

Create a Jira provider instance in AtlasClaw and configure these fields:

| Field | Required | Description |
| --- | --- | --- |
| `base_url` | Yes | Jira Server/Data Center or Atlassian Cloud base URL. |
| `username` | Yes | Jira username, or the account email for Atlassian Cloud. |
| `password` | Yes | Server/Data Center password, or Atlassian Cloud API token. |
| `api_version` | No | REST API version. Use `2` for Server/Data Center and `3` for Cloud. |
| `default_project` | No | Project key used when a request omits one. |
| `project_keys` | No | Comma-separated project keys available to the instance. |

Credentials are stored and resolved through AtlasClaw provider configuration.
The current client uses HTTP Basic authentication. Jira Data Center personal
access tokens, which require Bearer authentication, are not supported. The
skill does not require a separately installed Jira CLI.

## Runtime layout

```text
providers/jira/
├── PROVIDER.md
├── provider.schema.json
└── skills/
    └── jira-issue/
        ├── SKILL.md
        ├── references/
        └── scripts/
```

The registered tool entry points live in
`skills/jira-issue/scripts/jira_issue_*.py`. The command-line adapters in the
same directory are implementation helpers for the skill, not standalone
packages.

## Dependencies and tests

Jira uses the shared dependencies declared by the repository root
`requirements.txt`. Development and test dependencies are declared in
`requirements-dev.txt`.

Run the provider manifest test from the repository root:

```bash
python -m pytest providers/jira/test -q
```
