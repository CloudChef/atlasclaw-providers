---
name: "github"
description: "GitHub provider skill backed by the gh CLI. Use for GitHub repositories, pull requests, issues, workflow runs, checks, releases, search, and gh api queries."
category: "provider:github"
provider_type: "github"
instance_required: "true"

triggers:
  - github
  - gh
  - pull request
  - pr checks
  - github actions
  - workflow run
  - issue
  - repository

use_when:
  - User wants to inspect or operate on GitHub repositories, PRs, issues, checks, workflow runs, releases, or GitHub API resources
  - User provides a GitHub repository URL, PR number, issue number, workflow run ID, or gh command intent

avoid_when:
  - User wants generic issue tracking outside GitHub
  - User wants local git-only operations that do not need GitHub APIs

tool_cli_name: "github_cli"
tool_cli_description: "Run an authenticated gh CLI command using the selected GitHub provider instance and current user's GitHub token."
tool_cli_entrypoint: "scripts/github_cli.py:github_cli_handler"
tool_cli_groups:
  - github
  - repo
tool_cli_capability_class: "provider:github"
tool_cli_priority: 120
tool_cli_parameters: {"type":"object","properties":{"args":{"type":"array","description":"Arguments passed after the gh executable, for example [\"pr\",\"checks\",\"55\"]. Do not include the leading gh.","items":{"type":"string"}},"repo":{"type":"string","description":"Optional GitHub repository in [HOST/]OWNER/REPO form. Passed through GH_REPO instead of adding --repo."},"timeout_seconds":{"type":"integer","description":"Optional command timeout in seconds. Defaults to the provider instance timeout or 120."}},"required":["args"]}
---

# GitHub

Use this provider skill for authenticated GitHub operations through `gh`.

The runtime supplies the selected provider instance and the current user's
GitHub token. Do not ask the user to run `gh auth login`; this provider uses
AtlasClaw `user_token` credentials and non-interactive environment variables.

## Common Commands

Check CI status on a pull request:

```json
{"args": ["pr", "checks", "55"], "repo": "owner/repo"}
```

List recent workflow runs:

```json
{"args": ["run", "list", "--limit", "10"], "repo": "owner/repo"}
```

View a run and show failed logs:

```json
{"args": ["run", "view", "123456789", "--log-failed"], "repo": "owner/repo"}
```

Fetch a PR field through the GitHub API:

```json
{"args": ["api", "repos/owner/repo/pulls/55", "--jq", ".title"]}
```

## Safety

Commands that create or change GitHub data, including PRs, comments, reviews,
issues, workflow dispatches, releases, repository settings, or merges, require
clear user intent and any required confirmation before running.
