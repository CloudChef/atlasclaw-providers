#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Build a bounded, provider-neutral SmartCMP resource evidence profile."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any


MAX_PROFILE_DEPTH = 4
MAX_COLLECTION_ITEMS = 40
MAX_STRING_LENGTH = 1_000
MAX_KEY_LENGTH = 128
MAX_PROFILE_SERIALIZED = 32 * 1_024

_SENSITIVE_KEY_FRAGMENTS = (
    "apikey",
    "authentication",
    "accesstoken",
    "accesskey",
    "authorization",
    "bearer",
    "clientsecret",
    "cookie",
    "credential",
    "passphrase",
    "password",
    "passwd",
    "privatekey",
    "secret",
    "secretaccesskey",
    "secrettoken",
    "sessionkey",
    "token",
)
_INTERNAL_ID_KEYS = {
    "id",
    "resourceid",
    "nodeid",
    "nodeinstanceid",
    "uuid",
}
_PROFILE_FIELD_KEYS = {
    "name",
    "displayname",
    "resourcename",
    "componenttype",
    "resourcetype",
    "status",
    "providerstatus",
    "powerstate",
    "phase",
    "cloudprovider",
    "platform",
    "cloudentrytype",
    "cloudentryname",
    "region",
    "regionid",
    "regionname",
    "zone",
    "zoneid",
    "zonename",
    "resourcepool",
    "resourcepoolname",
    "resourcebundlename",
    "isagentinstalled",
    "monitorenabled",
    "createdat",
    "createddate",
    "updatedat",
    "updateddate",
}
_CONTAINER_KEYS = {
    "properties",
    "resourceinfo",
    "customproperties",
    "runtimeproperties",
    "extensibleproperties",
    "exts",
    "extra",
}
_ASSESSMENT_RESULT_KEYS = {
    "assessment",
    "assessmentresult",
    "assessmentresults",
    "compliance",
    "compliancefinding",
    "compliancefindings",
    "complianceresult",
    "complianceresults",
    "compliancestatus",
    "findings",
    "overallcompliance",
    "policyevaluation",
    "policyevaluations",
    "policyfinding",
    "policyfindings",
    "policyresult",
    "policyresults",
    "policyviolation",
    "policyviolations",
    "ruleevaluation",
    "ruleevaluations",
    "rulefinding",
    "rulefindings",
    "verdict",
}
_TRIMMABLE_FIXED_FIELDS = (
    ("state", "updatedAt"),
    ("state", "createdAt"),
    ("placement", "resourcePool"),
    ("placement", "zone"),
    ("placement", "region"),
    ("placement", "cloudEntry"),
    ("placement", "platform"),
    ("placement", "provider"),
    ("state", "monitorEnabled"),
    ("state", "agentInstalled"),
    ("state", "powerState"),
    ("state", "providerStatus"),
)
_UUID_RE = re.compile(
    r"(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_UUID_IN_TEXT_RE = re.compile(
    r"(?i)(?<![0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}(?![0-9a-f])"
)
_SENSITIVE_ASSIGNMENT_KEY = (
    r"password|passwd|passphrase|secret|token|cookie|authorization|credential|"
    r"api[_-]?key|access[_-]?key|private[_-]?key|client[_-]?secret|"
    r"secret[_-]?access[_-]?key|access[_-]?token|secret[_-]?token|session[_-]?key"
)
_QUOTED_SENSITIVE_ASSIGNMENT_RE = re.compile(
    rf"(?i)\b(?P<key>{_SENSITIVE_ASSIGNMENT_KEY})\b[\"']?\s*[:=]\s*"
    rf"(?P<quote>[\"'])(?P<value>.*?)(?P=quote)"
)
_BEARER_ASSIGNMENT_RE = re.compile(
    rf"(?i)\b(?P<key>{_SENSITIVE_ASSIGNMENT_KEY})\b[\"']?\s*[:=]\s*"
    rf"bearer\s+[A-Za-z0-9._~+/=-]+"
)
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    rf"(?i)\b(?P<key>{_SENSITIVE_ASSIGNMENT_KEY})\b[\"']?\s*[:=]\s*"
    rf"(?!\[REDACTED\])(?P<value>[^\s,;}}\]]+)"
)
_OMIT = object()


def build_resource_profile(
    record: dict[str, Any],
    normalized: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project one CMP record into a bounded resource-neutral LLM evidence object.

    Args:
        record: Canonical record returned by ``load_resource_records``.
        normalized: Optional shared ``type + properties`` projection.

    Returns:
        Identity, placement, state, generic attributes, and projection metadata.
        Internal UUIDs are omitted and sensitive values are redacted.
    """
    normalized = _mapping(normalized or record.get("normalized"))
    properties = _mapping(normalized.get("properties"))
    resource = _mapping(record.get("data") or record.get("resource"))
    summary = _mapping(record.get("summary"))
    details = _mapping(record.get("details"))
    sources = [properties, resource, summary]
    placement_sources = [*sources, _mapping(resource.get("cloudEntry"))]

    projection_state = {
        "redacted": 0,
        "internalIdsOmitted": 0,
        "assessmentFieldsOmitted": 0,
        "truncated": False,
    }
    identity = {
        "name": _first_text(
            sources,
            "name",
            "displayName",
            "resourceName",
            state=projection_state,
        ),
        "componentType": _first_text(
            [normalized, resource, summary, properties],
            "type",
            "componentType",
            state=projection_state,
        ),
        "resourceType": _first_text(
            sources,
            "resourceType",
            state=projection_state,
        ),
    }
    placement = _drop_empty(
        {
            "provider": _first_text(
                placement_sources,
                "cloudProvider",
                "provider",
                state=projection_state,
            ),
            "platform": _first_text(
                placement_sources,
                "platform",
                "cloudEntryType",
                state=projection_state,
            ),
            "cloudEntry": _first_text(
                placement_sources,
                "cloudEntryName",
                "cloudEntry",
                state=projection_state,
            ),
            "region": _first_text(
                placement_sources,
                "region",
                "regionName",
                "regionId",
                "location",
                state=projection_state,
            ),
            "zone": _first_text(
                placement_sources,
                "zone",
                "zoneName",
                "zoneId",
                state=projection_state,
            ),
            "resourcePool": _first_text(
                placement_sources,
                "resourcePool",
                "resourcePoolName",
                "resourceBundleName",
                state=projection_state,
            ),
        }
    )
    state = _drop_empty(
        {
            "status": _first_text(sources, "status", state=projection_state),
            "providerStatus": _first_text(
                sources,
                "providerStatus",
                "cloudStatus",
                state=projection_state,
            ),
            "powerState": _first_text(
                sources,
                "powerState",
                "phase",
                state=projection_state,
            ),
            "agentInstalled": _bounded_state_value(
                sources,
                "isAgentInstalled",
                "agentInstalled",
                state=projection_state,
            ),
            "monitorEnabled": _bounded_state_value(
                sources,
                "monitorEnabled",
                state=projection_state,
            ),
            "createdAt": _first_text(
                sources,
                "createdAt",
                "createdDate",
                state=projection_state,
            ),
            "updatedAt": _first_text(
                sources,
                "updatedAt",
                "updatedDate",
                state=projection_state,
            ),
        }
    )

    raw_attributes: dict[str, Any] = {}
    attribute_sources = [
        properties,
        _mapping(resource.get("properties")),
        _mapping(resource.get("resourceInfo")),
        _mapping(resource.get("customProperties")),
        _mapping(resource.get("RuntimeProperties")),
        _mapping(_mapping(resource.get("extensibleProperties")).get("RuntimeProperties")),
        _mapping(_mapping(resource.get("exts")).get("customProperty")),
        details,
        _mapping(resource.get("extra")),
        resource,
    ]
    for source in attribute_sources:
        for key, value in source.items():
            normalized_key = _normalized_key(key)
            if normalized_key in _PROFILE_FIELD_KEYS or normalized_key in _CONTAINER_KEYS:
                continue
            if key not in raw_attributes and value not in (None, ""):
                raw_attributes[str(key)] = value

    sanitized_attributes = _sanitize_value(
        raw_attributes,
        key="attributes",
        depth=0,
        state=projection_state,
    )
    if not isinstance(sanitized_attributes, dict):
        sanitized_attributes = {}

    profile: dict[str, Any] = {
        "identity": identity,
        "placement": placement,
        "state": state,
        "attributes": sanitized_attributes,
        "evidenceMetadata": {
            "source": (
                "cmp_legacy_fallback"
                if record.get("fallbackUsed")
                else "cmp_resource_view"
            ),
            "fieldCount": 0,
            "attributeCount": 0,
            "redactedFieldCount": projection_state["redacted"],
            "internalIdentifiersOmitted": projection_state["internalIdsOmitted"],
            "assessmentFieldsOmitted": projection_state[
                "assessmentFieldsOmitted"
            ],
            "truncated": bool(projection_state["truncated"]),
        },
    }
    _enforce_serialized_limit(profile, projection_state)
    _refresh_metadata(profile, projection_state)
    _enforce_serialized_limit(profile, projection_state)
    _refresh_metadata(profile, projection_state)
    return profile


def build_evidence_coverage(
    profile: dict[str, Any],
    record: dict[str, Any],
) -> dict[str, Any]:
    """Describe objective CMP evidence coverage without judging compliance.

    Args:
        profile: Sanitized profile returned by :func:`build_resource_profile`.
        record: Source record including fallback and collection errors.

    Returns:
        Present profile groups, structurally missing core fields, and projection flags.
    """
    identity = _mapping(profile.get("identity"))
    state = _mapping(profile.get("state"))
    metadata = _mapping(profile.get("evidenceMetadata"))
    missing = []
    if not identity.get("name"):
        missing.append("resourceProfile.identity.name")
    if not (identity.get("componentType") or identity.get("resourceType")):
        missing.append("resourceProfile.identity.type")
    if not state.get("status"):
        missing.append("resourceProfile.state.status")

    groups = []
    for key in ("identity", "placement", "state", "attributes"):
        value = profile.get(key)
        if isinstance(value, dict) and any(item not in (None, "", [], {}) for item in value.values()):
            groups.append(key)
    return {
        "source": metadata.get("source", "cmp_resource_view"),
        "groupsWithEvidence": groups,
        "missingCoreFields": missing,
        "fieldCount": metadata.get("fieldCount", 0),
        "attributeCount": metadata.get("attributeCount", 0),
        "redactedFieldCount": metadata.get("redactedFieldCount", 0),
        "internalIdentifiersOmitted": metadata.get("internalIdentifiersOmitted", 0),
        "assessmentFieldsOmitted": metadata.get("assessmentFieldsOmitted", 0),
        "truncated": bool(metadata.get("truncated")),
        "fallbackUsed": bool(record.get("fallbackUsed")),
        "collectionErrorCount": len(record.get("errors") or []),
    }


def structural_missing_evidence(profile: dict[str, Any], record: dict[str, Any]) -> list[str]:
    """Return objective retrieval/profile gaps that the LLM must consider."""
    coverage = build_evidence_coverage(profile, record)
    supplied_gaps = [
        sanitize_error_text(item)
        for item in record.get("missingEvidence") or []
    ]
    return _dedupe(
        supplied_gaps + list(coverage.get("missingCoreFields") or [])
    )


def redact_sensitive(value: Any, *, key: str = "") -> Any:
    """Return a bounded copy with sensitive values redacted.

    This compatibility helper uses the same projection rules as the generic
    profile and is safe for tests or legacy call sites that only have a value.
    """
    state = {
        "redacted": 0,
        "internalIdsOmitted": 0,
        "assessmentFieldsOmitted": 0,
        "truncated": False,
    }
    projected = _sanitize_value(value, key=key, depth=0, state=state)
    return None if projected is _OMIT else projected


def sanitize_error_text(value: Any) -> str:
    """Remove credentials and UUIDs from one user-visible collection error."""
    rendered = _redact_embedded_secrets(str(value or ""))
    rendered = _UUID_IN_TEXT_RE.sub("[internal-id]", rendered)
    rendered = " ".join(rendered.replace("\r", " ").replace("\n", " ").split())
    return rendered[:MAX_STRING_LENGTH]


def _sanitize_value(
    value: Any,
    *,
    key: str,
    depth: int,
    state: dict[str, Any],
) -> Any:
    if _is_assessment_result_key(key):
        state["assessmentFieldsOmitted"] += 1
        return _OMIT
    if _is_sensitive_key(key):
        state["redacted"] += 1
        return "[REDACTED]"
    if _is_internal_identifier(key, value):
        state["internalIdsOmitted"] += 1
        return _OMIT
    if depth >= MAX_PROFILE_DEPTH:
        state["truncated"] = True
        return "[depth-truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _sanitize_text(value, state)
    if isinstance(value, Mapping):
        projected: dict[str, Any] = {}
        items = sorted(value.items(), key=lambda item: str(item[0]))
        if len(items) > MAX_COLLECTION_ITEMS:
            state["truncated"] = True
        for nested_key, nested_value in items[:MAX_COLLECTION_ITEMS]:
            rendered_key = str(nested_key)[:MAX_KEY_LENGTH]
            projected_value = _sanitize_value(
                nested_value,
                key=rendered_key,
                depth=depth + 1,
                state=state,
            )
            if projected_value is not _OMIT:
                projected[rendered_key] = projected_value
        return projected
    if isinstance(value, (list, tuple, set)):
        items = sorted(value, key=str) if isinstance(value, set) else list(value)
        if len(items) > MAX_COLLECTION_ITEMS:
            state["truncated"] = True
        projected_items = []
        for item in items[:MAX_COLLECTION_ITEMS]:
            projected = _sanitize_value(item, key=key, depth=depth + 1, state=state)
            if projected is not _OMIT:
                projected_items.append(projected)
        return projected_items
    return _sanitize_value(str(value), key=key, depth=depth, state=state)


def _enforce_serialized_limit(profile: dict[str, Any], state: dict[str, Any]) -> None:
    attributes = profile.get("attributes")
    if isinstance(attributes, dict):
        while attributes and _serialized_size(profile) > MAX_PROFILE_SERIALIZED:
            attributes.pop(next(reversed(attributes)))
            state["truncated"] = True
    for group_name, field_name in _TRIMMABLE_FIXED_FIELDS:
        if _serialized_size(profile) <= MAX_PROFILE_SERIALIZED:
            return
        group = profile.get(group_name)
        if isinstance(group, dict) and field_name in group:
            group.pop(field_name)
            state["truncated"] = True


def _refresh_metadata(profile: dict[str, Any], state: dict[str, Any]) -> None:
    metadata = _mapping(profile.get("evidenceMetadata"))
    evidence_groups = {
        key: profile.get(key)
        for key in ("identity", "placement", "state", "attributes")
    }
    metadata.update(
        {
            "fieldCount": _count_leaf_values(evidence_groups),
            "attributeCount": len(_mapping(profile.get("attributes"))),
            "redactedFieldCount": state["redacted"],
            "internalIdentifiersOmitted": state["internalIdsOmitted"],
            "assessmentFieldsOmitted": state["assessmentFieldsOmitted"],
            "truncated": bool(state["truncated"]),
        }
    )
    profile["evidenceMetadata"] = metadata


def _serialized_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))


def _first_value(sources: list[Mapping[str, Any]], *keys: str) -> Any:
    for key in keys:
        for source in sources:
            value = source.get(key)
            if value not in (None, ""):
                return value
    return None


def _bounded_state_value(
    sources: list[Mapping[str, Any]],
    *keys: str,
    state: dict[str, Any],
) -> Any:
    value = _first_value(sources, *keys)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _sanitize_text(value, state)
    state["truncated"] = True
    return "[unsupported-non-scalar]"


def _first_text(
    sources: list[Mapping[str, Any]],
    *keys: str,
    state: dict[str, Any],
) -> str:
    value = _first_value(sources, *keys)
    if isinstance(value, Mapping):
        value = _first_value([value], "name", "displayName", "type", "code", "id")
    if value in (None, ""):
        return ""
    rendered = str(value).strip()
    return _sanitize_text(rendered, state)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _drop_empty(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item not in (None, "", [], {})}


def _normalized_key(value: Any) -> str:
    return "".join(character for character in str(value or "").casefold() if character.isalnum())


def _is_sensitive_key(value: Any) -> bool:
    normalized = _normalized_key(value)
    return any(fragment in normalized for fragment in _SENSITIVE_KEY_FRAGMENTS)


def _is_assessment_result_key(value: Any) -> bool:
    return _normalized_key(value) in _ASSESSMENT_RESULT_KEYS


def _is_internal_identifier(key: Any, value: Any) -> bool:
    normalized = _normalized_key(key)
    if normalized in _INTERNAL_ID_KEYS:
        return True
    return (
        isinstance(value, str)
        and _UUID_RE.fullmatch(value.strip()) is not None
        and (normalized.endswith("id") or normalized.endswith("uuid"))
    )


def _redact_embedded_secrets(value: str) -> str:
    rendered, _count = _redact_embedded_secrets_with_count(value)
    return rendered


def _redact_embedded_secrets_with_count(value: str) -> tuple[str, int]:
    rendered, quoted_count = _QUOTED_SENSITIVE_ASSIGNMENT_RE.subn(
        lambda match: f"{match.group('key')}=[REDACTED]",
        value,
    )
    rendered, bearer_count = _BEARER_ASSIGNMENT_RE.subn(
        lambda match: f"{match.group('key')}=[REDACTED]",
        rendered,
    )
    rendered, assignment_count = _SENSITIVE_ASSIGNMENT_RE.subn(
        lambda match: f"{match.group('key')}=[REDACTED]",
        rendered,
    )
    return rendered, quoted_count + bearer_count + assignment_count


def _sanitize_text(value: str, state: dict[str, Any]) -> str:
    rendered, redacted_count = _redact_embedded_secrets_with_count(value)
    rendered, internal_id_count = _UUID_IN_TEXT_RE.subn("[internal-id]", rendered)
    state["redacted"] += redacted_count
    state["internalIdsOmitted"] += internal_id_count
    if len(rendered) > MAX_STRING_LENGTH:
        state["truncated"] = True
        suffix = "...[TRUNCATED]"
        return f"{rendered[: MAX_STRING_LENGTH - len(suffix)]}{suffix}"
    return rendered


def _count_leaf_values(value: Any) -> int:
    if isinstance(value, Mapping):
        return sum(_count_leaf_values(item) for item in value.values())
    if isinstance(value, list):
        return sum(_count_leaf_values(item) for item in value)
    return 1 if value not in (None, "") else 0


def _dedupe(items: list[str]) -> list[str]:
    result = []
    seen = set()
    for item in items:
        rendered = str(item or "").strip()
        if rendered and rendered not in seen:
            seen.add(rendered)
            result.append(rendered)
    return result
