---
name: "github-repo"
description: "List recent accessible GitHub repositories for the current user's personal token."
category: "provider:github"
provider_type: "github"
instance_required: "true"

triggers:
  - github repository
  - github repo
  - list repos
  - accessible repositories

use_when:
  - User needs to choose a GitHub repository before inspecting PR checks or workflow runs
  - User wants to see recent repositories accessible with their own GitHub token

avoid_when:
  - User already selected a repository and wants PR or workflow details
  - User wants to write to a GitHub repository

tool_list_repos_name: "github_list_repos"
tool_list_repos_description: "List recent repositories accessible to the current user's GitHub token."
tool_list_repos_entrypoint: "scripts/handler.py:handler"
tool_list_repos_groups:
  - github
  - repo
tool_list_repos_capability_class: "provider:github"
tool_list_repos_priority: 90
tool_list_repos_result_mode: "tool_only_ok"
---

# github-repo

List recent repositories accessible with the authenticated user's GitHub token.
