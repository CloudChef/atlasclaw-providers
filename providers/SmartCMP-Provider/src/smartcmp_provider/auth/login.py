"""Provider-owned username/password login for SmartCMP credentials."""

from __future__ import annotations

import hashlib
from urllib.parse import urlparse

import httpx

from smartcmp_provider.errors import (
    SmartCmpAuthenticationError,
    SmartCmpTimeoutError,
    SmartCmpUpstreamError,
    SmartCmpValidationError,
)
from smartcmp_provider.transport.settings import (
    DEFAULT_TIMEOUT_SECONDS,
    coerce_timeout_seconds,
)

SAAS_AUTH_URL = "https://account.smartcmp.cloud/bss-api/api/authentication"
SAAS_HOSTS = frozenset(
    {
        "console.smartcmp.cloud",
        "account.smartcmp.cloud",
        "console.cloudchef.io",
    }
)


def infer_auth_url(cmp_url: str) -> str:
    """Infer the SmartCMP authentication endpoint for one configured base URL.

    Args:
        cmp_url: SmartCMP host or absolute URL selected by the adapter.

    Returns:
        The canonical SaaS authentication endpoint for known SaaS hosts, or the
        private-deployment ``/platform-api/login`` endpoint.

    Raises:
        SmartCmpValidationError: If the value has no usable host.
    """

    value = str(cmp_url or "").strip()
    if not value:
        raise SmartCmpValidationError("SmartCMP base_url is required for login.")
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    parsed = urlparse(value)
    if not parsed.netloc:
        raise SmartCmpValidationError(
            "SmartCMP base_url must include a host for login."
        )
    hostname = (parsed.hostname or "").lower()
    if hostname in SAAS_HOSTS and parsed.port in (None, 443):
        return SAAS_AUTH_URL
    return f"{parsed.scheme}://{parsed.netloc}/platform-api/login"


def resolve_auth_url(cmp_url: str, explicit_auth_url: str = "") -> str:
    """Resolve an explicit login endpoint before applying Provider inference.

    Args:
        cmp_url: SmartCMP instance base URL used for endpoint inference.
        explicit_auth_url: Optional deployment-specific authentication URL.

    Returns:
        An absolute authentication endpoint.
    """

    explicit = str(explicit_auth_url or "").strip()
    if explicit:
        return (
            explicit
            if explicit.startswith(("http://", "https://"))
            else f"https://{explicit}"
        )
    return infer_auth_url(cmp_url)


def login_with_password(
    auth_url: str,
    username: str,
    password: str,
    *,
    timeout_seconds: object = DEFAULT_TIMEOUT_SECONDS,
    tls_verify: bool | str = False,
    transport: httpx.BaseTransport | None = None,
) -> str:
    """Exchange SmartCMP credentials for a request-scoped session credential.

    SmartCMP's established login contract accepts an MD5 password digest and
    can return credentials as response cookies, JSON tokens, or both. This
    function performs one login attempt and never caches the result.

    Args:
        auth_url: Absolute Provider-selected authentication endpoint.
        username: SmartCMP login identifier.
        password: Plain password or an existing 32-character MD5 digest.
        timeout_seconds: Positive upstream timeout.
        tls_verify: TLS verification flag or CA bundle accepted by HTTPX.
        transport: Optional synchronous HTTPX transport for focused tests.

    Returns:
        Semicolon-separated SmartCMP session values suitable for compatibility
        adapters.

    Raises:
        SmartCmpValidationError: If required login input is missing.
        SmartCmpAuthenticationError: If SmartCMP rejects the credentials or
            returns no usable credential.
        SmartCmpTimeoutError: If the login call exceeds its timeout.
        SmartCmpUpstreamError: If the authentication service cannot be reached.
    """

    endpoint = str(auth_url or "").strip()
    login_id = str(username or "").strip()
    secret = str(password or "")
    if not endpoint or not login_id or not secret:
        raise SmartCmpValidationError(
            "SmartCMP auth_url, username, and password are required for login."
        )
    if not (
        len(secret) == 32
        and all(character in "0123456789abcdefABCDEF" for character in secret)
    ):
        secret = hashlib.md5(secret.encode()).hexdigest()

    timeout = coerce_timeout_seconds(timeout_seconds)
    try:
        with httpx.Client(
            verify=tls_verify,
            follow_redirects=False,
            timeout=timeout,
            transport=transport,
        ) as client:
            response = client.post(
                endpoint,
                data={"username": login_id, "password": secret},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except httpx.TimeoutException as exc:
        raise SmartCmpTimeoutError("SmartCMP login request timed out.") from exc
    except httpx.RequestError as exc:
        raise SmartCmpUpstreamError(
            f"SmartCMP login request failed: {exc}"
        ) from exc

    if response.status_code != 200:
        raise SmartCmpAuthenticationError(
            f"SmartCMP login failed: HTTP {response.status_code}"
        )

    credentials = dict(response.cookies)
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        token = str(payload.get("token") or "").strip()
        refresh_token = str(payload.get("refreshToken") or "").strip()
        if token:
            credentials["CloudChef-Authenticate"] = token
        if refresh_token:
            credentials["CloudChef-Authenticate-Refresh"] = refresh_token
    if not credentials:
        raise SmartCmpAuthenticationError(
            "SmartCMP login response contains no cookies or tokens."
        )
    return "; ".join(f"{key}={value}" for key, value in credentials.items())
