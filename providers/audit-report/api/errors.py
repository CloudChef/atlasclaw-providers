# -*- coding: utf-8 -*-
# Copyright 2026 Qianyun, Inc., www.cloudchef.io, All rights reserved.
"""Provider-local error type mapped by the AtlasClaw provider dispatcher."""

from __future__ import annotations


class ProviderError(Exception):
    """Structured provider failure with a stable code and HTTP status."""

    def __init__(self, message: str, *, status_code: int = 400, code: str = "provider_error") -> None:
        super().__init__(message)
        self.detail = message
        self.status_code = status_code
        self.code = code
