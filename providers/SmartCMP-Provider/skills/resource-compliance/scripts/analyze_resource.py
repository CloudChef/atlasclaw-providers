#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Collect bounded SmartCMP facts for generic LLM resource compliance analysis."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
SHARED_SCRIPT_DIR = SKILL_DIR.parent / "shared" / "scripts"
DATASOURCE_SCRIPT_DIR = SKILL_DIR.parent / "datasource" / "scripts"
RESOURCE_SCRIPT_DIR = SKILL_DIR.parent / "resource" / "scripts"

for import_root in (SHARED_SCRIPT_DIR, RESOURCE_SCRIPT_DIR):
    rendered_root = str(import_root)
    if rendered_root not in sys.path:
        sys.path.insert(0, rendered_root)

from _common import require_config
from _resource_object_actions import build_resource_object_actions
from _resource_target import (
    ResourceResolutionError,
    escape_markdown_cell,
    parse_resource_directory,
    resolve_resource_targets,
)


def _load_module_from_path(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load helper module: {module_path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


analysis_module = _load_module_from_path(
    "resource_compliance_analysis_local",
    SCRIPT_DIR / "_analysis.py",
)
profile_module = _load_module_from_path(
    "resource_compliance_profile_local",
    SCRIPT_DIR / "_resource_profile.py",
)
build_analysis_contract = analysis_module.build_analysis_contract
build_generic_analysis_result = analysis_module.build_generic_analysis_result
build_evidence_coverage = profile_module.build_evidence_coverage
build_resource_profile = profile_module.build_resource_profile
sanitize_error_text = profile_module.sanitize_error_text
structural_missing_evidence = profile_module.structural_missing_evidence


list_resource_module = _load_module_from_path(
    "resource_compliance_list_resource_local",
    DATASOURCE_SCRIPT_DIR / "list_resource.py",
)
load_resource_records = list_resource_module.load_resource_records
request_json = list_resource_module.request_json
search_resource_summaries = list_resource_module.search_resource_summaries


def _search_resource_page(page: int, size: int, resource_name: str):
    """Read one CMP page; exact matching remains client-side in the resolver."""
    base_url, _, headers, _ = require_config()
    return search_resource_summaries(
        base_url=base_url,
        headers=headers,
        request_fn=request_json,
        params={"page": page, "size": size, "queryValue": resource_name},
        payload={"queryValue": resource_name},
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse public and compatibility-only resource target parameters."""
    parser = argparse.ArgumentParser(
        description="Collect SmartCMP resource evidence for LLM compliance analysis."
    )
    parser.add_argument("positional_resource_ids", nargs="*")
    parser.add_argument("--resource-ids", nargs="*", default=[])
    parser.add_argument("--resource-name", action="append", default=[])
    parser.add_argument("--resource-index")
    parser.add_argument("--resource-directory-json")
    parser.add_argument("--trigger-source", default="user")
    parser.add_argument("--payload-json")
    return parser.parse_args(argv)


def normalize_request(args: argparse.Namespace) -> dict[str, Any]:
    """Normalize interactive or webhook input through the shared resource resolver."""
    if args.payload_json:
        payload = json.loads(args.payload_json)
        resource_ids = _split_resource_id_values(
            payload.get("resourceIds") or payload.get("resource_ids") or []
        )
        resource_names = _normalize_resource_names(
            payload.get("resourceName")
            or payload.get("resource_name")
            or payload.get("resourceNames")
            or payload.get("resource_names")
            or []
        )
        resource_index = _parse_resource_index(
            _first_present(payload.get("resourceIndex"), payload.get("resource_index"))
        )
        resource_directory_json = (
            payload.get("resourceDirectory")
            or payload.get("resource_directory")
            or payload.get("resourceDirectoryJson")
            or payload.get("resource_directory_json")
            or ""
        )
        trigger_source = (
            payload.get("triggerSource")
            or payload.get("trigger_source")
            or args.trigger_source
        )
        raw_metadata = payload.get("rawMetadata") or payload
    else:
        resource_ids = _split_resource_id_values(args.resource_ids)
        resource_ids.extend(_split_resource_id_values(args.positional_resource_ids))
        resource_names = _normalize_resource_names(args.resource_name)
        resource_index = _parse_resource_index(args.resource_index)
        resource_directory_json = args.resource_directory_json
        trigger_source = args.trigger_source
        raw_metadata = {}

    directory_items = parse_resource_directory(resource_directory_json)
    resource_ids, requested_resources, resolved_resources = resolve_resource_targets(
        resource_ids=resource_ids,
        resource_names=resource_names,
        resource_index=resource_index,
        directory_items=directory_items,
        trigger_source=trigger_source,
        search_page=_search_resource_page,
    )
    return {
        "resourceIds": resource_ids,
        "requestedResources": requested_resources,
        "resolvedResources": resolved_resources,
        "triggerSource": trigger_source,
        "rawMetadata": raw_metadata,
    }


def _split_resource_id_values(values: Any) -> list[str]:
    """Return de-duplicated internal resource IDs from compatibility inputs."""
    if values in (None, ""):
        return []
    raw_values = _as_list(values)
    resource_ids = []
    for value in raw_values:
        for candidate in str(value).replace(",", " ").split():
            normalized = candidate.strip()
            if normalized and normalized not in resource_ids:
                resource_ids.append(normalized)
    return resource_ids


def _normalize_resource_names(values: Any) -> list[str]:
    """Return explicit names without splitting names that contain spaces."""
    if values in (None, ""):
        return []
    raw_values = _as_list(values)
    names = []
    for value in raw_values:
        normalized = str(value).strip()
        if normalized and normalized not in names:
            names.append(normalized)
    return names


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _parse_resource_index(value: Any) -> int | None:
    """Parse a positive user-visible list index."""
    if value in (None, ""):
        return None
    try:
        index = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ResourceResolutionError("Resource index must be a positive integer.") from exc
    if index <= 0:
        raise ResourceResolutionError("Resource index must be a positive integer.")
    return index


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def load_resources(resource_ids: list[str]) -> list[dict[str, Any]]:
    """Load canonical read-only CMP resource records."""
    base_url, _, headers, _ = require_config()
    return load_resource_records(
        resource_ids,
        base_url=base_url,
        headers=headers,
        request_fn=request_json,
    )


def resolve_action_context() -> str:
    """Resolve the CMP base URL used only for read-only object actions."""
    try:
        base_url, _, _, _instance = require_config()
    except (Exception, SystemExit):
        return ""
    return str(base_url or "")


def attach_resource_object_metadata(
    result: dict[str, Any],
    index: int,
    *,
    base_url: str = "",
) -> dict[str, Any]:
    """Attach internal workflow identity and read-only resource actions."""
    resource_id = str(result.get("resourceId") or "").strip()
    resource_name = str(result.get("resourceName") or "").strip()
    result.update(
        {
            "index": index,
            "object_type": "smartcmp_resource",
            "object_id": resource_id,
            "object_name": resource_name or "resource",
            "object_actions": build_resource_object_actions(
                base_url,
                resource_id,
                resource_name=resource_name,
                include_detail_action=bool(resource_name),
                include_analysis_action=bool(resource_name),
            ),
        }
    )
    return result


def build_result(record: dict[str, Any], *, analysis_status: str) -> dict[str, Any]:
    """Build one generic resource evidence result from a CMP record."""
    profile = build_resource_profile(record)
    coverage = build_evidence_coverage(profile, record)
    errors = [sanitize_error_text(item) for item in record.get("errors") or []]
    result = build_generic_analysis_result(
        resource_profile=profile,
        evidence_coverage=coverage,
        missing_evidence=structural_missing_evidence(profile, record),
        errors=errors,
        analysis_status=analysis_status,
    )
    identity = profile.get("identity") or {}
    result.update(
        {
            "resourceId": str(record.get("resourceId") or ""),
            "resourceName": str(identity.get("name") or ""),
            "resourceType": str(identity.get("resourceType") or ""),
        }
    )
    return result


def render_output(payload: dict[str, Any]) -> str:
    """Render a non-judgmental evidence summary plus structured LLM context."""
    lines = [f"Collected compliance evidence for {payload['analyzedCount']} resource(s)."]
    if payload["failedCount"]:
        lines.append(f"Failed to fully collect {payload['failedCount']} resource(s).")
    lines.extend(
        [
            "",
            "| # | Resource | Type | CMP Status | Evidence |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for index, item in enumerate(payload["results"], start=1):
        profile = item.get("resourceProfile") or {}
        identity = profile.get("identity") or {}
        state = profile.get("state") or {}
        lines.append(
            "| "
            + " | ".join(
                escape_markdown_cell(value)
                for value in (
                    index,
                    item.get("resourceName") or "unknown resource",
                    identity.get("componentType") or identity.get("resourceType") or "unknown",
                    state.get("status") or "unknown",
                    item.get("analysisStatus") or "unknown",
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "##RESOURCE_COMPLIANCE_START##",
            json.dumps(payload, ensure_ascii=False),
            "##RESOURCE_COMPLIANCE_END##",
        ]
    )
    return "\n".join(lines)


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def main(argv: list[str] | None = None) -> int:
    """Collect CMP evidence and emit the generic LLM analysis context."""
    try:
        request = normalize_request(parse_args(argv))
    except (ResourceResolutionError, ValueError, json.JSONDecodeError) as exc:
        print(f"[ERROR] {sanitize_error_text(exc)}")
        return 1

    try:
        resource_records = load_resources(request["resourceIds"])
    except Exception:  # pragma: no cover - provider failures surface at runtime
        print("[ERROR] Failed to load the selected SmartCMP resource data.")
        return 1

    action_base_url = resolve_action_context()
    results = []
    analyzed_count = 0
    failed_count = 0
    for index, record in enumerate(resource_records, start=1):
        fetch_ok = record.get("fetchStatus") == "ok"
        result = build_result(
            record,
            analysis_status="evidence_collected" if fetch_ok else "fetch_failed",
        )
        results.append(
            attach_resource_object_metadata(result, index, base_url=action_base_url)
        )
        if fetch_ok:
            analyzed_count += 1
        else:
            failed_count += 1

    payload = {
        "triggerSource": request["triggerSource"],
        "requestedResourceIds": request["resourceIds"],
        "requestedResources": request["requestedResources"],
        "resolvedResources": request["resolvedResources"],
        "analyzedCount": analyzed_count,
        "failedCount": failed_count,
        "generatedAt": _now_iso(),
        "analysisContract": build_analysis_contract(),
        "results": results,
    }
    print(render_output(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
