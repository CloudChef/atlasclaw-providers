# -*- coding: utf-8 -*-
"""Storage roots for the audit-report provider."""

from __future__ import annotations

from pathlib import Path
from pathlib import PureWindowsPath
from typing import Any


def _config_value(host: Any, key: str) -> str:
    """Read one provider setting from the Host Services config surface."""
    getter = getattr(host, "get_config", None)
    if callable(getter):
        value = getter(key, "")
    else:
        config = getattr(host, "config", {})
        value = config.get(key, "") if isinstance(config, dict) else ""
    return str(value or "").strip()


def _configured_root(host: Any, key: str) -> Path | None:
    value = _config_value(host, key)
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"{key} must be an absolute path")
    return path


def _path_segment(value: Any, name: str) -> str:
    segment = str(value or "")
    if (not segment or segment in {".", ".."} or segment != segment.strip()
            or "/" in segment or "\\" in segment or "\x00" in segment
            or PureWindowsPath(segment).drive):
        raise ValueError(f"{name} must be a non-empty path segment")
    return segment


def report_data_dir(host: Any) -> Path:
    """Return the per-tenant and per-user report storage root, or legacy data root."""
    root = _configured_root(host, "reports_dir")
    if root is None:
        return Path(host.data_dir)
    user = getattr(host, "user", None)
    tenant_id = _path_segment(getattr(user, "tenant_id", ""), "tenant_id")
    user_id = _path_segment(getattr(user, "user_id", ""), "user_id")
    return root / tenant_id / user_id


def shared_data_dir(host: Any) -> Path:
    """Return the configured provider-shared root or the Host Services default."""
    return _configured_root(host, "standards_dir") or Path(host.shared_data_dir)


def has_configured_shared_data_dir(host: Any) -> bool:
    """Return whether the instance explicitly configures its shared storage root."""
    return _configured_root(host, "standards_dir") is not None
