---
name: "github-pr-checks"
description: "Inspect CI and check status for a GitHub pull request."
category: "provider:github"
provider_type: "github"
instance_required: "true"

triggers:
  - github pr checks
  - pull request checks
  - ci status
  - pr status

use_when:
  - User wants CI or check status for a pull request in a selected repository

avoid_when:
  - User has not selected or provided a repository
  - User wants to rerun workflows or write to GitHub

tool_pr_checks_name: "github_pr_checks"
tool_pr_checks_description: "Inspect CI checks for a GitHub pull request."
tool_pr_checks_entrypoint: "scripts/handler.py:handler"
tool_pr_checks_groups:
  - github
  - checks
tool_pr_checks_capability_class: "provider:github"
tool_pr_checks_priority: 100
tool_pr_checks_result_mode: "tool_only_ok"
---

# github-pr-checks

Inspect pull request checks and combined status for an explicitly selected repository.
