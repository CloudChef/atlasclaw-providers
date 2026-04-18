---
# === Provider Identity ===
provider_type: github
display_name: GitHub
version: "1.0.0"

# === LLM Context Fields (for Skill Discovery) ===
keywords:
  - github
  - pull request
  - workflow
  - actions
  - checks
  - ci
  - repository

capabilities:
  - List recent accessible repositories
  - Inspect pull request checks and commit status
  - List GitHub Actions workflow runs
  - View workflow run details and failed logs
  - Query selected read-only GitHub REST API endpoints

use_when:
  - User wants to inspect GitHub pull requests, CI checks, workflow runs, or run logs
  - User wants repository-scoped GitHub data from github.com
  - User has configured a personal GitHub token in their provider settings

avoid_when:
  - User wants to write to GitHub such as commenting, approving, merging, or rerunning workflows
  - User wants GitHub Enterprise Server support
  - User expects a shared organization token instead of a personal token
---

# GitHub Service Provider

GitHub.com read-only provider backed by GitHub REST API.

## Connection Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `base_url` | string | Fixed | GitHub REST base URL, fixed to `https://api.github.com` |
| `auth_type` | string | Fixed | Fixed to `user_token` |
| `user_token` | string | Yes | User-owned GitHub personal access token stored in the user's provider settings |

## Authentication Model

This provider supports **per-user credentials only**.

Allowed:

- GitHub fine-grained personal access token
- GitHub classic personal access token

Not supported:

- shared provider token in `atlasclaw.json`
- GitHub App installation token flow in phase 1
- GitHub Enterprise Server

## Provided Skills

| Skill | Description |
|-------|-------------|
| `github-repo` | List recent accessible repositories |
| `github-pr-checks` | Inspect PR checks and CI status |
| `github-run-list` | List recent workflow runs |
| `github-run-view` | View workflow run details |
| `github-run-failed-logs` | View failed workflow log excerpts |
| `github-api-query` | Query approved read-only REST endpoints |
