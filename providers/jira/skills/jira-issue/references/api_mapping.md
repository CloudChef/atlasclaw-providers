# Jira REST API Mapping for jira-issue skill

Used endpoints:

- Connectivity check: `GET /rest/api/{api_version}/serverInfo`
- Project discovery: `GET /rest/api/{api_version}/project`
- Create issue: `POST /rest/api/{api_version}/issue`
- Get issue: `GET /rest/api/{api_version}/issue/{issue_key}`
- Update issue: `PUT /rest/api/{api_version}/issue/{issue_key}`
- Delete issue: `DELETE /rest/api/{api_version}/issue/{issue_key}`

Auth:

- Basic auth with `username` + `password` from AtlasClaw provider
  configuration. For Atlassian Cloud, store the API token in `password`.
