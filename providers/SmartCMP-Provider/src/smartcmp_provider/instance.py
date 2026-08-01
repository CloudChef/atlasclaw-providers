"""SmartCMP instance connection contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse, urlunparse


_API_PATH = "/platform-api"


def smartcmp_ui_base_url(api_base_url: str) -> str:
    """Return the SmartCMP browser base URL for a normalized API base URL.

    Args:
        api_base_url: Selected SmartCMP instance URL, normally ending in
            ``/platform-api`` after authentication resolution.

    Returns:
        The same instance origin and optional tenant path without the API suffix,
        query, or fragment. Invalid or empty values return an empty string so an
        AtlasClaw Adapter can omit its optional navigation action.
    """

    parsed = urlparse(str(api_base_url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path = parsed.path.rstrip("/")
    if path.endswith(_API_PATH):
        path = path[: -len(_API_PATH)].rstrip("/")
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


@dataclass(frozen=True, slots=True)
class TlsSettings:
    """Describe TLS verification inputs for one SmartCMP instance.

    Attributes:
        verify: Whether the transport verifies the upstream certificate.
        ca_bundle: Optional path to a trusted CA bundle for private deployments.
    """

    verify: bool = True
    ca_bundle: str | None = None


@dataclass(frozen=True, slots=True)
class SmartCmpInstance:
    """Describe one explicitly selected SmartCMP endpoint.

    This immutable value contains connection properties only. Credentials and
    request-specific caller state are intentionally stored in separate contracts.

    Attributes:
        name: Stable configured instance name.
        base_url: SmartCMP API base URL selected by the adapter.
        auth_url: Optional authentication endpoint override.
        timeout_seconds: Per-request upstream timeout in seconds.
        tls: TLS verification settings for this instance.
    """

    name: str
    base_url: str
    auth_url: str | None = None
    timeout_seconds: float = 60.0
    tls: TlsSettings = field(default_factory=TlsSettings)

    @property
    def ui_base_url(self) -> str:
        """Return the browser base URL associated with this resolved instance."""

        return smartcmp_ui_base_url(self.base_url)
