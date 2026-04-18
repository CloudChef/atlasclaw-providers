---
name: "github-run-failed-logs"
description: "Return failed GitHub Actions log excerpts for an explicit repository run."
category: "provider:github"
provider_type: "github"
instance_required: "true"

triggers:
  - failed logs
  - workflow failed logs
  - run log failed
  - github log failed

use_when:
  - User wants failed-step log excerpts for a selected workflow run and repository

avoid_when:
  - User has not selected or provided a repository
  - User wants full raw logs for every successful step

tool_run_failed_logs_name: "github_run_failed_logs"
tool_run_failed_logs_description: "Return failed GitHub Actions log excerpts for a workflow run."
tool_run_failed_logs_entrypoint: "scripts/handler.py:handler"
tool_run_failed_logs_groups:
  - github
  - runs
tool_run_failed_logs_capability_class: "provider:github"
tool_run_failed_logs_priority: 115
tool_run_failed_logs_result_mode: "tool_only_ok"
---

# github-run-failed-logs

Return failed-step log excerpts for an explicitly selected repository run.
