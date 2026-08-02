"""Unified SmartCMP authentication contexts and Provider-owned resolvers."""

from smartcmp_provider.auth.models import (
    ResolvedSmartCmpRequest,
    SmartCmpAuthenticationContext,
    SmartCmpCredential,
)
from smartcmp_provider.auth.login import (
    infer_auth_url,
    login_with_password,
    resolve_auth_url,
)
from smartcmp_provider.auth.resolver import (
    normalize_base_url,
    resolve_integration_request,
    resolve_provided_request,
)

__all__ = [
    "ResolvedSmartCmpRequest",
    "SmartCmpAuthenticationContext",
    "SmartCmpCredential",
    "infer_auth_url",
    "login_with_password",
    "normalize_base_url",
    "resolve_auth_url",
    "resolve_integration_request",
    "resolve_provided_request",
]
