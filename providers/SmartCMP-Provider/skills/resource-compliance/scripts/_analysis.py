#!/usr/bin/env python3
"""Helpers for SmartCMP resource compliance analysis."""


def build_analysis_facts(resource_record: dict) -> dict:
    """Return a placeholder facts object for a resource record."""
    return {
        "resourceId": resource_record.get("resourceId", ""),
        "resourceName": resource_record.get("resource", {}).get("name")
        or resource_record.get("summary", {}).get("name", ""),
    }
