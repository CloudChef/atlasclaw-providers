---
# === Provider Identity ===
provider_type: github
display_name: GitHub
version: "1.0.0"

# === LLM Context Fields (for Skill Discovery) ===
keywords:
  - github
  - repository
  - repo
  - pull request
  - pr
  - issue
  - workflow
  - actions
  - ci
  - release
  - git

capabilities:
  - Inspect repositories, issues, pull requests, workflow runs, checks, releases, and GitHub API resources through the GitHub CLI
  - Run authenticated GitHub CLI commands under the current user's GitHub token
  - Support GitHub.com and GitHub Enterprise Server instances

use_when:
  - User wants to inspect or operate on GitHub repositories, issues, pull requests, checks, workflow runs, releases, or GitHub API resources
  - User references GitHub, gh, repository URLs, PR numbers, issue numbers, or GitHub Actions runs

avoid_when:
  - User wants generic issue tracking outside GitHub repositories
  - User wants cloud resource or CMP workflows
---

# GitHub Provider

GitHub repository and CI provider backed by the `gh` CLI. The provider runs
GitHub commands with the current AtlasClaw user's configured GitHub token.

## Connection Parameters

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `base_url` | string | No | GitHub API base URL. Defaults to `https://api.github.com` for GitHub.com. |
| `hostname` | string | No | GitHub host for `gh`, such as `github.com` or `github.company.com`. If omitted, it is inferred from `base_url`. |
| `auth_type` | string | Yes | Must be `user_token` for this provider version. |
| `user_token` | string | User setting | User-owned GitHub personal access token or compatible user access token. |
| `timeout_seconds` | number | No | Default command timeout in seconds. Defaults to `120`. |

## Authentication Model

This provider uses AtlasClaw `user_token` authentication. Each user configures
their own GitHub token in AtlasClaw account settings. At runtime the provider
maps that token to the environment variables supported by `gh`:

- GitHub.com: `GH_TOKEN`
- GitHub Enterprise Server: `GH_ENTERPRISE_TOKEN` plus `GH_HOST`

The provider does not run `gh auth login` and does not write persistent `gh`
credentials. Each command receives an isolated temporary `GH_CONFIG_DIR`.

Use a fine-grained personal access token when possible. The token must include
the repository, organization, Actions, pull request, issue, or other permissions
required by the command being run. Organizations that enforce SAML SSO may also
require the token to be authorized in GitHub before private resources are
visible.

OAuth App and GitHub App authorization flows are intentionally out of scope for
this provider-only version because they require application registration,
callback or device authorization UX, token exchange, refresh, and shared runtime
support.

## Configuration Examples

### GitHub.com

```json
{
  "service_providers": {
    "github": {
      "default": {
        "base_url": "https://api.github.com",
        "hostname": "github.com",
        "auth_type": "user_token"
      }
    }
  }
}
```

Users then configure their personal GitHub token in **Settings > Provider
Tokens**.

### GitHub Enterprise Server

```json
{
  "service_providers": {
    "github": {
      "enterprise": {
        "base_url": "https://github.company.com/api/v3",
        "hostname": "github.company.com",
        "auth_type": "user_token"
      }
    }
  }
}
```

## Provided Skills

| Skill | Description | Key Operations |
| --- | --- | --- |
| `github` | Authenticated GitHub CLI compatibility layer | `gh pr`, `gh issue`, `gh run`, `gh api`, `gh repo`, `gh search` |

## Safety Notes

Mutating GitHub operations such as creating PRs, comments, reviews, issues,
workflow dispatches, releases, or repository changes must only be run after the
user has clearly asked for that operation and any required AtlasClaw workflow
confirmation has happened.
