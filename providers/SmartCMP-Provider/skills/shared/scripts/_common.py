# -*- coding: utf-8 -*-
"""SmartCMP Provider Common Utilities.

This module provides shared utilities for all SmartCMP Provider scripts.
Import this module to get standardized environment handling and URL normalization.

Features:
  - Automatic URL normalization (adds /platform-api if missing)
  - Smart auth URL inference based on environment (SaaS vs Private)
  - Standardized environment variable handling
  - Common HTTP headers generation
  - SSL warning suppression
  - Auto-login with username/password when cookie not provided
  - Cookie caching with TTL to avoid repeated logins

Usage:
  from _common import get_cmp_config, create_headers, require_config

Environment Variables:
  CMP_URL      - Base URL (IP, hostname, or full path)
  CMP_COOKIE   - Full session cookie string (optional if username/password provided)
  CMP_USERNAME - Username for auto-login (fallback when no cookie)
  CMP_PASSWORD - Password for auto-login (fallback when no cookie)
  
Note: CMP_AUTH_URL is no longer required - it is automatically inferred from CMP_URL.
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
_SAAS_DOMAINS = ["smartcmp.cloud", "cloudchef.io"]
_SAAS_AUTH_URL = "https://account.smartcmp.cloud/bss-api/api/authentication"

# Cookie cache configuration - store in workspace sessions directory
_CACHE_DIR = Path.cwd() / ".atlasclaw" / "users" / "default" / "sessions"
_COOKIE_CACHE_FILE = _CACHE_DIR / "smartcmp_cookie_cache.json"
_COOKIE_TTL_SECONDS = 1800  # 30 minutes


def normalize_url(url: str) -> str:
    """Normalize CMP URL to ensure it includes the /platform-api path.
    
    This function handles multiple input formats:
      - IP only: "10.0.0.1" -> "https://10.0.0.1/platform-api"
      - Hostname only: "cmp.example.com" -> "https://cmp.example.com/platform-api"
      - With scheme: "https://cmp.example.com" -> "https://cmp.example.com/platform-api"
      - Already correct: "https://cmp.example.com/platform-api" -> unchanged
      - With trailing slash: "https://cmp.example.com/" -> "https://cmp.example.com/platform-api"
    
    Args:
        url: Raw URL from environment variable
        
    Returns:
        Normalized URL with scheme and /platform-api path
    """
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
    """Infer authentication URL from CMP base URL.
    
    This function automatically determines the correct auth endpoint based on
    the CMP URL pattern:
    
    - SaaS environment (*.smartcmp.cloud, *.cloudchef.io):
      -> https://account.smartcmp.cloud/bss-api/api/authentication
      
    - Private deployment (IP address or other domain):
      -> https://{host}/platform-api/login
    
    Args:
        cmp_url: The CMP base URL (e.g., "https://console.smartcmp.cloud" or "https://192.168.1.100")
        
    Returns:
        Inferred authentication endpoint URL
    """
    if not cmp_url:
        return ""
    
    # Add scheme if missing for parsing
    url = cmp_url.strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    
    # Check if this is a SaaS environment
    for saas_domain in _SAAS_DOMAINS:
        if saas_domain in host:
            return _SAAS_AUTH_URL
    
    # Private deployment - use same host with /platform-api/login path
    return f"{parsed.scheme}://{parsed.netloc}/platform-api/login"


def _get_cached_cookie(cmp_url: str = "") -> str:
    """Get cached cookie if still valid and URL matches.
    
    Args:
        cmp_url: Current CMP URL to validate cache against.
                 If URL changed, cache is considered invalid.
    
    Returns:
        Cached cookie string if valid, empty string otherwise.
    """
    try:
        if _COOKIE_CACHE_FILE.exists():
            data = json.loads(_COOKIE_CACHE_FILE.read_text(encoding="utf-8"))
            # Check expiration
            if data.get("expires_at", 0) <= time.time():
                return ""
            # Check URL match (environment switch detection)
            cached_url = data.get("cmp_url", "")
            if cmp_url and cached_url and cached_url != cmp_url:
                return ""
            return data.get("cookie", "")
    except Exception:
        pass
    return ""


def _cache_cookie(cookie: str, cmp_url: str = "", ttl_seconds: int = _COOKIE_TTL_SECONDS) -> None:
    """Cache cookie to file with URL binding.
    
    Args:
        cookie: The cookie string to cache
        cmp_url: The CMP URL this cookie belongs to
        ttl_seconds: Time-to-live in seconds
    """
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
        pass  # Silently ignore cache write failures


def _auto_login(auth_url: str, username: str, password: str) -> str:
    """Auto-login to SmartCMP and get session cookie.
    
    POST {auth_url}
    Content-Type: application/x-www-form-urlencoded
    Body: username=xxx&password=xxx
    
    Args:
        auth_url: Authentication endpoint URL
        username: Login username
        password: Login password
        
    Returns:
        Cookie string for subsequent requests
        
    Raises:
        RuntimeError: If login fails
    """
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
            raise RuntimeError("Login response contains no cookies or tokens")
        
        # Build cookie string
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
        return cookie_str
        
    except requests.RequestException as e:
        raise RuntimeError(f"Login request failed: {e}")


def get_cmp_config(exit_on_error: bool = True) -> tuple:
    """Get SmartCMP configuration from environment variables.
    
    Priority:
    1. Use CMP_COOKIE if provided
    2. Otherwise, try to use cached cookie
    3. Otherwise, auto-login with CMP_USERNAME/CMP_PASSWORD
    
    Note: CMP_AUTH_URL is automatically inferred from CMP_URL:
      - SaaS (*.smartcmp.cloud) -> account.smartcmp.cloud/bss-api/api/authentication
      - Private deployment -> {CMP_URL host}/platform-api/login
    
    Args:
        exit_on_error: If True, print error and exit when config unavailable
        
    Returns:
        Tuple of (base_url, cookie) where base_url is normalized
        
    Raises:
        SystemExit: When exit_on_error=True and config unavailable
    """
    raw_url = os.environ.get("CMP_URL", "")
    cookie = os.environ.get("CMP_COOKIE", "")
    username = os.environ.get("CMP_USERNAME", "")
    password = os.environ.get("CMP_PASSWORD", "")
    
    # Support legacy CMP_AUTH_URL for backward compatibility, but prefer auto-inference
    auth_url = os.environ.get("CMP_AUTH_URL", "")
    if not auth_url and raw_url:
        auth_url = _infer_auth_url(raw_url)
    
    # If no explicit cookie, try cache or auto-login
    if not cookie:
        # Try cached cookie first (validate against current URL)
        cookie = _get_cached_cookie(raw_url)
        
        # If still no cookie, try auto-login
        if not cookie and username and password and auth_url:
            try:
                cookie = _auto_login(auth_url, username, password)
                # Cache the new cookie with URL binding
                _cache_cookie(cookie, raw_url)
            except RuntimeError as e:
                if exit_on_error:
                    print(f"[ERROR] Auto-login failed: {e}")
                    sys.exit(1)
                return "", ""
    
    # Final validation
    if not raw_url or not cookie:
        if exit_on_error:
            print("[ERROR] SmartCMP configuration not available.")
            print()
            print("Configure one of the following:")
            print()
            print("  Option 1: Direct cookie")
            print("    $env:CMP_URL = \"<your-cmp-host>\"")
            print("    $env:CMP_COOKIE = \"<full cookie string>\"")
            print()
            print("  Option 2: Auto-login credentials (recommended)")
            print("    $env:CMP_URL = \"<your-cmp-host>\"")
            print("    $env:CMP_USERNAME = \"<username>\"")
            print("    $env:CMP_PASSWORD = \"<password>\"")
            print()
            print("  Note: Auth URL is auto-inferred from CMP_URL:")
            print("    - SaaS (*.smartcmp.cloud) -> account.smartcmp.cloud")
            print("    - Private deployment -> {CMP_URL}/platform-api/login")
            print()
            sys.exit(1)
        return "", ""
    
    base_url = normalize_url(raw_url)
    return base_url, cookie


def create_headers(cookie: str, content_type: str = "application/json; charset=utf-8") -> dict:
    """Create standard HTTP headers for SmartCMP API requests.
    
    Args:
        cookie: Session cookie string
        content_type: Content-Type header value (default: application/json)
        
    Returns:
        Dictionary of HTTP headers
    """
    headers = {"Cookie": cookie}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


# Convenience: Auto-configure when imported
# Scripts can use: from _common import BASE_URL, COOKIE, HEADERS
BASE_URL, COOKIE = get_cmp_config(exit_on_error=False)
HEADERS = create_headers(COOKIE) if COOKIE else {}


def require_config():
    """Validate that configuration is available, exit if not.
    
    Call this at the start of scripts that require CMP connection.
    
    Returns:
        Tuple of (base_url, cookie, headers)
    """
    global BASE_URL, COOKIE, HEADERS
    BASE_URL, COOKIE = get_cmp_config(exit_on_error=True)
    HEADERS = create_headers(COOKIE)
    return BASE_URL, COOKIE, HEADERS
