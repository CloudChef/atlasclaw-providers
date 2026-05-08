# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Extract SmartCMP approval resource spec display names from request parameters."""

from __future__ import annotations

import re
from typing import Any


_DETAIL_FRAGMENT_RE = re.compile(r"(?i)(?:\d+\s*v?\s*cpu|\d+\s*[gm]b|\d+\s*c\s*\d+\s*g)")
_SPEC_LABEL_RE = re.compile(
    r"(?i)^(?:current\s+selection|selected\s+spec(?:ification)?|spec(?:ification)?|flavor|compute\s+profile|当前选择|规格)[:：]?\s*"
)


def unwrap_value(value: Any) -> Any:
    """Return the payload value from SmartCMP form-field wrappers."""
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def extract_named_resource_specs(params: dict[str, Any]) -> list[str]:
    """Extract selected compute specification names without derived CPU/memory details.

    SmartCMP approval payloads can carry both raw fields such as ``memory`` and a
    user-facing selection such as ``Current Selection: Small,1vCPU,2GB``. When
    that selected specification is available, the approval list should show only
    the selected profile name, for example ``Small``.
    """
    if not isinstance(params, dict):
        return []

    candidates: list[str] = []
    _visit_for_spec_names(params, candidates)

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = _normalize_spec_name(candidate)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def extract_compute_profile_ids(params: dict[str, Any]) -> list[str]:
    """Extract selected compute profile/flavor IDs from SmartCMP request parameters."""
    if not isinstance(params, dict):
        return []

    ids_by_priority: dict[int, list[str]] = {0: [], 1: [], 2: []}
    _visit_for_compute_profile_ids(params, ids_by_priority)

    deduped: list[str] = []
    seen: set[str] = set()
    for priority in sorted(ids_by_priority):
        if ids_by_priority[priority]:
            candidates = ids_by_priority[priority]
            break
    else:
        candidates = []

    for raw_id in candidates:
        value = str(raw_id or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def extract_flavor_lookup_ids(params: dict[str, Any]) -> list[str]:
    """Return compute profile IDs that need external flavor-name resolution.

    A user-facing selected spec name in the request payload is already more
    precise than a secondary flavor lookup. Only unresolved profile IDs require
    the optional ``/flavors`` enrichment call.
    """
    if not isinstance(params, dict):
        return []
    if extract_named_resource_specs(params):
        return []
    return extract_compute_profile_ids(params)


def extract_flavor_name_map(payload: Any) -> dict[str, str]:
    """Build a flavor-id to display-name map from a SmartCMP /flavors response."""
    items = _extract_items(payload)
    result: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        flavor_id = _first_scalar(item.get("id"))
        name = _first_scalar(item.get("name"), item.get("displayName"), item.get("display_name"))
        if flavor_id and name:
            result[flavor_id] = name
    return result


def _visit_for_spec_names(value: Any, candidates: list[str]) -> None:
    if isinstance(value, list):
        for item in value:
            _visit_for_spec_names(item, candidates)
        return

    if not isinstance(value, dict):
        return

    labeled_value = _extract_labeled_selection_value(value)
    if labeled_value:
        candidates.append(labeled_value)

    for key, nested in value.items():
        if _is_spec_name_key(str(key)):
            candidates.extend(_candidate_strings_from_named_value(nested))
        _visit_for_spec_names(nested, candidates)


def _visit_for_compute_profile_ids(value: Any, ids_by_priority: dict[int, list[str]]) -> None:
    if isinstance(value, list):
        for item in value:
            _visit_for_compute_profile_ids(item, ids_by_priority)
        return

    if not isinstance(value, dict):
        return

    for key, nested in value.items():
        priority = _compute_profile_id_key_priority(str(key))
        if priority is not None:
            profile_id = _first_scalar(nested)
            if profile_id:
                ids_by_priority[priority].append(profile_id)
        _visit_for_compute_profile_ids(nested, ids_by_priority)


def _extract_labeled_selection_value(data: dict[str, Any]) -> str:
    label = _first_scalar(data.get("label"), data.get("displayName"), data.get("display_name"))
    if not label or not _is_selection_label(label):
        return ""

    return _first_scalar(
        data.get("value"),
        data.get("selectedValue"),
        data.get("selected_value"),
        data.get("currentValue"),
        data.get("current_value"),
    )


def _candidate_strings_from_named_value(value: Any) -> list[str]:
    unwrapped = unwrap_value(value)
    if isinstance(unwrapped, (str, int, float)):
        return [str(unwrapped)]
    if not isinstance(unwrapped, dict):
        return []

    values: list[str] = []
    for key in (
        "displayName",
        "display_name",
        "label",
        "name",
        "title",
        "text",
        "value",
    ):
        candidate = _first_scalar(unwrapped.get(key))
        if candidate:
            values.append(candidate)
    return values


def _first_scalar(*values: Any) -> str:
    for value in values:
        unwrapped = unwrap_value(value)
        if isinstance(unwrapped, (str, int, float)):
            text = str(unwrapped).strip()
            if text:
                return text
    return ""


def _is_selection_label(value: str) -> bool:
    normalized = re.sub(r"[\s_\-:：]+", "", value).lower()
    return normalized in {
        "currentselection",
        "selectedspec",
        "selectedspecification",
        "spec",
        "specification",
        "flavor",
        "computeprofile",
        "当前选择",
        "规格",
    }


def _is_spec_name_key(key: str) -> bool:
    normalized = re.sub(r"[\s_\-]+", "", key).lower()
    if "id" in normalized and "name" not in normalized and "label" not in normalized:
        return False
    if normalized in {
        "currentselection",
        "currentselectionname",
        "selectedspec",
        "selectedspecname",
        "selectedspecification",
        "selectedspecificationname",
        "selectedflavor",
        "selectedflavorname",
        "flavorname",
        "profilename",
        "computeprofilename",
        "computespecname",
        "specname",
        "specificationname",
    }:
        return True
    if "current" in normalized and "selection" in normalized:
        return True
    if "flavor" in normalized and any(part in normalized for part in ("name", "label", "display")):
        return True
    if "profile" in normalized and any(part in normalized for part in ("name", "label", "display")):
        return True
    if "spec" in normalized and any(part in normalized for part in ("name", "label", "display", "selection")):
        return True
    return False


def _compute_profile_id_key_priority(key: str) -> int | None:
    normalized = re.sub(r"[\s_\-]+", "", key).lower()
    if normalized == "computeprofileid" or normalized.endswith("computeprofileid"):
        return 0
    if normalized == "flavorid":
        return 1
    if normalized == "cloudflavorid":
        return 2
    return None


def _extract_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("content", "items", "result", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _normalize_spec_name(value: str) -> str:
    text = str(value or "").strip().strip("\"'")
    if not text:
        return ""

    text = _SPEC_LABEL_RE.sub("", text).strip()
    if not text:
        return ""

    comma_parts = [part.strip() for part in text.split(",")]
    if len(comma_parts) > 1 and any(_DETAIL_FRAGMENT_RE.search(part) for part in comma_parts[1:]):
        return comma_parts[0]

    for separator in (" - ", " / ", " ("):
        if separator not in text:
            continue
        head, tail = text.split(separator, 1)
        if _DETAIL_FRAGMENT_RE.search(tail):
            return head.strip()

    return text
