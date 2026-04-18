---
name: "github-run-view"
description: "View GitHub Actions workflow run details and failed steps for an explicit repository."
category: "provider:github"
provider_type: "github"
instance_required: "true"

triggers:
  - github run view
  - workflow run detail
  - run detail
  - failed workflow steps

use_when:
  - User wants details for a specific GitHub Actions workflow run in a selected repository

avoid_when:
  - User has not selected or provided a repository
  - User wants to rerun or cancel workflows

tool_run_view_name: "github_run_view"
tool_run_view_description: "View workflow run details and failed steps for a repository."
tool_run_view_entrypoint: "scripts/handler.py:handler"
tool_run_view_groups:
  - github
  - runs
tool_run_view_capability_class: "provider:github"
tool_run_view_priority: 110
tool_run_view_result_mode: "tool_only_ok"
---

# github-run-view

View workflow run details for an explicitly selected repository.
