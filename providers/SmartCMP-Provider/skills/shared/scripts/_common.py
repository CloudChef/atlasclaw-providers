"""SmartCMP Provider Common Utilities.

This module provides shared utilities for all SmartCMP Provider scripts.
Import this module to get standardized environment handling and URL normalization.

Features:
  - Automatic URL normalization (adds /platform-api if missing)
  - Standardized environment variable handling
  - Common HTTP headers generation
  - SSL warning suppression

Usage:
  from _common import get_cmp_config, create_headers

Environment Variables:
  CMP_URL    - Base URL (IP, hostname, or full path)
               Examples: "192.168.176.150", "https://cmp.corp.com", "https://cmp.corp.com/platform-api"
  CMP_COOKIE - Full session cookie string
"""
import os
import sys
import urllib3
from urllib.parse import urlparse, urlunparse

# Suppress SSL warnings globally when this module is imported
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# API path that should be appended if missing
_API_PATH = "/platform-api"


def normalize_url(url: str) -> str:
    """Normalize CMP URL to ensure it includes the /platform-api path.
    
    This function handles multiple input formats:
      - IP only: "192.168.176.150" → "https://192.168.176.150/platform-api"
      - Hostname only: "cmp.corp.com" → "https://cmp.corp.com/platform-api"
      - With scheme: "https://cmp.corp.com" → "https://cmp.corp.com/platform-api"
      - Already correct: "https://cmp.corp.com/platform-api" → unchanged
      - With trailing slash: "https://cmp.corp.com/" → "https://cmp.corp.com/platform-api"
    
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


def get_cmp_config(exit_on_error: bool = True) -> tuple:
    """Get SmartCMP configuration from environment variables.
    
    Reads CMP_URL and CMP_COOKIE from environment, normalizes the URL,
    and optionally exits with an error message if not configured.
    
    Args:
        exit_on_error: If True, print error and exit when env vars are missing
        
    Returns:
        Tuple of (base_url, cookie) where base_url is normalized
        
    Raises:
        SystemExit: When exit_on_error=True and env vars are missing
    """
    raw_url = os.environ.get("CMP_URL", "")
    cookie = os.environ.get("CMP_COOKIE", "")
    
    if not raw_url or not cookie:
        if exit_on_error:
            print("[ERROR] Environment variables not configured.")
            print()
            print("Set the following environment variables:")
            print()
            print("  PowerShell:")
            print('    $env:CMP_URL = "https://<host>/platform-api"')
            print('    $env:CMP_COOKIE = "<full cookie string>"')
            print()
            print("  Bash:")
            print('    export CMP_URL="https://<host>/platform-api"')
            print('    export CMP_COOKIE="<full cookie string>"')
            print()
            print("  Note: CMP_URL accepts IP, hostname, or full URL.")
            print("        The /platform-api path will be auto-appended if missing.")
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
    """
    global BASE_URL, COOKIE, HEADERS
    BASE_URL, COOKIE = get_cmp_config(exit_on_error=True)
    HEADERS = create_headers(COOKIE)
    return BASE_URL, COOKIE, HEADERS
