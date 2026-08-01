"""Resolve adapter authentication into request-scoped SmartCMP contracts."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from typing import Any, Literal, cast
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

from smartcmp_provider.auth.login import login_with_password, resolve_auth_url
from smartcmp_provider.auth.models import (
    ResolvedSmartCmpRequest,
    SmartCmpAuthenticationContext,
    SmartCmpAuthType,
    SmartCmpCredential,
)
from smartcmp_provider.context import ExecutionContext, Principal
from smartcmp_provider.errors import (
    SmartCmpAuthenticationError,
    SmartCmpValidationError,
)
from smartcmp_provider.instance import SmartCmpInstance, TlsSettings
from smartcmp_provider.transport.settings import coerce_timeout_seconds

_API_PATH = "/platform-api"
_DEFAULT_TIMEOUT_SECONDS = 60.0


def normalize_base_url(url: str) -> str:
    """Normalize a SmartCMP endpoint to the existing ``/platform-api`` base.

    Args:
        url: Configured host or URL selected by the owning adapter.

    Returns:
        Absolute URL without query or fragment and with one platform API suffix.

    Raises:
        SmartCmpValidationError: If no usable host is present.
    """

    value = str(url or "").strip()
    if not value:
        raise SmartCmpValidationError("SmartCMP base_url is required.")
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    parsed = urlparse(value)
    if not parsed.netloc:
        raise SmartCmpValidationError("SmartCMP base_url must include a host.")
    path = parsed.path.rstrip("/")
    if not path.endswith(_API_PATH):
        path = f"{path}{_API_PATH}"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def resolve_provided_request(
    *,
    instance_name: str,
    base_url: str,
    subject: str,
    auth_type: SmartCmpAuthType,
    credential_value: str,
    actor_type: Literal["user", "robot"] = "user",
    client_id: str | None = None,
    trace_id: str | None = None,
    auth_url: str | None = None,
    timeout_seconds: float | int | str = _DEFAULT_TIMEOUT_SECONDS,
    tls_verify: bool = False,
    deadline: datetime | None = None,
    idempotency_key: str | None = None,
) -> ResolvedSmartCmpRequest:
    """Resolve an adapter-provided credential without entrypoint-specific state.

    Args:
        instance_name: Adapter-selected SmartCMP instance identifier.
        base_url: SmartCMP endpoint selected by the owning adapter.
        subject: Stable request principal identifier.
        auth_type: SmartCMP credential semantics.
        credential_value: Request-scoped credential supplied by the adapter.
        actor_type: Interactive user or service robot.
        client_id: Optional adapter client or robot profile identifier.
        trace_id: Optional request correlation identifier.
        auth_url: Optional SmartCMP authentication endpoint.
        timeout_seconds: Request timeout accepted by SmartCMP transport.
        tls_verify: Whether the SmartCMP HTTP client verifies TLS certificates.
        deadline: Optional absolute operation deadline.
        idempotency_key: Optional mutation identity.

    Returns:
        Immutable execution context and Provider-resolved API credential.

    Raises:
        SmartCmpAuthenticationError: If the supplied credential is empty.
        SmartCmpValidationError: If instance or endpoint settings are invalid.
    """

    selected_name = str(instance_name or "").strip()
    if not selected_name:
        raise SmartCmpValidationError("SmartCMP instance name is required.")
    authentication = SmartCmpAuthenticationContext.provided(
        subject=str(subject or "").strip(),
        actor_type=actor_type,
        auth_type=auth_type,
        credential_value=str(credential_value or "").strip(),
        client_id=str(client_id or "").strip() or None,
    )
    return resolve_integration_request(
        instance=SmartCmpInstance(
            name=selected_name,
            base_url=base_url,
            auth_url=str(auth_url or "").strip() or None,
            timeout_seconds=coerce_timeout_seconds(timeout_seconds),
            tls=TlsSettings(verify=tls_verify),
        ),
        authentication=authentication,
        trace_id=str(trace_id or uuid4().hex),
        deadline=deadline,
        idempotency_key=idempotency_key,
    )


def resolve_atlasclaw_instance_request(
    *,
    instance_name: str,
    instance_config: Mapping[str, object],
    request_session_token: str = "",
    runtime_cookie: str = "",
    runtime_sso_token: str = "",
    request_session_only: bool = False,
    subject: str = "atlasclaw-user",
    actor_type: Literal["user", "robot"] = "user",
    client_id: str | None = None,
    trace_id: str | None = None,
) -> ResolvedSmartCmpRequest:
    """Resolve AtlasClaw page/chat credentials without duplicating auth policy.

    The AtlasClaw adapter owns selection of the current instance and extraction
    of its request cookies. SmartCMP Provider owns URL, auth-mode, password-login,
    credential-kind, and header semantics.

    Args:
        instance_name: AtlasClaw-selected Provider instance name.
        instance_config: Selected SmartCMP Provider instance mapping.
        request_session_token: Current request user's CloudChef session token.
        runtime_cookie: Runtime-resolved cookie credential for the instance.
        runtime_sso_token: Runtime-resolved SSO credential for the instance.
        request_session_only: Reject configured credentials when a page-bound
            operation requires the current signed-in user.
        subject: Request-scoped AtlasClaw principal identifier.
        actor_type: AtlasClaw caller kind. Webhook robot profiles must pass
            ``robot`` so audit context is not represented as an interactive user.
        client_id: Optional webhook robot profile or other AtlasClaw client ID.
        trace_id: Optional request correlation identifier.

    Returns:
        A request-scoped Provider execution and authentication binding.

    Raises:
        SmartCmpAuthenticationError: If no permitted credential is available.
        SmartCmpValidationError: If instance URL or timeout is invalid.
    """

    config = dict(instance_config)
    selected_name = str(instance_name or "").strip()
    if not selected_name:
        raise SmartCmpValidationError(
            "Selected SmartCMP Provider instance is unavailable."
        )
    base_url = normalize_base_url(config.get("base_url"))
    timeout = coerce_timeout_seconds(
        config.get("timeout", _DEFAULT_TIMEOUT_SECONDS)
    )
    request_token = str(request_session_token or "").strip()
    if request_session_only and not request_token:
        raise SmartCmpAuthenticationError(
            "Current SmartCMP user session is unavailable or expired."
        )
    if request_session_only:
        return resolve_provided_request(
            instance_name=selected_name,
            base_url=base_url,
            auth_url=str(config.get("auth_url") or "").strip() or None,
            timeout_seconds=timeout,
            tls_verify=False,
            subject=str(subject or "atlasclaw-user").strip(),
            actor_type=actor_type,
            auth_type="cookie",
            credential_value=request_token,
            client_id=str(client_id or "").strip() or None,
            trace_id=str(trace_id or uuid4().hex),
        )

    configured_auth_type = config.get("auth_type")
    auth_type = _selected_auth_type(configured_auth_type)
    if configured_auth_type not in (None, "", []) and not auth_type:
        raise SmartCmpValidationError(
            f"Unsupported SmartCMP auth_type: {configured_auth_type!r}."
        )
    token = ""
    if auth_type == "provider_token":
        token = str(config.get("provider_token") or "").strip()
    elif auth_type == "user_token":
        token = str(config.get("user_token") or "").strip()
    elif auth_type == "cookie":
        token = (
            request_token
            or runtime_cookie
            or str(config.get("cookie") or "").strip()
        )
    elif auth_type == "credential":
        # Explicit credential mode is a service-credential identity boundary.
        # A browser Cookie must never replace its configured username/password
        # or change the audited SmartCMP principal for this instance.
        token = ""
    else:
        token = (
            request_token
            or runtime_cookie
            or runtime_sso_token
            or str(config.get("provider_token") or "").strip()
            or str(config.get("user_token") or "").strip()
            or str(config.get("cookie") or "").strip()
        )
        if token:
            auth_type = (
                "user_token" if token.startswith("cmp_tk_") else "credential"
            )

    if (
        not token
        and str(config.get("username") or "").strip()
        and str(config.get("password") or "")
    ):
        token = login_with_password(
            resolve_auth_url(
                base_url,
                str(config.get("auth_url") or "").strip(),
            ),
            str(config["username"]).strip(),
            str(config["password"]),
            timeout_seconds=timeout,
            tls_verify=False,
        )
        auth_type = "cookie"

    if not token:
        raise SmartCmpAuthenticationError(
            "Selected SmartCMP Provider authentication is unavailable."
        )
    return resolve_provided_request(
        instance_name=selected_name,
        base_url=base_url,
        auth_url=str(config.get("auth_url") or "").strip() or None,
        timeout_seconds=timeout,
        tls_verify=False,
        subject=str(subject or "atlasclaw-user").strip(),
        actor_type=actor_type,
        auth_type=cast(SmartCmpAuthType, auth_type or "credential"),
        credential_value=token,
        client_id=str(client_id or "").strip() or None,
        trace_id=str(trace_id or uuid4().hex),
    )


def resolve_integration_request(
    *,
    instance: SmartCmpInstance,
    authentication: SmartCmpAuthenticationContext,
    trace_id: str,
    deadline: datetime | None = None,
    idempotency_key: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> ResolvedSmartCmpRequest:
    """Resolve one adapter-neutral authentication context into an API request.

    SmartCMP Provider owns credential lookup and conversion. Protocol adapters
    pass a configured reference or future OAuth context and never construct
    ``SmartCmpCredential`` themselves.

    Args:
        instance: Adapter-selected SmartCMP endpoint and connection settings.
        authentication: Shared principal and credential-source context.
        trace_id: Per-call correlation identifier.
        deadline: Optional absolute operation deadline.
        idempotency_key: Optional caller mutation identity.
        environ: Optional Provider credential source used only by focused tests.

    Returns:
        Immutable execution context and Provider-resolved API credential.

    Raises:
        SmartCmpAuthenticationError: If the referenced credential is absent.
        SmartCmpValidationError: If the configured endpoint is invalid.
    """

    runtime_env = os.environ if environ is None else environ
    if authentication.source == "configured_reference":
        credential_reference = str(
            authentication.credential_reference or ""
        ).strip()
        secret = str(runtime_env.get(credential_reference) or "").strip()
        if not secret:
            raise SmartCmpAuthenticationError(
                "SmartCMP configured credential is not available: "
                f"{credential_reference}",
                trace_id=trace_id,
            )
    else:
        secret = str(authentication.credential_value or "").strip()
        if not secret:
            raise SmartCmpAuthenticationError(
                "SmartCMP authentication context has no credential value.",
                trace_id=trace_id,
            )

    try:
        normalized_base_url = normalize_base_url(instance.base_url)
    except SmartCmpValidationError as error:
        raise SmartCmpValidationError(
            str(error),
            trace_id=trace_id,
        ) from error
    normalized_instance = replace(instance, base_url=normalized_base_url)
    principal = Principal(
        subject=authentication.subject,
        actor_type=authentication.actor_type,
        tenant_id=authentication.tenant_id,
        client_id=authentication.client_id,
        scopes=authentication.scopes,
    )
    context = ExecutionContext(
        principal=principal,
        instance=normalized_instance,
        trace_id=trace_id,
        deadline=deadline,
        idempotency_key=idempotency_key,
    )
    credential = SmartCmpCredential(
        kind=_credential_kind(authentication.auth_type, secret),
        value=secret,
    )
    return ResolvedSmartCmpRequest(context=context, credential=credential)


def _selected_auth_type(value: object) -> str:
    """Return the single auth mode already selected by an owning adapter."""

    if isinstance(value, list):
        return ""
    normalized = str(value or "").strip().lower()
    if normalized in {
        "provider_token",
        "user_token",
        "cookie",
        "credential",
        "oauth_token",
    }:
        return normalized
    return ""


def _credential_kind(
    auth_type: str,
    secret: str,
) -> Literal["bearer", "session", "cookie"]:
    """Map SmartCMP auth semantics to the exact API header contract."""

    if auth_type in {"provider_token", "oauth_token"}:
        return "bearer"
    if auth_type == "cookie":
        return "cookie"
    if auth_type == "user_token":
        return "bearer" if secret.startswith("cmp_tk_") else "session"
    return "session"
