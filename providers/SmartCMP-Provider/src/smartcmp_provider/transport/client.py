"""Request-scoped asynchronous HTTP client for SmartCMP operations."""

from __future__ import annotations

import json
import re
from datetime import datetime
from types import TracebackType
from typing import Any

import httpx

from smartcmp_provider.auth.models import ResolvedSmartCmpRequest
from smartcmp_provider.errors import (
    SmartCmpAuthenticationError,
    SmartCmpConflictError,
    SmartCmpNotFoundError,
    SmartCmpPermissionError,
    SmartCmpRateLimitError,
    SmartCmpTimeoutError,
    SmartCmpUpstreamError,
    SmartCmpValidationError,
)


_SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(?P<key>password|passwd|credentialPassword|token|authorization|"
    r"cookie|clientSecret|secret)\s*(?P<separator>[:=])\s*"
    r"(?P<value>\"[^\"]*\"|'[^']*'|[^,}\]\r\n]*)"
)
_SENSITIVE_KEY_FRAGMENTS = (
    "authorization",
    "clientsecret",
    "cookie",
    "credentialpassword",
    "password",
    "passwd",
    "secret",
    "token",
)


class SmartCmpClient:
    """Execute SmartCMP HTTP calls for one resolved request scope.

    A client instance owns exactly one immutable Principal/Instance/Credential
    binding. It does not read environment variables or module globals, so
    concurrent users and instances cannot overwrite each other's headers or URLs.
    """

    def __init__(
        self,
        request: ResolvedSmartCmpRequest,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Initialize a lazy async client for one request.

        Args:
            request: Request-scoped context and credential.
            transport: Optional HTTPX transport used by focused tests.
        """

        self.request = request
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> SmartCmpClient:
        """Open the underlying HTTPX client and return this request client."""

        await self._get_client()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the underlying HTTPX client when leaving an async context."""

        await self.close()

    async def close(self) -> None:
        """Close the owned HTTP connection pool if it has been opened."""

        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        allow_empty: bool = False,
    ) -> Any:
        """Execute one upstream request and return its decoded JSON payload.

        Args:
            method: HTTP method used by the SmartCMP endpoint.
            path: Provider-owned API path, optionally including a query string.
            params: Optional query parameters.
            json_body: Optional JSON request body.
            allow_empty: Return an empty object for a successful empty response.
                This is limited to explicit operations whose upstream contract
                permits HTTP 204 or a blank HTTP 200 body.

        Returns:
            Decoded JSON response.

        Raises:
            SmartCmpAuthenticationError: For HTTP 401.
            SmartCmpPermissionError: For HTTP 403.
            SmartCmpNotFoundError: For HTTP 404.
            SmartCmpConflictError: For HTTP 409.
            SmartCmpRateLimitError: For HTTP 429.
            SmartCmpValidationError: For HTTP 400 or 422.
            SmartCmpTimeoutError: When the configured timeout expires.
            SmartCmpUpstreamError: For transport, invalid JSON, or other service errors.
        """

        response = await self._request_response(
            method,
            path,
            params=params,
            json_body=json_body,
        )

        if allow_empty and not str(response.text or "").strip():
            return {}

        try:
            payload = response.json()
        except ValueError as exc:
            body = self._safe_body(response)
            raise SmartCmpUpstreamError(
                "SmartCMP returned invalid JSON. "
                f"Status={response.status_code}, Body={body}",
                trace_id=self.request.context.trace_id,
                http_status=response.status_code,
                mutation_outcome=(
                    "unknown" if self._is_mutation_method(method) else None
                ),
            ) from exc

        self._raise_business_error(payload)
        return payload

    async def request_json_or_text(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Execute one read and return decoded JSON or a plain-text body.

        This is limited to Provider-owned endpoints that legitimately vary
        between JSON and text across SmartCMP releases, such as the monitoring
        API URL setting. HTTP and JSON business errors retain normal mapping.

        Args:
            method: HTTP method required by the explicit domain operation.
            path: Provider-owned relative SmartCMP path.
            params: Optional query parameters.

        Returns:
            Decoded JSON when available, otherwise stripped response text.
        """

        response = await self._request_response(method, path, params=params)
        try:
            payload = response.json()
        except ValueError:
            return str(response.text or "").strip()
        self._raise_business_error(payload)
        return payload

    async def _request_response(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
    ) -> httpx.Response:
        """Execute one authenticated call without redirects or implicit retries.

        Redirects are rejected so a Provider credential cannot be forwarded to
        an unexpected origin. Transport failures on mutating methods carry an
        unknown outcome because SmartCMP may have accepted the write already.
        """

        timeout_seconds = self._effective_timeout_seconds()
        client = await self._get_client()
        url = self._build_url(path)
        request_kwargs: dict[str, Any] = {
            "headers": self.request.credential.headers(),
            "timeout": timeout_seconds,
        }
        if params is not None:
            request_kwargs["params"] = params
        if json_body is not None:
            request_kwargs["json"] = json_body
        try:
            response = await client.request(
                method.upper(),
                url,
                **request_kwargs,
            )
        except httpx.TimeoutException as exc:
            raise SmartCmpTimeoutError(
                "SmartCMP request timed out.",
                trace_id=self.request.context.trace_id,
                mutation_outcome=(
                    "unknown" if self._is_mutation_method(method) else None
                ),
            ) from exc
        except httpx.RequestError as exc:
            raise SmartCmpUpstreamError(
                f"SmartCMP request failed: {exc}",
                trace_id=self.request.context.trace_id,
                mutation_outcome=(
                    "unknown" if self._is_mutation_method(method) else None
                ),
            ) from exc
        if response.is_redirect:
            raise SmartCmpUpstreamError(
                "SmartCMP redirects are not allowed for authenticated requests.",
                trace_id=self.request.context.trace_id,
                http_status=response.status_code,
                mutation_outcome=(
                    "unknown"
                    if self._is_mutation_method(method)
                    else "definite_failure"
                ),
            )
        if response.status_code >= 400:
            self._raise_http_error(response, method=method)
        return response

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazily create the connection pool owned by this request scope."""

        if self._client is None:
            tls = self.request.context.instance.tls
            verify: bool | str = tls.ca_bundle if tls.ca_bundle else tls.verify
            self._client = httpx.AsyncClient(
                timeout=self.request.context.instance.timeout_seconds,
                verify=verify,
                follow_redirects=False,
                transport=self._transport,
            )
        return self._client

    def _effective_timeout_seconds(self) -> float:
        """Combine instance timeout with the invocation's remaining deadline."""

        timeout_seconds = self.request.context.instance.timeout_seconds
        deadline = self.request.context.deadline
        if deadline is None:
            return timeout_seconds

        now = datetime.now(deadline.tzinfo) if deadline.tzinfo else datetime.now()
        remaining_seconds = (deadline - now).total_seconds()
        if remaining_seconds <= 0:
            raise SmartCmpTimeoutError(
                "SmartCMP request deadline expired before the upstream call.",
                trace_id=self.request.context.trace_id,
                mutation_outcome="definite_failure",
            )
        return min(timeout_seconds, remaining_seconds)

    def _build_url(self, path: str) -> str:
        """Join only a Provider-owned relative path to the configured instance."""

        normalized_path = str(path or "").strip()
        if not normalized_path or "://" in normalized_path:
            raise SmartCmpValidationError(
                "SmartCMP operation path must be a Provider-owned relative path.",
                trace_id=self.request.context.trace_id,
            )
        base_url = self.request.context.instance.base_url.rstrip("/")
        return f"{base_url}/{normalized_path.lstrip('/')}"

    def _raise_http_error(
        self,
        response: httpx.Response,
        *,
        method: str,
    ) -> None:
        """Map one failed upstream response using the submitted HTTP method."""

        message = self._extract_error_message(response)
        rendered = f"HTTP {response.status_code}: {message}".rstrip()
        body = self._safe_body(response)
        if body and body != message:
            rendered = f"{rendered}. Response body: {body}"
        status_code = response.status_code
        kwargs = {
            "trace_id": self.request.context.trace_id,
            "http_status": status_code,
            "mutation_outcome": (
                "unknown"
                if status_code >= 500
                and self._is_mutation_method(method)
                else "definite_failure"
            ),
        }
        error_types = {
            400: SmartCmpValidationError,
            401: SmartCmpAuthenticationError,
            403: SmartCmpPermissionError,
            404: SmartCmpNotFoundError,
            409: SmartCmpConflictError,
            422: SmartCmpValidationError,
            429: SmartCmpRateLimitError,
        }
        error_type = error_types.get(response.status_code, SmartCmpUpstreamError)
        raise error_type(rendered, **kwargs)

    def _raise_business_error(self, payload: Any) -> None:
        """Map a successful HTTP response carrying a definite business failure."""

        if not isinstance(payload, dict) or payload.get("success") is not False:
            return
        message = str(
            payload.get("message")
            or payload.get("error")
            or payload.get("errMsg")
            or "SmartCMP rejected the operation."
        ).strip()
        message = self.sanitize_error_text(message)
        code = payload.get("code")
        prefix = (
            f"SmartCMP business error {code}"
            if code not in (None, "")
            else "SmartCMP business error"
        )
        raise SmartCmpUpstreamError(
            f"{prefix}: {message}",
            trace_id=self.request.context.trace_id,
            mutation_outcome="definite_failure",
        )

    @staticmethod
    def _extract_error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            message = str(
                payload.get("message")
                or payload.get("error")
                or payload.get("errMsg")
                or ""
            ).strip()
            if message:
                return SmartCmpClient.sanitize_error_text(message)
        return SmartCmpClient._safe_body(response)

    @staticmethod
    def _safe_body(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return SmartCmpClient.sanitize_error_text(
                str(response.text or "")
            )[:400]
        redacted = SmartCmpClient._redact_sensitive_value(payload)
        return json.dumps(
            redacted,
            ensure_ascii=False,
            separators=(",", ":"),
        )[:400]

    @staticmethod
    def _redact_sensitive_value(value: Any, *, key: str = "") -> Any:
        """Recursively redact credential-bearing upstream error fields."""

        normalized_key = "".join(
            character
            for character in str(key or "").casefold()
            if character.isalnum()
        )
        if any(fragment in normalized_key for fragment in _SENSITIVE_KEY_FRAGMENTS):
            return "[REDACTED]"
        if isinstance(value, dict):
            return {
                str(nested_key): SmartCmpClient._redact_sensitive_value(
                    nested_value,
                    key=str(nested_key),
                )
                for nested_key, nested_value in value.items()
            }
        if isinstance(value, list):
            return [
                SmartCmpClient._redact_sensitive_value(item)
                for item in value
            ]
        if isinstance(value, str):
            return SmartCmpClient.sanitize_error_text(value)
        return value

    @staticmethod
    def sanitize_error_text(value: str) -> str:
        """Redact credential assignments in one user-visible upstream message."""

        return _SENSITIVE_ASSIGNMENT_PATTERN.sub(
            lambda match: (
                f"{match.group('key')}{match.group('separator')}[REDACTED]"
            ),
            str(value or ""),
        ).strip()

    @staticmethod
    def _is_mutation_method(method: str) -> bool:
        """Return whether an HTTP method can produce a non-idempotent change."""

        return str(method or "").upper() not in {"GET", "HEAD", "OPTIONS"}
