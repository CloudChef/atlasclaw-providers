"""Public SmartCMP Provider contracts shared by protocol adapters.

AtlasClaw Skills and SmartCMP MCP depend on this package for authentication,
typed domain operations, and API transport. Neither adapter should reimplement
SmartCMP endpoint or credential behavior outside this boundary.
"""

from smartcmp_provider.capabilities import CapabilitySpec
from smartcmp_provider.auth.models import (
    ResolvedSmartCmpRequest,
    SmartCmpAuthenticationContext,
    SmartCmpCredential,
)
from smartcmp_provider.auth.resolver import (
    normalize_base_url,
    resolve_integration_request,
    resolve_provided_request,
)
from smartcmp_provider.context import ExecutionContext, Principal
from smartcmp_provider.errors import (
    SmartCmpAuthenticationError,
    SmartCmpConflictError,
    SmartCmpError,
    SmartCmpNotFoundError,
    SmartCmpPermissionError,
    SmartCmpRateLimitError,
    SmartCmpTargetResolutionError,
    SmartCmpTimeoutError,
    SmartCmpUnknownOutcomeError,
    SmartCmpUpstreamError,
    SmartCmpValidationError,
)
from smartcmp_provider.instance import SmartCmpInstance, TlsSettings
from smartcmp_provider.transport.client import SmartCmpClient

__all__ = [
    "CapabilitySpec",
    "ExecutionContext",
    "Principal",
    "ResolvedSmartCmpRequest",
    "SmartCmpClient",
    "SmartCmpAuthenticationContext",
    "SmartCmpCredential",
    "SmartCmpAuthenticationError",
    "SmartCmpConflictError",
    "SmartCmpError",
    "SmartCmpInstance",
    "SmartCmpNotFoundError",
    "SmartCmpPermissionError",
    "SmartCmpRateLimitError",
    "SmartCmpTargetResolutionError",
    "SmartCmpTimeoutError",
    "SmartCmpUnknownOutcomeError",
    "SmartCmpUpstreamError",
    "SmartCmpValidationError",
    "TlsSettings",
    "normalize_base_url",
    "resolve_integration_request",
    "resolve_provided_request",
]

__version__ = "1.0.0"
