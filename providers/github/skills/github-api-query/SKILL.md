---
name: "github-api-query"
description: "Query approved read-only repository-scoped GitHub REST API paths."
category: "provider:github"
provider_type: "github"
instance_required: "true"

triggers:
  - github api
  - github rest
  - repo api query
  - advanced github query

use_when:
  - User wants a read-only GitHub REST query not covered by the specialized skills

avoid_when:
  - User has not selected or provided a repository
  - User wants write operations or non-repository endpoints

tool_api_query_name: "github_api_query"
tool_api_query_description: "Query approved read-only repository-scoped GitHub REST API paths."
tool_api_query_entrypoint: "scripts/handler.py:handler"
tool_api_query_groups:
  - github
  - api
tool_api_query_capability_class: "provider:github"
tool_api_query_priority: 120
tool_api_query_result_mode: "tool_only_ok"
---

# github-api-query

Query repository-relative read-only GitHub REST API paths.
