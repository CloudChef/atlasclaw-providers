# Weaver Ecology Provider

Provider package scaffold for Weaver Ecology OA workflow integration.

## What It Provides

- Provider identity: `weaver_ecology`
- Auth model: `sso`
- Runtime scope: current-user Weaver workflow operations
- Catalog metadata and configuration schema through `provider.schema.json`

The provider is intended for Weaver Ecology workflow APIs such as listing todos,
creating workflow requests, and approving or rejecting requests. Workflow API
tools should run with a Weaver-native user token resolved from the current
AtlasClaw user context.

## Configuration

Direct access-token mode:

```json
{
  "service_providers": {
    "weaver_ecology": {
      "default": {
        "base_url": "https://ecology.company.com",
        "auth_type": "sso",
        "sso_token_mode": "access_token",
        "user_id_claim": "weaver_userid"
      }
    }
  }
}
```

Authorization-code exchange mode:

```json
{
  "service_providers": {
    "weaver_ecology": {
      "default": {
        "base_url": "https://ecology.company.com",
        "auth_type": "sso",
        "sso_token_mode": "authorization_code",
        "oauth_app_key": "${WEAVER_OAUTH_APP_KEY}",
        "oauth_app_secret": "${WEAVER_OAUTH_APP_SECRET}",
        "user_id_claim": "weaver_userid"
      }
    }
  }
}
```

## Files

- `PROVIDER.md`: LLM-facing provider contract and routing context
- `provider.schema.json`: machine-readable runtime/API/UI manifest
- `assets/icon.svg`: catalog icon

## Notes

Keep Weaver-specific workflow fields, endpoint details, and authentication
behavior in this provider package. AtlasClaw core should only depend on the
generic provider manifest contract.
