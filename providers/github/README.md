# GitHub Provider

Provider package for running authenticated GitHub CLI operations from
AtlasClaw.

## What It Provides

- Provider identity: `github`
- Auth model: `user_token`
- Runtime tool: `github_cli`
- Supported targets: GitHub.com and GitHub Enterprise Server

The provider is intentionally a thin compatibility layer around the official
`gh` CLI so existing GitHub workflows continue to work while AtlasClaw supplies
the current user's token through the provider runtime.

## Configuration

GitHub.com:

```json
{
  "service_providers": {
    "github": {
      "github": {
        "base_url": "https://api.github.com",
        "hostname": "github.com",
        "auth_type": "user_token"
      }
    }
  }
}
```

GitHub Enterprise Server:

```json
{
  "service_providers": {
    "github": {
      "github_enterprise": {
        "base_url": "https://github.company.com/api/v3",
        "hostname": "github.company.com",
        "auth_type": "user_token"
      }
    }
  }
}
```

Each AtlasClaw user stores their own GitHub personal access token in Provider
Tokens. The token's GitHub-side repository and organization permissions control
what the provider can do.

## What `user_token` Means

AtlasClaw `user_token` maps to the GitHub token string owned by the current
user. In GitHub this is normally one of:

- Fine-grained personal access token: recommended. Create it in GitHub personal
  settings, choose the target repositories, and grant only the permissions the
  workflow needs.
- Personal access token (classic): compatible with `gh`, but broader. Use it
  only when fine-grained tokens are not suitable for the target GitHub
  deployment or workflow.

Paste the token value into AtlasClaw **Settings > Provider Tokens** for the
GitHub provider instance. AtlasClaw stores it as `user_token`; the provider
then passes it to `gh` as `GH_TOKEN` for GitHub.com, or `GH_ENTERPRISE_TOKEN`
with `GH_HOST` for GitHub Enterprise Server.

Do not use a GitHub password, AtlasClaw login token, or the local credentials
created by `gh auth login` as `user_token`.

## Skill

The `github` skill exposes one executable tool:

```text
github_cli(args, repo=None, timeout_seconds=None)
```

Examples:

```json
{"args": ["pr", "checks", "55"], "repo": "owner/repo"}
{"args": ["run", "list", "--limit", "10"], "repo": "owner/repo"}
{"args": ["api", "repos/owner/repo/pulls/55", "--jq", ".title"]}
```

The wrapper sets `GH_PROMPT_DISABLED=1` and uses a temporary `GH_CONFIG_DIR` so
commands do not prompt for login or reuse machine-level `gh` credentials.

## Token Guidance

Prefer fine-grained personal access tokens. Grant only the repositories and
permissions required for the intended workflows, such as Pull requests, Issues,
Actions, Contents, or Metadata. Classic PATs can also work, but they are broader
and should be avoided when fine-grained tokens are available.

For organizations with SAML SSO enforcement, the token may need GitHub-side SSO
authorization before private organization resources are accessible.
