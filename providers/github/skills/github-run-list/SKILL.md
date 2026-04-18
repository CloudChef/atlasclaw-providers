---
name: "github-run-list"
description: "List recent GitHub Actions workflow runs for an explicit repository."
category: "provider:github"
provider_type: "github"
instance_required: "true"

triggers:
  - workflow runs
  - github run list
  - actions runs
  - recent workflow runs

use_when:
  - User wants recent GitHub Actions workflow runs for a selected repository

avoid_when:
  - User has not selected or provided a repository
  - User wants to rerun or cancel workflows

tool_run_list_name: "github_run_list"
tool_run_list_description: "List recent GitHub Actions workflow runs for a repository."
tool_run_list_entrypoint: "scripts/handler.py:handler"
tool_run_list_groups:
  - github
  - runs
tool_run_list_capability_class: "provider:github"
tool_run_list_priority: 105
tool_run_list_result_mode: "tool_only_ok"
---

# github-run-list

List recent workflow runs for an explicitly selected repository.
