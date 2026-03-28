#!/usr/bin/env python3
"""Shared helpers for SmartCMP cost optimization scripts."""


def build_pageable_request(page: int = 0, size: int = 20) -> dict:
    """Return a basic pageable request placeholder."""
    return {"page": page, "size": size}


def build_query_request(query_value: str = "") -> dict:
    """Return a basic query request placeholder."""
    return {"queryValue": query_value}
