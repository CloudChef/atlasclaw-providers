# Provider Auth Design

**Status (2026-04-05)**

This document is a proposed cross-provider auth design, not a description of
fully implemented behavior in the current AtlasClaw codebase.

Current AtlasClaw behavior:

- authenticates the current user and exposes identity through
  `UserInfo.raw_token` and `SkillDeps.user_token`
- injects `provider_instances`, selected `provider_instance`, and
  `provider_config` into `SkillDeps.extra`
- preserves request cookies in `SkillDeps.cookies`
- forwards request cookies and provider config to script-based providers through
  `ATLASCLAW_COOKIES` and `ATLASCLAW_PROVIDER_CONFIG`

Not yet implemented in core:

- generic `auth_context` and `embedded_provider_auth` request contracts
- shared `ProviderUserAuth`, `ProviderAuthResolver`, and `ProviderAuthCache`
- automatic provider-wrapper injection of `deps.extra["provider_auth"]`

**Context**

AtlasClaw Core already authenticates the current user and exposes request-scoped
identity through `UserInfo.raw_token` and `SkillDeps.user_token`. Provider
instances are also selected and injected into `deps.extra`. What is still
missing is a generic provider auth layer that turns the current AtlasClaw-side
identity into a provider-native user credential that the target system
actually accepts.

This gap is visible in provider integrations that currently depend on static
instance credentials such as shared cookies, usernames, or passwords. That
model does not support strict permission inheritance when AtlasClaw itself is
already running under the current user's SSO identity.

The design in this document defines a generic provider auth model that works
for embedded UI, standalone AtlasClaw deployments, REST/API access, websocket
clients, and webhook-driven skill execution.

**Proposed Decision**

Introduce a generic provider auth layer with the following rules:

- AtlasClaw Core authenticates the current user and passes upstream auth
  context into request-scoped skill dependencies.
- Each provider is responsible for resolving provider-native user auth from
  that upstream auth context.
- Provider auth resolution happens at the provider level, not inside each
  individual skill.
- Provider auth is cached per user and per provider instance.
- Skills consume resolved provider auth, not raw shared instance credentials.
- Embedded pass-through auth is preferred when available. Standalone SSO
  exchange is the fallback when provider-native auth is not already present in
  the current request.

**Goals**

- Preserve strict permission inheritance across provider skill execution.
- Keep AtlasClaw Core thin and provider implementations rich.
- Support both embedded and standalone deployments without changing skill
  semantics.
- Avoid forcing every provider skill to re-implement auth discovery logic.
- Allow script-based providers to migrate gradually without rewriting business
  logic.

**Non-Goals**

- Building a universal token exchange service inside AtlasClaw Core.
- Requiring every provider to use the same credential shape.
- Treating upstream AtlasClaw SSO tokens as automatically valid for all
  provider APIs.
- Reusing shared service-account credentials as the default per-user model.

**Key Terms**

- **Upstream Auth Context**: The current AtlasClaw-side authenticated user
  context, usually derived from OIDC, SSO, API auth, or host application auth.
- **Provider-Native Auth**: The actual user credential accepted by the target
  provider system, such as a bearer token, session cookie, or provider-issued
  token.
- **Embedded Pass-Through**: Provider-native auth is already available in the
  current request because AtlasClaw runs inside or alongside the host system.
- **Standalone Exchange**: Provider-native auth must be derived from upstream
  SSO context by calling a provider-specific login, token exchange, or session
  bootstrap endpoint.
- **Provider Auth Resolver**: Provider-owned logic that decides how to derive
  provider-native auth for the current user.

## Architecture

**Core Responsibilities**

- Authenticate the current user and populate `UserInfo`.
- Preserve upstream auth context in request-scoped dependencies.
- Select the active provider instance.
- Call the provider auth resolver before provider skill execution.
- Provide in-run request-scoped caching hooks.

Core does not implement provider-specific login rules, cookie parsing, token
exchange formats, or provider-specific refresh logic.

**Provider Responsibilities**

- Decide which auth mode is valid for the target system.
- Resolve provider-native auth from upstream auth context or embedded
  pass-through data.
- Cache provider-native auth per user and per provider instance.
- Normalize provider auth into a stable structure consumable by skills.
- Handle refresh, expiry, invalidation, and provider-specific auth failures.

**Skill Responsibilities**

- Use the provider-native auth already resolved by the provider auth layer.
- Avoid performing ad hoc auth discovery.
- Avoid reading shared static credentials when user-scoped auth is available.

## Auth Source Model

Provider auth resolution should follow this precedence order:

1. In-run cache for the current execution
2. Embedded pass-through provider auth already present in the current request
3. Cross-run cache for the current user and provider instance
4. Standalone SSO exchange or provider-side session bootstrap
5. Explicit provider-specific fallback, only if intentionally configured

This means embedded deployments should reuse the host application's current
provider-native session when available. Standalone deployments fall back to
provider-side exchange logic.

## Provider Auth Modes

Provider auth has two independent dimensions:

- **Acquisition path**
  - pass-through
  - exchange/bootstrap
- **Credential shape**
  - bearer token
  - session/cookie

Common modes are:

- `embedded_pass_through`
  The request already carries provider-native auth material. The resolver
  validates and reuses it.
- `direct_bearer`
  The provider accepts the same upstream bearer token without requiring a
  provider-local session.
- `exchange_bearer`
  The provider requires a provider-audience bearer token minted from the
  upstream SSO identity.
- `exchange_session`
  The provider accepts SSO, but creates its own local session and returns a
  session cookie or provider-local token.

Providers may support one or more modes. A provider implementation may expose
instance-level configuration such as:

```json
{
  "service_providers": {
    "example": {
      "prod": {
        "base_url": "https://api.example.com",
        "auth_mode": "auto"
      }
    }
  }
}
```

Suggested meaning:

- `auto`: provider chooses based on request context and provider capabilities
- `embedded`: prefer pass-through and fail if it is unavailable
- `bearer`: require bearer-style provider auth
- `session`: require session bootstrap and cookie/token reuse

The final decision belongs to the provider resolver, not to the individual
skill implementation.

## Request-Scoped Contract

AtlasClaw Core should standardize two request-scoped structures in
`SkillDeps.extra`.

**1. `auth_context`**

Generic upstream user auth context supplied by AtlasClaw Core:

```python
{
    "auth_provider": "oidc",
    "access_token": "...",
    "id_token": "...",
    "subject": "...",
    "email": "...",
    "tenant_id": "...",
    "roles": [...],
}
```

This is the AtlasClaw-side identity context. It is not automatically
provider-native auth.

**2. `embedded_provider_auth`**

Optional host-supplied provider-native auth material already present in the
current request. This structure should be explicit and provider-qualified:

```python
{
    "smartcmp:prod": {
        "auth_type": "cookie",
        "cookie": "...",
        "source": "browser",
    },
    "jira:corp": {
        "auth_type": "bearer",
        "access_token": "...",
        "source": "browser",
    },
}
```

Core should not guess vendor cookie names. Host integrations, reverse proxies,
or embedded adapters should translate incoming request auth into this normalized
structure before skill execution.

## Provider Auth Interfaces

The generic provider auth model should be centered around three types.

```python
@dataclass
class ProviderUserAuth:
    auth_type: str
    principal_id: str
    access_token: str = ""
    refresh_token: str = ""
    cookie: str = ""
    expires_at: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


class ProviderAuthResolver(Protocol):
    async def resolve_user_auth(
        self,
        *,
        provider_type: str,
        instance_name: str,
        instance_config: dict[str, Any],
        user_info: UserInfo,
        deps_extra: dict[str, Any],
    ) -> ProviderUserAuth: ...


class ProviderAuthCache(Protocol):
    def get(self, cache_key: str) -> Optional[ProviderUserAuth]: ...
    def set(self, cache_key: str, auth: ProviderUserAuth) -> None: ...
    def invalidate(self, cache_key: str) -> None: ...
```

`ProviderUserAuth` is the only structure that skills should need. Providers may
store additional provider-specific metadata in `extra`, but the top-level fields
should remain stable across providers.

## Generic Resolution Flow

The resolver algorithm should be:

1. Build a cache key from `tenant_id + user_id + provider_type + instance_name`
2. Check request-scoped in-run cache
3. Check `embedded_provider_auth` for this provider instance
4. If present, validate it and return provider-native auth
5. Check optional cross-run cache
6. Otherwise derive provider-native auth from `auth_context`
7. Cache the result
8. Inject the resolved `ProviderUserAuth` back into `deps.extra`

Reference pseudocode:

```python
async def resolve_user_auth(...):
    cache_key = f"{tenant_id}:{user_id}:{provider_type}:{instance_name}"
    run_cache = deps_extra.setdefault("_provider_auth_cache", {})

    auth = run_cache.get(cache_key) or provider_cache.get(cache_key)
    if auth and not expired(auth):
        return auth

    embedded = deps_extra.get("embedded_provider_auth", {}).get(
        f"{provider_type}:{instance_name}"
    )
    if embedded:
        auth = validate_embedded_auth(embedded, instance_config)
        run_cache[cache_key] = auth
        provider_cache.set(cache_key, auth)
        return auth

    auth = provider_cache.get(cache_key)
    if auth and not expired(auth):
        run_cache[cache_key] = auth
        return auth

    upstream = deps_extra.get("auth_context", {})
    auth = await exchange_or_bootstrap_from_upstream(upstream, instance_config)
    run_cache[cache_key] = auth
    provider_cache.set(cache_key, auth)
    return auth
```

## Integration Points

**Provider Wrapper**

Provider auth resolution should happen in the provider wrapper after provider
instance selection and before the actual skill handler is invoked.

This is the correct hook because:

- provider instance identity is already known
- the resolver runs once per provider invocation instead of once per script
- all provider skills can share the same auth decision

The wrapper should inject:

- `deps.extra["provider_auth"]`
- `deps.extra["provider_auth_source"]`
- `deps.extra["provider_auth_cache_key"]`

**Script Compatibility Layer**

Script-based providers should remain compatible by mapping `ProviderUserAuth`
into environment variables before script execution. Example mappings:

- `provider_auth.cookie -> CMP_COOKIE`
- `provider_auth.access_token -> CMP_ACCESS_TOKEN`
- `provider_auth.auth_type -> PROVIDER_AUTH_TYPE`
- `provider_auth.principal_id -> PROVIDER_PRINCIPAL_ID`

This layer should adapt the resolved auth to existing script contracts without
forcing an immediate rewrite of all provider business logic.

## Caching Model

Provider auth must never be cached globally per provider instance. It must be
scoped to the current user and provider instance.

Recommended cache key:

```text
{tenant_id}:{user_id}:{provider_type}:{instance_name}
```

Recommended cache layers:

- **Run cache**
  Stored in `deps.extra`, valid only for the current run
- **Cross-run cache**
  Optional reusable cache for refreshable sessions or short-lived provider
  tokens

Suggested storage rule:

- default to filesystem-backed cache under the current user's workspace scope
- redact values from logs and debugging output
- support invalidation on 401, logout, or provider-specific expiry signals

If reusable secrets are stored at rest, the implementation should support
platform-appropriate encryption or secure storage policy.

## Security Rules

- Never write resolved provider-native user auth back into
  `service_providers`.
- Never share provider-native auth across users.
- Never log raw provider cookies or tokens.
- Never let individual skills silently downgrade to shared instance credentials
  when user-scoped auth is expected.
- Treat upstream `auth_context` and provider-native auth as separate things.
- Invalidate cached provider auth when the provider returns auth failure or the
  current AtlasClaw user changes.

## Deployment Semantics

**Embedded Mode**

In embedded mode, AtlasClaw should prefer host-provided provider-native auth.
If the host request already carries the target system's cookie or token, the
provider should reuse it directly instead of performing a second SSO exchange.

This avoids duplicate login hops and keeps provider skill execution aligned
with the user's current browser session.

**Standalone Mode**

In standalone mode, AtlasClaw usually has only upstream SSO identity. Provider
auth must be derived by calling the provider's own token exchange, login, or
session bootstrap endpoint.

This is still user-scoped auth. It is not a return to shared service accounts.

## Error Handling

Provider auth resolution should fail with explicit, typed errors:

- missing upstream auth context
- embedded auth present but invalid for the chosen provider instance
- exchange/bootstrap rejected by provider
- provider auth expired and refresh failed
- provider auth mode unsupported for the active instance

Auth failures should invalidate the relevant cache entry and return a
user-visible error that identifies the provider and auth phase that failed.

## Testing Requirements

Provider auth should be covered by tests for:

- embedded pass-through success
- standalone exchange success
- per-user cache isolation
- per-instance cache isolation
- cache invalidation on provider auth failure
- provider selection plus auth resolution ordering
- script wrapper environment mapping
- websocket, API, and channel entry paths preserving auth context

## Migration Guidance

Existing providers can migrate incrementally:

1. Add a provider auth resolver
2. Normalize resolved auth into `ProviderUserAuth`
3. Update the provider wrapper to inject `provider_auth`
4. Keep legacy scripts working via environment variable mapping
5. Remove shared static auth from the normal user path

Providers that currently rely on shared cookies, usernames, or passwords may
keep those as explicit non-default fallbacks, but they should no longer be the
primary auth model for user-scoped provider skills when SSO context is
available.

## Example: SmartCMP as a Concrete Provider

SmartCMP illustrates why this design is needed:

- current scripts are session/cookie-oriented
- embedded deployments may already have a SmartCMP session in the browser
- standalone deployments may need to bootstrap a SmartCMP session from upstream
  SSO context

Under this design, SmartCMP would implement provider auth once, then expose the
resolved session cookie or token to all SmartCMP skills through the same
provider-native auth contract.

**Outcome**

This design keeps AtlasClaw Core responsible for user identity, keeps provider
auth logic inside providers, preserves permission inheritance, and gives both
script-based and code-based providers a consistent migration path to user-scoped
SSO-aware execution.
