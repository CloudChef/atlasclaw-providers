#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Small layout helpers for SmartCMP form schema edits."""

from __future__ import annotations

from typing import Any


def ensure_field_in_root_fieldsets(
    schema: dict[str, Any],
    field_key: str,
    warnings: list[str],
) -> None:
    """Ensure an inserted top-level field is reachable from root fieldsets."""
    if not isinstance(field_key, str) or not field_key:
        return

    fieldsets = schema.get("fieldsets")
    if fieldsets is None:
        schema["fieldsets"] = [{"id": "default", "fields": [field_key]}]
        warnings.append(f"Created root fieldsets for inserted field {field_key!r}.")
        return
    if not isinstance(fieldsets, list):
        return

    target_fieldset: dict[str, Any] | None = None
    for fieldset in fieldsets:
        if not isinstance(fieldset, dict):
            continue
        fields = fieldset.get("fields")
        if not isinstance(fields, list):
            fields = fieldset.get("properties")
            if not isinstance(fields, list):
                continue
        if field_key in fields:
            return
        if target_fieldset is None:
            target_fieldset = fieldset

    if target_fieldset is None:
        target_fieldset = {"id": "default", "fields": []}
        fieldsets.append(target_fieldset)

    fields = target_fieldset.setdefault("fields", [])
    if isinstance(fields, list):
        fields.append(field_key)
        warnings.append(f"Added inserted field {field_key!r} to root fieldsets.")
