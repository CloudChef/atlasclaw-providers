---
provider_type: weaver_ecology
display_name: Weaver Ecology
version: "1.0.0"

keywords:
  - weaver
  - ecology
  - e-cology
  - workflow
  - OA
  - 泛微
  - 流程
  - 待办
  - 审批

capabilities:
  - List the current user's Weaver Ecology OA workflow todos
  - Create Weaver workflow requests as the current user
  - Submit, approve, and reject Weaver workflow requests using provider-native user identity

use_when:
  - User asks to view Weaver or Ecology workflow todos
  - User asks to create or submit an OA workflow request
  - User asks to approve or reject a Weaver workflow request

avoid_when:
  - User wants cloud resource fulfillment or CMP workflow operations
  - User wants generic issue tracking outside Weaver Ecology workflows
---

# Weaver Ecology Provider

Weaver Ecology provider integration for OA workflow operations. The provider is
designed to run workflow API calls as the current AtlasClaw user after resolving
a Weaver-native user token and user identifier.

## Authentication Model

This provider uses AtlasClaw `sso` authentication. AtlasClaw supplies the
current user's provider SSO token at runtime; the provider either uses that
token directly as a Weaver access token or exchanges an authorization code for a
Weaver access token.

The provider instance must set `auth_type` to `sso`.

## Connection Parameters

| Parameter | Required | Description |
| --- | --- | --- |
| `base_url` | Yes | Weaver Ecology base URL, for example `https://ecology.company.com`. |
| `auth_type` | Yes | Must be `sso`. |
| `sso_token_mode` | No | `access_token` to use the runtime SSO token directly, or `authorization_code` to exchange it. Defaults to `access_token`. |
| `user_id_claim` | No | Claim name used to read the Weaver user id from the current user identity. |
| `user_id_map` | No | Optional mapping from AtlasClaw user id to Weaver user id. |
| `oauth_app_key` | Conditional | Weaver OAuth app key when `sso_token_mode` is `authorization_code`. |
| `oauth_app_secret` | Conditional | Weaver OAuth app secret when `sso_token_mode` is `authorization_code`. |
| `token_endpoint` | No | OAuth token endpoint path. Defaults to Weaver's open API token endpoint. |
| `timeout_seconds` | No | HTTP timeout in seconds. |

## Runtime Boundary

`provider.schema.json` is the machine-readable source for catalog metadata,
configuration fields, auth modes, defaults, aliases, and redaction. This file is
only the LLM-facing provider contract and routing context.
