# -*- coding: utf-8 -*-
"""SmartCMP Provider Common Utilities - Updated for SkillDeps Integration.

This module now reads configuration from ATLASCLAW_PROVIDER_CONFIG and ATLASCLAW_COOKIES
instead of individual environment variables, while maintaining backward compatibility.

Features:
  - Read configuration from SkillDeps (via environment variables)
  - Automatic URL normalization (adds /platform-api if missing)
  - Smart auth URL inference based on environment (SaaS vs Private)
  - Common HTTP headers generation
  - SSL warning suppression
  - Auto-login with username/password when cookie not provided
  - Cookie caching with TTL to avoid repeated logins

Usage:
  from _common import get_cmp_config, create_headers, require_config

Environment Variables (from SkillDeps):
  ATLASCLAW_COOKIES          - JSON string of all cookies from HTTP request
  ATLASCLAW_PROVIDER_CONFIG  - JSON string of provider configuration from atlasclaw.json
  ATLASCLAW_USER_ID          - Current user ID

Legacy Environment Variables (fallback):
  CMP_URL       - Base URL (IP, hostname, or full path)
  CMP_API_TOKEN - User API token for token-based authentication
  CMP_COOKIE    - Full session cookie string
  CMP_USERNAME  - Username for auto-login
  CMP_PASSWORD  - Password for auto-login
"""
import os
import sys
import json
import time
import urllib3
import requests
from pathlib import Path
from urllib.parse import urlparse, urlunparse

# Suppress SSL warnings globally when this module is imported
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# API path that should be appended if missing
_API_PATH = "/platform-api"

# SaaS environment detection
# Domain suffix alone is not reliable because private deployments can also use
# smartcmp.cloud subdomains.
_SAAS_HOSTS = {
    "console.smartcmp.cloud",
    "account.smartcmp.cloud",
    "console.cloudchef.io",
}
_SAAS_AUTH_URL = "https://account.smartcmp.cloud/bss-api/api/authentication"

# Cookie cache configuration
def _get_cache_dir() -> Path:
    """Get the cache directory path."""
    atlasclaw_root = os.environ.get("ATLASCLAW_ROOT", "")
    if atlasclaw_root:
        return Path(atlasclaw_root) / ".atlasclaw" / "users" / "default" / "sessions"
    return Path.cwd() / ".atlasclaw" / "users" / "default" / "sessions"

_CACHE_DIR = _get_cache_dir()
_COOKIE_CACHE_FILE = _CACHE_DIR / "smartcmp_cookie_cache.json"
_COOKIE_TTL_SECONDS = 1800  # 30 minutes


def normalize_url(url: str) -> str:
    """Normalize CMP URL to ensure it includes the /platform-api path."""
    if not url:
        return ""

    url = url.strip()

    # Add scheme if missing
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    # Parse the URL
    parsed = urlparse(url)

    # Get the path and normalize it
    path = parsed.path.rstrip("/")

    # Check if path already ends with /platform-api
    if not path.endswith(_API_PATH):
        path = path + _API_PATH

    # Reconstruct the URL
    normalized = urlunparse((
        parsed.scheme,
        parsed.netloc,
        path,
        "",  # params
        "",  # query
        ""   # fragment
    ))

    return normalized


def _infer_auth_url(cmp_url: str) -> str:
    """Infer authentication URL from CMP base URL."""
    if not cmp_url:
        return ""

    url = cmp_url.strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    # Only canonical SmartCMP SaaS hosts on the default HTTPS port should route
    # to the shared SaaS authentication API.
    if hostname in _SAAS_HOSTS and parsed.port in (None, 443):
        return _SAAS_AUTH_URL

    # Private deployment
    return f"{parsed.scheme}://{parsed.netloc}/platform-api/login"


def _resolve_auth_url(cmp_url: str, explicit_auth_url: str = "") -> str:
    """Resolve the auth URL using explicit configuration first, then inference."""
    explicit_auth_url = (explicit_auth_url or "").strip()
    if explicit_auth_url:
        if not explicit_auth_url.startswith(("http://", "https://")):
            explicit_auth_url = f"https://{explicit_auth_url}"
        return explicit_auth_url
    return _infer_auth_url(cmp_url)


def _get_cached_cookie(cmp_url: str = "") -> str:
    """Get cached cookie if still valid and URL matches."""
    try:
        if _COOKIE_CACHE_FILE.exists():
            data = json.loads(_COOKIE_CACHE_FILE.read_text(encoding="utf-8"))
            # Check expiration
            if data.get("expires_at", 0) <= time.time():
                return ""
            # Check URL match
            cached_url = data.get("cmp_url", "")
            if cmp_url and cached_url and cached_url != cmp_url:
                return ""
            return data.get("cookie", "")
    except Exception:
        pass
    return ""


def _cache_cookie(cookie: str, cmp_url: str = "", ttl_seconds: int = _COOKIE_TTL_SECONDS) -> None:
    """Cache cookie to file with URL binding."""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "cookie": cookie,
            "cmp_url": cmp_url,
            "expires_at": time.time() + ttl_seconds,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        _COOKIE_CACHE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def _auto_login(auth_url: str, username: str, password: str) -> str:
    """Auto-login to SmartCMP and get session cookie."""
    import hashlib

    # Auto-detect: if password is not 32-char hex (MD5 format), auto-encrypt it
    if not (len(password) == 32 and all(c in '0123456789abcdefABCDEF' for c in password)):
        password = hashlib.md5(password.encode()).hexdigest()

    try:
        resp = requests.post(
            auth_url,
            data={"username": username, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            verify=False,
            timeout=30
        )

        if resp.status_code != 200:
            raise RuntimeError(f"Login failed: HTTP {resp.status_code}")

        # Build cookie string from response cookies
        cookies = resp.cookies.get_dict()
        body = {}

        # Also try to get token from response body
        try:
            body = resp.json()
            if "token" in body:
                cookies["CloudChef-Authenticate"] = body["token"]
            if "refreshToken" in body:
                cookies["CloudChef-Authenticate-Refresh"] = body["refreshToken"]
        except Exception:
            pass

        if not cookies:
            message = "Login response contains no cookies or tokens"
            body_code = body.get("code", "")
            body_message = body.get("message", "")
            if body_code or body_message:
                message = f"{message}: {body_code} {body_message}".strip()
            raise RuntimeError(message)

        # Build cookie string
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
        return cookie_str

    except requests.RequestException as e:
        raise RuntimeError(f"Login request failed: {e}")


def _get_config_from_skilldeps() -> tuple:
    """Get configuration from SkillDeps-injected environment variables.

    Returns:
        Tuple of (base_url, auth_token, instance_config) or (None, None, None) if not available
    """
    # Read from SkillDeps-injected environment variables
    cookies_json = os.environ.get('ATLASCLAW_COOKIES', '{}')
    provider_config_json = os.environ.get('ATLASCLAW_PROVIDER_CONFIG', '{}')

    cookies = {}
    provider_config = {}

    try:
        cookies = json.loads(cookies_json)
    except json.JSONDecodeError:
        pass

    try:
        provider_config = json.loads(provider_config_json)
    except json.JSONDecodeError:
        pass

    # Get SmartCMP instances from provider config
    smartcmp_instances = provider_config.get('smartcmp', {})

    if not smartcmp_instances:
        return None, None, None

    # Select instance (default to first, or use 'prod' if available)
    instance_name = 'prod' if 'prod' in smartcmp_instances else list(smartcmp_instances.keys())[0]
    instance = smartcmp_instances.get(instance_name, {})

    # Extract configuration
    base_url = instance.get('base_url', '')
    explicit_auth_url = instance.get('auth_url', '')

    # Authentication priority:
    # 1. CloudChef-Authenticate from cookies (UI passed)
    # 2. User token from provider config
    # 3. Cookie from provider config
    # 4. Username/Password from provider config
    cloudchef_token = cookies.get('CloudChef-Authenticate', '')
    user_token = instance.get('user_token', '')
    config_cookie = instance.get('cookie', '')
    username = instance.get('username', '')
    password = instance.get('password', '')

    # Determine auth token
    auth_token = cloudchef_token or user_token or config_cookie

    # If no token but have credentials, try auto-login
    if not auth_token and username and password and base_url:
        try:
            auth_url = _resolve_auth_url(base_url, explicit_auth_url)
            cookie_str = _auto_login(auth_url, username, password)
            # Cache the full cookie string for future use
            _cache_cookie(cookie_str, base_url)
            # Extract CloudChef-Authenticate JWT token from cookie string
            for part in cookie_str.split(';'):
                part = part.strip()
                if part.startswith('CloudChef-Authenticate='):
                    auth_token = part.split('=', 1)[1]
                    break
            # Fallback to full cookie string if token not found
            if not auth_token:
                auth_token = cookie_str
        except RuntimeError:
            pass

    if not base_url:
        return None, None, None

    # Normalize URL
    base_url = normalize_url(base_url)

    return base_url, auth_token, instance


def _get_config_from_env() -> tuple:
    """Get configuration from legacy environment variables (backward compatibility).

    Returns:
        Tuple of (base_url, auth_token, instance_config) or (None, None, None) if not available
    """
    raw_url = os.environ.get("CMP_URL", "")
    user_token = os.environ.get("CMP_API_TOKEN", "")
    cookie = os.environ.get("CMP_COOKIE", "")
    username = os.environ.get("CMP_USERNAME", "")
    password = os.environ.get("CMP_PASSWORD", "")
    explicit_auth_url = os.environ.get("CMP_AUTH_URL", "")

    if not raw_url:
        return None, None, None

    # If user token is provided, use it directly
    if user_token:
        base_url = normalize_url(raw_url)
        instance = {'base_url': raw_url, 'user_token': user_token}
        return base_url, user_token, instance

    auth_url = _resolve_auth_url(raw_url, explicit_auth_url)

    # If no explicit cookie, try cache or auto-login
    if not cookie:
        # Try cached cookie first
        cookie = _get_cached_cookie(raw_url)

        # If still no cookie, try auto-login
        if not cookie and username and password and auth_url:
            try:
                cookie = _auto_login(auth_url, username, password)
                _cache_cookie(cookie, raw_url)
            except RuntimeError:
                pass

    if not cookie:
        return None, None, None

    # Extract CloudChef-Authenticate JWT token for API header use
    auth_token = cookie
    for part in cookie.split(';'):
        part = part.strip()
        if part.startswith('CloudChef-Authenticate='):
            auth_token = part.split('=', 1)[1]
            break

    base_url = normalize_url(raw_url)

    # Build a minimal instance config for compatibility
    instance = {
        'base_url': raw_url,
        'cookie': cookie,
    }
    if username:
        instance['username'] = username

    return base_url, auth_token, instance


def get_cmp_config(exit_on_error: bool = True) -> tuple:
    """Get SmartCMP configuration from SkillDeps or environment variables.

    Priority:
    1. ATLASCLAW_PROVIDER_CONFIG / ATLASCLAW_COOKIES (from SkillDeps)
    2. Legacy CMP_URL / CMP_COOKIE / CMP_USERNAME / CMP_PASSWORD

    Args:
        exit_on_error: If True, print error and exit when config unavailable

    Returns:
        Tuple of (base_url, auth_token, instance_config)

    Raises:
        SystemExit: When exit_on_error=True and config unavailable
    """
    # Try SkillDeps first
    base_url, auth_token, instance = _get_config_from_skilldeps()

    # Fall back to legacy environment variables
    if not base_url or not auth_token:
        base_url, auth_token, instance = _get_config_from_env()

    # Final validation
    if not base_url or not auth_token:
        if exit_on_error:
            print("[ERROR] SmartCMP configuration not available.")
            print()
            print("Configure one of the following in atlasclaw.json:")
            print()
            print('  "service_providers": {')
            print('    "smartcmp": {')
            print('      "prod": {')
            print('        "base_url": "https://cmp.example.com/platform-api",')
            print('        "cookie": "${CMP_COOKIE}"')
            print('      }')
            print('    }')
            print('  }')
            print()
            print("Or pass CloudChef-Authenticate cookie in HTTP request.")
            print()
            sys.exit(1)
        return "", "", {}

    return base_url, auth_token, instance


def create_headers(auth_token: str, content_type: str = "application/json; charset=utf-8") -> dict:
    """Create standard HTTP headers for SmartCMP API requests.

    Args:
        auth_token: CloudChef-Authenticate token, session cookie, or API token
        content_type: Content-Type header value (default: application/json)

    Returns:
        Dictionary of HTTP headers
    """
    headers = {}
    if auth_token:
        # API tokens (cmp_tk_*) use Authorization: Bearer header
        if auth_token.startswith("cmp_tk_"):
            headers["Authorization"] = f"Bearer {auth_token}"
        else:
            headers["CloudChef-Authenticate"] = auth_token
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def require_config():
    """Validate that configuration is available, exit if not.

    Call this at the start of scripts that require CMP connection.

    Returns:
        Tuple of (base_url, auth_token, headers, instance)
    """
    base_url, auth_token, instance = get_cmp_config(exit_on_error=True)
    headers = create_headers(auth_token)
    return base_url, auth_token, headers, instance


# Convenience: Auto-configure when imported
# Scripts can use: from _common import BASE_URL, AUTH_TOKEN, HEADERS, INSTANCE
BASE_URL, AUTH_TOKEN, INSTANCE = get_cmp_config(exit_on_error=False)
HEADERS = create_headers(AUTH_TOKEN) if AUTH_TOKEN else {}
